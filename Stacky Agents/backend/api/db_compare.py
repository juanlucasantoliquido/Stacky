"""api/db_compare.py — Plan 122 F4: núcleo del Comparador de BD entre ambientes
(serie 122-126). url_prefix="/db-compare" → rutas finales /api/db-compare/...

Gate estricto: TODOS los endpoints excepto /health devuelven 403 si
STACKY_DB_COMPARE_ENABLED está OFF (default). El password entra SOLO por
POST .../password (write-only), JAMÁS sale en respuestas ni logs.
"""
from __future__ import annotations

import json as _json
import logging
import os as _os

import config as _config
import runtime_paths as _rt
from flask import Blueprint, current_app, jsonify, request

from services import (
    dbcompare_config_import,
    dbcompare_data,
    dbcompare_engine,
    dbcompare_registry,
    dbcompare_runs,
    dbcompare_scripts,
    dbcompare_snapshot,
)
from services import dbcompare_sqlnames as _sqlnames
from services import egress_policies as _egress_policies
from services.db_query import validate_select_only as _validate_select_only

logger = logging.getLogger(__name__)

bp = Blueprint("db_compare", __name__, url_prefix="/db-compare")


def _require_enabled():
    if not getattr(_config.config, "STACKY_DB_COMPARE_ENABLED", False):
        return jsonify({"ok": False, "error": "Comparador de BD deshabilitado (STACKY_DB_COMPARE_ENABLED)."}), 403
    return None


def _require_webconfig_import_enabled():
    """[Plan 157 F2] Gate del import local desde web.config/datasource (hija del master)."""
    if not getattr(_config.config, "STACKY_DB_COMPARE_WEBCONFIG_IMPORT_ENABLED", False):
        return jsonify({
            "ok": False,
            "error": "Import de web.config deshabilitado (STACKY_DB_COMPARE_WEBCONFIG_IMPORT_ENABLED).",
        }), 403
    return None


def _require_data_enabled():
    """[Plan 126 F4] Gate adicional para paridad de DATOS (hija, opt-in doble)."""
    if not getattr(_config.config, "STACKY_DB_COMPARE_DATA_DIFF_ENABLED", False):
        return jsonify({
            "ok": False,
            "error": "Paridad de datos deshabilitada (STACKY_DB_COMPARE_DATA_DIFF_ENABLED).",
        }), 403
    return None


def _with_snapshot_recency(env: dict) -> dict:
    """[ADICIÓN ARQUITECTO] agrega latest_snapshot_taken_at/latest_snapshot_hash8."""
    snap = dbcompare_snapshot.latest_snapshot(env["alias"])
    env = dict(env)
    env["latest_snapshot_taken_at"] = snap["taken_at"] if snap else None
    env["latest_snapshot_hash8"] = snap["content_hash"][:8] if snap else None
    return env


@bp.get("/health")
def health_route():
    return jsonify({
        "ok": True,
        "flag_enabled": bool(getattr(_config.config, "STACKY_DB_COMPARE_ENABLED", False)),
        # [FIX C5, Plan 126] la UI (F5) lee este campo para mostrar/ocultar el
        # botón "Comparar datos…" sin tener que llamar a un endpoint aparte.
        "data_diff_enabled": bool(getattr(_config.config, "STACKY_DB_COMPARE_DATA_DIFF_ENABLED", False)),
        # [Plan 157] flags de UX leídas por el frontend para gatear wizard/import/panel.
        # Additivo y backward-compatible: con las 3 OFF el frontend queda como main.
        "config_in_place_enabled": bool(getattr(_config.config, "STACKY_DB_COMPARE_CONFIG_IN_PLACE_ENABLED", False)),
        "webconfig_import_enabled": bool(getattr(_config.config, "STACKY_DB_COMPARE_WEBCONFIG_IMPORT_ENABLED", False)),
        "migration_panel_enabled": bool(getattr(_config.config, "STACKY_DB_COMPARE_MIGRATION_PANEL_ENABLED", False)),
        # [Plan 176] triage curado, gates read-only, prefs de tabla y UX v2 del diff.
        "triage_enabled": bool(getattr(_config.config, "STACKY_DB_COMPARE_TRIAGE_ENABLED", False)),
        "gates_enabled": bool(getattr(_config.config, "STACKY_DB_COMPARE_GATES_ENABLED", False)),
        "table_prefs_enabled": bool(getattr(_config.config, "STACKY_DB_COMPARE_TABLE_PREFS_ENABLED", False)),
        "diff_ux_v2_enabled": bool(getattr(_config.config, "STACKY_DB_COMPARE_DIFF_UX_V2_ENABLED", False)),
        "keyring_available": dbcompare_registry.keyring_available(),
        "drivers": dbcompare_engine.driver_status(),
    })


