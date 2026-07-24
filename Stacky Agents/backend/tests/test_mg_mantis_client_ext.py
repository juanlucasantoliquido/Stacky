"""tests/test_mg_mantis_client_ext.py — Plan 217 F2a (C6).

Valida los 2 métodos NUEVOS aditivos de `services/mantis_client.py`
(`MantisClient.fetch_all_issues` y `MantisClient.download_attachment_binary`),
sin tocar ni un test de `fetch_open_issues`/`fetch_attachments` existentes.

Mockea `urllib.request.urlopen` con el mismo patrón que
`test_ado_client_extensions.py` (helpers `_make_http_response`/`_make_http_error`).
"""
from __future__ import annotations

import base64
import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from services.mantis_client import MantisApiError, MantisClient, MantisConfigError


def _make_http_response(body, status: int = 200, headers: dict | None = None):
    """Simula un objeto HTTPResponse de urllib. `body` puede ser dict (se
    serializa a JSON) o bytes crudos (para respuestas binarias)."""
    raw = json.dumps(body).encode("utf-8") if isinstance(body, dict) else body
    resp = MagicMock()
    resp.read.return_value = raw
    resp.status = status
    hdrs = headers or {}

    class _FakeHeaders:
        def get(self, key, default=None):
            return hdrs.get(key, default)

    resp.headers = _FakeHeaders()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _make_http_error(code: int, body: str = ""):
    class FakeHeaders:
        def get(self, key, default=None):
            return default

    return urllib.error.HTTPError(
        url="https://fake",
        code=code,
        msg=f"HTTP {code}",
        hdrs=FakeHeaders(),
        fp=io.BytesIO(body.encode("utf-8")),
    )


@pytest.fixture
def mantis_client():
    return MantisClient(
        url="https://mantis.ejemplo.local",
        project_id="310",
        token="fake-token",
    )


# ── fetch_all_issues ─────────────────────────────────────────────────────


def test_fetch_all_issues_incluye_resueltos_y_cerrados(mantis_client):
    """A diferencia de fetch_open_issues, NO filtra por _RESOLVED_STATUS_IDS
    (80=resolved, 90=closed) — el issue resuelto debe aparecer."""
    page1 = {
        "issues": [
            {"id": 1, "summary": "Abierto", "status": {"id": 10, "label": "new"}},
            {"id": 2, "summary": "Resuelto", "status": {"id": 80, "label": "resolved"}},
            {"id": 3, "summary": "Cerrado", "status": {"id": 90, "label": "closed"}},
        ]
    }

    def fake_urlopen(req, timeout=None, context=None):
        return _make_http_response(page1)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        issues = mantis_client.fetch_all_issues()

    assert len(issues) == 3
    ids = {i["id"] for i in issues}
    assert ids == {1, 2, 3}


def test_fetch_all_issues_pagina_hasta_pagina_incompleta(mantis_client):
    call_count = {"n": 0}

    def fake_urlopen(req, timeout=None, context=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            issues = [{"id": i, "status": {"id": 90}} for i in range(50)]
            return _make_http_response({"issues": issues})
        return _make_http_response({"issues": [{"id": 999, "status": {"id": 10}}]})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        issues = mantis_client.fetch_all_issues()

    assert call_count["n"] == 2
    assert len(issues) == 51


def test_fetch_all_issues_sin_project_id_lanza_config_error():
    client = MantisClient(url="https://mantis.ejemplo.local", project_id="", token="fake-token")
    with pytest.raises(MantisConfigError):
        client.fetch_all_issues()


# ── download_attachment_binary ───────────────────────────────────────────


def test_download_attachment_binary_devuelve_bytes_crudos(mantis_client):
    raw_bytes = b"\x89PNG\r\n\x1a\nfake-binary-content"

    def fake_urlopen(req, timeout=None, context=None):
        return _make_http_response(raw_bytes, headers={"Content-Type": "image/png"})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = mantis_client.download_attachment_binary("501")

    assert result == raw_bytes
    assert isinstance(result, bytes)


def test_download_attachment_binary_decodifica_json_base64(mantis_client):
    original = b"contenido de prueba en base64"
    encoded = base64.b64encode(original).decode("ascii")
    body = {"content": encoded}

    def fake_urlopen(req, timeout=None, context=None):
        return _make_http_response(body, headers={"Content-Type": "application/json"})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = mantis_client.download_attachment_binary("501")

    assert result == original


def test_download_attachment_binary_propaga_http_error_como_mantis_api_error(mantis_client):
    def fake_urlopen(req, timeout=None, context=None):
        raise _make_http_error(404, "not found")

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with pytest.raises(MantisApiError):
            mantis_client.download_attachment_binary("999")
