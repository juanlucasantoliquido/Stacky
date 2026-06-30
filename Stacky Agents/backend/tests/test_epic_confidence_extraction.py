"""Plan 44 F0 — Extracción de confidence_grounding del HTML de la épica."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_extracts_explicit_number():
    from api.tickets import _extract_confidence_from_html
    assert _extract_confidence_from_html("...confidence_grounding = 0.83...") == 0.83


def test_extracts_with_colon_separator():
    from api.tickets import _extract_confidence_from_html
    assert _extract_confidence_from_html("confidence_grounding: 0.5") == 0.5


def test_caps_to_one():
    from api.tickets import _extract_confidence_from_html
    assert _extract_confidence_from_html("confidence_grounding = 1.5") == 1.0


def test_low_confidence_marker_returns_sentinel():
    from api.tickets import _extract_confidence_from_html, _LOW_CONFIDENCE_SENTINEL
    html = "<p>[BAJA CONFIANZA DE GROUNDING — operador, validá...]</p>"
    assert _extract_confidence_from_html(html) == _LOW_CONFIDENCE_SENTINEL


def test_returns_none_when_absent():
    from api.tickets import _extract_confidence_from_html
    assert _extract_confidence_from_html("<h1>Épica</h1><h2>RF-001</h2>") is None


def test_returns_none_on_empty():
    from api.tickets import _extract_confidence_from_html
    assert _extract_confidence_from_html(None) is None
    assert _extract_confidence_from_html("") is None


def test_non_epic_html_returns_none():
    """[A1] Output de run normal (no épica) → None (sin falso positivo)."""
    from api.tickets import _extract_confidence_from_html
    html = "<h1>Resultado de análisis</h1><p>Se procesaron 12 registros.</p>"
    assert _extract_confidence_from_html(html) is None


def test_regex_against_real_html_pattern():
    """[A1] Formato mínimo conforme a R-GROUNDING ítem 5 (BusinessAgent v1.5.0)."""
    from api.tickets import _extract_confidence_from_html
    assert _extract_confidence_from_html("<p>confidence_grounding = 0.91</p>") == 0.91


@pytest.fixture()
def _app_ctx():
    from app import create_app
    app = create_app()
    with app.app_context():
        yield app


def test_autopublish_persists_extracted_confidence(_app_ctx, monkeypatch):
    """La confidence extraída se persiste en epic_summary['confidence'] (no None)."""
    import api.tickets as t_mod

    mock_client = MagicMock()
    mock_client.create_work_item.return_value = {
        "id": 8888,
        "fields": {"System.Title": "T"},
        "_links": {"html": {"href": "https://dev.azure.com/x/_workitems/edit/8888"}},
    }
    mock_client.work_item_url.return_value = "https://dev.azure.com/x/_workitems/edit/8888"
    monkeypatch.setattr(t_mod, "_ado_client_for_ticket", lambda **kw: mock_client)
    monkeypatch.setattr(t_mod, "_epic_brief_save", lambda *a, **k: None)
    monkeypatch.setattr(t_mod, "_persist_epic_ticket", lambda *a, **k: None, raising=False)

    output = (
        "```html\n"
        "<h1>EP-1 — Portal</h1><p>módulo Login.</p>"
        "<hr><h2>RF-001 — Auth</h2><p>confidence_grounding = 0.7</p>\n"
        "```"
    )
    result = t_mod.autopublish_epic_from_run(
        output=output, brief="b", project_name="Pacifico", already_published_id=None,
    )
    assert result.epic_summary is not None
    assert result.epic_summary["confidence"] == 0.7
