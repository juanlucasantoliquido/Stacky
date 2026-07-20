"""api/evolution.py — Plan 167: Centro de Evolución (contratos §4.8).

`/health` responde SIEMPRE 200 (patrón api/metrics.py:565-573) para el gating
de navegación; el resto está gateado por STACKY_EVOLUTION_CENTER_ENABLED (404
con OFF). El kill-switch env-only STACKY_EVOLUTION_HARD_DISABLE (A1) gana
SIEMPRE: apaga todo salvo `/health` (que reporta `hard_disabled`).
Imports de `services` LAZY dentro de cada handler (patrón Plan 128).
"""
from flask import Blueprint, jsonify, request

from config import config as _cfg  # G1

bp = Blueprint("evolution", __name__, url_prefix="/evolution")


def _enabled() -> bool:
    from services import evolution_store as _st  # lazy

    if _st.evolution_hard_disabled():  # A1: el kill-switch gana SIEMPRE
        return False
    return bool(getattr(_cfg, "STACKY_EVOLUTION_CENTER_ENABLED", False))


def _cycle_enabled() -> bool:
    return _enabled() and bool(getattr(_cfg, "STACKY_EVOLUTION_CYCLE_ENABLED", False))


def _disabled_resp():
    return (
        jsonify({
            "ok": False, "error": "evolution_disabled",
            "message": "El Centro de Evolución está deshabilitado (STACKY_EVOLUTION_CENTER_ENABLED).",
        }),
        404,
    )


def _clamp(raw, default: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(1, min(200, value))


@bp.get("/health")
def health():
    from services import evolution_store as st

    return jsonify({
        "ok": True, "flag_enabled": _enabled(),
        "hard_disabled": st.evolution_hard_disabled(),
    })


@bp.get("/overview")
def overview():
    if not _enabled():
        return _disabled_resp()
    from services import evolution_store as st

    aspects = st.ensure_seed_aspects()
    proposals = st.list_proposals()
    counts = {s: 0 for s in st.VALID_STATUSES}
    for p in proposals:
        status = p.get("status")
        if status in counts:
            counts[status] += 1
    tail = st.read_cycles_tail(1)
    return jsonify({
        "ok": True, "aspects": aspects, "counts": counts,
        "last_cycle": tail[0] if tail else None,
    })


@bp.get("/proposals")
def list_proposals():
    if not _enabled():
        return _disabled_resp()
    from services import evolution_store as st

    return jsonify({
        "ok": True,
        "proposals": st.list_proposals(
            status=request.args.get("status") or None,
            aspect_id=request.args.get("aspect_id") or None,
            origin=request.args.get("origin") or None,
        ),
    })


@bp.get("/proposals/<pid>")
def get_proposal(pid):
    if not _enabled():
        return _disabled_resp()
    from services import evolution_store as st

    p = st.get_proposal(pid)
    if p is None:
        return jsonify({"ok": False, "error": "proposal_not_found"}), 404
    return jsonify({"ok": True, "proposal": p})


@bp.post("/proposals")
def create_proposal():
    if not _enabled():
        return _disabled_resp()
    from services import evolution_store as st

    body = request.get_json(silent=True) or {}
    origin = body.get("origin") or "manual"
    actor = "optimizer" if origin == "optimizer" else "operator"
    try:
        p = st.create_proposal(
            aspect_id=body.get("aspect_id"),
            title=body.get("title") or "",
            rationale=body.get("rationale") or "",
            origin=origin,
            artifact_type=body.get("artifact_type") or "free_text",
            target_ref=body.get("target_ref"),
            proposed_content=body.get("proposed_content"),
            evidence=body.get("evidence"),
            initial_status=body.get("initial_status") or "pending_review",
            cycle_id=body.get("cycle_id"),
            parent_proposal_id=body.get("parent_proposal_id"),
            base_hash=body.get("base_hash"),
            actor=actor,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": "invalid_payload", "message": str(exc)}), 400
    return jsonify({"ok": True, "proposal": p}), 201


@bp.post("/proposals/<pid>/transition")
def transition_proposal(pid):
    if not _enabled():
        return _disabled_resp()
    from services import evolution_apply as ap
    from services import evolution_store as st

    body = request.get_json(silent=True) or {}
    action = body.get("action")
    note = body.get("note")
    force = bool(body.get("force", False))
    try:
        if action == "apply":
            p = ap.apply_proposal(pid, actor="operator")
        elif action == "rollback":
            p = ap.rollback_proposal(pid, actor="operator", force=force)
        else:
            p = st.transition(pid, action, actor="operator", note=note)
    except st.InvalidTransition as exc:
        return jsonify({"ok": False, "error": "invalid_transition", "message": str(exc)}), 409
    except KeyError:
        return jsonify({"ok": False, "error": "proposal_not_found"}), 404
    except ValueError as exc:
        msg = str(exc)
        if "artifact_not_appliable" in msg:
            return jsonify({"ok": False, "error": "artifact_not_appliable", "message": msg}), 409
        return jsonify({"ok": False, "error": "invalid_payload", "message": msg}), 400
    except RuntimeError as exc:
        msg = str(exc)
        if msg.startswith("target_drifted"):
            return jsonify({"ok": False, "error": "target_drifted", "message": msg}), 409
        if "evolution_hard_disabled" in msg:
            return _disabled_resp()
        return jsonify({"ok": False, "error": "apply_failed", "message": msg}), 502
    return jsonify({"ok": True, "proposal": p})


@bp.post("/cycle/run")
def cycle_run():
    if not _enabled():
        return _disabled_resp()
    if not _cycle_enabled():
        return (
            jsonify({
                "ok": False, "error": "evolution_cycle_disabled",
                "message": "El ciclo MAPE está deshabilitado (STACKY_EVOLUTION_CYCLE_ENABLED).",
            }),
            404,
        )
    from services import evolution_cycle as cyc

    body = request.get_json(silent=True) or {}
    aspects = body.get("aspects")
    use_llm = bool(body.get("use_llm", True))
    try:
        record = cyc.run_cycle(aspects=aspects, use_llm=use_llm)
    except RuntimeError as exc:
        msg = str(exc)
        if "cycle_already_running" in msg:
            return jsonify({"ok": False, "error": "cycle_already_running", "message": msg}), 409
        if "evolution_hard_disabled" in msg:
            return _disabled_resp()
        raise
    return jsonify({"ok": True, "cycle": record})


@bp.get("/cycles")
def cycles():
    if not _enabled():
        return _disabled_resp()
    from services import evolution_store as st

    return jsonify({"ok": True, "cycles": st.read_cycles_tail(_clamp(request.args.get("limit"), 20))})


@bp.get("/ledger")
def ledger():
    if not _enabled():
        return _disabled_resp()
    from services import evolution_store as st

    return jsonify({"ok": True, "events": st.read_ledger_tail(_clamp(request.args.get("limit"), 50))})
