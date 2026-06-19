"""Plan 42 F2 — Preflight de grounding en épica + F4 resumen post-épica.

Tests:
F2:
1. test_warnings_empty_when_epic_cites_modules
2. test_warnings_empty_when_epic_marks_assumptions
3. test_warnings_present_when_no_grounding
4. test_autopublish_attaches_grounding_warnings_not_blocks
5. test_autopublish_no_warnings_when_flag_off

F4:
6. test_summary_counts_rf
7. test_summary_extracts_cited_modules
8. test_summary_carries_warnings_and_confidence
9. test_autopublish_attaches_epic_summary_when_flag_on
10. test_autopublish_no_summary_when_flag_off

F2 integración débil:
11. test_confidence_grounding_marked_in_html
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
# F2 — _epic_grounding_warnings (función pura)
# ---------------------------------------------------------------------------

def test_warnings_empty_when_epic_cites_modules():
    from api.tickets import _epic_grounding_warnings
    html = "<h1>EP-1</h1><h2>RF-001</h2><p>Módulo Facturación gestiona...</p>"
    assert _epic_grounding_warnings(html) == []


def test_warnings_empty_when_epic_marks_assumptions():
    from api.tickets import _epic_grounding_warnings
    html = "<h1>EP-2</h1><h2>RF-001</h2><p>[SUPUESTO: el proceso envía emails]</p>"
    assert _epic_grounding_warnings(html) == []


def test_warnings_present_when_no_grounding():
    from api.tickets import _epic_grounding_warnings
    html = "<h1>EP-3</h1><h2>RF-001</h2><p>El sistema debe registrar el evento.</p>"
    warnings = _epic_grounding_warnings(html)
    assert len(warnings) == 1
    assert "epic_grounding_low" in warnings[0]


def _mock_ado_for_grounding(monkeypatch, ado_id=7777):
    import api.tickets as t_mod
    mock_client = MagicMock()
    mock_client.create_work_item.return_value = {
        "id": ado_id,
        "fields": {"System.Title": "T"},
        "_links": {"html": {"href": f"https://dev.azure.com/x/{ado_id}"}},
    }
    mock_client.work_item_url.return_value = f"https://dev.azure.com/x/{ado_id}"
    monkeypatch.setattr(t_mod, "_ado_client_for_ticket", lambda **kw: mock_client)
    monkeypatch.setattr(t_mod, "_epic_brief_save", lambda *a, **k: None)
    monkeypatch.setattr(t_mod, "_persist_epic_ticket", lambda *a, **k: None, raising=False)
    return mock_client


EPIC_NO_GROUNDING = (
    "<h1>EP-10 — Sistema de Reportes</h1>"
    "<hr><h2>RF-001 — Exportación</h2>"
    "<p>El sistema debe exportar el reporte en PDF.</p>"
)

EPIC_WITH_GROUNDING = (
    "<h1>EP-11 — Módulo de Facturación</h1>"
    "<hr><h2>RF-001 — Cálculo</h2>"
    "<p>El módulo FacturacionNocturna calcula los totales diarios.</p>"
)


@pytest.fixture()
def _app_ctx():
    from app import create_app
    app = create_app()
    with app.app_context():
        yield app


def test_autopublish_attaches_grounding_warnings_not_blocks(_app_ctx, monkeypatch):
    """Grounding ON, epic sin grounding → warnings adjuntos en resultado pero ado_id presente."""
    monkeypatch.setenv("STACKY_EPIC_GROUNDING_PREFLIGHT_ENABLED", "true")
    monkeypatch.setenv("STACKY_EPIC_SUMMARY_ENABLED", "false")
    _mock_ado_for_grounding(monkeypatch)
    from api.tickets import autopublish_epic_from_run
    output = "```html\n" + EPIC_NO_GROUNDING + "\n```"
    res = autopublish_epic_from_run(
        output=output, brief="brief", project_name="proj", already_published_id=None
    )
    assert res.ado_id is not None, "La épica debe publicarse aunque haya warnings de grounding"
    assert res.error is None
    assert len(res.grounding_warnings) == 1
    assert "epic_grounding_low" in res.grounding_warnings[0]


def test_autopublish_no_warnings_when_flag_off(_app_ctx, monkeypatch):
    """Grounding OFF → grounding_warnings vacío aunque la épica no cite módulos."""
    monkeypatch.setenv("STACKY_EPIC_GROUNDING_PREFLIGHT_ENABLED", "false")
    monkeypatch.setenv("STACKY_EPIC_SUMMARY_ENABLED", "false")
    _mock_ado_for_grounding(monkeypatch, ado_id=7778)
    from api.tickets import autopublish_epic_from_run
    output = "```html\n" + EPIC_NO_GROUNDING + "\n```"
    res = autopublish_epic_from_run(
        output=output, brief="brief", project_name="proj", already_published_id=None
    )
    assert res.grounding_warnings == []


# ---------------------------------------------------------------------------
# F4 — build_epic_summary (función pura)
# ---------------------------------------------------------------------------

def test_summary_counts_rf():
    from api.tickets import build_epic_summary
    html = "<h1>EP-1</h1><h2>RF-001</h2><p>x</p><h2>RF-002</h2><p>y</p>"
    s = build_epic_summary(ado_id=1, ado_url="http://x", clean_html=html, warnings=[], confidence=None)
    assert s["rf_count"] == 2


def test_summary_extracts_cited_modules():
    from api.tickets import build_epic_summary
    html = "<h1>EP-1</h1><h2>RF-001</h2><p>Módulo Facturación gestiona esto.</p>"
    s = build_epic_summary(ado_id=1, ado_url="http://x", clean_html=html, warnings=[], confidence=None)
    assert any("Facturación" in m or "facturación" in m.lower() for m in s["cited_modules"])


def test_summary_carries_warnings_and_confidence():
    from api.tickets import build_epic_summary
    html = "<h1>EP-1</h1><h2>RF-001</h2><p>x</p>"
    s = build_epic_summary(
        ado_id=42, ado_url="http://a", clean_html=html,
        warnings=["epic_grounding_low: ..."], confidence=0.3
    )
    assert s["ado_id"] == 42
    assert s["warnings"] == ["epic_grounding_low: ..."]
    assert s["confidence"] == 0.3


def test_autopublish_attaches_epic_summary_when_flag_on(_app_ctx, monkeypatch):
    """Summary ON → epic_summary en el resultado con rf_count."""
    monkeypatch.setenv("STACKY_EPIC_SUMMARY_ENABLED", "true")
    monkeypatch.setenv("STACKY_EPIC_GROUNDING_PREFLIGHT_ENABLED", "false")
    _mock_ado_for_grounding(monkeypatch, ado_id=7780)
    from api.tickets import autopublish_epic_from_run
    output = "```html\n" + EPIC_NO_GROUNDING + "\n```"
    res = autopublish_epic_from_run(
        output=output, brief="brief", project_name="proj", already_published_id=None
    )
    assert res.epic_summary is not None
    assert res.epic_summary["rf_count"] == 1
    assert res.epic_summary["ado_id"] == 7780


def test_autopublish_no_summary_when_flag_off(_app_ctx, monkeypatch):
    """Summary OFF → epic_summary es None."""
    monkeypatch.setenv("STACKY_EPIC_SUMMARY_ENABLED", "false")
    monkeypatch.setenv("STACKY_EPIC_GROUNDING_PREFLIGHT_ENABLED", "false")
    _mock_ado_for_grounding(monkeypatch, ado_id=7781)
    from api.tickets import autopublish_epic_from_run
    output = "```html\n" + EPIC_NO_GROUNDING + "\n```"
    res = autopublish_epic_from_run(
        output=output, brief="brief", project_name="proj", already_published_id=None
    )
    assert res.epic_summary is None


# ---------------------------------------------------------------------------
# F2 integración débil — el process-catalog llega a enrich_blocks
# ---------------------------------------------------------------------------

def test_confidence_grounding_marked_in_html():
    """El process-catalog inyectado por enrich_blocks es un bloque en la lista."""
    from services.context_enrichment import build_process_dictionary_block

    profile_with_catalog = {
        "process_catalog": [
            {"name": "FacturacionNocturna", "purpose": "Genera facturas", "kind": "batch"},
        ]
    }
    block = build_process_dictionary_block(profile_with_catalog)
    assert block is not None
    assert block["id"] == "process-catalog"
    assert "FacturacionNocturna" in block["content"]
