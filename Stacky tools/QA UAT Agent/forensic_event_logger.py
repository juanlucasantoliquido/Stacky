"""
event_logger.py (forense) — Logger canónico de eventos para QA UAT Agent.

NOTA: Este módulo es DISTINTO de execution_logger.py (que sigue existiendo
para compatibilidad con el pipeline existente). Este nuevo EventLogger
implementa el esquema universal v1.0 con persistencia dual SQLite + JSONL,
redacción de secretos, y patrón intent → completed/failed/blocked.

USO BÁSICO:
    from forensic_event_logger import ForensicEventLogger, make_run_id

    run_id = make_run_id(ticket_id=70)
    run_dir = Path("evidence/70") / run_id
    log = ForensicEventLogger(run_id=run_id, ticket_id=70, run_dir=run_dir)

    # Emitir eventos
    log.emit_run_started({"mode": "dry-run"})
    log.emit_stage_started("reader")
    log.emit_stage_completed("reader", {"scenarios": 3})
    log.emit_run_completed({"verdict": "PASS"})
    log.close()

USO COMO CONTEXT MANAGER:
    with ForensicEventLogger(run_id, ticket_id=70, run_dir=run_dir) as log:
        log.emit_stage_started("reader")
        ...
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from event_schema import build_event, SCHEMA_VERSION
from event_store import EventStore, EventStoreFactory
from redactor import redact_dict, redact_text

import logging

_py_logger = logging.getLogger("stacky.qa_uat.forensic_event_logger")


def make_run_id(ticket_id: Any, prefix: str = "uat") -> str:
    """Genera run_id canónico: uat-<ticket>-<YYYYMMDD>-<HHMMSS>"""
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{ticket_id}-{ts}"


def make_trace_id(run_id: str) -> str:
    return f"trace-{run_id}"


# ── ForensicEventLogger ────────────────────────────────────────────────────────

class ForensicEventLogger:
    """
    Logger de eventos forenses para un run de QA UAT.

    - Thread-safe.
    - Nunca lanza al exterior.
    - Todo evento cumple el esquema universal v1.0.
    - Redacta secretos automáticamente.
    - Persiste dual: SQLite + JSONL via EventStore.
    """

    def __init__(
        self,
        run_id: str,
        ticket_id: Any,
        run_dir: Path,
        *,
        store: Optional[EventStore] = None,
    ) -> None:
        self.run_id = run_id
        self.ticket_id = ticket_id
        self.run_dir = run_dir
        self.trace_id = make_trace_id(run_id)
        self._seq = 0
        self._seq_lock = threading.Lock()
        self._store = store or EventStoreFactory.get(run_dir)
        self._last_event_id: Optional[str] = None
        self._stage_start_events: dict[str, str] = {}  # stage → event_id

    # ── Seq ───────────────────────────────────────────────────────────────────

    def _next_seq(self) -> int:
        with self._seq_lock:
            self._seq += 1
            return self._seq

    # ── Core emit ─────────────────────────────────────────────────────────────

    def emit(
        self,
        *,
        source: str,
        event_type: str,
        category: str,
        stage: str,
        action: str,
        status: str,
        level: str = "info",
        message: str,
        payload: Optional[dict] = None,
        artifact_refs: Optional[list] = None,
        learning_eligible: bool = False,
        span_id: Optional[str] = None,
        parent_event_id: Optional[str] = None,
        causation_event_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        redact_payload: bool = True,
    ) -> Optional[str]:
        """
        Emitir un evento canónico.

        Devuelve event_id si fue persistido, None si falló.
        """
        try:
            # Redactar payload antes de persistir
            clean_payload = payload or {}
            redacted_fields: list[str] = []
            redaction_applied = False
            if redact_payload and clean_payload:
                clean_payload, redacted_fields, redaction_applied = redact_dict(clean_payload)

            seq = self._next_seq()
            event = build_event(
                run_id=self.run_id,
                ticket_id=self.ticket_id,
                trace_id=self.trace_id,
                seq_run=seq,
                source=source,
                event_type=event_type,
                category=category,
                stage=stage,
                action=action,
                status=status,
                level=level,
                message=message,
                payload=clean_payload,
                artifact_refs=artifact_refs or [],
                learning_eligible=learning_eligible,
                span_id=span_id,
                parent_event_id=parent_event_id or self._last_event_id,
                causation_event_id=causation_event_id,
                correlation_id=correlation_id,
                duration_ms=duration_ms,
                redaction_applied=redaction_applied,
                redacted_fields=redacted_fields,
            )

            ok = self._store.write_event(event)
            if ok:
                self._last_event_id = event["event_id"]
                return event["event_id"]
            else:
                _py_logger.error(
                    "ForensicEventLogger: persistencia fallida para evento %s — run DEBE bloquearse",
                    event_type,
                )
                return None
        except Exception as exc:
            _py_logger.error("ForensicEventLogger.emit error: %s", exc, exc_info=True)
            return None

    # ── Helpers de lifecycle ──────────────────────────────────────────────────

    def emit_run_started(self, payload: Optional[dict] = None) -> Optional[str]:
        return self.emit(
            source="pipeline",
            event_type="run.started",
            category="run_started",
            stage="run",
            action="run_started",
            status="started",
            message=f"Run {self.run_id} iniciado",
            payload=payload,
        )

    def emit_run_completed(self, payload: Optional[dict] = None) -> Optional[str]:
        return self.emit(
            source="pipeline",
            event_type="run.completed",
            category="run_completed",
            stage="run",
            action="run_completed",
            status="completed",
            message=f"Run {self.run_id} completado",
            payload=payload,
        )

    def emit_run_blocked(self, reason: str, message: str, payload: Optional[dict] = None) -> Optional[str]:
        return self.emit(
            source="pipeline",
            event_type="run.blocked",
            category="run_blocked",
            stage="run",
            action="run_blocked",
            status="blocked",
            level="warning",
            message=message,
            payload={"reason": reason, **(payload or {})},
        )

    def emit_run_failed(self, reason: str, message: str, payload: Optional[dict] = None) -> Optional[str]:
        return self.emit(
            source="pipeline",
            event_type="run.failed",
            category="run_failed",
            stage="run",
            action="run_failed",
            status="failed",
            level="error",
            message=message,
            payload={"reason": reason, **(payload or {})},
        )

    # ── Stage events ──────────────────────────────────────────────────────────

    def emit_stage_started(self, stage: str, payload: Optional[dict] = None) -> Optional[str]:
        eid = self.emit(
            source="pipeline",
            event_type="stage.started",
            category="stage_started",
            stage=stage,
            action="stage_started",
            status="started",
            message=f"Stage '{stage}' iniciado",
            payload=payload,
        )
        if eid:
            self._stage_start_events[stage] = eid
        return eid

    def emit_stage_completed(self, stage: str, payload: Optional[dict] = None,
                             duration_ms: Optional[int] = None) -> Optional[str]:
        start_eid = self._stage_start_events.get(stage)
        return self.emit(
            source="pipeline",
            event_type="stage.completed",
            category="stage_completed",
            stage=stage,
            action="stage_completed",
            status="completed",
            message=f"Stage '{stage}' completado",
            payload=payload,
            duration_ms=duration_ms,
            causation_event_id=start_eid,
        )

    def emit_stage_failed(self, stage: str, reason: str,
                          payload: Optional[dict] = None, duration_ms: Optional[int] = None) -> Optional[str]:
        start_eid = self._stage_start_events.get(stage)
        return self.emit(
            source="pipeline",
            event_type="stage.failed",
            category="stage_failed",
            stage=stage,
            action="stage_failed",
            status="failed",
            level="error",
            message=f"Stage '{stage}' falló: {reason}",
            payload={"reason": reason, **(payload or {})},
            duration_ms=duration_ms,
            causation_event_id=start_eid,
        )

    def emit_stage_blocked(self, stage: str, reason: str,
                           payload: Optional[dict] = None) -> Optional[str]:
        start_eid = self._stage_start_events.get(stage)
        return self.emit(
            source="pipeline",
            event_type="stage.blocked",
            category="stage_blocked",
            stage=stage,
            action="stage_blocked",
            status="blocked",
            level="warning",
            message=f"Stage '{stage}' bloqueado: {reason}",
            payload={"reason": reason, **(payload or {})},
            causation_event_id=start_eid,
        )

    # ── Decision / info ───────────────────────────────────────────────────────

    def emit_decision(self, stage: str, action: str, message: str,
                      payload: Optional[dict] = None,
                      learning_eligible: bool = False) -> Optional[str]:
        return self.emit(
            source="agent",
            event_type=f"decision.{action}",
            category="decision",
            stage=stage,
            action=action,
            status="completed",
            message=message,
            payload=payload,
            learning_eligible=learning_eligible,
        )

    def emit_info(self, stage: str, message: str, payload: Optional[dict] = None) -> Optional[str]:
        return self.emit(
            source="agent",
            event_type="info",
            category="info",
            stage=stage,
            action="info",
            status="ok",
            message=message,
            payload=payload,
        )

    def emit_warning(self, stage: str, message: str, payload: Optional[dict] = None) -> Optional[str]:
        return self.emit(
            source="agent",
            event_type="warning",
            category="warning",
            stage=stage,
            action="warning",
            status="ok",
            level="warning",
            message=message,
            payload=payload,
        )

    def emit_error(self, stage: str, message: str, error: Optional[str] = None,
                   payload: Optional[dict] = None) -> Optional[str]:
        p = payload or {}
        if error:
            p["error"] = error
        return self.emit(
            source="agent",
            event_type="error",
            category="error",
            stage=stage,
            action="error",
            status="failed",
            level="error",
            message=message,
            payload=p,
        )

    # ── File events ───────────────────────────────────────────────────────────

    def emit_file_read(self, stage: str, path: str, size_bytes: Optional[int] = None) -> Optional[str]:
        return self.emit(
            source="filesystem",
            event_type="file.read",
            category="file_read",
            stage=stage,
            action="file_read",
            status="completed",
            message=f"Archivo leído: {path}",
            payload={"path": path, "size_bytes": size_bytes},
        )

    def emit_file_written(self, stage: str, path: str, size_bytes: Optional[int] = None,
                          artifact_refs: Optional[list] = None) -> Optional[str]:
        return self.emit(
            source="filesystem",
            event_type="file.written",
            category="file_written",
            stage=stage,
            action="file_written",
            status="completed",
            message=f"Archivo escrito: {path}",
            payload={"path": path, "size_bytes": size_bytes},
            artifact_refs=artifact_refs,
        )

    def emit_file_missing(self, stage: str, path: str) -> Optional[str]:
        return self.emit(
            source="filesystem",
            event_type="file.missing",
            category="file_missing",
            stage=stage,
            action="file_missing",
            status="failed",
            level="warning",
            message=f"Archivo no encontrado: {path}",
            payload={"path": path},
        )

    # ── Artifact event ────────────────────────────────────────────────────────

    def emit_artifact_created(self, stage: str, artifact_id: str, artifact_type: str,
                               path: str, sha256: Optional[str] = None,
                               size_bytes: Optional[int] = None,
                               scenario_id: Optional[str] = None) -> Optional[str]:
        return self.emit(
            source="filesystem",
            event_type="artifact.created",
            category="artifact_created",
            stage=stage,
            action="artifact_created",
            status="completed",
            message=f"Artifact creado: {artifact_type} → {path}",
            payload={
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
                "path": path,
                "sha256": sha256,
                "size_bytes": size_bytes,
                "scenario_id": scenario_id,
            },
            artifact_refs=[artifact_id],
        )

    # ── Metric event ──────────────────────────────────────────────────────────

    def emit_metric(self, stage: str, name: str, value: Any,
                    unit: Optional[str] = None, payload: Optional[dict] = None) -> Optional[str]:
        return self.emit(
            source="metrics",
            event_type=f"metric.{name}",
            category="metric",
            stage=stage,
            action=f"metric.{name}",
            status="completed",
            message=f"Métrica: {name} = {value}",
            payload={"name": name, "value": value, "unit": unit, **(payload or {})},
        )

    # ── Verdict ───────────────────────────────────────────────────────────────

    def emit_verdict(self, stage: str, verdict: str, reason: Optional[str] = None,
                     payload: Optional[dict] = None) -> Optional[str]:
        return self.emit(
            source="pipeline",
            event_type=f"verdict.{verdict.lower()}",
            category="verdict",
            stage=stage,
            action="verdict",
            status="completed",
            level="info" if verdict in ("PASS", "OK") else "warning",
            message=f"Veredicto: {verdict}" + (f" — {reason}" if reason else ""),
            payload={"verdict": verdict, "reason": reason, **(payload or {})},
        )

    # ── Convenience: stage context manager ────────────────────────────────────

    def stage(self, stage_name: str, payload: Optional[dict] = None):
        """Context manager que emite stage.started + stage.completed/failed automáticamente."""
        return _StageContext(self, stage_name, payload)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def flush(self) -> None:
        self._store.flush()

    def close(self) -> None:
        self._store.flush()

    def __enter__(self) -> "ForensicEventLogger":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            self.emit_error("run", f"Excepción no manejada: {exc_val}", error=str(exc_val))
        self.close()


class _StageContext:
    def __init__(self, log: ForensicEventLogger, stage_name: str, payload: Optional[dict]) -> None:
        self._log = log
        self._stage = stage_name
        self._payload = payload
        self._t0: float = 0.0

    def __enter__(self) -> "_StageContext":
        self._t0 = time.monotonic()
        self._log.emit_stage_started(self._stage, self._payload)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        duration_ms = int((time.monotonic() - self._t0) * 1000)
        if exc_type is None:
            self._log.emit_stage_completed(self._stage, duration_ms=duration_ms)
        else:
            self._log.emit_stage_failed(
                self._stage,
                reason=str(exc_val),
                payload={"exception_type": exc_type.__name__ if exc_type else ""},
                duration_ms=duration_ms,
            )
        # No suppress exception
