"""Tests de integración para sse_bus."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    import pipeline_events as pe
    new_dir = tmp_path / "data"
    new_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(pe, "_DATA_DIR", new_dir)
    pe.EventStore._singleton = None
    yield
    pe.EventStore._singleton = None


class TestFormatSSE:
    def test_format_sse_incluye_id_event_data(self):
        from sse_bus import format_sse
        out = format_sse(42, "action_started", {"action": "foo", "ticket_id": "1"})
        assert "id: 42" in out
        assert "event: action_started" in out
        assert '"action":"foo"' in out or "\"action\": \"foo\"" in out
        # Doble salto al final para separador SSE
        assert out.endswith("\n\n")

    def test_format_comment_para_heartbeat(self):
        from sse_bus import format_comment
        out = format_comment("heartbeat now")
        assert out.startswith(":")
        assert "heartbeat now" in out


class TestEventStream:
    def test_stream_emite_hello_y_heartbeat(self):
        from sse_bus import event_stream

        gen = event_stream(max_seconds=1)
        chunks = list(gen)

        # Primer chunk es el 'hello'
        assert any("event: hello" in c for c in chunks)
        # Debe haber un stream-ended tras max_seconds
        assert any("stream-ended" in c for c in chunks)

    def test_stream_filtra_por_ticket(self):
        import pipeline_events as pe
        from sse_bus import event_stream

        # Emitimos ANTES de que el cliente inicie el stream; no llegarán al live,
        # pero sí a través del replay si hay last_event_id. Para este test
        # validamos que emits posteriores al hello sean filtrados.
        gen = event_stream(ticket_id="TICK-A", max_seconds=1.5)

        # Capturar el primer hello
        first = next(gen)
        assert "event: hello" in first

        # Emitir uno que debe pasar el filtro y otro que no
        pe.emit(kind="notification", ticket_id="TICK-A", message="in")
        pe.emit(kind="notification", ticket_id="TICK-B", message="out")

        # Drenar el resto del stream
        rest = list(gen)
        blob = "\n".join(rest)

        # TICK-A debería aparecer, TICK-B nunca
        assert "TICK-A" in blob
        assert "TICK-B" not in blob

    def test_stream_replay_con_last_event_id(self):
        import pipeline_events as pe
        from sse_bus import event_stream

        # Emitir eventos previos
        pe.emit(kind="notification", ticket_id="TICK-R", message="historico_1")
        pe.emit(kind="notification", ticket_id="TICK-R", message="historico_2")
        time.sleep(0.3)

        # Stream con Last-Event-ID hace replay
        gen = event_stream(ticket_id="TICK-R", last_event_id="5", max_seconds=1.0)
        chunks = list(gen)
        blob = "\n".join(chunks)

        # Los históricos deberían estar
        assert "historico_1" in blob
        assert "historico_2" in blob
