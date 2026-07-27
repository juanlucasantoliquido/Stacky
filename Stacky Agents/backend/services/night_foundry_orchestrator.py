"""services/night_foundry_orchestrator.py — Plan 202 E5 (La Fragua Nocturna F0/TMV).

Coordinador DETERMINISTA del turno nocturno: drena la cola de a UN item por
iteracion (cero colision estructural), corta duro por presupuesto o kill-switch, y
es resumible (los `done` no se re-ejecutan; los `claimed` huerfanos se re-claman).

El dispatch del carril `critic` (LLM) lo inyecta el skill Claude-nativo (E7) como
callable; sin el, los critic quedan `pending` y el operador los corre a mano
(fallback declarado para Codex/Copilot).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import runtime_paths
from services import night_foundry_ledger as L
from services import night_foundry_planner as P
from services import night_foundry_workers as W

logger = logging.getLogger(__name__)

# Estimado de costo de UNA critica LLM. Se PRE-RESERVA contra el presupuesto ANTES
# de dispatchar: el costo real solo se conoce post-hoc, asi que sin pre-carga un
# solo critic podria pasarse del techo (R2 seria un tope blando, no duro).
CRITIC_EST_TOKENS = 6000


def _stop_file() -> Path:
    return Path(runtime_paths.data_dir()) / "night_foundry" / "STOP"


def _env_on(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def should_stop(night: str, budget: int) -> tuple[bool, str]:
    """Kill-switches redundantes, evaluados ANTES de tomar cada item.

    Dos env: `STACKY_NIGHT_FOUNDRY_HARD_DISABLE` (PROPIO) y
    `STACKY_EVOLUTION_HARD_DISABLE` (mismo nombre que reserva el plan 167; hoy sin
    reader en main — forward-compatible: cuando RSI llegue, un solo boton detiene
    RSI Y la Fragua). Mas el archivo STOP, creable de un clic desde el panel.
    """
    if _env_on("STACKY_NIGHT_FOUNDRY_HARD_DISABLE") or _env_on("STACKY_EVOLUTION_HARD_DISABLE"):
        return True, "hard_disable"
    if _stop_file().exists():
        return True, "stop_file"
    if L.spent_tokens(night) >= budget:
        return True, "budget"
    return False, ""


def run_deterministic_item(item: dict) -> dict:
    """Ejecuta un item de carril determinista (auditor/package/reconciler).

    El `critic` NO entra aca: no hay camino por el que un carril LLM se ejecute sin
    el dispatch explicito del runtime Claude.
    """
    lane, target = item["lane"], item["target"]
    if lane == "auditor":
        return W.run_auditor(target.split("branch:", 1)[1])
    if lane == "package":
        nn = target.split("plan:", 1)[1]
        return W.build_package(nn, P._doc_for(nn))
    if lane == "reconciler":
        nn = target.split("plan:", 1)[1]
        r = W.run_reconciler(nn, P._doc_for(nn))
        return {"output_ref": None, "cost_tokens": 0, "reconciler": r}
    raise ValueError(f"carril no determinista: {lane}")


def run_night(night: str | None = None, *, budget: int, dispatch_critic=None) -> dict:
    """Loop serializado: UN item por iteracion, con `should_stop` antes de cada uno.

    `seen` son los ids salteados en ESTA corrida (critic sin dispatch, o critic sin
    presupuesto para su pre-reserva): se excluyen del claim para que el loop TERMINE
    en vez de re-clamarlos indefinidamente.
    """
    night = night or f"{datetime.now(timezone.utc):%Y-%m-%d}"

    # Guard de disponibilidad ANTES de tocar la cola. Falla CERRADO (no procesa
    # nada) y VISIBLE (el motivo viaja al digest y al panel): un deploy congelado
    # no tiene repo git ni carpeta de planes, asi que la Fragua no corre ahi.
    disp = P.foundry_availability()
    if not disp["available"]:
        logger.warning("night_foundry: turno no ejecutado (%s): %s",
                       disp["reason_code"], disp["reason"])
        return {"night": night, "stopped_reason": "unavailable",
                "unavailable_reason_code": disp["reason_code"],
                "unavailable_reason": disp["reason"],
                "spent_tokens": L.spent_tokens(night)}

    stopped = "queue_empty"
    seen: set[str] = set()
    while True:
        stop, why = should_stop(night, budget)
        if stop:
            stopped = why
            break
        item = L.claim_next(exclude_ids=seen)
        if item is None:
            stopped = "queue_empty"
            break
        if item["lane"] == "critic":
            if dispatch_critic is None:
                # Fallback sin runtime Claude: dejar pending y no re-clamar hoy.
                L.record_result(item["id"], "pending")
                seen.add(item["id"])
                continue
            if L.spent_tokens(night) + CRITIC_EST_TOKENS > budget:
                L.record_result(item["id"], "pending")
                seen.add(item["id"])
                stopped = "budget"
                break
        try:
            if item["lane"] == "critic":
                res = dispatch_critic(item)  # invoca el skill criticar-y-mejorar-plan
            else:
                res = run_deterministic_item(item)
            # KPI-5: un worker que violo la post-condicion read-only NO se acepta como
            # exitoso; el item se marca failed para que el digest lo denuncie.
            if res.get("readonly_ok") is False:
                L.record_result(item["id"], "failed", output_ref=res.get("output_ref"),
                                cost_tokens=res.get("cost_tokens", 0),
                                error="violacion read-only: el worker modifico el working tree")
            else:
                L.record_result(item["id"], "done", output_ref=res.get("output_ref"),
                                cost_tokens=res.get("cost_tokens", 0))
        except Exception as e:  # noqa: BLE001 — un item roto no tumba la noche entera
            L.record_result(item["id"], "failed", error=str(e)[:300])
    return {"night": night, "stopped_reason": stopped, "spent_tokens": L.spent_tokens(night)}