@bp.get("/environments")
def list_environments_route():
    gate = _require_enabled()
    if gate:
        return gate
    envs = [_with_snapshot_recency(e) for e in dbcompare_registry.list_environments()]
    return jsonify({
        "ok": True,
        "environments": envs,
        "keyring_available": dbcompare_registry.keyring_available(),
    })


@bp.post("/environments")
def upsert_environment_route():
    gate = _require_enabled()
    if gate:
        return gate
    body = request.get_json(silent=True) or {}
    try:
        env = dbcompare_registry.upsert_environment(
            alias=(body.get("alias") or "").strip(),
            engine=(body.get("engine") or "").strip(),
            host=(body.get("host") or "").strip(),
            port=body.get("port"),
            database=(body.get("database") or "").strip(),
            username=(body.get("username") or "").strip(),
            odbc_driver=body.get("odbc_driver") or "ODBC Driver 17 for SQL Server",
            schema_filter=body.get("schema_filter"),
            notes=body.get("notes") or "",
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "environment": _with_snapshot_recency(env)})


@bp.delete("/environments/<alias>")
def delete_environment_route(alias):
    gate = _require_enabled()
    if gate:
        return gate
    if not dbcompare_registry.delete_environment(alias):
        return jsonify({"ok": False, "error": f"ambiente '{alias}' no existe."}), 404
    return jsonify({"ok": True})


@bp.post("/environments/<alias>/password")
def set_password_route(alias):
    gate = _require_enabled()
    if gate:
        return gate
    body = request.get_json(silent=True) or {}
    password = body.get("password")
    if not password:
        return jsonify({"ok": False, "error": "password requerido"}), 400
    if not dbcompare_registry.keyring_available():
        return jsonify({
            "ok": False,
            "error": (
                "keyring no disponible: instale keyring==25.6.0; el password NO se "
                "guardó (nunca se persiste en texto plano)."
            ),
        }), 503
    dbcompare_registry.set_password(alias, password)
    return jsonify({"ok": True})


@bp.delete("/environments/<alias>/password")
def clear_password_route(alias):
    gate = _require_enabled()
    if gate:
        return gate
    dbcompare_registry.clear_password(alias)
    return jsonify({"ok": True})


@bp.post("/environments/<alias>/test")
def test_connection_route(alias):
    gate = _require_enabled()
    if gate:
        return gate
    result = dbcompare_engine.test_connection(alias)
    return jsonify(result)


