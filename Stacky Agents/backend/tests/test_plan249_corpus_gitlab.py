"""Plan 249 F0 — el corpus GitLab: tres niveles, procedencia declarada, guardia regenerable."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND / "scripts") not in sys.path:
    sys.path.insert(0, str(BACKEND / "scripts"))

import regen_gitlab_derived_corpus as regen  # noqa: E402

GOLDEN = BACKEND / "tests" / "fixtures" / "cicd_nl" / "golden"
DERIVED = BACKEND / "tests" / "fixtures" / "cicd_gitlab" / "derived"
PROCEDENCIA = BACKEND / "tests" / "fixtures" / "cicd_gitlab" / "PROCEDENCIA.md"


def _origenes() -> list:
    return sorted(p for p in GOLDEN.glob("*.yml"))


def test_derivado_regenera_identico():
    """Guardia de deriva del nivel A: la receta reproduce el disco byte a byte."""
    for origen in _origenes():
        esperado = (regen.PROVENANCE_HEADER_FMT % origen.name) + regen.render_derived(
            origen.read_text(encoding="utf-8"))
        destino = DERIVED / regen.derived_name(origen.name)
        assert destino.exists(), destino
        assert destino.read_text(encoding="utf-8") == esperado, origen.name


def test_derivado_tiene_header_de_procedencia():
    for origen in _origenes():
        destino = DERIVED / regen.derived_name(origen.name)
        assert destino.read_text(encoding="utf-8").startswith("# DERIVADO - NO EDITAR A MANO.")


def test_derivado_no_depende_de_ruta_externa():
    fuente = (BACKEND / "scripts" / "regen_gitlab_derived_corpus.py").read_text(encoding="utf-8")
    assert "N:\\" not in fuente
    assert "RSPACIFICO" not in fuente


def test_procedencia_declara_los_tres_niveles():
    texto = PROCEDENCIA.read_text(encoding="utf-8")
    assert "nivel A" in texto
    assert "nivel B" in texto
    assert "nivel C" in texto
    assert "no existe corpus GitLab real" in texto


def test_nivel_c_esta_vacio_y_es_intencional():
    """CONTRATO, no accidente: no se fabrica un golden GitLab 'real'."""
    real = BACKEND / "tests" / "fixtures" / "cicd_gitlab" / "real"
    assert (not real.exists()) or not any(real.iterdir())


def test_foto_del_defecto_2026_07_26():
    """Congela §2.2 al dia de hoy. **F3 debe romper este test a proposito** y actualizarlo.

    ACTUALIZADO EN F3 (2026-07-26): antes de F3 los 9 derivados sumaban 0 comandos reales y
    dos traian `echo 'no-op'`. Despues de F3 la foto es la de abajo, y el diff de los 9
    archivos derivados es la evidencia revisable de que el renderer mejoro de verdad.
    """
    textos = {p.name: p.read_text(encoding="utf-8") for p in sorted(DERIVED.glob("*.yml"))}
    assert len(textos) == 9
    # Post-F3: los 9 emiten al menos un job con cuerpo, y ninguno queda con SOLO `no-op`.
    for nombre, texto in textos.items():
        assert "script:" in texto, nombre
    con_noop_unico = [n for n, t in textos.items()
                      if t.count("script:") == 1 and "no-op" in t]
    assert con_noop_unico == [], con_noop_unico
