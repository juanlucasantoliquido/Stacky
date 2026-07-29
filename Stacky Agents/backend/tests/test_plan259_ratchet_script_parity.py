"""Plan 259 F8.b — Guardian de paridad .sh <-> .ps1 del ratchet del arnes.

POR QUE EXISTE. `test_harness_ratchet_meta.py` parsea SOLO el `.sh`; la unica
garantia del gemelo Windows es un comentario que dice "Mantener en sync". Ya
fallo dos veces: el plan 266 con una coma colgante (el parser gritaba) y este plan
con comillas faltantes (el parser NO grita: PowerShell lee cada ruta pelada como
un NOMBRE DE COMANDO, asi que el array parsea con 0 errores y las rutas nuevas se
pierden MUDAS).

DISEÑO — TEXTO, NO POWERSHELL. El test no invoca PowerShell: seria atarlo a un
runtime. Parsea los dos archivos con `re` y compara conjuntos, asi que corre igual
en Codex CLI, Claude Code CLI y GitHub Copilot Pro, en Windows y fuera.
"""
from __future__ import annotations

import pathlib
import re

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_SH = _BACKEND / "scripts" / "run_harness_tests.sh"
_PS1 = _BACKEND / "scripts" / "run_harness_tests.ps1"

# .sh:  rutas peladas, una por linea       -> tests/foo.py
_SH_RE = re.compile(r"^\s*(tests/[\w/]+\.py)\s*$", re.M)
# .ps1: rutas ENTRECOMILLADAS, con coma    -> "tests/foo.py",
_PS1_RE = re.compile(r'^\s*"(tests/[\w/]+\.py)"\s*,?\s*$', re.M)

_PLAN259 = (
    "tests/test_plan259_setup_guide_data.py",
    "tests/test_plan259_project_manager_gitlab.py",
    "tests/test_plan259_api_projects_gitlab.py",
    "tests/test_plan259_gitlab_token_dpapi.py",
    "tests/test_plan259_setup_guide_api.py",
    "tests/test_plan259_enable_engine.py",
    "tests/test_plan259_tracker_parity_guard.py",
    "tests/test_plan259_ratchet_script_parity.py",
)

# Plan 259 v4 (N2) — DEUDA AJENA MEDIDA, no un objetivo. Al escribir este plan el
# .sh tenia 687 rutas y el .ps1 623: el .ps1 viene 64 archivos atras por deriva de
# planes anteriores (test_mg_*, test_plan70_group_*, test_plan237/238/239_*,
# test_rag_*, ...). Exigir igualdad de conjuntos haria este test ROJO DE FABRICA y
# obligaria a arreglar rojo ajeno, que este plan prohibe. Es un RATCHET: solo baja.
_PS1_LAG_MAX = 64


def _sh() -> set[str]:
    return set(_SH_RE.findall(_SH.read_text(encoding="utf-8")))


def _ps1() -> set[str]:
    return set(_PS1_RE.findall(_PS1.read_text(encoding="utf-8")))


def test_las_dos_listas_son_no_vacias():
    """Un regex que deja de matchear por un cambio de formato daria dos conjuntos
    vacios y los otros tests pasarian EN FALSO. Este lo tapa."""
    assert len(_sh()) >= 100, f".sh: solo {len(_sh())} rutas"
    assert len(_ps1()) >= 100, f".ps1: solo {len(_ps1())} rutas"


@pytest.mark.parametrize("ruta", _PLAN259)
def test_los_8_de_este_plan_estan_en_las_dos_listas(ruta):
    """CRITERIO PROPIO DEL PLAN. Es el que atrapa las comillas faltantes: si
    alguien pega las rutas peladas en el .ps1, no aparecen en _ps1() y el test lo
    dice por nombre."""
    assert ruta in _sh(), f"{ruta} falta en run_harness_tests.sh"
    assert ruta in _ps1(), (
        f"{ruta} falta en run_harness_tests.ps1 "
        f"(¿la pegaste SIN comillas? el .ps1 usa \"ruta\", con coma)"
    )


def test_el_ps1_no_tiene_rutas_sin_comillas():
    """El modo de falla EXACTO de B5: parsea bien, evalua a nada."""
    peladas = _SH_RE.findall(_PS1.read_text(encoding="utf-8"))
    assert peladas == [], (
        "el .ps1 tiene rutas SIN comillas (sintaxis del .sh). PowerShell las lee "
        f"como nombres de comando y el array las pierde en silencio: {peladas}"
    )


def test_el_ps1_no_pierde_terreno():
    """Delta contra el rojo MEDIDO, no igualdad (v4, hallazgo N2)."""
    sh, ps1 = _sh(), _ps1()
    solo_en_ps1 = ps1 - sh
    solo_en_sh = sh - ps1
    assert solo_en_ps1 == set(), (
        f"el .ps1 tiene rutas que el .sh no tiene: {sorted(solo_en_ps1)}"
    )
    assert len(solo_en_sh) <= _PS1_LAG_MAX, (
        f"el .ps1 perdio terreno: {len(solo_en_sh)} archivos solo en el .sh "
        f"(maximo {_PS1_LAG_MAX}). Agregalos al .ps1 CON COMILLAS. "
        f"Bajar _PS1_LAG_MAX es alcance de quien salde esa deuda.\n"
        f"solo_en_sh: {sorted(solo_en_sh)}"
    )


def test_ninguna_ruta_apunta_a_un_archivo_inexistente():
    """test_harness_ratchet_meta ya lo hace para el .sh; aca se extiende al .ps1."""
    faltantes = sorted(r for r in (_sh() | _ps1()) if not (_BACKEND / r).exists())
    assert faltantes == [], f"rutas registradas que no existen en disco: {faltantes}"