@bp.post("/environments/<alias>/snapshot")
def take_snapshot_route(alias):
    gate = _require_enabled()
    if gate:
        return gate
    try:
        snapshot = dbcompare_snapshot.take_snapshot(alias)
    except (ValueError, dbcompare_engine.DbCompareEngineError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(snapshot)


# ──────────────────────────────────────────────────────────────────────────────
# Plan 157 F2/F3 — Import local de web.config/datasource (agente local determinista)
# ──────────────────────────────────────────────────────────────────────────────

_ALLOWED_IMPORT_EXT = (".config", ".xml")
_MAX_IMPORT_BYTES = 1_000_000
_MAX_IMPORT_CHARS = 1_000_000


def _import_allowlist_roots() -> list[str]:
    """Raíces permitidas para el modo `path` (C2 v2). Prefijos de realpath normcase."""
    roots: list[str] = []
    for fn in (_rt.app_root, _rt.projects_dir, _rt.data_dir):
        try:
            roots.append(_os.path.normcase(_os.path.realpath(str(fn()))))
        except Exception:  # noqa: BLE001 — raíz no resoluble: se omite del allowlist
            continue
    return roots


def _path_under_allowlist(rp: str) -> bool:
    ncrp = _os.path.normcase(rp)
    for root in _import_allowlist_roots():
        if ncrp == root or ncrp.startswith(root + _os.sep):
            return True
    return False


def _read_import_source(body: dict):
    """Devuelve (raw, None) o (None, (response, status)). Modo `content` preferido
    (FileReader del browser); modo `path` restringido por allowlist (C2 v2)."""
    content = body.get("content")
    if isinstance(content, str) and content != "":
        if len(content) > _MAX_IMPORT_CHARS:
            return None, (jsonify({"ok": False, "error": "content demasiado grande."}), 413)
        return content, None

    path = body.get("path")
    if not isinstance(path, str) or not path.strip():
        return None, (jsonify({"ok": False, "error": "falta 'content' o 'path'."}), 400)

    rp = _os.path.realpath(path)
    if not _path_under_allowlist(rp):
        return None, (jsonify({"ok": False, "error": "path_fuera_de_allowlist"}), 403)
    if not _os.path.exists(rp):
        return None, (jsonify({"ok": False, "error": "el archivo no existe."}), 404)
    if _os.path.isdir(rp):
        return None, (jsonify({"ok": False, "error": "la ruta es un directorio."}), 400)
    try:
        size = _os.path.getsize(rp)
    except OSError:
        return None, (jsonify({"ok": False, "error": "no se pudo leer el archivo."}), 400)
    if size > _MAX_IMPORT_BYTES:
        return None, (jsonify({"ok": False, "error": "archivo demasiado grande (>1MB)."}), 413)
    if _os.path.splitext(rp)[1].lower() not in _ALLOWED_IMPORT_EXT:
        return None, (jsonify({"ok": False, "error": "extensión no permitida (solo .config/.xml)."}), 415)
    try:
        with open(rp, "r", encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
    except OSError:
        return None, (jsonify({"ok": False, "error": "no se pudo leer el archivo."}), 400)
    return raw, None


def _build_previews(conns) -> list[dict]:
    """Previews SEGUROS (sin password, sin masked_raw) + index. Punto monkeypatchable
    para el test del self-check (F3): si un bug dejara colar un secreto acá, el
    self-check fail-closed corta la respuesta con 500."""
    return [
        {**dbcompare_config_import.preview_dict(pc), "index": i}
        for i, (pc, _pw) in enumerate(conns)
    ]


def _egress_selfcheck(payload: dict):
    """[ADICIÓN ARQUITECTO Plan 157] Gate ejecutable fail-closed: serializa el body y
    lo pasa por el detector de egreso; si aparece la clase `secrets`, ABORTA con 500
    (preferimos romper a filtrar) y loguea alerta SIN el valor."""
    blob = _json.dumps(payload, ensure_ascii=False, default=str)
    if "secrets" in _egress_policies.detect_classes(blob):
        logger.error("import-config: self-check de egreso BLOQUEO una respuesta con posible secreto")
        return jsonify({"ok": False, "error": "egress_selfcheck_bloqueo"}), 500
    return None


@bp.post("/environments/import-config")
def import_config_route():
    gate = _require_enabled()
    if gate:
        return gate
    gate = _require_webconfig_import_enabled()
    if gate:
        return gate
    body = request.get_json(silent=True) or {}
    raw, err = _read_import_source(body)
    if err is not None:
        return err
    parece_xml = raw.lstrip().startswith("<")  # C4 v2: dispatch literal, sin heurística
    if parece_xml:
        conns = dbcompare_config_import.parse_webconfig(raw)
    else:
        conns = [dbcompare_config_import.parse_connection_string(raw)]
    import_id = dbcompare_config_import.stash_parsed(conns)
    previews = _build_previews(conns)
    logger.info("import-config: %d conexiones detectadas", len(previews))  # solo el conteo
    result = {"ok": True, "import_id": import_id, "connections": previews}
    blocked = _egress_selfcheck(result)
    if blocked is not None:
        return blocked
    return jsonify(result)


@bp.post("/environments/import-config/confirm")
def confirm_import_route():
    gate = _require_enabled()
    if gate:
        return gate
    gate = _require_webconfig_import_enabled()
    if gate:
        return gate
    body = request.get_json(silent=True) or {}
    import_id = body.get("import_id")
    index = body.get("index")
    alias = (body.get("alias") or "").strip()
    overrides = body.get("overrides") if isinstance(body.get("overrides"), dict) else {}
    if not isinstance(import_id, str) or not isinstance(index, int):
        return jsonify({"ok": False, "error": "import_id/index inválidos."}), 400

    pc, pw = dbcompare_config_import.pop_parsed(import_id, index)
    if pc is None:
        return jsonify({"ok": False, "error": "import_id/index no encontrado o ya consumido."}), 404

    def _pick(key, fallback):
        v = overrides.get(key)
        return v if v is not None else fallback

    engine = (str(_pick("engine", pc.engine) or "").strip() or "sqlserver")
    host = _pick("host", pc.host)
    port = _pick("port", pc.port)
    database = _pick("database", pc.database)
    username = _pick("username", pc.username)

    try:
        env = dbcompare_registry.upsert_environment(
            alias=alias,
            engine=engine,
            host=str(host or "").strip(),
            port=port,
            database=str(database or "").strip(),
            username=str(username or "").strip(),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    password_warning = None
    if pw:
        if dbcompare_registry.keyring_available():
            dbcompare_registry.set_password(alias, pw)
        else:
            password_warning = (
                "keyring no disponible: el ambiente se creó pero la contraseña no se "
                "guardó; seteala manualmente desde el panel de ambientes."
            )

    result = {"ok": True, "alias": env.get("alias", alias)}
    if password_warning:
        result["password_warning"] = password_warning
    blocked = _egress_selfcheck(result)
    if blocked is not None:
        return blocked
    return jsonify(result)


@bp.get("/environments/<alias>/snapshots")
def list_snapshots_route(alias):
    gate = _require_enabled()
    if gate:
        return gate
    return jsonify({"ok": True, "snapshots": dbcompare_snapshot.list_snapshots(alias)})


@bp.get("/snapshots/<snapshot_id>")
def get_snapshot_route(snapshot_id):
    gate = _require_enabled()
    if gate:
        return gate
    snapshot = dbcompare_snapshot.load_snapshot(snapshot_id)
    if snapshot is None:
        return jsonify({"ok": False, "error": f"snapshot '{snapshot_id}' no existe."}), 404
    return jsonify(snapshot)


# --------------------------------------------------------------------------
# Plan 123 F3 — corridas comparativas (motor de diff sobre los snapshots de arriba)
# --------------------------------------------------------------------------

@bp.post("/compare")
def create_compare_run_route():
    gate = _require_enabled()
    if gate:
        return gate
    body = request.get_json(silent=True) or {}
    source_alias = (body.get("source_alias") or "").strip()
    target_alias = (body.get("target_alias") or "").strip()
    mode = body.get("mode") or "fresh"
    if not source_alias or not target_alias:
        return jsonify({"ok": False, "error": "source_alias y target_alias son requeridos"}), 400
    try:
        run = dbcompare_runs.create_run(source_alias, target_alias, mode=mode)
    except dbcompare_runs.DbCompareBusyError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    except (dbcompare_runs.DbCompareRunError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "run": run}), 202


@bp.get("/runs")
def list_runs_route():
    gate = _require_enabled()
    if gate:
        return gate
    raw_limit = request.args.get("limit")
    limit = 50
    if raw_limit is not None:
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "limit debe ser un entero"}), 400
        if limit < 0:
            return jsonify({"ok": False, "error": "limit no puede ser negativo"}), 400
    return jsonify({"ok": True, "runs": dbcompare_runs.list_runs(limit=limit)})


