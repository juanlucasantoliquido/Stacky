"""Plan 79 — F5: validación de la config contra los estados reales del tracker."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from harness.task_states import validate_states_against_tracker  # noqa: E402


def test_warns_on_unknown_ado_state():
    valid = ["New", "Active", "Done"]
    profile = {"tracker_state_machine": {"developer": {"next_state_ok": "Finiquitado"}}}
    warnings = validate_states_against_tracker(profile, valid)
    assert len(warnings) == 1
    assert warnings[0]["agent_type"] == "developer"
    assert warnings[0]["field"] == "next_state_ok"
    assert warnings[0]["value"] == "Finiquitado"
    assert warnings[0]["reason"] == "state_not_in_tracker"


def test_no_warning_when_valid():
    valid = ["New", "Active", "Done"]
    profile = {"tracker_state_machine": {"developer": {"in_progress": "Active", "next_state_ok": "Done"}}}
    assert validate_states_against_tracker(profile, valid) == []


def test_gitlab_logical_states_ok():
    valid = ["functional", "accepted", "in_progress"]
    profile = {"tracker_state_machine": {"developer": {"in_progress": "in_progress"}}}
    assert validate_states_against_tracker(profile, valid) == []


def test_empty_valid_states_no_validation():
    profile = {"tracker_state_machine": {"developer": {"in_progress": "Anything"}}}
    assert validate_states_against_tracker(profile, []) == []


def test_pure_never_raises():
    assert validate_states_against_tracker(None, ["Active"]) == []
    assert validate_states_against_tracker(123, ["Active"]) == []
    assert validate_states_against_tracker({"tracker_state_machine": "x"}, ["Active"]) == []


# ── Wiring endpoint-level: PUT /api/projects/<name>/client-profile ──────────


@pytest.fixture()
def client(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)

    from app import create_app
    import project_manager
    import services.client_profile as cp
    import api.client_profile as api_cp

    monkeypatch.setattr(project_manager, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(cp, "projects_dir", lambda: projects_dir)
    monkeypatch.setattr(api_cp, "PROJECTS_DIR", projects_dir)

    pdir = projects_dir / "RSPACIFICO"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "config.json").write_text(json.dumps({
        "name": "RSPACIFICO",
        "display_name": "RSPACIFICO",
        "issue_tracker": {"type": "azure_devops"},
    }, indent=2), encoding="utf-8")

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def test_put_client_profile_includes_state_warnings_for_unknown_state(client):
    provider = MagicMock()
    provider.fetch_states.return_value = ["New", "Active", "Done"]
    with patch("api.client_profile.get_tracker_provider", return_value=provider):
        resp = client.put(
            "/api/projects/RSPACIFICO/client-profile",
            json={"profile": {"tracker_state_machine": {"developer": {"next_state_ok": "Finiquitado"}}}},
        )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert "state_warnings" in body
    assert any(w["value"] == "Finiquitado" for w in body["state_warnings"])


def test_put_client_profile_no_state_warnings_when_valid(client):
    provider = MagicMock()
    provider.fetch_states.return_value = ["New", "Active", "Done"]
    with patch("api.client_profile.get_tracker_provider", return_value=provider):
        resp = client.put(
            "/api/projects/RSPACIFICO/client-profile",
            json={"profile": {"tracker_state_machine": {"developer": {"in_progress": "Active", "next_state_ok": "Done"}}}},
        )
    assert resp.status_code == 200
    assert resp.get_json()["state_warnings"] == []


def test_put_client_profile_fetch_states_failure_does_not_break_save(client):
    provider = MagicMock()
    provider.fetch_states.side_effect = Exception("tracker unreachable")
    with patch("api.client_profile.get_tracker_provider", return_value=provider):
        resp = client.put(
            "/api/projects/RSPACIFICO/client-profile",
            json={"profile": {"tracker_state_machine": {"developer": {"next_state_ok": "Anything"}}}},
        )
    assert resp.status_code == 200
    assert resp.get_json()["state_warnings"] == []
