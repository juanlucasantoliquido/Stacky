"""Plan 72 F2 — Blueprint CI: trigger y monitoreo de pipelines (HITL).

Endpoints:
  POST /api/ci/<project>/trigger         — dispara pipeline (confirm=True obligatorio).
  GET  /api/ci/<project>/trigger-preview — preview read-only (no dispara).
  GET  /api/ci/<project>/pipeline/<id>   — estado del pipeline (monitor).

Blueprint registrado en api/__init__.py con url_prefix="/ci" sobre api_bp
(url_prefix="/api") → rutas finales /api/ci/... (C1, sin doble prefijo).

Flag STACKY_PIPELINE_TRIGGER_ENABLED: default ON (operador 2026-07-05), leída
per-request (C2'). El default efectivo vive en config.py; su FlagSpec declara
default=True. Si la flag está apagada → guard 404 per-request; el blueprint
siempre está registrado.
"""
from __future__ import annotations

import concurrent.futures as _fut
import hashlib
import re as _re
import time
from dataclasses import replace as _dc_replace
from pathlib import Path

import config as _config
from flask import Blueprint, abort, jsonify, request
from services.ci_env_gate import GATE_BUDGET_S, Readiness, evaluate_readiness
from services.ci_provider import get_ci_provider, ItemRef
from services.ci_trigger_rules import normalize_ref, validate_trigger_credentials, should_trigger
from services.pipeline_env_resolver import resolve
from services.pipeline_environments import build_matrix, derive_environments, extract_requirements
from services.tracker_provider import TrackerApiError

# Blueprint con url_prefix="/ci" → registrado en api_bp (url_prefix="/api") → /api/ci/...
# NUNCA url_prefix="/api/ci" (daría /api/api/ci, doble prefijo, C1).
bp = Blueprint("ci", __name__, url_prefix="/ci")

# ---------------------------------------------------------------------------
# Stores in-process (mono-operador single-process, C5'/C4)
# ---------------------------------------------------------------------------

# Idempotencia por (tracker_type, ref): clave → dict{ref,sha,pipeline_id,ts}
_RECENT_TRIGGERS: dict[tuple[str, str], dict] = {}

# Cap anti-N+1: contador de polls activos por pipeline_id
_ACTIVE_POLLS: dict[str, int] = {}
_MAX_ACTIVE_POLLS_PER_PIPELINE = 5

# Plan 260 (F4, ADICIÓN ARQUITECTO 2) — memoria de veredictos del gate de
# entornos. Misma ventana de 60s que la idempotencia. NO es un cache de datos
# del proveedor: es el resultado YA CALCULADO del gate.
# clave: (provider_name, ref_value, yaml_sha256) -> (Readiness, ts_monotonic)
_RECENT_READINESS: dict[tuple[str, str, str], tuple] = {}
_MAX_READINESS = 32
_READINESS_WINDOW_S = 60.0


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _recent_triggers(tracker_type: str, ref: str) -> list[dict]:
    """Devuelve [entry] o [] para (tracker_type, ref)."""
    entry = _RECENT_TRIGGERS.get((tracker_type, ref))
    return [entry] if entry else []


def _record_trigger(tracker_type: str, ref: str, sha: str, pipeline_id: str) -> None:
    """Registra el último trigger para (tracker_type, ref)."""
    _RECENT_TRIGGERS[(tracker_type, ref)] = {
        "ref": ref,
        "sha": sha,
        "pipeline_id": pipeline_id,
        "ts": time.time(),
    }


#: Plan 294 F7 — tope y forma de las variables por corrida.
_MAX_TRIGGER_VARS = 25
_TRIGGER_VAR_KEY_RE = _re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class TriggerVarsInvalid(ValueError):
    """Plan 294 F7 — el cuerpo trae variables mal formadas. Siempre 400, nunca 500."""