@bp.get("/runs/<run_id>")
def get_run_route(run_id):
    gate = _require_enabled()
    if gate:
        return gate
    run = dbcompare_runs.get_run(run_id)
    if run is None:
        return jsonify({"ok": False, "error": f"corrida '{run_id}' no existe."}), 404
    # [Plan 176 F1] Las item_key se calculan ANTES del enmascarado: el masking
    # tapa los valores de PK, así que el frontend no podría derivarlas nunca.
    from services import dbcompare_triage
    dbcompare_triage.attach_item_keys(run)
    from services import dbcompare_masking  # Plan 181 — masking de presentación del data-diff
    return jsonify(dbcompare_masking.apply_to_run_response(run))


@bp.get("/runs/<run_id>/export.md")
def export_run_markdown_route(run_id):
    gate = _require_enabled()
    if gate:
        return gate
    run = dbcompare_runs.get_run(run_id)
    if run is None:
        return jsonify({"ok": False, "error": f"corrida '{run_id}' no existe."}), 404
    if run.get("status") != "done":
        return jsonify({
            "ok": False,
            "error": f"la corrida no está 'done' (status={run.get('status')}).",
        }), 409
    md = dbcompare_runs.export_markdown(run)
    response = current_app.response_class(md, mimetype="text/markdown; charset=utf-8")
    response.headers["Content-Disposition"] = f'attachment; filename="{run_id}.md"'
    return response


# --------------------------------------------------------------------------
# Plan 176 F1 — Triage del diff: la decisión humana sobre cada diferencia.
# Mismo blueprint y mismo _require_enabled; la flag hija solo agrega el 403.
# --------------------------------------------------------------------------

def _require_triage_enabled():
    if not getattr(_config.config, "STACKY_DB_COMPARE_TRIAGE_ENABLED", False):
        return jsonify({
            "ok": False,
            "error": "Triage del diff deshabilitado (STACKY_DB_COMPARE_TRIAGE_ENABLED).",
        }), 403
    return None


def _triage_gates(run_id: str):
    """Gates comunes de las 3 rutas: devuelve (respuesta_de_error, run)."""
    for gate in (_require_enabled(), _require_triage_enabled()):
        if gate:
            return gate, None
    run = dbcompare_runs.get_run(run_id)
    if run is None:
        return (jsonify({"ok": False, "error": f"corrida '{run_id}' no existe."}), 404), None
    return None, run


