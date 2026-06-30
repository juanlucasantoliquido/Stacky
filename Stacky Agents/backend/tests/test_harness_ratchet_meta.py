"""Plan 49 F4 — Meta-test del ratchet de cobertura del arnés.

Falla si un archivo tests/test_*.py nuevo no está ni en HARNESS_TEST_FILES
(scripts/run_harness_tests.sh) ni en una allowlist explícita con motivo.
Convierte el ratchet de manual a auto-verificado: impide que la cobertura del
arnés se encoja en silencio.
"""

import re
import pathlib

_BACKEND = pathlib.Path(__file__).resolve().parents[1]  # backend/
_SCRIPT = _BACKEND / "scripts" / "run_harness_tests.sh"
_ALLOWLIST = _BACKEND / "tests" / "harness_ratchet_allowlist.txt"
_TESTS_DIR = _BACKEND / "tests"


def _ratchet_files() -> set[str]:
    """Parsea HARNESS_TEST_FILES del .sh: líneas que son sólo 'tests/....py'."""
    text = _SCRIPT.read_text(encoding="utf-8")
    return set(re.findall(r"^\s*(tests/[\w/]+\.py)\s*$", text, re.MULTILINE))


def _allowlist() -> set[str]:
    if not _ALLOWLIST.exists():
        return set()
    out = set()
    for line in _ALLOWLIST.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.add(line)
    return out


def _all_test_files() -> set[str]:
    """Todos los tests/test_*.py relativos a backend/, posix-normalizados."""
    return {
        p.relative_to(_BACKEND).as_posix()
        for p in _TESTS_DIR.rglob("test_*.py")
    }


def test_ratchet_clasifica_todos_los_tests():
    ratchet = _ratchet_files()
    allow = _allowlist()
    todos = _all_test_files()
    sin_clasificar = sorted(todos - ratchet - allow)
    assert not sin_clasificar, (
        "Tests no clasificados (agregalos a HARNESS_TEST_FILES en "
        "scripts/run_harness_tests.sh si pasan aislados, o a "
        "tests/harness_ratchet_allowlist.txt con motivo):\n  - "
        + "\n  - ".join(sin_clasificar)
    )


def test_allowlist_no_se_solapa_con_ratchet():
    overlap = _ratchet_files() & _allowlist()
    assert not overlap, (
        f"Archivos en ratchet Y allowlist (redundante): {sorted(overlap)}"
    )


def test_ratchet_no_referencia_archivos_inexistentes():
    faltantes = sorted(f for f in _ratchet_files() if not (_BACKEND / f).exists())
    assert not faltantes, (
        f"HARNESS_TEST_FILES referencia archivos inexistentes: {faltantes}"
    )
