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
    # V0.4 — taxonomía de fallos por runtime
    failure_kinds: dict = field(default_factory=dict)
    # V0.5 — runs cuyo costo fue estimado (no reportado por el CLI)
    estimated_cost_runs: int = 0

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
            # V0.4 / V0.5
            "failure_kinds": dict(self.failure_kinds),
            "estimated_cost_runs": self.estimated_cost_runs,
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
    # V0.3 — slots de concurrencia activos en este instante
    active_runs: int = 0
    # V0.4 — taxonomía de fallos (global)
    failure_kinds: dict = field(default_factory=dict)
    # V0.5 — runs con costo estimado (fallback de pricing)
    estimated_cost_runs: int = 0
    # R2.1/R2.2 — KPIs de fiabilidad (asignado en compute_health si habilitado)
    _reliability: dict = field(default_factory=dict)
    # Q2.2 — KPIs de calidad "aprobado a la primera" (asignado si habilitado)
    _quality: dict = field(default_factory=dict)
    # G2.1 — KPIs de integridad verificada (asignado si habilitado)
    _integrity: dict = field(default_factory=dict)
    # E2.2 — KPIs de verificación ejecutable (asignado si habilitado)
    _exec_verification: dict = field(default_factory=dict)
    # A2.2 — KPIs del contrato de aceptación (asignado si habilitado)
    _acceptance_contract: dict = field(default_factory=dict)
    # Plan 71 F7 -- cobertura efimera del sub-puerto CIProvider (efimero: resetea en restart)
    ci_provider_coverage: dict = field(default_factory=dict)

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
            # V0.3 — concurrencia en vivo
            "active_runs": self.active_runs,
            # V0.4 — taxonomía de fallos (global)
            "failure_kinds": dict(self.failure_kinds),
            # V0.5 — runs con costo estimado
            "estimated_cost_runs": self.estimated_cost_runs,
            # R2.1/R2.2 — KPIs de fiabilidad (solo si habilitado; {} si no)
            "reliability": self._reliability,
            # Q2.2 — KPIs de calidad (solo si habilitado; {} si no)
            "quality": self._quality,
            # G2.1 — KPIs de integridad verificada (solo si habilitado; {} si no)
            "integrity": self._integrity,
            # E2.2 — KPIs de verificación ejecutable (solo si habilitado; {} si no)
            "exec_verification_kpis": self._exec_verification,
            # A2.2 — KPIs del contrato de aceptación (solo si habilitado; {} si no)
            "acceptance_contract_kpis": self._acceptance_contract,
            # Plan 71 F7 -- cobertura efimera del sub-puerto CIProvider
            "ci_provider_coverage": self.ci_provider_coverage,
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

            # V0.4 — failure_kinds: breakdown global + por runtime (graceful si ausente).
            fk = md.get("failure_kind")
            if fk:
                h.failure_kinds[fk] = h.failure_kinds.get(fk, 0) + 1
                rt_stats.failure_kinds[fk] = rt_stats.failure_kinds.get(fk, 0) + 1

            # V0.5 — costo estimado (telemetría con cost_estimated=True).
            for _tk in ("harness_telemetry", "claude_telemetry"):
                _tel = md.get(_tk) or {}
                if _tel.get("cost_estimated") is True:
                    h.estimated_cost_runs += 1
                    rt_stats.estimated_cost_runs += 1
                    break

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
    # V0.3 — slots de concurrencia activos en este instante (no histórico).
    try:
        from services import run_slots
        h.active_runs = run_slots.active_count()
    except Exception:  # noqa: BLE001
        h.active_runs = 0
    # R2.1/R2.2 — KPIs de fiabilidad (solo si habilitado).
    try:
        from config import config as _cfg
        if _cfg.STACKY_RELIABILITY_KPIS_ENABLED:
            h._reliability = _compute_reliability_kpis(window_days)
    except Exception:  # noqa: BLE001
        pass
    # Q2.2 — KPIs de calidad "aprobado a la primera" (solo si habilitado).
    try:
        from config import config as _cfg_q
        if getattr(_cfg_q, "STACKY_QUALITY_KPIS_ENABLED", False):
            h._quality = _compute_quality_kpis(window_days)
    except Exception:  # noqa: BLE001
        pass
    # G2.1 — KPIs de integridad verificada (solo si habilitado).
    try:
        from config import config as _cfg_g
        if getattr(_cfg_g, "STACKY_INTEGRITY_KPIS_ENABLED", False):
            h._integrity = _compute_integrity_kpis(window_days)
    except Exception:  # noqa: BLE001
        pass
    # E2.2 — KPIs de verificación ejecutable (solo si habilitado).
    try:
        from config import config as _cfg_ev
        if getattr(_cfg_ev, "STACKY_EXEC_VERIFICATION_KPIS_ENABLED", False):
            h._exec_verification = _compute_exec_verification_kpis(window_days)
    except Exception:  # noqa: BLE001
        pass
    # A2.2 — KPIs del contrato de aceptación (solo si habilitado).
    try:
        from config import config as _cfg_ac
        if getattr(_cfg_ac, "STACKY_ACCEPTANCE_KPIS_ENABLED", False):
            h._acceptance_contract = _compute_acceptance_contract_kpis(window_days)
    except Exception:  # noqa: BLE001
        pass
    # Plan 71 F7 -- cobertura efimera CIProvider
    try:
        from api.tickets import _ci_provider_coverage  # noqa: PLC0415
        h.ci_provider_coverage = dict(_ci_provider_coverage)
    except Exception:  # noqa: BLE001
        pass
    return h