def _triage_payload(run_id: str, run: dict) -> dict:
    from services import dbcompare_triage

    doc = dbcompare_triage.load_triage(run_id)
    total = len(((run.get("diff") or {}).get("items")) or [])
    doc["summary"] = (
        dbcompare_triage.triage_summary(doc, total)
        if run.get("status") == "done" else None
    )
    return doc


@bp.get("/runs/<run_id>/triage")
def get_triage_route(run_id):
    error, run = _triage_gates(run_id)
    if error:
        return error
    return jsonify(_triage_payload(run_id, run))


@bp.put("/runs/<run_id>/triage/item")
def put_triage_item_route(run_id):
    from services import dbcompare_triage

    error, run = _triage_gates(run_id)
    if error:
        return error

    body = request.get_json(silent=True) or {}
    item_key = (body.get("item_key") or "").strip()
    decision = (body.get("decision") or "").strip()

    if decision not in dbcompare_triage.DECISIONS:
        return jsonify({"ok": False, "error": "decision_invalida",
                        "validas": list(dbcompare_triage.DECISIONS)}), 400
    if run.get("status") != "done":
        return jsonify({"ok": False, "error": "run_no_done",
                        "status": run.get("status")}), 409
    if not _item_key_pertenece(run, item_key):
        return jsonify({"ok": False, "error": "item_desconocido",
                        "item_key": item_key}), 404

    doc = dbcompare_triage.set_decision(run_id, item_key, decision,
                                        note=body.get("note") or "")
    doc["summary"] = dbcompare_triage.triage_summary(
        doc, len(((run.get("diff") or {}).get("items")) or []))
    return jsonify(doc)


def _item_key_pertenece(run: dict, item_key: str) -> bool:
    """Una decisión sobre un ítem que no está en la corrida es un error del caller.

    Sin este chequeo el archivo de triage acumularía basura de corridas viejas y
    el resumen contaría decisiones sobre ítems que ya no existen.
    """
    from services import dbcompare_triage

    if not item_key:
        return False
    if not item_key.startswith("data:"):
        conocidas = {
            dbcompare_triage.item_key_for_schema_item(i)
            for i in ((run.get("diff") or {}).get("items")) or []
        }
        return item_key in conocidas

    tablas = ((run.get("data_diff") or {}).get("tables")) or {}
    if not tablas:
        return False
    # `data:<schema>.<tabla>:<pk>` — se valida la tabla, no la fila: el masking
    # puede haber cambiado lo que el operador vio, pero no de qué tabla es.
    resto = item_key[len("data:"):]
    prefijo = resto.split(":", 1)[0] if ":" in resto else ""
    return prefijo in tablas


@bp.get("/runs/<run_id>/triage/exclusions.md")
def get_triage_exclusions_route(run_id):
    from services import dbcompare_triage

    error, run = _triage_gates(run_id)
    if error:
        return error

    md = dbcompare_triage.exclusions_markdown(
        run_id, dbcompare_triage.load_triage(run_id))
    response = current_app.response_class(md, mimetype="text/markdown; charset=utf-8")
    response.headers["Content-Disposition"] = \
        f'attachment; filename="{run_id}-exclusiones.md"'
    return response


# --------------------------------------------------------------------------
# Plan 176 F6 — Tablas de parámetro y claves naturales. Globales, no por
# ambiente: es el mismo producto en todos los ambientes del cliente.
# --------------------------------------------------------------------------

def _require_table_prefs_enabled():
    if not getattr(_config.config, "STACKY_DB_COMPARE_TABLE_PREFS_ENABLED", False):
        return jsonify({
            "ok": False,
            "error": "Preferencias de tabla deshabilitadas "
                     "(STACKY_DB_COMPARE_TABLE_PREFS_ENABLED).",
        }), 403
    return None


@bp.get("/table-prefs")
def get_table_prefs_route():
    from services import dbcompare_table_prefs

    for gate in (_require_enabled(), _require_table_prefs_enabled()):
        if gate:
            return gate
    return jsonify({"ok": True, **dbcompare_table_prefs.load_prefs()})


