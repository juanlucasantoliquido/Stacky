"""Tests for collaborative memory Git sync (Phase E)."""
import gzip
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture(autouse=True)
def init_db():
    from db import init_db

    init_db()


def test_atomic_gzip_chunk_is_reproducible(tmp_path):
    from services import memory_git_sync

    events = [
        {
            "schema_version": 1,
            "chunk_id": "chunk-test",
            "event_id": "evt-1",
            "event_type": "observation",
            "entity_id": "mem-fixed",
            "payload_hash": "abc",
            "payload": {"title": "A", "content": "B"},
            "exported_at": "2026-06-06T00:00:00",
        }
    ]
    a = tmp_path / "a.jsonl.gz"
    b = tmp_path / "b.jsonl.gz"

    sha_a = memory_git_sync.write_chunk_atomic(a, events)
    sha_b = memory_git_sync.write_chunk_atomic(b, events)

    assert sha_a == sha_b
    assert a.read_bytes() == b.read_bytes()
    with gzip.open(a, "rt", encoding="utf-8") as fh:
        assert json.loads(fh.readline())["event_type"] == "observation"


def test_export_outbox_only_includes_active_shared_scopes(tmp_path):
    from db import session_scope
    from services import memory_git_sync, memory_store

    project = "MEM_SYNC_OUTBOX"
    exported = memory_store.save_observation(
        project=project,
        type="client_policy",
        title="Shared policy",
        content="Export this active project memory",
        scope="project",
        status="active",
    )
    memory_store.save_observation(
        project=project,
        type="client_policy",
        title="Private note",
        content="Never export this private memory",
        scope="private",
        status="active",
        author_email="dev@local",
    )
    memory_store.save_observation(
        project=project,
        type="client_policy",
        title="Draft note",
        content="Never export draft",
        scope="project",
        status="draft",
    )

    assert memory_git_sync.enqueue_exportable(project=project) == 1
    chunk = memory_git_sync.export_pending_chunk(project=project, repo_path=tmp_path)

    assert chunk["event_count"] == 1
    with session_scope() as session:
        rows = session.query(memory_git_sync.StackyMemorySyncOutbox).filter_by(project=project).all()
        assert len(rows) == 1
        assert rows[0].entity_id == exported
        assert rows[0].status == "pending"
        assert rows[0].chunk_id == chunk["chunk_id"]


def test_import_chunks_is_idempotent(tmp_path):
    from db import session_scope
    from services import memory_git_sync, memory_store

    project = "MEM_SYNC_IMPORT"
    repo = tmp_path / "repo"
    event = {
        "schema_version": 1,
        "chunk_id": "chunk-import",
        "event_id": "evt-import",
        "event_type": "observation",
        "entity_id": "mem-import-fixed",
        "payload_hash": "x",
        "payload": {
            "memory_id": "mem-import-fixed",
            "project": project,
            "scope": "project",
            "type": "bugfix",
            "title": "Imported memory",
            "content": "Import once only",
            "status": "active",
            "tags": ["sync"],
            "normalized_hash": memory_store._normalized_hash("Imported memory", "Import once only"),
            "revision_count": 1,
            "duplicate_count": 1,
        },
        "exported_at": "2026-06-06T00:00:00",
    }
    memory_git_sync.write_chunk_atomic(
        repo / "chunks" / "2026" / "06" / "06" / "chunk-import.jsonl.gz",
        [event],
    )

    first = memory_git_sync.import_chunks(project=project, repo_path=repo)
    second = memory_git_sync.import_chunks(project=project, repo_path=repo)

    assert first["imported_chunks"] == 1
    assert first["events_imported"] == 1
    assert second["imported_chunks"] == 0
    with session_scope() as session:
        count = (
            session.query(memory_store.StackyMemoryObservation)
            .filter_by(project=project, memory_id="mem-import-fixed")
            .count()
        )
        assert count == 1


