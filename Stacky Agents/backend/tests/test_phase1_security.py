from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture
def fake_dpapi(monkeypatch):
    import services.secrets_store as secrets_store

    monkeypatch.setattr(
        secrets_store,
        "_protect_bytes",
        lambda data: b"enc::" + data,
    )
    monkeypatch.setattr(
        secrets_store,
        "_unprotect_bytes",
        lambda data: data.split(b"enc::", 1)[1],
    )
    return secrets_store


@pytest.fixture
def isolated_client(tmp_path, monkeypatch):
    import app as app_module
    import project_manager
    import api.projects as projects_api

    projects_dir = tmp_path / "projects"
    active_file = tmp_path / "data" / "active_project.json"

    monkeypatch.setattr(project_manager, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(project_manager, "ACTIVE_FILE", active_file)
    monkeypatch.setattr(projects_api, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(app_module, "_startup_sync", lambda logger: None)

    app = app_module.create_app()
    app.config.update(TESTING=True)
    with app.test_client() as client:
        yield client, projects_dir


def test_init_project_rejects_nonexistent_workspace(isolated_client):
    client, _ = isolated_client

    response = client.post(
        "/api/init_project",
        json={
            "name": "RSPACIFICO",
            "display_name": "RS Pacífico",
            "workspace_root": "Z:/ruta/que/no/existe",
            "tracker_type": "azure_devops",
            "organization": "UbimiaPacifico",
            "ado_project": "Strategist_Pacifico",
        },
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "workspace_root no existe" in payload["error"]


def test_init_project_persists_docs_paths(isolated_client, tmp_path):
    client, projects_dir = isolated_client
    workspace = tmp_path / "workspace"
    technical = tmp_path / "docs" / "technical"
    functional = tmp_path / "docs" / "functional"
    workspace.mkdir()
    technical.mkdir(parents=True)
    functional.mkdir(parents=True)

    response = client.post(
        "/api/init_project",
        json={
            "name": "ACME",
            "display_name": "ACME",
            "workspace_root": str(workspace),
            "docs_paths": {
                "technical": str(technical),
                "functional": str(functional),
            },
            "tracker_type": "azure_devops",
            "organization": "Org",
            "ado_project": "AdoProject",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["project"]["docs_paths"]["technical"].endswith("/technical")
    saved = json.loads((projects_dir / "ACME" / "config.json").read_text(encoding="utf-8"))
    assert saved["docs_paths"]["functional"].endswith("/functional")


def test_test_docs_paths_counts_markdown_and_pdf(isolated_client, tmp_path):
    client, _ = isolated_client
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (docs / "manual.pdf").write_bytes(b"%PDF-1.4")

    response = client.post(
        "/api/projects/NEW/test_docs_paths",
        json={"docs_paths": {"technical": str(docs), "functional": ""}},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["counts"]["technical"]["md"] == 1
    assert payload["counts"]["technical"]["pdf"] == 1


def test_write_jira_auth_encrypts_token(fake_dpapi, tmp_path, monkeypatch):
    import project_manager
    from services.secrets_store import read_secret_from_file

    monkeypatch.setattr(project_manager, "PROJECTS_DIR", tmp_path / "projects")

    auth_path = project_manager.write_jira_auth(
        name="B2IMPACT",
        url="https://jira.example.com",
        user="qa@example.com",
        token="jira-secret-token",
    )

    raw_payload = json.loads(auth_path.read_text(encoding="utf-8"))
    assert raw_payload["user"] == "qa@example.com"
    assert raw_payload["token"] != "jira-secret-token"
    assert raw_payload["token_format"] == "dpapi"

    resolved = read_secret_from_file(auth_path, "token", format_field="token_format")
    assert resolved.value == "jira-secret-token"


def test_ado_pat_file_is_migrated_from_legacy_plaintext(fake_dpapi, tmp_path):
    from services.ado_client import _read_pat_file

    auth_path = tmp_path / "ado_auth.json"
    auth_path.write_text(
        json.dumps({"pat": "legacy-plain-pat", "pat_format": "raw"}, indent=2),
        encoding="utf-8",
    )

    encoded = _read_pat_file(auth_path)

    assert encoded is not None
    migrated_payload = json.loads(auth_path.read_text(encoding="utf-8"))
    assert migrated_payload["pat"] != "legacy-plain-pat"
    assert migrated_payload["pat_format"] == "dpapi"
