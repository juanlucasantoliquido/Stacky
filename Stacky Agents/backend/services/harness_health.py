"""F3.3 / H0.2 — Score de salud del arnés (multi-runtime).

Agrega datos que las Fases 1-2 YA persisten en AgentExecution (sin columnas ni
escrituras nuevas; pura lectura). Una vista, sin acciones requeridas al operador.

H0.2: compute_health ahora agrega los 3 runtimes. Campos top-level = agregado
global; `by_runtime` = desglose por runtime. Campo `legacy_claude_only` preserva
retro-compat para consumidores que asumían solo claude_code_cli.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy.orm import joinedload

from db import session_scope
from models import AgentExecution, Ticket

if TYPE_CHECKING:
    pass

_CLI_RUNTIME = "claude_code_cli"
_ALL_RUNTIMES = ("claude_code_cli", "codex_cli", "github_copilot")
_TERMINAL = {"completed", "needs_review", "error"}


@dataclass
class RuntimeStats:
    """Métricas por runtime individual."""
    runtime: str
    runs: int = 0
    terminal_runs: int = 0
    completed: int = 0
    autocorrected: int = 0
    total_cost_usd: float = 0.0
    runs_with_cost: int = 0          # runs con dato real de costo
    ticket_ids: set = field(default_factory=set)
    avg_contract_score: float | None = None
    # H8 — KPIs de valor agregado
    autocorrection_saves: int = 0   # autocorrect invocado Y completed
    memory_hits: int = 0            # runs con memory_blocks_injected >= 1
    runaway_stops: int = 0          # runs con metadata["runaway"] presente

    def _rate(self, num: int, den: int) -> float | None:
        return round(num / den, 4) if den else None

    def to_dict(self) -> dict:
        # cost_per_ticket es None si no hubo ningún run con telemetría de costo
        cost_per = (
            round(self.total_cost_usd / len(self.ticket_ids), 4)
            if self.runs_with_cost and self.ticket_ids else None
        )
        return {
            "runs": self.runs,
            "completed_rate": self._rate(self.completed, self.terminal_runs),
            "autocorrection_rate": self._rate(self.autocorrected, self.terminal_runs),
            "cost_per_ticket": cost_per,
            "avg_contract_score": (
                round(self.avg_contract_score, 1)
                if self.avg_contract_score is not None else None
            ),
            # H8
            "autocorrection_saves": self.autocorrection_saves,
            "memory_hit_rate": self._rate(self.memory_hits, self.runs),
            "runaway_stops": self.runaway_stops,
        }


@dataclass
class HarnessHealth:
    window_days: int
    total_runs: int = 0
    terminal_runs: int = 0
    completed: int = 0
    needs_review: int = 0
    errored: int = 0
    autocorrected_runs: int = 0
    completed_without_intervention: int = 0
    total_cost_usd: float = 0.0
    runs_with_cost: int = 0
    tickets: int = 0
    avg_contract_score_by_agent: dict[str, float] = field(default_factory=dict)
    model_distribution: dict[str, int] = field(default_factory=dict)
    # H0.2 — por runtime
    _by_runtime: dict[str, RuntimeStats] = field(default_factory=dict)
    # H8 — KPIs de valor agregado (agregado global)
    autocorrection_saves: int = 0
    _memory_hits: int = 0           # interno; se expone como memory_hit_rate
    runaway_stops: int = 0
    # H8 — por proyecto (ticket.project)
    _by_project: dict[str, RuntimeStats] = field(default_factory=dict)

    def _rate(self, num: int, den: int) -> float | None:
        return round(num / den, 4) if den else None

    def to_dict(self) -> dict:
        # Retro-compat: legacy_claude_only = solo las métricas del runtime claude.
        cl_stats = self._by_runtime.get("claude_code_cli")
        legacy = {}
        if cl_stats:
            cl_tickets = len(cl_stats.ticket_ids)
            legacy = {
                "total_runs": cl_stats.runs,
                "total_cost_usd": round(cl_stats.total_cost_usd, 4),
                "cost_per_ticket_usd": (
                    round(cl_stats.total_cost_usd / cl_tickets, 4) if cl_tickets else None
                ),
            }

        return {
            "window_days": self.window_days,
            "total_runs": self.total_runs,
            "terminal_runs": self.terminal_runs,
            "completed": self.completed,
            "needs_review": self.needs_review,
            "errored": self.errored,
            "completed_without_intervention_rate": self._rate(
                self.completed_without_intervention, self.terminal_runs
            ),
            "autocorrection_rate": self._rate(self.autocorrected_runs, self.terminal_runs),
            "error_rate": self._rate(self.errored, self.terminal_runs),
            "total_cost_usd": round(self.total_cost_usd, 4),
            "cost_per_ticket_usd": (
                round(self.total_cost_usd / self.tickets, 4) if self.tickets else None
            ),
            "runs_with_cost_telemetry": self.runs_with_cost,
            "avg_contract_score_by_agent": {
                a: round(s, 1) for a, s in self.avg_contract_score_by_agent.items()
            },
            "model_distribution": self.model_distribution,
            # H0.2 — desglose por runtime
            "by_runtime": {rt: stats.to_dict() for rt, stats in self._by_runtime.items()},
            # retro-compat para consumidores que asumían solo claude_code_cli
            "legacy_claude_only": legacy,
            # H8 — KPIs de valor agregado
            "autocorrection_saves": self.autocorrection_saves,
            "memory_hit_rate": (
                round(self._memory_hits / self.total_runs, 4)
                if self.total_runs else None
            ),
            "runaway_stops": self.runaway_stops,
            # H8 — desglose por proyecto
            "by_project": {p: stats.to_dict() for p, stats in self._by_project.items()},
        }


def _get_or_create_runtime_stats(
    by_runtime: dict[str, RuntimeStats], runtime: str
) -> RuntimeStats:
    if runtime not in by_runtime:
        by_runtime[runtime] = RuntimeStats(runtime=runtime)
    return by_runtime[runtime]


def _extract_cost(md: dict) -> float | None:
    """Extrae costo desde claude_telemetry o harness_telemetry."""
    for key in ("claude_telemetry", "harness_telemetry"):
        telemetry = md.get(key) or {}
        cost = telemetry.get("total_cost_usd")
        if isinstance(cost, (int, float)):
            return float(cost)
    return None


def compute_health(
    window_days: int = 14,
    runtimes: list[str] | None = None,
) -> HarnessHealth:
    """Calcula la salud del arnés sobre los runs de los últimos `window_days`.

    H0.2: agrega TODOS los runtimes por defecto (runtimes=None).
    Pasar runtimes=["codex_cli"] limita a ese subset.

    Default 14 días: alinea con la ventana de medición de F2.5 (memoria colaborativa).
    """
    since = datetime.utcnow() - timedelta(days=window_days)
    h = HarnessHealth(window_days=window_days)

    score_sum: dict[str, float] = {}
    score_n: dict[str, int] = {}
    ticket_ids: set[int] = set()
    by_runtime: dict[str, RuntimeStats] = {}
    by_project: dict[str, RuntimeStats] = {}

    # Scores por runtime para avg_contract_score en RuntimeStats
    rt_score_sum: dict[str, float] = {}
    rt_score_n: dict[str, int] = {}
    # Scores por proyecto
    proj_score_sum: dict[str, float] = {}
    proj_score_n: dict[str, int] = {}

    with session_scope() as session:
        rows = (
            session.query(AgentExecution)
            .options(joinedload(AgentExecution.ticket))
            .filter(AgentExecution.started_at >= since)
            .all()
        )
        for ex in rows:
            md = ex.metadata_dict
            runtime = md.get("runtime") or ""
            if not runtime:
                continue
            if runtimes is not None and runtime not in runtimes:
                continue

            rt_stats = _get_or_create_runtime_stats(by_runtime, runtime)
            rt_stats.runs += 1
            rt_stats.ticket_ids.add(ex.ticket_id)

            # H8 — by_project: agrupar por ticket.project (joinedload garantiza que no haya N+1)
            project = (ex.ticket.project if ex.ticket else None) or "unknown"
            proj_stats = _get_or_create_runtime_stats(by_project, project)
            proj_stats.runs += 1
            proj_stats.ticket_ids.add(ex.ticket_id)

            h.total_runs += 1
            ticket_ids.add(ex.ticket_id)

            status = ex.status
            is_terminal = status in _TERMINAL
            if is_terminal:
                h.terminal_runs += 1
                rt_stats.terminal_runs += 1
                proj_stats.terminal_runs += 1

            autocorrect = md.get("autocorrect") or {}
            attempts = int(autocorrect.get("attempts") or 0)
            if attempts > 0:
                h.autocorrected_runs += 1
                rt_stats.autocorrected += 1
                proj_stats.autocorrected += 1

            if status == "completed":
                h.completed += 1
                rt_stats.completed += 1
                proj_stats.completed += 1
                if attempts == 0:
                    h.completed_without_intervention += 1
            elif status == "needs_review":
                h.needs_review += 1
            elif status == "error":
                h.errored += 1

            # H8 — autocorrection_saves: autocorrect invocado Y terminó completed
            if attempts > 0 and status == "completed":
                h.autocorrection_saves += 1
                rt_stats.autocorrection_saves += 1
                proj_stats.autocorrection_saves += 1

            # H8 — memory_hit_rate: memory_blocks_injected >= 1 (ausencia = 0)
            mem_blocks = md.get("memory_blocks_injected")
            if isinstance(mem_blocks, (int, float)) and mem_blocks > 0:
                h._memory_hits += 1
                rt_stats.memory_hits += 1
                proj_stats.memory_hits += 1

            # H8 — runaway_stops: metadata["runaway"] presente y no nulo
            if md.get("runaway") is not None:
                h.runaway_stops += 1
                rt_stats.runaway_stops += 1
                proj_stats.runaway_stops += 1

            cost = _extract_cost(md)
            if cost is not None:
                h.total_cost_usd += cost
                h.runs_with_cost += 1
                rt_stats.total_cost_usd += cost
                rt_stats.runs_with_cost += 1
                proj_stats.total_cost_usd += cost
                proj_stats.runs_with_cost += 1

            # model_distribution: solo claude tiene claude_code_model significativo
            model = md.get("claude_code_model")
            if model:
                h.model_distribution[model] = h.model_distribution.get(model, 0) + 1

            cr = ex.contract_result
            if cr and isinstance(cr.get("score"), (int, float)):
                sc = float(cr["score"])
                score_sum[ex.agent_type] = score_sum.get(ex.agent_type, 0.0) + sc
                score_n[ex.agent_type] = score_n.get(ex.agent_type, 0) + 1
                rt_score_sum[runtime] = rt_score_sum.get(runtime, 0.0) + sc
                rt_score_n[runtime] = rt_score_n.get(runtime, 0) + 1
                proj_score_sum[project] = proj_score_sum.get(project, 0.0) + sc
                proj_score_n[project] = proj_score_n.get(project, 0) + 1

    h.tickets = len(ticket_ids)
    h.avg_contract_score_by_agent = {
        a: score_sum[a] / score_n[a] for a in score_sum if score_n.get(a)
    }
    # Propagar avg_contract_score a cada RuntimeStats
    for rt, stats in by_runtime.items():
        if rt_score_n.get(rt):
            stats.avg_contract_score = rt_score_sum[rt] / rt_score_n[rt]
    # Propagar avg_contract_score a cada ProjectStats
    for proj, stats in by_project.items():
        if proj_score_n.get(proj):
            stats.avg_contract_score = proj_score_sum[proj] / proj_score_n[proj]

    h._by_runtime = by_runtime
    h._by_project = by_project
    return h