@bp.put("/table-prefs")
def put_table_prefs_route():
    from services import dbcompare_table_prefs

    for gate in (_require_enabled(), _require_table_prefs_enabled()):
        if gate:
            return gate

    body = request.get_json(silent=True) or {}
    schema = (body.get("schema") or "").strip()
    tabla = (body.get("table") or "").strip()
    if not schema or not tabla:
        return jsonify({"ok": False, "error": "schema y table son requeridos"}), 400

    kwargs = {}
    # Presencia, no verdad: mandar natural_key=null borra la clave; omitirla la
    # deja como estaba. Sin esa distinción no se podría tocar solo el flag.
    if "natural_key" in body:
        kwargs["natural_key"] = body.get("natural_key")
    if "param_table" in body:
        kwargs["param_table"] = body.get("param_table")

    try:
        doc = dbcompare_table_prefs.set_pref(schema, tabla, **kwargs)
    except ValueError as exc:
        return jsonify({"ok": False, "error": "natural_key_invalida",
                        "message": str(exc)}), 400
    return jsonify({"ok": True, **doc})


# --------------------------------------------------------------------------
# Plan 176 F7 — Verificación de cierre: ¿se aplicó lo confirmado y sigue intacto
# lo excluido? Pertenece a la capacidad de triage, así que comparte su flag.
# --------------------------------------------------------------------------

@bp.post("/runs/<run_id>/verify-closure")
def verify_closure_route(run_id):
    from services import dbcompare_closure

    error, _run = _triage_gates(run_id)
    if error:
        return error

    try:
        resultado = dbcompare_closure.start_closure(run_id)
    except ValueError as exc:
        codigo = 409 if str(exc).startswith("run_not_done") else 404
        return jsonify({"ok": False, "error": str(exc)}), codigo
    except dbcompare_runs.DbCompareBusyError as exc:
        return jsonify({"ok": False, "error": "par_ocupado", "message": str(exc)}), 409
    except _SCRIPTS_RUN_ERRORS as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    return jsonify({"ok": True, **resultado}), 202


@bp.get("/runs/<run_id>/closure")
def get_closure_route(run_id):
    from services import dbcompare_closure, dbcompare_triage

    error, viejo = _triage_gates(run_id)
    if error:
        return error

    linkage = dbcompare_closure.load_linkage(run_id)
    if linkage is None:
        return jsonify({"ok": False, "error": "sin_verificacion"}), 404

    verificacion_id = linkage.get("verification_run_id")
    nuevo = dbcompare_runs.get_run(verificacion_id)
    if nuevo is None:
        return jsonify({"ok": False, "error": "verificacion_no_encontrada",
                        "verification_run_id": verificacion_id}), 404
    if nuevo.get("status") != "done":
        return jsonify({"ok": False, "error": "verificacion_en_curso",
                        "verification_run_id": verificacion_id,
                        "status": nuevo.get("status")}), 409

    reporte = dbcompare_closure.evaluate_closure(
        viejo, nuevo, dbcompare_triage.load_triage(run_id))
    return jsonify({"ok": True, **reporte})


# --------------------------------------------------------------------------
# Plan 176 F4 — Gates de precondición read-only. Derivar y exportar son puros;
# EJECUTAR solo pasa por el POST explícito de abajo (nunca automático).
# --------------------------------------------------------------------------

def _require_gates_enabled():
    if not getattr(_config.config, "STACKY_DB_COMPARE_GATES_ENABLED", False):
        return jsonify({
            "ok": False,
            "error": "Gates de precondición deshabilitadas (STACKY_DB_COMPARE_GATES_ENABLED).",
        }), 403
    return None


def _gates_gates(run_id: str):
    """Gates comunes de las 3 rutas: devuelve (respuesta_de_error, run)."""
    for gate in (_require_enabled(), _require_gates_enabled()):
        if gate:
            return gate, None
    run = dbcompare_runs.get_run(run_id)
    if run is None:
        return (jsonify({"ok": False, "error": f"corrida '{run_id}' no existe."}), 404), None
    if run.get("status") != "done":
        return (jsonify({
            "ok": False,
            "error": f"la corrida no está 'done' (status={run.get('status')}).",
        }), 409), None
    return None, run


@bp.get("/runs/<run_id>/gates")
def get_gates_route(run_id):
    from services import dbcompare_gates

    error, run = _gates_gates(run_id)
    if error:
        return error

    return jsonify({
        "ok": True,
        "gates": dbcompare_gates.derive_gates(run.get("diff") or {},
                                              run.get("target_alias") or ""),
        "results": dbcompare_gates.load_results(run_id).get("results", {}),
    })


@bp.post("/runs/<run_id>/gates/evaluate")
def evaluate_gates_route(run_id):
    """Corre las precondiciones contra el destino. SIEMPRE a pedido del operador."""
    from services import dbcompare_gates

    error, _run = _gates_gates(run_id)
    if error:
        return error

    body = request.get_json(silent=True) or {}
    gate_ids = body.get("gate_ids")
    if gate_ids is not None and not isinstance(gate_ids, list):
        return jsonify({"ok": False, "error": "gate_ids debe ser una lista"}), 400

    try:
        doc = dbcompare_gates.evaluate_gates(run_id, gate_ids)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **doc})