def _validar_variables(crudo):
    """Plan 294 F7 — dict[str, str] acotado, o `None` si no vino nada.

    Lanza TriggerVarsInvalid (que la ruta traduce a 400, nunca a 500) si el
    cuerpo no tiene la forma esperada. El tope y el patron de la clave existen
    porque esto termina en una corrida REAL del sistema del operador: una clave
    rara o un diccionario gigante son un error del llamador, no algo que haya
    que reenviar al proveedor.
    """
    if crudo is None:
        return None
    if not isinstance(crudo, dict):
        raise TriggerVarsInvalid(
            "las variables por corrida tienen que venir como un objeto de nombre y valor"
        )
    if len(crudo) > _MAX_TRIGGER_VARS:
        raise TriggerVarsInvalid(
            f"demasiadas variables por corrida ({len(crudo)}); el maximo es "
            f"{_MAX_TRIGGER_VARS}"
        )
    out: dict[str, str] = {}
    for k, v in crudo.items():
        if not isinstance(k, str) or not _TRIGGER_VAR_KEY_RE.match(k):
            raise TriggerVarsInvalid(
                f"el nombre de variable {k!r} no es valido: se admiten letras, "
                f"numeros y guion bajo, y no puede empezar con un numero"
            )
        if not isinstance(v, (str, int, bool)):
            raise TriggerVarsInvalid(
                f"el valor de {k!r} tiene que ser texto, numero entero o si/no"
            )
        out[k] = str(v)
    return out


def _read_pat_scopes(provider) -> set[str] | None:
    """Best-effort (C3'): lee scopes del client_profile si están disponibles.

    Devuelve None cuando no hay metadata de scopes → validate_trigger_credentials
    no bloqueará (retorna True).
    """
    # En esta versión no hay metadata de scopes en el client; siempre None → no bloquear.
    # Si en el futuro client_profile expone scopes verificables, leerlos aquí.
    return None


# ---------------------------------------------------------------------------
# Plan 260 F4 — gate antes de disparar (§4.5). Ninguna llamada de red que el
# panel de la matriz no haga ya; el gate corre A PEDIDO, dentro del request.
# ---------------------------------------------------------------------------

def _yaml_fuente_inventario() -> str | None:
    """Fuente 2 (import blando, §2.4.3): el YAML de la (única) pipeline
    registrada en el inventario del Plan 246 para el workspace activo. Si no
    hay exactamente una, o no se puede leer, degrada a None — NUNCA asume."""
    try:
        from runtime_paths import _active_workspace_root  # noqa: PLC0415
        from services.pipeline_inventory import scan_repo_pipelines  # noqa: PLC0415

        root = _active_workspace_root()
        if not root:
            return None
        entries, _meta = scan_repo_pipelines(str(root))
        candidatos = [e for e in entries if e.get("yaml_path")]
        if len(candidatos) != 1:
            return None
        ruta = Path(str(root)) / candidatos[0]["yaml_path"]
        if not ruta.is_file():
            return None
        return ruta.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 — import/lectura blanda: nunca rompe el gate
        return None


def _leer_yaml_por_path(yaml_path: str) -> str | None:
    """(v2, C7) El preview es GET: acepta ?yaml_path= (una RUTA relativa del
    workspace, nunca el YAML entero por query string — eso lo dejaría en los
    logs de acceso del servidor, violando KPI-5 por la puerta de atrás)."""
    if not yaml_path:
        return None
    try:
        from runtime_paths import _active_workspace_root  # noqa: PLC0415

        root = _active_workspace_root()
        if not root:
            return None
        raiz = Path(str(root)).resolve()
        ruta = (raiz / yaml_path).resolve()
        if raiz != ruta and raiz not in ruta.parents:
            return None  # fuera del workspace: no seguir path traversal
        if not ruta.is_file():
            return None
        return ruta.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return None


def _resolver_yaml_para_gate(*, yaml_text: str | None, yaml_path: str | None) -> str | None:
    """3 fuentes, PRIMERA que acierta (§4, F4)."""
    if isinstance(yaml_text, str) and yaml_text.strip():
        return yaml_text
    if yaml_path:
        leido = _leer_yaml_por_path(yaml_path)
        if leido:
            return leido
    return _yaml_fuente_inventario()


def _podar_readiness_cache() -> None:
    """(v3, C12) Poda por ventana + cap duro: sin esto el dict crece una
    entrada por cada (proveedor, ref, sha) visto y nunca suelta objetos
    Readiness (que traen `missing`/`reasons`)."""
    ahora = time.monotonic()
    vencidas = [k for k, (_r, ts) in _RECENT_READINESS.items()
               if ahora - ts > _READINESS_WINDOW_S]
    for k in vencidas:
        _RECENT_READINESS.pop(k, None)
    while len(_RECENT_READINESS) > _MAX_READINESS:
        mas_vieja = min(_RECENT_READINESS, key=lambda k: _RECENT_READINESS[k][1])
        _RECENT_READINESS.pop(mas_vieja, None)


