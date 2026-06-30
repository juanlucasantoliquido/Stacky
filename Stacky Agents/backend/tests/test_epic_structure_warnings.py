"""Plan 50 F2 — Warnings estructurales deterministas de la épica."""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from api.tickets import _structural_epic_warnings, _epic_grounding_warnings


def test_rf_no_consecutiva():
    out = _structural_epic_warnings("<h2>RF-1</h2><p>a</p><h2>RF-3</h2><p>b</p>")
    assert any("no consecutiva" in w and "2" in w for w in out)


def test_rf_duplicados():
    out = _structural_epic_warnings("<h2>RF-2</h2><p>a</p><h2>RF-2</h2><p>b</p>")
    assert any("duplicados" in w and "2" in w for w in out)


def test_headings_vacios():
    out = _structural_epic_warnings("<h1></h1><h2>RF-1</h2><p>x</p>")
    assert any("headings vacíos" in w for w in out)


def test_bloque_rf_sin_contenido():
    out = _structural_epic_warnings("<h2>RF-1</h2><h2>RF-2</h2><p>x</p>")
    assert any("sin contenido" in w for w in out)


def test_epica_bien_formada_sin_warnings():
    html = "<h2>RF-1</h2><p>a</p><h2>RF-2</h2><p>b</p><h2>RF-3</h2><p>c</p>"
    assert _structural_epic_warnings(html) == []


def test_flag_off_no_agrega_estructurales(monkeypatch):
    monkeypatch.setenv("STACKY_EPIC_STRUCTURE_WARNINGS_ENABLED", "false")
    # HTML con RF duplicado pero que SÍ cita módulo/proceso (sin warning histórico)
    html = "<p>proceso X</p><h2>RF-2</h2><p>a</p><h2>RF-2</h2><p>b</p>"
    out = _epic_grounding_warnings(html)
    assert not any("epic_structure" in w for w in out)


def test_flag_on_agrega_estructurales(monkeypatch):
    monkeypatch.setenv("STACKY_EPIC_STRUCTURE_WARNINGS_ENABLED", "true")
    html = "<p>proceso X</p><h2>RF-2</h2><p>a</p><h2>RF-2</h2><p>b</p>"
    out = _epic_grounding_warnings(html)
    assert any("epic_structure" in w for w in out)
