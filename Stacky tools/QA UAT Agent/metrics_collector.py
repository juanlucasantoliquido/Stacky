"""
metrics_collector.py — Recolector de métricas por run para QA UAT Agent.

Analiza el contenido de un run completado (events.jsonl, checkpoints/,
run_manifest.json, run_state.json, .playwright-report.json, blockers.json)
y produce un registro de métricas normalizado.

Las métricas se persisten en data/metrics.jsonl (append-only, una línea por run).

SCHEMA de un registro de métricas:
{
  "run_id": "uat-70-...",
  "ticket_id": 70,
  "collected_at": "...",
  "tool_version": "1.0.0",

  "run": {
    "duration_ms": 12345,
    "status": "completed",  // completed | failed | blocked | unknown
    "verdict": "PASS",      // PASS | FAIL | BLOCKED | MIXED | UNKNOWN
    "mode": "dry-run",
    "headed": false,
    "started_at": "...",
    "completed_at": "..."
  },

  "events": {
    "total": 142,
    "by_level": {"info": 100, "warning": 30, "error": 12},
    "by_category": {"page_click": 20, "page_fill": 15, ...},
    "failures": 5,
    "blockers": 2,
    "playwright_actions": 45
  },

  "playwright": {
    "scenarios": 3,
    "pass": 2,
    "fail": 1,
    "blocked": 0,
    "assertions_total": 18,
    "assertions_pass": 16,
    "assertions_fail": 2,
    "screenshots": 12,
    "network_errors": 2
  },

  "stages": {
    "completed": ["reader", "compiler", "generator", "runner"],
    "failed": ["evaluator"],
    "blocked": []
  },

  "learnings": {
    "candidates_generated": 3,
    "approved": 1
  },

  "blockers_summary": {
    "total": 2,
    "resolved": 2,
    "pending": 0
  }
}
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

_py_logger = logging.getLogger("stacky.qa_uat.metrics_collector")

_METRICS_DB_PATH = Path(__file__).parent / "data" / "metrics.jsonl"
_TOOL_VERSION = "2.0.0"  # Sprint 7 — extended signal/time/flake metrics

_VALID_CATEGORIES = ["ENV", "DATA", "GEN", "NAV", "PIP", "OBS", "APP", "OPS", "SEC"]


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ── Sprint 7 typed metrics ────────────────────────────────────────────────────

@dataclass
class SignalMetrics:
    """Verdict / category breakdown for a run."""
    unknown_verdict_count: int = 0
    blocked_without_reason_count: int = 0
    blocked_by_category: dict = field(default_factory=lambda: {c: 0 for c in _VALID_CATEGORIES})
    fail_app_count: int = 0
    pass_count: int = 0
    skipped_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TimeMetrics:
    """Stage durations for a run."""
    time_to_first_actionable_failure_ms: Optional[int] = None
    preflight_duration_ms: Optional[int] = None
    compile_duration_ms: Optional[int] = None
    runner_duration_ms: Optional[int] = None
    triage_duration_ms: Optional[int] = None
    total_duration_ms: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class UiMapMetrics:
    """UI map / generation health metrics."""
    ui_map_cache_hit: Optional[bool] = None   # True | False | None if not used
    selector_aliases_missing: int = 0
    generator_blocked: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FlakeMetrics:
    """Flake / quarantine metrics accumulated in session."""
    retry_count: int = 0
    quarantined_tests_active: int = 0
    quarantine_expired_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RunMetrics:
    """Full metrics for a single run — Sprint 7 schema."""
    run_id: str
    ticket_id: Any
    lane: Optional[str]
    collected_at: str
    tool_version: str
    signal: SignalMetrics
    timing: TimeMetrics
    ui_map: UiMapMetrics
    flake: FlakeMetrics

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "ticket_id": str(self.ticket_id),
            "lane": self.lane,
            "collected_at": self.collected_at,
            "tool_version": self.tool_version,
            "signal": self.signal.to_dict(),
            "timing": self.timing.to_dict(),
            "ui_map": self.ui_map.to_dict(),
            "flake": self.flake.to_dict(),
        }


@dataclass
class AggregatedMetrics:
    """Aggregated across multiple runs."""
    period_days: int
    total_runs: int
    pass_rate: float
    fail_app_rate: float
    blocked_rate: float
    avg_total_duration_ms: Optional[float]
    unknown_verdict_total: int
    blocked_by_category: dict
    ui_map_cache_hit_rate: Optional[float]
    avg_retry_count: float
    quarantined_active_total: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DashboardSummary:
    """High-level dashboard summary (multi-panel)."""
    generated_at: str
    period_days: int
    run_health: dict
    generation_health: dict
    quarantine_health: dict

    def to_dict(self) -> dict:
        return asdict(self)


class MetricsCollector:
    """
    Recolecta métricas de un run completado y las persiste.

    Uso:
        mc = MetricsCollector(evidence_dir=Path("evidence/70"))
        metrics = mc.collect_run_metrics(
            run_id="uat-70-20260101-120000", ticket_id=70
        )
        mc.persist(metrics)
    """

    def __init__(
        self,
        evidence_dir: Path,
        metrics_path: Optional[Path] = None,
    ) -> None:
        self.evidence_dir = evidence_dir
        self._metrics_path = metrics_path or _METRICS_DB_PATH
        self._metrics_path.parent.mkdir(parents=True, exist_ok=True)

    # ── API ────────────────────────────────────────────────────────────────────

    def collect_run_metrics(
        self,
        run_id: str,
        ticket_id: Any,
        *,
        run_dir: Optional[Path] = None,
    ) -> dict:
        """
        Analizar el run y devolver dict de métricas.

        run_dir por defecto: evidence_dir / run_id
        """
        rd = run_dir or (self.evidence_dir / run_id)

        metrics: dict = {
            "run_id": run_id,
            "ticket_id": str(ticket_id),
            "collected_at": _utcnow(),
            "tool_version": _TOOL_VERSION,
        }

        metrics["run"] = self._collect_run_meta(rd)
        metrics["events"] = self._collect_event_stats(rd)
        metrics["playwright"] = self._collect_playwright_stats(rd)
        metrics["stages"] = self._collect_stage_stats(rd)
        metrics["learnings"] = self._collect_learning_stats(rd)
        metrics["blockers_summary"] = self._collect_blocker_stats(rd)

        return metrics

    def persist(self, metrics: dict) -> bool:
        """Agregar métricas al archivo JSONL. Devuelve True si OK."""
        try:
            with open(self._metrics_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(metrics, ensure_ascii=False) + "\n")
            return True
        except Exception as exc:
            _py_logger.warning("MetricsCollector: error persistiendo: %s", exc)
            return False

    def collect_and_persist(
        self, run_id: str, ticket_id: Any, *, run_dir: Optional[Path] = None
    ) -> dict:
        """Shortcut: collect + persist."""
        m = self.collect_run_metrics(run_id, ticket_id, run_dir=run_dir)
        self.persist(m)
        return m

    def load_all(self) -> list[dict]:
        """Cargar todas las métricas históricas."""
        if not self._metrics_path.exists():
            return []
        records = []
        try:
            with open(self._metrics_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        except Exception as exc:
            _py_logger.warning("MetricsCollector: error leyendo: %s", exc)
        return records

    def load_since(self, days: int = 7) -> list[dict]:
        """Cargar métricas de los últimos N días."""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%S")
        all_recs = self.load_all()
        return [
            r for r in all_recs
            if r.get("collected_at", "0") >= cutoff_str
        ]

    # ── Colectores privados ────────────────────────────────────────────────────

    def _collect_run_meta(self, run_dir: Path) -> dict:
        """Leer run_manifest.json y run_state.json."""
        manifest = {}
        state = {}

        manifest_path = run_dir / "run_manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        state_path = run_dir / "run_state.json"
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        return {
            "duration_ms": state.get("duration_ms") or manifest.get("duration_ms"),
            "status": state.get("status", "unknown"),
            "verdict": state.get("verdict", "UNKNOWN"),
            "mode": manifest.get("mode", "unknown"),
            "headed": manifest.get("headed", False),
            "started_at": manifest.get("started_at") or state.get("started_at"),
            "completed_at": state.get("completed_at"),
        }

    def _collect_event_stats(self, run_dir: Path) -> dict:
        """Analizar events.jsonl."""
        events_path = run_dir / "events.jsonl"
        if not events_path.exists():
            return {"total": 0, "by_level": {}, "by_category": {}, "failures": 0,
                    "blockers": 0, "playwright_actions": 0}

        total = 0
        by_level: dict[str, int] = {}
        by_category: dict[str, int] = {}
        failures = 0
        blockers = 0
        pw_actions = 0

        try:
            with open(events_path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        evt = json.loads(line)
                        total += 1
                        lvl = evt.get("level", "info")
                        by_level[lvl] = by_level.get(lvl, 0) + 1
                        cat = evt.get("category", "")
                        if cat:
                            by_category[cat] = by_category.get(cat, 0) + 1
                        if evt.get("status") == "failed":
                            failures += 1
                        if cat == "blocker":
                            blockers += 1
                        if evt.get("source") == "playwright":
                            pw_actions += 1
                    except Exception:
                        pass
        except Exception:
            pass

        return {
            "total": total,
            "by_level": by_level,
            "by_category": by_category,
            "failures": failures,
            "blockers": blockers,
            "playwright_actions": pw_actions,
        }

    def _collect_playwright_stats(self, run_dir: Path) -> dict:
        """Analizar datos de Playwright (playwright.jsonl, report)."""
        pw_dir = run_dir / "playwright"
        stats: dict = {
            "scenarios": 0,
            "pass": 0,
            "fail": 0,
            "blocked": 0,
            "assertions_total": 0,
            "assertions_pass": 0,
            "assertions_fail": 0,
            "screenshots": 0,
            "network_errors": 0,
        }

        if not pw_dir.exists():
            return stats

        # Screenshots
        if (pw_dir / "screenshots.jsonl").exists():
            try:
                with open(pw_dir / "screenshots.jsonl", encoding="utf-8") as f:
                    stats["screenshots"] = sum(1 for line in f if line.strip())
            except Exception:
                pass

        # Network errors
        if (pw_dir / "network.jsonl").exists():
            try:
                with open(pw_dir / "network.jsonl", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            rec = json.loads(line)
                            if rec.get("event_kind") == "failure":
                                stats["network_errors"] += 1
                        except Exception:
                            pass
            except Exception:
                pass

        # Assertions from actions.jsonl
        if (pw_dir / "actions.jsonl").exists():
            try:
                with open(pw_dir / "actions.jsonl", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            rec = json.loads(line)
                            if rec.get("category") == "page_assertion":
                                stats["assertions_total"] += 1
                                if rec.get("status") == "completed":
                                    stats["assertions_pass"] += 1
                                elif rec.get("status") == "failed":
                                    stats["assertions_fail"] += 1
                        except Exception:
                            pass
            except Exception:
                pass

        # Playwright JSON report
        pw_report = self.evidence_dir / ".playwright-report.json"
        if pw_report.exists():
            try:
                report = json.loads(pw_report.read_text(encoding="utf-8"))
                suites = report.get("suites", [])

                def _count_specs(suite: dict) -> tuple[int, int, int]:
                    total_pass = sum(1 for s in suite.get("specs", [])
                                     if all(r.get("status") == "passed"
                                            for r in s.get("tests", [{}])))
                    total_fail = sum(1 for s in suite.get("specs", [])
                                     if any(r.get("status") in ("failed", "timedOut")
                                            for r in s.get("tests", [{}])))
                    total_specs = len(suite.get("specs", []))
                    for sub in suite.get("suites", []):
                        p, f, t = _count_specs(sub)
                        total_pass += p
                        total_fail += f
                        total_specs += t
                    return total_pass, total_fail, total_specs

                for s in suites:
                    p, fl, t = _count_specs(s)
                    stats["pass"] += p
                    stats["fail"] += fl
                    stats["scenarios"] += t
            except Exception:
                pass

        return stats

    def _collect_stage_stats(self, run_dir: Path) -> dict:
        """Analizar checkpoints/ para determinar qué stages completaron."""
        chk_dir = run_dir / "checkpoints"
        completed: list[str] = []
        failed: list[str] = []
        blocked: list[str] = []

        if not chk_dir.exists():
            return {"completed": completed, "failed": failed, "blocked": blocked}

        for f in sorted(chk_dir.glob("*.json")):
            name = f.stem  # e.g. "01_runner.completed"
            parts = name.split(".")
            if len(parts) >= 2:
                stage_part = parts[0].split("_", 1)
                stage = stage_part[1] if len(stage_part) == 2 else parts[0]
                status = parts[-1]
                if status == "completed":
                    completed.append(stage)
                elif status == "failed":
                    failed.append(stage)
                elif status == "blocked":
                    blocked.append(stage)

        return {"completed": completed, "failed": failed, "blocked": blocked}

    def _collect_learning_stats(self, run_dir: Path) -> dict:
        """Contar candidatos de learning generados para este run."""
        try:
            from learning_store import LearningStore
            store = LearningStore()
            candidates = store.get_candidates(status="candidate")
            approved = store.get_approved()
            # Filter by run_id
            run_id = run_dir.name
            run_candidates = [c for c in candidates if c.get("run_id") == run_id]
            run_approved = [a for a in approved if a.get("run_id") == run_id]
            return {
                "candidates_generated": len(run_candidates),
                "approved": len(run_approved),
            }
        except Exception:
            return {"candidates_generated": 0, "approved": 0}

    def _collect_blocker_stats(self, run_dir: Path) -> dict:
        """Leer blockers.json."""
        blockers_path = run_dir / "blockers.json"
        if not blockers_path.exists():
            return {"total": 0, "resolved": 0, "pending": 0, "skipped": 0}
        try:
            blockers = json.loads(blockers_path.read_text(encoding="utf-8"))
            total = len(blockers)
            resolved = sum(1 for b in blockers if b.get("status") == "resolved")
            pending = sum(1 for b in blockers if b.get("status") == "pending")
            skipped = sum(1 for b in blockers if b.get("status") == "skipped")
            return {"total": total, "resolved": resolved, "pending": pending, "skipped": skipped}
        except Exception:
            return {"total": 0, "resolved": 0, "pending": 0, "skipped": 0}


# ── Sprint 7 module-level functions ───────────────────────────────────────────

def collect_run_metrics(
    execution_log: list[dict],
    run_id: str = "",
    ticket_id: Any = 0,
    lane: Optional[str] = None,
) -> RunMetrics:
    """
    Analyse a list of execution.jsonl event dicts and produce a RunMetrics.

    Parameters
    ----------
    execution_log : Events loaded from execution.jsonl (list of dicts).
    run_id        : Run identifier string.
    ticket_id     : Ticket ID (int or str).
    lane          : Active lane name (from QA_UAT_LANE env var, or None).
    """
    # ── Signal metrics ─────────────────────────────────────────────────────────
    signal = SignalMetrics()
    timing = TimeMetrics()
    ui_map = UiMapMetrics()
    flake = FlakeMetrics()

    # Stage duration tracking
    _stage_starts: dict[str, int] = {}  # stage -> epoch_ms at start

    first_failure_ms: Optional[int] = None
    run_start_ms: Optional[int] = None
    run_end_ms: Optional[int] = None

    for evt in execution_log:
        etype = evt.get("event", "")
        ts_raw = evt.get("timestamp") or evt.get("ts") or ""

        # Epoch helper
        def _ts_to_epoch_ms(ts: str) -> Optional[int]:
            if not ts:
                return None
            try:
                ts_clean = ts.replace("Z", "+00:00")
                dt = datetime.fromisoformat(ts_clean)
                return int(dt.timestamp() * 1000)
            except Exception:
                return None

        ts_ms = _ts_to_epoch_ms(ts_raw)

        # Session start / end
        if etype == "session_start":
            run_start_ms = ts_ms
        elif etype == "session_end":
            run_end_ms = ts_ms

        # Stage start / end for timing
        elif etype == "stage_start":
            stage_name = evt.get("stage", "")
            if ts_ms:
                _stage_starts[stage_name] = ts_ms
        elif etype == "stage_end":
            stage_name = evt.get("stage", "")
            dur = evt.get("duration_ms")
            if dur is not None:
                dur = int(dur)
                if stage_name in ("environment_preflight", "preflight"):
                    timing.preflight_duration_ms = dur
                elif stage_name in ("compiler", "uat_scenario_compiler"):
                    timing.compile_duration_ms = dur
                elif stage_name == "runner":
                    timing.runner_duration_ms = dur
                elif stage_name == "triage":
                    timing.triage_duration_ms = dur

        # Verdict signals
        elif etype == "pipeline_verdict_decision":
            verdict = evt.get("verdict", "")
            category = evt.get("category") or ""
            reason = evt.get("reason") or ""

            if verdict == "UNKNOWN" or verdict == "":
                signal.unknown_verdict_count += 1
            elif verdict == "PASS":
                signal.pass_count += 1
            elif verdict == "SKIPPED":
                signal.skipped_count += 1
            elif verdict in ("BLOCKED", "FAIL", "MIXED"):
                if verdict == "FAIL" and category == "APP":
                    signal.fail_app_count += 1
                elif verdict == "BLOCKED":
                    if not reason:
                        signal.blocked_without_reason_count += 1
                    if category in signal.blocked_by_category:
                        signal.blocked_by_category[category] += 1
                    # Track time to first actionable failure
                    if first_failure_ms is None and ts_ms:
                        first_failure_ms = ts_ms

        # Runner summary
        elif etype == "runner_summary":
            v = evt.get("verdict", "")
            cat = evt.get("category") or ""
            if v == "PASS":
                signal.pass_count += 1
            elif v == "FAIL" and cat == "APP":
                signal.fail_app_count += 1
            elif v in ("BLOCKED", "MIXED"):
                if cat in signal.blocked_by_category:
                    signal.blocked_by_category[cat] += 1

            # Retry count
            retries = evt.get("retries") or 0
            flake.retry_count += int(retries)

            # Duration
            dur = evt.get("duration_ms")
            if dur is not None and timing.runner_duration_ms is None:
                timing.runner_duration_ms = int(dur)

        # UI map cache
        elif etype == "ui_map_cache_result":
            hit = evt.get("cache_hit")
            if hit is not None:
                # Use AND logic: if ANY cache miss, mark false
                if ui_map.ui_map_cache_hit is None:
                    ui_map.ui_map_cache_hit = bool(hit)
                else:
                    ui_map.ui_map_cache_hit = ui_map.ui_map_cache_hit and bool(hit)

        # Selector contract violations
        elif etype == "selector_contract_validation":
            if evt.get("status") == "BLOCKED":
                reason = evt.get("reason", "")
                if "ALIAS_NOT_IN_UI_MAP" in reason:
                    ui_map.selector_aliases_missing += 1

        # Generator blocked
        elif etype == "stage_end" and evt.get("stage") == "generator":
            if not evt.get("ok", True):
                ui_map.generator_blocked = True

        # Retry decisions
        elif etype == "retry_decision":
            flake.retry_count += 1

    # Compute total duration
    if run_start_ms and run_end_ms:
        timing.total_duration_ms = run_end_ms - run_start_ms

    # Compute time_to_first_actionable_failure
    if first_failure_ms and run_start_ms:
        timing.time_to_first_actionable_failure_ms = first_failure_ms - run_start_ms

    # Quarantine info from registry (non-fatal)
    try:
        from quarantine_registry import get_registry
        reg = get_registry()
        active = reg.get_active_quarantines()
        flake.quarantined_tests_active = len(active)
        expired = reg.expire_old_quarantines()
        flake.quarantine_expired_count = len(expired)
    except Exception:
        pass

    return RunMetrics(
        run_id=run_id,
        ticket_id=ticket_id,
        lane=lane,
        collected_at=_utcnow(),
        tool_version=_TOOL_VERSION,
        signal=signal,
        timing=timing,
        ui_map=ui_map,
        flake=flake,
    )


def aggregate_metrics(runs: list[RunMetrics]) -> AggregatedMetrics:
    """Aggregate a list of RunMetrics into AggregatedMetrics."""
    n = len(runs)
    if n == 0:
        return AggregatedMetrics(
            period_days=0, total_runs=0, pass_rate=0.0, fail_app_rate=0.0,
            blocked_rate=0.0, avg_total_duration_ms=None, unknown_verdict_total=0,
            blocked_by_category={c: 0 for c in _VALID_CATEGORIES},
            ui_map_cache_hit_rate=None, avg_retry_count=0.0,
            quarantined_active_total=0,
        )

    pass_total = sum(r.signal.pass_count for r in runs)
    fail_app_total = sum(r.signal.fail_app_count for r in runs)
    blocked_total = sum(sum(r.signal.blocked_by_category.values()) for r in runs)
    unknown_total = sum(r.signal.unknown_verdict_count for r in runs)
    retry_total = sum(r.flake.retry_count for r in runs)
    quarantine_total = sum(r.flake.quarantined_tests_active for r in runs)

    # Aggregate blocked_by_category
    agg_blocked: dict[str, int] = {c: 0 for c in _VALID_CATEGORIES}
    for r in runs:
        for cat, cnt in r.signal.blocked_by_category.items():
            agg_blocked[cat] = agg_blocked.get(cat, 0) + cnt

    # Duration average
    durations = [r.timing.total_duration_ms for r in runs if r.timing.total_duration_ms is not None]
    avg_dur = sum(durations) / len(durations) if durations else None

    # UI map cache hit rate
    cache_hits = [r.ui_map.ui_map_cache_hit for r in runs if r.ui_map.ui_map_cache_hit is not None]
    cache_hit_rate = sum(1 for h in cache_hits if h) / len(cache_hits) if cache_hits else None

    # Rates (against total runs as denominator — one run = one pipeline verdict)
    pass_rate = pass_total / n if n else 0.0
    fail_app_rate = fail_app_total / n if n else 0.0
    blocked_rate = blocked_total / n if n else 0.0

    return AggregatedMetrics(
        period_days=0,  # caller sets this
        total_runs=n,
        pass_rate=round(pass_rate, 3),
        fail_app_rate=round(fail_app_rate, 3),
        blocked_rate=round(blocked_rate, 3),
        avg_total_duration_ms=round(avg_dur, 1) if avg_dur is not None else None,
        unknown_verdict_total=unknown_total,
        blocked_by_category=agg_blocked,
        ui_map_cache_hit_rate=round(cache_hit_rate, 3) if cache_hit_rate is not None else None,
        avg_retry_count=round(retry_total / n, 2) if n else 0.0,
        quarantined_active_total=quarantine_total,
    )


def get_dashboard_summary(
    since_days: int = 7,
    metrics_path: Optional[Path] = None,
) -> DashboardSummary:
    """
    Build a DashboardSummary from persisted sprint-7 RunMetrics JSONL.
    Falls back to legacy metrics.jsonl format for backwards compatibility.
    """
    path = metrics_path or (Path(__file__).parent / "data" / "run_metrics.jsonl")
    legacy_path = Path(__file__).parent / "data" / "metrics.jsonl"
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%S")

    run_metrics_list: list[RunMetrics] = []

    # Load sprint-7 run_metrics.jsonl
    for p in (path, legacy_path):
        if p.exists():
            try:
                with open(p, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                            if rec.get("collected_at", "0") < cutoff_str:
                                continue
                            # Sprint 7 format has 'signal'/'timing'/'ui_map'/'flake'
                            if "signal" in rec:
                                sig = rec["signal"]
                                tim = rec.get("timing", {})
                                ui = rec.get("ui_map", {})
                                fl = rec.get("flake", {})
                                rm = RunMetrics(
                                    run_id=rec.get("run_id", ""),
                                    ticket_id=rec.get("ticket_id", 0),
                                    lane=rec.get("lane"),
                                    collected_at=rec.get("collected_at", ""),
                                    tool_version=rec.get("tool_version", ""),
                                    signal=SignalMetrics(
                                        unknown_verdict_count=sig.get("unknown_verdict_count", 0),
                                        blocked_without_reason_count=sig.get("blocked_without_reason_count", 0),
                                        blocked_by_category=sig.get("blocked_by_category", {c: 0 for c in _VALID_CATEGORIES}),
                                        fail_app_count=sig.get("fail_app_count", 0),
                                        pass_count=sig.get("pass_count", 0),
                                        skipped_count=sig.get("skipped_count", 0),
                                    ),
                                    timing=TimeMetrics(**{k: tim.get(k) for k in TimeMetrics.__dataclass_fields__}),
                                    ui_map=UiMapMetrics(**{k: ui.get(k) for k in UiMapMetrics.__dataclass_fields__}),
                                    flake=FlakeMetrics(**{k: fl.get(k) for k in FlakeMetrics.__dataclass_fields__}),
                                )
                                run_metrics_list.append(rm)
                        except Exception:
                            pass
            except Exception:
                pass
        if run_metrics_list:
            break

    agg = aggregate_metrics(run_metrics_list)
    agg.period_days = since_days

    # ── Run health panel ───────────────────────────────────────────────────────
    n = agg.total_runs
    pass_t = sum(r.signal.pass_count for r in run_metrics_list)
    fail_t = sum(r.signal.fail_app_count for r in run_metrics_list)
    blocked_t = sum(sum(r.signal.blocked_by_category.values()) for r in run_metrics_list)
    skipped_t = sum(r.signal.skipped_count for r in run_metrics_list)
    unknown_t = agg.unknown_verdict_total

    run_health = {
        "panel": "run_health",
        "period_days": since_days,
        "total_runs": n,
        "pass": pass_t,
        "fail_app": fail_t,
        "blocked": blocked_t,
        "mixed": max(0, n - pass_t - fail_t - blocked_t - skipped_t - unknown_t),
        "skipped": skipped_t,
        "unknown": unknown_t,
        "blocked_by_category": agg.blocked_by_category,
    }

    # ── Generation health panel ────────────────────────────────────────────────
    cache_hits = [r.ui_map.ui_map_cache_hit for r in run_metrics_list if r.ui_map.ui_map_cache_hit is not None]
    cache_hit_rate = sum(1 for h in cache_hits if h) / len(cache_hits) if cache_hits else 0.0
    stale_misses = sum(1 for h in cache_hits if not h)
    stale_rate = stale_misses / len(cache_hits) if cache_hits else 0.0
    alias_missing = sum(r.ui_map.selector_aliases_missing for r in run_metrics_list)
    alias_missing_rate = alias_missing / n if n else 0.0

    generation_health = {
        "panel": "generation_health",
        "ui_map_cache_hit_rate": round(cache_hit_rate, 3),
        "ui_map_stale_rate": round(stale_rate, 3),
        "selector_alias_missing_rate": round(alias_missing_rate, 3),
        "screens_without_ui_map": [],  # populated by dashboard_builder which reads ui_maps dir
    }

    # ── Quarantine health panel ────────────────────────────────────────────────
    quarantine_health = {
        "panel": "quarantine_health",
        "active_quarantines": 0,
        "expired_unresolved": 0,
        "oldest_quarantine_days": None,
    }
    try:
        from quarantine_registry import get_registry
        summary = get_registry().get_quarantine_summary()
        quarantine_health["active_quarantines"] = summary.active_count
        quarantine_health["expired_unresolved"] = summary.expired_unresolved_count
        quarantine_health["oldest_quarantine_days"] = summary.oldest_active_days
    except Exception:
        pass

    return DashboardSummary(
        generated_at=_utcnow(),
        period_days=since_days,
        run_health=run_health,
        generation_health=generation_health,
        quarantine_health=quarantine_health,
    )


def build_run_metrics_summary_event(run_metrics: RunMetrics) -> dict:
    """
    Build the execution.jsonl event for run_metrics_summary.
    Called at the end of the pipeline.
    """
    return {
        "event": "run_metrics_summary",
        "run_id": run_metrics.run_id,
        "ticket_id": str(run_metrics.ticket_id),
        "lane": run_metrics.lane,
        "unknown_count": run_metrics.signal.unknown_verdict_count,
        "blocked_by_category": run_metrics.signal.blocked_by_category,
        "fail_app_count": run_metrics.signal.fail_app_count,
        "pass_count": run_metrics.signal.pass_count,
        "total_duration_ms": run_metrics.timing.total_duration_ms,
        "ui_map_cache_hit": run_metrics.ui_map.ui_map_cache_hit,
        "retry_count": run_metrics.flake.retry_count,
        "quarantined_tests_active": run_metrics.flake.quarantined_tests_active,
    }


def persist_run_metrics(
    run_metrics: RunMetrics,
    path: Optional[Path] = None,
) -> bool:
    """Append RunMetrics to run_metrics.jsonl. Returns True if OK."""
    target = path or (Path(__file__).parent / "data" / "run_metrics.jsonl")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as f:
            f.write(json.dumps(run_metrics.to_dict(), ensure_ascii=False) + "\n")
        return True
    except Exception as exc:
        _py_logger.warning("persist_run_metrics: error: %s", exc)
        return False
