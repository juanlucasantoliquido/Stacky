"""Tests Q0.1 — Inyección de criterios de aceptación como checklist.

TDD para `services/acceptance_criteria.py` y el inyector en
`services/context_enrichment._inject_acceptance_criteria`.

Suite aislada: no usa DB real; mockea build_ado_client y session_scope.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Tests de acceptance_criteria.py helpers
# ---------------------------------------------------------------------------

def test_resolve_returns_ac_field():
    """Ticket con AcceptanceCriteria → devuelve ese campo."""
    ticket = MagicMock()
    ticket.stacky_project_name = "PROJ"
    ticket.project = "PROJ"
    ticket.ado_id = 42

    mock_client = MagicMock()
    mock_client._batch_get.return_value = [
        {"fields": {"Microsoft.VSTS.Common.AcceptanceCriteria": "Criterio A\nCriterio B"}}
    ]
    with patch("services.project_context.build_ado_client", return_value=mock_client):
        from services.acceptance_criteria import resolve
        result = resolve(ticket)
    assert "Criterio A" in result
    assert "Criterio B" in result


def test_resolve_fallback_to_description():
    """Sin AC field → fallback a Description."""
    ticket = MagicMock()
    ticket.stacky_project_name = "PROJ"
    ticket.project = "PROJ"
    ticket.ado_id = 42

    mock_client = MagicMock()
    mock_client._batch_get.return_value = [
        {"fields": {"System.Description": "Descripción larga"}}
    ]
    with patch("services.project_context.build_ado_client", return_value=mock_client):
        from services.acceptance_criteria import resolve
        result = resolve(ticket)
    assert "Descripción larga" in result


def test_resolve_empty_when_no_fields():
    """Sin payload → cadena vacía."""
    ticket = MagicMock()
    ticket.stacky_project_name = "PROJ"
    ticket.project = "PROJ"
    ticket.ado_id = 42

    mock_client = MagicMock()
    mock_client._batch_get.return_value = []
    with patch("services.project_context.build_ado_client", return_value=mock_client):
        from services.acceptance_criteria import resolve
        result = resolve(ticket)
    assert result == ""


def test_render_checklist_formats_imperativo():
    """render_checklist produce el header y los bullets correctamente."""
    from services.acceptance_criteria import render_checklist
    text = "Debe hacer A\nDebe hacer B"
    result = render_checklist(text)
    assert "DEBE cumplir" in result
    assert "- Debe hacer A" in result
    assert "- Debe hacer B" in result


def test_render_checklist_empty_input():
    """Texto vacío → cadena vacía."""
    from services.acceptance_criteria import render_checklist
    assert render_checklist("") == ""
    assert render_checklist("   ") == ""


# ---------------------------------------------------------------------------
# Tests de _inject_acceptance_criteria en context_enrichment
# ---------------------------------------------------------------------------

def _make_ticket(ado_id=42):
    t = MagicMock()
    t.ado_id = ado_id
    t.stacky_project_name = "TEST_PROJ"
    t.project = "TEST_PROJ"
    return t


def test_inject_adds_block_when_flag_on_and_ac_present():
    """Flag ON + ticket con AC → bloque 'acceptance-criteria' presente."""
    mock_session = MagicMock()
    mock_session.__enter__ = lambda s: mock_session
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.get.return_value = _make_ticket()

    mock_client = MagicMock()
    mock_client._batch_get.return_value = [
        {"fields": {"Microsoft.VSTS.Common.AcceptanceCriteria": "El sistema debe procesar X"}}
    ]

    with (
        patch("services.context_enrichment._acceptance_criteria_enabled", return_value=True),
        patch("db.session_scope", return_value=mock_session),
        patch("services.project_context.build_ado_client", return_value=mock_client),
    ):
        from services.context_enrichment import _inject_acceptance_criteria
        blocks = _inject_acceptance_criteria(
            ticket_id=1,
            project_name="TEST_PROJ",
            blocks=[],
            log=lambda *a, **kw: None,
        )

    ids = [b.get("id") for b in blocks]
    assert "acceptance-criteria" in ids
    content = next(b["content"] for b in blocks if b.get("id") == "acceptance-criteria")
    assert "DEBE cumplir" in content
    assert "El sistema debe procesar X" in content


def test_inject_noop_when_flag_off():
    """Flag OFF → byte-idéntico."""
    with patch("services.context_enrichment._acceptance_criteria_enabled", return_value=False):
        from services.context_enrichment import _inject_acceptance_criteria
        blocks_in = [{"id": "existing", "content": "x"}]
        blocks_out = _inject_acceptance_criteria(
            ticket_id=1,
            project_name="TEST_PROJ",
            blocks=blocks_in,
            log=lambda *a, **kw: None,
        )
    assert blocks_out is blocks_in


def test_inject_noop_when_no_ac():
    """Sin AC en ADO → no-op."""
    mock_session = MagicMock()
    mock_session.__enter__ = lambda s: mock_session
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.get.return_value = _make_ticket()

    mock_client = MagicMock()
    mock_client._batch_get.return_value = [{"fields": {}}]

    with (
        patch("services.context_enrichment._acceptance_criteria_enabled", return_value=True),
        patch("services.context_enrichment.session_scope", return_value=mock_session),
        patch("services.project_context.build_ado_client", return_value=mock_client),
    ):
        from services.context_enrichment import _inject_acceptance_criteria
        blocks_out = _inject_acceptance_criteria(
            ticket_id=1,
            project_name="TEST_PROJ",
            blocks=[],
            log=lambda *a, **kw: None,
        )
    assert not any(b.get("id") == "acceptance-criteria" for b in blocks_out)


def test_inject_idempotent():
    """Si el bloque ya existe no se duplica."""
    with patch("services.context_enrichment._acceptance_criteria_enabled", return_value=True):
        from services.context_enrichment import _inject_acceptance_criteria
        existing = [{"id": "acceptance-criteria", "content": "ya existe"}]
        blocks_out = _inject_acceptance_criteria(
            ticket_id=1,
            project_name="TEST_PROJ",
            blocks=existing,
            log=lambda *a, **kw: None,
        )
    count = sum(1 for b in blocks_out if b.get("id") == "acceptance-criteria")
    assert count == 1