@bp.get("/runs/<run_id>/gates/export.sql")
def get_gates_export_route(run_id):
    """El SQL de las precondiciones, para correrlo afuera de Stacky.

    NO entra al bundle del 125 a propósito: es un artefacto propio y meterlo ahí
    tocaría el Manifest v1, que está congelado.
    """
    from services import dbcompare_gates

    error, run = _gates_gates(run_id)
    if error:
        return error

    sql = dbcompare_gates.gates_export_sql(
        run.get("diff") or {}, run.get("target_alias") or "",
        run.get("engine") or "sqlserver")
    response = current_app.response_class(sql, mimetype="text/plain; charset=utf-8")
    response.headers["Content-Disposition"] = \
        f'attachment; filename="{run_id}-precondiciones.sql"'
    return response


# --------------------------------------------------------------------------
# Plan 125 F5 — bundle de scripts de paridad + backups pareados (mismo blueprint,
# mismo _require_enabled; Stacky GENERA, jamás ejecuta — ver doc 125 §3).
# --------------------------------------------------------------------------

_SCRIPTS_RUN_ERRORS = (dbcompare_scripts.DbCompareRunError, dbcompare_runs.DbCompareRunError)


@bp.post("/runs/<run_id>/scripts")
def generate_scripts_route(run_id):
    gate = _require_enabled()
    if gate:
        return gate
    run = dbcompare_runs.get_run(run_id)
    if run is None:
        return jsonify({"ok": False, "error": f"corrida '{run_id}' no existe."}), 404
    if run.get("status") != "done":
        return jsonify({
            "ok": False,
            "error": f"la corrida no está 'done' (status={run.get('status')}).",
        }), 409
    # [Plan 176 F3] La curación del operador se aplica al generar: lo excluido
    # no emite script ni backup. Con la flag OFF, excluded=None ⇒ bundle de antes.
    excluded = None
    if getattr(_config.config, "STACKY_DB_COMPARE_TRIAGE_ENABLED", False):
        from services import dbcompare_triage
        excluded = dbcompare_triage.excluded_keys(dbcompare_triage.load_triage(run_id))
    try:
        manifest = dbcompare_scripts.generate_parity_bundle(
            run_id, excluded_keys=excluded or None)
    except _SCRIPTS_RUN_ERRORS as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({
        "ok": True,
        "manifest": manifest,
        "triage_applied": {"excluded_count": len(excluded or ())},
    })


@bp.get("/runs/<run_id>/scripts")
def get_scripts_manifest_route(run_id):
    gate = _require_enabled()
    if gate:
        return gate
    manifest = dbcompare_scripts.load_manifest(run_id)
    if manifest is None:
        return jsonify({
            "ok": False,
            "error": "todavía no se generaron scripts de paridad para esta corrida.",
        }), 404
    return jsonify({"ok": True, "manifest": manifest})


def _scripts_allowlist(manifest: dict) -> set[str]:
    # [Plan 176 F3] TRIAGE_EXCLUSIONS.md no entra al manifest (Manifest v1 está
    # congelado), pero el visor tiene que poder servirlo.
    allowed = {"README.md", "MANIFEST.json", "TRIAGE_EXCLUSIONS.md"}
    for entry in manifest.get("entries", []):
        allowed.add(entry["file"])
        if entry.get("backup_file"):
            allowed.add(entry["backup_file"])
        if entry.get("rollback_file"):
            allowed.add(entry["rollback_file"])
    return allowed


@bp.get("/runs/<run_id>/scripts/file")
def get_scripts_file_route(run_id):
    gate = _require_enabled()
    if gate:
        return gate
    rel_path = request.args.get("path") or ""
    if not rel_path or ".." in rel_path or rel_path.startswith("/") or rel_path.startswith("\\"):
        return jsonify({"ok": False, "error": "path inválido."}), 400
    manifest = dbcompare_scripts.load_manifest(run_id)
    if manifest is None:
        return jsonify({
            "ok": False,
            "error": "todavía no se generaron scripts de paridad para esta corrida.",
        }), 404
    if rel_path not in _scripts_allowlist(manifest):
        return jsonify({"ok": False, "error": "archivo no encontrado en el manifest de esta corrida."}), 400
    content = dbcompare_scripts.read_bundle_file(run_id, rel_path)
    if content is None:
        return jsonify({"ok": False, "error": "archivo no encontrado en disco."}), 404
    return current_app.response_class(content, mimetype="text/plain; charset=utf-8")


