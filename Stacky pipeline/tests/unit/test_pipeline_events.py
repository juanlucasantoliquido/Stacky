"""Tests para pipeline_events: modelo, emit, queue, rotación, read_events."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """Redirige el DATA_DIR del módulo a una tmp_path por test."""
    import pipeline_events as pe
    new_dir = tmp_path / "data"
    new_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(pe, "_DATA_DIR", new_dir)
    # Reset singleton para que use el nuevo DATA_DIR
    pe.EventStore._singleton = None
    yield
    pe.EventStore._singleton = None


class TestPipelineEventModel:
    def test_modelo_valida_y_serializa(self):
        from pipeline_events import PipelineEvent
        ev = PipelineEvent(
            ts=datetime.now(timezone.utc),
            execution_id="abc-123",
            kind="action_started",
            ticket_id="0027698",
            action="invoke_dev",
            phase="dev",
        )
        dumped = ev.model_dump(mode="json", exclude_none=True)
        assert dumped["kind"] == "action_started"
        assert dumped["action"] == "invoke_dev"
        assert dumped["ticket_id"] == "0027698"
        assert "correlation" in dumped  # default factory

    def test_kind_invalido_lanza_validation_error(self):
        from pipeline_events import PipelineEvent
        with pytest.raises(Exception):
            PipelineEvent(
                ts=datetime.now(timezone.utc),
                execution_id="x",
                kind="kind_inexistente",  # type: ignore[arg-type]
            )


class TestEmitAndPersist:
    def _wait_for_file(self, data_dir: Path, timeout: float = 2.0) -> Path:
        deadline = time.time() + timeout
        while time.time() < deadline:
            files = list(data_dir.glob("pipeline_events_*.jsonl"))
            if files and files[0].stat().st_size > 0:
                return files[0]
            time.sleep(0.05)
        pytest.fail(f"No se creó archivo JSONL en {data_dir}")

    def test_emit_persiste_en_jsonl(self, tmp_path):
        import pipeline_events as pe
        pe.emit(kind="action_started", ticket_id="0000001", action="unit_test")
        f = self._wait_for_file(pe._DATA_DIR)
        lines = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) >= 1
        assert any(l["action"] == "unit_test" for l in lines)
        assert all("execution_id" in l for l in lines)

    def test_emit_fire_and_forget_no_rompe_con_kind_invalido(self):
        import pipeline_events as pe
        # kind inválido → emit debe retornar None sin propagar
        res = pe.emit(kind="inexistente_kind", ticket_id="x")  # type: ignore[arg-type]
        assert res is None

    def test_emit_genera_execution_id_por_default(self):
        import pipeline_events as pe
        ev = pe.emit(kind="notification", message="test")
        assert ev is not None
        assert ev.execution_id
        assert len(ev.execution_id) >= 32  # uuid4


class TestReadEvents:
    def test_read_events_filtra_por_ticket(self, tmp_path):
        import pipeline_events as pe
        pe.emit(kind="action_started", ticket_id="A", action="x")
        pe.emit(kind="action_started", ticket_id="B", action="y")
        # Dar tiempo al writer async
        time.sleep(0.3)

        events_a = pe.read_events(ticket_id="A", days_back=1)
        events_b = pe.read_events(ticket_id="B", days_back=1)
        assert all(e.get("ticket_id") == "A" for e in events_a)
        assert all(e.get("ticket_id") == "B" for e in events_b)
        assert len(events_a) >= 1
        assert len(events_b) >= 1

    def test_read_events_filtra_por_kind(self):
        import pipeline_events as pe
        pe.emit(kind="action_started", ticket_id="Z", action="a")
        pe.emit(kind="action_error", ticket_id="Z", error_kind="network", message="x")
        time.sleep(0.3)

        errors = pe.read_events(ticket_id="Z", kind="action_error", days_back=1)
        assert len(errors) >= 1
        assert all(e["kind"] == "action_error" for e in errors)


class TestShortId:
    def test_short_id_devuelve_primeros_8(self):
        from pipeline_events import short_id
        assert short_id("abcdefghijklmnop") == "abcdefgh"
        assert short_id("") == "-"
        assert short_id(None) == "-"  # type: ignore[arg-type]


class TestSubscribe:
    def test_subscribe_recibe_evento_emitido(self):
        import pipeline_events as pe
        sub = pe.subscribe(maxsize=10)
        pe.emit(kind="notification", ticket_id="S", message="hola")
        # El worker drena async; dar tiempo
        ev = sub.get(timeout=1.5)
        assert ev.kind == "notification"
        assert ev.ticket_id == "S"
        pe.unsubscribe(sub)
