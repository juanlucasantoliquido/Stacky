"""api/pipeline_environments.py — Blueprint de la matriz de entornos. Plan 251 F4.

url_prefix="/pipeline-environments" -> ruta final /api/pipeline-environments/...
Guard PER-REQUEST (abort(404)), nunca gateado en el registro del blueprint.

SOLO LECTURA: no escribe en el repo, ni en el proveedor, ni en el disco del operador.
POST es por TRANSPORTE (el YAML viaja en el body, mismo patron que
POST /api/devops/parse-yaml del plan 87), no por semantica.
"""
from __future__ import annotations

import config as _config
from flask import Blueprint, abort, jsonify, request

from services.pipeline_env_resolver import resolve
from services.pipeline_environments import (
    PROVIDER_GITLAB,
    PROVIDERS,
    build_matrix,
    derive_environments,
    extract_requirements,
    to_json_payload,
)
from services.secret_masking import strip_secret_keys

bp = Blueprint("pipeline_environments", __name__, url_prefix="/pipeline-environments")

MAX_YAML_CHARS = 500_000


def _guard():
    # GOTCHA dura: la INSTANCIA (_config.config), no el modulo: getattr del modulo
    # devuelve el default y mata el branch OFF (el test flag-off pasaria en falso).
    if not getattr(_config.config, "STACKY_PIPELINE_ENV_MATRIX_ENABLED", False):
        abort(404)
    if request.method == "POST" and not request.is_json:
        abort(400, description="Content-Type application/json requerido")


def _guard_declare():
    """Plan 260 — guard de la ruta de ESCRITURA. Exige LAS DOS flags: la del
    blueprint (matriz) y la propia de declaracion. _guard() ya usa la
    INSTANCIA (_config.config); acá se repite el mismo patrón para la propia."""
    _guard()                                   # 404 si la matriz esta OFF + chequeo de JSON
    if not getattr(_config.config, "STACKY_PIPELINE_ENV_DECLARE_ENABLED", False):
        abort(404)


def _matriz_para_declarar(body: dict):
    """Plan 260 — mismo armado que /analyze (SIEMPRE resuelto contra el
    proveedor: F2/F3 necesitan saber que falta de VERDAD). Devuelve
    (matriz, provider, error_response); error_response es None si todo ok."""
    provider = str(body.get("provider") or "")
    if provider not in PROVIDERS:
        return None, None, (jsonify({
            "error": "provider_no_soportado",
            "detail": "provider debe ser uno de: %s" % ", ".join(PROVIDERS)}), 400)

    yaml_text = body.get("yaml_text")
    if not isinstance(yaml_text, str) or not yaml_text.strip():
        return None, None, (jsonify({"error": "yaml_text_requerido"}), 400)
    if len(yaml_text) > MAX_YAML_CHARS:
        return None, None, (jsonify({
            "error": "yaml_demasiado_grande",
            "detail": "YAML demasiado grande (máx 500 KB)"}), 400)

    project = body.get("project")
    requisitos = extract_requirements(yaml_text, provider)
    entornos = derive_environments(yaml_text, provider)

    from services.pipeline_env_resolver import list_scoped_variables  # noqa: PLC0415
    _vars, scopes, deg_scopes = list_scoped_variables(project)
    if scopes:
        entornos = derive_environments(yaml_text, provider, tuple(scopes))
    resoluciones, deg_resolve = resolve(
        requisitos, entornos, provider, project=project, use_provider=True,
        yaml_text=yaml_text)
    degradaciones = tuple(deg_scopes) + tuple(d for d in deg_resolve if d not in deg_scopes)

    matriz = build_matrix(requisitos, entornos, resoluciones, provider, degraded=degradaciones)
    return matriz, provider, None


def _mensaje_declare_seguro(e: Exception) -> str:
    """PROHIBIDO str(e) de una excepcion desconocida (KPI-5): puede traer el
    cuerpo de la respuesta del proveedor."""
    from services.tracker_provider import TrackerApiError  # noqa: PLC0415

    if isinstance(e, TrackerApiError):
        return "El proveedor no pudo guardar esta variable (código %s)" % getattr(e, "status", "?")
    return "Error interno al declarar esta variable"


@bp.route("/declare-preview", methods=["POST"])
def declare_preview():
    """body: {yaml_text, provider, project} -> plan + los DOS contadores
    (ADICIÓN 3). SOLO LECTURA: guard = la flag de la matriz nada más (ver que
    se declararía no necesita la flag de escritura)."""
    _guard()
    from services.pipeline_env_declare import (  # noqa: PLC0415
        pendiente_visible,
        plan_declaration,
        proyectar_celdas,
    )

    body = request.get_json(silent=True) or {}
    matriz, provider, error = _matriz_para_declarar(body)
    if error is not None:
        return error

    plan = plan_declaration(matriz, provider)
    actual = pendiente_visible(matriz.cells)
    proyectado = pendiente_visible(proyectar_celdas(matriz.cells, plan))

    return jsonify({
        "plan": {
            "items": [{"key": i.key, "secret": i.secret, "reason": i.reason, "note": i.note}
                      for i in plan.items],
            "skipped": [{"key": k, "motivo": m} for k, m in plan.skipped],
            "provider": plan.provider,
        },
        "pendiente_visible_actual": actual,
        "pendiente_visible_proyectado": proyectado,
    }), 200


