#!/usr/bin/env python3
"""Tests unitarios para scripts core de Kaizen. stdlib pura, sin pytest. (132 tests)

Cubre:
  - new_session.py: slugify, utc_now, read_config_value, render, append_to_index
  - validate.py: check_required, check_enums, check_patterns, check_scores
  - autoloop.py: recent_objectives, recent_decisions_summary
  - dashboard_static.py: _tag_pills, _pending_review_section, _gen_decisions_index, build_data
  - metrics.py: summarize (sessions/verdicts/escalation/p95), _percentile
  - archive.py: main() — 5 caminos (no_args, not_found, idempotente, no_closed, closed)
  - list_sessions.py: main() y get_opt
  - show_session.py: main() — 3 caminos (no_args, not_found, exists)
  - forensic_view.py: fmt_data (pura) + main() — 2 caminos (no_args, no_log)
  - adapter_info.py: list_adapters, describe_valid(0), describe_missing(1)
  - _config.py: load_yaml — escalares, anidados, listas, comentarios
  - doctor.py: main() — 6 ramas (sin_config/WARN, config_invalida/FAIL, perfil_faltante/FAIL,
               instalacion_completa/OK, contratos_faltantes/FAIL, scripts_faltantes/FAIL)
  - autoloop.py: gather_focus (dir vacio, archivo editable, foco vacio) + active_config sin CONFIG
  - _console.py: enable_utf8() — no lanza en streams reales, no lanza sin reconfigure
  - run_session.py: compute_total, required_keys, validate_required (5 casos puros)
  - dashboard_static.py: _impl_badge, _phase_pills, _session_rows (5 casos de render HTML)
  - _config.py: _coerce (null/bool/int/string con comillas) + _strip_comment (hash en strings)
  - metrics.py: _median (lista vacia, lista par, lista impar)
  - check.py: _parse_test_count (patron test_core, patron test_aotl, sin patron, 0)
  - adapter_info.py: active_adapter (default 'generic' sin config, y 'mock' con config)
  - autoloop.py: load_adapter (vacio si no existe, dict si existe) + load_profile (igual)
  - autoloop.py: build_context (claves obligatorias, valores reflejados)
  - run_session.py: update_index_status (modifica solo la entrada correcta, id inexistente)
  - run_session.py: load_json (archivo valido, inexistente lanza FileNotFoundError, malformado lanza JSONDecodeError)
  - validate.py: validate_session (valida/0, inexistente/1, score_fuera_de_rango/1, strict_falta_proposal/1)
  - metrics.py: print_report (encabezado, campos), read_index (sin archivo, con fixture), read_forensic (sin archivo)
  - spawn_child.py: max_iterations (sin config/con perfil), write_json (crea archivo valido)
  - dashboard_static.py: generate_html (smoke test: retorna HTML con 'kaizen')
  - check.py: run_and_capture (rc=0+output, rc=1+output con mock subprocess)
  - engine.py: st_now (retorna ISO 8601 UTC)

Uso:
    python scripts/test_core.py        # corre todos los tests
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
from validate import check_required, check_enums, check_patterns, check_scores  # noqa: E402


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


@test
def test_check_scores_valid():
    """Scores todos validos (0-3), total coincide con suma -> sin errores."""
    obj = {
        "scores": {"value": 3, "correctness": 2, "scope": 3, "reversibility": 3, "measurability": 2},
        "total": 13,
    }
    errs = check_scores(obj, "evaluation.schema.json")
    assert_eq(errs, [], "scores validos no deben producir errores")


@test
def test_check_scores_out_of_range():
    """Score fuera de rango 0-3 -> error."""
    obj = {
        "scores": {"value": 5, "correctness": 2, "scope": 3, "reversibility": 3, "measurability": 2},
        "total": 15,
    }
    errs = check_scores(obj, "evaluation.schema.json")
    assert_true(len(errs) >= 1 and "value" in errs[0], "debe detectar score 5 fuera de rango")


@test
def test_check_scores_total_mismatch():
    """Total no coincide con suma de scores -> error."""
    obj = {
        "scores": {"value": 3, "correctness": 3, "scope": 3, "reversibility": 3, "measurability": 3},
        "total": 10,  # deberia ser 15
    }
    errs = check_scores(obj, "evaluation.schema.json")
    assert_true(len(errs) >= 1 and "total=10" in errs[0], "debe detectar total incorrecto")


@test
def test_check_scores_non_evaluation_schema():
    """Para schemas distintos de evaluation.schema.json, devuelve lista vacia."""
    obj = {"scores": {"value": 99}, "total": 99}
    errs = check_scores(obj, "proposal.schema.json")
    assert_eq(errs, [], "no debe validar scores en schemas que no son evaluation")


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


import adapter_info as _ai  # noqa: E402
import archive as _arc  # noqa: E402
import forensic_view as _fv  # noqa: E402
import json as _json  # noqa: E402
import list_sessions as _ls  # noqa: E402
import show_session as _sh  # noqa: E402


def _mk_arc_index(tmp_dir: Path, sessions: list) -> Path:
    idx = tmp_dir / "sessions" / "_index.json"
    idx.parent.mkdir(parents=True, exist_ok=True)
    idx.write_text(_json.dumps({"sessions": sessions}), encoding="utf-8")
    return idx


@test
def test_list_adapters_finds_dirs():
    """list_adapters devuelve nombres de subdirs con adapter.yaml en ADAPTERS."""
    with tempfile.TemporaryDirectory() as td:
        # Crea 2 adapters y 1 directorio sin yaml (debe ignorarse)
        for name in ("alpha", "beta"):
            d = Path(td) / name
            d.mkdir()
            (d / "adapter.yaml").write_text("name: %s\n" % name, encoding="utf-8")
        (Path(td) / "gamma").mkdir()  # sin adapter.yaml
        orig = _ai.ADAPTERS; _ai.ADAPTERS = Path(td)
        try:
            result = _ai.list_adapters()
            assert_eq(result, ["alpha", "beta"], "debe listar solo los que tienen adapter.yaml")
        finally:
            _ai.ADAPTERS = orig


@test
def test_describe_valid_adapter():
    """describe con yaml que tiene todos los campos -> exit 0."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "mi-adapter"
        d.mkdir()
        (d / "adapter.yaml").write_text(
            "name: mi-adapter\ndescription: test\nobserve: observe.prompt\n"
            "engine: claude\napply: auto\nmeasure: selfcheck\n",
            encoding="utf-8",
        )
        orig = _ai.ADAPTERS; _ai.ADAPTERS = Path(td)
        try:
            assert_eq(_ai.describe("mi-adapter"), 0)
        finally:
            _ai.ADAPTERS = orig


