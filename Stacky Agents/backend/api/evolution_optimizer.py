"""api/evolution_optimizer.py — Plan 169 F4: optimizador evolutivo (contratos §4.8).

Tercer blueprint del Centro de Evolución (mismo url_prefix `/evolution`, nombre distinto
— válido en Flask, rutas no colisionan con el 167 ni las `/fitness/*` del 168).
`/optimizer/health` responde SIEMPRE 200; el resto está gateado por `_optimizer_enabled()`
(CENTER && OPTIMIZER) → 404 `optimizer_disabled` con OFF (byte-idéntico, KPI-6). Imports
de services LAZY dentro de cada handler (patrón 167/168 F4/F5).
"""
from flask import Blueprint, jsonify, request

from config import config as _cfg  # G1

bp = Blueprint("evolution_optimizer", __name__, url_prefix="/evolution")

_GENERATOR_UNAVAILABLE_MSG = (
    "El generador local no está configurado (LOCAL_LLM_ENDPOINT). "
    "Configuralo en el Arnés o elegí el generador runtime."
)
_VALID_RUNTIMES = (None, "github_copilot", "claude_code_cli", "codex_cli")


def _optimizer_enabled() -> bool:
    return bool(getattr(_cfg, "STACKY_EVOLUTION_CENTER_ENABLED", False)) and \
        bool(getattr(_cfg, "STACKY_EVOLUTION_OPTIMIZER_ENABLED", False))


def _harness_enabled() -> bool:
    return bool(getattr(_cfg, "STACKY_EVOLUTION_CENTER_ENABLED", False)) and \
        bool(getattr(_cfg, "STACKY_EVAL_HARNESS_ENABLED", False))


def _disabled_resp():
    return jsonify({
        "ok": False, "error": "optimizer_disabled",
        "message": "El optimizador evolutivo está deshabilitado (STACKY_EVOLUTION_OPTIMIZER_ENABLED).",
    }), 404


def _clamp(raw, default: int, lo: int, hi: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, value))


# ── Health (siempre 200) ─────────────────────────────────────────────────────
@bp.get("/optimizer/health")
def health():
    from services import variant_generator
    mode, ready = variant_generator.resolve_generator_mode()
    return jsonify({
        "ok": True,
        "flag_enabled": _optimizer_enabled(),
        "generator_mode": mode,
        "generator_ready": ready,
        "harness_enabled": _harness_enabled(),
    })


# ── Targets ──────────────────────────────────────────────────────────────────
@bp.get("/optimizer/targets")
def targets():
    if not _optimizer_enabled():
        return _disabled_resp()
    from services import evolution_optimizer

    return jsonify({"ok": True, "targets": evolution_optimizer.list_targets()})


# ── Lanzar corrida ───────────────────────────────────────────────────────────
@bp.post("/optimizer/run")
def run():
    if not _optimizer_enabled():
        return _disabled_resp()
    from services import evolution_optimizer
    from services import evolution_optimizer_store as store

    body = request.get_json(silent=True) or {}
    target_ref = body.get("target_ref")
    runtime = body.get("runtime")
    use_judge = bool(body.get("use_judge", True))  # C11
    rng_seed = body.get("rng_seed")

    if runtime not in _VALID_RUNTIMES:
        return jsonify({"ok": False, "error": "invalid_payload", "message": "runtime inválido"}), 400
    if rng_seed is not None and (isinstance(rng_seed, bool) or not isinstance(rng_seed, int)):
        return jsonify({"ok": False, "error": "invalid_payload", "message": "rng_seed debe ser entero"}), 400
    if not _harness_enabled():
        return jsonify({"ok": False, "error": "fitness_harness_disabled",
                        "message": "El arnés de fitness está deshabilitado; sin él no hay fitness."}), 409
    try:
        started = evolution_optimizer.start_optimization_run(
            target_ref=target_ref, runtime=runtime, use_judge=use_judge, rng_seed=rng_seed,
        )
    except KeyError:
        return jsonify({"ok": False, "error": "target_not_found"}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": "invalid_payload", "message": str(exc)}), 400
    except RuntimeError as exc:
        msg = str(exc)
        if "optimizer_already_running" in msg:
            return jsonify({"ok": False, "error": "optimizer_already_running"}), 409
        if "generator_unavailable" in msg:
            return jsonify({"ok": False, "error": "generator_unavailable",
                            "message": _GENERATOR_UNAVAILABLE_MSG}), 409
        raise
    # C4 — responder el estado REAL al momento de responder (relee el store DESPUÉS de lanzar).
    current = store.get_run(started["id"]) or started
    return jsonify({"ok": True, "run": current}), 202


@bp.post("/optimizer/runs/<rid>/cancel")
def cancel(rid):
    if not _optimizer_enabled():
        return _disabled_resp()
    from services import evolution_optimizer_store as store

    try:
        updated = store.request_cancel(rid)
    except KeyError:
        return jsonify({"ok": False, "error": "run_not_found"}), 404
    except ValueError:
        return jsonify({"ok": False, "error": "run_not_running"}), 409
    return jsonify({
        "ok": True, "run": updated,
        "note": "cancelación cooperativa: se aplica entre pasos; la invocación en curso termina sola",
    })


@bp.get("/optimizer/runs/<rid>")
def get_run(rid):
    if not _optimizer_enabled():
        return _disabled_resp()
    from services import evolution_optimizer_store as store

    run_obj = store.get_run(rid)
    if run_obj is None:
        return jsonify({"ok": False, "error": "run_not_found"}), 404
    return jsonify({"ok": True, "run": run_obj})


@bp.get("/optimizer/runs")
def runs():
    if not _optimizer_enabled():
        return _disabled_resp()
    from services import evolution_optimizer_store as store

    return jsonify({"ok": True, "runs": store.list_runs(_clamp(request.args.get("limit"), 20, 1, 100))})


@bp.get("/optimizer/archive")
def archive():
    if not _optimizer_enabled():
        return _disabled_resp()
    from services import evolution_optimizer_store as store

    return jsonify({"ok": True, "entries": store.read_archive(
        run_id=request.args.get("run_id") or None,
        aspect_key=request.args.get("aspect_key") or None,
        limit=_clamp(request.args.get("limit"), 50, 1, 200),
    )})


@bp.get("/optimizer/lessons")
def lessons():
    if not _optimizer_enabled():
        return _disabled_resp()
    from services import evolution_optimizer_store as store

    return jsonify({"ok": True, "lessons": store.read_lessons_tail(
        aspect_key=request.args.get("aspect_key") or None,
        limit=_clamp(request.args.get("limit"), 20, 1, 100),
    )})


@bp.get("/optimizer/pareto")
def pareto():
    if not _optimizer_enabled():
        return _disabled_resp()
    from services import evolution_optimizer_store as store

    aspect_key = request.args.get("aspect_key")
    if not aspect_key:
        return jsonify({"ok": False, "error": "aspect_key_requerido"}), 400
    return jsonify({"ok": True, "front": store.get_pareto(aspect_key)})
