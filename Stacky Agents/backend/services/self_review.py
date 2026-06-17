from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from config import config
from db import session_scope
from models import AgentExecution, Ticket

logger = logging.getLogger("stacky.self_review")


@dataclass(frozen=True)
class SelfReviewResult:
    score: float
    checklist: list[dict]
    skipped_reason: str | None


def _strip_html(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()


def _extract_json(text: str) -> dict:
    raw = (text or "").strip()
    block = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    if block:
        raw = block.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    obj = re.search(r"\{[\s\S]+\}", raw)
    if not obj:
        raise ValueError("self_review response without JSON object")
    return json.loads(obj.group(0))


def _resolve_criteria(ticket: Ticket) -> str:
    from services.project_context import build_ado_client

    client = build_ado_client(
        project_name=ticket.stacky_project_name,
        tracker_project=ticket.project,
    )
    payload = client._batch_get([int(ticket.ado_id)])
    if not payload:
        return ""
    fields = (payload[0] or {}).get("fields") or {}
    ac = _strip_html(fields.get("Microsoft.VSTS.Common.AcceptanceCriteria"))
    if ac:
        return ac
    return _strip_html(fields.get("System.Description"))


def review_artifact(*, execution_id: int, artifact_text: str) -> SelfReviewResult:
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return SelfReviewResult(score=1.0, checklist=[], skipped_reason="execution_not_found")
        ticket = session.get(Ticket, row.ticket_id)
        if ticket is None:
            return SelfReviewResult(score=1.0, checklist=[], skipped_reason="ticket_not_found")

    criteria_text = _resolve_criteria(ticket)
    if not criteria_text:
        return SelfReviewResult(score=1.0, checklist=[], skipped_reason="no_acceptance_criteria")

    try:
        import copilot_bridge
        from services import llm_router

        decision = llm_router.decide(
            agent_type="qa",
            blocks=[{"content": criteria_text}, {"content": artifact_text[:12000]}],
            project_name=ticket.stacky_project_name,
        )
        system = (
            "Evalua cumplimiento de acceptance criteria. "
            "Devuelve solo JSON: {\"checklist\":[{\"criterion\":str,\"met\":bool,\"evidence\":str}]}"
        )
        user = (
            "CRITERIOS:\n"
            f"{criteria_text}\n\n"
            "ARTEFACTO:\n"
            f"{(artifact_text or '')[:20000]}"
        )

        result = copilot_bridge.invoke(
            agent_type="self_review",
            system=system,
            user=user,
            on_log=lambda _l, _m: None,
            execution_id=None,
            model=decision.model,
            project_name=ticket.stacky_project_name,
        )
        payload = _extract_json(result.text)
        checklist_raw = payload.get("checklist") or []
        checklist: list[dict] = []
        for item in checklist_raw:
            if not isinstance(item, dict):
                continue
            criterion = str(item.get("criterion") or "").strip()
            if not criterion:
                continue
            checklist.append(
                {
                    "criterion": criterion,
                    "met": bool(item.get("met")),
                    "evidence": str(item.get("evidence") or "").strip(),
                }
            )

        if not checklist:
            return SelfReviewResult(score=1.0, checklist=[], skipped_reason="llm_error")

        met = sum(1 for c in checklist if c.get("met"))
        score = met / max(len(checklist), 1)
        return SelfReviewResult(score=round(score, 4), checklist=checklist, skipped_reason=None)
    except Exception:
        logger.warning("self review LLM failed for execution_id=%s", execution_id, exc_info=True)
        return SelfReviewResult(score=1.0, checklist=[], skipped_reason="llm_error")


def apply_to_execution(*, execution_id: int) -> dict:
    mode = (config.STACKY_SELF_REVIEW_MODE or "off").strip().lower()
    if mode not in {"off", "annotate", "gate"}:
        mode = "off"
    if mode == "off":
        return {"status": "unchanged", "applied": False}

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return {"status": "unchanged", "applied": False}
        if row.status != "completed":
            return {"status": "unchanged", "applied": False}
        artifact_text = row.output or ""

    # Q1.1 — reutilizar caché del criteria_repair runner (cero doble-costo LLM).
    try:
        from harness.criteria_repair import get_cached_review
        _cached = get_cached_review(execution_id)
    except Exception:  # noqa: BLE001
        _cached = None

    result = _cached if _cached is not None else review_artifact(
        execution_id=execution_id, artifact_text=artifact_text
    )

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        if row is None:
            return {"status": "unchanged", "applied": False}

        metadata = row.metadata_dict
        checklist = result.checklist
        met_count = sum(1 for c in checklist if c.get("met"))
        metadata["self_review"] = {
            "score": result.score,
            "checklist": checklist,
            "met": met_count,
            "total": len(checklist),
            "skipped_reason": result.skipped_reason,
            "mode": mode,
        }

        if mode == "gate" and result.skipped_reason is None and result.score < float(config.STACKY_SELF_REVIEW_MIN_SCORE):
            row.status = "needs_review"
            row.error_message = row.error_message or "Self-review score under threshold"
            metadata["failure_kind"] = metadata.get("failure_kind") or "self_review_gate"
            row.metadata_dict = metadata
            return {"status": "needs_review", "applied": True}

        row.metadata_dict = metadata
        return {"status": "completed", "applied": True}
