"""Tests de F2.1 — Stacky MCP server (protocolo + tools de escritura validadas)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── Protocolo ──────────────────────────────────────────────────────────────────


def test_initialize_and_tools_list():
    from services import stacky_mcp_server as s

    init = s.handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["serverInfo"]["name"] == "stacky"
    assert init["result"]["protocolVersion"]

    listed = s.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in listed["result"]["tools"]}
    assert names == {
        "stacky_get_ticket",
        "stacky_search_memory",
        "stacky_search_similar",
        "stacky_submit_comment",
        "stacky_submit_task",
    }
    # Cada tool declara inputSchema (validación server-side).
    for t in listed["result"]["tools"]:
        assert t["inputSchema"]["type"] == "object"


def test_notification_initialized_has_no_response():
    from services import stacky_mcp_server as s

    assert s.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_unknown_method_returns_error():
    from services import stacky_mcp_server as s

    resp = s.handle_message({"jsonrpc": "2.0", "id": 9, "method": "no/such"})
    assert resp["error"]["code"] == -32601


# ── submit_comment: validación server-side ──────────────────────────────────────


def test_submit_comment_rejects_empty(tmp_path, monkeypatch):
    from services import stacky_mcp_tools as tools

    monkeypatch.setattr(tools, "_outputs_root", lambda: tmp_path)
    res = tools.submit_comment(ado_id=206, html="   ")
    assert res["ok"] is False
    assert res["errors"]


def test_submit_comment_writes_canonical_file(tmp_path, monkeypatch):
    from services import stacky_mcp_tools as tools

    monkeypatch.setattr(tools, "_outputs_root", lambda: tmp_path)
    # No encolar de verdad (sin DB de outbox en este test).
    monkeypatch.setattr(tools, "_enqueue_comment", lambda **k: "op-1")
    res = tools.submit_comment(ado_id=206, html="<p>listo</p>")
    assert res["ok"] is True
    written = tmp_path / "206" / "comment.html"
    assert written.read_text(encoding="utf-8") == "<p>listo</p>"


# ── submit_task: schema + ordinal vs ADO id real ────────────────────────────────


def _valid_payload(epic_id: int) -> dict:
    return {
        "epic_id": epic_id,
        "rf_id": "RF-019",
        "title": "Alta de marca",
        "description_html": "<p>x</p>",
        "plan_de_pruebas_path": "plan.md",
        "parent_link_type": "child",
        "status": "pending_manual_creation",
        "generated_at": "2026-06-09T00:00:00Z",
        "generated_by": "test",
    }


def test_submit_task_rejects_epic_id_mismatch(tmp_path, monkeypatch):
    from services import stacky_mcp_tools as tools

    monkeypatch.setattr(tools, "_outputs_root", lambda: tmp_path)
    monkeypatch.setattr(tools, "_enqueue_task", lambda **k: "op-1")
    # Directorio será epic-206 pero el payload trae epic_id=1 (ordinal) → mismatch.
    payload = _valid_payload(epic_id=1)
    res = tools.submit_task(epic_ado_id=206, payload=payload)
    assert res["ok"] is False
    assert any("mismatch" in e.lower() or "ordinal" in e.lower() for e in res["errors"])
    # El archivo inválido NO debe quedar en disco (contrato del MCP).
    assert not (tmp_path / "epic-206" / "rf-019" / "pending-task.json").exists()


def test_submit_task_writes_valid_file(tmp_path, monkeypatch):
    from services import stacky_mcp_tools as tools

    monkeypatch.setattr(tools, "_outputs_root", lambda: tmp_path)
    monkeypatch.setattr(tools, "_enqueue_task", lambda **k: "op-2")
    # check_db en artifact_validator devuelve None (no consultable) → no bloquea.
    res = tools.submit_task(epic_ado_id=206, payload=_valid_payload(epic_id=206))
    assert res["ok"] is True, res
    written = tmp_path / "epic-206" / "rf-019" / "pending-task.json"
    data = json.loads(written.read_text(encoding="utf-8"))
    assert data["epic_id"] == 206
    assert data["status"] == "pending_manual_creation"


def test_submit_task_autofills_epic_id_from_dir(tmp_path, monkeypatch):
    from services import stacky_mcp_tools as tools

    monkeypatch.setattr(tools, "_outputs_root", lambda: tmp_path)
    monkeypatch.setattr(tools, "_enqueue_task", lambda **k: "op-3")
    payload = _valid_payload(epic_id=206)
    payload.pop("epic_id")  # ausente → se completa con epic_ado_id
    res = tools.submit_task(epic_ado_id=206, payload=payload)
    assert res["ok"] is True, res
    written = tmp_path / "epic-206" / "rf-019" / "pending-task.json"
    assert json.loads(written.read_text(encoding="utf-8"))["epic_id"] == 206
