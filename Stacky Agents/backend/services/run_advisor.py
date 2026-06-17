"""V1.2 — Smart dispatch v1: recomendación (no imposición) de runtime+modelo.

Reglas deterministas, SIN LLM. Usa los KPIs que el arnés ya recolecta para
sugerir el mejor runtime por agent_type, y delega el modelo en llm_router
(el clamp duro a sonnet aplica solo). v1 nunca fuerza (enforcement es V2.2).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger("stacky.services.run_advisor")

_DEFAULT_RUNTIME = "github_copilot"
_MIN_RUNS_TO_SCORE = 5

# Pesos del score (plan §V1.2): éxito-sin-intervención (3) − autocorrect (1) − costo (1)
_W_SUCCESS = 3.0
_W_AUTOCORRECT = 1.0
_W_COST = 1.0


@dataclass(frozen=True)
class Advice:
    runtime: str
    model: str | None
    reason: str
    confidence: str  # "high" | "low" | "default"

    def to_dict(self) -> dict:
        return {
            "runtime": self.runtime,
            "model": self.model,
            "reason": self.reason,
            "confidence": self.confidence,
        }


@dataclass
class _RuntimeScore:
    runtime: str
    runs: int = 0
    completed: int = 0
    autocorrected: int = 0
    cost_sum: float = 0.0
    cost_n: int = 0

    @property
    def success_rate(self) -> float:
        return self.completed / self.runs if self.runs else 0.0

    @property
    def autocorrect_rate(self) -> float:
        return self.autocorrected / self.runs if self.runs else 0.0

    @property
    def avg_cost(self) -> float | None:
        return self.cost_sum / self.cost_n if self.cost_n else None


def _collect_scores(agent_type: str, window_days: int) -> dict[str, _RuntimeScore]:
    from db import session_scope
    from models import AgentExecution
    from harness.capabilities import CAPABILITIES

    since = datetime.utcnow() - timedelta(days=window_days)
    scores: dict[str, _RuntimeScore] = {}
    with session_scope() as session:
        rows = (
            session.query(AgentExecution)
            .filter(AgentExecution.started_at >= since)
            .filter(AgentExecution.agent_type == agent_type)
            .all()
        )
        for ex in rows:
            md = ex.metadata_dict
            runtime = md.get("runtime") or ""
            if runtime not in CAPABILITIES:  # solo runtimes válidos del contrato
                continue
            if ex.status not in ("completed", "needs_review", "error"):
                continue  # solo terminales
            s = scores.setdefault(runtime, _RuntimeScore(runtime=runtime))
            s.runs += 1
            if ex.status == "completed":
                s.completed += 1
            ac = md.get("autocorrect") or {}
            if ac.get("attempts"):
                s.autocorrected += 1
            cost = _extract_cost(md)
            if cost is not None:
                s.cost_sum += cost
                s.cost_n += 1
    return scores


def _extract_cost(md: dict) -> float | None:
    for key in ("claude_telemetry", "harness_telemetry"):
        block = md.get(key) or {}
        c = block.get("total_cost_usd")
        if isinstance(c, (int, float)):
            return float(c)
    return None


def _score_value(s: _RuntimeScore, max_cost: float | None) -> float:
    cost_norm = 0.0
    if max_cost and s.avg_cost is not None:
        cost_norm = s.avg_cost / max_cost
    return (
        _W_SUCCESS * s.success_rate
        - _W_AUTOCORRECT * s.autocorrect_rate
        - _W_COST * cost_norm
    )


def advise(
    *,
    agent_type: str,
    project: str | None = None,
    context_blocks: list[dict] | None = None,
    window_days: int = 14,
) -> Advice:
    """Recomienda runtime+modelo para `agent_type`. Determinista, sin LLM."""
    scores = _collect_scores(agent_type, window_days)
    scorable = {rt: s for rt, s in scores.items() if s.runs >= _MIN_RUNS_TO_SCORE}

    if not scorable:
        return Advice(
            runtime=_DEFAULT_RUNTIME,
            model=_recommend_model(agent_type, context_blocks, project),
            reason="sin historial suficiente (< 5 runs por runtime); se usa el default",
            confidence="default",
        )

    costs = [s.avg_cost for s in scorable.values() if s.avg_cost is not None]
    max_cost = max(costs) if costs else None
    ranked = sorted(
        scorable.values(), key=lambda s: _score_value(s, max_cost), reverse=True
    )
    best = ranked[0]
    success_pct = round(best.success_rate * 100)
    reason = (
        f"{best.runtime}: {success_pct}% éxito sobre {best.runs} runs de "
        f"'{agent_type}' (autocorrección {round(best.autocorrect_rate * 100)}%)"
    )
    # confidence: high si hay separación clara o un solo candidato dominante
    confidence = "high"
    if len(ranked) > 1:
        gap = _score_value(best, max_cost) - _score_value(ranked[1], max_cost)
        if gap < 0.2:
            confidence = "low"
            reason += " (ventaja ajustada vs alternativas)"

    return Advice(
        runtime=best.runtime,
        model=_recommend_model(agent_type, context_blocks, project),
        reason=reason,
        confidence=confidence,
    )


def _recommend_model(
    agent_type: str, context_blocks: list[dict] | None, project: str | None
) -> str | None:
    """Delega en llm_router.decide (el clamp duro aplica solo). None si falla."""
    from services import llm_router

    try:
        decision = llm_router.decide(
            agent_type=agent_type,
            blocks=context_blocks or [],
            project_name=project,
        )
        return llm_router.clamp_model(decision.model)
    except Exception:  # noqa: BLE001 — el advisor nunca rompe el flujo
        logger.debug("run_advisor: decide() falló, modelo None", exc_info=True)
        return None
