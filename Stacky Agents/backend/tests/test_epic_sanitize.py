"""Plan 50 F1 — Golden-set de _sanitize_epic_html (normaliza forma, no semántica)."""

import sys
import pathlib

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # backend/

from api.tickets import (
    _sanitize_epic_html,
    _extract_epic_html,
    _extract_epic_html_raw,
    _looks_like_epic,
    build_epic_summary,
)


# ── (1) RF-guion-espacio ──────────────────────────────────────────────────────

def test_rf_guion_espacio():
    assert "RF-12" in _sanitize_epic_html("<h2>RF- 12</h2>")
    assert "RF-12" in _sanitize_epic_html("<h2>RF -12</h2>")
    assert "RF-12" in _sanitize_epic_html("<h2>RF - 12</h2>")


# ── (2) fences residuales ─────────────────────────────────────────────────────

def test_fence_residual_se_elimina():
    out = _sanitize_epic_html("<h1>Épica</h1>\n```\n<h2>RF-1</h2>")
    assert "```" not in out
    assert "<h2>RF-1</h2>" in out


def test_backticks_en_linea_con_texto_se_preservan():
    # backticks dentro de una línea con más contenido NO se tocan (solo líneas
    # que son SOLO backticks).
    out = _sanitize_epic_html("<p>usar <code>```bash</code> aquí</p>")
    assert "```bash" in out


# ── (3) emojis de checklist ───────────────────────────────────────────────────

def test_emojis_checklist_eliminados():
    out = _sanitize_epic_html("<p>Validar entrada</p>\n✅ ☑ hecho")
    for e in "✅☑✔✓🟢❌⬜□▢":
        assert e not in out
    assert "Validar entrada" in out
    assert "hecho" in out


# ── (5) dedup de bloques RF idénticos ─────────────────────────────────────────

def test_dedup_bloques_rf_identicos():
    block = "<h2>RF-3</h2><p>Cuerpo X</p>"
    out = _sanitize_epic_html(block + "\n" + block)
    assert out.count("RF-3") == 1


def test_mismo_numero_cuerpo_distinto_se_preservan():
    html = "<h2>RF-2</h2><p>Cuerpo X</p>\n<h2>RF-2</h2><p>Cuerpo Y</p>"
    out = _sanitize_epic_html(html)
    assert "Cuerpo X" in out and "Cuerpo Y" in out
    assert out.count("RF-2") == 2


# ── casos borde ──────────────────────────────────────────────────────────────

def test_none_y_vacio():
    assert _sanitize_epic_html(None) == ""
    assert _sanitize_epic_html("") == ""
    assert _sanitize_epic_html("   ") == ""


def test_html_sin_rf_no_rompe():
    out = _sanitize_epic_html("<h1>Épica</h1><p>Sin requerimientos</p>")
    assert "<h1>Épica</h1>" in out


# ── (6) idempotencia sobre todo el corpus ─────────────────────────────────────

_CORPUS = [
    "<h2>RF- 12</h2>",
    "<h1>Épica</h1>\n```\n<h2>RF-1</h2>",
    "<p>Validar</p>\n✅ ☑ hecho",
    "<h2>RF-3</h2><p>X</p>\n<h2>RF-3</h2><p>X</p>",
    "<h2>RF-2</h2><p>X</p>\n<h2>RF-2</h2><p>Y</p>",
    "<h1>Épica</h1><p>Sin RF</p>",
    "",
]


@pytest.mark.parametrize("raw", _CORPUS, ids=range(len(_CORPUS)))
def test_idempotencia(raw):
    once = _sanitize_epic_html(raw)
    assert _sanitize_epic_html(once) == once


# ── caso Pacífico: no rompe estructura ────────────────────────────────────────

_PACIFICO = (
    "Voy a leer el archivo de entrada.\n\n"
    "```html\n"
    "<h1>Épica: Carga de procesos batch</h1>\n"
    "<h2>RF- 1 — Validar entrada Mul2Bane</h2><p>El proceso valida el formato.</p>\n"
    "<h2>RF-2 — Aplicar RSCore</h2><p>Aplica las reglas.</p>\n"
    "```\n\n"
    "Listo, escribí la épica. ✅ Todo OK"
)


def test_caso_pacifico_extrae_y_es_epica():
    clean = _extract_epic_html(_PACIFICO)
    assert _looks_like_epic(clean) is True
    assert "RF-1" in clean  # guion-espacio normalizado
    assert "Voy a leer" not in clean
    assert "✅" not in clean


# ── passthrough con flag OFF ──────────────────────────────────────────────────

def test_passthrough_flag_off(monkeypatch):
    monkeypatch.setenv("STACKY_EPIC_SANITIZE_ENABLED", "false")
    raw = "```html\n<h2>RF- 9</h2><p>X</p>\n```"
    out = _extract_epic_html(raw)
    # con flag OFF, el guion-espacio NO se normaliza (comportamiento histórico)
    assert "RF- 9" in out
    # _extract_epic_html_raw nunca sanitiza, independiente de la flag
    assert "RF- 9" in _extract_epic_html_raw(raw)


# ── [ADICIÓN] telemetría epic_sanitize_changed ────────────────────────────────

def test_epic_summary_sanitize_changed_flag():
    s = build_epic_summary(
        ado_id=1, ado_url="u", clean_html="<h2>RF-1</h2><p>x</p>",
        warnings=[], confidence=None, sanitize_changed=True,
    )
    assert s["epic_sanitize_changed"] is True
    s2 = build_epic_summary(
        ado_id=1, ado_url="u", clean_html="<h2>RF-1</h2><p>x</p>",
        warnings=[], confidence=None,
    )
    assert s2["epic_sanitize_changed"] is False
