"""Contrato END-TO-END que faltaba (diagnóstico 2026-06-18):

Una run brief→épica con `claude_code_cli` termina `completed` con un `output`
que NO es HTML limpio: contiene preámbulo conversacional, uno o más fences
```html ... ``` (la épica) y un resumen final con checklist/emojis.

El modal (EpicFromBriefModal) envía ese output CRUDO como `description_html`
a POST /api/tickets/epics/from-brief. Sin saneamiento, la Épica creada en ADO
queda contaminada con el preámbulo y los fences.

Estos tests atan el contrato real: del `output` de la run hay que poder extraer
una ÉPICA HTML limpia (el bloque ```html```), y el endpoint debe sanear lo que
reciba antes de mandarlo a ADO. Reproduce el output real de la run id=1.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest


# --- Fixture: output REAL de la run reproducida (id=1, BusinessAgent, CLI) ---
# Estructura fiel: preámbulo + fence ```html (épica) + resumen con ✅.
# (Recortado al esqueleto verificable; preserva los marcadores que importan.)
_REAL_RUN_OUTPUT = (
    "Voy a leer el archivo del agente BusinessAgent para adoptar su rol correctamente.\n\n"
    "Leyendo el índice de documentación funcional online del proyecto.\n\n"
    "El archivo ya existe en `Agentes/outputs/brief-pool/epic-gmr.html` de una ejecución "
    "previa. A continuación el HTML de la épica listo para aprobación:\n\n"
    "---\n\n"
    "```html\n"
    "<h1>EP-30 — Incorporación de acceso directo al motor GMR</h1>\n"
    "<p><strong>Resumen ejecutivo:</strong> La Plataforma de Gestión...</p>\n"
    "<h2>RF-030</h2>\n"
    "<ul>\n  <li>CA-01: ...</li>\n</ul>\n"
    "```\n\n"
    "---\n\n"
    "**Archivo fuente:** `Agentes/outputs/brief-pool/epic-gmr.html` (ya persistido).\n\n"
    "**Verificaciones contra el brief del operador:**\n"
    "- EP-30 / RF-030 aplicados ✅\n"
    "- 1 solo ticket RF ✅\n\n"
    "Cuando aprobés la épica, Stacky la publica vía `POST /api/tickets/epics/from-brief`."
)


# ---------------------------------------------------------------------------
# 1) El extractor: del output crudo saca el HTML de épica LIMPIO.
# ---------------------------------------------------------------------------

def test_extract_epic_html_from_real_run_output():
    from api.tickets import _extract_epic_html

    cleaned = _extract_epic_html(_REAL_RUN_OUTPUT)

    # Debe contener la épica…
    assert "<h1>EP-30" in cleaned
    assert "RF-030" in cleaned
    # …y NADA del preámbulo conversacional ni del resumen/fences.
    assert "Voy a leer el archivo" not in cleaned
    assert "Leyendo el índice" not in cleaned
    assert "```" not in cleaned, "no deben quedar fences markdown"
    assert "Verificaciones contra el brief" not in cleaned
    assert "✅" not in cleaned
    assert "POST /api/tickets/epics/from-brief" not in cleaned


def test_extract_epic_html_passthrough_clean_html():
    """HTML ya limpio (sin fences) debe devolverse intacto (compat hacia atrás)."""
    from api.tickets import _extract_epic_html

    clean = "<h1>Épica</h1><p>Contenido</p>"
    assert _extract_epic_html(clean).strip() == clean


def test_extract_epic_html_empty_safe():
    from api.tickets import _extract_epic_html

    assert _extract_epic_html("") == ""
    assert _extract_epic_html(None) == ""


def test_extract_epic_html_dedups_identical_blocks():
    """El CLI a veces emite el mismo bloque html dos veces; tomar uno solo."""
    from api.tickets import _extract_epic_html

    block = "<h1>EP-30</h1>\n<p>X</p>"
    raw = f"intro\n\n```html\n{block}\n```\n\nmedio\n\n```html\n{block}\n```\n\nfin"
    cleaned = _extract_epic_html(raw)
    assert cleaned.count("<h1>EP-30</h1>") == 1


# ---------------------------------------------------------------------------
# 2) El endpoint sanea el description_html crudo antes de mandarlo a ADO.
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    from app import create_app
    app = create_app()
    with app.test_client() as c:
        yield c


def test_endpoint_sanitizes_raw_output_before_ado(client, monkeypatch):
    """El description_html crudo (output del agente) llega LIMPIO a create_work_item."""
    captured = {}

    mock_client = MagicMock()

    def _capture_create(**kwargs):
        captured.update(kwargs)
        return {
            "id": 9999,
            "fields": {"System.Title": kwargs.get("title", "T")},
            "_links": {"html": {"href": "https://dev.azure.com/x/_workitems/edit/9999"}},
        }

    mock_client.create_work_item.side_effect = _capture_create
    mock_client.work_item_url.return_value = "https://dev.azure.com/x/_workitems/edit/9999"

    monkeypatch.setattr("api.tickets._ado_client_for_ticket", lambda **kw: mock_client)
    import api.tickets as t_mod
    monkeypatch.setattr(t_mod, "_epic_brief_save", lambda *a, **k: None)

    body = {
        "title": "EP-30 GMR",
        "description_html": _REAL_RUN_OUTPUT,  # output CRUDO de la run real
        "brief": "brief",
        "project_name": "P",
        "confirm": True,
    }
    resp = client.post(
        "/api/tickets/epics/from-brief",
        data=json.dumps(body),
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)

    sent = captured.get("description", "")
    assert "<h1>EP-30" in sent
    assert "Voy a leer el archivo" not in sent
    assert "```" not in sent
    assert "✅" not in sent


# ---------------------------------------------------------------------------
# 3) Derivación de título: auto-publicación sin título manual del operador.
# ---------------------------------------------------------------------------

def test_derive_title_prefers_first_heading():
    from api.tickets import _derive_epic_title

    assert _derive_epic_title("<h1>EP-30 — GMR</h1><h2>RF-030</h2>") == "EP-30 — GMR"


def test_derive_title_strips_nested_tags():
    from api.tickets import _derive_epic_title

    assert _derive_epic_title("<h1>EP-1 <strong>Core</strong></h1>") == "EP-1 Core"


def test_derive_title_unescapes_entities():
    from api.tickets import _derive_epic_title

    assert _derive_epic_title("<h1>Cobros &amp; Pagos</h1>") == "Cobros & Pagos"


def test_derive_title_falls_back_to_text_without_heading():
    from api.tickets import _derive_epic_title

    assert _derive_epic_title("<p>Solo un parrafo</p>") == "Solo un parrafo"


def test_derive_title_empty_uses_fallback():
    from api.tickets import _derive_epic_title

    assert _derive_epic_title("") == "Épica generada desde brief"
    assert _derive_epic_title(None) == "Épica generada desde brief"
    assert _derive_epic_title("<div></div>") == "Épica generada desde brief"


def test_derive_title_extracts_clean_epic_from_real_run_output():
    """Sobre el output CRUDO de la run real: extraer HTML + derivar título."""
    from api.tickets import _derive_epic_title, _extract_epic_html

    title = _derive_epic_title(_extract_epic_html(_REAL_RUN_OUTPUT))
    assert title == "EP-30 — Incorporación de acceso directo al motor GMR"


def test_derive_title_truncates_long():
    from api.tickets import _derive_epic_title

    out = _derive_epic_title("<h1>" + "A" * 400 + "</h1>")
    assert len(out) <= 250
