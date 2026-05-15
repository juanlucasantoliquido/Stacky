"""Tests unitarios para las extensiones de AdoClient (Fase 2).

TU-01a  create_work_item construye JSON Patch correcto con Hierarchy-Reverse.
TU-01b  create_work_item pasa Content-Type: application/json-patch+json.
TU-02a  upload_attachment hace POST con stream binario y fileName correcto.
TU-02b  link_attachment_to_work_item hace PATCH con rel: AttachedFile.
TU-09a  _request_with_retry reintenta 3 veces en 429 con backoff.
TU-09b  Respeta header Retry-After (máx 30 s clampeado).
TU-09c  Eleva AdoApiError con correlation_id tras agotar reintentos.
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


# ---------------------------------------------------------------------------
# Helpers para mockear urllib
# ---------------------------------------------------------------------------

def _make_http_response(body: dict, status: int = 200):
    """Simula un objeto HTTPResponse de urllib."""
    raw = json.dumps(body).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = raw
    resp.status = status
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _make_http_error(code: int, body: str = "", headers=None):
    """Simula urllib.error.HTTPError."""
    hdrs = headers or {}

    class FakeHeaders:
        def get(self, key, default=None):
            return hdrs.get(key, default)

    err = urllib.error.HTTPError(
        url="https://fake",
        code=code,
        msg=f"HTTP {code}",
        hdrs=FakeHeaders(),
        fp=io.BytesIO(body.encode("utf-8")),
    )
    return err


# ---------------------------------------------------------------------------
# Fixture: AdoClient pre-autenticado (sin llamadas reales)
# ---------------------------------------------------------------------------

@pytest.fixture
def ado_client():
    """Retorna un AdoClient con auth hardcodeada para tests — sin resolver PAT."""
    from services.ado_client import AdoClient
    with patch("services.ado_client._resolve_auth_header", return_value="Basic dGVzdA=="):
        client = AdoClient(org="TestOrg", project="TestProject")
    return client


# ---------------------------------------------------------------------------
# TU-01a — create_work_item construye JSON Patch correcto
# ---------------------------------------------------------------------------

def test_create_work_item_json_patch_structure(ado_client):
    """TU-01a: El JSON Patch incluye Title, Description, State y Hierarchy-Reverse."""
    captured_body: list[list] = []

    def fake_urlopen(req, timeout):
        # Capturar el body del request para inspección
        body_bytes = req.data
        body = json.loads(body_bytes.decode("utf-8"))
        captured_body.append(body)
        return _make_http_response({"id": 1234, "url": "https://fake/1234"})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = ado_client.create_work_item(
            work_item_type="Task",
            fields={
                "System.Title": "RF-001 — Test Task",
                "System.Description": "<p>Test</p>",
                "System.State": "Technical review",
            },
            parent_ado_id=149,
        )

    assert result["id"] == 1234
    assert len(captured_body) == 1
    patch_ops = captured_body[0]

    # Verificar cada operación del patch
    ops_by_path = {op["path"]: op for op in patch_ops}

    assert "/fields/System.Title" in ops_by_path
    assert ops_by_path["/fields/System.Title"]["value"] == "RF-001 — Test Task"

    assert "/fields/System.Description" in ops_by_path
    assert ops_by_path["/fields/System.Description"]["value"] == "<p>Test</p>"

    assert "/fields/System.State" in ops_by_path
    assert ops_by_path["/fields/System.State"]["value"] == "Technical review"

    # Verificar relación Hierarchy-Reverse
    hierarchy_ops = [
        op for op in patch_ops
        if op["path"] == "/relations/-"
        and isinstance(op.get("value"), dict)
        and op["value"].get("rel") == "System.LinkTypes.Hierarchy-Reverse"
    ]
    assert len(hierarchy_ops) == 1, "Debe haber exactamente 1 operación de Hierarchy-Reverse"
    rel_value = hierarchy_ops[0]["value"]
    assert "149" in rel_value["url"], "La URL de la relación debe incluir el ado_id del Epic padre"


# ---------------------------------------------------------------------------
# TU-01b — create_work_item pasa Content-Type correcto
# ---------------------------------------------------------------------------

def test_create_work_item_content_type(ado_client):
    """TU-01b: Content-Type debe ser application/json-patch+json."""
    captured_req: list = []

    def fake_urlopen(req, timeout):
        captured_req.append(req)
        return _make_http_response({"id": 999, "url": "https://fake/999"})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        ado_client.create_work_item(
            work_item_type="Task",
            fields={"System.Title": "Test"},
            parent_ado_id=149,
        )

    assert len(captured_req) == 1
    req = captured_req[0]
    ct = req.get_header("Content-type")
    assert ct == "application/json-patch+json", (
        f"Content-Type esperado 'application/json-patch+json', recibido '{ct}'"
    )


# ---------------------------------------------------------------------------
# TU-02a — upload_attachment POST con stream binario y fileName
# ---------------------------------------------------------------------------

def test_upload_attachment_request_shape(ado_client, tmp_path):
    """TU-02a: POST a _apis/wit/attachments con fileName en querystring y body binario."""
    test_file = tmp_path / "plan-de-pruebas.md"
    test_file.write_bytes(b"# Plan de Pruebas\n\nContenido de prueba.")

    captured: list = []

    def fake_urlopen(req, timeout):
        captured.append(req)
        return _make_http_response({
            "id": "aaa-bbb-ccc",
            "url": "https://dev.azure.com/attachments/aaa-bbb-ccc",
        })

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = ado_client.upload_attachment(
            file_path=test_file,
            file_name="plan-de-pruebas.md",
        )

    assert result["id"] == "aaa-bbb-ccc"
    assert len(captured) == 1
    req = captured[0]

    # Verificar URL tiene fileName en query string
    assert "fileName=plan-de-pruebas.md" in req.full_url or "fileName=plan-de-pruebas.md" in req.get_full_url()

    # Verificar que el body es el contenido binario del archivo
    assert req.data == b"# Plan de Pruebas\n\nContenido de prueba."

    # Verificar Content-Type para stream binario
    ct = req.get_header("Content-type")
    assert "octet-stream" in ct or "application/octet-stream" in ct


# ---------------------------------------------------------------------------
# TU-02b — link_attachment_to_work_item hace PATCH con rel AttachedFile
# ---------------------------------------------------------------------------

def test_link_attachment_to_work_item_patch_shape(ado_client):
    """TU-02b: PATCH work item con operación add de relación AttachedFile."""
    captured: list = []

    def fake_urlopen(req, timeout):
        captured.append(req)
        body = json.loads(req.data.decode("utf-8"))
        return _make_http_response({"id": 1234, "relations": [body]})

    attachment_url = "https://dev.azure.com/attachments/aaa-bbb-ccc"
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        ado_client.link_attachment_to_work_item(
            work_item_id=1234,
            attachment_url=attachment_url,
            comment="Plan de pruebas - RF-001",
        )

    assert len(captured) == 1
    req = captured[0]
    assert req.method == "PATCH"
    assert "1234" in req.full_url or "1234" in req.get_full_url()

    body = json.loads(req.data.decode("utf-8"))
    assert isinstance(body, list), "El body debe ser una lista de operaciones JSON Patch"

    attach_ops = [
        op for op in body
        if op.get("path") == "/relations/-"
        and isinstance(op.get("value"), dict)
        and op["value"].get("rel") == "AttachedFile"
    ]
    assert len(attach_ops) == 1
    assert attach_ops[0]["value"]["url"] == attachment_url
    assert attach_ops[0]["value"]["attributes"]["comment"] == "Plan de pruebas - RF-001"


# ---------------------------------------------------------------------------
# TU-09a — _request_with_retry reintenta 3 veces en 429 con backoff
# ---------------------------------------------------------------------------

def test_retry_on_429(ado_client):
    """TU-09a: Reintenta hasta 3 veces en 429; a la 3ª vez con éxito, retorna resultado."""
    call_count = [0]
    sleep_calls: list[float] = []

    def fake_urlopen(req, timeout):
        call_count[0] += 1
        if call_count[0] < 3:
            raise _make_http_error(429, "Too Many Requests")
        return _make_http_response({"id": 1, "success": True})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)):
            result = ado_client._request_with_retry("GET", "https://fake/test")

    assert result["success"] is True
    assert call_count[0] == 3
    # Backoff: primer sleep ~1s, segundo ~2s
    assert len(sleep_calls) == 2
    assert sleep_calls[0] < sleep_calls[1], "Backoff debe ser creciente"
    assert sleep_calls[0] >= 1.0
    assert sleep_calls[1] >= 2.0


def test_retry_on_503(ado_client):
    """TU-09a (variante): Reintenta en 503 con el mismo comportamiento."""
    call_count = [0]
    sleep_calls: list[float] = []

    def fake_urlopen(req, timeout):
        call_count[0] += 1
        if call_count[0] < 2:
            raise _make_http_error(503, "Service Unavailable")
        return _make_http_response({"ok": True})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)):
            result = ado_client._request_with_retry("GET", "https://fake/test")

    assert result["ok"] is True
    assert call_count[0] == 2


# ---------------------------------------------------------------------------
# TU-09b — Respeta header Retry-After (máx 30 s clampeado)
# ---------------------------------------------------------------------------

def test_retry_after_header_respected(ado_client):
    """TU-09b: Si ADO responde con Retry-After: 60, espera máx 30s (clamp)."""
    call_count = [0]
    sleep_calls: list[float] = []

    def fake_urlopen(req, timeout):
        call_count[0] += 1
        if call_count[0] == 1:
            raise _make_http_error(429, "Too Many Requests", headers={"Retry-After": "60"})
        return _make_http_response({"ok": True})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)):
            ado_client._request_with_retry("GET", "https://fake/test")

    assert len(sleep_calls) >= 1
    assert sleep_calls[0] == 30.0, f"Esperado 30s (clamped), recibido {sleep_calls[0]}"


def test_retry_after_small_value_not_clamped(ado_client):
    """TU-09b (variante): Retry-After: 5 → espera exactamente 5s."""
    sleep_calls: list[float] = []
    call_count = [0]

    def fake_urlopen(req, timeout):
        call_count[0] += 1
        if call_count[0] == 1:
            raise _make_http_error(429, "Too Many Requests", headers={"Retry-After": "5"})
        return _make_http_response({"ok": True})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)):
            ado_client._request_with_retry("GET", "https://fake/test")

    assert len(sleep_calls) >= 1
    assert sleep_calls[0] == 5.0


# ---------------------------------------------------------------------------
# TU-09c — Eleva AdoApiError con correlation_id tras agotar reintentos
# ---------------------------------------------------------------------------

def test_retry_exhausted_raises_with_correlation_id(ado_client):
    """TU-09c: Tras 3 intentos fallidos, eleva AdoApiError con correlation_id."""
    from services.ado_client import AdoApiError

    call_count = [0]

    def fake_urlopen(req, timeout):
        call_count[0] += 1
        raise _make_http_error(503, "Service Unavailable")

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with patch("time.sleep"):
            with pytest.raises(AdoApiError) as exc_info:
                ado_client._request_with_retry("GET", "https://fake/test")

    assert call_count[0] == 3, "Deben haberse hecho exactamente 3 intentos"
    error_msg = str(exc_info.value)
    assert "503" in error_msg or "Service Unavailable" in error_msg
    # correlation_id debe estar disponible en el error o en el atributo
    exc = exc_info.value
    assert hasattr(exc, "correlation_id"), "AdoApiError debe tener atributo correlation_id"
    assert exc.correlation_id is not None and len(exc.correlation_id) > 0
