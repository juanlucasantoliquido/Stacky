"""Plan 55 F0 — Tests de build_epic_payload_preview (función pura, no toca ADO/BD).

Valida que:
- EpicPayloadPreview y build_epic_payload_preview son importables desde api.tickets.
- output vacío/None → ok=False, error="empty_output".
- output prosa sin HTML → ok=False, error="epic_not_in_output".
- output con HTML de épica válida → ok=True, title no vacío, html no vacío.
- work_item_type="Issue" devuelve el mismo comportamiento puro (mismo path de extracción).
"""
from __future__ import annotations

import pytest


OUTPUT_WITH_EPIC = (
    "Claro, acá va la épica:\n\n"
    "```html\n"
    "<h1>EP-9 — Portal de Autogestión</h1><p>Objetivo de negocio...</p>"
    "<hr><h2>RF-001 — Autenticación</h2><p>El usuario debe poder ingresar.</p>\n"
    "```\n\n"
    "Resumen: listo ✅"
)

OUTPUT_NARRATION = (
    "Voy a leer el archivo... El archivo de salida para EP-31 ya existe. "
    "La épica fue escrita correctamente en el directorio de outputs."
)


@pytest.fixture()
def _app_ctx():
    from app import create_app
    app = create_app()
    with app.app_context():
        yield app


def test_empty_output_returns_error(_app_ctx):
    """output=None → ok=False, error='empty_output'."""
    from api.tickets import build_epic_payload_preview

    result = build_epic_payload_preview(
        output=None,
        brief="Necesito un portal",
        project_name="Pacifico",
    )
    assert result.ok is False
    assert result.error == "empty_output"
    assert result.title is None
    assert result.html is None


def test_empty_string_output_returns_error(_app_ctx):
    """output='' → ok=False, error='empty_output'."""
    from api.tickets import build_epic_payload_preview

    result = build_epic_payload_preview(
        output="   ",
        brief="Necesito un portal",
        project_name="Pacifico",
    )
    assert result.ok is False
    assert result.error == "empty_output"


def test_narration_not_html_returns_error(_app_ctx):
    """output prosa sin HTML de épica → ok=False, error='epic_not_in_output'."""
    from api.tickets import build_epic_payload_preview

    result = build_epic_payload_preview(
        output=OUTPUT_NARRATION,
        brief="Necesito un portal",
        project_name="Pacifico",
    )
    assert result.ok is False
    assert result.error == "epic_not_in_output"
    assert result.title is None


def test_valid_epic_html_returns_ok(_app_ctx):
    """output con HTML de épica válida → ok=True, title no vacío, html no vacío."""
    from api.tickets import build_epic_payload_preview

    result = build_epic_payload_preview(
        output=OUTPUT_WITH_EPIC,
        brief="Necesito un portal de autogestión",
        project_name="Pacifico",
    )
    assert result.ok is True
    assert result.error is None
    assert result.title
    assert "Portal de Autogestión" in result.title
    assert result.html
    assert "RF-001" in result.html


def test_epic_and_issue_paths_differ(_app_ctx):
    """work_item_type='Issue' vs 'Epic' — ambos usan el mismo extractor de HTML.

    El path Issue no rescata del disco (preview es puro sobre output).
    Ambos devuelven ok=True para un output con HTML de épica válido.
    """
    from api.tickets import build_epic_payload_preview

    result_epic = build_epic_payload_preview(
        output=OUTPUT_WITH_EPIC,
        brief="brief",
        project_name="Pacifico",
        work_item_type="Epic",
    )
    result_issue = build_epic_payload_preview(
        output=OUTPUT_WITH_EPIC,
        brief="brief",
        project_name="Pacifico",
        work_item_type="Issue",
    )
    assert result_epic.ok is True
    assert result_issue.ok is True
    # El tipo se refleja en work_item_type del resultado.
    assert result_epic.work_item_type == "Epic"
    assert result_issue.work_item_type == "Issue"
    # El html extraído debe ser el mismo (misma función de extracción).
    assert result_epic.html == result_issue.html


def test_preview_html_matches_publisher(_app_ctx, monkeypatch):
    """DoD: build_epic_payload_preview.html == lo que autopublish_epic_from_run enviaría a ADO.

    Mockeamos _publish_epic_to_ado para capturar el description_html que le pasa
    autopublish_epic_from_run y comparamos con el html del preview.
    """
    import api.tickets as t_mod
    from unittest.mock import MagicMock
    from api.tickets import build_epic_payload_preview, _AutopublishResult

    captured: dict = {}

    def _fake_publish(*, description_html, brief, project_name):
        captured["html"] = description_html
        mock_result = MagicMock()
        mock_result.ado_id = 9999
        mock_result.url = "https://dev.azure.com/test"
        return mock_result

    monkeypatch.setattr(t_mod, "_publish_epic_to_ado", _fake_publish, raising=False)
    monkeypatch.setattr(t_mod, "_epic_brief_save", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(t_mod, "_persist_epic_ticket", lambda *a, **k: None, raising=False)

    from api.tickets import autopublish_epic_from_run
    autopublish_epic_from_run(
        output=OUTPUT_WITH_EPIC,
        brief="Necesito un portal de autogestión",
        project_name="Pacifico",
        already_published_id=None,
    )

    preview = build_epic_payload_preview(
        output=OUTPUT_WITH_EPIC,
        brief="Necesito un portal de autogestión",
        project_name="Pacifico",
    )

    assert preview.ok is True
    assert captured.get("html") is not None
    assert preview.html == captured["html"], (
        f"Preview html != Publisher html:\nPREVIEW={preview.html!r}\nPUBLISHER={captured['html']!r}"
    )
