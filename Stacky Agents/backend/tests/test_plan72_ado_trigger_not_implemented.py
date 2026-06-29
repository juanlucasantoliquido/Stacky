"""Plan 72 F3 — AdoCIProvider.trigger_pipeline lanza NotImplementedError.

2 casos:
  1. AdoCIProvider().trigger_pipeline → NotImplementedError con "v1".
  2. Endpoint POST /api/ci/.../trigger + confirm=True + ADO provider → 501.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

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
# Caso 1 — trigger_pipeline lanza NotImplementedError con "v1"
# ---------------------------------------------------------------------------
def test_ado_ci_trigger_not_implemented():
    from services.ado_ci_provider import AdoCIProvider
    from services.ci_provider import ItemRef

    provider = AdoCIProvider.__new__(AdoCIProvider)
    with pytest.raises(NotImplementedError, match="v1"):
        provider.trigger_pipeline(ItemRef(item_id="1", tracker_type="azure_devops"), "main")


# ---------------------------------------------------------------------------
# Caso 2 — Endpoint con ADO provider → 501
# ---------------------------------------------------------------------------
def test_trigger_endpoint_ado_returns_501(client, monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_PIPELINE_TRIGGER_ENABLED", True)

    mock_provider = MagicMock()
    mock_provider.name = "azure_devops"
    mock_provider.trigger_pipeline.side_effect = NotImplementedError(
        "trigger_pipeline ADO fuera de scope v1 — usar push o Azure Pipelines REST directo"
    )

    with patch("api.ci.get_ci_provider", return_value=mock_provider), \
         patch("api.ci._read_pat_scopes", return_value=None):
        resp = client.post("/api/ci/adoproject/trigger", json={
            "confirm": True,
            "ref": "main",
            "sha": "abc",
        })

    assert resp.status_code == 501
    data = resp.get_json()
    assert "v1" in data["error"] or "ADO" in data["error"] or "scope" in data["error"].lower()
