"""Plan 72 F4 — Tests del endpoint GET /api/ci/<project>/trigger-preview.

4 casos según el plan (C5 — TDD del backend nuevo):
  1. Flag OFF → GET trigger-preview → 404.
  2. Flag ON + ref=develop + last_pipeline mockeado → 200 con kind="branch", ref="develop".
  3. [C5] Trigger reciente → would_reuse=True, existing_pipeline_id no nulo (should_trigger
     llamado UNA vez con sha del último pipeline, no "").
  4. last_pipeline_for_ref con fetch_pipelines vacío → None; con lista → primer ítem.
     AdoCIProvider.last_pipeline_for_ref → None.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
import config


@pytest.fixture()
def app():
    from app import create_app
    _app = create_app()
    _app.config["TESTING"] = True
    return _app


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_stores():
    import api.ci as ci_mod
    ci_mod._RECENT_TRIGGERS.clear()
    ci_mod._ACTIVE_POLLS.clear()
    yield
    ci_mod._RECENT_TRIGGERS.clear()
    ci_mod._ACTIVE_POLLS.clear()


# ---------------------------------------------------------------------------
# Caso 1 — Flag OFF → 404
# ---------------------------------------------------------------------------
def test_preview_flag_off_returns_404(client, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", False)
    resp = client.get("/api/ci/myproject/trigger-preview?ref=develop")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Caso 2 — Flag ON + last_pipeline mockeado → 200 con kind + ref
# ---------------------------------------------------------------------------
def test_preview_returns_kind_and_ref(client, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", True)
    mock_provider = MagicMock()
    mock_provider.name = "gitlab"
    mock_provider.last_pipeline_for_ref.return_value = {
        "id": "7", "status": "success", "sha": "abc777", "ref": "develop",
    }

    with patch("api.ci.get_ci_provider", return_value=mock_provider):
        resp = client.get("/api/ci/myproject/trigger-preview?ref=develop")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["kind"] == "branch"
    assert data["ref"] == "develop"
    assert data["last_pipeline"]["id"] == "7"


# ---------------------------------------------------------------------------
# Caso 3 — [C5] Trigger reciente → would_reuse=True con sha del pipeline real
# ---------------------------------------------------------------------------
def test_preview_would_reuse_when_recent_trigger(client, monkeypatch):
    import api.ci as ci_mod
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", True)

    # Pre-sembrar store con sha del pipeline real
    ci_mod._RECENT_TRIGGERS[("gitlab", "develop")] = {
        "ref": "develop",
        "sha": "abc777",  # mismo sha que last_pipeline
        "pipeline_id": "55",
        "ts": time.time(),
    }

    mock_provider = MagicMock()
    mock_provider.name = "gitlab"
    mock_provider.last_pipeline_for_ref.return_value = {
        "id": "55", "status": "success", "sha": "abc777", "ref": "develop",
    }

    with patch("api.ci.get_ci_provider", return_value=mock_provider):
        resp = client.get("/api/ci/myproject/trigger-preview?ref=develop")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["would_reuse"] is True
    assert data["existing_pipeline_id"] == "55"


# ---------------------------------------------------------------------------
# Caso 4 — last_pipeline_for_ref en adapters
# ---------------------------------------------------------------------------
def test_gitlab_last_pipeline_for_ref_empty():
    from services.gitlab_ci_provider import GitLabCIProvider

    provider = GitLabCIProvider.__new__(GitLabCIProvider)
    mock_delegate = MagicMock()
    mock_delegate.fetch_pipelines.return_value = []
    provider._delegate = mock_delegate

    result = provider.last_pipeline_for_ref("develop")
    assert result is None


def test_gitlab_last_pipeline_for_ref_returns_first():
    from services.gitlab_ci_provider import GitLabCIProvider

    provider = GitLabCIProvider.__new__(GitLabCIProvider)
    mock_delegate = MagicMock()
    mock_delegate.fetch_pipelines.return_value = [
        {"id": "7", "status": "success"},
        {"id": "6", "status": "failed"},
    ]
    provider._delegate = mock_delegate

    result = provider.last_pipeline_for_ref("develop")
    assert result is not None
    assert result["id"] == "7"


def test_ado_last_pipeline_for_ref_returns_none():
    from services.ado_ci_provider import AdoCIProvider

    provider = AdoCIProvider.__new__(AdoCIProvider)
    result = provider.last_pipeline_for_ref("main")
    assert result is None