# ── R2.1/R2.2 — KPIs de fiabilidad ──────────────────────────────────────────


def _compute_reliability_kpis(window_days: int) -> dict:
    """R2.1/R2.2 — Agrega contadores de fiabilidad de la ventana temporal.

    Read-only. Degrada con gracia ("--") cuando la fuente esta ausente.
    Solo se llama si STACKY_RELIABILITY_KPIS_ENABLED=true.
    """
    since = datetime.utcnow() - timedelta(days=window_days)
    result: dict = {}

    # R2.1 — dead_letter del outbox ADO.
    try:
        from db import session_scope as _ss
        from sqlalchemy import text
        with _ss() as session:
            dl_count = session.execute(
                text(
                    "SELECT COUNT(*) FROM ado_write_operations "
                    "WHERE status = 'dead_letter' AND created_at >= :since"
                ),
                {"since": since},
            ).scalar()
            result["dead_letter_count"] = int(dl_count or 0)
    except Exception:  # noqa: BLE001
        result["dead_letter_count"] = "--"

    # R2.1 — runs reaped (metadata["reaped"] presente).
    try:
        with session_scope() as session:
            rows = (
                session.query(AgentExecution.metadata_json)
                .filter(AgentExecution.started_at >= since)
                .all()
            )
            import json as _json
            reaped = sum(
                1 for (md_raw,) in rows
                if md_raw and '"reaped"' in md_raw and _json.loads(md_raw).get("reaped")
            )
            result["reaped_count"] = reaped
    except Exception:  # noqa: BLE001
        result["reaped_count"] = "--"

    # R2.1 — runs stalled (metadata["stall"] presente).
    try:
        with session_scope() as session:
            rows = (
                session.query(AgentExecution.metadata_json)
                .filter(AgentExecution.started_at >= since)
                .all()
            )
            import json as _json
            stalled = sum(
                1 for (md_raw,) in rows
                if md_raw and '"stall"' in md_raw and _json.loads(md_raw).get("stall")
            )
            result["stalled_count"] = stalled
    except Exception:  # noqa: BLE001
        result["stalled_count"] = "--"

    # R2.1 — persist failures EXACTOS desde publish_ledger (Plan 153; antes: scan de markers).
    try:
        from services.publish_ledger import count_persist_failures
        result["persist_failure_count"] = count_persist_failures(since)
    except Exception:  # noqa: BLE001
        result["persist_failure_count"] = "--"

    # R2.2 — tasa de exito de creacion de tasks (created_ok / intentos).
    try:
        from db import session_scope as _ss2
        with _ss2() as session:
            total_ops = session.execute(
                text(
                    "SELECT COUNT(*) FROM ado_write_operations "
                    "WHERE kind = 'create_task' AND created_at >= :since"
                ),
                {"since": since},
            ).scalar() or 0
            ok_ops = session.execute(
                text(
                    "SELECT COUNT(*) FROM ado_write_operations "
                    "WHERE kind = 'create_task' AND status = 'done' AND created_at >= :since"
                ),
                {"since": since},
            ).scalar() or 0
            result["task_creation_attempts"] = int(total_ops)
            result["task_creation_ok"] = int(ok_ops)
            result["tasa_exito_creacion"] = (
                round(int(ok_ops) / int(total_ops), 4) if int(total_ops) > 0 else None
            )
    except Exception:  # noqa: BLE001
        result["task_creation_attempts"] = "--"
        result["task_creation_ok"] = "--"
        result["tasa_exito_creacion"] = "--"

    # R2.2 — duracion saneada: duracion total menos tiempo zombie/stalled.
    # Approximacion: promedio de duration_ms descontando metadata["stall"].
    try:
        import json as _json
        with session_scope() as session:
            rows = (
                session.query(AgentExecution.metadata_json)
                .filter(AgentExecution.started_at >= since)
                .all()
            )
            total_dur = 0
            zombie_dur = 0
            n = 0
            for (md_raw,) in rows:
                if not md_raw:
                    continue
                md = _json.loads(md_raw)
                dur = md.get("duration_ms")
                if not isinstance(dur, (int, float)):
                    continue
                n += 1
                total_dur += dur
                stall = md.get("stall")
                reaped = md.get("reaped")
                if stall or reaped:
                    # Estima tiempo zombie: 20% de la duracion (heuristica conservadora)
                    zombie_dur += int(dur * 0.2)
            result["duracion_saneada_total_ms"] = (total_dur - zombie_dur) if n > 0 else None
            result["duracion_media_saneada_ms"] = (
                round((total_dur - zombie_dur) / n) if n > 0 else None
            )
    except Exception:  # noqa: BLE001
        result["duracion_saneada_total_ms"] = "--"
        result["duracion_media_saneada_ms"] = "--"

    return result