@bp.route("/declare", methods=["POST"])
def declare():
    """body: {yaml_text, provider, project, confirm: true, keys?: [...]}.
    Crea, con valor VACIO, los nombres que faltan. HITL: exige confirm=True.
    keys (opcional) restringe el lote a un subconjunto del plan."""
    _guard_declare()
    from services.ci_variables import (  # noqa: PLC0415
        VariablesUnavailableError,
        get_variables_provider,
    )
    from services.pipeline_env_declare import (  # noqa: PLC0415
        DeclarePlan,
        pendiente_visible,
        plan_declaration,
        proyectar_celdas,
    )

    body = request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm=True requerido (HITL)"}), 400

    matriz, provider, error = _matriz_para_declarar(body)
    if error is not None:
        return error

    plan = plan_declaration(matriz, provider)

    keys_body = body.get("keys")
    if keys_body is not None:
        keys_solicitadas = set(keys_body)
        keys_del_plan = {i.key for i in plan.items}
        fuera_del_plan = sorted(keys_solicitadas - keys_del_plan)
        if fuera_del_plan:
            return jsonify({"error": "keys_fuera_del_plan", "keys": fuera_del_plan}), 400
        items_a_declarar = [i for i in plan.items if i.key in keys_solicitadas]
    else:
        items_a_declarar = list(plan.items)

    project = body.get("project")
    try:
        proveedor = get_variables_provider(project)
    except VariablesUnavailableError as e:
        return jsonify({"error": "proveedor_sin_variables", "detail": str(e)}), 409

    declared: list = []
    failed: list = []
    needs_masking: list = []
    declaradas_ok: list = []
    for item in items_a_declarar:
        try:
            resultado = proveedor.set_variable(item.key, "", item.secret)
            declared.append({"key": item.key, "secret": item.secret})
            declaradas_ok.append(item)
            if provider == PROVIDER_GITLAB and item.secret and not resultado.get("masked"):
                needs_masking.append(item.key)
        except Exception as e:  # noqa: BLE001 — sanitizado, nunca str(e) crudo
            failed.append({"key": item.key, "error": _mensaje_declare_seguro(e)})

    # (ADICIÓN 3) el "after" se PROYECTA con la misma tabla de verdad — no hace
    # falta releer al proveedor de nuevo (0 llamadas de red extra).
    plan_efectivo = DeclarePlan(items=tuple(declaradas_ok), skipped=plan.skipped, provider=provider)
    celdas_after = proyectar_celdas(matriz.cells, plan_efectivo)

    return jsonify({
        "declared": declared,
        "skipped": [{"key": k, "motivo": m} for k, m in plan.skipped],
        "failed": failed,
        "needs_masking": needs_masking,
        "pending_count_after": sum(1 for c in celdas_after if c.state == "falta"),
        "pendiente_visible_after": pendiente_visible(celdas_after),
    }), 200


@bp.route("/analyze", methods=["POST"])
def analyze():
    """body: {yaml_text, provider, project?, resolve?} -> matriz entorno x valor."""
    _guard()
    body = request.get_json(silent=True) or {}

    provider = str(body.get("provider") or "")
    if provider not in PROVIDERS:
        return jsonify({"error": "provider_no_soportado",
                        "detail": "provider debe ser uno de: %s" % ", ".join(PROVIDERS)}), 400

    yaml_text = body.get("yaml_text")
    if not isinstance(yaml_text, str) or not yaml_text.strip():
        return jsonify({"error": "yaml_text_requerido"}), 400
    if len(yaml_text) > MAX_YAML_CHARS:
        return jsonify({"error": "yaml_demasiado_grande",
                        "detail": "YAML demasiado grande (máx 500 KB)"}), 400

    usar_proveedor = body.get("resolve")
    usar_proveedor = True if not isinstance(usar_proveedor, bool) else usar_proveedor
    project = body.get("project")

    requisitos = extract_requirements(yaml_text, provider)
    resoluciones: dict = {}
    degradaciones: tuple = ()
    entornos = derive_environments(yaml_text, provider)

    if usar_proveedor:
        # los scopes del proveedor tambien son evidencia de entornos (§F2 fuente 4)
        from services.pipeline_env_resolver import (  # noqa: PLC0415
            list_scoped_variables,
        )
        _vars, scopes, deg_scopes = list_scoped_variables(project)
        if scopes:
            entornos = derive_environments(yaml_text, provider, tuple(scopes))
        resoluciones, deg_resolve = resolve(
            requisitos, entornos, provider, project=project, use_provider=True,
            yaml_text=yaml_text)
        degradaciones = tuple(deg_scopes) + tuple(
            d for d in deg_resolve if d not in deg_scopes)
    else:
        resoluciones, degradaciones = resolve(
            requisitos, entornos, provider, project=project, use_provider=False,
            yaml_text=yaml_text)

    matriz = build_matrix(requisitos, entornos, resoluciones, provider,
                          degraded=degradaciones)
    # red C (estructural): claves de diccionario que suenen a secreto. NO sustituye a
    # las redes de VALOR del modulo puro; es la ultima linea, no la primera.
    payload = strip_secret_keys(to_json_payload(matriz, provider))
    return jsonify(payload), 200