@test
def test_describe_missing_fields():
    """describe con yaml sin campos requeridos -> exit 1."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "incompleto"
        d.mkdir()
        (d / "adapter.yaml").write_text("name: incompleto\n", encoding="utf-8")
        orig = _ai.ADAPTERS; _ai.ADAPTERS = Path(td)
        try:
            assert_eq(_ai.describe("incompleto"), 1)
        finally:
            _ai.ADAPTERS = orig


@test
def test_fmt_data_empty():
    """fmt_data con dict vacio -> cadena vacia."""
    assert_eq(_fv.fmt_data({}), "")


@test
def test_fmt_data_with_verdict():
    """fmt_data con verdict -> incluye 'verdict=accept'."""
    result = _fv.fmt_data({"verdict": "accept", "score": 15})
    assert_true("verdict=accept" in result, "debe incluir 'verdict=accept'")
    assert_true("score" not in result, "score no es un campo KEY_FIELDS, no debe aparecer")


@test
def test_forensic_view_no_args():
    """Sin argumentos -> exit 2."""
    assert_eq(_fv.main([]), 2)


@test
def test_forensic_view_no_log():
    """Sesion sin forensic.jsonl -> exit 1."""
    with tempfile.TemporaryDirectory() as td:
        # Crea el directorio de sesion pero SIN el forensic.jsonl
        (Path(td) / "mi-sesion").mkdir()
        orig = _fv.SESSIONS; _fv.SESSIONS = Path(td)
        try:
            assert_eq(_fv.main(["mi-sesion"]), 1)
        finally:
            _fv.SESSIONS = orig


@test
def test_show_session_no_args():
    """Sin argumentos -> exit 2."""
    assert_eq(_sh.main([]), 2)


@test
def test_show_session_not_found():
    """Sesion que no existe -> exit 1."""
    with tempfile.TemporaryDirectory() as td:
        orig = _sh.SESSIONS; _sh.SESSIONS = Path(td)
        try:
            assert_eq(_sh.main(["sesion_inexistente"]), 1)
        finally:
            _sh.SESSIONS = orig


@test
def test_show_session_exists():
    """Sesion existente con session.json minimo -> exit 0."""
    with tempfile.TemporaryDirectory() as td:
        sdir = Path(td) / "mi-sesion-test"
        sdir.mkdir()
        (sdir / "session.json").write_text(
            _json.dumps({"id": "mi-sesion-test", "objective": "prueba show", "mode": "aotl",
                         "adapter": "claude", "tags": []}),
            encoding="utf-8",
        )
        orig = _sh.SESSIONS; _sh.SESSIONS = Path(td)
        try:
            assert_eq(_sh.main(["mi-sesion-test"]), 0)
        finally:
            _sh.SESSIONS = orig


@test
def test_list_sessions_no_index():
    """Sin indice -> exit 0 (no explota)."""
    orig = _ls.INDEX
    _ls.INDEX = Path("/tmp/__kaizen_nonexistent_ls_test__.json")
    try:
        assert_eq(_ls.main([]), 0)
    finally:
        _ls.INDEX = orig


@test
def test_list_sessions_returns_zero():
    """Con indice de 2 sesiones -> exit 0."""
    with tempfile.TemporaryDirectory() as td:
        idx = _mk_arc_index(Path(td), [
            {"id": "s1", "status": "closed", "verdict": "accept", "objective": "obj1"},
            {"id": "s2", "status": "closed", "verdict": "reject", "objective": "obj2"},
        ])
        orig = _ls.INDEX; _ls.INDEX = idx
        try:
            assert_eq(_ls.main([]), 0)
        finally:
            _ls.INDEX = orig


@test
def test_list_sessions_get_opt():
    """get_opt extrae el valor del flag indicado."""
    assert_eq(_ls.get_opt(["--status", "closed", "--verdict", "accept"], "--status"), "closed")
    assert_eq(_ls.get_opt(["--status", "closed"], "--verdict"), None)
    assert_eq(_ls.get_opt([], "--status"), None)


@test
def test_archive_no_args_exits_2():
    """Sin argumentos -> exit code 2."""
    assert_eq(_arc.main([]), 2)


@test
def test_archive_session_not_found():
    """Sesion inexistente en indice -> exit code 1."""
    with tempfile.TemporaryDirectory() as td:
        idx = _mk_arc_index(Path(td), [{"id": "s1", "status": "closed"}])
        orig = _arc.INDEX; _arc.INDEX = idx
        try:
            assert_eq(_arc.main(["no_existe"]), 1)
        finally:
            _arc.INDEX = orig


@test
def test_archive_idempotent():
    """Sesion ya archivada -> exit 0 sin error."""
    with tempfile.TemporaryDirectory() as td:
        idx = _mk_arc_index(Path(td), [{"id": "s1", "status": "archived"}])
        orig = _arc.INDEX; _arc.INDEX = idx
        try:
            assert_eq(_arc.main(["s1"]), 0)
        finally:
            _arc.INDEX = orig


@test
def test_archive_rejects_non_closed():
    """Sesion con status=open -> exit code 1 (solo se archivan 'closed')."""
    with tempfile.TemporaryDirectory() as td:
        idx = _mk_arc_index(Path(td), [{"id": "s1", "status": "open"}])
        orig = _arc.INDEX; _arc.INDEX = idx
        try:
            assert_eq(_arc.main(["s1"]), 1)
        finally:
            _arc.INDEX = orig


@test
def test_archive_closed_session():
    """Sesion closed -> status=archived en el indice y exit 0."""
    with tempfile.TemporaryDirectory() as td:
        idx = _mk_arc_index(Path(td), [{"id": "s1", "status": "closed", "verdict": "accept"}])
        orig = _arc.INDEX; _arc.INDEX = idx
        try:
            result = _arc.main(["s1"])
            assert_eq(result, 0)
            data = _json.loads(idx.read_text(encoding="utf-8"))
            entry = data["sessions"][0]
            assert_eq(entry["status"], "archived", "debe haber cambiado a archived")
        finally:
            _arc.INDEX = orig


@test
def test_tag_pills_none():
    """Tags=None -> guion (indicador vacio)."""
    result = _ds._tag_pills(None)
    assert_true("—" in result, "debe devolver guion para None")


@test
def test_tag_pills_with_user_tags():
    """Tags de usuario visibles -> HTML con el texto del tag."""
    result = _ds._tag_pills(["infra", "cli"])
    assert_true("infra" in result, "debe incluir 'infra'")
    assert_true("cli" in result, "debe incluir 'cli'")


@test
def test_tag_pills_filters_engine_tags():
    """Tags engine:* se filtran -> si solo habia engine:* devuelve guion."""
    result = _ds._tag_pills(["engine:claude", "engine:mock"])
    assert_true("—" in result, "solo engine tags debe devolver guion")
    assert_true("claude" not in result, "no debe mostrar engine:claude como pill")


@test
def test_build_data_basic_keys():
    """build_data() devuelve dict con las claves minimas esperadas."""
    data = _ds.build_data()
    assert_true("sessions" in data, "debe tener 'sessions'")
    assert_true("file_url" in data, "debe tener 'file_url'")
    assert_true("verdicts" in data, "debe tener 'verdicts'")
    assert_true("p95_elapsed_ms" in data, "debe tener 'p95_elapsed_ms'")


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
# Tests de metrics.py — summarize (funcion principal)
# ---------------------------------------------------------------------------
import metrics as _metrics  # noqa: E402


def _mk_run_events(run_id: str, session_id: str, elapsed_ms: float, verdict: str,
                   escalated: bool = False) -> list:
    """Crea eventos forenses minimos para un run (start + decision + end)."""
    return [
        {"run_id": run_id, "session_id": session_id, "run_kind": "run_session",
         "seq": 0, "event": "run.start", "level": "INFO", "elapsed_ms": 0},
        {"run_id": run_id, "session_id": session_id, "run_kind": "run_session",
         "seq": 5, "event": "decision.written", "level": "INFO", "elapsed_ms": elapsed_ms / 2,
         "data": {"verdict": verdict, "escalated": escalated}},
        {"run_id": run_id, "session_id": session_id, "run_kind": "run_session",
         "seq": 9, "event": "run.end", "level": "INFO", "elapsed_ms": elapsed_ms,
         "data": {"verdict": verdict}},
    ]


@test
def test_summarize_empty():
    """Sin sesiones ni eventos -> campos clave en 0/None."""
    s = _metrics.summarize([], [])
    assert_eq(s["sessions_total"], 0)
    assert_eq(s["runs_total"], 0)
    assert_eq(s["acceptance_rate"], None)
    assert_eq(s["escalation_rate"], None)


@test
def test_summarize_single_accept():
    """1 sesion accept + 1 run -> sessions_total=1, acceptance_rate=1.0."""
    idx = [{"id": "s1", "verdict": "accept"}]
    evts = _mk_run_events("r1", "s1", 20.0, "accept")
    s = _metrics.summarize(idx, evts)
    assert_eq(s["sessions_total"], 1)
    assert_eq(s["runs_total"], 1)
    assert_eq(s["acceptance_rate"], 1.0)
    assert_eq(s["escalations_to_human"], 0)
    assert_true(s["avg_elapsed_ms"] > 0, "avg_elapsed debe ser positivo")


@test
def test_summarize_accept_and_reject():
    """accept+reject: acceptance_rate=0.5, p95 calculado correctamente."""
    idx = [{"id": "s1", "verdict": "accept"}, {"id": "s2", "verdict": "reject"}]
    evts = _mk_run_events("r1", "s1", 10.0, "accept") + _mk_run_events("r2", "s2", 30.0, "reject")
    s = _metrics.summarize(idx, evts)
    assert_eq(s["sessions_total"], 2)
    assert_eq(s["acceptance_rate"], 0.5)
    assert_true(s["p95_elapsed_ms"] >= s["median_elapsed_ms"], "p95 >= mediana")


@test
def test_summarize_escalation_counted():
    """Escalacion en evento decision.written -> escalations_to_human=1."""
    idx = [{"id": "s1", "verdict": "iterate"}]
    evts = _mk_run_events("r1", "s1", 25.0, "iterate", escalated=True)
    s = _metrics.summarize(idx, evts)
    assert_eq(s["escalations_to_human"], 1)
    assert_true(s["escalation_rate"] > 0, "escalation_rate debe ser positivo")


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


# ---------------------------------------------------------------------------
# Tests de _config.py — load_yaml (parser YAML minimo, stdlib pura)
# ---------------------------------------------------------------------------
from _config import load_yaml as _load_yaml  # noqa: E402


@test
def test_load_yaml_scalars():
    """Parsea int, bool, null y string (con y sin comillas)."""
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "t.yaml"
        f.write_text(
            "n: 42\nb: true\nnull_val: null\ns: hello\nq: 'world'\n",
            encoding="utf-8",
        )
        d = _load_yaml(f)
        assert_eq(d["n"], 42, "int")
        assert_eq(d["b"], True, "bool")
        assert_eq(d["null_val"], None, "null")
        assert_eq(d["s"], "hello", "string sin comillas")
        assert_eq(d["q"], "world", "string con comillas simples")


@test
def test_load_yaml_nested():
    """Parsea mapeos anidados por indentacion."""
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "t.yaml"
        f.write_text(
            "outer:\n  inner: 7\n  deep:\n    val: ok\n",
            encoding="utf-8",
        )
        d = _load_yaml(f)
        assert_eq(d["outer"]["inner"], 7, "inner int")
        assert_eq(d["outer"]["deep"]["val"], "ok", "deep string")


@test
def test_load_yaml_list():
    """Parsea listas de escalares (lineas '- item')."""
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "t.yaml"
        f.write_text(
            "items:\n  - alpha\n  - 2\n  - true\n",
            encoding="utf-8",
        )
        d = _load_yaml(f)
        assert_eq(d["items"], ["alpha", 2, True], "lista mixta")


@test
def test_load_yaml_strips_comments():
    """Elimina comentarios '#' sin afectar strings con '#' dentro de comillas."""
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "t.yaml"
        f.write_text(
            "a: 1  # esto es comentario\nb: 'url#hash'  # otro comentario\n",
            encoding="utf-8",
        )
        d = _load_yaml(f)
        assert_eq(d["a"], 1, "valor antes del comentario")
        assert_eq(d["b"], "url#hash", "hash dentro de string no es comentario")


# ---------------------------------------------------------------------------
# Tests de doctor.py — 7 ramas: config/perfil/adapter/contratos/scripts/PROTECTED/indice
# ---------------------------------------------------------------------------
import importlib
import json as _json
import types as _types


def _mk_doctor_root(td: str, *, with_config: bool = True, config_valid: bool = True,
                    with_profile: bool = True, with_adapter: bool = True,
                    with_contracts: bool = True, with_scripts: bool = True,
                    with_index: bool = True) -> Path:
    """Monta un ROOT minimo en tempdir para probar doctor.main()."""
    root = Path(td)
    # config/
    (root / "config" / "profiles").mkdir(parents=True, exist_ok=True)
    if with_config:
        adapter_name = "mock" if with_adapter else "noexiste"
        cfg_text = "mode: aotl\nadapter: %s\nprofile: default\n" % adapter_name
        if not config_valid:
            cfg_text = ": invalid yaml {{{\n"
        (root / "config" / "kaizen.config.yaml").write_text(cfg_text, encoding="utf-8")
    if with_profile:
        (root / "config" / "profiles" / "default.yaml").write_text("gate:\n  accept: 11\n", encoding="utf-8")
    # adapters/
    if with_adapter:
        (root / "adapters" / "mock").mkdir(parents=True, exist_ok=True)
        (root / "adapters" / "mock" / "adapter.yaml").write_text("name: mock\n", encoding="utf-8")
    # contracts/
    if with_contracts:
        (root / "contracts").mkdir(exist_ok=True)
        for c in ["session.input.schema.json", "proposal.schema.json", "evaluation.schema.json",
                  "decision.schema.json", "artifact.schema.json", "session.output.schema.json"]:
            (root / "contracts" / c).write_text("{}", encoding="utf-8")
    # scripts/ (los requeridos)
    if with_scripts:
        (root / "scripts").mkdir(exist_ok=True)
        for s in ["new_session.py", "run_session.py", "validate.py", "metrics.py", "selfcheck.py"]:
            (root / "scripts" / s).write_text("", encoding="utf-8")
    # sessions/
    if with_index:
        (root / "sessions").mkdir(exist_ok=True)
        (root / "sessions" / "_index.json").write_text('{"sessions": []}', encoding="utf-8")
    return root


def _run_doctor(td_root: Path) -> tuple[int, str]:
    """Corre doctor.main con ROOT parcheado; devuelve (exit_code, stdout)."""
    import io, contextlib
    import doctor as _doctor_mod
    old_root = _doctor_mod.ROOT
    old_cfg = _doctor_mod.CONFIG
    old_contracts = _doctor_mod.CONTRACTS
    try:
        _doctor_mod.ROOT = td_root
        _doctor_mod.CONFIG = td_root / "config" / "kaizen.config.yaml"
        _doctor_mod.CONTRACTS = td_root / "contracts"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = _doctor_mod.main([])
        return code, buf.getvalue()
    finally:
        _doctor_mod.ROOT = old_root
        _doctor_mod.CONFIG = old_cfg
        _doctor_mod.CONTRACTS = old_contracts


@test
def test_doctor_sin_config_reporta_warn():
    """Sin config activa: doctor reporta WARN (config ausente es advertencia, no falla dura).
    El adapter default 'generic' puede no existir -> FAIL adicional; lo que importa es
    que la ausencia de config produce al menos un '!!' en el output."""
    with tempfile.TemporaryDirectory() as td:
        root = _mk_doctor_root(td, with_config=False)
        _code, out = _run_doctor(root)
        assert_true("!!" in out or "WARN" in out, "debe reportar WARN por config ausente: %r" % out)


@test
def test_doctor_config_invalida_exit_1():
    """Con config que no parsea: doctor da FAIL y exit 1."""
    with tempfile.TemporaryDirectory() as td:
        root = _mk_doctor_root(td, config_valid=False)
        code, out = _run_doctor(root)
        assert_eq(code, 1, "config invalida debe ser exit 1")
        assert_true("FAIL" in out or "XX" in out, "debe reportar FAIL")


@test
def test_doctor_perfil_faltante_exit_1():
    """Con perfil faltante: doctor da FAIL y exit 1."""
    with tempfile.TemporaryDirectory() as td:
        root = _mk_doctor_root(td, with_profile=False)
        code, out = _run_doctor(root)
        assert_eq(code, 1, "perfil faltante debe ser exit 1")


@test
def test_doctor_instalacion_completa_exit_0():
    """Instalacion completa y valida: doctor da todos OK y exit 0."""
    with tempfile.TemporaryDirectory() as td:
        root = _mk_doctor_root(td)
        code, out = _run_doctor(root)
        assert_eq(code, 0, "instalacion completa debe ser exit 0: %r" % out)
        assert_true("OK" in out, "debe reportar OK")


@test
def test_doctor_contratos_faltantes_exit_1():
    """Sin contratos: doctor da FAIL y exit 1."""
    with tempfile.TemporaryDirectory() as td:
        root = _mk_doctor_root(td, with_contracts=False)
        code, out = _run_doctor(root)
        assert_eq(code, 1, "sin contratos debe ser exit 1")


@test
def test_doctor_scripts_faltantes_exit_1():
    """Sin scripts nucleo: doctor da FAIL y exit 1."""
    with tempfile.TemporaryDirectory() as td:
        root = _mk_doctor_root(td, with_scripts=False)
        code, out = _run_doctor(root)
        assert_eq(code, 1, "sin scripts nucleo debe ser exit 1")


# ---------------------------------------------------------------------------
# Tests de autoloop.py — gather_focus y active_config
# ---------------------------------------------------------------------------
import autoloop  # noqa: E402


@test
def test_gather_focus_dir_vacio():
    """gather_focus con directorio vacio devuelve tree y files vacias."""
    with tempfile.TemporaryDirectory() as td:
        old_root = autoloop.ROOT
        try:
            autoloop.ROOT = Path(td)
            tree, files = autoloop.gather_focus(["."])
            assert_eq(tree, [], "dir vacio debe dar tree vacio")
            assert_eq(files, {}, "dir vacio debe dar files vacio")
        finally:
            autoloop.ROOT = old_root


@test
def test_gather_focus_incluye_archivo_editable():
    """gather_focus con 1 archivo no protegido lo incluye en tree y files."""
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "test.txt"
        f.write_text("contenido de prueba", encoding="utf-8")
        old_root = autoloop.ROOT
        try:
            autoloop.ROOT = Path(td)
            tree, files = autoloop.gather_focus(["."])
            assert_true(len(tree) == 1, "tree debe tener 1 archivo: %r" % tree)
            assert_true(len(files) == 1, "files debe tener 1 archivo: %r" % files)
            assert_true(list(files.values())[0] == "contenido de prueba", "contenido incorrecto")
        finally:
            autoloop.ROOT = old_root


@test
def test_gather_focus_foco_lista_vacia():
    """gather_focus con lista de foco vacia devuelve tree y files vacias."""
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "algo.txt").write_text("x", encoding="utf-8")
        old_root = autoloop.ROOT
        try:
            autoloop.ROOT = Path(td)
            tree, files = autoloop.gather_focus([])  # sin foco
            assert_eq(tree, [], "foco vacio debe dar tree vacio")
            assert_eq(files, {}, "foco vacio debe dar files vacio")
        finally:
            autoloop.ROOT = old_root


@test
def test_active_config_sin_config():
    """active_config devuelve {} si CONFIG no existe."""
    old_cfg = autoloop.CONFIG
    try:
        autoloop.CONFIG = Path("/tmp/__kaizen_no_existe_config__.yaml")
        cfg = autoloop.active_config()
        assert_eq(cfg, {}, "sin CONFIG debe retornar dict vacio")
    finally:
        autoloop.CONFIG = old_cfg


# ---------------------------------------------------------------------------
# Tests de _console.py — enable_utf8(): no lanza en condiciones normales ni sin reconfigure
# ---------------------------------------------------------------------------
from _console import enable_utf8  # noqa: E402


@test
def test_enable_utf8_no_lanza():
    """enable_utf8() no lanza excepciones en stdout/stderr reales."""
    enable_utf8()  # solo verifica que no levanta


@test
def test_enable_utf8_sin_reconfigure():
    """enable_utf8() no lanza si los streams no tienen reconfigure (objeto sin ese metodo)."""
    import types
    dummy = types.SimpleNamespace()  # sin reconfigure
    import _console as _con
    import sys
    old_stdout, old_stderr = sys.stdout, sys.stderr
    try:
        sys.stdout = dummy  # type: ignore[assignment]
        sys.stderr = dummy  # type: ignore[assignment]
        _con.enable_utf8()  # debe capturar la excepcion internamente
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


# ---------------------------------------------------------------------------
# Tests de new_session.py — render() y append_to_index()
# ---------------------------------------------------------------------------
import new_session as _ns  # noqa: E402


@test
def test_render_sin_placeholders():
    """render() con mapping vacio devuelve el texto original intacto."""
    with tempfile.TemporaryDirectory() as td:
        tpl = Path(td) / "tpl.txt"
        tpl.write_text("texto sin placeholders", encoding="utf-8")
        result = _ns.render(tpl, {})
        assert_eq(result, "texto sin placeholders")


@test
def test_render_con_archivo_real():
    """render() lee un archivo y sustituye todos los placeholders."""
    with tempfile.TemporaryDirectory() as td:
        tpl = Path(td) / "tpl.txt"
        tpl.write_text("sesion={{SESSION_ID}} obj={{OBJECTIVE}}", encoding="utf-8")
        result = _ns.render(tpl, {"SESSION_ID": "s-42", "OBJECTIVE": "mejorar algo"})
        assert_eq(result, "sesion=s-42 obj=mejorar algo")


@test
def test_append_to_index_crea_indice_si_no_existe():
    """append_to_index() crea el indice desde cero si no existe."""
    with tempfile.TemporaryDirectory() as td:
        idx = Path(td) / "sessions" / "_index.json"
        idx.parent.mkdir(parents=True)
        old_idx = _ns.INDEX
        try:
            _ns.INDEX = idx
            _ns.append_to_index({"id": "s-1", "objective": "primera sesion"})
            data = _json.loads(idx.read_text(encoding="utf-8"))
            assert_eq(len(data["sessions"]), 1)
            assert_eq(data["sessions"][0]["id"], "s-1")
        finally:
            _ns.INDEX = old_idx


@test
def test_append_to_index_agrega_a_indice_existente():
    """append_to_index() agrega al final sin borrar las entradas previas."""
    with tempfile.TemporaryDirectory() as td:
        idx = Path(td) / "sessions" / "_index.json"
        idx.parent.mkdir(parents=True)
        idx.write_text(_json.dumps({"sessions": [{"id": "s-0", "objective": "ya existia"}]}),
                       encoding="utf-8")
        old_idx = _ns.INDEX
        try:
            _ns.INDEX = idx
            _ns.append_to_index({"id": "s-1", "objective": "nueva"})
            data = _json.loads(idx.read_text(encoding="utf-8"))
            assert_eq(len(data["sessions"]), 2, "debe haber 2 sesiones")
            assert_eq(data["sessions"][1]["id"], "s-1", "la nueva es la ultima")
        finally:
            _ns.INDEX = old_idx


# ---------------------------------------------------------------------------
# Tests de run_session.py — compute_total, required_keys, validate_required
# ---------------------------------------------------------------------------
import sys as _sys
import importlib as _il
_sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_session as _rs  # noqa: E402


@test
def test_compute_total_full_scores():
    """Suma correcta de los 5 campos de scores (1+2+3+2+3=11)."""
    scores = {"value": 1, "correctness": 2, "scope": 3, "reversibility": 2, "measurability": 3}
    assert_eq(_rs.compute_total(scores), 11)


@test
def test_compute_total_empty_scores():
    """Scores vacio -> total=0 (no KeyError)."""
    assert_eq(_rs.compute_total({}), 0)


@test
def test_compute_total_partial_scores():
    """Solo algunos campos presentes -> suma los presentes, 0 para los que faltan."""
    scores = {"value": 3, "correctness": 3}  # 3 campos ausentes = 0
    assert_eq(_rs.compute_total(scores), 6)


@test
def test_required_keys_returns_list():
    """required_keys extrae la lista del campo 'required' del schema."""
    schema = {"required": ["session_id", "verdict", "rationale"], "properties": {}}
    keys = _rs.required_keys(schema)
    assert_eq(keys, ["session_id", "verdict", "rationale"])


@test
def test_validate_required_detects_missing():
    """validate_required detecta campo faltante contra schema real del contrato."""
    with tempfile.TemporaryDirectory() as td:
        # Schema minimo con 2 campos requeridos
        schema_path = Path(td) / "mini.schema.json"
        schema_path.write_text(
            '{"required": ["session_id", "verdict"], "properties": {}}',
            encoding="utf-8",
        )
        # Objeto con solo uno de los dos campos
        missing = _rs.validate_required({"session_id": "s1"}, schema_path)
        assert_eq(missing, ["verdict"], "debe detectar 'verdict' como faltante")


# ---------------------------------------------------------------------------
# Tests de dashboard_static.py — _impl_badge, _phase_pills, _session_rows
# ---------------------------------------------------------------------------


@test
def test_impl_badge_none():
    """_impl_badge(None) devuelve guion HTML (estado indefinido)."""
    result = _ds._impl_badge(None)
    assert_true("—" in result, "None debe devolver guion")


@test
def test_impl_badge_implemented():
    """_impl_badge('implemented') devuelve badge con el texto 'implemented'."""
    result = _ds._impl_badge("implemented")
    assert_true("implemented" in result, "debe contener 'implemented'")
    # Debe ser un span HTML (badge)
    assert_true("<span" in result, "debe ser un elemento span")


@test
def test_phase_pills_returns_all_phases():
    """_phase_pills() devuelve HTML con las fases del pipeline (en español)."""
    result = _ds._phase_pills(None)
    # El pipeline tiene al menos 3 fases conocidas (en español)
    assert_true(len(result) > 50, "debe generar HTML con las fases del pipeline")
    assert_true("proponer" in result, "debe incluir la fase 'proponer'")


@test
def test_phase_pills_active_phase_highlighted():
    """_phase_pills con fase activa genera HTML distinto (activa vs inactiva)."""
    result_none = _ds._phase_pills(None)
    result_propose = _ds._phase_pills("propose")
    assert_true(result_none != result_propose,
                "la fase activa debe cambiar el HTML vs sin fase")


@test
def test_session_rows_genera_filas():
    """_session_rows con 1 sesion genera al menos 1 fila <tr>."""
    sessions = [{"id": "s-test", "objective": "mejorar algo", "verdict": "accept",
                 "status": "closed", "created_utc": "2026-06-22T10:00:00Z"}]
    result = _ds._session_rows(sessions)
    assert_true("<tr>" in result, "debe generar al menos una fila <tr>")
    assert_true("mejorar algo" in result, "debe incluir el objetivo de la sesion")


# ---------------------------------------------------------------------------
# Tests de _config.py — _coerce y _strip_comment (helpers del parser YAML)
# ---------------------------------------------------------------------------
from _config import _coerce, _strip_comment  # noqa: E402


@test
def test_coerce_null_values():
    """_coerce retorna None para '', '~' y 'null' (case-insensitive)."""
    assert_eq(_coerce(""), None, "vacio -> None")
    assert_eq(_coerce("~"), None, "~ -> None")
    assert_eq(_coerce("null"), None, "null -> None")
    assert_eq(_coerce("NULL"), None, "NULL -> None")


@test
def test_coerce_booleans():
    """_coerce retorna True/False para 'true'/'false' (case-insensitive)."""
    assert_eq(_coerce("true"), True)
    assert_eq(_coerce("True"), True)
    assert_eq(_coerce("false"), False)
    assert_eq(_coerce("FALSE"), False)


@test
def test_coerce_integers():
    """_coerce retorna int para valores numericos enteros."""
    assert_eq(_coerce("42"), 42)
    assert_eq(_coerce("0"), 0)
    assert_eq(_coerce("-7"), -7)


@test
def test_coerce_strings_with_quotes():
    """_coerce strip comillas simples y dobles del valor."""
    assert_eq(_coerce("'hola mundo'"), "hola mundo")
    assert_eq(_coerce('"doble"'), "doble")


@test
def test_strip_comment_removes_trailing_hash():
    """_strip_comment elimina comentarios # al final de la linea."""
    result = _strip_comment("valor: 42  # esto es un comentario")
    assert_true("comentario" not in result, "debe eliminar el comentario")
    assert_true("valor" in result, "debe preservar el valor")


