"""Plan 45 F1 — Publicación de Issues desde run (publish_issue_from_run).

No toca ADO real: mockea `_ado_client_for_ticket`, `_epic_brief_save` y
`_persist_issue_ticket`. Cubre los 7 casos borde del plan.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def _app_ctx():
    from app import create_app
    app = create_app()
    with app.app_context():
        yield app


def _mock_ado(monkeypatch, *, ado_id=7777, raises=None, comment_exists=None):
    import api.tickets as t_mod
    mock_client = MagicMock()
    if raises is not None:
        mock_client.create_work_item.side_effect = raises
    else:
        mock_client.create_work_item.return_value = {
            "id": ado_id,
            "fields": {"System.Title": "T"},
            "_links": {"html": {"href": f"https://dev.azure.com/x/_workitems/edit/{ado_id}"}},
        }
    mock_client.work_item_url.return_value = f"https://dev.azure.com/x/_workitems/edit/{ado_id}"
    mock_client.comment_exists.return_value = comment_exists
    monkeypatch.setattr(t_mod, "_ado_client_for_ticket", lambda **kw: mock_client)
    monkeypatch.setattr(t_mod, "_epic_brief_save", lambda *a, **k: None)
    monkeypatch.setattr(t_mod, "_persist_issue_ticket", lambda *a, **k: None, raising=False)
    return mock_client


OUTPUT_WITH_ISSUE = (
    "Acá va el issue:\n\n"
    "```html\n"
    "<h1>Bug en login</h1><p>Objetivo...</p>"
    "<hr><h2>RF-001 — Reparar auth</h2><p>El usuario no puede ingresar.</p>\n"
    "```\n\nListo ✅"
)


def test_idempotent_when_already_published(_app_ctx, monkeypatch):
    """Caso 1: already_published_id != None → skipped, sin llamadas ADO."""
    from api.tickets import publish_issue_from_run
    mock_client = _mock_ado(monkeypatch)
    result = publish_issue_from_run(
        output=OUTPUT_WITH_ISSUE, brief="x", project_name="Pacifico",
        already_published_id=1234,
    )
    assert result.ado_id == 1234
    assert result.skipped is True
    assert result.error is None
    mock_client.create_work_item.assert_not_called()


def test_empty_output_skipped(_app_ctx, monkeypatch):
    """Caso 2: output vacío → skipped, sin error."""
    from api.tickets import publish_issue_from_run
    mock_client = _mock_ado(monkeypatch)
    result = publish_issue_from_run(
        output="   ", brief="x", project_name="Pacifico", already_published_id=None,
    )
    assert result.skipped is True
    assert result.ado_id is None
    mock_client.create_work_item.assert_not_called()


def test_narration_only_is_noisy_error(_app_ctx, monkeypatch):
    """Caso 3: output que no es épica/issue → error epic_not_in_output, sin ADO."""
    from api.tickets import publish_issue_from_run
    mock_client = _mock_ado(monkeypatch)
    result = publish_issue_from_run(
        output="Ya escribí el issue en un archivo, listo.", brief="x",
        project_name="Pacifico", already_published_id=None,
    )
    assert result.ado_id is None
    assert result.error is not None
    assert "epic_not_in_output" in result.error
    mock_client.create_work_item.assert_not_called()


def test_creates_issue_work_item(_app_ctx, monkeypatch):
    """Caso éxito: crea WI tipo Issue y postea comentario funcional."""
    from api.tickets import publish_issue_from_run
    mock_client = _mock_ado(monkeypatch, ado_id=7777, comment_exists=None)
    result = publish_issue_from_run(
        output=OUTPUT_WITH_ISSUE, brief="Reparar login", project_name="Pacifico",
        already_published_id=None,
    )
    assert result.ado_id == 7777
    assert result.error is None
    assert mock_client.create_work_item.call_count == 1
    kwargs = mock_client.create_work_item.call_args.kwargs
    assert kwargs["work_item_type"] == "Issue"
    assert "```" not in kwargs["description"]
    # Posteó UN comentario con el marker de fase funcional.
    assert mock_client.post_comment.call_count == 1
    comment_args = mock_client.post_comment.call_args
    posted_text = comment_args.args[1] if len(comment_args.args) > 1 else comment_args.kwargs.get("text", "")
    assert "stacky:issue-phase:funcional" in posted_text


def test_ado_create_failure_is_noisy(_app_ctx, monkeypatch):
    """Caso 4: ADO falla en create_work_item → error no vacío, ado_id None."""
    from api.tickets import publish_issue_from_run
    from api.tickets import _AdoApiError
    _mock_ado(monkeypatch, raises=_AdoApiError("ADO 503", status_code=503))
    result = publish_issue_from_run(
        output=OUTPUT_WITH_ISSUE, brief="x", project_name="Pacifico",
        already_published_id=None,
    )
    assert result.ado_id is None
    assert result.error is not None


def test_comment_failure_not_fatal(_app_ctx, monkeypatch):
    """Caso 5: post_comment falla → el Issue ya existe; función no falla fatal."""
    from api.tickets import publish_issue_from_run
    mock_client = _mock_ado(monkeypatch, ado_id=7777, comment_exists=None)
    mock_client.post_comment.side_effect = RuntimeError("ADO comment 500")
    result = publish_issue_from_run(
        output=OUTPUT_WITH_ISSUE, brief="x", project_name="Pacifico",
        already_published_id=None,
    )
    # El Issue se creó igual: ado_id sellado, sin error fatal.
    assert result.ado_id == 7777
    assert result.error is None


def test_comment_idempotent_when_marker_exists(_app_ctx, monkeypatch):
    """Caso 6: comment_exists devuelve dict → post_comment NO se llama (idempotencia)."""
    from api.tickets import publish_issue_from_run
    mock_client = _mock_ado(
        monkeypatch, ado_id=7777, comment_exists={"id": 1, "text": "ya está"}
    )
    result = publish_issue_from_run(
        output=OUTPUT_WITH_ISSUE, brief="x", project_name="Pacifico",
        already_published_id=None,
    )
    assert result.ado_id == 7777
    mock_client.post_comment.assert_not_called()
