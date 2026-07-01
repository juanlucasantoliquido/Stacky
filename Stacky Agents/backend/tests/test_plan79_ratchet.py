"""Plan 79 — F7: ratchet — todos los test_plan79_*.py están registrados en
scripts/run_harness_tests.sh (regla ratchet-obliga-registrar-tests, Plan 49 F4).

Nota: el meta-test genérico tests/test_harness_ratchet_meta.py YA cubre esta
invariante para TODO test_*.py del repo (no solo plan79) y ya pasa con estos 8
archivos registrados. Este test es la verificación focalizada en plan79 que
pide el plan — evita duplicar el parseo del .sh reimportando el mismo regex.
"""
from __future__ import annotations

import pathlib
import re

_BACKEND = pathlib.Path(__file__).resolve().parent.parent
_SCRIPT = _BACKEND / "scripts" / "run_harness_tests.sh"
_TESTS_DIR = _BACKEND / "tests"


def _ratchet_files() -> set[str]:
    text = _SCRIPT.read_text(encoding="utf-8")
    return set(re.findall(r"^\s*(tests/[\w/]+\.py)\s*$", text, re.MULTILINE))


def test_all_plan79_test_files_are_registered_in_ratchet():
    ratchet = _ratchet_files()
    plan79_files = {
        f"tests/{p.name}" for p in _TESTS_DIR.glob("test_plan79_*.py")
    }
    missing = sorted(plan79_files - ratchet)
    assert not missing, (
        "Archivos test_plan79_*.py NO registrados en run_harness_tests.sh:\n  - "
        + "\n  - ".join(missing)
    )