_READINESS_DEGRADADO_VACIO = Readiness(
    verdict="degradado", pending_count=0, unknown_count=0, pending_fingerprint="",
    missing=(), reasons=(), resolved=False,
)


def _evaluar_readiness(project: str, ref_value: str, provider, *,
                       yaml_text: str | None = None, yaml_path: str | None = None) -> Readiness:
    """Arma la matriz y evalúa el veredicto. NUNCA lanza (try/except total):
    un bug propio del gate jamás puede romper un disparo."""
    try:
        texto = _resolver_yaml_para_gate(yaml_text=yaml_text, yaml_path=yaml_path)
        if not texto:
            return _READINESS_DEGRADADO_VACIO

        pipeline_provider = provider.name
        yaml_sha256 = hashlib.sha256(texto.encode("utf-8")).hexdigest()
        clave = (provider.name, ref_value, yaml_sha256)

        # (ADICIÓN 2) reuso del veredicto — misma ventana que la idempotencia.
        cacheada = _RECENT_READINESS.get(clave)
        if cacheada is not None:
            readiness_prev, ts = cacheada
            if time.monotonic() - ts <= _READINESS_WINDOW_S:
                return _dc_replace(readiness_prev, source="preview_reusado")

        requisitos = extract_requirements(texto, pipeline_provider)
        entornos = derive_environments(texto, pipeline_provider)

        t0 = time.monotonic()
        resolved = True
        resoluciones: dict = {}
        # (v3, C2 — REVERIFICADO en esta implementación) `with ThreadPoolExecutor`
        # NO alcanza: su __exit__ vuelve a llamar shutdown(wait=True) y JOINEA
        # el hilo huérfano igual, aunque ya se haya llamado shutdown(wait=False)
        # adentro (medido: con `with`, el request tardaba los 3s completos del
        # doble lento, no los 1.5s del presupuesto). Por eso el executor se
        # maneja a mano, sin `with`, y se cierra una SOLA vez en el `finally`
        # con wait=False — así el request nunca espera al hilo huérfano.
        ex = _fut.ThreadPoolExecutor(max_workers=1)
        try:
            f = ex.submit(resolve, requisitos, entornos, pipeline_provider, project, True, texto)
            try:
                resoluciones, _deg = f.result(timeout=GATE_BUDGET_S)
            except _fut.TimeoutError:
                resolved = False
        except Exception:  # noqa: BLE001 — red, proveedor sin configurar, lo que sea
            resolved = False
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        matriz = build_matrix(requisitos, entornos, resoluciones, pipeline_provider)
        readiness = evaluate_readiness(matriz, resolved=resolved, source="calculado",
                                       elapsed_ms=elapsed_ms)

        # (v3, C4) solo se ALMACENA (y solo se reusa) un veredicto resuelto de
        # verdad y con sha no vacío — un `degradado` jamás se persiste.
        if readiness.resolved and yaml_sha256:
            _RECENT_READINESS[clave] = (readiness, time.monotonic())
            _podar_readiness_cache()
        return readiness
    except Exception:  # noqa: BLE001 — el gate JAMAS rompe el trigger
        return _READINESS_DEGRADADO_VACIO


def _serializar_readiness(r: Readiness) -> dict:
    return {
        "verdict": r.verdict,
        "pending_count": r.pending_count,
        "unknown_count": r.unknown_count,
        "pending_fingerprint": r.pending_fingerprint,
        "missing": [{"name": n, "environment": e} for n, e in r.missing],
        "resolved": r.resolved,
        "source": r.source,
        "elapsed_ms": r.elapsed_ms,
    }


# ---------------------------------------------------------------------------
# POST /<project>/trigger — HITL obligatorio
# ---------------------------------------------------------------------------

