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
    target = body.get("target")  # "ado" | "gitlab"
    try:
        yaml_str = to_ado_yaml(spec) if target == "ado" else to_gitlab_yaml(spec)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    path = "azure-pipelines.yml" if target == "ado" else ".gitlab-ci.yml"
    branch = body.get("branch") or f"feature/pipeline-{_slug(spec.name)}"
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
    return jsonify(result)
