"""Plan 72 F2 — Blueprint CI: trigger y monitoreo de pipelines (HITL).

Endpoints:
  POST /api/ci/<project>/trigger         — dispara pipeline (confirm=True obligatorio).
  GET  /api/ci/<project>/trigger-preview — preview read-only (no dispara).
  GET  /api/ci/<project>/pipeline/<id>   — estado del pipeline (monitor).

Blueprint registrado en api/__init__.py con url_prefix="/ci" sobre api_bp
(url_prefix="/api") → rutas finales /api/ci/... (C1, sin doble prefijo).

Flag STACKY_PIPELINE_TRIGGER_ENABLED: default OFF, leída per-request (C2').
Si OFF → guard 404 per-request; el blueprint siempre está registrado.
"""
from __future__ import annotations

import time

import config as _config
from flask import Blueprint, abort, jsonify, request
from services.ci_provider import get_ci_provider, ItemRef
from services.ci_trigger_rules import normalize_ref, validate_trigger_credentials, should_trigger
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


def _read_pat_scopes(provider) -> set[str] | None:
    """Best-effort (C3'): lee scopes del client_profile si están disponibles.

    Devuelve None cuando no hay metadata de scopes → validate_trigger_credentials
    no bloqueará (retorna True).
    """
    # En esta versión no hay metadata de scopes en el client; siempre None → no bloquear.
    # Si en el futuro client_profile expone scopes verificables, leerlos aquí.
    return None


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
        result = provider.trigger_pipeline(item_ref, ref_value)
    except TrackerApiError as exc:
        return jsonify({"error": str(exc), "kind": exc.kind}), exc.status
    except NotImplementedError as exc:
        return jsonify({"error": str(exc)}), 501

    # Guardar el sha del body (referencia del operador) para idempotencia correcta;
    # si el provider retorna un sha más preciso (del commit real), usarlo como fallback.
    recorded_sha = body.get("sha", "") or result.get("sha", "")
    _record_trigger(provider.name, ref_value, recorded_sha, result["id"])
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
    return jsonify({
        "kind": kind,
        "ref": ref_value,
        "last_pipeline": last,
        "would_reuse": (not fire),
        "existing_pipeline_id": existing,
    })


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
