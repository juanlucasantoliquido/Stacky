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
    from services.project_context import (
        build_ado_client,
        ruteo_estricto_por_tracker,
        tracker_is_azure_devops,
    )

    # Plan 281 F7 sitio 6 — esta función NO tiene `except` (C5): hoy propaga la
    # AdoConfigError a `review_artifact`, que la llama FUERA de su `try`. Con un
    # tracker no-ADO el cambio es de EXCEPCIÓN PROPAGADA a no-op declarado: ""
    # hace que `review_artifact` devuelva skipped_reason="no_acceptance_criteria",
    # que es la degradación honesta. El otro caller
    # (`acceptance_contract._get_criteria_text`) ya trata "" como "sin criterios".
    if (
        not tracker_is_azure_devops(getattr(ticket, "stacky_project_name", None))
        and ruteo_estricto_por_tracker()
    ):
        return ""

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
        # Plan 290 F3 — el self-review se saltea y devuelve score=1.0, o sea
        # "perfecto", sobre un artefacto que NADIE revisó. Que quede dicho, no
        # solo devuelto. NO cambia el retorno: sigue score=1.0 + skipped_reason.
        #
        # La declaración va acá y no en `_resolve_criteria`: esa función no tiene
        # `execution_id` y la llaman otros caminos; instrumentarla exigiría
        # cambiarle la firma. Acá el dato está a tres líneas.
        #
        # El guard se REPITE a propósito: `criteria_text` puede venir vacío por dos
        # motivos distintos — el tracker no tiene el campo (degradación, sitio 6) o
        # el ticket ADO no tiene criterios cargados (ticket incompleto, que NO es
        # una degradación de capacidad). Sin el guard se declararían falsos
        # positivos sobre proyectos ADO y el KPI se inflaría con ruido.
        # El `try` NO es decorativo y NO es redundante con el de `declarar`:
        # `review_artifact` no está dentro de ningún `try` de su llamador (a
        # diferencia del sitio de F2, que corre dentro del `except` de
        # `business_preflight.evaluate`, :198-200). Acá, cualquier excepción — del
        # propio `declarar`, del resolvedor de tracker, o del import — subiría hasta
        # `apply_to_execution` y tumbaría la corrida por no poder anotar un aviso.
        try:
            from services import capability_degradation
            from services.project_context import (
                ruteo_estricto_por_tracker,
                tracker_efectivo_de_ticket,
                tracker_is_azure_devops,
            )

            if (
                not tracker_is_azure_devops(getattr(ticket, "stacky_project_name", None))
                and ruteo_estricto_por_tracker()
            ):
                capability_degradation.declarar(
                    execution_id=execution_id,
                    capability="tracker.acceptance_criteria",
                    reason=(
                        "el tracker no expone criterios de aceptación "
                        "(Microsoft.VSTS.Common.AcceptanceCriteria es un campo de Azure DevOps): "
                        "el self-review se saltea y NO evaluó el artefacto"
                    ),
                    provider=tracker_efectivo_de_ticket(ticket),
                    site="self_review.review_artifact",
                )
        except Exception:  # noqa: BLE001 — un aviso nunca tumba un self-review
            pass
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