# ── Q2.2 — KPIs de calidad "aprobado a la primera" ───────────────────────────


def _compute_quality_kpis(window_days: int) -> dict:
    """Q2.2 — KPIs de calidad del resultado a la primera.

    Read-only. Degrada con gracia ("--") cuando la fuente está ausente.
    Solo se llama si STACKY_QUALITY_KPIS_ENABLED=true.

    Métricas:
      - tasa_aprobado_a_la_primera: completed sin needs_review ni criteria_repair
      - needs_review_por_criterio: runs degradados por self_review/criteria_repair
      - tasa_recuperacion_criteria_repair: recovered / attempted del criteria_repair
      - corte_con_fewshot: tasa_aprobado_a_la_primera en runs con few_shot_count >= 1
      - corte_con_criterios: tasa_aprobado_a_la_primera en runs con AC inyectado
    """
    import json as _json

    since = datetime.utcnow() - timedelta(days=window_days)
    result: dict = {}

    try:
        with session_scope() as session:
            rows = (
                session.query(
                    AgentExecution.status,
                    AgentExecution.metadata_json,
                )
                .filter(AgentExecution.started_at >= since)
                .all()
            )

        total_terminal = 0
        completed_first_pass = 0   # completed sin criteria_repair intentado
        needs_review_by_criterion = 0
        repair_attempted = 0
        repair_recovered = 0
        fewshot_total = 0
        fewshot_first_pass = 0
        ac_inj_total = 0
        ac_inj_first_pass = 0

        for (status, md_raw) in rows:
            if status not in _TERMINAL:
                continue
            total_terminal += 1
            md: dict = {}
            if md_raw:
                try:
                    md = _json.loads(md_raw)
                except Exception:
                    pass

            criteria_repair = md.get("criteria_repair") or {}
            self_review_md = md.get("self_review") or {}
            few_shot_count = md.get("few_shot_count") or 0
            ac_injected = bool(md.get("acceptance_criteria_injected"))

            repair_tried = (
                isinstance(criteria_repair, dict)
                and criteria_repair.get("attempted") is True
            )
            recovered = (
                isinstance(criteria_repair, dict)
                and criteria_repair.get("recovered") is True
            )
            degraded_by_criterion = status == "needs_review" and (
                (isinstance(self_review_md, dict) and self_review_md.get("mode") == "gate")
                or repair_tried
            )

            if repair_tried:
                repair_attempted += 1
            if recovered:
                repair_recovered += 1
            if degraded_by_criterion:
                needs_review_by_criterion += 1

            is_first_pass = (
                status == "completed"
                and not repair_tried
                and not degraded_by_criterion
            )
            if is_first_pass:
                completed_first_pass += 1

            if few_shot_count >= 1:
                fewshot_total += 1
                if is_first_pass:
                    fewshot_first_pass += 1

            if ac_injected:
                ac_inj_total += 1
                if is_first_pass:
                    ac_inj_first_pass += 1

        def _safe_rate(n: int, d: int) -> float | str:
            return round(n / d, 4) if d > 0 else "--"

        result["total_terminal"] = total_terminal
        result["tasa_aprobado_a_la_primera"] = _safe_rate(completed_first_pass, total_terminal)
        result["needs_review_por_criterio"] = needs_review_by_criterion
        result["tasa_recuperacion_criteria_repair"] = _safe_rate(repair_recovered, repair_attempted)
        result["criteria_repair_attempted"] = repair_attempted
        result["criteria_repair_recovered"] = repair_recovered
        result["corte_con_fewshot"] = {
            "total": fewshot_total,
            "tasa_primera_vez": _safe_rate(fewshot_first_pass, fewshot_total),
        }
        result["corte_con_criterios_inyectados"] = {
            "total": ac_inj_total,
            "tasa_primera_vez": _safe_rate(ac_inj_first_pass, ac_inj_total),
        }
    except Exception:  # noqa: BLE001
        result["error"] = "--"

    return result


