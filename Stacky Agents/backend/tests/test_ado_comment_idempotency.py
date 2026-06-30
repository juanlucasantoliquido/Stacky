"""Plan 52 F1 — Idempotencia robusta de comentarios: comment_exists recorre
TODAS las páginas de comentarios (no solo las 50 más recientes), siguiendo
continuationToken con un tope duro de páginas.
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
    from services.ado_client import AdoClient
    with patch("services.ado_client._resolve_auth_header", return_value="Basic dGVzdA=="):
        client = AdoClient(org="TestOrg", project="TestProject")
    return client


_MARKER = "<!-- stacky:issue-phase:funcional -->"


def test_comment_exists_finds_marker_on_second_page(ado_client):
    pages = [
        {"comments": [{"text": "ruido"} for _ in range(50)], "continuationToken": "tok1"},
        {"comments": [{"text": f"{_MARKER} cuerpo"}]},  # sin continuationToken
    ]
    calls = []

    def fake_request(method, url, *a, **k):
        calls.append(url)
        return pages[len(calls) - 1]

    with patch.object(ado_client, "_request", side_effect=fake_request):
        found = ado_client.comment_exists(1, _MARKER)
    assert found is not None
    assert _MARKER in found.get("text", "")
    assert len(calls) == 2


def test_comment_exists_returns_none_when_marker_absent_across_all_pages(ado_client):
    pages = [
        {"comments": [{"text": "uno"}], "continuationToken": "tok1"},
        {"comments": [{"text": "dos"}]},
    ]
    calls = []

    def fake_request(method, url, *a, **k):
        calls.append(url)
        return pages[len(calls) - 1]

    with patch.object(ado_client, "_request", side_effect=fake_request):
        assert ado_client.comment_exists(1, _MARKER) is None
    assert len(calls) == 2


def test_comment_exists_stops_at_page_cap(ado_client):
    from services import ado_client as mod

    def fake_request(method, url, *a, **k):
        # Paginación infinita simulada: siempre devuelve continuationToken.
        return {"comments": [{"text": "ruido"}], "continuationToken": "always"}

    with patch.object(ado_client, "_request", side_effect=fake_request) as m:
        result = ado_client.comment_exists(1, _MARKER)
    assert result is None
    assert m.call_count <= mod._COMMENT_PAGE_CAP


def test_comment_exists_empty_marker_returns_none_without_http(ado_client):
    with patch.object(ado_client, "_request") as m:
        assert ado_client.comment_exists(1, "") is None
    m.assert_not_called()
