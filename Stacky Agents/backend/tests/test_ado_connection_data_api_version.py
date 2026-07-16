"""Plan 148 F0 — D9: connectionData debe usar api-version con sufijo -preview.

ADO trata `_apis/connectionData` como recurso PREVIEW; con `api-version=7.1` a
secas responde "under preview. The -preview flag must be supplied", por lo que
`get_authenticated_user` nunca resolvía la identidad. El fix agrega una
constante propia `_CONNECTION_DATA_API_VERSION = "7.1-preview"` usada SOLO en
connectionData; los endpoints GA (wiql/workitems/workitemtypes/attachments)
deben seguir en `_API_VERSION = "7.1"` sin sufijo.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture
def ado_client():
    """AdoClient con auth hardcodeada — sin resolver PAT real ni pegarle a la red."""
    from services.ado_client import AdoClient
    with patch("services.ado_client._resolve_auth_header", return_value="Basic dGVzdA=="):
        client = AdoClient(org="TestOrg", project="TestProject")
    return client


def test_connection_data_url_uses_preview(ado_client, monkeypatch):
    """get_authenticated_user pide connectionData con api-version=7.1-preview."""
    captured_urls: list[str] = []

    def fake_request(self, method, url, body=None):
        captured_urls.append(url)
        return {"authenticatedUser": {"uniqueName": "x@y.com", "providerDisplayName": "X"}}

    monkeypatch.setattr("services.ado_client.AdoClient._request", fake_request)

    result = ado_client.get_authenticated_user()

    assert len(captured_urls) == 1
    assert "/_apis/connectionData?api-version=7.1-preview" in captured_urls[0]
    assert result["unique_name"] == "x@y.com"


def test_ga_endpoints_still_ga(ado_client, monkeypatch):
    """Un endpoint GA (workitemtypes) NO lleva el sufijo -preview: sigue en 7.1 a secas."""
    captured_urls: list[str] = []

    def fake_request(self, method, url, body=None):
        captured_urls.append(url)
        return {"value": []}

    monkeypatch.setattr("services.ado_client.AdoClient._request", fake_request)

    ado_client.fetch_states()

    assert len(captured_urls) == 1
    assert "api-version=7.1" in captured_urls[0]
    assert "-preview" not in captured_urls[0]