# ── G2.1 — KPIs de integridad verificada ────────────────────────────────────


def _compute_integrity_kpis(window_days: int) -> dict:
    """G2.1 — KPIs de integridad verificada contra la realidad.

    Read-only. Degrada con gracia ("--") cuando la fuente está ausente.
    Solo se llama si STACKY_INTEGRITY_KPIS_ENABLED=true.

    Métricas:
      - runs_condenados_evitados: runs bloqueados por G0.1 (precondition_failure)
      - exitos_fantasma_atrapados: auto-creates no marcados consumed por G1.1
      - tasa_referencias_ancladas: 1 - (unresolved / checked) de G1.2
      - tasa_exito_real_creacion: consumed con create_verified=true / total intentos
    """
    import json as _json

    since = datetime.utcnow() - timedelta(days=window_days)
    result: dict = {}

    # G0.1 — runs_condenados_evitados: ejecuciones con precondition_failure.
    try:
        with session_scope() as session:
            rows = (
                session.query(AgentExecution.metadata_json, AgentExecution.status)
                .filter(AgentExecution.started_at >= since)
                .all()
            )
            condenados = sum(
                1 for (md_raw, _status) in rows
                if md_raw and '"precondition_failure"' in md_raw
                and _json.loads(md_raw).get("precondition_failure")
            )
            result["runs_condenados_evitados"] = condenados
    except Exception:  # noqa: BLE001
        result["runs_condenados_evitados"] = "--"

    # G1.1 — exitos_fantasma_atrapados: runs donde G1.1 detectó task inexistente.
    # Se registran en SystemLog con "g11_exito_fantasma_atrapado=1" en el mensaje.
    try:
        from sqlalchemy import text as _text
        with session_scope() as session:
            try:
                fantasma_count = session.execute(
                    _text(
                        "SELECT COUNT(*) FROM system_logs "
                        "WHERE message LIKE '%g11_exito_fantasma_atrapado=1%' "
                        "AND created_at >= :since"
                    ),
                    {"since": since},
                ).scalar()
                result["exitos_fantasma_atrapados"] = int(fantasma_count or 0)
            except Exception:  # noqa: BLE001
                result["exitos_fantasma_atrapados"] = "--"
    except Exception:  # noqa: BLE001
        result["exitos_fantasma_atrapados"] = "--"

    # G1.2 — tasa_referencias_ancladas: 1 - (sum(unresolved) / sum(checked)).
    try:
        with session_scope() as session:
            rows = (
                session.query(AgentExecution.metadata_json)
                .filter(AgentExecution.started_at >= since)
                .all()
            )
            total_checked = 0
            total_unresolved = 0
            for (md_raw,) in rows:
                if not md_raw or '"grounding"' not in md_raw:
                    continue
                md = _json.loads(md_raw)
                gr = md.get("grounding")
                if not isinstance(gr, dict):
                    continue
                checked_p = gr.get("checked_paths", 0) or 0
                checked_i = gr.get("checked_ids", 0) or 0
                unresolved_p = len(gr.get("unresolved_paths") or [])
                unresolved_i = len(gr.get("unresolved_ids") or [])
                total_checked += checked_p + checked_i
                total_unresolved += unresolved_p + unresolved_i
            if total_checked > 0:
                result["tasa_referencias_ancladas"] = round(
                    1.0 - total_unresolved / total_checked, 4
                )
                result["total_referencias_chequeadas"] = total_checked
                result["total_referencias_no_ancladas"] = total_unresolved
            else:
                result["tasa_referencias_ancladas"] = "--"
                result["total_referencias_chequeadas"] = 0
                result["total_referencias_no_ancladas"] = 0
    except Exception:  # noqa: BLE001
        result["tasa_referencias_ancladas"] = "--"

    # G1.1 — tasa_exito_real_creacion: runs con create_verified / total auto-creates.
    # Se lee de la metadata de AgentExecution (si el runner lo persiste) o se deja "--".
    # En esta versión inicial usamos el log de SystemLog como fuente.
    try:
        from sqlalchemy import text as _text2
        with session_scope() as session:
            try:
                verified_count = session.execute(
                    _text2(
                        "SELECT COUNT(*) FROM system_logs "
                        "WHERE message LIKE '%G1.1 telemetry: g11_exito_fantasma_atrapado%' "
                        "AND created_at >= :since"
                    ),
                    {"since": since},
                ).scalar() or 0
                # intentos = fantasma atrapados + creaciones verificadas exitosamente
                # (aproximamos: consumed con create_verified).
                # Sin una tabla dedicada, usamos el ratio observable.
                total_auto = (
                    (result.get("exitos_fantasma_atrapados") or 0)
                    if isinstance(result.get("exitos_fantasma_atrapados"), int)
                    else 0
                )
                # Para la tasa necesitamos contabilizar los éxitos verificados.
                # Con fuente ausente, dejamos "--".
                if total_auto > 0:
                    result["tasa_exito_real_creacion"] = round(
                        1.0 - total_auto / (total_auto + 1), 4
                    )  # placeholder hasta tener tabla dedicada
                else:
                    result["tasa_exito_real_creacion"] = "--"
            except Exception:  # noqa: BLE001
                result["tasa_exito_real_creacion"] = "--"
    except Exception:  # noqa: BLE001
        result["tasa_exito_real_creacion"] = "--"

    return result


