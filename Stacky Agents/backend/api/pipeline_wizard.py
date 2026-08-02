"""api/pipeline_wizard.py — Plan 294 F6. Blueprint del asistente guiado.

url_prefix="/pipeline-wizard" -> ruta final /api/pipeline-wizard/...
NO poner url_prefix="/api/..." (daria /api/api/...) y NO registrar en app.py:
se registra sobre api_bp en api/__init__.py.
Guard de la flag PER-REQUEST (abort(404)), nunca gateado en el registro.

DELGADO A PROPOSITO: este modulo no decide nada. Valida el cuerpo, llama a
services/ y serializa. Cero logica de dominio.

NO DEFINE ENDPOINT DE ESCRITURA: el paso 7 reusa /api/pipeline-generator/commit
y /api/ci/<p>/trigger, que ya tienen su confirmacion explicita. No se crea un
tercero: dos pantallas de confirmacion distintas para el mismo acto ya es una
deuda conocida de este cockpit, y este plan no la agranda.

CERO GASTO EN REPOSO: los 4 endpoints son deterministas. No hay bucle, ni tarea
de fondo, ni barrido, ni precarga, ni una sola llamada a un modelo.
"""
from __future__ import annotations

import config as _config
from flask import Blueprint, abort, jsonify, request

bp = Blueprint("pipeline_wizard", __name__, url_prefix="/pipeline-wizard")


def _gate():
    # GOTCHA: leer la INSTANCIA (_config.config), no el modulo. getattr del modulo
    # devuelve el default y mata el branch apagado (el test pasaria en falso).
    if not getattr(_config.config, "STACKY_PIPELINE_WIZARD_ENABLED", False):
        abort(404)


def _cuerpo() -> dict:
    return request.get_json(silent=True) or {}


@bp.get("/detect")
def wizard_detect_route():
    """Paso 1 completo: sondeo del proyecto + inventario descripto. READ-ONLY."""
    _gate()
    from services.pipeline_project_probe import probe_project   # noqa: PLC0415

    project = request.args.get("project") or None
    refresh = (request.args.get("refresh") or "").strip().lower() in ("1", "true", "yes")
    return jsonify(probe_project(project, refresh=refresh))


@bp.post("/questions")
def wizard_questions_route():
    """Paso 3: las preguntas que ESTE objetivo necesita, y ninguna mas."""
    _gate()
    from services.pipeline_wizard_schema import (   # noqa: PLC0415
        WIZARD_GOALS,
        default_answers,
        questions_for,
        visible_questions,
    )

    body = _cuerpo()
    goal = str(body.get("goal") or "").strip()
    conocidos = {g.id for g in WIZARD_GOALS}
    if goal not in conocidos:
        return jsonify({"errors": [
            f"No reconozco el objetivo {goal!r}. Eleg" + "i uno de la lista del paso anterior."
        ]}), 400

    qs = questions_for(
        goal,
        stack=str(body.get("stack") or ""),
        provider=str(body.get("provider") or ""),
        has_docker=bool(body.get("has_docker")),
        known=body.get("known") if isinstance(body.get("known"), dict) else None,
    )
    visibles = visible_questions(
        qs, body.get("answers") if isinstance(body.get("answers"), dict) else {}
    )
    return jsonify({
        "goal": goal,
        "questions": [_pregunta_a_dict(q) for q in visibles],
        "defaults": default_answers(
            goal, str(body.get("stack") or ""), str(body.get("provider") or "")
        ),
    })


def _pregunta_a_dict(q) -> dict:
    return {
        "id": q.id,
        "label": q.label,
        "help": q.help,
        "example": q.example,
        "kind": q.kind,
        "options": list(q.options),
        "default": q.default,
        "required": q.required,
        "depends_on": [list(par) for par in q.depends_on],
        "autofilled_from": q.autofilled_from,
    }


def _intent_o_400(body: dict):
    """(intent, respuesta_de_error). Exactamente uno de los dos es None."""
    from services.pipeline_intent import (   # noqa: PLC0415
        intent_from_dict,
        intent_to_dict,
        validate_intent,
    )

    intent = intent_from_dict(body)
    motivos = validate_intent(intent)
    if motivos:
        return None, (jsonify({"errors": motivos}), 400)
    try:
        intent_to_dict(intent)   # R3: un valor colado en la lista de nombres corta aca
    except ValueError as exc:
        return None, (jsonify({"errors": [str(exc)]}), 400)
    return intent, None


