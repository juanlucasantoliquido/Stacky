"""Plan 149 F4/F5/F7 — Superficie de cuarentena de intake en el Desatascador,
endpoint de re-intake 1-click, y diag read-only global."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest


@pytest.fixture(autouse=True)
def _clean_quarantine_state():
    """R7 — el módulo-global _SEEN_TERMINAL_PENDING/_QUARANTINE_REASON es
    compartido entre tests; limpiar en setup/teardown evita contaminación."""
    from services import output_watcher as ow_mod
    ow_mod._SEEN_TERMINAL_PENDING.clear()
    ow_mod._QUARANTINE_REASON.clear()
    yield
    ow_mod._SEEN_TERMINAL_PENDING.clear()
    ow_mod._QUARANTINE_REASON.clear()


# ── F4 — quarantine_snapshot + ruteo del board por intake ───────────────────


def test_quarantine_snapshot_records_reason(tmp_path):
    from services.output_watcher import _quarantine_pending_once, quarantine_snapshot

    tmp_pt = tmp_path / "pending-task.json"
    tmp_pt.write_text("", encoding="utf-8")
    _quarantine_pending_once(tmp_pt, "archivo vacío")

    snap = quarantine_snapshot()
    assert snap[str(tmp_pt)]["reason"] == "archivo vacío"


def _make_epic_dir(tmp_path: Path, ado_id: int) -> Path:
    epic_dir = tmp_path / "Agentes" / "outputs" / f"epic-{ado_id}"
    epic_dir.mkdir(parents=True)
    return epic_dir


def test_scan_parse_errors_carry_reason_code_when_flag_on(tmp_path, monkeypatch):
    import config as cfg
    monkeypatch.setattr(cfg.config, "STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED", True)

    epic_dir = _make_epic_dir(tmp_path, 7001)
    (epic_dir / "pending-task.json").write_text("   ", encoding="utf-8")

    from api.tickets import _scan_pending_tasks_for_epic
    _pending, _consumed, parse_errors = _scan_pending_tasks_for_epic(tmp_path, 7001)

    assert len(parse_errors) == 1
    assert parse_errors[0]["reason_code"] == "empty"


def test_scan_parse_errors_legacy_when_flag_off(tmp_path, monkeypatch):
    import config as cfg
    monkeypatch.setattr(cfg.config, "STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED", False)

    epic_dir = _make_epic_dir(tmp_path, 7002)
    (epic_dir / "pending-task.json").write_text("   ", encoding="utf-8")

    from api.tickets import _scan_pending_tasks_for_epic
    _pending, _consumed, parse_errors = _scan_pending_tasks_for_epic(tmp_path, 7002)

    assert len(parse_errors) == 1
    assert parse_errors[0]["reason_code"] is None
    assert "error" in parse_errors[0]


# ── F5 — endpoint POST /api/tickets/reintake-pending-task ───────────────────
# ── F7 — endpoint GET /api/diag/intake-quarantine ────────────────────────────


@pytest.fixture(scope="session")
def flask_app():
    os.environ["STACKY_OUTPUT_WATCHER_ENABLED"] = "false"
    os.environ["STACKY_MANIFEST_WATCHER_ENABLED"] = "false"
    import app as app_module
    app_module._startup_sync = lambda logger: None
    application = app_module.create_app()
    application.config["TESTING"] = True
    try:
        from services.ticket_status import stop_stale_recovery
        stop_stale_recovery()
    except Exception:
        pass
    return application


@pytest.fixture(scope="session", autouse=True)
def init_db(flask_app):
    from db import Base, engine
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client(flask_app):
    with flask_app.test_client() as c:
        yield c


@pytest.fixture
def tmp_repo(monkeypatch, tmp_path):
    import api.tickets as tickets_mod
    monkeypatch.setattr(tickets_mod, "REPO_ROOT", tmp_path)
    return tmp_path


def _valid_pending_task_payload(epic_id: int = 8001, rf_id: str = "RF-1") -> dict:
    return {
        "generated_at": "2026-07-16T00:00:00Z",
        "generated_by": "developer",
        "epic_id": epic_id,
        "rf_id": rf_id,
        "title": "Tarea X",
        "description_html": "<p>desc</p>",
        "plan_de_pruebas_path": "plan.md",
        "parent_link_type": "child",
        "status": "pending_manual_creation",
    }


def test_reintake_404_when_flag_off(client, monkeypatch):
    import config as cfg
    monkeypatch.setattr(cfg.config, "STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED", False)

    resp = client.post("/api/tickets/reintake-pending-task", json={
        "pending_task_path": "Agentes/outputs/epic-1/pending-task.json", "epic_ado_id": 1,
    })
    assert resp.status_code == 404


def test_reintake_422_when_still_invalid(client, monkeypatch, tmp_repo):
    import config as cfg
    monkeypatch.setattr(cfg.config, "STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED", True)

    epic_dir = tmp_repo / "Agentes" / "outputs" / "epic-8002"
    epic_dir.mkdir(parents=True)
    pt = epic_dir / "pending-task.json"
    pt.write_text("", encoding="utf-8")

    resp = client.post("/api/tickets/reintake-pending-task", json={
        "pending_task_path": "Agentes/outputs/epic-8002/pending-task.json",
        "epic_ado_id": 8002,
    })
    assert resp.status_code == 422
    body = resp.get_json()
    assert body["details"]["reason_code"] == "empty"


def test_reintake_404_when_file_missing(client, monkeypatch, tmp_repo):
    import config as cfg
    monkeypatch.setattr(cfg.config, "STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED", True)

    resp = client.post("/api/tickets/reintake-pending-task", json={
        "pending_task_path": "Agentes/outputs/epic-8003/nope.json",
        "epic_ado_id": 8003,
    })
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["error_type"] == "not_found"


def test_reintake_rejects_path_traversal(client, monkeypatch, tmp_repo):
    import config as cfg
    monkeypatch.setattr(cfg.config, "STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED", True)

    resp = client.post("/api/tickets/reintake-pending-task", json={
        "pending_task_path": "../../etc/x", "epic_ado_id": 1,
    })
    assert resp.status_code == 422
    body = resp.get_json()
    assert body["error_type"] == "validation"


def test_reintake_calls_create_child_task_when_valid(client, monkeypatch, tmp_repo):
    import config as cfg
    monkeypatch.setattr(cfg.config, "STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED", True)

    epic_dir = tmp_repo / "Agentes" / "outputs" / "epic-8004"
    epic_dir.mkdir(parents=True)
    pt = epic_dir / "pending-task.json"
    rel = "Agentes/outputs/epic-8004/pending-task.json"
    pt.write_text(json.dumps(_valid_pending_task_payload(8004)), encoding="utf-8")

    # Sembrar la cuarentena con la MISMA forma de clave que usa el watcher
    # (repo_root / rel, sin .resolve()) — C3.
    from services.output_watcher import _quarantine_pending_once, quarantine_snapshot
    seeded_key = tmp_repo / rel
    _quarantine_pending_once(seeded_key, "empty")
    assert str(seeded_key) in quarantine_snapshot()

    calls: list[dict] = []

    class _FakeResp:
        status_code = 200
        headers = {"content-type": "application/json"}

        def json(self):
            return {"ok": True, "idempotent": False}

    def _fake_post(url, json=None, timeout=None, **kw):
        calls.append({"url": url, "body": json})
        return _FakeResp()

    import requests
    monkeypatch.setattr(requests, "post", _fake_post)

    resp = client.post("/api/tickets/reintake-pending-task", json={
        "pending_task_path": rel, "epic_ado_id": 8004,
    })
    assert resp.status_code == 200
    assert len(calls) == 1
    assert calls[0]["url"].endswith("/api/tickets/by-ado/8004/create-child-task")
    assert calls[0]["body"]["pending_task_path"] == rel
    # C3 — la cuarentena se limpió vía clear_quarantine (misma clave que el watcher).
    assert str(seeded_key) not in quarantine_snapshot()


# ── F7 — diag read-only global ───────────────────────────────────────────────


def test_diag_intake_quarantine_lists_all_when_flag_on(client, monkeypatch):
    import config as cfg
    monkeypatch.setattr(cfg.config, "STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED", True)

    from services.output_watcher import _quarantine_pending_once
    _quarantine_pending_once(Path("Z:/fake/a/pending-task.json"), "archivo vacío")
    _quarantine_pending_once(Path("Z:/fake/b/pending-task.json"), "JSON truncado")

    resp = client.get("/api/diag/intake-quarantine")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["enabled"] is True
    assert body["count"] == 2
    assert all("reason" in item for item in body["items"])


def test_diag_intake_quarantine_disabled_when_flag_off(client, monkeypatch):
    import config as cfg
    monkeypatch.setattr(cfg.config, "STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED", False)

    resp = client.get("/api/diag/intake-quarantine")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {"enabled": False, "items": []}