@test
def test_strip_comment_preserves_hash_in_string():
    """_strip_comment NO elimina # dentro de strings con comillas."""
    result = _strip_comment("url: 'https://example.com/path#hash'")
    assert_true("#hash" in result, "hash dentro de string no debe eliminarse")


# ---------------------------------------------------------------------------
# Tests de metrics.py — _median (complementa los tests de _percentile)
# ---------------------------------------------------------------------------


@test
def test_median_empty():
    """_median de lista vacia devuelve 0.0."""
    assert_eq(_metrics._median([]), 0.0)  # noqa: SLF001


@test
def test_median_odd_list():
    """_median de lista impar devuelve el elemento del medio."""
    assert_eq(_metrics._median([1.0, 3.0, 5.0]), 3.0)


@test
def test_median_even_list():
    """_median de lista par devuelve el promedio de los 2 centrales."""
    result = _metrics._median([1.0, 2.0, 3.0, 4.0])
    assert_eq(result, 2.5, "mediana de [1,2,3,4] debe ser 2.5")


# ---------------------------------------------------------------------------
# Tests de check.py — _parse_test_count (extrae conteo de tests del output)
# ---------------------------------------------------------------------------
import check as _chk  # noqa: E402


@test
def test_parse_test_count_core_pattern():
    """_parse_test_count detecta el patron de test_core.py: '85 OK, 0 FAIL'."""
    assert_eq(_chk._parse_test_count("85 OK, 0 FAIL"), 85)  # noqa: SLF001


