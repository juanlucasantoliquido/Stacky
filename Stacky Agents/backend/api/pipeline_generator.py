"""
api/pipeline_generator.py — Blueprint generador declarativo de pipelines ADO/GitLab.

Plan 73 F5 — endpoints /preview y /commit con HITL.

Blueprint registrado SIEMPRE en api/__init__.py sobre api_bp (url_prefix="/api").
url_prefix="/pipeline-generator" → ruta final /api/pipeline-generator/...
FIX C2: NO url_prefix="/api/pipeline-generator" (daría /api/api/...) y NO registrar en app.py.
Guard de la flag es PER-REQUEST (abort(404)) — no gated en el registro del blueprint.
"""
from __future__ import annotations

import re

import config as _config
from flask import Blueprint, abort, jsonify, request

from services.pipeline_spec import dict_to_spec
from services.pipeline_renderers import to_ado_yaml, to_gitlab_yaml
from services.repo_writer import get_repo_writer
from services.tracker_provider import TrackerApiError

# url_prefix="/pipeline-generator" → /api/pipeline-generator/... (C2)
bp = Blueprint("pipeline_generator", __name__, url_prefix="/pipeline-generator")


def _target_efectivo(body: dict) -> tuple[str, str]:
    """Plan 288 — (target, origen) de la escritura. El PROYECTO manda.

    `get_repo_writer(project)` ya resuelve el repositorio por el tracker del
    proyecto, así que un `target` que no coincida con ese tracker sólo puede
    producir un archivo mal formado en el repo correcto: YAML de ADO dentro de
    un repo de GitLab, o al revés. No hay caso legítimo en el que ganen los dos.

    Por eso: si el proyecto DECLARA tracker, gana el proyecto (origen
    "project"). Si no lo declara — proyecto ausente, sin config, o tracker sin
    pipelines (jira/mantis) — manda el cuerpo (origen "body"), que es el
    comportamiento byte-idéntico al previo a este plan.

    NUNCA lanza: el resolvedor de `services/project_context.py` ya es a prueba
    de todo y devuelve "" cuando no puede.
    """
    from services.project_context import provider_de_pipeline_del_proyecto

    del_proyecto = provider_de_pipeline_del_proyecto(body.get("project"))
    if del_proyecto:
        return del_proyecto, "project"
    return body.get("target"), "body"


def _slug(name: str) -> str:
    """FIX C11: nombre de rama git válido a partir de spec.name.
    [a-z0-9._-]; strip('-'); fallback 'pipeline'."""
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", (name or "").strip().lower()).strip("-")
    return s or "pipeline"


@bp.post("/preview")
def preview_route():
    """Renderiza PipelineSpec → YAML ADO + GitLab. PURO (sin commit)."""
    if not getattr(_config.config, "STACKY_PIPELINE_GENERATOR_ENABLED", False):
        abort(404)   # guard per-request (C2)
    body = request.get_json(silent=True) or {}
    spec = dict_to_spec(body)
    errors = spec.validate()
    if errors:
        return jsonify({"errors": [{"field": e.field, "message": e.message} for e in errors]}), 400
    try:
        ado = to_ado_yaml(spec)
        gitlab = to_gitlab_yaml(spec)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ado": ado, "gitlab": gitlab})


@bp.post("/commit")
def commit_route():
    """Commitea YAML renderizado al repo del tracker. HITL obligatorio (confirm=True)."""
    if not getattr(_config.config, "STACKY_PIPELINE_GENERATOR_ENABLED", False):
        abort(404)   # guard per-request (C2)
    body = request.get_json(silent=True) or {}
    # RIEL ABSOLUTO — HITL (F5 caso 4, gate de significancia)
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm=True requerido (HITL)"}), 400
    spec = dict_to_spec(body)
    errors = spec.validate()
    if errors:
        return jsonify({"errors": [{"field": e.field, "message": e.message} for e in errors]}), 400
    # Plan 288 — "ado" | "gitlab". El proyecto manda sobre el cuerpo (ver
    # _target_efectivo); sin proyecto resoluble, el cuerpo decide como siempre.
    target, target_source = _target_efectivo(body)
    try:
        yaml_str = to_ado_yaml(spec) if target == "ado" else to_gitlab_yaml(spec)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    path = "azure-pipelines.yml" if target == "ado" else ".gitlab-ci.yml"
    branch = body.get("branch") or f"feature/pipeline-{_slug(spec.name)}"

    # Plan 260 F5.2 — gate de secretos ANTES de escribir. MISMA decision binaria
    # que arriba elige el renderer/la ruta (`target == "ado"`): `target` NO esta
    # validado (viene de body.get pelado), pasarlo crudo al motor de reglas
    # apagaria SEC003/SEC005/SEC007 en silencio (cicd_security_rules.py).
    if getattr(_config.config, "STACKY_PIPELINE_SECRET_COMMIT_GATE_ENABLED", False):
        from services.ci_env_gate import evaluar_gate_secretos  # noqa: PLC0415

        prov_reglas = "ado" if target == "ado" else "gitlab"
        duros, auditado = evaluar_gate_secretos(yaml_str, provider=prov_reglas)
        if not auditado:
            return jsonify({"error": "no se pudo auditar el YAML: no se commitea",
                            "kind": "secret_gate_indeterminado"}), 422
        if duros:
            return jsonify({"error": "el YAML contiene un secreto literal",
                            "kind": "secret_in_yaml",
                            "findings": [{"code": c, "location": loc, "message": m}
                                        for c, loc, m in duros]}), 422

    try:
        writer = get_repo_writer(body.get("project"))
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    try:
        result = writer.commit_file(
            path=path,
            content=yaml_str,
            branch=branch,
            message=f"pipeline({spec.name}): update via Stacky",
        )
    except TrackerApiError as e:
        # FIX C1 — 403/404/etc real de GitLab; _request ya lo lanzó
        return jsonify({"error": str(e), "kind": getattr(e, "kind", "")}), e.status
    except NotImplementedError as e:
        # ADO render-only v1 (C12)
        return jsonify({"error": str(e)}), 501
    # Plan 288 — el operador tiene que poder VER a qué proveedor fue y por qué:
    # sin esto, "el proyecto ganó" es una decisión invisible. Copia: el dict del
    # writer no se muta.
    return jsonify({
        **(result if isinstance(result, dict) else {"result": result}),
        # Espejo EXACTO de la decisión que se tomó arriba para elegir renderer y
        # ruta (`target == "ado"`): informa lo que pasó, no lo que se pidió.
        "target": "ado" if target == "ado" else "gitlab",
        "target_source": target_source,
    })
