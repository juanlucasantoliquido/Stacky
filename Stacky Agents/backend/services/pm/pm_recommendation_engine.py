"""Recommendation Engine para PM Intelligence Suite — Fase 2 (advisory).

Toma el último snapshot del sprint + riesgos detectados + histórico, llama al
LLM y genera recomendaciones accionables NO punitivas.

Gates:
- Solo opera si el eval del componente "recommendation_engine" pasa.
- `advisory_only` y `publish_recommended=False` son inmutables — el engine
  rechaza outputs que intenten cambiarlos.

NO publica nada a ADO. Persiste las recomendaciones en pm_ai_recommendations
para que el operador las revise + acknowledge manualmente.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from services.pm.pm_evals import is_advisory_enabled
from services.pm.pm_llm_client import LLMCallSpec, call_llm
from services.pm.pm_prompts import RECOMMENDATION_SYSTEM_V1, build_recommendation_user

logger = logging.getLogger("stacky_agents.pm.recommendation_engine")

_VALID_PRIORITIES = {"P0", "P1", "P2"}
_VALID_CATEGORIES = {"SCOPE", "RESOURCE", "PROCESS", "RISK_MITIGATION"}
_PUNITIVE_TERMS = ["despedir", "echar", "incompetente", "lento", "vago"]


@dataclass
class RecommendationRunResult:
    project: str
    sprint_id: str | None
    gate_passed: bool
    generated: int
    rejected: int
    rejected_reasons: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    model: str = ""
    advisory_only: bool = True

    def to_dict(self) -> dict:
        return {
            "project": self.project,
            "sprint_id": self.sprint_id,
            "gate_passed": self.gate_passed,
            "generated": self.generated,
            "rejected": self.rejected,
            "rejected_reasons": self.rejected_reasons,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": round(self.cost_usd, 6),
            "model": self.model,
            "advisory_only": self.advisory_only,
        }


def _stable_rec_id(project: str, sprint_id: str | None, action: str, idx: int) -> str:
    payload = f"{project}|{sprint_id or 'no-sprint'}|{idx}|{action}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"REC-{digest}"


def _build_input_payload(*, snapshot: dict, risks: list[dict], history: list[dict]) -> dict:
    """Arma el payload que el prompt consume — formato declarado en el contrato."""
    kpis = (snapshot or {}).get("kpis") or {}
    sprint_summary = {
        "velocity_current": kpis.get("completed_story_points") or kpis.get("done_items") or 0,
        "velocity_avg": _avg_velocity(history),
        "completion_rate_pct": kpis.get("completion_rate_pct") or 0,
        "days_remaining": kpis.get("days_remaining"),
        "blocked_items_count": kpis.get("blocked_items") or 0,
    }
    return {
        "rec_input_version": "1.0",
        "sprint_summary": sprint_summary,
        "risk_feed": [
            {
                "risk_id": r.get("risk_id"),
                "category": r.get("category"),
                "severity": r.get("severity"),
                "rule": r.get("rule"),
                "description": r.get("description"),
            }
            for r in (risks or [])
        ],
        "historical_sprints": history or [],
    }


def _avg_velocity(history: list[dict]) -> float:
    vs = [h.get("velocity") for h in history or [] if isinstance(h.get("velocity"), (int, float))]
    return round(sum(vs) / len(vs), 2) if vs else 0.0


def _validate_recommendation_item(item: Any) -> tuple[bool, str | None]:
    """Devuelve (ok, reason). Rechaza items que violan reglas no negociables."""
    if not isinstance(item, dict):
        return False, "not_dict"
    priority = item.get("priority")
    if priority not in _VALID_PRIORITIES:
        return False, f"invalid_priority_{priority}"
    category = item.get("category")
    if category not in _VALID_CATEGORIES:
        return False, f"invalid_category_{category}"
    action = (item.get("action") or "").strip()
    if not action:
        return False, "empty_action"
    if len(action) > 200:
        return False, "action_too_long"
    # publish_recommended siempre debe ser false
    if item.get("publish_recommended") is True:
        return False, "publish_recommended_must_be_false"
    # Lenguaje punitivo
    full_text = (
        action.lower()
        + " "
        + (item.get("rationale") or "").lower()
    )
    for kw in _PUNITIVE_TERMS:
        if kw in full_text:
            return False, f"punitive_keyword_{kw}"
    return True, None


def generate_recommendations(
    *,
    project: str,
    snapshot: dict | None = None,
    risks: list[dict] | None = None,
    history: list[dict] | None = None,
    model: str = "claude-sonnet-4-6",
    force_unsafe: bool = False,
    skip_gate_check: bool = False,
) -> RecommendationRunResult:
    """Genera recomendaciones advisory para el sprint dado.

    Args:
        project: proyecto al que pertenecen las recomendaciones.
        snapshot: payload del snapshot (con `kpis` adentro). Si falta, se intenta
                  cargar el último de pm_sprint_snapshots.
        risks: lista de riesgos vigentes (no acknowledged).
        history: lista de sprints históricos {name, velocity, completion_rate_pct}.
        model: modelo LLM. Default sonnet por requerir más razonamiento.
        force_unsafe: bypassa el gate si True.
        skip_gate_check: skip de la corrida de evals si True.
    """
    from db import session_scope
    from services.pm.models import PmAiRecommendation, PmRiskItem, PmSprintSnapshot

    # 1. Gate check
    gate_passed = True
    if not skip_gate_check and not force_unsafe:
        try:
            gate_passed = is_advisory_enabled("recommendation_engine", model=model)
        except Exception as e:  # noqa: BLE001
            logger.warning("recommendation_engine: gate check falló (%s) — bloqueando", e)
            gate_passed = False
        if not gate_passed:
            return RecommendationRunResult(
                project=project, sprint_id=None, gate_passed=False,
                generated=0, rejected=0, rejected_reasons=["eval_gate_blocked"],
                model=model,
            )

    # 2. Cargar snapshot y riesgos si no vinieron
    if snapshot is None or risks is None:
        with session_scope() as session:
            if snapshot is None:
                row = (
                    session.query(PmSprintSnapshot)
                    .filter(PmSprintSnapshot.project == project)
                    .order_by(PmSprintSnapshot.captured_at.desc())
                    .first()
                )
                snapshot = row.snapshot if row else {}
            if risks is None:
                sprint_id_filter = (snapshot or {}).get("iteration", {}).get("id")
                q = session.query(PmRiskItem).filter(PmRiskItem.project == project)
                if sprint_id_filter:
                    q = q.filter(PmRiskItem.sprint_id == str(sprint_id_filter))
                q = q.filter(PmRiskItem.acknowledged.is_(False))
                risks = [r.to_dict() for r in q.all()]

    history = history or []
    sprint_id = ((snapshot or {}).get("iteration") or {}).get("id")

    # 3. Llamar LLM con tracking
    input_payload = _build_input_payload(snapshot=snapshot or {}, risks=risks or [], history=history)
    spec = LLMCallSpec(
        project=project,
        agent_kind="recommendation",
        prompt_type="rec_engine_v1",
        model=model,
        system=RECOMMENDATION_SYSTEM_V1,
        user=build_recommendation_user(input_payload),
        max_output_tokens=1500,
        temperature=0.0,
        expect_json=True,
    )
    result = call_llm(spec)

    if not result.success or not isinstance(result.parsed_json, dict):
        return RecommendationRunResult(
            project=project, sprint_id=sprint_id, gate_passed=gate_passed,
            generated=0, rejected=0,
            rejected_reasons=[f"llm_call_failed: {result.error}" if result.error else "llm_call_failed"],
            tokens_in=result.tokens_in, tokens_out=result.tokens_out,
            cost_usd=result.cost_usd, model=result.model,
        )

    output = result.parsed_json
    if output.get("advisory_only") is not True:
        return RecommendationRunResult(
            project=project, sprint_id=sprint_id, gate_passed=gate_passed,
            generated=0, rejected=0,
            rejected_reasons=["output_advisory_only_not_true"],
            tokens_in=result.tokens_in, tokens_out=result.tokens_out,
            cost_usd=result.cost_usd, model=result.model,
        )

    items = output.get("recommendations") or []
    generated = 0
    rejected = 0
    rejected_reasons: list[str] = []

    with session_scope() as session:
        for idx, item in enumerate(items):
            ok, reason = _validate_recommendation_item(item)
            if not ok:
                rejected += 1
                if reason:
                    rejected_reasons.append(reason)
                continue
            action = str(item.get("action") or "").strip()
            rec_id = _stable_rec_id(project, str(sprint_id) if sprint_id else None, action, idx)

            existing = (
                session.query(PmAiRecommendation)
                .filter(PmAiRecommendation.rec_id == rec_id)
                .one_or_none()
            )
            if existing is not None:
                # Re-generación del mismo sprint: actualizar rationale/confidence pero
                # mantener acknowledge.
                existing.rationale = item.get("rationale")
                existing.supporting_data = item.get("supporting_data") or {}
                try:
                    existing.confidence = float(item.get("confidence") or 0)
                except (TypeError, ValueError):
                    existing.confidence = 0.0
                existing.model = result.model
                existing.usage_id = result.usage_id
                generated += 1
                continue

            try:
                confidence = float(item.get("confidence") or 0)
            except (TypeError, ValueError):
                confidence = 0.0

            row = PmAiRecommendation(
                rec_id=rec_id,
                project=project,
                sprint_id=str(sprint_id) if sprint_id else None,
                priority=item["priority"],
                category=item["category"],
                action=action[:200],
                rationale=item.get("rationale"),
                confidence=max(0.0, min(1.0, confidence)),
                advisory_only=True,
                publish_recommended=False,
                human_approval_required=True,
                model=result.model,
                usage_id=result.usage_id,
            )
            row.supporting_data = item.get("supporting_data") or {}
            session.add(row)
            generated += 1

    return RecommendationRunResult(
        project=project,
        sprint_id=str(sprint_id) if sprint_id else None,
        gate_passed=gate_passed,
        generated=generated,
        rejected=rejected,
        rejected_reasons=rejected_reasons,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        cost_usd=result.cost_usd,
        model=result.model,
    )


def acknowledge_recommendation(rec_id: str, actor: str) -> dict | None:
    """Marca una recomendación como reconocida por un operador."""
    from db import session_scope
    from services.pm.models import PmAiRecommendation

    with session_scope() as session:
        row = (
            session.query(PmAiRecommendation)
            .filter(PmAiRecommendation.rec_id == rec_id)
            .one_or_none()
        )
        if row is None:
            return None
        if row.acknowledged:
            return row.to_dict()
        row.acknowledged = True
        row.acknowledged_by = actor[:200]
        row.acknowledged_at = datetime.utcnow()
        return row.to_dict()
