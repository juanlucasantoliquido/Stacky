"""H1.3 — RunTelemetry y persist por runtime.

Contrato:
  - RunTelemetry: dataclass con los campos comunes de telemetría.
  - persist(execution_id, t): escribe en metadata["harness_telemetry"].
    Para retro-compat, claude_code_cli mantiene "claude_telemetry" además.
  - from_claude_stream(stream_telemetry): crea RunTelemetry desde el dict
    que emite claude_code_cli_runner._capture_result_telemetry.
  - from_codex_event(event): crea RunTelemetry desde un evento JSONL de codex.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("stacky.harness.telemetry")

# Importación top-level para que los tests puedan monkeypatch
try:
    from db import session_scope
    from models import AgentExecution
except ImportError:
    session_scope = None  # type: ignore[assignment]
    AgentExecution = None  # type: ignore[assignment]


@dataclass
class RunTelemetry:
    runtime: str
    session_id: str | None = None
    num_turns: int | None = None
    total_cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime": self.runtime,
            "session_id": self.session_id,
            "num_turns": self.num_turns,
            "total_cost_usd": self.total_cost_usd,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
        }


def from_claude_stream(stream_telemetry: dict[str, Any]) -> RunTelemetry:
    """Construye RunTelemetry desde el dict de claude_code_cli_runner."""
    usage = stream_telemetry.get("usage") or {}
    return RunTelemetry(
        runtime="claude_code_cli",
        session_id=stream_telemetry.get("session_id"),
        num_turns=stream_telemetry.get("num_turns"),
        total_cost_usd=stream_telemetry.get("total_cost_usd"),
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        cache_read_tokens=usage.get("cache_read_input_tokens"),
        raw=dict(stream_telemetry),
    )


def from_codex_event(event: dict[str, Any]) -> RunTelemetry:
    """Construye RunTelemetry desde un evento JSONL de codex.

    El schema del JSONL de codex no está documentado; se extrae lo que se pueda
    de los campos conocidos y el resto se guarda en raw para observabilidad.
    """
    # session_id puede estar top-level o en item
    session_id = event.get("session_id") or event.get("conversation_id")
    item = event.get("item") or {}
    if not session_id:
        session_id = item.get("session_id") or item.get("conversation_id")

    # Campos de uso — puede estar en usage, tokens, o top-level
    usage = event.get("usage") or event.get("tokens") or {}
    input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens")
    output_tokens = usage.get("output_tokens") or usage.get("completion_tokens")
    cache_read = usage.get("cache_read_input_tokens") or usage.get("cache_read_tokens")

    num_turns = event.get("num_turns") or event.get("turn_count")
    total_cost = event.get("total_cost_usd") or event.get("cost_usd")

    return RunTelemetry(
        runtime="codex_cli",
        session_id=session_id,
        num_turns=num_turns,
        total_cost_usd=total_cost,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read,
        raw=dict(event),
    )


def persist(execution_id: int, t: RunTelemetry) -> None:
    """Escribe harness_telemetry en metadata de la ejecución.

    Para retro-compat con harness_health, claude_code_cli también mantiene
    la clave legacy "claude_telemetry" (no se rompe ningún test existente).
    """
    try:
        with session_scope() as session:
            row = session.get(AgentExecution, execution_id)
            if row is None:
                logger.warning("[exec=%s] ejecución no encontrada para telemetría", execution_id)
                return
            md = row.metadata_dict
            md["harness_telemetry"] = t.to_dict()
            # Retro-compat: claude mantiene la clave legacy
            if t.runtime == "claude_code_cli" and t.raw:
                md["claude_telemetry"] = {k: v for k, v in t.raw.items() if k != "session_id"}
            row.metadata_dict = md
    except Exception:
        logger.exception("[exec=%s] fallo al persistir harness_telemetry", execution_id)
