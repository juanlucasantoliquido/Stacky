"""
replay_run.py — Reproductor forense de runs QA UAT.

Lee el events.jsonl de un run y genera una narración estructurada
(replay report) que permite entender exactamente qué pasó, en qué orden,
cuánto tardó cada stage, qué errores ocurrieron y dónde está la evidencia.

El replay NO re-ejecuta Playwright ni el pipeline. Es una reconstrucción
puramente analítica del event log.

SALIDA:
{
  "ok": true,
  "run_id": "uat-70-...",
  "ticket_id": 70,
  "replay_at": "...",
  "run_meta": {...},           // de run_manifest.json
  "run_state": {...},          // de run_state.json
  "timeline": [                // eventos en orden cronológico
    {
      "seq": 1,
      "ts": "...",
      "event_type": "run.started",
      "stage": "init",
      "status": "completed",
      "message": "..."
    },
    ...
  ],
  "stages": {                  // resumen por stage
    "reader": {
      "started_at": "...",
      "completed_at": "...",
      "duration_ms": 1234,
      "status": "completed",
      "event_count": 5
    },
    ...
  },
  "errors": [                  // todos los eventos con status=failed o level=error
    {...}
  ],
  "blockers": [...],           // de blockers.json
  "artifacts": [...],          // de artifacts/_registry.json
  "checkpoints": [...],        // de checkpoints/*.json
  "learning_candidates": [...],// de learning_store para este run
  "total_events": 142,
  "total_duration_ms": 12345
}
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_py_logger = logging.getLogger("stacky.qa_uat.replay_run")


class ReplayRun:
    """
    Genera un replay report de un run a partir de su event log.

    Uso:
        rr = ReplayRun(run_id="uat-70-...", run_dir=Path("evidence/70/uat-70-..."))
        report = rr.replay()
        print(json.dumps(report, indent=2, ensure_ascii=False))
    """

    def __init__(self, run_id: str, run_dir: Path) -> None:
        self.run_id = run_id
        self.run_dir = run_dir

    def replay(self) -> dict:
        """Generar el replay report completo."""
        events = self._load_events()
        manifest = self._load_json(self.run_dir / "run_manifest.json")
        state = self._load_json(self.run_dir / "run_state.json")
        blockers = self._load_json_list(self.run_dir / "blockers.json")
        artifacts = self._load_json_list(self.run_dir / "artifacts" / "_registry.json")
        checkpoints = self._load_checkpoints()

        timeline = self._build_timeline(events)
        stages = self._build_stage_summaries(events, checkpoints)
        errors = self._extract_errors(events)
        learning_candidates = self._load_learning_candidates()

        # Total duration
        total_duration_ms = state.get("duration_ms") if state else None
        if total_duration_ms is None and timeline:
            first_ts = timeline[0].get("ts", "")
            last_ts = timeline[-1].get("ts", "")
            if first_ts and last_ts:
                try:
                    t0 = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
                    t1 = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                    total_duration_ms = int((t1 - t0).total_seconds() * 1000)
                except Exception:
                    pass

        return {
            "ok": True,
            "run_id": self.run_id,
            "ticket_id": (manifest or state or {}).get("ticket_id"),
            "replay_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "run_meta": manifest or {},
            "run_state": state or {},
            "timeline": timeline,
            "stages": stages,
            "errors": errors,
            "blockers": blockers,
            "artifacts": artifacts,
            "checkpoints": checkpoints,
            "learning_candidates": learning_candidates,
            "total_events": len(events),
            "total_duration_ms": total_duration_ms,
        }

    # ── Loaders ────────────────────────────────────────────────────────────────

    def _load_events(self) -> list[dict]:
        events_path = self.run_dir / "events.jsonl"
        if not events_path.exists():
            return []
        events = []
        try:
            with open(events_path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        except Exception as exc:
            _py_logger.warning("ReplayRun: error leyendo events: %s", exc)
        return events

    def _load_json(self, path: Path) -> Optional[dict]:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _load_json_list(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _load_checkpoints(self) -> list[dict]:
        chk_dir = self.run_dir / "checkpoints"
        if not chk_dir.exists():
            return []
        checkpoints = []
        for f in sorted(chk_dir.glob("*.json")):
            try:
                checkpoints.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                pass
        return checkpoints

    def _load_learning_candidates(self) -> list[dict]:
        try:
            from learning_store import LearningStore
            store = LearningStore()
            all_candidates = store.get_candidates(status="candidate")
            approved = store.get_approved()
            run_candidates = [
                c for c in (all_candidates + approved)
                if c.get("run_id") == self.run_id
            ]
            return run_candidates
        except Exception:
            return []

    # ── Builders ───────────────────────────────────────────────────────────────

    def _build_timeline(self, events: list[dict]) -> list[dict]:
        """
        Construir timeline simplificado: campos clave de cada evento,
        ordenado por seq_run.
        """
        timeline = []
        for evt in sorted(events, key=lambda e: e.get("seq_run", 0)):
            timeline.append({
                "seq": evt.get("seq_run"),
                "ts": evt.get("ts"),
                "event_type": evt.get("event_type"),
                "event_id": evt.get("event_id"),
                "stage": evt.get("stage"),
                "action": evt.get("action"),
                "status": evt.get("status"),
                "level": evt.get("level"),
                "message": evt.get("message"),
                "source": evt.get("source"),
                "duration_ms": evt.get("duration_ms"),
            })
        return timeline

    def _build_stage_summaries(
        self, events: list[dict], checkpoints: list[dict]
    ) -> dict:
        """Resumir cada stage: tiempo, estado, conteo de eventos."""
        stages: dict[str, dict] = {}

        # Inicializar desde eventos stage.started
        for evt in events:
            et = evt.get("event_type", "")
            stage = evt.get("stage", "")
            if not stage:
                continue

            if stage not in stages:
                stages[stage] = {
                    "started_at": None,
                    "completed_at": None,
                    "duration_ms": None,
                    "status": "unknown",
                    "event_count": 0,
                    "error_count": 0,
                }

            stages[stage]["event_count"] += 1

            if evt.get("level") == "error" or evt.get("status") == "failed":
                stages[stage]["error_count"] += 1

            if "stage.started" in et or "stage_started" in et:
                stages[stage]["started_at"] = evt.get("ts")
            elif "stage.completed" in et or "stage_completed" in et:
                stages[stage]["completed_at"] = evt.get("ts")
                stages[stage]["status"] = "completed"
                if evt.get("duration_ms"):
                    stages[stage]["duration_ms"] = evt.get("duration_ms")
            elif "stage.failed" in et or "stage_failed" in et:
                stages[stage]["completed_at"] = evt.get("ts")
                stages[stage]["status"] = "failed"
            elif "stage.blocked" in et or "stage_blocked" in et:
                stages[stage]["completed_at"] = evt.get("ts")
                stages[stage]["status"] = "blocked"

        # Calcular duration_ms desde timestamps donde no viene en evento
        for stage_data in stages.values():
            if stage_data["duration_ms"] is None and stage_data["started_at"] and stage_data["completed_at"]:
                try:
                    t0 = datetime.fromisoformat(stage_data["started_at"].replace("Z", "+00:00"))
                    t1 = datetime.fromisoformat(stage_data["completed_at"].replace("Z", "+00:00"))
                    stage_data["duration_ms"] = int((t1 - t0).total_seconds() * 1000)
                except Exception:
                    pass

        return stages

    def _extract_errors(self, events: list[dict]) -> list[dict]:
        """Extraer todos los eventos con status=failed o level=error."""
        errors = []
        for evt in events:
            if evt.get("status") == "failed" or evt.get("level") == "error":
                errors.append({
                    "seq": evt.get("seq_run"),
                    "ts": evt.get("ts"),
                    "event_type": evt.get("event_type"),
                    "event_id": evt.get("event_id"),
                    "stage": evt.get("stage"),
                    "message": evt.get("message"),
                    "error": (evt.get("payload") or {}).get("error"),
                    "source": evt.get("source"),
                })
        return errors


# ── CLI entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    p = argparse.ArgumentParser(
        description="Replay forense de un run QA UAT",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument("--run-id", required=True, help="Run ID (uat-70-...)")
    p.add_argument(
        "--run-dir",
        help="Directorio del run (default: evidence/<ticket_part>/<run_id>)",
    )
    p.add_argument(
        "--ticket",
        help="Ticket ID (para resolver run-dir por defecto)",
    )
    p.add_argument(
        "--output",
        help="Path para guardar el replay report JSON (default: stdout)",
    )

    args = p.parse_args()

    if args.run_dir:
        run_dir = Path(args.run_dir)
    elif args.ticket:
        # evidence/<ticket>/<run_id>/
        run_dir = Path(__file__).parent / "evidence" / str(args.ticket) / args.run_id
    else:
        # Intentar inferir del run_id: uat-70-...
        parts = args.run_id.split("-")
        ticket_guess = parts[1] if len(parts) > 1 else "0"
        run_dir = Path(__file__).parent / "evidence" / ticket_guess / args.run_id

    if not run_dir.exists():
        print(json.dumps({"ok": False, "error": f"run_dir no existe: {run_dir}"}, indent=2))
        sys.exit(1)

    rr = ReplayRun(run_id=args.run_id, run_dir=run_dir)
    report = rr.replay()

    output_str = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(output_str, encoding="utf-8")
        print(f"Replay report guardado en: {args.output}", file=sys.stderr)
    else:
        print(output_str)
