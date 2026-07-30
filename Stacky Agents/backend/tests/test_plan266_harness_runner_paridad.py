"""Plan 266 F6.5 — el runner .ps1 del arnés no tiene gate propio. Este es.

El .ps1 dice "mantener en sync con run_harness_tests.sh" y nadie lo verificaba;
el meta-test (test_harness_ratchet_meta.py:13) parsea SOLO el .sh.

Python puro: no invoca pwsh ni PowerShell, solo lee los dos archivos como texto.
Corre igual en los 3 runtimes, en Linux y en CI sin PowerShell instalado.
"""
import re
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
_SH = _SCRIPTS / "run_harness_tests.sh"
_PS1 = _SCRIPTS / "run_harness_tests.ps1"

_SH_ENTRY = re.compile(r"^\s*(tests/[\w/]+\.py)\s*$", re.M)
_PS1_ENTRY = re.compile(r'^\s*"(tests/[\w/]+\.py)"\s*,?\s*$', re.M)


def _sh_files() -> set[str]:
    return set(_SH_ENTRY.findall(_SH.read_text(encoding="utf-8")))


def _ps1_files() -> set[str]:
    return set(_PS1_ENTRY.findall(_PS1.read_text(encoding="utf-8")))


def test_ps1_sin_coma_colgante():
    # El corazón de C12: una coma colgante justo antes del ")" de cierre del
    # array revienta el parser de PowerShell entero. Implementación literal
    # (C33): para cada línea que es solo ")", la última línea NO vacía anterior
    # no puede terminar en coma.
    lineas = _PS1.read_text(encoding="utf-8").splitlines()
    for i, linea in enumerate(lineas):
        if linea.strip() != ")":
            continue
        j = i - 1
        while j >= 0 and lineas[j].strip() == "":
            j -= 1
        assert j >= 0, f"no se encontró línea no vacía antes de la línea {i + 1}"
        assert not lineas[j].rstrip().endswith(","), (
            f"coma colgante en run_harness_tests.ps1:{j + 1} justo antes del "
            f"cierre ')' en la línea {i + 1} — PowerShell no admite coma "
            f"colgante en un literal de array."
        )


def test_ps1_es_subconjunto_del_sh():
    # Invariante medido y cierto hoy (.ps1 ⊆ .sh): cazaría un archivo agregado
    # al .ps1 y olvidado en el .sh, que es el que rompe el meta-test.
    extras = _ps1_files() - _sh_files()
    assert extras == set(), f"archivos SOLO en el .ps1 (faltan en el .sh): {sorted(extras)}"


def test_los_tests_de_este_plan_estan_en_los_dos():
    esperados = {
        "tests/test_plan266_summary_shape.py",
        "tests/test_plan266_harness_runner_paridad.py",
        "tests/test_plan266_flag_cableado.py",
    }
    sh = _sh_files()
    ps1 = _ps1_files()
    faltan_sh = esperados - sh
    faltan_ps1 = esperados - ps1
    assert not faltan_sh, f"faltan en run_harness_tests.sh: {sorted(faltan_sh)}"
    assert not faltan_ps1, f"faltan en run_harness_tests.ps1: {sorted(faltan_ps1)}"


def test_ambas_listas_no_estan_vacias():
    # Anti-censo-vacío, calibrado contra la realidad medida (no contra un
    # número cómodo): mismo criterio que F4 test 12 le exigió al censo del
    # centinela.
    assert len(_sh_files()) >= 600
    assert len(_ps1_files()) >= 600
