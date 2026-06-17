from __future__ import annotations

from datetime import datetime
from typing import Any

import agent_runner
from config import config
from db import session_scope
from models import AgentExecution, PipelineRun, Ticket

_STAGE_ORDER = ["business", "functional", "technical", "developer", "qa"]


def _assert_enabled() -> None:
    if not bool(getattr(config, "STACKY_PIPELINES_ENABLED", False)):
        raise RuntimeError("pipelines_disabled")


def _now() -> datetime:
    return datetime.utcnow()


def _launch_stage(*, pipeline_id: int, stage_index: int, runtime: str = "github_copilot") -> int:
    ticket_title = ""
    ticket_description = ""
    ticket_ado_id = 0
    ticket_id_value = 0
    project_name: str | None = None
    with session_scope() as session:
        run = session.get(PipelineRun, pipeline_id)
        if run is None:
            raise RuntimeError("pipeline_not_found")
        ticket = session.get(Ticket, run.ticket_id)
        if ticket is None:
            raise RuntimeError("ticket_not_found")
        stages = run.stages
        if stage_index < 0 or stage_index >= len(stages):
            raise RuntimeError("stage_out_of_range")
        stage = stages[stage_index]
        run.current_stage = stage_index
        run.updated_at = _now()
        project_name = ticket.stacky_project_name
        ticket_title = ticket.title
        ticket_description = ticket.description or ""
        ticket_ado_id = int(ticket.ado_id)
        ticket_id_value = int(ticket.id)

    context_blocks = [
        {
            "type": "ticket_context",
            "ticket_id": ticket_id_value,
            "ado_id": ticket_ado_id,
            "title": ticket_title,
            "description": ticket_description,
        }
    ]

    execution_id = agent_runner.run_agent(
        agent_type=stage,
        ticket_id=ticket_id_value,
        context_blocks=context_blocks,
        chain_from=[],
        user="pipeline_orchestrator",
        runtime=runtime,
        project_name=project_name,
    )

    with session_scope() as session:
        run = session.get(PipelineRun, pipeline_id)
        if run is None:
            return execution_id
        run.last_execution_id = execution_id
        run.updated_at = _now()

        exec_row = session.get(AgentExecution, execution_id)
        if exec_row is not None:
            md = dict(exec_row.metadata_dict or {})
            md["pipeline_run_id"] = pipeline_id
            md["pipeline_stage"] = stage
            md["pipeline_stage_index"] = stage_index
            exec_row.metadata_dict = md

    return execution_id


def start(*, ticket_id: int, stages: list[str] | None = None, runtime: str = "github_copilot") -> dict[str, Any]:
    _assert_enabled()
    normalized = [s for s in (stages or _STAGE_ORDER) if s in _STAGE_ORDER]
    if not normalized:
        raise ValueError("invalid_stages")

    with session_scope() as session:
        ticket = session.get(Ticket, ticket_id)
        if ticket is None:
            raise ValueError("ticket_not_found")
        active = (
            session.query(PipelineRun)
            .filter(
                PipelineRun.ticket_id == ticket_id,
                PipelineRun.status.in_(["running", "paused"]),
            )
            .first()
        )
        if active is not None:
            raise RuntimeError("pipeline_already_active")

        run = PipelineRun(
            ticket_id=ticket_id,
            project=ticket.stacky_project_name or ticket.project,
            status="running",
            current_stage=0,
            created_at=_now(),
            updated_at=_now(),
        )
        run.stages = normalized
        session.add(run)
        session.flush()
        pipeline_id = run.id

    execution_id = _launch_stage(pipeline_id=pipeline_id, stage_index=0, runtime=runtime)
    with session_scope() as session:
        run = session.get(PipelineRun, pipeline_id)
        return {
            "ok": True,
            "pipeline": run.to_dict() if run else {"id": pipeline_id},
            "launched_execution_id": execution_id,
        }


def get_run(pipeline_id: int) -> dict[str, Any] | None:
    with session_scope() as session:
        run = session.get(PipelineRun, pipeline_id)
        return run.to_dict() if run else None


def cancel(pipeline_id: int) -> dict[str, Any]:
    _assert_enabled()
    with session_scope() as session:
        run = session.get(PipelineRun, pipeline_id)
        if run is None:
            raise ValueError("pipeline_not_found")
        run.status = "cancelled"
        run.updated_at = _now()
        last_execution_id = run.last_execution_id

    if last_execution_id:
        try:
            agent_runner.cancel(last_execution_id)
        except Exception:
            pass

    return {"ok": True, "pipeline": get_run(pipeline_id)}


def resume(pipeline_id: int, runtime: str = "github_copilot") -> dict[str, Any]:
    _assert_enabled()
    with session_scope() as session:
        run = session.get(PipelineRun, pipeline_id)
        if run is None:
            raise ValueError("pipeline_not_found")
        if run.status != "paused":
            raise RuntimeError("pipeline_not_paused")

        next_stage = min(run.current_stage + 1, max(len(run.stages) - 1, 0))
        run.status = "running"
        run.updated_at = _now()

    execution_id = _launch_stage(pipeline_id=pipeline_id, stage_index=next_stage, runtime=runtime)
    return {"ok": True, "pipeline": get_run(pipeline_id), "launched_execution_id": execution_id}


def on_execution_end(*, execution_id: int, final_status: str) -> None:
    with session_scope() as session:
        exec_row = session.get(AgentExecution, execution_id)
        if exec_row is None:
            return
        md = exec_row.metadata_dict or {}
        pipeline_id = md.get("pipeline_run_id")
        stage_index = md.get("pipeline_stage_index")
        if pipeline_id is None:
            return

        run = session.get(PipelineRun, int(pipeline_id))
        if run is None or run.status not in {"running", "paused"}:
            return

        stages = run.stages
        if final_status == "completed":
            if stage_index is None:
                stage_index = run.current_stage
            if int(stage_index) >= len(stages) - 1:
                run.status = "completed"
                run.updated_at = _now()
                return
            run.current_stage = int(stage_index) + 1
            run.updated_at = _now()
            next_stage = run.current_stage
        elif final_status in {"error", "needs_review"}:
            run.status = "paused"
            run.updated_at = _now()
            return
        else:
            run.status = "failed"
            run.updated_at = _now()
            return

    # Lanzar siguiente etapa fuera de la transacción.
    _launch_stage(pipeline_id=int(pipeline_id), stage_index=int(next_stage))


_HOOK_REGISTERED = False


def register_ticket_status_hook() -> None:
    global _HOOK_REGISTERED
    if _HOOK_REGISTERED:
        return

    from services import ticket_status

    def _post_hook(**kwargs: Any) -> None:
        try:
            on_execution_end(
                execution_id=int(kwargs.get("execution_id") or 0),
                final_status=str(kwargs.get("final_status") or ""),
            )
        except Exception:
            return

    ticket_status.register_post_hook(_post_hook)
    _HOOK_REGISTERED = True