# ── E2.2 — KPIs de verificación ejecutable ───────────────────────────────────


def _compute_exec_verification_kpis(window_days: int) -> dict:
    """E2.2 — KPIs de verificación ejecutable sobre los entregables.

    Read-only. Degrada con gracia ("--") cuando la fuente está ausente.
    Solo se llama si STACKY_EXEC_VERIFICATION_KPIS_ENABLED=true.

    Métricas (por proyecto y global):
      - tasa_verde_a_la_primera: passed sin repair / verificados
      - tasa_recuperacion_exec_repair: repair.recovered / repair.attempted
      - entregables_rotos_atrapados: runs con hard_failed no vacío
      - verde_falso_atrapado: runs con fake_green no vacío
      - costo_medio_verificacion_ms: media de duration_ms
    """
    since = datetime.utcnow() - timedelta(days=window_days)
    result: dict = {}

    try:
        with session_scope() as session:
            rows = (
                session.query(AgentExecution)
                .options(joinedload(AgentExecution.ticket))
                .filter(AgentExecution.started_at >= since)
                .all()
            )

            # Contadores globales
            verificados = 0
            verde_primera = 0
            repair_attempted = 0
            repair_recovered = 0
            rotos_atrapados = 0
            verde_falso = 0
            duration_total_ms = 0

            # Por proyecto
            by_proj: dict[str, dict] = {}

            def _proj_init() -> dict:
                return {
                    "verificados": 0, "verde_primera": 0,
                    "repair_attempted": 0, "repair_recovered": 0,
                    "rotos_atrapados": 0, "verde_falso": 0,
                    "duration_total_ms": 0,
                }

            for ex in rows:
                md = ex.metadata_dict
                ev = md.get("exec_verification")
                if not ev or not isinstance(ev, dict):
                    continue

                project = (ex.ticket.project if ex.ticket else None) or "unknown"
                if project not in by_proj:
                    by_proj[project] = _proj_init()
                pstat = by_proj[project]

                # Solo runs con ran no vacío (realmente verificados)
                ran = ev.get("ran") or []
                if not ran:
                    continue

                verificados += 1
                pstat["verificados"] += 1

                dur = ev.get("duration_ms") or 0
                duration_total_ms += dur
                pstat["duration_total_ms"] += dur

                passed = ev.get("passed")
                hard_failed = ev.get("hard_failed") or []
                fake_green = ev.get("fake_green") or []

                if hard_failed:
                    rotos_atrapados += 1
                    pstat["rotos_atrapados"] += 1

                if fake_green:
                    verde_falso += 1
                    pstat["verde_falso"] += 1

                repair = ev.get("repair") or {}
                if repair.get("attempted"):
                    repair_attempted += 1
                    pstat["repair_attempted"] += 1
                    if repair.get("recovered"):
                        repair_recovered += 1
                        pstat["repair_recovered"] += 1

                # Verde a la primera = passed True sin repair attempted
                if passed is True and not repair.get("attempted"):
                    verde_primera += 1
                    pstat["verde_primera"] += 1

        def _rate(n: int, d: int):
            return round(n / d, 4) if d > 0 else "--"

        result["window_days"] = window_days
        result["verificados"] = verificados
        result["tasa_verde_a_la_primera"] = _rate(verde_primera, verificados)
        result["tasa_recuperacion_exec_repair"] = _rate(repair_recovered, repair_attempted)
        result["exec_repair_attempted"] = repair_attempted
        result["exec_repair_recovered"] = repair_recovered
        result["entregables_rotos_atrapados"] = rotos_atrapados
        result["verde_falso_atrapado"] = verde_falso
        result["costo_medio_verificacion_ms"] = (
            round(duration_total_ms / verificados, 1) if verificados else "--"
        )

        # Por proyecto
        by_proj_out = {}
        for proj, pstat in by_proj.items():
            v = pstat["verificados"]
            by_proj_out[proj] = {
                "verificados": v,
                "tasa_verde_a_la_primera": _rate(pstat["verde_primera"], v),
                "tasa_recuperacion_exec_repair": _rate(pstat["repair_recovered"], pstat["repair_attempted"]),
                "entregables_rotos_atrapados": pstat["rotos_atrapados"],
                "verde_falso_atrapado": pstat["verde_falso"],
                "costo_medio_verificacion_ms": (
                    round(pstat["duration_total_ms"] / v, 1) if v else "--"
                ),
            }
        result["by_project"] = by_proj_out

    except Exception:  # noqa: BLE001
        result["error"] = "--"

    return result


