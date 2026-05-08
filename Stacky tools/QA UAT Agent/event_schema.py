"""
event_schema.py — Esquema universal de eventos para QA UAT Agent.

Define el contrato canónico de todos los eventos del sistema:
  - Campos obligatorios
  - Fuentes permitidas
  - Categorías permitidas
  - Tipos de evento permitidos
  - Función de construcción de evento válido

Principio: si no está registrado, no ocurrió.
           si no puede registrarse, no debe ejecutarse.

Schema version: 1.0
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

# ── Versión del esquema ────────────────────────────────────────────────────────

SCHEMA_VERSION = "1.0"

# ── Fuentes permitidas ─────────────────────────────────────────────────────────

ALLOWED_SOURCES = frozenset({
    "agent",
    "pipeline",
    "python",
    "powershell",
    "subprocess",
    "playwright",
    "browser_console",
    "browser_network",
    "ado_cli",
    "db",
    "filesystem",
    "human",
    "learning",
    "metrics",
    "analytics",
    "experiment",
    "anomaly",
})

# ── Categorías de eventos permitidas ──────────────────────────────────────────

ALLOWED_CATEGORIES = frozenset({
    "stage_started",
    "stage_completed",
    "stage_failed",
    "stage_blocked",
    "command_started",
    "command_stdout",
    "command_stderr",
    "command_completed",
    "decision",
    "file_read",
    "file_written",
    "file_missing",
    "file_parse_failed",
    "browser_launch",
    "browser_close",
    "page_goto",
    "page_click",
    "page_fill",
    "page_select",
    "page_wait",
    "page_assertion",
    "page_screenshot",
    "network_request",
    "network_response",
    "console_log",
    "human_question",
    "human_answer",
    "learning_candidate_created",
    "learning_approved",
    "learning_applied",
    "learning_succeeded",
    "learning_failed",
    "learning_deprecated",
    "artifact_created",
    "metric",
    "kpi",
    "experiment_started",
    "experiment_evaluated",
    "anomaly_detected",
    "verdict",
    "error",
    # Extras para run lifecycle
    "run_started",
    "run_completed",
    "run_blocked",
    "run_failed",
    "blocker_created",
    "preflight",
    "info",
    "warning",
})

# ── Niveles de log ─────────────────────────────────────────────────────────────

ALLOWED_LEVELS = frozenset({"debug", "info", "warning", "error", "critical"})

# ── Status permitidos ──────────────────────────────────────────────────────────

ALLOWED_STATUSES = frozenset({
    "started",
    "completed",
    "failed",
    "blocked",
    "skipped",
    "intent",
    "pending",
    "approved",
    "rejected",
    "active",
    "deprecated",
    "superseded",
    "running",
    "ok",
})

# ── Campos obligatorios por evento ─────────────────────────────────────────────

REQUIRED_EVENT_FIELDS = frozenset({
    "event_id",
    "schema_version",
    "run_id",
    "ticket_id",
    "trace_id",
    "span_id",
    "seq_run",
    "ts",
    "source",
    "event_type",
    "category",
    "stage",
    "action",
    "status",
    "level",
    "message",
    "payload",
    "artifact_refs",
    "learning_eligible",
    "redaction",
})

# ── Contadores globales ────────────────────────────────────────────────────────

import threading

_global_seq_lock = threading.Lock()
_global_seq: int = 0


def _next_global_seq() -> int:
    global _global_seq
    with _global_seq_lock:
        _global_seq += 1
        return _global_seq


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _monotonic_ms() -> int:
    return int(time.monotonic() * 1000)


def _new_event_id() -> str:
    return f"evt_{_next_global_seq():06d}_{uuid.uuid4().hex[:8]}"


def _new_span_id(action: str = "") -> str:
    slug = action.replace(".", "-").replace("_", "-")[:20] if action else "span"
    return f"span-{slug}-{uuid.uuid4().hex[:6]}"


# ── Constructor canónico de eventos ───────────────────────────────────────────

def build_event(
    *,
    run_id: str,
    ticket_id: Any,
    trace_id: str,
    seq_run: int,
    source: str,
    event_type: str,
    category: str,
    stage: str,
    action: str,
    status: str,
    level: str,
    message: str,
    payload: Optional[dict] = None,
    artifact_refs: Optional[list] = None,
    learning_eligible: bool = False,
    span_id: Optional[str] = None,
    parent_event_id: Optional[str] = None,
    causation_event_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    event_id: Optional[str] = None,
    redaction_applied: bool = False,
    redacted_fields: Optional[list] = None,
    duration_ms: Optional[int] = None,
    seq_global: Optional[int] = None,
    monotonic_ms: Optional[int] = None,
    extra: Optional[dict] = None,
) -> dict:
    """
    Construir un evento canónico que cumple el esquema v1.0.

    Todo evento emitido por QA UAT Agent debe construirse via esta función.
    No construir dicts de eventos a mano fuera de este módulo.
    """
    if source not in ALLOWED_SOURCES:
        raise ValueError(f"event_schema: source no permitida: {source!r}. Usar una de {sorted(ALLOWED_SOURCES)}")
    if category not in ALLOWED_CATEGORIES:
        raise ValueError(f"event_schema: category no permitida: {category!r}. Usar una de {sorted(ALLOWED_CATEGORIES)}")
    if level not in ALLOWED_LEVELS:
        raise ValueError(f"event_schema: level no permitido: {level!r}. Usar uno de {sorted(ALLOWED_LEVELS)}")

    eid = event_id or _new_event_id()
    sid = span_id or _new_span_id(action)
    sg = seq_global if seq_global is not None else _next_global_seq()
    mono = monotonic_ms if monotonic_ms is not None else _monotonic_ms()

    event: dict = {
        "event_id": eid,
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "ticket_id": ticket_id,
        "trace_id": trace_id,
        "span_id": sid,
        "parent_event_id": parent_event_id,
        "causation_event_id": causation_event_id,
        "correlation_id": correlation_id,
        "seq_global": sg,
        "seq_run": seq_run,
        "ts": _utcnow_iso(),
        "monotonic_ms": mono,
        "source": source,
        "event_type": event_type,
        "category": category,
        "stage": stage,
        "action": action,
        "status": status,
        "level": level,
        "message": message,
        "payload": payload or {},
        "artifact_refs": artifact_refs or [],
        "learning_eligible": learning_eligible,
        "redaction": {
            "applied": redaction_applied,
            "fields": redacted_fields or [],
        },
    }

    if duration_ms is not None:
        event["duration_ms"] = duration_ms

    if extra:
        event.update(extra)

    return event


def validate_event(event: dict) -> list[str]:
    """
    Validar que un evento cumple el esquema obligatorio.

    Devuelve lista de errores (vacía si es válido).
    """
    errors: list[str] = []
    for field in REQUIRED_EVENT_FIELDS:
        if field not in event:
            errors.append(f"campo obligatorio faltante: {field!r}")

    if "source" in event and event["source"] not in ALLOWED_SOURCES:
        errors.append(f"source inválida: {event['source']!r}")

    if "category" in event and event["category"] not in ALLOWED_CATEGORIES:
        errors.append(f"category inválida: {event['category']!r}")

    if "level" in event and event["level"] not in ALLOWED_LEVELS:
        errors.append(f"level inválido: {event['level']!r}")

    if "seq_run" in event:
        if not isinstance(event["seq_run"], int) or event["seq_run"] < 0:
            errors.append("seq_run debe ser entero >= 0")

    if "redaction" in event:
        r = event["redaction"]
        if not isinstance(r, dict):
            errors.append("redaction debe ser un objeto")
        elif "applied" not in r:
            errors.append("redaction.applied es obligatorio")

    return errors
