"""api/night_foundry.py — Plan 202 E7. Superficie de la Fragua Nocturna.

url_prefix="/night-foundry" -> ruta final /api/night-foundry/...
Guard de la flag PER-REQUEST (abort(404)); nunca gateado en el registro del blueprint.

Todo lo que expone es LECTURA o HITL explícito:
  * `GET /status`, `GET /digest/latest`, `GET /ledger` — solo lectura.
  * `POST /run-one-turn` — corre UN ítem determinista porque el operador clickeó.
    No arma autonomía: no hay scheduler, watcher ni hook de arranque que lo llame
    (KPI-9, costo ocioso 0).
  * `POST/DELETE /stop` — kill-switch de un clic. SOLO detiene o rehabilita; jamás
    arranca una corrida.
"""
from __future__ import annotations

from datetime import datetime, timezone

import config as _config
from flask import Blueprint, abort, jsonify, request

from services import night_foundry_digest as digest
from services import night_foundry_ledger as ledger
from services import night_foundry_orchestrator as orch
from services import night_foundry_planner as planner

bp = Blueprint("night_foundry", __name__, url_prefix="/night-foundry")


def _guard():
    # la INSTANCIA, no el módulo: getattr del módulo devuelve el default y mata el
    # branch OFF (el test flag-off pasaría en falso).
    if not getattr(_config.config, "STACKY_NIGHT_FOUNDRY_ENABLED", False):
        abort(404)


def _budget() -> int:
    try:
        return int(getattr(_config.config, "STACKY_NIGHT_FOUNDRY_TOKEN_BUDGET", 40000) or 40000)
    except (TypeError, ValueError):
        return 40000


def _hoy() -> str:
    return f"{datetime.now(timezone.utc):%Y-%m-%d}"


@bp.get("/status")
def status_route():
    """Estado de la Fragua, incluida su DISPONIBILIDAD real en este runtime.

    Que la Fragua no pueda correr (deploy congelado, sin repo git, sin carpeta de
    planes) es un hecho VISIBLE con motivo legible, no un silencio que se confunda
    con "no había trabajo".
    """
    _guard()
    disp = planner.foundry_availability()
    noche = _hoy()
    return jsonify({
        "availability": disp,
        "night": noche,
        "budget_tokens": _budget(),
        "spent_tokens": ledger.spent_tokens(noche),
        "stopped": orch._stop_file().exists(),
        "backlog": planner.foundry_backlog_gate(noche),
    }), 200


@bp.get("/digest/latest")
def latest_digest_route():
    _guard()
    return jsonify({"digest": digest.latest_digest(),
                    "availability": planner.foundry_availability()}), 200


@bp.get("/ledger")
def ledger_route():
    _guard()
    noche = (request.args.get("night") or "").strip() or _hoy()
    estado = (request.args.get("state") or "").strip() or None
    return jsonify({"night": noche, "items": ledger.list_items(night=noche, state=estado)}), 200


@bp.post("/run-one-turn")
def run_one_turn_route():
    """Botón manual: deriva la cola (opcional) y procesa UN ítem determinista.

    HITL por construcción: corre solo cuando el operador clickea. Un ítem del carril
    de crítica NO se ejecuta acá —necesita el runtime Claude— y queda pendiente con
    el motivo explícito, en vez de fingir que se hizo.
    """
    _guard()
    disp = planner.foundry_availability()
    if not disp["available"]:
        return jsonify({"ok": False, "processed": None, "reason": disp["reason_code"],
                        "detail": disp["reason"], "availability": disp}), 409

    cuerpo = request.get_json(silent=True) or {}
    noche = str(cuerpo.get("night") or "").strip() or _hoy()
    resumen = None
    if cuerpo.get("plan", True):
        resumen = planner.plan_night(noche)

    parar, motivo = orch.should_stop(noche, _budget())
    if parar:
        return jsonify({"ok": True, "processed": None, "reason": motivo,
                        "plan": resumen}), 200

    item = ledger.claim_next()
    if item is None:
        return jsonify({"ok": True, "processed": None, "reason": "queue_empty",
                        "plan": resumen}), 200
    if item["lane"] == "critic":
        ledger.record_result(item["id"], "pending")
        return jsonify({"ok": True, "processed": None, "reason": "critic_necesita_claude",
                        "item": item, "plan": resumen}), 200
    try:
        res = orch.run_deterministic_item(item)
        if res.get("readonly_ok") is False:
            ledger.record_result(item["id"], "failed", output_ref=res.get("output_ref"),
                                 error="violacion read-only: el worker modifico el working tree")
            estado = "failed"
        else:
            ledger.record_result(item["id"], "done", output_ref=res.get("output_ref"),
                                 cost_tokens=res.get("cost_tokens", 0))
            estado = "done"
    except Exception as exc:  # noqa: BLE001
        ledger.record_result(item["id"], "failed", error=str(exc)[:300])
        return jsonify({"ok": False, "processed": item["id"], "state": "failed",
                        "error": str(exc)[:300], "plan": resumen}), 200
    return jsonify({"ok": True, "processed": item["id"], "state": estado,
                    "lane": item["lane"], "target": item["target"],
                    "output_ref": res.get("output_ref"), "plan": resumen}), 200


@bp.post("/stop")
def stop_on_route():
    """Detiene la Fragua sin tocar variables de entorno: crea el archivo STOP."""
    _guard()
    p = orch._stop_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("", encoding="utf-8")
    return jsonify({"stopped": True}), 200


@bp.delete("/stop")
def stop_off_route():
    """Rehabilita: borra el archivo STOP. Detener/reanudar, NUNCA arrancar."""
    _guard()
    p = orch._stop_file()
    if p.exists():
        p.unlink()
    return jsonify({"stopped": False}), 200
