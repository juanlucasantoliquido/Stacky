"""tests/test_mg_adapters_api.py — Plan 217 F2a (después del scraping, C6).

Valida `tools/migrar_mantis_gitlab/adapters/api_adapter.py`: `MantisApiReadAdapter`
delega correctamente en un `MantisClient` real (mocks HTTP de alto nivel vía
`urllib.request.urlopen`, sin red real) y rechaza `MantisSOAPClient` con
`NotImplementedError` explícito (limitación declarada de este batch).
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from services.mantis_client import MantisClient, MantisSOAPClient
from tools.migrar_mantis_gitlab.adapters.api_adapter import MantisApiReadAdapter


def _make_http_response(body: dict):
    raw = json.dumps(body).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = raw
    resp.headers = MagicMock()
    resp.headers.get.return_value = "application/json"
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


@pytest.fixture
def api_adapter():
    client = MantisClient(
        url="https://mantis.ejemplo.local", project_id="310", token="fake-token"
    )
    return MantisApiReadAdapter(client), client


def test_fetch_all_issues_delega_en_mantis_client(api_adapter):
    adapter, _client = api_adapter

    def fake_urlopen(req, timeout=None, context=None):
        return _make_http_response({
            "issues": [
                {"id": 1, "summary": "uno", "status": {"id": 80}},
                {"id": 2, "summary": "dos", "status": {"id": 10}},
            ]
        })

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        issues = adapter.fetch_all_issues()

    assert len(issues) == 2
    assert {i["id"] for i in issues} == {1, 2}


def test_fetch_comments_delega_en_fetch_notes(api_adapter):
    adapter, _client = api_adapter

    def fake_urlopen(req, timeout=None, context=None):
        return _make_http_response({
            "id": 1,
            "notes": [{"id": 10, "text": "nota de ejemplo", "reporter": {"name": "demo"}}],
        })

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        comments = adapter.fetch_comments(1)

    assert len(comments) == 1
    assert comments[0]["text"] == "nota de ejemplo"


def test_fetch_attachments_delega_en_mantis_client(api_adapter):
    adapter, _client = api_adapter

    def fake_urlopen(req, timeout=None, context=None):
        return _make_http_response({
            "id": 1,
            "attachments": [{"id": "501", "file_name": "demo.txt", "size": 10}],
        })

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        attachments = adapter.fetch_attachments(1)

    assert len(attachments) == 1
    assert attachments[0]["name"] == "demo.txt"


def test_fetch_relationships_declara_gap_como_lista_vacia(api_adapter):
    adapter, _client = api_adapter
    # No debe llegar a hacer red: MantisClient (REST) no expone relaciones
    # estructuradas en este batch -> gap declarado, no inventado.
    assert adapter.fetch_relationships(1) == []


def test_download_attachment_binary_delega_en_mantis_client(api_adapter):
    adapter, _client = api_adapter
    raw_bytes = b"contenido-binario-de-prueba"

    def fake_urlopen(req, timeout=None, context=None):
        resp = MagicMock()
        resp.read.return_value = raw_bytes
        resp.headers = MagicMock()
        resp.headers.get.return_value = "application/octet-stream"
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = adapter.download_attachment_binary("501")

    assert result == raw_bytes


def test_soap_client_rechazado_con_not_implemented_error():
    soap_client = MantisSOAPClient.__new__(MantisSOAPClient)  # sin __init__ (evita WSDL real)
    with pytest.raises(NotImplementedError, match="scraping"):
        MantisApiReadAdapter(soap_client)
