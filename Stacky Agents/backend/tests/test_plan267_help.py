"""Plan 267 §4.1 [C10 + C28] — verificador ACOTADO de las 3 entradas de PLAIN_HELP.

POR QUE EXISTE: tests/test_harness_flags_help.py arrastra fallos AJENOS
preexistentes (medido 2026-07-29: 4 failed / 4 passed), y esos rojos son
exactamente las reglas que las entradas nuevas deben cumplir. Un modelo menor no
puede distinguir su propio error del rojo preexistente, asi que ese archivo NO es
criterio de aceptacion de ninguna fase de este plan; este si lo es, porque mira
SOLO las 3 claves del plan 267.

POR QUE ES UN TEST Y NO UN SCRIPT EN scripts/: nacio como
scripts/check_plan267_help.py y eso rompia
test_harness_flags_help.py::test_no_runtime_imports_plain_help, el centinela de
impacto NULO en los 3 runtimes — solo el registry y tests/ pueden referirse a
harness_flags_help. Vive aca para respetar ese centinela sin debilitarlo, y de
paso corre en el arnes como cualquier otro test.

Tampoco se usa `pytest -k` para acotar: un -k que no matchea nada devuelve
`N deselected` con EXIT 0, o sea un falso verde perfecto.
"""
from __future__ import annotations

import re

import pytest

from services.harness_flags_help import PLAIN_HELP

# Denylist congelada de tests/test_harness_flags_help.py: 15 palabras, match por
# palabra completa e insensible a mayusculas.
DENYLIST = (
    "MCP", "TF-IDF", "LLM", "stdin", "stdout", "endpoint", "frontmatter",
    "prompt", "token", "regex", "backend", "frontend", "gate", "hook", "runtime",
)
LIMITES = {"what": 200, "on_effect": 240, "off_effect": 240, "example": 300}
CLAVES = (
    "STACKY_DEVOPS_ACTION_CATALOG_ENABLED",
    "STACKY_DEVOPS_ACTION_NL_ENABLED",
    "STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED",
)

_KEY_RE = re.compile(r"\b[A-Z]+_[A-Z0-9_]+\b")
_PHASE_RE = re.compile(r"\bF\d")


def _texto(ayuda) -> str:
    return " ".join([ayuda.what, ayuda.on_effect, ayuda.off_effect, ayuda.example])


@pytest.mark.parametrize("clave", CLAVES)
def test_la_clave_tiene_ayuda_llana(clave):
    assert PLAIN_HELP.get(clave) is not None, f"{clave}: FALTA en PLAIN_HELP"


@pytest.mark.parametrize("clave", CLAVES)
def test_campos_no_vacios_y_acotados(clave):
    ayuda = PLAIN_HELP[clave]
    excesos = []
    for campo, maximo in LIMITES.items():
        valor = getattr(ayuda, campo)
        if not valor:
            excesos.append(f"{campo}: VACIO")
        elif len(valor) > maximo:
            excesos.append(f"{campo}: largo {len(valor)} > {maximo}")
    assert excesos == [], f"{clave} -> {excesos}"


@pytest.mark.parametrize("clave", CLAVES)
def test_efectos_empiezan_con_si(clave):
    ayuda = PLAIN_HELP[clave]
    malos = [c for c in ("on_effect", "off_effect") if not getattr(ayuda, c).startswith("Si ")]
    assert malos == [], f"{clave}: estos no empiezan con 'Si ' -> {malos}"


@pytest.mark.parametrize("clave", CLAVES)
def test_sin_jerga_prohibida(clave):
    texto = _texto(PLAIN_HELP[clave])
    hits = [p for p in DENYLIST if re.search(r"\b" + re.escape(p) + r"\b", texto, re.I)]
    assert hits == [], f"{clave}: jerga prohibida {hits}"


@pytest.mark.parametrize("clave", CLAVES)
def test_no_cita_claves_ni_fases(clave):
    texto = _texto(PLAIN_HELP[clave])
    problemas = []
    if _KEY_RE.search(texto):
        problemas.append("cita una clave en mayusculas")
    if _PHASE_RE.search(texto):
        problemas.append("cita una fase")
    assert problemas == [], f"{clave}: {problemas}"
