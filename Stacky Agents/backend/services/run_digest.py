from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta

from db import session_scope
from models import AgentExecution, Ticket


def compose_digest(days: int = 7, project: str | None = None) -> dict:
    now = datetime.utcnow()
    start = now - timedelta(days=max(days, 1))

    with session_scope() as session:
        q = session.query(AgentExecution, Ticket).join(Ticket, Ticket.id == AgentExecution.ticket_id)
        q = q.filter(AgentExecution.started_at >= start)
        if project:
            q = q.filter(Ticket.stacky_project_name == project)
        rows = q.all()

    if not rows:
        return {
            "period": {"days": days, "start": start.isoformat() + "Z", "end": now.isoformat() + "Z"},
            "totals": {
                "runs": 0,
                "completed": 0,
                "needs_review": 0,
                "error": 0,
                "success_rate": 0.0,
                "tickets_touched": 0,
                "cost_usd": {"reported": 0.0, "estimated": 0.0, "total": 0.0},
            },
            "by_agent_type": [],
            "by_runtime": [],
            "top_failures": [],
            "highlights": ["sin actividad en el período"],
            "partial": False,
        }

    totals = Counter()
    by_agent = defaultdict(lambda: Counter())
    by_runtime = defaultdict(lambda: Counter())
    failures = Counter()
    tickets_touched = set()
    reported_cost = 0.0
    estimated_cost = 0.0
    partial = False

    for exec_row, ticket in rows:
        totals["runs"] += 1
        totals[str(exec_row.status)] += 1
        tickets_touched.add(ticket.ado_id)

        md = exec_row.metadata_dict or {}
        runtime = str(md.get("runtime") or "unknown")
        by_agent[exec_row.agent_type]["runs"] += 1
        by_agent[exec_row.agent_type][str(exec_row.status)] += 1
        by_runtime[runtime]["runs"] += 1
        by_runtime[runtime][str(exec_row.status)] += 1

        telemetry = md.get("claude_telemetry") if isinstance(md.get("claude_telemetry"), dict) else {}
        cost = telemetry.get("total_cost_usd") if isinstance(telemetry, dict) else None
        if cost is not None:
            try:
                reported_cost += float(cost)
            except Exception:
                partial = True
        elif md.get("cost_estimated") is not None:
            try:
                estimated_cost += float(md.get("cost_estimated"))
                partial = True
            except Exception:
                partial = True

        if exec_row.status in {"error", "needs_review"}:
            kind = str(md.get("failure_kind") or (exec_row.error_message or "error")).strip()
            failures[kind[:80]] += 1

    completed = int(totals.get("completed", 0))
    success_rate = completed / max(int(totals["runs"]), 1)

    def _serialize_group(group_data: dict[str, Counter]) -> list[dict]:
        out: list[dict] = []
        for name, stats in sorted(group_data.items(), key=lambda kv: kv[0]):
            runs = int(stats.get("runs", 0))
            out.append(
                {
                    "name": name,
                    "runs": runs,
                    "completed": int(stats.get("completed", 0)),
                    "needs_review": int(stats.get("needs_review", 0)),
                    "error": int(stats.get("error", 0)),
                    "success_rate": round(int(stats.get("completed", 0)) / max(runs, 1), 4),
                }
            )
        return out

    best_agent = max(_serialize_group(by_agent), key=lambda x: (x["success_rate"], x["runs"]))
    most_used_runtime = max(_serialize_group(by_runtime), key=lambda x: x["runs"])

    return {
        "period": {"days": days, "start": start.isoformat() + "Z", "end": now.isoformat() + "Z"},
        "totals": {
            "runs": int(totals["runs"]),
            "completed": completed,
            "needs_review": int(totals.get("needs_review", 0)),
            "error": int(totals.get("error", 0)),
            "success_rate": round(success_rate, 4),
            "tickets_touched": len(tickets_touched),
            "cost_usd": {
                "reported": round(reported_cost, 6),
                "estimated": round(estimated_cost, 6),
                "total": round(reported_cost + estimated_cost, 6),
            },
        },
        "by_agent_type": _serialize_group(by_agent),
        "by_runtime": _serialize_group(by_runtime),
        "top_failures": [{"kind": k, "count": int(v)} for k, v in failures.most_common(5)],
        "highlights": [
            f"mejor agente: {best_agent['name']} ({best_agent['success_rate'] * 100:.0f}% éxito)",
            f"runtime más usado: {most_used_runtime['name']} ({most_used_runtime['runs']} runs)",
        ],
        "partial": partial,
    }


def to_markdown(digest: dict) -> str:
    totals = digest.get("totals") or {}
    cost = (totals.get("cost_usd") or {}).get("total", 0)
    lines = [
        "# Stacky Digest",
        "",
        f"- Runs: {totals.get('runs', 0)}",
        f"- Éxito: {totals.get('success_rate', 0) * 100:.1f}%",
        f"- Costo total USD: {cost}",
        f"- Tickets tocados: {totals.get('tickets_touched', 0)}",
        "",
        "## Highlights",
    ]
    for h in digest.get("highlights") or []:
        lines.append(f"- {h}")
    return "\n".join(lines) + "\n"


def to_html(digest: dict) -> str:
    totals = digest.get("totals") or {}
    highlights = "".join(f"<li>{h}</li>" for h in (digest.get("highlights") or []))
    return (
        "<html><body>"
        "<h1>Stacky Digest</h1>"
        f"<p>Runs: <b>{totals.get('runs', 0)}</b></p>"
        f"<p>Éxito: <b>{totals.get('success_rate', 0) * 100:.1f}%</b></p>"
        f"<p>Costo total USD: <b>{(totals.get('cost_usd') or {}).get('total', 0)}</b></p>"
        "<h2>Highlights</h2>"
        f"<ul>{highlights}</ul>"
        "</body></html>"
    )
