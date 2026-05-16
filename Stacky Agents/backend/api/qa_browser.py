"""Guarded Codex Browser QA UAT endpoints."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from flask import Blueprint, abort, jsonify, request

import log_streamer
from config import config
from db import session_scope
from models import AgentExecution, Ticket
from services import qa_browser_runner, ticket_status
from services.qa_browser_context import build_qa_browser_context, render_context_markdown
from services.qa_browser_plan import (
    BrowserRunInput,
    build_ado_comment_html,
    build_codex_browser_prompt,
    build_guarded_browser_spec,
    dumps_spec,
)
from ._helpers import current_user

logger = logging.getLogger("stacky_agents.api.qa_browser")

bp = Blueprint("qa_browser", __name__, url_prefix="/qa-browser")

_AGENT_TYPE = "qa-browser"


@bp.post("/runs")
def create_run():
    """Create a guarded QA UAT browser run spec for Codex Browser."""
    payload = request.get_json(force=True, silent=True) or {}
    ticket_id = _positive_int(payload.get("ticket_id"), "ticket_id")
    operator_note = (payload.get("operator_note") or "").strip() or None
    allowed_base_url = (
        payload.get("allowed_base_url")
        or getattr(config, "QA_BROWSER_DEFAULT_BASE_URL", "")
        or "http://localhost:35017/AgendaWeb/"
    ).strip()
    if not allowed_base_url.startswith(("http://", "https://")):
        abort(400, "allowed_base_url must start with http:// or https://")
    max_scenarios = int(payload.get("max_scenarios") or 16)
    if max_scenarios < 1 or max_scenarios > 30:
        abort(400, "max_scenarios must be between 1 and 30")
    auto_start = _bool(payload.get("auto_start"), default=True)
    model_override = (payload.get("model_override") or "").strip() or None

    user = current_user()
    stacky_api_base_url = _stacky_api_base_url()

    with session_scope() as session:
        ticket = _resolve_ticket(session, ticket_id)
        if ticket is None:
            abort(404, f"Ticket {ticket_id} not found")

        context = build_qa_browser_context(session, ticket)
        spec = build_guarded_browser_spec(
            BrowserRunInput(
                ticket_id=ticket.id,
                ticket_ado_id=ticket.ado_id,
                ticket_title=ticket.title,
                ticket_state=ticket.ado_state,
                ticket_url=ticket.ado_url,
                allowed_base_url=allowed_base_url,
                context=context,
                operator_note=operator_note,
                max_scenarios=max_scenarios,
            )
        )
        context_markdown = render_context_markdown(context)

        exec_row = AgentExecution(
            ticket_id=ticket.id,
            agent_type=_AGENT_TYPE,
            status="queued",
            started_by=user,
            started_at=datetime.utcnow(),
        )
        exec_row.input_context = [
            {
                "id": "qa_browser_ticket_context",
                "kind": "readonly",
                "title": "Contexto completo ADO para QA UAT Codex",
                "content": context_markdown,
            },
            {
                "id": "qa_browser_run_spec",
                "kind": "readonly",
                "title": "Contrato de ejecucion QA Browser",
                "content": dumps_spec(spec),
            },
        ]
        exec_row.output = spec["markdown"]
        exec_row.output_format = "markdown"
        exec_row.metadata_dict = {
            "feature": "qa_browser_uat_codex",
            "runtime": "codex_browser",
            "allowed_base_url": allowed_base_url,
            "publish_ado_comment": "always_on_complete",
            "context_stats": context.get("stats"),
            "spec": spec,
            "events": [],
            "evidence": [],
        }
        session.add(exec_row)
        session.flush()
        execution_id = exec_row.id
        spec["execution_id"] = execution_id
        spec["stacky_api_base_url"] = stacky_api_base_url
        spec["codex_browser_prompt"] = build_codex_browser_prompt(spec)
        exec_row.input_context = [
            exec_row.input_context[0],
            {
                "id": "qa_browser_run_spec",
                "kind": "readonly",
                "title": "Contrato de ejecucion QA Browser",
                "content": dumps_spec(spec),
            },
        ]
        md = exec_row.metadata_dict
        md["spec"] = spec
        md["runner"] = {
            "auto_start": auto_start,
            "runtime": qa_browser_runner.RUNTIME if auto_start else "manual_handoff",
            "model_override": model_override,
        }
        exec_row.metadata_dict = md
        resolved_ticket_id = ticket.id
        ticket_project = ticket.project

    log_streamer.open(execution_id)
    log_streamer.push(execution_id, "info", "TEST QA UAT CODEX preparado")
    log_streamer.push(execution_id, "info", f"ticket_id={resolved_ticket_id} allowed_base_url={allowed_base_url}")
    log_streamer.push(execution_id, "info", f"contexto: {spec['context_stats']}")
    log_streamer.push(execution_id, "info", f"escenarios detectados={len(spec['scenarios'])}")
    response_status = "queued"
    if auto_start:
        workspace_root = _resolve_workspace_root_for_ticket(ticket_project)
        with session_scope() as session:
            row = _get_qa_run(session, execution_id)
            row.status = "running"
            md = row.metadata_dict
            runner = dict(md.get("runner") or {})
            runner["workspace_root"] = workspace_root
            runner["started_at"] = datetime.utcnow().isoformat() + "Z"
            md["runner"] = runner
            row.metadata_dict = md
        ticket_status.on_execution_start(
            ticket_id=resolved_ticket_id,
            execution_id=execution_id,
            agent_type=_AGENT_TYPE,
            user=user,
        )
        log_streamer.push(
            execution_id,
            "info",
            "Codex automatico iniciado: Stacky ejecutara el prompt y esperara eventos/complete",
            group="codex-browser",
        )
        qa_browser_runner.start_run(
            execution_id=execution_id,
            prompt=spec["codex_browser_prompt"],
            workspace_root=workspace_root,
            model_override=model_override,
        )
        response_status = "running"
    else:
        log_streamer.push(
            execution_id,
            "warn",
            "run preparado en modo manual: falta ejecutar el prompt en Codex Browser; el ticket aun no se marca como running",
        )

    return jsonify(
        {
            "ok": True,
            "execution_id": execution_id,
            "ticket_id": resolved_ticket_id,
            "ado_id": spec["ticket"]["ado_id"],
            "spec": spec,
            "runner_prompt": spec["codex_browser_prompt"],
            "stream_url": f"/api/executions/{execution_id}/logs/stream",
            "status": response_status,
        }
    ), 202


@bp.get("/runs/<int:execution_id>/spec")
def get_run_spec(execution_id: int):
    with session_scope() as session:
        row = _get_qa_run(session, execution_id)
        spec = row.metadata_dict.get("spec")
        if not spec:
            abort(404, "qa browser spec not found")
        return jsonify({"ok": True, "execution_id": execution_id, "spec": spec})


@bp.post("/runs/<int:execution_id>/events")
def push_event(execution_id: int):
    payload = request.get_json(force=True, silent=True) or {}
    event_type = (payload.get("type") or "event").strip()
    scenario_id = payload.get("scenario_id")
    step_id = payload.get("step_id")
    level = (payload.get("level") or "info").strip().lower()
    if level not in {"debug", "info", "warn", "error"}:
        level = "info"
    message = (payload.get("message") or "").strip() or event_type
    event = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "type": event_type,
        "level": level,
        "scenario_id": scenario_id,
        "step_id": step_id,
        "message": message,
        "data": payload.get("data") or {},
    }
    activated_ticket_id: int | None = None
    with session_scope() as session:
        row = _get_qa_run(session, execution_id)
        if row.status == "queued":
            row.status = "running"
            activated_ticket_id = row.ticket_id
        md = row.metadata_dict
        events = list(md.get("events") or [])
        events.append(event)
        md["events"] = events[-500:]
        row.metadata_dict = md

    if activated_ticket_id is not None:
        ticket_status.on_execution_start(
            ticket_id=activated_ticket_id,
            execution_id=execution_id,
            agent_type=_AGENT_TYPE,
            user=current_user(),
        )
        log_streamer.push(execution_id, "info", "Codex Browser activo: ejecucion iniciada", group="codex-browser")

    log_message = message
    if scenario_id:
        log_message = f"{scenario_id}{'/' + step_id if step_id else ''}: {message}"
    log_streamer.push(execution_id, level, log_message, group="codex-browser")
    return jsonify({"ok": True, "event": event})


@bp.post("/runs/<int:execution_id>/evidence")
def add_evidence(execution_id: int):
    payload = request.get_json(force=True, silent=True) or {}
    evidence = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "scenario_id": payload.get("scenario_id"),
        "step_id": payload.get("step_id"),
        "kind": payload.get("kind") or "note",
        "label": payload.get("label") or "",
        "value": payload.get("value") or "",
    }
    with session_scope() as session:
        row = _get_qa_run(session, execution_id)
        md = row.metadata_dict
        items = list(md.get("evidence") or [])
        items.append(evidence)
        md["evidence"] = items[-500:]
        row.metadata_dict = md
    log_streamer.push(
        execution_id,
        "info",
        f"evidence {evidence['kind']} {evidence.get('scenario_id') or ''}".strip(),
        group="codex-browser",
    )
    return jsonify({"ok": True, "evidence": evidence})


@bp.post("/runs/<int:execution_id>/complete")
def complete_run(execution_id: int):
    """Close the run and always try to publish a detailed ADO comment."""
    payload = request.get_json(force=True, silent=True) or {}
    result = _normalize_result(payload)

    with session_scope() as session:
        row = _get_qa_run(session, execution_id)
        ticket = session.get(Ticket, row.ticket_id)
        if ticket is None:
            abort(404, "ticket not found")
        md = row.metadata_dict
        spec = md.get("spec")
        if not spec:
            abort(404, "qa browser spec not found")
        result.setdefault("evidence", md.get("evidence") or [])
        ado_id = ticket.ado_id

    publish_error: str | None = None
    publish_result: dict[str, Any] | None = None
    comment_html = build_ado_comment_html(
        execution_id=execution_id,
        spec=spec,
        result=result,
    )
    try:
        from services.ado_client import AdoClient

        publish_result = AdoClient().post_comment(ado_id, comment_html, fmt="html")
    except Exception as exc:  # noqa: BLE001
        publish_error = str(exc)
        logger.exception("qa_browser complete: ADO comment publish failed")

    final_status = "completed" if publish_error is None else "error"
    if publish_error:
        comment_html = build_ado_comment_html(
            execution_id=execution_id,
            spec=spec,
            result=result,
            publish_error=publish_error,
        )

    output = _render_result_markdown(
        execution_id=execution_id,
        spec=spec,
        result=result,
        publish_error=publish_error,
        publish_result=publish_result,
    )

    with session_scope() as session:
        row = _get_qa_run(session, execution_id)
        md = row.metadata_dict
        md["result"] = result
        md["ado_comment"] = {
            "attempted": True,
            "ok": publish_error is None,
            "error": publish_error,
            "response": publish_result,
            "html": comment_html,
        }
        row.metadata_dict = md
        row.output = output
        row.output_format = "markdown"
        row.status = final_status
        row.error_message = publish_error
        row.completed_at = datetime.utcnow()
        ticket_id = row.ticket_id

    log_streamer.push(execution_id, "info", f"veredicto final={result['verdict']}", group="codex-browser")
    if publish_error:
        log_streamer.push(execution_id, "error", f"ADO comment failed: {publish_error}", group="ado")
    else:
        log_streamer.push(execution_id, "info", "comentario ADO publicado", group="ado")
    log_streamer.close(execution_id)
    ticket_status.on_execution_end(
        ticket_id=ticket_id,
        execution_id=execution_id,
        final_status=final_status,
        agent_type=_AGENT_TYPE,
        error=publish_error,
    )

    return jsonify(
        {
            "ok": publish_error is None,
            "execution_id": execution_id,
            "status": final_status,
            "result": result,
            "ado_comment": {
                "ok": publish_error is None,
                "error": publish_error,
                "response": publish_result,
            },
        }
    ), 200 if publish_error is None else 502


def _resolve_ticket(session: Any, ticket_id: int) -> Ticket | None:
    return (
        session.query(Ticket).filter(Ticket.id == ticket_id).first()
        or session.query(Ticket).filter(Ticket.ado_id == ticket_id).first()
    )


def _get_qa_run(session: Any, execution_id: int) -> AgentExecution:
    row = session.get(AgentExecution, execution_id)
    if row is None or row.agent_type != _AGENT_TYPE:
        abort(404, f"QA Browser execution {execution_id} not found")
    return row


def _positive_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or value < 1:
        abort(400, f"{field} must be a positive integer")
    return value


def _bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def _stacky_api_base_url() -> str:
    root = (request.host_url or "").rstrip("/")
    if root:
        return root
    return f"http://127.0.0.1:{config.PORT}"


def _resolve_workspace_root_for_ticket(ticket_project: str | None) -> str:
    try:
        from project_manager import (
            find_project_for_tracker,
            get_active_project,
            get_project_config,
        )

        if ticket_project:
            _, cfg = find_project_for_tracker(ticket_project)
            if cfg.get("workspace_root"):
                return cfg["workspace_root"]

        active = get_active_project()
        if active:
            cfg = get_project_config(active) or {}
            if cfg.get("workspace_root"):
                return cfg["workspace_root"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("qa_browser: no se pudo resolver workspace_root: %s", exc)

    from pathlib import Path

    return str(Path(__file__).resolve().parents[2])


def _normalize_result(payload: dict[str, Any]) -> dict[str, Any]:
    verdict = str(payload.get("verdict") or "BLOCKED").upper()
    if verdict not in {"PASS", "FAIL", "BLOCKED", "MIXED"}:
        verdict = "BLOCKED"
    scenarios = payload.get("scenarios") if isinstance(payload.get("scenarios"), list) else []
    normalized_scenarios: list[dict[str, Any]] = []
    for item in scenarios:
        if not isinstance(item, dict):
            continue
        item_verdict = str(item.get("verdict") or "BLOCKED").upper()
        if item_verdict not in {"PASS", "FAIL", "BLOCKED"}:
            item_verdict = "BLOCKED"
        normalized_scenarios.append(
            {
                "scenario_id": item.get("scenario_id") or item.get("id") or "-",
                "verdict": item_verdict,
                "steps_executed": item.get("steps_executed") or [],
                "expected": item.get("expected") or "",
                "actual": item.get("actual") or "",
                "evidence": item.get("evidence") or [],
            }
        )
    return {
        "verdict": verdict,
        "summary": payload.get("summary") or "Run finalizado por Codex Browser.",
        "scenarios": normalized_scenarios,
        "raw": payload,
        "completed_at": datetime.utcnow().isoformat() + "Z",
    }


def _render_result_markdown(
    *,
    execution_id: int,
    spec: dict[str, Any],
    result: dict[str, Any],
    publish_error: str | None,
    publish_result: dict[str, Any] | None,
) -> str:
    lines = [
        "# QA UAT Codex Browser - Resultado",
        "",
        f"Run: `{execution_id}`",
        f"Ticket: ADO-{spec['ticket'].get('ado_id')}",
        f"Veredicto: `{result['verdict']}`",
        f"Resumen: {result.get('summary')}",
        "",
        "## Publicacion ADO",
        "",
        "Estado: " + ("OK" if publish_error is None else f"ERROR - {publish_error}"),
    ]
    if publish_result:
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(publish_result, ensure_ascii=False, indent=2)[:3000])
        lines.append("```")
    lines.extend(["", "## Escenarios", ""])
    for item in result.get("scenarios") or []:
        lines.append(f"### {item.get('scenario_id')} - {item.get('verdict')}")
        if item.get("expected"):
            lines.append(f"Esperado: {item.get('expected')}")
        if item.get("actual"):
            lines.append(f"Actual: {item.get('actual')}")
        for evidence in item.get("evidence") or []:
            lines.append(f"- Evidencia: {evidence}")
        lines.append("")
    return "\n".join(lines)
