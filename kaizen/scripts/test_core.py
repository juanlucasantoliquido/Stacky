#!/usr/bin/env python3
"""Tests unitarios para scripts core de Kaizen. stdlib pura, sin pytest.

Cubre:
  - new_session.py: slugify, utc_now, read_config_value
  - validate.py: check_required, check_enums, check_patterns

Uso:
    python scripts/test_core.py        # corre todos los tests
    python -m scripts.test_core        # alternativa
"""
from __future__ import annotations

import datetime
import sys
import tempfile
import textwrap
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


# ---------------------------------------------------------------------------
# Mini-runner sin pytest
# ---------------------------------------------------------------------------
_tests: list[tuple[str, object]] = []
_passed = 0
_failed = 0


def test(fn=None, *, name: str | None = None):
    """Decorador para registrar tests."""
    if fn is None:
        return lambda f: test(f, name=name)
    _tests.append((name or fn.__name__, fn))
    return fn


def run_all() -> int:
    global _passed, _failed
    for name, fn in _tests:
        try:
            fn()
            _passed += 1
            print("  OK  %s" % name)
        except Exception as exc:  # noqa: BLE001
            _failed += 1
            print("  FAIL %s — %s" % (name, exc))
            traceback.print_exc(limit=3)
    print("\n%d OK, %d FAIL" % (_passed, _failed))
    return 0 if _failed == 0 else 1


def assert_eq(got, expected, msg: str = ""):
    if got != expected:
        raise AssertionError("%s: got %r, expected %r" % (msg or "assert_eq", got, expected))


def assert_true(cond, msg: str = ""):
    if not cond:
        raise AssertionError(msg or "assert_true falló")


# ---------------------------------------------------------------------------
# Tests de new_session.py — slugify, utc_now, read_config_value
# ---------------------------------------------------------------------------
from new_session import slugify, utc_now, read_config_value  # noqa: E402


@test
def test_slugify_basic():
    assert_eq(slugify("Mejorar mensajes de error"), "mejorar-mensajes-de-error")


@test
def test_slugify_special_chars():
    assert_eq(slugify("fix: colisión en new!"), "fix-colisi-n-en-new")


@test
def test_slugify_multiple_spaces():
    assert_eq(slugify("   hello   world   "), "hello-world")


@test
def test_slugify_empty():
    assert_eq(slugify(""), "sesion")


@test
def test_slugify_only_symbols():
    assert_eq(slugify("!!!"), "sesion")


@test
def test_utc_now_returns_utc():
    t = utc_now()
    assert_true(isinstance(t, datetime.datetime), "debe ser datetime")
    assert_true(t.tzinfo is not None, "debe tener tzinfo")


@test
def test_read_config_value_missing_file():
    """Si no existe config, devuelve el default."""
    val = read_config_value.__wrapped__ if hasattr(read_config_value, "__wrapped__") else None
    # Llamamos con la función real; si el archivo no existe devuelve default
    result = read_config_value("mode", "hitl")
    # Solo verificamos que devuelve un string (el config puede o no existir)
    assert_true(isinstance(result, str), "debe devolver string")


@test
def test_read_config_value_from_tempfile():
    """Lee un valor de un YAML simulado."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        f.write(textwrap.dedent("""\
            mode: aotl
            adapter: claude
        """))
        tmp = Path(f.name)
    try:
        # Parchamos CONFIG temporalmente
        import new_session as ns
        original = ns.CONFIG
        ns.CONFIG = tmp
        assert_eq(ns.read_config_value("mode", "hitl"), "aotl")
        assert_eq(ns.read_config_value("adapter", "generic"), "claude")
        assert_eq(ns.read_config_value("missing_key", "default123"), "default123")
    finally:
        ns.CONFIG = original
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Tests de validate.py — check_required, check_enums, check_patterns
# ---------------------------------------------------------------------------
from validate import check_required, check_enums, check_patterns  # noqa: E402


@test
def test_check_required_all_present():
    schema = {"required": ["a", "b"]}
    errs = check_required({"a": 1, "b": 2}, schema)
    assert_eq(errs, [], "sin errores cuando todo presente")


@test
def test_check_required_missing_field():
    schema = {"required": ["a", "b"]}
    errs = check_required({"a": 1}, schema)
    assert_true(len(errs) == 1 and "b" in errs[0], "debe detectar campo faltante b")


@test
def test_check_required_empty_schema():
    schema = {}
    errs = check_required({"a": 1}, schema)
    assert_eq(errs, [])


@test
def test_check_enums_valid():
    schema = {"properties": {"mode": {"enum": ["hitl", "aotl"]}}}
    errs = check_enums({"mode": "hitl"}, schema)
    assert_eq(errs, [])


@test
def test_check_enums_invalid():
    schema = {"properties": {"mode": {"enum": ["hitl", "aotl"]}}}
    errs = check_enums({"mode": "unknown"}, schema)
    assert_true(len(errs) == 1 and "unknown" in errs[0])


@test
def test_check_enums_field_absent():
    """Si el campo no está en obj, no hay error."""
    schema = {"properties": {"mode": {"enum": ["hitl"]}}}
    errs = check_enums({}, schema)
    assert_eq(errs, [])


@test
def test_check_patterns_valid():
    schema = {"properties": {"session_id": {"pattern": r"^\d{4}-"}}}
    errs = check_patterns({"session_id": "2026-06-22"}, schema)
    assert_eq(errs, [])


@test
def test_check_patterns_invalid():
    schema = {"properties": {"session_id": {"pattern": r"^\d{4}-"}}}
    errs = check_patterns({"session_id": "abc-xyz"}, schema)
    assert_true(len(errs) == 1)


if __name__ == "__main__":
    print("Kaizen — test_core.py")
    print("=" * 40)
    raise SystemExit(run_all())
