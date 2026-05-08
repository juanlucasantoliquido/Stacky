"""
Tests para action_log — Logger + Reverser (T15).

Cobertura: log_action, list_actions, get_action, reverse_action,
mark_reversed/failed, dry_run, handlers registrados y no registrados,
rollback ya revertido, rollback sin reverse_action.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from action_log.logger import (
    log_action,
    list_actions,
    get_action,
    mark_entry_reversed,
    mark_entry_failed,
    ActionLogEntry,
)
from action_log.reverser import (
    reverse_action,
    register_reverse_handler,
    list_reversible_actions,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _state_dir(tmp_path) -> str:
    d = str(tmp_path / "state")
    os.makedirs(d, exist_ok=True)
    return d


def _log(tmp_path, **kwargs) -> ActionLogEntry:
    """Shortcut para loguear con path temporal."""
    from datetime import datetime, timezone
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    log_path = str(tmp_path / "state" / f"action_log_{month}.jsonl")
    os.makedirs(str(tmp_path / "state"), exist_ok=True)
    return log_action(log_path=log_path, **kwargs)


# ── log_action ────────────────────────────────────────────────────────────────


def test_log_action_creates_entry(tmp_path):
    entry = _log(
        tmp_path,
        actor="TestActor",
        tool="test.tool",
        params={"a": 1},
        result={"ok": True},
        reverse=("test.undo", {"a": 1}),
        ticket_id=42,
    )
    assert entry.id
    assert entry.actor == "TestActor"
    assert entry.tool == "test.tool"
    assert entry.status == "logged"
    assert entry.reverse_action == {"tool": "test.undo", "params": {"a": 1}}
    assert entry.ticket_id == 42


def test_log_action_persists_to_file(tmp_path):
    entry = _log(
        tmp_path,
        actor="A",
        tool="t",
        params={},
        result={},
        reverse=None,
    )
    from datetime import datetime, timezone
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    log_path = str(tmp_path / "state" / f"action_log_{month}.jsonl")
    lines = open(log_path, encoding="utf-8").readlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["id"] == entry.id


def test_log_action_no_reverse(tmp_path):
    entry = _log(
        tmp_path,
        actor="A",
        tool="t",
        params={},
        result={},
        reverse=None,
    )
    assert entry.reverse_action is None


# ── list_actions / get_action ─────────────────────────────────────────────────


def test_list_actions_all(tmp_path):
    state = _state_dir(tmp_path)
    _log(tmp_path, actor="A", tool="t1", params={}, result={}, ticket_id=1)
    _log(tmp_path, actor="B", tool="t2", params={}, result={}, ticket_id=2)
    entries = list_actions(state_dir=state)
    assert len(entries) == 2


def test_list_actions_filter_by_ticket(tmp_path):
    state = _state_dir(tmp_path)
    _log(tmp_path, actor="A", tool="t1", params={}, result={}, ticket_id=1)
    _log(tmp_path, actor="B", tool="t2", params={}, result={}, ticket_id=2)
    entries = list_actions(ticket_id=1, state_dir=state)
    assert len(entries) == 1
    assert entries[0].ticket_id == 1


def test_get_action_by_id(tmp_path):
    state = _state_dir(tmp_path)
    entry = _log(tmp_path, actor="A", tool="t", params={}, result={})
    found = get_action(entry.id, state_dir=state)
    assert found is not None
    assert found.id == entry.id


def test_get_action_not_found(tmp_path):
    state = _state_dir(tmp_path)
    found = get_action("uuid-inexistente", state_dir=state)
    assert found is None


# ── mark_entry_reversed / failed ──────────────────────────────────────────────


def test_mark_entry_reversed(tmp_path):
    state = _state_dir(tmp_path)
    entry = _log(tmp_path, actor="A", tool="t", params={}, result={})
    mark_entry_reversed(entry.id, state_dir=state)
    found = get_action(entry.id, state_dir=state)
    assert found.status == "reversed"


def test_mark_entry_failed(tmp_path):
    state = _state_dir(tmp_path)
    entry = _log(tmp_path, actor="A", tool="t", params={}, result={})
    mark_entry_failed(entry.id, state_dir=state)
    found = get_action(entry.id, state_dir=state)
    assert found.status == "failed"


# ── reverse_action ────────────────────────────────────────────────────────────


def test_reverse_action_not_found(tmp_path):
    state = _state_dir(tmp_path)
    result = reverse_action("uuid-no-existe", state_dir=state)
    assert result["status"] == "failed"
    assert "no encontrada" in result["reason"]


def test_reverse_action_no_reverse_defined(tmp_path):
    state = _state_dir(tmp_path)
    entry = _log(tmp_path, actor="A", tool="t", params={}, result={}, reverse=None)
    result = reverse_action(entry.id, state_dir=state)
    assert result["status"] == "skipped"
    assert "reverse-action" in result["reason"]


def test_reverse_action_already_reversed(tmp_path):
    state = _state_dir(tmp_path)
    entry = _log(
        tmp_path,
        actor="A",
        tool="t",
        params={},
        result={},
        reverse=("t.undo", {}),
    )
    mark_entry_reversed(entry.id, state_dir=state)
    result = reverse_action(entry.id, state_dir=state)
    assert result["status"] == "skipped"
    assert "revertida" in result["reason"]


def test_reverse_action_with_registered_handler(tmp_path):
    state = _state_dir(tmp_path)
    calls = []

    def my_handler(params):
        calls.append(params)
        return {"ok": True, "detail": "Done"}

    register_reverse_handler("my_tool.undo", my_handler)

    entry = _log(
        tmp_path,
        actor="A",
        tool="my_tool.do",
        params={"x": 1},
        result={"y": 2},
        reverse=("my_tool.undo", {"x": 1}),
    )
    result = reverse_action(entry.id, state_dir=state)
    assert result["status"] == "reversed"
    assert calls == [{"x": 1}]

    # Debe quedar marcado como reversed
    found = get_action(entry.id, state_dir=state)
    assert found.status == "reversed"


def test_reverse_action_handler_fails(tmp_path):
    state = _state_dir(tmp_path)

    def failing_handler(params):
        return {"ok": False, "detail": "No se pudo revertir"}

    register_reverse_handler("fail_tool.undo", failing_handler)
    entry = _log(
        tmp_path,
        actor="A",
        tool="fail_tool.do",
        params={},
        result={},
        reverse=("fail_tool.undo", {}),
    )
    result = reverse_action(entry.id, state_dir=state)
    assert result["status"] == "failed"

    found = get_action(entry.id, state_dir=state)
    assert found.status == "failed"


def test_reverse_action_handler_raises(tmp_path):
    state = _state_dir(tmp_path)

    def raising_handler(params):
        raise RuntimeError("Algo explotó")

    register_reverse_handler("raise_tool.undo", raising_handler)
    entry = _log(
        tmp_path,
        actor="A",
        tool="raise_tool.do",
        params={},
        result={},
        reverse=("raise_tool.undo", {}),
    )
    result = reverse_action(entry.id, state_dir=state)
    assert result["status"] == "failed"
    assert "explotó" in result["reason"]


def test_reverse_action_dry_run(tmp_path):
    state = _state_dir(tmp_path)
    entry = _log(
        tmp_path,
        actor="A",
        tool="t",
        params={},
        result={},
        reverse=("t.undo", {"k": "v"}),
    )
    result = reverse_action(entry.id, state_dir=state, dry_run=True)
    assert result["status"] == "dry_run"
    assert "t.undo" in result["reason"]
    # No debe marcarse como reversed
    found = get_action(entry.id, state_dir=state)
    assert found.status == "logged"


# ── list_reversible_actions ───────────────────────────────────────────────────


def test_list_reversible_actions(tmp_path):
    state = _state_dir(tmp_path)
    e1 = _log(tmp_path, actor="A", tool="t1", params={}, result={}, reverse=("t1.undo", {}))
    e2 = _log(tmp_path, actor="A", tool="t2", params={}, result={}, reverse=None)
    reversibles = list_reversible_actions(state_dir=state)
    ids = [r["id"] for r in reversibles]
    assert e1.id in ids
    assert e2.id not in ids


def test_list_reversible_excludes_already_reversed(tmp_path):
    state = _state_dir(tmp_path)
    entry = _log(
        tmp_path,
        actor="A",
        tool="t",
        params={},
        result={},
        reverse=("t.undo", {}),
    )
    mark_entry_reversed(entry.id, state_dir=state)
    reversibles = list_reversible_actions(state_dir=state)
    assert all(r["id"] != entry.id for r in reversibles)
