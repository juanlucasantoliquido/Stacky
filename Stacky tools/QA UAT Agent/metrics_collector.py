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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_py_logger = logging.getLogger("stacky.qa_uat.metrics_collector")

_METRICS_DB_PATH = Path(__file__).parent / "data" / "metrics.jsonl"
_TOOL_VERSION = "1.0.0"


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


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