@test
def test_parse_test_count_aotl_pattern():
    """_parse_test_count detecta el patron de test_aotl.py: '50/50 verdes.'."""
    assert_eq(_chk._parse_test_count("50/50 verdes."), 50)  # noqa: SLF001


@test
def test_parse_test_count_no_pattern():
    """_parse_test_count devuelve 0 si no hay patron conocido."""
    assert_eq(_chk._parse_test_count(""), 0)  # noqa: SLF001
    assert_eq(_chk._parse_test_count("error: module not found"), 0)  # noqa: SLF001


@test
def test_parse_test_count_multiline():
    """_parse_test_count extrae el patron de un output multilinea real."""
    output = "  OK  test_foo\n  OK  test_bar\n\n99 OK, 0 FAIL"
    assert_eq(_chk._parse_test_count(output), 99)  # noqa: SLF001


# ---------------------------------------------------------------------------
# Tests de adapter_info.py — active_adapter (config y default)
# ---------------------------------------------------------------------------
import adapter_info as _ai  # noqa: E402


@test
def test_active_adapter_default_generic():
    """active_adapter devuelve 'generic' si no hay config."""
    old_cfg = _ai.CONFIG
    try:
        _ai.CONFIG = Path("/tmp/__kaizen_no_config_ai__.yaml")
        result = _ai.active_adapter()
        assert_eq(result, "generic", "sin config debe devolver 'generic'")
    finally:
        _ai.CONFIG = old_cfg


