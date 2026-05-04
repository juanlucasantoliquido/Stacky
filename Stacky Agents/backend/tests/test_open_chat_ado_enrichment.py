"""Tests para el enriquecimiento ADO en el endpoint /api/agents/open-chat.

Verifica que `_build_ado_enrichment_sections` (api/agents.py):
  - devuelve secciones markdown con `## Comentarios ADO` y `## Adjuntos`
  - usa el helper `_html_to_text` para limpiar HTML de comentarios
  - inlinea `text_content` de adjuntos textuales
  - silencia errores de AdoClient sin romper el flujo del endpoint

No toca ADO real: mockea `AdoClient` con un fake controlado.
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


class _FakeAdoClient:
    """Doble de AdoClient con respuestas controladas por el test."""

    def __init__(self, comments=None, attachments=None, raise_on=None):
        self._comments = comments or []
        self._attachments = attachments or []
        self._raise_on = raise_on or set()

    def fetch_comments(self, ado_id, top=30):
        if "comments" in self._raise_on:
            raise RuntimeError("simulated ADO comments outage")
        return list(self._comments)

    def fetch_attachments(self, ado_id):
        if "attachments" in self._raise_on:
            raise RuntimeError("simulated ADO attachments outage")
        return list(self._attachments)


# ── _format_attachment_size ─────────────────────────────────────────────────


def test_format_size_zero_returns_unknown():
    from api.agents import _format_attachment_size

    assert _format_attachment_size(0) == "tamaño desconocido"


def test_format_size_bytes_kb_mb():
    from api.agents import _format_attachment_size

    assert _format_attachment_size(512) == "512 B"
    assert _format_attachment_size(2048) == "2.0 KB"
    assert _format_attachment_size(2 * 1024 * 1024) == "2.0 MB"


# ── _build_ado_enrichment_sections — happy paths ────────────────────────────


def test_build_sections_includes_comments_section():
    from api.agents import _build_ado_enrichment_sections

    fake = _FakeAdoClient(
        comments=[
            {"author": "Juan", "date": "2026-04-15", "text": "<p>Falta validar fecha</p>"},
            {"author": "Ana", "date": "2026-04-16", "text": "<div>Confirmado por PO</div>"},
        ],
    )
    with patch("services.ado_client.AdoClient", return_value=fake):
        sections = _build_ado_enrichment_sections(ado_id=65)

    joined = "\n\n".join(sections)
    assert "## Comentarios ADO" in joined
    assert "Juan" in joined
    assert "2026-04-15" in joined
    assert "Falta validar fecha" in joined
    # HTML strip: no quedan tags <p> ni <div>
    assert "<p>" not in joined and "<div>" not in joined


def test_build_sections_includes_attachments_section_with_text_inline():
    from api.agents import _build_ado_enrichment_sections

    fake = _FakeAdoClient(
        attachments=[
            {
                "name": "log.txt",
                "url": "https://dev.azure.com/.../log.txt",
                "size": 1024,
                "text_content": "ERROR: something happened",
            },
            {
                "name": "screen.png",
                "url": "https://dev.azure.com/.../screen.png",
                "size": 200000,
                "text_content": None,
            },
        ],
    )
    with patch("services.ado_client.AdoClient", return_value=fake):
        sections = _build_ado_enrichment_sections(ado_id=65)

    joined = "\n\n".join(sections)
    assert "## Adjuntos" in joined
    assert "**log.txt**" in joined
    assert "**screen.png**" in joined
    assert "1.0 KB" in joined
    # text_content del .txt fue inlineado
    assert "ERROR: something happened" in joined
    assert "### Adjunto: log.txt" in joined
    # screen.png no tiene text_content → no genera bloque inline propio
    assert "### Adjunto: screen.png" not in joined


def test_build_sections_includes_both_when_present():
    from api.agents import _build_ado_enrichment_sections

    fake = _FakeAdoClient(
        comments=[{"author": "Juan", "date": "2026-04-15", "text": "<p>Nota</p>"}],
        attachments=[{"name": "a.txt", "url": "u", "size": 10, "text_content": "x"}],
    )
    with patch("services.ado_client.AdoClient", return_value=fake):
        sections = _build_ado_enrichment_sections(ado_id=65)

    joined = "\n\n".join(sections)
    assert "## Comentarios ADO" in joined
    assert "## Adjuntos" in joined


# ── _build_ado_enrichment_sections — error paths (silencia errores) ─────────


def test_build_sections_returns_empty_when_ado_client_init_fails():
    """Si AdoClient lanza al instanciarse (config faltante), no rompe."""
    from api.agents import _build_ado_enrichment_sections

    with patch(
        "services.ado_client.AdoClient",
        side_effect=RuntimeError("ADO_PAT no configurado"),
    ):
        sections = _build_ado_enrichment_sections(ado_id=65)

    assert sections == []


def test_build_sections_silences_fetch_comments_error():
    """Error en fetch_comments no bloquea — adjuntos siguen funcionando."""
    from api.agents import _build_ado_enrichment_sections

    fake = _FakeAdoClient(
        attachments=[{"name": "ok.txt", "url": "u", "size": 5, "text_content": "y"}],
        raise_on={"comments"},
    )
    with patch("services.ado_client.AdoClient", return_value=fake):
        sections = _build_ado_enrichment_sections(ado_id=65)

    joined = "\n\n".join(sections)
    assert "## Comentarios ADO" not in joined
    assert "## Adjuntos" in joined


def test_build_sections_silences_fetch_attachments_error():
    """Error en fetch_attachments no bloquea — comentarios siguen funcionando."""
    from api.agents import _build_ado_enrichment_sections

    fake = _FakeAdoClient(
        comments=[{"author": "Ana", "date": "2026-04-16", "text": "<p>ok</p>"}],
        raise_on={"attachments"},
    )
    with patch("services.ado_client.AdoClient", return_value=fake):
        sections = _build_ado_enrichment_sections(ado_id=65)

    joined = "\n\n".join(sections)
    assert "## Comentarios ADO" in joined
    assert "## Adjuntos" not in joined


def test_build_sections_returns_empty_when_no_comments_no_attachments():
    """Ticket sin comentarios ni adjuntos → ninguna sección agregada."""
    from api.agents import _build_ado_enrichment_sections

    fake = _FakeAdoClient(comments=[], attachments=[])
    with patch("services.ado_client.AdoClient", return_value=fake):
        sections = _build_ado_enrichment_sections(ado_id=65)

    assert sections == []


def test_build_sections_skips_empty_comment_text():
    """Comentarios sin texto (HTML vacío) son ignorados."""
    from api.agents import _build_ado_enrichment_sections

    fake = _FakeAdoClient(
        comments=[
            {"author": "Juan", "date": "2026-04-15", "text": ""},
            {"author": "Ana", "date": "2026-04-16", "text": "<p>   </p>"},
            {"author": "Pepe", "date": "2026-04-17", "text": "<p>real</p>"},
        ],
    )
    with patch("services.ado_client.AdoClient", return_value=fake):
        sections = _build_ado_enrichment_sections(ado_id=65)

    joined = "\n\n".join(sections)
    assert "Juan" not in joined  # comentario vacío descartado
    assert "Ana" not in joined  # solo whitespace descartado
    assert "Pepe" in joined
    assert "real" in joined


# ── /open-chat — integración con bridge mockeado ────────────────────────────


@pytest.fixture
def client():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def test_open_chat_message_includes_ado_sections(client):
    """End-to-end: /api/agents/open-chat envía al bridge un message con
    secciones de comentarios y adjuntos cuando ADO los provee."""
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=12345,
            project="RSPacifico",
            title="ticket de prueba",
            ado_state="Active",
            description="descripcion funcional",
            priority=2,
        )
        session.add(t)
        session.flush()
        ticket_id = t.id

    fake = _FakeAdoClient(
        comments=[{"author": "QA", "date": "2026-04-20", "text": "<p>repro paso 1</p>"}],
        attachments=[
            {"name": "trace.log", "url": "https://x", "size": 50, "text_content": "stack here"}
        ],
    )

    captured: dict = {}

    class _FakeBridgeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

    def _fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _FakeBridgeResponse()

    with patch("services.ado_client.AdoClient", return_value=fake), patch(
        "requests.post", side_effect=_fake_post
    ):
        r = client.post(
            "/api/agents/open-chat",
            json={"ticket_id": ticket_id, "context_blocks": [], "vscode_agent_filename": "X.agent.md"},
        )

    assert r.status_code == 200
    msg = captured["json"]["message"]
    assert "## Comentarios ADO" in msg
    assert "QA" in msg
    assert "repro paso 1" in msg
    assert "## Adjuntos" in msg
    assert "**trace.log**" in msg
    assert "stack here" in msg
    # El encabezado original sigue intacto
    assert "ADO-12345" in msg
    assert "descripcion funcional" in msg


def test_open_chat_works_when_ado_unavailable(client):
    """Si AdoClient falla al instanciarse, el endpoint sigue funcionando
    (sin secciones ADO) y el bridge recibe el mensaje base."""
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=99999,
            project="RSPacifico",
            title="sin ADO",
            ado_state="Active",
            description="solo descripcion",
        )
        session.add(t)
        session.flush()
        ticket_id = t.id

    captured: dict = {}

    class _FakeBridgeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

    def _fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return _FakeBridgeResponse()

    with patch(
        "services.ado_client.AdoClient",
        side_effect=RuntimeError("ADO_PAT missing"),
    ), patch("requests.post", side_effect=_fake_post):
        r = client.post(
            "/api/agents/open-chat",
            json={"ticket_id": ticket_id, "context_blocks": [], "vscode_agent_filename": "X.agent.md"},
        )

    assert r.status_code == 200
    msg = captured["json"]["message"]
    assert "ADO-99999" in msg
    assert "solo descripcion" in msg
    # No deben aparecer secciones ADO
    assert "## Comentarios ADO" not in msg
    assert "## Adjuntos" not in msg
