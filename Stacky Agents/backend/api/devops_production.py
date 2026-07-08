"""api/devops_production.py — Plan 95 F3. Blueprint del flujo "Llevar a producción"
(MR/PR con merge HITL). url_prefix SIN /api (patrón devops_variables.py)."""
from flask import Blueprint, abort, request
from werkzeug.exceptions import HTTPException
import config as _config
from services.merge_request_provider import get_merge_request_provider
from services.tracker_provider import TrackerConfigError, TrackerApiError

bp = Blueprint("devops_production", __name__, url_prefix="/devops/production")


def _guard():
    """Guard de flag y CSRF (91 C5, espejo devops_variables.py)."""
    if not getattr(_config.config, "STACKY_DEVOPS_PRODUCTION_ENABLED", False):
        abort(404)
    if request.method in ("POST", "PUT", "DELETE") and not request.is_json:
        abort(400, description="Content-Type application/json requerido")


def _call_provider(fn):
    """Mapeo ÚNICO de excepciones para todas las rutas (espejo devops_variables.py C6/C14).

    HTTPException (abort explícito de la vista) NUNCA cae al 500 genérico.
    """
    try:
        return fn()
    except TrackerConfigError as e:
        return {"error": str(e), "kind": "tracker_config"}, 400
    except TrackerApiError as e:
        return {"error": str(e), "kind": e.kind}, e.status or 502
    except HTTPException:
        raise
    except Exception:
        return {"error": "error interno de producción"}, 500


def _default_branch(provider, project):
    """Plan 95 F3 — default branch del repo, por tracker.

    GitLab: GET /projects/:id → campo default_branch.
    ADO: delega en services.ado_pipeline_definitions._default_branch (F1.a),
    que ya resuelve repo_id y hace el GET del repositorio.
    """
    if provider.name == "azure_devops":
        from services.ado_pipeline_definitions import _default_branch as _ado_default_branch  # noqa: PLC0415
        return _ado_default_branch(provider, project)

    # GitLab
    proj_path = provider._client._project_path()
    body, _ = provider._client._request("GET", f"/projects/{proj_path}")
    return body.get("default_branch") or "main"


@bp.route("/mr", methods=["POST"])
def create_mr():
    """POST /devops/production/mr — crea el MR/PR (HITL con confirm)."""
    _guard()

    def _do_create():
        body = request.get_json()
        project = body.get("project")
        source_branch = body.get("source_branch")
        target_branch = body.get("target_branch")
        title = body.get("title")
        confirm = body.get("confirm")

        if confirm is not True:
            abort(400, description="confirm=true requerido")
        if not source_branch:
            abort(400, description="source_branch requerido")

        provider = get_merge_request_provider(project)
        if not target_branch:
            target_branch = _default_branch(provider, project)
        if not title:
            title = f"pipeline: {source_branch}"

        result = provider.create_merge_request(source_branch, target_branch, title, "")
        return result, 201

    return _call_provider(_do_create)


@bp.route("/mr/<mr_id>", methods=["GET"])
def get_mr(mr_id: str):
    """GET /devops/production/mr/<mr_id>?project= — polling del estado."""
    _guard()

    def _do_get():
        project = request.args.get("project")
        provider = get_merge_request_provider(project)
        return provider.get_merge_request(mr_id)

    return _call_provider(_do_get)


@bp.route("/mr/<mr_id>/merge", methods=["POST"])
def merge_mr(mr_id: str):
    """POST /devops/production/mr/<mr_id>/merge — mergea (HITL con confirm)."""
    _guard()

    def _do_merge():
        body = request.get_json()
        project = body.get("project")
        confirm = body.get("confirm")

        if confirm is not True:
            abort(400, description="confirm=true requerido")

        provider = get_merge_request_provider(project)
        return provider.merge_merge_request(mr_id)

    return _call_provider(_do_merge)


@bp.route("/ado/ensure-definition", methods=["POST"])
def ensure_ado_definition():
    """POST /devops/production/ado/ensure-definition — crea la pipeline definition
    ADO si falta (HITL con confirm). En proyectos GitLab ⇒ 400."""
    _guard()

    def _do_ensure():
        from services.project_context import resolve_project_context  # noqa: PLC0415
        from services.ado_pipeline_definitions import (  # noqa: PLC0415
            ensure_yaml_definition,
            DefinitionConfirmRequired,
        )

        body = request.get_json()
        project = body.get("project")
        confirm = body.get("confirm")

        ctx = resolve_project_context(project_name=project)
        tracker_type = (getattr(ctx, "tracker_type", None) or "azure_devops").strip().lower()
        if tracker_type != "azure_devops":
            return {"error": "solo aplica a proyectos ADO"}, 400

        if confirm is not True:
            abort(400, description="confirm=true requerido")

        try:
            return ensure_yaml_definition(project, confirm=True)
        except DefinitionConfirmRequired as e:
            # No debería ocurrir (confirm ya validado arriba), pero por las dudas
            # se traduce a un 409 honesto en vez de un 500.
            return {"error": str(e), "kind": "ado_definition_confirm_required"}, 409

    return _call_provider(_do_ensure)
