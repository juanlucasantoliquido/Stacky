"""api/devops_variables.py — Plan 94 F3. Blueprint de variables CI."""
from flask import Blueprint, abort, request
from werkzeug.exceptions import HTTPException
import config as _config
from services.ci_variables import VariablesUnavailableError, get_variables_provider
from services.tracker_provider import TrackerConfigError, TrackerApiError

bp = Blueprint("devops_variables", __name__, url_prefix="/devops/variables")


def _guard():
    """Guard de flag y CSRF (C6, 91 C5)."""
    if not getattr(_config.config, "STACKY_DEVOPS_VARIABLES_ENABLED", False):
        abort(404)
    if request.method in ("POST", "PUT", "DELETE") and not request.is_json:
        abort(400, description="Content-Type application/json requerido")


def _call_provider(fn):
    """C6/C14 — mapeo ÚNICO para TODAS las rutas.

    Ejecuta fn() y traduce excepciones en este orden:
    - VariablesUnavailableError → 409 con kind
    - TrackerConfigError → 400 con kind (C14a)
    - TrackerApiError → 502 (ya viene sanitizada de F2)
    - Exception → 500 con mensaje genérico (C14b)
    """
    try:
        return fn()
    except VariablesUnavailableError as e:
        return {"error": str(e), "kind": "variables_unavailable"}, 409
    except TrackerConfigError as e:
        return {"error": str(e), "kind": "tracker_config"}, 400
    except TrackerApiError as e:
        return {"error": str(e)}, e.status or 502
    except HTTPException:
        # abort(400)/abort(404) explícitos de la vista (confirm HITL, key
        # inválida, delete ausente) NO son errores inesperados: deben propagar
        # tal cual, no colapsar al 500 genérico de abajo.
        raise
    except Exception:
        return {"error": "error interno de variables"}, 500


@bp.route("", methods=["GET"])
def list_variables():
    """GET /devops/variables?project= → lista variables sin valores."""
    _guard()

    def _do_list():
        project = request.args.get("project")
        provider = get_variables_provider(project)
        variables = provider.list_variables()
        return {"variables": variables, "provider": provider.name}

    return _call_provider(_do_list)


@bp.route("", methods=["POST"])
def create_variable():
    """POST /devops/variables → crea variable (HITL con confirm)."""
    _guard()

    def _do_create():
        body = request.get_json()
        project = body.get("project")
        key = body.get("key")
        value = body.get("value")
        secret = body.get("secret", False)
        confirm = body.get("confirm")

        if confirm is not True:
            abort(400, description="confirm=true requerido")

        # Validar key
        from services.ci_variables import validate_variable_key
        error = validate_variable_key(key)
        if error:
            abort(400, description=error)

        provider = get_variables_provider(project)
        result = provider.set_variable(key, value, secret)
        return result, 201

    return _call_provider(_do_create)


@bp.route("/delete", methods=["POST"])
def delete_variable():
    """POST /devops/variables/delete → borra variable (HITL con confirm)."""
    _guard()

    def _do_delete():
        body = request.get_json()
        project = body.get("project")
        key = body.get("key")
        confirm = body.get("confirm")

        if confirm is not True:
            abort(400, description="confirm=true requerido")

        provider = get_variables_provider(project)
        deleted = provider.delete_variable(key)
        if not deleted:
            abort(404, description="Variable no encontrada")
        return {"ok": True}

    return _call_provider(_do_delete)
