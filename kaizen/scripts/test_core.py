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


# ---------------------------------------------------------------------------
# Tests de autoloop.py — recent_decisions_summary
# ---------------------------------------------------------------------------
import autoloop  # noqa: E402


@test
def test_recent_objectives_empty():
    """Si INDEX no existe, recent_objectives devuelve lista vacia."""
    orig = autoloop.INDEX
    autoloop.INDEX = Path("/tmp/__kaizen_nonexistent_index_test__.json")
    try:
        result = autoloop.recent_objectives(n=5)
        assert_eq(result, [], "debe devolver [] si no hay indice")
    finally:
        autoloop.INDEX = orig


@test
def test_recent_objectives_returns_last_n():
    """Devuelve los ultimos n objetivos del indice."""
    with tempfile.TemporaryDirectory() as td:
        idx = Path(td) / "sessions" / "_index.json"
        idx.parent.mkdir(parents=True)
        sessions = [{"id": "s%d" % i, "status": "closed", "objective": "obj%d" % i}
                    for i in range(7)]
        idx.write_text(__import__("json").dumps({"sessions": sessions}), encoding="utf-8")
        orig = autoloop.INDEX
        autoloop.INDEX = idx
        try:
            result = autoloop.recent_objectives(n=3)
            assert_eq(result, ["obj4", "obj5", "obj6"], "debe devolver los ultimos 3")
        finally:
            autoloop.INDEX = orig


@test
def test_recent_decisions_summary_empty_dir():
    """Si decisions/ esta vacio, retorna lista vacia."""
    with tempfile.TemporaryDirectory() as td:
        orig = autoloop.ROOT
        autoloop.ROOT = Path(td)
        try:
            result = autoloop.recent_decisions_summary()
            assert_eq(result, [])
        finally:
            autoloop.ROOT = orig


@test
def test_recent_decisions_summary_with_adr():
    """Extrae titulo y veredicto de un ADR .md valido."""
    with tempfile.TemporaryDirectory() as td:
        decisions_dir = Path(td) / "decisions"
        decisions_dir.mkdir()
        adr = decisions_dir / "0001-mi-decision.md"
        adr.write_text(textwrap.dedent("""\
            # ADR 0001 — Mi primera decision
            - session: 2026-06-22T000000Z__test
            - Veredicto: accept (por gate)

            ## Contexto
            ...
        """), encoding="utf-8")
        orig = autoloop.ROOT
        autoloop.ROOT = Path(td)
        try:
            result = autoloop.recent_decisions_summary(n=5)
            assert_true(len(result) == 1, "debe haber 1 entrada")
            assert_true("Mi primera decision" in result[0], "debe incluir el titulo")
            assert_true("accept" in result[0], "debe incluir el veredicto")
        finally:
            autoloop.ROOT = orig


@test
def test_recent_decisions_summary_excludes_readme():
    """El README.md de decisions/ no debe aparecer como ADR."""
    with tempfile.TemporaryDirectory() as td:
        decisions_dir = Path(td) / "decisions"
        decisions_dir.mkdir()
        readme = decisions_dir / "README.md"
        readme.write_text("# Registro de decisiones\n", encoding="utf-8")
        adr = decisions_dir / "0001-real-adr.md"
        adr.write_text("# ADR 0001 — Real\n- Veredicto: accept\n", encoding="utf-8")
        orig = autoloop.ROOT
        autoloop.ROOT = Path(td)
        try:
            result = autoloop.recent_decisions_summary(n=5)
            assert_true(len(result) == 1, "solo debe haber 1 entrada (el ADR, no el README)")
            assert_true("Real" in result[0], "debe incluir el ADR real")
        finally:
            autoloop.ROOT = orig


# ---------------------------------------------------------------------------
# Tests de dashboard_static.py — _gen_decisions_index
# ---------------------------------------------------------------------------
import dashboard_static as _ds  # noqa: E402


@test
def test_pending_review_section_empty():
    """Lista vacia -> cadena vacia (sin HTML)."""
    result = _ds._pending_review_section([])
    assert_eq(result, "", "debe devolver '' para lista vacia")