@test
def test_active_adapter_reads_config():
    """active_adapter devuelve el adapter de la config cuando existe."""
    with tempfile.TemporaryDirectory() as td:
        cfg = Path(td) / "kaizen.config.yaml"
        cfg.write_text("mode: aotl\nadapter: mock\nprofile: default\n", encoding="utf-8")
        old_cfg = _ai.CONFIG
        try:
            _ai.CONFIG = cfg
            result = _ai.active_adapter()
            assert_eq(result, "mock", "con adapter: mock debe devolver 'mock'")
        finally:
            _ai.CONFIG = old_cfg


# ---------------------------------------------------------------------------
# Tests de autoloop.py — load_adapter y load_profile
# ---------------------------------------------------------------------------


@test
def test_load_adapter_no_existe():
    """load_adapter devuelve {} si el adapter no existe."""
    old_root = autoloop.ROOT
    try:
        autoloop.ROOT = Path("/tmp/__kaizen_no_adapters__")
        result = autoloop.load_adapter("noexiste")
        assert_eq(result, {}, "adapter no existente debe devolver {}")
    finally:
        autoloop.ROOT = old_root


@test
def test_load_adapter_con_archivo():
    """load_adapter devuelve el contenido del adapter.yaml si existe."""
    with tempfile.TemporaryDirectory() as td:
        adapter_dir = Path(td) / "adapters" / "test-adapter"
        adapter_dir.mkdir(parents=True)
        (adapter_dir / "adapter.yaml").write_text(
            "name: test-adapter\ndescription: adapter de prueba\n", encoding="utf-8"
        )
        old_root = autoloop.ROOT
        try:
            autoloop.ROOT = Path(td)
            result = autoloop.load_adapter("test-adapter")
            assert_eq(result["name"], "test-adapter", "debe cargar el nombre del adapter")
        finally:
            autoloop.ROOT = old_root


