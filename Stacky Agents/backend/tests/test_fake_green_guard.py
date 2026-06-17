"""Tests E1.2 — Guard anti-verde-falso (FakeGreenGuard).

Verifica detección de:
  (a) tests sin assert
  (b) 0 colectados
  (c) todos skip/xfail
  (d) cuerpo vacío / pass trivial

Restricciones:
  - Solo archivos de test en changed_files
  - Parseo fallido → no marcar (sin falsos positivos)
  - Soft por defecto; escalable a HARD con flag HARD
  - Flag OFF → byte-idéntico
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_BACKEND = Path(__file__).parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture(autouse=True)
def reset_cache():
    from services import exec_verification as _ev
    _ev._CACHE.clear()
    yield
    _ev._CACHE.clear()


def _run_guard(tmp_path, content: str, filename: str = "test_foo.py", hard: bool = False):
    """Helper: corre FakeGreenGuard sobre un archivo de test."""
    from config import Config
    from services.exec_verification import FakeGreenGuard
    test_file = tmp_path / filename
    test_file.write_text(content)

    with patch.object(Config, "STACKY_FAKE_GREEN_GUARD_HARD", hard):
        guard = FakeGreenGuard()
        return guard.run(str(tmp_path), [str(test_file)], timeout_s=10)


# ── 1. Test sin assert → marcado como soft-warn ──────────────────────────────

def test_no_assert_is_soft(tmp_path):
    content = """\
def test_nothing():
    x = 1 + 1
"""
    result = _run_guard(tmp_path, content)
    assert result.status in ("soft", "hard")
    assert "test" in result.detail.lower() or "assert" in result.detail.lower()


# ── 2. Test con assert → limpio ──────────────────────────────────────────────

def test_with_assert_is_clean(tmp_path):
    content = """\
def test_ok():
    assert 1 + 1 == 2
"""
    result = _run_guard(tmp_path, content)
    assert result.status == "passed"


# ── 3. Todos los tests marcados skip → marcado ───────────────────────────────

def test_all_skip_is_flagged(tmp_path):
    content = """\
import pytest

@pytest.mark.skip
def test_a():
    assert True

@pytest.mark.skip
def test_b():
    assert False
"""
    result = _run_guard(tmp_path, content)
    assert result.status in ("soft", "hard")


# ── 4. Cuerpo vacío (pass) → marcado ─────────────────────────────────────────

def test_empty_body_is_flagged(tmp_path):
    content = """\
def test_empty():
    pass
"""
    result = _run_guard(tmp_path, content)
    assert result.status in ("soft", "hard")


# ── 5. Archivo de test ajeno (no en changed_files) → ignorado ───────────────

def test_non_changed_file_ignored(tmp_path):
    """Si el archivo no está en changed_files, FakeGreenGuard no lo inspecciona."""
    test_file = tmp_path / "test_other.py"
    test_file.write_text("def test_nothing(): pass\n")

    from services.exec_verification import FakeGreenGuard
    from config import Config
    guard = FakeGreenGuard()
    # Pasamos changed_files vacío → no aplica
    assert not guard.applies(str(tmp_path), [])

    result = guard.run(str(tmp_path), [], timeout_s=10)
    assert result.status == "passed"


# ── 6. Parseo fallido → no marca (sin falsos positivos) ─────────────────────

def test_parse_failure_does_not_mark(tmp_path):
    """Archivo con sintaxis inválida para AST → no marca (evita FP)."""
    content = "def test_broken(:\n    pass\n"  # SyntaxError
    result = _run_guard(tmp_path, content)
    # Con parseo fallido, FakeGreenGuard retorna "passed" (no marca)
    assert result.status == "passed"


# ── 7. soft vs hard según flag ───────────────────────────────────────────────

def test_soft_default(tmp_path):
    content = "def test_nothing(): pass\n"
    result = _run_guard(tmp_path, content, hard=False)
    assert result.status == "soft"


def test_hard_with_flag(tmp_path):
    content = "def test_nothing(): pass\n"
    result = _run_guard(tmp_path, content, hard=True)
    assert result.status == "hard"


# ── 8. Archivo que no es de test → no aplica ─────────────────────────────────

def test_non_test_file_not_applicable(tmp_path):
    from services.exec_verification import FakeGreenGuard
    utils_file = tmp_path / "utils.py"
    utils_file.write_text("def helper(): pass\n")
    guard = FakeGreenGuard()
    assert not guard.applies(str(tmp_path), [str(utils_file)])


# ── 9. Test con xfail → marcado ──────────────────────────────────────────────

def test_all_xfail_is_flagged(tmp_path):
    content = """\
import pytest

@pytest.mark.xfail
def test_x():
    assert 1 == 2
"""
    result = _run_guard(tmp_path, content)
    assert result.status in ("soft", "hard")


# ── 10. Mix: un test con assert, otro sin → no marca (uno es válido) ─────────

def test_mixed_one_valid(tmp_path):
    """Si hay al menos un test válido con assert, no se marca como verde-falso."""
    content = """\
def test_no_assert():
    x = 1

def test_with_assert():
    assert 1 == 1
"""
    result = _run_guard(tmp_path, content)
    assert result.status == "passed"


# ── 11. Archivo de test JS/TS sin expect → marcado ──────────────────────────

def test_ts_test_no_expect(tmp_path):
    content = """\
describe('suite', () => {
  it('should work', () => {
    const x = 1;
  });
});
"""
    result = _run_guard(tmp_path, content, filename="foo.test.ts")
    assert result.status in ("soft", "hard")


# ── 12. Archivo de test JS/TS con expect → limpio ───────────────────────────

def test_ts_test_with_expect(tmp_path):
    content = """\
describe('suite', () => {
  it('should work', () => {
    expect(1 + 1).toBe(2);
  });
});
"""
    result = _run_guard(tmp_path, content, filename="bar.test.ts")
    assert result.status == "passed"


# ── 13. it.skip en JS/TS → marcado ──────────────────────────────────────────

def test_ts_all_skip(tmp_path):
    content = """\
describe('suite', () => {
  it.skip('should skip', () => {
    expect(1).toBe(1);
  });
});
"""
    result = _run_guard(tmp_path, content, filename="skip.test.ts")
    assert result.status in ("soft", "hard")


# ── 14. FakeGreenGuard en verify() con flag ENABLED ─────────────────────────

def test_fake_green_guard_in_verify(tmp_path):
    """Integration: verify() corre FakeGreenGuard cuando enabled."""
    test_file = tmp_path / "test_empty.py"
    test_file.write_text("def test_nothing():\n    pass\n")

    from config import Config
    with patch.object(Config, "STACKY_EXEC_VERIFICATION_ENABLED", True), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_MODE", "annotate"), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_TIMEOUT_S", 30), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_BUDGET_S", 120), \
         patch.object(Config, "STACKY_EXEC_VERIFICATION_PROJECTS", ""), \
         patch.object(Config, "STACKY_FAKE_GREEN_GUARD_HARD", False):
        from services.exec_verification import verify
        report = verify(workspace=str(tmp_path), changed_files=[str(test_file)])

    assert "FakeGreenGuard" in report.ran
    # Soft → no hard_failed pero sí soft
    assert any(r.name == "FakeGreenGuard" for r in report.soft)
    assert report.fake_green  # tiene entradas
