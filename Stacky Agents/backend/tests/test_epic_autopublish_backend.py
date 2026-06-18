"""Plan 41 — Autopublicación backend de la épica brief→épica.

Reproduce el agujero recurrente "brief→épica nunca crea el ticket en ADO":
el handshake de publicación vivía 100% en el navegador, así que si el frontend
no completaba el polling/publish, la run terminaba OK pero SIN épica en ADO.

La garantía se mueve al backend vía `autopublish_epic_from_run`, que es el
contrato que el finalizador del runner CLI invoca de forma autónoma.

No toca ADO real: mockea `_ado_client_for_ticket` y `_epic_brief_save`.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture()
def _app_ctx():
    """Algunas rutas internas usan logger del app; un app context basta."""
    from app import create_app
    app = create_app()
    with app.app_context():
        yield app


def _mock_ado(monkeypatch, *, ado_id=5555, raises=None):
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
    monkeypatch.setattr(t_mod, "_ado_client_for_ticket", lambda **kw: mock_client)
    monkeypatch.setattr(t_mod, "_epic_brief_save", lambda *a, **k: None)
    # No persistir ticket local (DB de test) — aislar el contrato de publicación.
    monkeypatch.setattr(t_mod, "_persist_epic_ticket", lambda *a, **k: None, raising=False)
    return mock_client


OUTPUT_WITH_EPIC = (
    "Claro, acá va la épica:\n\n"
    "```html\n"
    "<h1>EP-9 — Portal de Autogestión</h1><p>Objetivo de negocio...</p>"
    "<hr><h2>RF-001 — Autenticación</h2><p>El usuario debe poder ingresar.</p>\n"
    "```\n\n"
    "Resumen: listo ✅"
)


def test_autopublish_creates_epic_when_frontend_absent(_app_ctx, monkeypatch):
    """EL AGUJERO: run brief→épica termina OK con HTML de épica en el output,
    pero NADIE llamó a /epics/from-brief → la épica debe crearse igual desde el
    backend y devolver el ado_id sellado."""
    from api.tickets import autopublish_epic_from_run

    mock_client = _mock_ado(monkeypatch, ado_id=5555)

    result = autopublish_epic_from_run(
        output=OUTPUT_WITH_EPIC,
        brief="Necesito un portal de autogestión",
        project_name="Pacifico",
        already_published_id=None,
    )

    assert result.ado_id == 5555
    assert result.error is None
    # Se publicó UNA épica con el título derivado del heading.
    assert mock_client.create_work_item.call_count == 1
    kwargs = mock_client.create_work_item.call_args.kwargs
    assert kwargs["work_item_type"] == "Epic"
    assert kwargs["title"] == "EP-9 — Portal de Autogestión"
    # El HTML enviado a ADO fue extraído limpio (sin preámbulo ni fences).
    assert "Portal de Autogestión" in kwargs["description"]
    assert "```" not in kwargs["description"]
    assert "Resumen" not in kwargs["description"]


def test_autopublish_idempotent_when_already_sealed(_app_ctx, monkeypatch):
    """Si la run ya trae un epic_ado_id sellado, NO se republica (sin duplicados)."""
    from api.tickets import autopublish_epic_from_run

    mock_client = _mock_ado(monkeypatch, ado_id=5555)

    result = autopublish_epic_from_run(
        output=OUTPUT_WITH_EPIC,
        brief="x",
        project_name="Pacifico",
        already_published_id=4242,
    )

    assert result.ado_id == 4242
    assert result.error is None
    assert result.skipped is True
    mock_client.create_work_item.assert_not_called()


def test_autopublish_noisy_failure_on_ado_error(_app_ctx, monkeypatch):
    """Si ADO falla, NO hay ado_id y se devuelve un error visible (la run debe
    quedar needs_review, nunca completed silencioso)."""
    from api.tickets import autopublish_epic_from_run
    from services.ado_client import AdoApiError

    _mock_ado(monkeypatch, raises=AdoApiError("ADO 503", status_code=503))

    result = autopublish_epic_from_run(
        output=OUTPUT_WITH_EPIC,
        brief="x",
        project_name="Pacifico",
        already_published_id=None,
    )

    assert result.ado_id is None
    assert result.error is not None
    assert "ADO 503" in result.error


def test_autopublish_noisy_failure_on_narration_only(_app_ctx, monkeypatch):
    """Output que es NARRACIÓN del agente (texto puro sin estructura de épica) →
    FALLO RUIDOSO `epic_not_in_output`, NO skip silencioso.

    Este es el síntoma exacto del bug histórico: el agente narra ("ya escribí el
    archivo...") en vez de devolver el HTML de la épica. Si esto se tragara en
    silencio, la run quedaría `completed` sin épica en ADO. El guard
    `_looks_like_epic` (heading + bloque RF) debe rechazarlo con error visible
    para que el llamante degrade a needs_review."""
    from api.tickets import autopublish_epic_from_run

    mock_client = _mock_ado(monkeypatch, ado_id=5555)

    result = autopublish_epic_from_run(
        output="No pude generar la épica, falta información.",
        brief="x",
        project_name="Pacifico",
        already_published_id=None,
    )

    assert result.ado_id is None
    assert result.error is not None
    assert "epic_not_in_output" in result.error
    assert result.skipped is False
    mock_client.create_work_item.assert_not_called()
