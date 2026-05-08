"""Tests de ActionContext / track_action."""

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


def _collect_events(pe_mod, ticket_id: str, timeout: float = 1.5) -> list[dict]:
    deadline = time.time() + timeout
    last: list[dict] = []
    while time.time() < deadline:
        last = pe_mod.read_events(ticket_id=ticket_id, days_back=1)
        if last:
            return last
        time.sleep(0.05)
    return last


class TestActionContextHappyPath:
    def test_started_y_done_se_emiten(self):
        import pipeline_events as pe
        from action_tracker import ActionContext

        with ActionContext("invoke_dev", ticket_id="T1", phase="dev") as ac:
            ac.progress(25, "agent_typing")
            ac.progress(75, "writing_files")

        time.sleep(0.3)
        events = _collect_events(pe, "T1")
        kinds = [e.get("kind") for e in events]
        assert "action_started" in kinds
        assert "action_progress" in kinds
        assert "action_done" in kinds
        # Duration presente en done
        done_evs = [e for e in events if e.get("kind") == "action_done"]
        assert done_evs and "duration_ms" in done_evs[0]

    def test_execution_id_se_mantiene_entre_eventos(self):
        import pipeline_events as pe
        from action_tracker import ActionContext

        with ActionContext("scm_push", ticket_id="T2", phase="deploy") as ac:
            ac.progress(50, "uploading")

        time.sleep(0.3)
        events = _collect_events(pe, "T2")
        exec_ids = {e.get("execution_id") for e in events if e.get("action") == "scm_push"}
        assert len(exec_ids) == 1  # todos los eventos comparten el mismo execution_id

    def test_parent_execution_id_se_hereda(self):
        import pipeline_events as pe
        from action_tracker import ActionContext

        with ActionContext("outer_action", ticket_id="T3", phase="dev") as outer:
            with ActionContext("inner_action", ticket_id="T3", phase="dev") as inner:
                assert inner.parent_execution_id == outer.execution_id

        time.sleep(0.3)
        events = _collect_events(pe, "T3")
        inner_events = [e for e in events if e.get("action") == "inner_action"]
        assert inner_events
        assert inner_events[0].get("parent_execution_id") is not None


class TestActionContextErrorPath:
    def test_excepcion_emite_action_error_clasificado(self):
        import pipeline_events as pe
        from action_tracker import ActionContext

        with pytest.raises(ConnectionRefusedError):
            with ActionContext("fetch_data", ticket_id="E1", phase="sync"):
                raise ConnectionRefusedError("upstream down")

        time.sleep(0.3)
        events = _collect_events(pe, "E1")
        errs = [e for e in events if e.get("kind") == "action_error"]
        assert errs, f"Se esperaba action_error en {events}"
        assert errs[0].get("error_kind") == "network"
        assert errs[0].get("user_friendly")

    def test_excepcion_se_propaga_al_caller(self):
        from action_tracker import ActionContext

        with pytest.raises(ValueError):
            with ActionContext("do_x", ticket_id="E2"):
                raise ValueError("nope")


class TestTrackActionDecorator:
    def test_decorator_envuelve_funcion(self):
        import pipeline_events as pe
        from action_tracker import track_action

        @track_action("my_op", phase="dev")
        def work(*, ticket_id: str, value: int) -> int:
            return value * 2

        result = work(ticket_id="D1", value=21)
        assert result == 42

        time.sleep(0.3)
        events = _collect_events(pe, "D1")
        kinds = [e.get("kind") for e in events if e.get("action") == "my_op"]
        assert "action_started" in kinds
        assert "action_done" in kinds

    def test_decorator_nunca_rompe_el_callable(self):
        """Aunque el tracker falle internamente, la función debe correr."""
        from action_tracker import track_action

        @track_action("should_run", phase="dev")
        def fn(ticket_id=None):
            return "ok"

        assert fn(ticket_id="X") == "ok"