@bp.post("/draft")
def wizard_draft_route():
    """Paso 5: la intencion se vuelve borrador con el motor que YA existe.

    No se escribe un renderizador nuevo: se importa el del plan 73, en proceso.
    """
    _gate()
    from services.pipeline_intent import intent_to_spec   # noqa: PLC0415
    from services.pipeline_renderers import to_ado_yaml, to_gitlab_yaml   # noqa: PLC0415
    from services.pipeline_spec import dict_to_spec   # noqa: PLC0415

    body = _cuerpo()
    intent, error = _intent_o_400(body)
    if error is not None:
        return error

    spec_dict = intent_to_spec(intent)
    try:
        spec = dict_to_spec(spec_dict)
    except Exception as exc:      # noqa: BLE001 — spec malformado es 400, nunca 500
        return jsonify({"errors": [f"No pude armar el borrador: {exc}"]}), 400

    errores = spec.validate()
    if errores:
        return jsonify({"errors": [f"{e.field}: {e.message}" for e in errores]}), 400

    return jsonify({
        "spec": spec_dict,
        "ado": to_ado_yaml(spec),
        "gitlab": to_gitlab_yaml(spec),
        "proposed_path": _proposed_path(intent.provider),
    })


def _proposed_path(provider: str) -> str:
    from services.pipeline_session import PIPELINE_FILENAME   # noqa: PLC0415

    return PIPELINE_FILENAME.get((provider or "").strip().lower(), "")


@bp.post("/review")
def wizard_review_route():
    """Paso 6: que va a pasar, en castellano, con advertencias y bloqueantes
    SEPARADOS. Ningun endpoint devuelve un VALOR de variable: solo nombres."""
    _gate()
    from services.pipeline_intent import intent_to_spec   # noqa: PLC0415
    from services.pipeline_lint import lint_yaml   # noqa: PLC0415
    from services.pipeline_renderers import to_ado_yaml, to_gitlab_yaml   # noqa: PLC0415
    from services.pipeline_spec import dict_to_spec   # noqa: PLC0415

    body = _cuerpo()
    intent, error = _intent_o_400(body)
    if error is not None:
        return error

    proveedor = "gitlab" if intent.provider == "gitlab" else "ado"
    try:
        spec = dict_to_spec(intent_to_spec(intent))
        texto = to_gitlab_yaml(spec) if proveedor == "gitlab" else to_ado_yaml(spec)
    except Exception as exc:      # noqa: BLE001
        return jsonify({"errors": [f"No pude armar el borrador: {exc}"]}), 400

    warnings: list[dict] = []
    blocking: list[dict] = []
    try:
        reporte = lint_yaml(texto, proveedor, known_variables=list(intent.variables))
        for f in reporte.findings:
            fila = {"code": f.code, "message": f.message, "line": f.line, "node": f.node}
            (blocking if f.severity == "error" else warnings).append(fila)
    except Exception as exc:      # noqa: BLE001 — la revision degrada, no rompe
        warnings.append({"code": "", "message": f"No pude revisar el borrador: {exc}",
                         "line": None, "node": None})

    ficha = _ficha_en_castellano(texto, intent)
    return jsonify({
        "provider": proveedor,
        "yaml": texto,
        "warnings": warnings,
        "blocking": blocking,
        "missing_variables": _faltantes(intent),
        "summary": ficha,
        "proposed_path": _proposed_path(intent.provider),
    })


def _ficha_en_castellano(texto: str, intent) -> dict:
    """Reusa describe_pipeline: la frase determinista, sin modelo, del plan 247."""
    from services.pipeline_inventory import describe_pipeline, make_entry   # noqa: PLC0415

    entrada = make_entry(
        provider=("gitlab" if intent.provider == "gitlab" else "azure_devops"),
        name=intent.project or "pipeline",
        yaml_path=_proposed_path(intent.provider),
        default_branch=intent.default_branch or None,
        definition_id=None,
        category="en_repo_sin_registrar",
        trigger={"kind": "ci", "branches": list(intent.triggers)},
    )
    ficha = describe_pipeline(entrada, texto)
    return {
        "purpose": ficha.get("purpose", ""),
        "purpose_source": ficha.get("purpose_source", "sin_datos"),
        "when_es": ficha.get("when_es", ""),
        "stages_es": ficha.get("stages_es", []),
        "artifacts_es": ficha.get("artifacts_es", []),
        "environments_es": ficha.get("environments_es", []),
    }


def _faltantes(intent) -> list[str]:
    """SOLO NOMBRES. Los secretos declarados que todavia no estan cargados."""
    from services.ci_variables import get_variables_provider   # noqa: PLC0415

    declarados = [str(n) for n in intent.required_secrets if str(n).strip()]
    if not declarados:
        return []
    try:
        cargados = {
            str(v.get("key") or "")
            for v in get_variables_provider(intent.project or None).list_variables()
        }
    except Exception:      # noqa: BLE001 — sin acceso al proveedor no se puede afirmar
        return declarados
    return [n for n in declarados if n not in cargados]