@bp.get("/runs/<run_id>/scripts.zip")
def get_scripts_zip_route(run_id):
    gate = _require_enabled()
    if gate:
        return gate
    manifest = dbcompare_scripts.load_manifest(run_id)
    if manifest is None:
        return jsonify({
            "ok": False,
            "error": "todavía no se generaron scripts de paridad para esta corrida.",
        }), 404
    zip_bytes = dbcompare_scripts.bundle_zip_bytes(run_id)
    response = current_app.response_class(zip_bytes, mimetype="application/zip")
    response.headers["Content-Disposition"] = f'attachment; filename="dbcompare_{run_id}.zip"'
    return response


# --------------------------------------------------------------------------
# Plan 126 F4 — paridad de DATOS (gate doble: master + STACKY_DB_COMPARE_DATA_DIFF_ENABLED)
# --------------------------------------------------------------------------


def _best_effort_row_count(alias: str, schema: str, table: str, dialect: str) -> int | None:
    """[ADICIÓN ARQUITECTO, crítica v2] COUNT(*) best-effort por lado; nunca
    lanza — timeout/error de conexión/driver faltante -> None (no rompe el
    endpoint). El SQL generado pasa por el MISMO validador que F2 (KPI-2)."""
    try:
        q = _sqlnames.qualified(schema, table, dialect)
        sql = f"SELECT COUNT(*) FROM {q}"
        if not _validate_select_only(sql).ok:
            return None
        engine = dbcompare_engine.open_engine(alias)
    except Exception:  # noqa: BLE001 — best-effort: cualquier fallo -> None
        return None
    try:
        from sqlalchemy import text as _sql_text

        with engine.connect() as conn:
            return conn.execute(_sql_text(sql)).scalar()
    except Exception:  # noqa: BLE001
        return None
    finally:
        engine.dispose()


@bp.get("/runs/<run_id>/data-candidates")
def data_candidates_route(run_id):
    gate = _require_enabled()
    if gate:
        return gate
    gate = _require_data_enabled()
    if gate:
        return gate

    run = dbcompare_runs.get_run(run_id)
    if run is None:
        return jsonify({"ok": False, "error": f"corrida '{run_id}' no existe."}), 404
    if run.get("status") != "done":
        return jsonify({"ok": False, "error": f"la corrida no está done (status={run.get('status')})."}), 409

    dialect = run["engine"]
    src_snap = dbcompare_snapshot.latest_snapshot(run["source_alias"])
    candidates: list[dict] = []
    if src_snap is not None:
        for schema in sorted(src_snap.get("schemas", {})):
            tables = src_snap["schemas"][schema].get("tables", {})
            for tname in sorted(tables):
                table = tables[tname]
                pk_cols = table.get("primary_key", {}).get("columns") or []
                comparable = bool(pk_cols)
                candidates.append({
                    "schema": schema,
                    "table": tname,
                    "has_pk": comparable,
                    "estimated_columns": len(table.get("columns") or []),
                    "comparable": comparable,
                    "reason": "" if comparable else "la tabla no tiene PK en el snapshot de origen",
                    "row_count_source": _best_effort_row_count(run["source_alias"], schema, tname, dialect),
                    "row_count_target": _best_effort_row_count(run["target_alias"], schema, tname, dialect),
                })
    return jsonify({"ok": True, "candidates": candidates})


@bp.post("/runs/<run_id>/data-diff")
def start_data_diff_route(run_id):
    gate = _require_enabled()
    if gate:
        return gate
    gate = _require_data_enabled()
    if gate:
        return gate

    body = request.get_json(silent=True) or {}
    tables = body.get("tables") or []
    if len(tables) > dbcompare_data._MAX_TABLES_PER_DATA_DIFF:
        return jsonify({
            "ok": False,
            "error": f"máximo {dbcompare_data._MAX_TABLES_PER_DATA_DIFF} tablas por corrida (recibidas {len(tables)}).",
        }), 400

    run = dbcompare_runs.get_run(run_id)
    if run is None:
        return jsonify({"ok": False, "error": f"corrida '{run_id}' no existe."}), 404
    if run.get("status") != "done":
        return jsonify({"ok": False, "error": f"la corrida no está done (status={run.get('status')})."}), 409

    try:
        dbcompare_data.run_data_diff(run_id, tables)
    except dbcompare_data.DbCompareDataError as exc:
        # A esta altura ya se validó existencia/estado/tamaño arriba: lo único
        # que puede fallar es el lock de "ya hay un diff de datos activo".
        return jsonify({"ok": False, "error": str(exc)}), 409

    return jsonify({"ok": True}), 202
