"""V2.2 (Plan 22) — Presupuesto por ticket: degradar antes que bloquear.

El operador define un tope de costo acumulado por ticket
(`STACKY_BUDGET_PER_TICKET_USD`, 0.0 = sin límite). Antes de lanzar un run:

1. Se suma lo ya gastado por el ticket (reales + estimados, reusando el motor de
   costos del centro de costos: `cost_analytics.extract_cost_row`).
2. Si `gastado + estimación_del_run > presupuesto` → se **degrada** el modelo un
   escalón (opus → sonnet → haiku) y se sella la decisión.
3. Si aun degradado sigue excediendo → se **bloquea** con 402, y el operador puede
   forzar explícitamente con `force_budget=true`.

Riel: este módulo vive en `services/` y NUNCA importa de `api/`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("stacky.run_budget")

# Escalera de degradación: un escalón por vez, del más caro al más barato.
# Se matchea por subcadena para no atarse a una generación concreta de modelos.
_DEGRADE_LADDER: list[tuple[str, str]] = [
    ("opus", "sonnet"),
    ("sonnet", "haiku"),
]

ACTION_OK = "ok"
ACTION_DEGRADE = "degrade"
ACTION_BLOCK = "block"


@dataclass
class BudgetDecision:
    """Veredicto del presupuesto para un run que todavía no se lanzó."""

    action: str  # "ok" | "degrade" | "block"
    spent_usd: float
    budget_usd: float
    projected_usd: float
    model_from: str | None = None
    model_to: str | None = None
    forced: bool = False

    def to_metadata(self) -> dict:
        """Sello para metadata de la ejecución. Sólo cuando hubo decisión activa."""
        return {
            "budget_degraded": self.action == ACTION_DEGRADE,
            "budget_spent_usd": round(self.spent_usd, 6),
            "budget_usd": round(self.budget_usd, 6),
            "budget_model_from": self.model_from,
            "budget_model_to": self.model_to,
            "budget_forced": self.forced,
        }

    def to_error_payload(self) -> dict:
        """Cuerpo del 402 (la forma que el plan 22 V2.2 especifica)."""
        return {
            "error": "budget_exceeded",
            "spent": round(self.spent_usd, 6),
            "budget": round(self.budget_usd, 6),
            "projected": round(self.projected_usd, 6),
            "hint": "reenviá con force_budget=true para lanzarlo igual",
        }


def degrade_model(model: str | None) -> str | None:
    """Baja el modelo UN escalón. None si no hay a dónde bajar (o no se reconoce).

    Nunca sube: si el modelo ya es el más barato de la escalera, devuelve None.
    """
    if not model:
        return None
    lowered = str(model).lower()
    for caro, barato in _DEGRADE_LADDER:
        if caro in lowered:
            return lowered.replace(caro, barato)
    return None


def spent_for_ticket(ticket_id: int) -> float:
    """Suma el costo (reportado o estimado) de todas las ejecuciones del ticket."""
    if not ticket_id:
        return 0.0
    try:
        from db import session_scope
        from models import AgentExecution
        from services.cost_analytics import extract_cost_row

        total = 0.0
        with session_scope() as session:
            rows = (
                session.query(AgentExecution)
                .filter(AgentExecution.ticket_id == ticket_id)
                .all()
            )
            for row in rows:
                try:
                    cost = extract_cost_row(row.metadata_dict or {}).cost_usd
                except Exception:  # noqa: BLE001
                    cost = None
                if cost:
                    total += float(cost)
        return total
    except Exception as exc:  # noqa: BLE001
        # Falla-abierto: si no se puede medir el gasto, NO se bloquea al operador.
        logger.warning("V2.2 no se pudo calcular el gasto del ticket %s: %s", ticket_id, exc)
        return 0.0


def evaluate(
    *,
    ticket_id: int,
    model: str | None = None,
    estimated_run_usd: float = 0.0,
    force: bool = False,
) -> BudgetDecision | None:
    """Decide si el run procede, se degrada o se bloquea. None = flag apagada.

    Devolver None significa "no corresponde evaluar" y deja el launch byte-idéntico.
    """
    try:
        from config import config as _cfg

        budget = float(getattr(_cfg, "STACKY_BUDGET_PER_TICKET_USD", 0.0) or 0.0)
    except Exception:  # noqa: BLE001
        return None

    if budget <= 0:
        return None  # 0.0 = sin límite

    spent = spent_for_ticket(ticket_id)
    projected = spent + max(0.0, float(estimated_run_usd or 0.0))

    if projected <= budget:
        return BudgetDecision(
            action=ACTION_OK, spent_usd=spent, budget_usd=budget, projected_usd=projected
        )

    if force:
        # Override explícito del operador: se deja pasar, pero queda sellado.
        return BudgetDecision(
            action=ACTION_OK,
            spent_usd=spent,
            budget_usd=budget,
            projected_usd=projected,
            forced=True,
        )

    cheaper = degrade_model(model)
    if cheaper:
        return BudgetDecision(
            action=ACTION_DEGRADE,
            spent_usd=spent,
            budget_usd=budget,
            projected_usd=projected,
            model_from=model,
            model_to=cheaper,
        )

    return BudgetDecision(
        action=ACTION_BLOCK,
        spent_usd=spent,
        budget_usd=budget,
        projected_usd=projected,
        model_from=model,
    )