def test_sync_push_failure_keeps_outbox_pending_with_chunk(tmp_path, monkeypatch):
    from db import session_scope
    from services import memory_git_sync, memory_store

    monkeypatch.setenv("STACKY_HOME", str(tmp_path / "Stacky"))
    monkeypatch.setenv("STACKY_MEMORY_GIT_PUSH_ATTEMPTS", "1")
    project = "MEM_SYNC_PUSH_FAIL"
    memory_store.save_observation(
        project=project,
        type="discovery",
        title="Push failure",
        content="Keep pending when remote push fails",
        scope="project",
        status="active",
    )

    result = memory_git_sync.sync_once(
        project=project,
        enabled=True,
        remote_url=str(tmp_path / "missing-remote.git"),
        push=True,
        timeout_seconds=5,
    )

    assert result["ok"] is False
    assert result["exported_events"] == 1
    with session_scope() as session:
        row = session.query(memory_git_sync.StackyMemorySyncOutbox).filter_by(project=project).first()
        assert row.status == "pending"
        assert row.chunk_id
        assert row.attempts >= 1


def test_memory_sync_api_status_and_run(tmp_path, monkeypatch):
    from services import memory_store

    monkeypatch.setenv("STACKY_HOME", str(tmp_path / "Stacky"))
    project = "MEM_SYNC_API"
    memory_store.save_observation(
        project=project,
        type="client_policy",
        title="API sync",
        content="Commit into the dedicated local memory repo",
        scope="project",
        status="active",
    )
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as client:
        status = client.get(f"/api/memory/sync/status?project={project}")
        assert status.status_code == 200
        assert status.get_json()["repo_exists"] is False

        run = client.post(
            "/api/memory/sync/run",
            json={"project": project, "enabled": True, "push": False, "timeout_seconds": 5},
        )
        assert run.status_code == 200
        payload = run.get_json()
        assert payload["ok"] is True
        assert payload["exported_events"] == 1
        assert Path(payload["repo_path"]).exists()


def test_export_quarantines_secret_and_skips(tmp_path):
    from db import session_scope
    from services import memory_git_sync, memory_store

    project = "MEM_SYNC_SECRET"
    mid = memory_store.save_observation(
        project=project,
        type="client_policy",
        title="Leaky policy",
        content="usar token ADO_PAT=abc123secretvalue para el deploy",
        scope="project",
        status="active",
    )

    # Invariante de export: el secreto no se encola; la memoria queda en cuarentena.
    assert memory_git_sync.enqueue_exportable(project=project) == 0
    assert memory_store.get(mid)["status"] == "quarantined"
    with session_scope() as session:
        rows = session.query(memory_git_sync.StackyMemorySyncOutbox).filter_by(project=project).all()
        assert rows == []


def test_export_redacts_pii_irreversibly(tmp_path):
    from services import memory_git_sync, memory_store

    project = "MEM_SYNC_PII"
    memory_store.save_observation(
        project=project,
        type="client_policy",
        title="Contacto de escalamiento",
        content="escalar siempre a juan.perez@cliente.com antes de cerrar",
        scope="project",
        status="active",
    )

    assert memory_git_sync.enqueue_exportable(project=project) == 1
    chunk = memory_git_sync.export_pending_chunk(project=project, repo_path=tmp_path)
    assert chunk["event_count"] == 1

    files = list(tmp_path.rglob("*.jsonl.gz"))
    assert len(files) == 1
    with gzip.open(files[0], "rt", encoding="utf-8") as fh:
        event = json.loads(fh.readline())
    payload = event["payload"]

    # El email original NO debe estar en el chunk; queda el placeholder fijo.
    assert "juan.perez@cliente.com" not in payload["content"]
    assert "[PII_EMAIL]" in payload["content"]
    # normalized_hash recomputado sobre el contenido redactado: import no falla checksum.
    assert payload["normalized_hash"] == memory_store._normalized_hash(
        payload["title"], payload["content"]
    )


def test_sync_run_api_defaults_to_disabled(tmp_path, monkeypatch):
    from services import memory_store

    monkeypatch.setenv("STACKY_HOME", str(tmp_path / "Stacky"))
    monkeypatch.delenv("STACKY_MEMORY_GIT_SYNC_ENABLED", raising=False)
    project = "MEM_SYNC_GOV"
    memory_store.save_observation(
        project=project,
        type="client_policy",
        title="Should not export",
        content="bare POST must not enable sync",
        scope="project",
        status="active",
    )
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as client:
        # POST sin "enabled": cae al flag de entorno (OFF) → no exporta nada.
        run = client.post("/api/memory/sync/run", json={"project": project})
        assert run.status_code == 200
        payload = run.get_json()
        assert payload["enabled"] is False
        assert payload["exported_events"] == 0
