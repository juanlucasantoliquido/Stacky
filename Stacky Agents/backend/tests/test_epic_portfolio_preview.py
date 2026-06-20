"""Plan 55 F3 — Tests de build_epic_portfolio_preview y _split_epics_html (funciones puras).

Valida:
- output sin H1s → lista de 1 ítem (una épica).
- output con 3 H1s → lista de 3 ítems.
- La partición es determinista (mismo input → mismo output).
- Endpoint GET /api/tickets/epic-portfolio-preview → 404 si flag OFF (default).
"""
from __future__ import annotations

import pytest


HTML_NO_H1 = (
    "<h2>RF-001 — Login</h2><p>El usuario debe poder ingresar.</p>"
)

VALID_EPIC_BLOCK = (
    "<h1>{title}</h1><p>Objetivo de negocio...</p>"
    "<hr><h2>RF-001 — Autenticación</h2><p>El usuario debe poder ingresar.</p>"
)

HTML_THREE_H1 = "\n".join([
    VALID_EPIC_BLOCK.format(title="EP-1 — Portal"),
    VALID_EPIC_BLOCK.format(title="EP-2 — Reportes"),
    VALID_EPIC_BLOCK.format(title="EP-3 — Integraciones"),
])

OUTPUT_SINGLE_EPIC = (
    "```html\n"
    + VALID_EPIC_BLOCK.format(title="EP-1 — Portal")
    + "\n```\n"
)

OUTPUT_THREE_EPICS = (
    "```html\n"
    + HTML_THREE_H1
    + "\n```\n"
)


@pytest.fixture()
def _app_ctx():
    from app import create_app
    app = create_app()
    with app.app_context():
        yield app


# ── _split_epics_html ──────────────────────────────────────────────────────────

def test_no_h1_returns_single_chunk(_app_ctx):
    """HTML sin H1s → [html] (una sola épica)."""
    from api.tickets import _split_epics_html

    result = _split_epics_html(HTML_NO_H1)
    assert len(result) == 1
    assert result[0] == HTML_NO_H1


def test_three_h1_returns_three_chunks(_app_ctx):
    """HTML con 3 H1s → 3 bloques."""
    from api.tickets import _split_epics_html

    result = _split_epics_html(HTML_THREE_H1)
    assert len(result) == 3
    assert "EP-1" in result[0]
    assert "EP-2" in result[1]
    assert "EP-3" in result[2]


def test_split_is_deterministic(_app_ctx):
    """Mismo HTML → misma partición siempre."""
    from api.tickets import _split_epics_html

    r1 = _split_epics_html(HTML_THREE_H1)
    r2 = _split_epics_html(HTML_THREE_H1)
    assert r1 == r2


# ── build_epic_portfolio_preview ───────────────────────────────────────────────

def test_no_h1_output_returns_single_preview(_app_ctx):
    """output sin H1 → lista de 1 EpicPayloadPreview."""
    from api.tickets import build_epic_portfolio_preview

    result = build_epic_portfolio_preview(
        output=OUTPUT_SINGLE_EPIC,
        brief="brief de prueba",
        project_name="Pacifico",
    )
    assert isinstance(result, list)
    assert len(result) == 1


def test_three_h1_returns_three_items(_app_ctx):
    """output con 3 H1s → 3 previews."""
    from api.tickets import build_epic_portfolio_preview

    result = build_epic_portfolio_preview(
        output=OUTPUT_THREE_EPICS,
        brief="brief de prueba",
        project_name="Pacifico",
    )
    assert isinstance(result, list)
    assert len(result) == 3
    for item in result:
        assert item.ok is True


def test_portfolio_never_raises_on_empty(_app_ctx):
    """output vacío → lista de 1 ítem con ok=False, sin excepción."""
    from api.tickets import build_epic_portfolio_preview

    result = build_epic_portfolio_preview(
        output=None,
        brief="brief",
        project_name="Pacifico",
    )
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].ok is False


# ── Endpoint ──────────────────────────────────────────────────────────────────

def test_endpoint_404_when_flag_off():
    """STACKY_EPIC_PORTFOLIO_ENABLED=false (default) → 404."""
    import os
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    os.environ["STACKY_EPIC_PORTFOLIO_ENABLED"] = "false"

    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        with app.app_context():
            resp = c.get("/api/tickets/epic-portfolio-preview?execution_id=1")
            assert resp.status_code == 404

    # Limpiar para no afectar otros tests
    del os.environ["STACKY_EPIC_PORTFOLIO_ENABLED"]
