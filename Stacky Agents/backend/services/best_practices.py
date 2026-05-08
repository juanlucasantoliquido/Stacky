"""
FA-46 — Org-wide best practices feed.

Resumen periódico (semanal por default) que muestra qué patrones llevan
a tasas de aprobación más altas. Lo consume un dashboard/feed.

Hoy genera el resumen on-demand vía endpoint. Fase 5+: job semanal con email.

Métricas que devuelve:
- Top agentes por tasa de aprobación
- Top operadores por contribución (con su tasa)
- Top contracts (rules) que más se incumplen — oportunidad de mejora
- Patrones de bloques que correlacionan con aprobación
- Modelos LLM más usados / costo medio por agente
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from db import session_scope
from models import AgentExecution


@dataclass
class FeedSection:
    title: str
    items: list[dict]


def _safe_load(s: str | None) -> dict | list:
    if not s:
        return {}
    try:
        return json.loads(s)
    except Exception:
        return {}


def generate(*, days: int = 7) -> list[FeedSection]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    sections: list[FeedSection] = []

    with session_scope() as session:
        execs = (
            session.query(AgentExecution)
            .filter(AgentExecution.started_at >= cutoff)
            .all()
        )
    total = len(execs)

    if total == 0:
        return [FeedSection(
            title=f"Sin actividad en los últimos {days} días",
            items=[],
        )]

    # ---------------- Agentes por tasa de aprobación ----------------
    by_agent_total: Counter = Counter()
    by_agent_approved: Counter = Counter()
    for e in execs:
        by_agent_total[e.agent_type] += 1
        if e.verdict == "approved":
            by_agent_approved[e.agent_type] += 1
    agent_stats = []
    for agent_type, n in by_agent_total.most_common():
        rate = by_agent_approved[agent_type] / n if n else 0
        agent_stats.append({"agent_type": agent_type, "runs": n, "approval_rate": round(rate, 2)})
    sections.append(FeedSection(title="Agentes — actividad y aprobación", items=agent_stats))

    # ---------------- Top operadores ----------------
    by_user_total: Counter = Counter()
    by_user_approved: Counter = Counter()
    for e in execs:
        by_user_total[e.started_by] += 1
        if e.verdict == "approved":
            by_user_approved[e.started_by] += 1
    user_stats = []
    for user, n in by_user_total.most_common(10):
        rate = by_user_approved[user] / n if n else 0
        user_stats.append({"user": user, "runs": n, "approval_rate": round(rate, 2)})
    sections.append(FeedSection(title="Top operadores", items=user_stats))

    # ---------------- Top contract failures ----------------
    failure_counts: Counter = Counter()
    for e in execs:
        cr = _safe_load(e.contract_result_json)
        if isinstance(cr, dict):
            for f in cr.get("failures", []) or []:
                rule = f.get("rule") or f.get("message", "?")
                failure_counts[(e.agent_type, rule)] += 1
    failures_top = [
        {"agent_type": at, "rule": rule, "count": c}
        for (at, rule), c in failure_counts.most_common(10)
    ]
    sections.append(FeedSection(
        title="Reglas de contrato más incumplidas (oportunidad de mejora)",
        items=failures_top,
    ))

    # ---------------- Modelos usados y costo medio ----------------
    by_model_count: Counter = Counter()
    by_agent_cost: defaultdict[str, list[float]] = defaultdict(list)
    for e in execs:
        md = _safe_load(e.metadata_json)
        if not isinstance(md, dict):
            continue
        m = md.get("model")
        if m:
            by_model_count[m] += 1
        # cost_usd_estimate is computed by some setups; here metadata may lack — skip
    models = [{"model": m, "uses": c} for m, c in by_model_count.most_common(8)]
    sections.append(FeedSection(title="Modelos LLM más usados", items=models))

    # ---------------- Bloques que correlacionan con aprobación ----------------
    block_total: Counter = Counter()
    block_approved: Counter = Counter()
    for e in execs:
        ic = _safe_load(e.input_context_json)
        if not isinstance(ic, list):
            continue
        ids_seen: set[str] = set()
        for b in ic:
            if isinstance(b, dict) and b.get("id"):
                ids_seen.add(b["id"])
        for bid in ids_seen:
            block_total[bid] += 1
            if e.verdict == "approved":
                block_approved[bid] += 1
    block_corr = []
    for bid, n in block_total.most_common(15):
        if n < 3:
            continue
        rate = block_approved[bid] / n if n else 0
        block_corr.append({"block_id": bid, "uses": n, "approval_rate": round(rate, 2)})
    block_corr.sort(key=lambda r: r["approval_rate"], reverse=True)
    sections.append(FeedSection(
        title="Bloques que más correlacionan con aprobación",
        items=block_corr,
    ))

    return sections


def to_payload(*, days: int = 7) -> dict:
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "window_days": days,
        "sections": [{"title": s.title, "items": s.items} for s in generate(days=days)],
    }
