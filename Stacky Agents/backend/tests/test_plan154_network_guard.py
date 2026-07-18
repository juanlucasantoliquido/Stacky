"""Plan 154 F5 — Guard de red bajo STACKY_TEST_MODE.

Cubre los 3 puntos del plan:
  (i)   fixture autouse _no_network_egress (conftest.py) bloquea connect() no-loopback.
  (ii)  _startup_sync gateado en el call-site de create_app().
  (iii) self-POST del watcher (mode_a) solo corre con opt-in explicito.
STACKY_TEST_MODE=1 ya lo setea tests/conftest.py para toda la suite.
"""
import json
import socket
from unittest import mock

import pytest


# ── (i) guard de sockets ──────────────────────────────────────────────────────

def test_guard_bloquea_egress_no_loopback():
    """Conectar a TEST-NET-1 (192.0.2.1, nunca ruteable) levanta RuntimeError
    del guard — NO un TimeoutError."""
    with pytest.raises(RuntimeError) as ei:
        socket.create_connection(("192.0.2.1", 80), timeout=1)
    assert "guard-red" in str(ei.value)


def test_guard_permite_loopback():
    """Conectar a un listener local efimero en 127.0.0.1 NO levanta."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(("127.0.0.1", port))  # no debe levantar
        client.close()
    finally:
        listener.close()


# ── (ii) _startup_sync gateado ────────────────────────────────────────────────

def test_startup_sync_gateado_en_test_mode():
    """create_app() bajo STACKY_TEST_MODE (ya seteado por conftest) NO invoca
    _startup_sync: el gate del call-site F5.ii lo salta."""
    import os
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    import app as _app_mod
    with mock.patch.object(_app_mod, "_startup_sync") as _sync:
        _app_mod.create_app()
    assert not _sync.called


# ── (iii) self-POST del watcher requiere opt-in ───────────────────────────────

class _FakeResp:
    status_code = 200

    def json(self):
        return {"ok": True, "task_ado_id": 999}


def _write_valid_pending(tmp_path, epic_ado_id):
    payload = {
        "rf_id": "RF-001",
        "title": "test",
        "status": "pending_manual_creation",
        "generated_at": "2026-05-16T00:00:00Z",
        "generated_by": "pytest-plan154-f5",
        "epic_id": int(epic_ado_id),
        "description_html": "<p>generado por tests (plan 154 F5)</p>",
        "plan_de_pruebas_path": "outputs/plan_de_pruebas.md",
        "parent_link_type": "System.LinkTypes.Hierarchy-Reverse",
    }
    p = tmp_path / "pending-task.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_watcher_self_post_requiere_opt_in(tmp_path, monkeypatch):
    """Sin opt-in, el auto-create NO postea (gate F5.iii). Con opt-in, SI."""
    import requests
    from services import output_watcher

    epic_ado_id = 40207
    pt = _write_valid_pending(tmp_path, epic_ado_id)

    calls = {"n": 0}

    def _counting_post(url, json=None, timeout=None):
        calls["n"] += 1
        return _FakeResp()

    monkeypatch.setattr(requests, "post", _counting_post)

    # SIN opt-in (STACKY_TEST_MODE=1 por conftest) → gate corta antes del POST.
    monkeypatch.delenv("STACKY_TEST_ALLOW_WATCHER_SELF_POST", raising=False)
    res = output_watcher._auto_create_pending_tasks(
        epic_ado_id=epic_ado_id, pending_files=[pt],
    )
    assert calls["n"] == 0, res

    # CON opt-in → el auto-create procede y postea.
    monkeypatch.setenv("STACKY_TEST_ALLOW_WATCHER_SELF_POST", "1")
    res2 = output_watcher._auto_create_pending_tasks(
        epic_ado_id=epic_ado_id, pending_files=[pt],
    )
    assert calls["n"] >= 1, res2
