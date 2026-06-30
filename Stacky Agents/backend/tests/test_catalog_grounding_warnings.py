"""Plan 50 F3 — Linter puro de procesos citados contra el process_catalog."""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from api.tickets import _catalog_grounding_warnings

_CATALOG = [{"name": "Mul2Bane"}, {"name": "IncHost"}]


def test_proceso_en_catalogo_sin_warning():
    assert _catalog_grounding_warnings("<p>proceso Mul2Bane</p>", _CATALOG) == []


def test_proceso_fantasma_warning():
    out = _catalog_grounding_warnings("<p>proceso ProcesoFantasma</p>", _CATALOG)
    assert out and "ProcesoFantasma" in out[0]


def test_matching_normalizado():
    assert _catalog_grounding_warnings("<p>proceso  mul2bane </p>", _CATALOG) == []


def test_catalogo_vacio_o_none():
    assert _catalog_grounding_warnings("<p>proceso X</p>", []) == []
    assert _catalog_grounding_warnings("<p>proceso X</p>", None) == []


def test_html_sin_citas():
    assert _catalog_grounding_warnings("<h1>Épica</h1>", _CATALOG) == []
