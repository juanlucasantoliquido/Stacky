"""V1.1 — Tests del registro/versionado de prompts de agente."""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture(autouse=True)
def _db_ready():
    from db import init_db, session_scope
    from models import AgentPromptVersion

    init_db()
    with session_scope() as session:
        session.query(AgentPromptVersion).delete()
    yield


def _sha(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def test_record_version_inserts_once():
    from services import agent_prompt_registry as reg

    body = "# DevPacifico\nsystem prompt v1"
    v1 = reg.record_version("DevPacifico.agent.md", body, source="import_endpoint")
    assert v1 is not None
    assert v1["sha256"] == _sha(body)
    # mismo body otra vez → no duplica (mismo sha)
    v2 = reg.record_version("DevPacifico.agent.md", body, source="fs_scan")
    assert v2["sha256"] == v1["sha256"]
    versions = reg.list_versions("DevPacifico.agent.md")
    assert len(versions) == 1


def test_record_version_new_body_new_version():
    from services import agent_prompt_registry as reg

    reg.record_version("Dev.agent.md", "body A", source="import_endpoint")
    reg.record_version("Dev.agent.md", "body B", source="import_endpoint")
    versions = reg.list_versions("Dev.agent.md")
    assert len(versions) == 2
    assert {v["sha256"] for v in versions} == {_sha("body A"), _sha("body B")}


def test_fs_scan_source_recorded():
    from services import agent_prompt_registry as reg

    v = reg.record_version("Q.agent.md", "manual edit", source="fs_scan")
    assert v["source"] == "fs_scan"


def test_diff_between_versions():
    from services import agent_prompt_registry as reg

    a = reg.record_version("D.agent.md", "line1\nline2\n", source="import_endpoint")
    b = reg.record_version("D.agent.md", "line1\nline2 changed\n", source="import_endpoint")
    diff = reg.diff_versions(a["id"], b["id"])
    assert "line2 changed" in diff
    assert diff.startswith("---") or "@@" in diff


def test_diff_missing_version_raises():
    from services import agent_prompt_registry as reg

    a = reg.record_version("D.agent.md", "x", source="import_endpoint")
    with pytest.raises(ValueError):
        reg.diff_versions(a["id"], 999999)


def test_record_version_empty_body_skips():
    from services import agent_prompt_registry as reg

    assert reg.record_version("E.agent.md", "", source="fs_scan") is None
    assert reg.list_versions("E.agent.md") == []


def test_ensure_version_for_run_idempotent():
    """Sello en el run: registra si no existe, no duplica si ya existe."""
    from services import agent_prompt_registry as reg

    body = "run body"
    sha1 = reg.ensure_version("R.agent.md", body)
    sha2 = reg.ensure_version("R.agent.md", body)
    assert sha1 == sha2 == _sha(body)
    assert len(reg.list_versions("R.agent.md")) == 1


# ── Endpoints ────────────────────────────────────────────────────────────────
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")
    from app import create_app
    from services.ticket_status import stop_stale_recovery
    from services.manifest_watcher import stop_manifest_watcher

    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()
    stop_manifest_watcher()


def test_versions_endpoint(client):
    from services import agent_prompt_registry as reg

    reg.record_version("Dev.agent.md", "body A", source="import_endpoint")
    reg.record_version("Dev.agent.md", "body B", source="import_endpoint")
    r = client.get("/api/agents/Dev.agent.md/versions")
    assert r.status_code == 200
    data = r.get_json()
    assert data["filename"] == "Dev.agent.md"
    assert len(data["versions"]) == 2


def test_diff_endpoint(client):
    from services import agent_prompt_registry as reg

    a = reg.record_version("D.agent.md", "l1\nl2\n", source="import_endpoint")
    b = reg.record_version("D.agent.md", "l1\nl2 changed\n", source="import_endpoint")
    r = client.get(f"/api/agents/D.agent.md/versions/diff?from={a['id']}&to={b['id']}")
    assert r.status_code == 200
    assert b"l2 changed" in r.data


def test_diff_endpoint_missing_params(client):
    r = client.get("/api/agents/D.agent.md/versions/diff")
    assert r.status_code == 400


def test_versions_endpoint_bad_filename(client):
    r = client.get("/api/agents/notanagent.txt/versions")
    assert r.status_code == 400