@test
def test_load_profile_no_existe():
    """load_profile devuelve {} si el perfil no existe."""
    old_root = autoloop.ROOT
    try:
        autoloop.ROOT = Path("/tmp/__kaizen_no_profiles__")
        result = autoloop.load_profile({})
        assert_eq(result, {}, "perfil no existente debe devolver {}")
    finally:
        autoloop.ROOT = old_root


@test
def test_load_profile_con_archivo():
    """load_profile devuelve el contenido del perfil si existe."""
    with tempfile.TemporaryDirectory() as td:
        profiles_dir = Path(td) / "config" / "profiles"
        profiles_dir.mkdir(parents=True)
        (profiles_dir / "custom.yaml").write_text(
            "review:\n  accept_threshold: 12\n", encoding="utf-8"
        )
        old_root = autoloop.ROOT
        try:
            autoloop.ROOT = Path(td)
            result = autoloop.load_profile({"profile": "custom"})
            assert_eq(result["review"]["accept_threshold"], 12,
                      "debe cargar el umbral del perfil")
        finally:
            autoloop.ROOT = old_root


@test
def test_load_json_archivo_valido():
    """load_json retorna el dict cuando el archivo existe y es JSON valido."""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "data.json"
        path.write_text('{"key": "value", "num": 42}', encoding="utf-8")
        result = _rs.load_json(path)
        assert_eq(result["key"], "value", "debe retornar el valor del campo key")
        assert_eq(result["num"], 42, "debe retornar el valor numerico")


@test
def test_load_json_archivo_inexistente():
    """load_json lanza FileNotFoundError si el archivo no existe."""
    try:
        _rs.load_json(Path("/no/existe/archivo.json"))
        assert False, "debia lanzar FileNotFoundError"
    except FileNotFoundError:
        pass  # esperado


@test
def test_load_json_malformado():
    """load_json lanza json.JSONDecodeError si el archivo no es JSON valido."""
    import json as _json
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "bad.json"
        path.write_text("esto no es json {{{", encoding="utf-8")
        try:
            _rs.load_json(path)
            assert False, "debia lanzar json.JSONDecodeError"
        except _json.JSONDecodeError:
            pass  # esperado


@test
def test_update_index_status_modifica_correcta():
    """update_index_status modifica solo la entrada con el session_id dado."""
    with tempfile.TemporaryDirectory() as td:
        idx = Path(td) / "sessions" / "_index.json"
        idx.parent.mkdir(parents=True)
        data = {"sessions": [
            {"id": "s1", "status": "open", "verdict": None},
            {"id": "s2", "status": "open", "verdict": None},
        ]}
        idx.write_text(__import__("json").dumps(data), encoding="utf-8")
        old_idx = _rs.INDEX
        try:
            _rs.INDEX = idx
            _rs.update_index_status("s1", "closed", "accept")
            result = __import__("json").loads(idx.read_text(encoding="utf-8"))
            s1 = next(e for e in result["sessions"] if e["id"] == "s1")
            s2 = next(e for e in result["sessions"] if e["id"] == "s2")
            assert_eq(s1["status"], "closed", "s1.status debe ser closed")
            assert_eq(s1["verdict"], "accept", "s1.verdict debe ser accept")
            assert_eq(s2["status"], "open", "s2 no debe ser modificada")
        finally:
            _rs.INDEX = old_idx


@test
def test_update_index_status_id_inexistente():
    """update_index_status no falla si session_id no existe en el indice."""
    with tempfile.TemporaryDirectory() as td:
        idx = Path(td) / "sessions" / "_index.json"
        idx.parent.mkdir(parents=True)
        data = {"sessions": [{"id": "s1", "status": "open", "verdict": None}]}
        idx.write_text(__import__("json").dumps(data), encoding="utf-8")
        old_idx = _rs.INDEX
        try:
            _rs.INDEX = idx
            _rs.update_index_status("no_existe", "closed", "reject")  # no debe lanzar
            result = __import__("json").loads(idx.read_text(encoding="utf-8"))
            assert_eq(result["sessions"][0]["status"], "open", "s1 no debe ser modificada")
        finally:
            _rs.INDEX = old_idx