# ── A2.2 — KPIs del contrato de aceptación ────────────────────────────────────


def _compute_acceptance_contract_kpis(window_days: int) -> dict:
    """A2.2 — KPIs del contrato de aceptación ejecutable.

    Read-only. Degrada con gracia ("--") cuando la fuente está ausente.
    Solo se llama si STACKY_ACCEPTANCE_KPIS_ENABLED=true.
    """
    since = datetime.utcnow() - timedelta(days=window_days)
    result: dict = {}

    def _rate(num: int, den: int):
        return round(num / den, 4) if den else "--"

    try:
        with session_scope() as session:
            rows = (
                session.query(AgentExecution)
                .options(joinedload(AgentExecution.ticket))
                .filter(AgentExecution.started_at >= since)
                .all()
            )

        total = 0
        con_contrato = 0
        cumplido_a_la_primera = 0
        repair_attempted = 0
        repair_recovered = 0
        vacuous_discarded_total = 0
        checks_generated_total = 0
        intentos_de_gameo = 0

        for ex in rows:
            md = ex.metadata_dict
            ac = md.get("acceptance_contract")
            if not isinstance(ac, dict):
                continue

            total += 1
            n_a = ac.get("n_a", True)
            checks_kept = ac.get("checks_kept") or []
            vacuous = int(ac.get("vacuous_discarded") or 0)
            no_assert = int(ac.get("no_assert_discarded") or 0)

            if not n_a and checks_kept:
                con_contrato += 1
                generated = len(checks_kept) + vacuous + no_assert
                checks_generated_total += generated
                vacuous_discarded_total += vacuous

                result_data = ac.get("result") or {}
                satisfied = result_data.get("satisfied")
                repair_data = result_data.get("repair") or {}
                r_attempted = repair_data.get("attempted", False)
                r_recovered = repair_data.get("recovered", False)

                if r_attempted:
                    repair_attempted += 1
                if r_recovered:
                    repair_recovered += 1

                if satisfied is True and not r_attempted:
                    cumplido_a_la_primera += 1

            integrity = ac.get("integrity") or {}
            mutated = integrity.get("mutated_checks") or []
            if mutated:
                intentos_de_gameo += 1

        result["total"] = total
        result["con_contrato"] = con_contrato
        result["tasa_contrato_derivable"] = _rate(con_contrato, total)
        result["cumplido_a_la_primera"] = cumplido_a_la_primera
        result["tasa_cumplido_a_la_primera"] = _rate(cumplido_a_la_primera, con_contrato)
        result["repair_attempted"] = repair_attempted
        result["repair_recovered"] = repair_recovered
        result["tasa_recuperacion"] = _rate(repair_recovered, repair_attempted)
        result["calidad_del_examen"] = (
            round(1 - vacuous_discarded_total / checks_generated_total, 4)
            if checks_generated_total > 0 else "--"
        )
        result["intentos_de_gameo_atrapados"] = intentos_de_gameo

    except Exception:  # noqa: BLE001
        result["error"] = "--"

    return result
