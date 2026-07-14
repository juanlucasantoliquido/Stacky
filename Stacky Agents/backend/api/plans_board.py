"""api/plans_board.py — Plan 128: tablero de evolución de planes (solo lectura).

`/health` responde siempre 200 (patrón Plan 87) e incluye `next_free_number`
SIN gate de flag (cómputo barato, un solo iterdir()) — ver "[v2 ADICIÓN
ARQUITECTO]" en docs/128_PLAN_TABLERO_EVOLUCION_PLANES.md. `/list` y
`/detail/<n>` sí están gateados por STACKY_PLANS_BOARD_ENABLED (404 con OFF).
"""
from flask import Blueprint, jsonify, request

from config import config

bp = Blueprint("plans_board", __name__, url_prefix="/plans-board")


def _enabled() -> bool:
    return bool(getattr(config, "STACKY_PLANS_BOARD_ENABLED", False))


def _disabled_resp():
    return (
        jsonify(
            {
                "ok": False,
                "error": "plans_board_disabled",
                "message": "El tablero de planes está deshabilitado (STACKY_PLANS_BOARD_ENABLED).",
            }
        ),
        404,
    )


@bp.get("/health")
def plans_board_health():
    # [v2 ADICIÓN ARQUITECTO] next_free_number va SIEMPRE, sin gate de flag: cómputo barato
    # (un iterdir(), sin ledger/git) que cierra el anti-colisión aunque el tablero esté OFF.
    from services import plans_board  # import lazy (patrón Plan 109, api/docs.py:224)

    docs_dir = plans_board.docs_dir_default()
    next_n = plans_board.next_free_number(docs_dir) if docs_dir.exists() else None
    return jsonify({"ok": True, "flag_enabled": _enabled(), "next_free_number": next_n})


@bp.get("/list")
def plans_board_list():
    if not _enabled():
        return _disabled_resp()
    from services import plans_board  # import lazy (patrón Plan 109, api/docs.py:224)

    refresh = request.args.get("refresh", "").strip() == "1"
    return jsonify(plans_board.get_board_cached(refresh=refresh))


@bp.get("/detail/<int:number>")
def plans_board_detail(number: int):
    if not _enabled():
        return _disabled_resp()
    from services import plans_board

    payload = plans_board.get_detail(number)
    if payload is None:
        return jsonify({"ok": False, "error": "plan_not_found"}), 404
    return jsonify(payload)