@bp.post("/<project>/trigger")
def trigger_pipeline_route(project: str):
    """Dispara un pipeline CI (HITL: confirm=True requerido).

    Flag OFF → 404 (guard per-request).
    Sin confirm=True → 400 (riel absoluto HITL).
    """
    if not getattr(_config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", False):
        abort(404)

    body = request.get_json(silent=True) or {}

    # RIEL ABSOLUTO HITL — sin confirm=True → rechazar siempre
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm=True requerido (HITL)"}), 400

    # Normalizar ref
    try:
        _, ref_value = normalize_ref(body.get("ref") or "")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    # Obtener provider
    provider = get_ci_provider(project)
    scopes = _read_pat_scopes(provider)  # None si no verificable (C3')
    ok, msg = validate_trigger_credentials(provider.name, scopes)
    if not ok:
        return jsonify({"error": msg}), 400  # solo si scope CONOCIDO y faltante

    # Plan 260 F4 — el gate corre DESPUES de tener provider.name (hace falta
    # para el reuso de veredicto) y ANTES de la idempotencia, para no consumir
    # la ventana de 60s con un disparo que se va a rechazar.
    readiness = None
    if getattr(_config.config, "STACKY_PIPELINE_TRIGGER_ENV_GATE_ENABLED", False):
        readiness = _evaluar_readiness(project, ref_value, provider,
                                       yaml_text=body.get("yaml_text"))
        if readiness.verdict == "bloquea" and body.get("acknowledge_missing") is not True:
            return jsonify({
                "error": "faltan %d valor(es) obligatorio(s) para esta pipeline"
                         % readiness.pending_count,
                "kind": "env_pending",
                "missing": [{"name": n, "environment": e} for n, e in readiness.missing],
                "pending_fingerprint": readiness.pending_fingerprint,
                "elapsed_ms": readiness.elapsed_ms,
                "hint": "cargá los valores en Variables, o reintentá con acknowledge_missing=true",
            }), 409

    # Plan 294 F7 — variables de ESTA corrida. Va DESPUES del guard de confirm y
    # DESPUES del gate del plan 260, y ANTES de la idempotencia: no consume la
    # ventana de 60 s con un disparo que el gate ya iba a rechazar.
    variables = None
    if getattr(_config.config, "STACKY_PIPELINE_TRIGGER_VARS_ENABLED", False):
        try:
            variables = _validar_variables(body.get("variables"))
        except TriggerVarsInvalid as exc:
            return jsonify({"error": str(exc), "kind": "trigger_vars_invalid"}), 400
    elif body.get("variables"):
        # 409 y no 403: la ruta existe y la flag madre esta encendida. Es un
        # conflicto de configuracion, no un permiso (aca no hay permisos).
        return jsonify({"error": "las variables por corrida estan desactivadas",
                        "kind": "trigger_vars_disabled",
                        "hint": "Activala en Configuracion -> Arnes, categoria DevOps."}), 409

    # Idempotencia
    recent = _recent_triggers(provider.name, ref_value)
    fire, existing = should_trigger(ref_value, body.get("sha", ""), recent, window_seconds=60)
    if not fire:
        return jsonify({
            "pipeline_id": existing,
            "message": "idempotency: pipeline reciente reusado",
            "status": "reused",
        })

    # Disparar
    item_ref = ItemRef(
        item_id=str(body.get("item_id", "")),
        tracker_type=provider.name,
        ref=ref_value,
    )
    try:
        # R10 — sin variables, el llamado es BYTE-IDENTICO al de siempre: se pasan
        # DOS argumentos, no tres con None. No es cosmetica: hay proveedores y
        # dobles vivos cuya firma sigue siendo (item_ref, ref), y mandarles un
        # tercer posicional los rompe con 500 (medido: rompia
        # test_plan72_trigger_endpoint::test_trigger_uses_provider_name_for_item_ref).
        if variables:
            result = provider.trigger_pipeline(item_ref, ref_value, variables)
        else:
            result = provider.trigger_pipeline(item_ref, ref_value)
    except TrackerApiError as exc:
        return jsonify({"error": str(exc), "kind": exc.kind}), exc.status
    except NotImplementedError as exc:
        return jsonify({"error": str(exc)}), 501

    # Guardar el sha del body (referencia del operador) para idempotencia correcta;
    # si el provider retorna un sha más preciso (del commit real), usarlo como fallback.
    recorded_sha = body.get("sha", "") or result.get("sha", "")
    _record_trigger(provider.name, ref_value, recorded_sha, result["id"])

    # Plan 191 — bitácora durable (best-effort: JAMÁS rompe el trigger)
    if getattr(_config.config, "STACKY_CI_RUN_LEDGER_ENABLED", False):
        try:
            from services.ci_run_ledger import append_run
            append_run({
                "project": project,
                "tracker_type": provider.name,
                "ref": ref_value,
                "sha": recorded_sha,
                "pipeline_id": result["id"],
                "web_url": result.get("web_url"),
                "source": "stacky",
                # Plan 260 — aditivo (ENTRY_FIELDS crece 2 claves al final).
                "env_ack": bool(body.get("acknowledge_missing") is True),
                "pending_fingerprint": readiness.pending_fingerprint if readiness else None,
            })
        except Exception:  # noqa: BLE001 — el ledger nunca es camino crítico
            from services.stacky_logger import logger as stacky_logger
            stacky_logger.info("ci_run_ledger", "append_failed", pipeline_id=str(result.get("id")))

    # Plan 260 (ADICIÓN 5) — la latencia del gate viaja SIEMPRE que corrió,
    # también en el 200 del disparo que pasó (no solo en el 409 del bloqueo).
    if readiness is not None:
        result = {**result, "readiness": _serializar_readiness(readiness)}

    return jsonify(result)


# ---------------------------------------------------------------------------
# GET /<project>/trigger-preview — read-only HITL informado (C5, ADICIÓN v2)
# ---------------------------------------------------------------------------

@bp.get("/<project>/trigger-preview")
def trigger_preview_route(project: str):
    """Preview read-only: muestra ref resuelto + último pipeline + si se reusaría.

    NO dispara nada. NO muta _RECENT_TRIGGERS.
    should_trigger se llama UNA sola vez con last_sha del pipeline real (C5).
    """
    if not getattr(_config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", False):
        abort(404)

    ref = request.args.get("ref") or ""
    try:
        kind, ref_value = normalize_ref(ref)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    provider = get_ci_provider(project)
    last = provider.last_pipeline_for_ref(ref_value)
    last_sha = (last or {}).get("sha", "")
    recent = _recent_triggers(provider.name, ref_value)
    # C5: UNA sola llamada con last_sha (no sha="" dos veces)
    fire, existing = should_trigger(ref_value, last_sha, recent, window_seconds=60)

    payload = {
        "kind": kind,
        "ref": ref_value,
        "last_pipeline": last,
        "would_reuse": (not fire),
        "existing_pipeline_id": existing,
    }

    # Plan 260 F4 — campo ADITIVO: sin yaml_path, el preview usa la fuente 2
    # (inventario) y, si tampoco, degradado. El preview ESCRIBE el veredicto
    # en _RECENT_READINESS (ADICIÓN 2) para que el trigger posterior lo reuse.
    if getattr(_config.config, "STACKY_PIPELINE_TRIGGER_ENV_GATE_ENABLED", False):
        readiness = _evaluar_readiness(project, ref_value, provider,
                                       yaml_path=request.args.get("yaml_path"))
        payload["readiness"] = _serializar_readiness(readiness)

    return jsonify(payload)


# ---------------------------------------------------------------------------
# GET /<project>/pipeline/<pipeline_id> — monitoreo (F5, C4)
# ---------------------------------------------------------------------------

@bp.get("/<project>/pipeline/<pipeline_id>")
def monitor_pipeline_route(project: str, pipeline_id: str):
    """Estado del pipeline. Cap de concurrencia real con _ACTIVE_POLLS (C4)."""
    if not getattr(_config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", False):
        abort(404)

    n = _ACTIVE_POLLS.get(pipeline_id, 0)
    if n >= _MAX_ACTIVE_POLLS_PER_PIPELINE:
        return jsonify({"error": "too many active polls for pipeline"}), 429

    _ACTIVE_POLLS[pipeline_id] = n + 1
    try:
        provider = get_ci_provider(project)
        result = provider.monitor_pipeline(pipeline_id)

        # Plan 191 — persistir desenlace (best-effort; JAMÁS rompe el monitor)
        if getattr(_config.config, "STACKY_CI_RUN_LEDGER_ENABLED", False):
            try:
                status = str((result or {}).get("status") or "").lower()
                if status in ("success", "failed", "canceled", "skipped"):
                    from datetime import datetime, timezone
                    from services.ci_run_ledger import update_run_status
                    # Plan 258 F3 — se pasa `project`: el pipeline_id se repite
                    # entre proyectos (medido: el id 42, 6 veces), y sin este
                    # eje el cierre de un proyecto podía escribirse sobre la
                    # corrida de otro.
                    update_run_status(
                        str(pipeline_id), status,
                        datetime.now(timezone.utc).isoformat(),
                        project=project,
                    )
            except Exception:  # noqa: BLE001 — el monitor nunca se degrada por el ledger
                pass

        return jsonify({**result, "tracker_type": provider.name, "source": "ci"})
    except TrackerApiError as exc:
        return jsonify({"error": str(exc), "kind": exc.kind}), exc.status
    except NotImplementedError as exc:
        return jsonify({"error": str(exc)}), 501
    finally:
        _ACTIVE_POLLS[pipeline_id] = max(0, _ACTIVE_POLLS.get(pipeline_id, 1) - 1)


# ---------------------------------------------------------------------------
# GET /runs — bitácora local de corridas disparadas (Plan 191, read-only)
# ---------------------------------------------------------------------------

@bp.get("/runs")
def list_ci_runs_route():
    """Bitácora local de corridas disparadas. Plan 191. Read-only.

    Ruta final GET /api/ci/runs — 1 segmento, no colisiona con /<project>/trigger
    (POST 2 seg), /<project>/trigger-preview (GET 2 seg) ni /<project>/pipeline/<id>
    (GET 3 seg).
    """
    if not getattr(_config.config, "STACKY_CI_RUN_LEDGER_ENABLED", False):
        abort(404)
    project = request.args.get("project") or None
    try:
        limit = int(request.args.get("limit", "50"))
    except ValueError:
        return jsonify({"error": "limit inválido"}), 400
    from services.ci_run_ledger import list_runs
    return jsonify({"runs": list_runs(project=project, limit=limit)})


# ---------------------------------------------------------------------------
# Plan 193 — Triage de fallos CI (read-only): jobs fallidos + log inline.
# Expone el puerto 96 (CILogsProvider) por HTTP con cap y masking. Rutas ADITIVAS
# DESPUÉS de /runs (191). El puerto y sus providers NO se tocan (KPI-3).
# ---------------------------------------------------------------------------

def _map_ci_logs_error(exc):
    """Mapeo espejo del patrón de la casa (KPI-4): TrackerConfigError → 400,
    TrackerApiError → su status (fallback 502). NUNCA un 500 crudo."""
    from services.tracker_provider import TrackerConfigError  # noqa: PLC0415
    if isinstance(exc, TrackerConfigError):
        return jsonify({"error": str(exc), "kind": "tracker_config"}), 400
    if isinstance(exc, TrackerApiError):
        return jsonify({"error": str(exc), "kind": exc.kind}), exc.status or 502
    raise exc


@bp.get("/<project>/pipeline/<pipeline_id>/failed-jobs")
def ci_failed_jobs_route(project: str, pipeline_id: str):
    """Jobs fallidos del pipeline (puerto 96, read-only). Plan 193.

    Flag OFF → 404. Errores del tracker mapeados (KPI-4), nunca 500 crudo.
    """
    if not getattr(_config.config, "STACKY_CI_FAILURE_TRIAGE_ENABLED", False):
        abort(404)
    from services.ci_logs_provider import get_ci_logs_provider  # noqa: PLC0415
    from services.tracker_provider import TrackerConfigError  # noqa: PLC0415
    try:
        provider = get_ci_logs_provider(project)
        jobs = provider.list_failed_jobs(str(pipeline_id))
    except (TrackerConfigError, TrackerApiError) as exc:
        return _map_ci_logs_error(exc)
    return jsonify({"jobs": jobs, "provider": provider.name})


@bp.get("/<project>/job/<job_id>/log")
def ci_job_log_route(project: str, job_id: str):
    """Log de un job, con tail 200K y masking (KPI-1/KPI-2). Plan 193.

    Flag OFF → 404. Errores del tracker mapeados (KPI-4), nunca 500 crudo.
    """
    if not getattr(_config.config, "STACKY_CI_FAILURE_TRIAGE_ENABLED", False):
        abort(404)
    from services.ci_logs_provider import get_ci_logs_provider  # noqa: PLC0415
    from services.ci_log_view import tail_and_mask  # noqa: PLC0415
    from services.tracker_provider import TrackerConfigError  # noqa: PLC0415
    try:
        provider = get_ci_logs_provider(project)
        text = provider.get_job_log(str(job_id))
    except (TrackerConfigError, TrackerApiError) as exc:
        return _map_ci_logs_error(exc)
    out = tail_and_mask(text)
    out["provider"] = provider.name  # C5 — consistencia con /failed-jobs
    return jsonify(out)