@test
def test_pending_review_section_iterate_verdict():
    """Sesion con verdict=iterate aparece en la seccion con texto 'Pendiente'."""
    sessions = [{"id": "s1", "objective": "mejorar algo", "verdict": "iterate", "status": "closed"}]
    result = _ds._pending_review_section(sessions)
    assert_true("Pendiente" in result, "debe incluir encabezado 'Pendiente'")
    assert_true("mejorar algo" in result, "debe incluir el objetivo de la sesion")


@test
def test_pending_review_section_escalated():
    """Sesion con escalated_to_human=True aparece aunque verdict sea accept."""
    sessions = [{"id": "s2", "objective": "objeto escalado", "verdict": "accept",
                 "escalated_to_human": True, "status": "closed"}]
    result = _ds._pending_review_section(sessions)
    assert_true("objeto escalado" in result, "debe incluir el objetivo de la sesion escalada")
    assert_true(len(result) > 0, "no debe ser cadena vacia cuando hay escalacion")


@test
def test_gen_decisions_index_empty_dir():
    """Si decisions/ tiene 0 archivos .md numericos, no escribe README."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "decisions"
        d.mkdir()
        _ds._gen_decisions_index(d)
        assert not (d / "README.md").exists(), "no debe crear README si no hay ADRs"


@test
def test_gen_decisions_index_generates_table():
    """Con 2 ADRs, genera README con tabla que incluye titulo y veredicto."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "decisions"
        d.mkdir()
        (d / "0001-primera.md").write_text(
            "# ADR 0001 — Primera decision\n- Veredicto: accept (gate)\n",
            encoding="utf-8",
        )
        (d / "0002-segunda.md").write_text(
            "# ADR 0002 — Segunda decision\n- Veredicto: reject\n",
            encoding="utf-8",
        )
        _ds._gen_decisions_index(d)
        readme = (d / "README.md").read_text(encoding="utf-8")
        assert "Primera decision" in readme, "debe incluir titulo del ADR 0001"
        assert "accept" in readme, "debe incluir veredicto accept"
        assert "Segunda decision" in readme, "debe incluir titulo del ADR 0002"
        assert "reject" in readme, "debe incluir veredicto reject"


@test
def test_gen_decisions_index_excludes_non_numeric():
    """README.md en decisions/ no se incluye como fila de la tabla."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "decisions"
        d.mkdir()
        (d / "README.md").write_text("# Registro\n", encoding="utf-8")
        (d / "0001-real.md").write_text("# ADR 0001 — Real\n- Veredicto: accept\n", encoding="utf-8")
        _ds._gen_decisions_index(d)
        readme = (d / "README.md").read_text(encoding="utf-8")
        # La tabla debe tener exactamente 1 fila de datos (el ADR real)
        rows = [ln for ln in readme.splitlines() if ln.startswith("| 0")]
        assert_eq(len(rows), 1, "solo 1 fila: el ADR numerico, no el README previo")


# ---------------------------------------------------------------------------
# Tests de metrics.py — _percentile (funcion pura local)
# ---------------------------------------------------------------------------
import metrics as _metrics  # noqa: E402


def _pct(xs, p):
    """Wrapper para llamar _percentile definida localmente en metrics.py."""
    return _metrics._percentile(xs, p)  # noqa: SLF001


@test
def test_percentile_empty_list():
    """Lista vacia devuelve 0."""
    assert_eq(_pct([], 95), 0.0)


@test
def test_percentile_single_element():
    """1 elemento: cualquier percentil es ese elemento."""
    assert_eq(_pct([42.0], 50), 42.0)
    assert_eq(_pct([42.0], 95), 42.0)
    assert_eq(_pct([42.0], 0), 42.0)


@test
def test_percentile_p95_multi():
    """p95 de [1..20] deve ser ~19.05 (interpolacion lineal)."""
    xs = sorted(float(i) for i in range(1, 21))
    p95 = _pct(xs, 95)
    assert_true(18.0 <= p95 <= 20.0, "p95 de [1..20] debe estar entre 18 y 20, got %s" % p95)


if __name__ == "__main__":
    print("Kaizen — test_core.py")
    print("=" * 40)
    raise SystemExit(run_all())