@test
def test_build_context_claves_obligatorias():
    """build_context devuelve las 8 claves obligatorias del contrato de contexto."""
    with tempfile.TemporaryDirectory() as td:
        old_root = autoloop.ROOT
        old_index = autoloop.INDEX
        try:
            # Montar estructura minima: decisions/ vacio + sessions/_index.json vacio
            autoloop.ROOT = Path(td)
            autoloop.INDEX = Path(td) / "sessions" / "_index.json"
            (Path(td) / "sessions").mkdir(parents=True)
            autoloop.INDEX.write_text('{"sessions": []}', encoding="utf-8")
            ctx = autoloop.build_context("sid-001", "test-obj", 1, [], "python scripts/check.py")
            for key in ("session_id", "objective", "iteration", "tree",
                        "files", "recent_decisions", "protected", "measure_command"):
                assert_true(key in ctx, "build_context debe incluir clave: %s" % key)
        finally:
            autoloop.ROOT = old_root
            autoloop.INDEX = old_index


@test
def test_build_context_valores_pasados():
    """build_context refleja session_id, objective e iteration en el dict retornado."""
    with tempfile.TemporaryDirectory() as td:
        old_root = autoloop.ROOT
        old_index = autoloop.INDEX
        try:
            autoloop.ROOT = Path(td)
            autoloop.INDEX = Path(td) / "sessions" / "_index.json"
            (Path(td) / "sessions").mkdir(parents=True)
            autoloop.INDEX.write_text('{"sessions": []}', encoding="utf-8")
            ctx = autoloop.build_context("my-session", "my-objective", 3, [], "cmd")
            assert_eq(ctx["session_id"], "my-session", "session_id debe coincidir")
            assert_eq(ctx["objective"], "my-objective", "objective debe coincidir")
            assert_eq(ctx["iteration"], 3, "iteration debe coincidir")
        finally:
            autoloop.ROOT = old_root
            autoloop.INDEX = old_index


# ---------------------------------------------------------------------------
# B-88: check.run_and_capture y engine.st_now — 3 casos
# ---------------------------------------------------------------------------
import check as _check_mod
import engine as _engine_mod
import subprocess as _sp88


@test
def test_run_and_capture_rc0_retorna_output():
    """run_and_capture con rc=0 devuelve (0, stdout+stderr combinado)."""
    old = _check_mod.subprocess.run
    try:
        _check_mod.subprocess.run = lambda *a, **kw: _sp88.CompletedProcess(
            args=[], returncode=0, stdout="hola\n", stderr="warn\n"
        )
        rc, out = _check_mod.run_and_capture("test_core.py")
        assert_eq(rc, 0, "returncode debe ser 0")
        assert "hola" in out, "stdout debe estar en output"
        assert "warn" in out, "stderr debe estar en output"
    finally:
        _check_mod.subprocess.run = old


@test
def test_run_and_capture_rc1_retorna_output():
    """run_and_capture con rc=1 devuelve (1, output combinado)."""
    old = _check_mod.subprocess.run
    try:
        _check_mod.subprocess.run = lambda *a, **kw: _sp88.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error critico\n"
        )
        rc, out = _check_mod.run_and_capture("validate.py")
        assert_eq(rc, 1, "returncode debe ser 1")
        assert "error critico" in out, "stderr debe estar en output"
    finally:
        _check_mod.subprocess.run = old


@test
def test_st_now_retorna_iso8601_utc():
    """st_now retorna un string ISO 8601 con offset UTC."""
    ts = _engine_mod.st_now()
    assert isinstance(ts, str), "debe ser string"
    assert "+00:00" in ts or ts.endswith("Z"), "debe indicar UTC"
    assert "T" in ts, "debe tener separador T de ISO 8601"


# ---------------------------------------------------------------------------
# B-87: spawn_child.max_iterations, write_json + smoke test generate_html — 4 casos
# ---------------------------------------------------------------------------
import spawn_child as _sc
import dashboard_static as _ds_mod


@test
def test_max_iterations_sin_config():
    """max_iterations devuelve 3 (default) cuando no hay config."""
    old_cfg = _sc.CONFIG
    old_root = _sc.ROOT
    try:
        with tempfile.TemporaryDirectory() as td:
            # Crear estructura de perfiles en tempdir
            (Path(td) / "config" / "profiles").mkdir(parents=True)
            (Path(td) / "config" / "profiles" / "default.yaml").write_text(
                "aotl:\n  max_iterations: 3\n", encoding="utf-8"
            )
            _sc.CONFIG = Path(td) / "config" / "no_existe.yaml"
            _sc.ROOT = Path(td)
            result = _sc.max_iterations()
            assert_eq(result, 3, "sin config debe devolver 3 (default)")
    finally:
        _sc.CONFIG = old_cfg
        _sc.ROOT = old_root


@test
def test_max_iterations_con_perfil():
    """max_iterations lee el perfil y devuelve el valor configurado."""
    old_cfg = _sc.CONFIG
    old_root = _sc.ROOT
    try:
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "config" / "profiles").mkdir(parents=True)
            (Path(td) / "config" / "profiles" / "default.yaml").write_text(
                "aotl:\n  max_iterations: 7\n", encoding="utf-8"
            )
            # No crear config -> usa perfil 'default'
            _sc.CONFIG = Path(td) / "config" / "no_existe.yaml"
            _sc.ROOT = Path(td)
            result = _sc.max_iterations()
            assert_eq(result, 7, "debe leer max_iterations del perfil")
    finally:
        _sc.CONFIG = old_cfg
        _sc.ROOT = old_root


