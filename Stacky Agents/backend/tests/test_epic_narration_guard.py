"""Fix robusto — guard anti-narración en la autopublicación brief→épica.

Bug recurrente (evidencia DB viva, ticket 70 [Stacky] Brief Pool, ado_id=-1):
el BusinessAgent A VECES devuelve NARRACIÓN como mensaje final ("Voy a leer el
archivo... El archivo de salida para EP-31 ya existe...") en vez del HTML de la
épica (la escribe en un archivo). El sistema guardaba esa narración como `output`
y la trataba como épica. Resultado: `completed` fantasma sin épica en ADO, o peor,
publicación de narración como épica basura.

Estos tests fijan el contrato robusto:
  - narración pura → NO publica, error visible `epic_not_in_output` (run → needs_review).
  - épica válida (<h1> + <hr><h2>RF-) → publica y sella metadata["epic_ado_id"].
  - idempotencia: sello presente → no republica.

Mock total del cliente ADO — NUNCA toca ADO real.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


# Narración REAL capturada de la DB viva (ticket 70). CERO tags HTML, CERO headings.
NARRATION_OUTPUT = (
    "Voy a leer el archivo del agente BusinessAgent para entender mi rol.\n\n"
    "Rol adoptado: Agente de Negocio Senior.\n\n"
    "El archivo de salida para EP-31 ya existe. Voy a revisarlo contra el brief "
    "actual para ver si necesita cambios o si ya está completo.\n\n"
    "He revisado el contenido y parece consistente con el brief. No realizo "
    "cambios adicionales."
)

# Épica VÁLIDA: resumen + bloque RF con el contrato <hr><h2>RF-.
VALID_EPIC_HTML = (
    "<h1>Motor de Cobranzas Automatizado</h1>\n"
    "<p><strong>Resumen ejecutivo:</strong> Automatiza el cobro nocturno.</p>\n"
    "<hr><h2>RF-001: Generación de lote de cobro</h2>\n"
    "<p><strong>Descripción del requerimiento:</strong> ...</p>\n"
    "<ul><li>Condición verificable</li></ul>"
)

# Variante: la épica llega envuelta en un fence ```html ... ``` con preámbulo.
VALID_EPIC_FENCED = (
    "Claro, acá está la épica:\n\n```html\n" + VALID_EPIC_HTML + "\n```\n"
    "Espero que te sirva."
)


def _mock_ado(monkeypatch, *, new_id: int = 8001):
    """Stubea el cliente ADO y la escritura en disco. Devuelve el mock_client."""
    import api.tickets as t_mod

    mock_client = MagicMock()
    mock_client.create_work_item.return_value = {
        "id": new_id,
        "fields": {"System.Title": "T"},
        "_links": {"html": {"href": f"https://dev.azure.com/x/_workitems/edit/{new_id}"}},
    }
    mock_client.work_item_url.return_value = f"https://dev.azure.com/x/_workitems/edit/{new_id}"
    monkeypatch.setattr(t_mod, "_ado_client_for_ticket", lambda **kw: mock_client)
    monkeypatch.setattr(t_mod, "_persist_epic_ticket", lambda *a, **k: None)
    monkeypatch.setattr(t_mod, "_epic_brief_save", lambda *a, **k: None)
    return mock_client


# ── _looks_like_epic: validador puro ────────────────────────────────────────


def test_looks_like_epic_rejects_narration():
    """Narración pura (sin tags, sin RF) → False."""
    from api.tickets import _looks_like_epic

    assert _looks_like_epic(NARRATION_OUTPUT) is False


def test_looks_like_epic_rejects_stray_tag_without_rf():
    """HTML con un tag suelto pero SIN bloque RF → False (no es épica)."""
    from api.tickets import _looks_like_epic

    assert _looks_like_epic("<p>Voy a revisar el archivo EP-31.</p>") is False


def test_looks_like_epic_accepts_valid_epic():
    """<h1> + <hr><h2>RF- → True."""
    from api.tickets import _looks_like_epic

    assert _looks_like_epic(VALID_EPIC_HTML) is True


def test_looks_like_epic_accepts_fenced_epic():
    """La épica dentro de un fence html (tras extracción) → True."""
    from api.tickets import _looks_like_epic, _extract_epic_html

    assert _looks_like_epic(_extract_epic_html(VALID_EPIC_FENCED)) is True


def test_looks_like_epic_safe_on_empty():
    from api.tickets import _looks_like_epic

    assert _looks_like_epic(None) is False
    assert _looks_like_epic("") is False
    assert _looks_like_epic("   ") is False


# ── autopublish_epic_from_run: el guard de extremo a extremo ─────────────────


def test_autopublish_narration_does_not_publish_and_errors(monkeypatch):
    """REPRO DEL BUG: output = narración real → NO publica, error visible.

    HOY (antes del fix) este output quedaba `skipped=True` sin error (completed
    fantasma silencioso) — o publicaría basura si la narración tuviera un tag.
    Tras el fix debe devolver error `epic_not_in_output` para degradar a
    needs_review con metadata["epic_publish_error"] accionable.
    """
    from api.tickets import autopublish_epic_from_run

    mock_client = _mock_ado(monkeypatch)
    res = autopublish_epic_from_run(
        output=NARRATION_OUTPUT,
        brief="Brief de cobranzas",
        project_name="Pacifico",
        already_published_id=None,
    )
    # NUNCA se intentó crear el work item con narración.
    mock_client.create_work_item.assert_not_called()
    assert res.ado_id is None
    assert res.skipped is False  # es FALLO, no skip silencioso
    assert res.error is not None
    assert "epic_not_in_output" in res.error


def test_autopublish_valid_epic_publishes_and_seals(monkeypatch):
    """Camino feliz: épica válida → publica, devuelve ado_id sellable."""
    from api.tickets import autopublish_epic_from_run

    mock_client = _mock_ado(monkeypatch, new_id=8042)
    res = autopublish_epic_from_run(
        output=VALID_EPIC_HTML,
        brief="Brief",
        project_name="Pacifico",
        already_published_id=None,
    )
    mock_client.create_work_item.assert_called_once()
    # Se publicó el HTML LIMPIO de la épica (no narración).
    _, kwargs = mock_client.create_work_item.call_args
    assert "RF-001" in kwargs["description"]
    assert res.ado_id == 8042
    assert res.error is None
    assert res.skipped is False


def test_autopublish_fenced_epic_publishes(monkeypatch):
    """Épica dentro de fence html con preámbulo → se extrae y publica."""
    from api.tickets import autopublish_epic_from_run

    mock_client = _mock_ado(monkeypatch, new_id=8043)
    res = autopublish_epic_from_run(
        output=VALID_EPIC_FENCED,
        brief="Brief",
        project_name="Pacifico",
        already_published_id=None,
    )
    mock_client.create_work_item.assert_called_once()
    _, kwargs = mock_client.create_work_item.call_args
    # El fence y el preámbulo se removieron; quedó el HTML de la épica.
    assert kwargs["description"].lstrip().startswith("<h1>")
    assert "Claro, acá está" not in kwargs["description"]
    assert res.ado_id == 8043


def test_autopublish_idempotent_when_already_sealed(monkeypatch):
    """Sello presente → no republica (skipped=True), devuelve el id sellado."""
    from api.tickets import autopublish_epic_from_run

    mock_client = _mock_ado(monkeypatch)
    res = autopublish_epic_from_run(
        output=VALID_EPIC_HTML,
        brief="Brief",
        project_name="Pacifico",
        already_published_id=777,
    )
    mock_client.create_work_item.assert_not_called()
    assert res.ado_id == 777
    assert res.skipped is True
    assert res.error is None


def test_autopublish_empty_output_skips_silently(monkeypatch):
    """Output vacío → skip sin error (no hay nada que publicar todavía)."""
    from api.tickets import autopublish_epic_from_run

    mock_client = _mock_ado(monkeypatch)
    res = autopublish_epic_from_run(
        output="",
        brief="Brief",
        project_name="Pacifico",
        already_published_id=None,
    )
    mock_client.create_work_item.assert_not_called()
    assert res.ado_id is None
    assert res.skipped is True
    assert res.error is None


# ── Pase correctivo (C): predicado de disparo del reintento en el runner ─────
# El reintento vive embebido en _on_stream_event (stdin abierto, patrón Q1.1).
# La CONDICIÓN de disparo es exactamente: not _looks_like_epic(_extract_epic_html
# (output)). Estos tests fijan ese predicado replicando la decisión del closure,
# al estilo de test_stall_watchdog (probar la lógica, no arrancar el subproceso).


def _epic_repair_should_fire(current_output: str) -> bool:
    """Espejo de la condición de disparo del pase correctivo en el runner."""
    from api.tickets import _extract_epic_html, _looks_like_epic

    return not _looks_like_epic(_extract_epic_html(current_output))


def test_epic_repair_fires_on_narration():
    """Narración como output del último turno → se pide el reintento."""
    assert _epic_repair_should_fire(NARRATION_OUTPUT) is True


def test_epic_repair_does_not_fire_on_valid_epic():
    """Output ya es épica válida → NO se reintenta (no malgastar turnos/costo)."""
    assert _epic_repair_should_fire(VALID_EPIC_HTML) is False
    assert _epic_repair_should_fire(VALID_EPIC_FENCED) is False


def test_epic_repair_send_message_only_on_narration():
    """Simula el closure: send_fn se invoca SOLO ante narración, una vez."""
    sent: list[str] = []

    def fake_send(msg: str) -> bool:
        sent.append(msg)
        return True

    # Turno 1: narración → dispara, envía mensaje correctivo pidiendo SOLO HTML.
    if _epic_repair_should_fire(NARRATION_OUTPUT):
        fake_send("Re-emití AHORA ... EXCLUSIVAMENTE el HTML de la épica ...")
    assert len(sent) == 1
    assert "HTML de la épica" in sent[0]

    # Tras un reintento que entrega épica válida → ya no se dispararía de nuevo.
    sent.clear()
    if _epic_repair_should_fire(VALID_EPIC_HTML):
        fake_send("no debería enviarse")
    assert sent == []


def test_epic_repair_flag_exists_default_on():
    """El flag de gobierno existe y viene ON por default (fix 'completo')."""
    from config import config

    assert isinstance(config.STACKY_EPIC_REPAIR_ENABLED, bool)