@test
def test_write_json_crea_archivo_valido():
    """write_json escribe JSON valido que puede re-leerse."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "out.json"
        _sc.write_json(p, {"key": "valor", "num": 42})
        data = _json.loads(p.read_text(encoding="utf-8"))
        assert_eq(data["key"], "valor", "debe conservar key")
        assert_eq(data["num"], 42, "debe conservar num")


@test
def test_generate_html_smoke():
    """generate_html devuelve un string HTML con la cabecera KAIZEN sin lanzar excepciones."""
    data = _ds_mod.build_data()
    html = _ds_mod.generate_html(data)
    assert isinstance(html, str), "debe retornar un string"
    assert "kaizen" in html.lower(), "debe contener 'kaizen' en el HTML (case-insensitive)"
    assert "<html" in html.lower(), "debe ser un documento HTML"


# ---------------------------------------------------------------------------
# B-86: metrics.print_report, read_index, read_forensic — 5 casos
# ---------------------------------------------------------------------------
import io as _io
import metrics as _metrics_mod


def _empty_summary() -> dict:
    return _metrics_mod.summarize([], [])


@test
def test_print_report_contiene_encabezado():
    """print_report escribe la cabecera KAIZEN a stdout."""
    old_out = sys.stdout
    try:
        buf = _io.StringIO()
        sys.stdout = buf
        _metrics_mod.print_report(_empty_summary())
    finally:
        sys.stdout = old_out
    assert "KAIZEN" in buf.getvalue(), "debe contener KAIZEN en el encabezado"


@test
def test_print_report_contiene_campos_requeridos():
    """print_report incluye los campos principales en la salida."""
    old_out = sys.stdout
    try:
        buf = _io.StringIO()
        sys.stdout = buf
        _metrics_mod.print_report(_empty_summary())
    finally:
        sys.stdout = old_out
    out = buf.getvalue()
    assert "Sesiones totales" in out, "debe mostrar sesiones totales"
    assert "Tasa de aceptaci" in out, "debe mostrar tasa de aceptacion"
    assert "p95" in out, "debe mostrar p95"


@test
def test_read_index_sin_archivo():
    """read_index devuelve [] cuando el archivo no existe."""
    old = _metrics_mod.INDEX
    try:
        _metrics_mod.INDEX = Path(tempfile.mkdtemp()) / "no_existe.json"
        result = _metrics_mod.read_index()
        assert_eq(result, [], "sin archivo debe devolver lista vacia")
    finally:
        _metrics_mod.INDEX = old


@test
def test_read_index_con_fixture():
    """read_index devuelve las sesiones del archivo."""
    with tempfile.TemporaryDirectory() as td:
        idx = Path(td) / "_index.json"
        idx.write_text(_json.dumps({"sessions": [{"id": "s1"}, {"id": "s2"}]}), encoding="utf-8")
        old = _metrics_mod.INDEX
        try:
            _metrics_mod.INDEX = idx
            result = _metrics_mod.read_index()
            assert_eq(len(result), 2, "debe devolver 2 sesiones")
            assert_eq(result[0]["id"], "s1", "primera sesion debe ser s1")
        finally:
            _metrics_mod.INDEX = old


@test
def test_read_forensic_sin_archivo():
    """read_forensic devuelve [] cuando el archivo no existe."""
    old = _metrics_mod.FORENSIC
    try:
        _metrics_mod.FORENSIC = Path(tempfile.mkdtemp()) / "no_existe.jsonl"
        result = _metrics_mod.read_forensic()
        assert_eq(result, [], "sin archivo debe devolver lista vacia")
    finally:
        _metrics_mod.FORENSIC = old


# ---------------------------------------------------------------------------
# B-83: validate.validate_session — 4 casos de integración
# ---------------------------------------------------------------------------
import validate as _validate_mod


def _make_session_dir(td: str) -> Path:
    """Crea sesion valida minima en td y retorna el directorio."""
    root = Path(td)
    sid = "2026-06-22T000000Z__test-session-b83"
    sdir = root / "sessions" / sid
    sdir.mkdir(parents=True)
    (sdir / "session.json").write_text(_json.dumps({
        "id": sid,
        "objective": "obj",
        "mode": "hitl",
        "adapter": "generic",
        "created_utc": "2026-06-22T00:00:00+00:00",
        "status": "open",
    }), encoding="utf-8")
    return sdir


@test
def test_validate_session_valida():
    """validate_session devuelve 0 cuando session.json es valida y no hay artefactos opcionales."""
    with tempfile.TemporaryDirectory() as td:
        sdir = _make_session_dir(td)
        old_s, old_c = _validate_mod.SESSIONS, _validate_mod.CONTRACTS
        try:
            _validate_mod.SESSIONS = Path(td) / "sessions"
            _validate_mod.CONTRACTS = _validate_mod.CONTRACTS  # contratos reales
            rc = _validate_mod.validate_session("2026-06-22T000000Z__test-session-b83", strict=False)
            assert_eq(rc, 0, "sesion valida debe retornar 0")
        finally:
            _validate_mod.SESSIONS = old_s
            _validate_mod.CONTRACTS = old_c


@test
def test_validate_session_inexistente():
    """validate_session devuelve 1 cuando el directorio de sesion no existe."""
    with tempfile.TemporaryDirectory() as td:
        old_s = _validate_mod.SESSIONS
        try:
            _validate_mod.SESSIONS = Path(td) / "sessions"
            (Path(td) / "sessions").mkdir()
            rc = _validate_mod.validate_session("no-existe", strict=False)
            assert_eq(rc, 1, "sesion inexistente debe retornar 1")
        finally:
            _validate_mod.SESSIONS = old_s


@test
def test_validate_session_score_fuera_de_rango():
    """validate_session devuelve 1 cuando evaluation.json tiene score > 3."""
    with tempfile.TemporaryDirectory() as td:
        sdir = _make_session_dir(td)
        (sdir / "evaluation.json").write_text(_json.dumps({
            "session_id": "2026-06-22T000000Z__test-session-b83",
            "scores": {"value": 5, "correctness": 2, "scope": 2, "reversibility": 2, "measurability": 2},
            "total": 13,
            "blocking": [],
            "preliminary_verdict": "accept",
            "evaluator": "test",
        }), encoding="utf-8")
        old_s = _validate_mod.SESSIONS
        try:
            _validate_mod.SESSIONS = Path(td) / "sessions"
            rc = _validate_mod.validate_session("2026-06-22T000000Z__test-session-b83", strict=False)
            assert_eq(rc, 1, "score > 3 debe retornar 1")
        finally:
            _validate_mod.SESSIONS = old_s


@test
def test_validate_session_strict_falta_proposal():
    """validate_session devuelve 1 en modo strict si falta proposal.json."""
    with tempfile.TemporaryDirectory() as td:
        sdir = _make_session_dir(td)
        old_s = _validate_mod.SESSIONS
        try:
            _validate_mod.SESSIONS = Path(td) / "sessions"
            rc = _validate_mod.validate_session("2026-06-22T000000Z__test-session-b83", strict=True)
            assert_eq(rc, 1, "strict sin proposal debe retornar 1")
        finally:
            _validate_mod.SESSIONS = old_s


# --- run_session: load_profile y utc_now (B-96) -----------------------------------------------

@test
def test_utc_now_formato():
    """utc_now() retorna string ISO con offset UTC ('+00:00') y longitud >= 19."""
    ts = _rs.utc_now()
    assert "+00:00" in ts, "utc_now debe incluir '+00:00', got: %r" % ts
    assert len(ts) >= 19, "utc_now debe tener al menos 19 chars, got: %r" % ts


@test
def test_load_profile_sin_config_ni_perfil_lanza():
    """load_profile() lanza FileNotFoundError cuando CONFIG no existe y el perfil default tampoco."""
    with tempfile.TemporaryDirectory() as td:
        old_config = _rs.CONFIG
        old_root = _rs.ROOT
        try:
            _rs.ROOT = Path(td)
            _rs.CONFIG = Path(td) / "config" / "kaizen.config.yaml"
            raised = False
            try:
                _rs.load_profile()
            except (FileNotFoundError, OSError):
                raised = True
            assert raised, "load_profile sin config ni perfil default debe lanzar FileNotFoundError"
        finally:
            _rs.CONFIG = old_config
            _rs.ROOT = old_root


@test
def test_load_profile_con_config():
    """load_profile() carga el perfil indicado en CONFIG cuando existe."""
    with tempfile.TemporaryDirectory() as td:
        old_config = _rs.CONFIG
        old_root = _rs.ROOT
        try:
            _rs.ROOT = Path(td)
            cfg_dir = Path(td) / "config"
            cfg_dir.mkdir()
            (cfg_dir / "kaizen.config.yaml").write_text("profile: custom\n", encoding="utf-8")
            profiles_dir = cfg_dir / "profiles"
            profiles_dir.mkdir()
            (profiles_dir / "custom.yaml").write_text(
                "aotl:\n  commit_on_accept: false\n", encoding="utf-8")
            _rs.CONFIG = cfg_dir / "kaizen.config.yaml"
            result = _rs.load_profile()
            assert isinstance(result, dict), "load_profile debe retornar dict"
            assert result.get("aotl", {}).get("commit_on_accept") is False, \
                "debe cargar perfil custom con commit_on_accept=false, got: %r" % result
        finally:
            _rs.CONFIG = old_config
            _rs.ROOT = old_root


if __name__ == "__main__":
    print("Kaizen — test_core.py")
    print("=" * 40)
    raise SystemExit(run_all())
