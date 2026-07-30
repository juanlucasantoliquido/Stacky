"""Plan 266 F0.2/F1.5/F3 — forma garantizada del summary del Comparador de BD.

No importa `app` ni llama a `create_app()`: solo `services.dbcompare_runs`, con
`_runs_dir` monkeypatcheado a `tmp_path`. No toca la base viva del operador.
"""
import json
import pathlib

import pytest

from services import dbcompare_runs


def _run_dict(run_id, **over):
    base = {
        "run_id": run_id, "source_alias": "DEV", "target_alias": "QA",
        "engine": "sqlserver", "initiated_by": "operator", "mode": "fresh",
        "status": "done", "phase": "done",
        "started_at": "2026-07-27T10:00:00Z", "finished_at": "2026-07-27T10:01:00Z",
        "duration_ms": 60000, "source_snapshot_id": "s1", "target_snapshot_id": "s2",
        "summary": None, "diff": None, "error": None,
    }
    base.update(over)
    return base


@pytest.fixture
def runs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(dbcompare_runs, "_runs_dir", lambda: tmp_path)
    return tmp_path


def _write(runs_dir, run):
    (runs_dir / f"{run['run_id']}.json").write_text(
        json.dumps(run, ensure_ascii=False), encoding="utf-8")


def test_list_runs_completa_by_severity_faltante(runs_dir):
    _write(runs_dir, _run_dict("r1", summary={"parity_score": 91.7}))
    runs = dbcompare_runs.list_runs()
    assert runs[0]["summary"]["by_severity"] == {"info": 0, "warn": 0, "danger": 0}


def test_list_runs_completa_by_action_y_by_object_type(runs_dir):
    _write(runs_dir, _run_dict("r1", summary={"parity_score": 91.7}))
    runs = dbcompare_runs.list_runs()
    assert runs[0]["summary"]["by_action"] == {"added": 0, "removed": 0, "changed": 0}
    assert runs[0]["summary"]["by_object_type"] == {"table": 0, "view": 0, "sequence": 0}


def test_list_runs_completa_claves_parciales(runs_dir):
    _write(runs_dir, _run_dict("r1", summary={"by_severity": {"danger": 3}}))
    runs = dbcompare_runs.list_runs()
    assert runs[0]["summary"]["by_severity"] == {"info": 0, "warn": 0, "danger": 3}


def test_list_runs_coerce_valores_no_numericos(runs_dir):
    _write(runs_dir, _run_dict(
        "r1", summary={"by_severity": {"danger": "3", "warn": None, "info": -1}}))
    runs = dbcompare_runs.list_runs()
    assert runs[0]["summary"]["by_severity"] == {"info": 0, "warn": 0, "danger": 3}


def test_list_runs_preserva_summary_none(runs_dir):
    _write(runs_dir, _run_dict("r1", summary=None, status="running"))
    runs = dbcompare_runs.list_runs()
    assert runs[0]["summary"] is None


def test_get_run_normaliza_igual_que_list_runs(runs_dir):
    _write(runs_dir, _run_dict("r1", summary={"parity_score": 91.7}))
    run = dbcompare_runs.get_run("r1")
    assert run["summary"]["by_severity"] == {"info": 0, "warn": 0, "danger": 0}


def test_get_run_normaliza_tambien_el_summary_anidado_del_diff(runs_dir):
    # C4: get_run devuelve el run COMPLETO, diff incluido (a diferencia de list_runs,
    # que lo saca). SummaryHero.tsx y svgMath.ts leen justamente esa copia anidada.
    _write(runs_dir, _run_dict(
        "r1",
        summary={"parity_score": 91.7},
        diff={"summary": {"parity_score": 91.7}, "objects": []},
    ))
    run = dbcompare_runs.get_run("r1")
    assert run["diff"]["summary"]["by_severity"] == {"info": 0, "warn": 0, "danger": 0}
    assert run["diff"]["summary"]["by_action"] == {"added": 0, "removed": 0, "changed": 0}
    assert run["diff"]["summary"]["by_object_type"] == {"table": 0, "view": 0, "sequence": 0}


def test_get_run_no_reescribe_el_archivo_en_disco(runs_dir):
    _write(runs_dir, _run_dict(
        "r1",
        summary={"parity_score": 91.7},
        diff={"summary": {"parity_score": 91.7}, "objects": []},
    ))
    path = runs_dir / "r1.json"
    before = path.read_bytes()
    dbcompare_runs.get_run("r1")
    after = path.read_bytes()
    assert before == after


def test_list_runs_no_altera_summary_completo(runs_dir):
    # Control positivo: la normalización no puede pisar datos buenos.
    canon = {
        "by_severity": {"info": 1, "warn": 2, "danger": 3},
        "by_action": {"added": 1, "removed": 1, "changed": 1},
        "by_object_type": {"table": 5, "view": 2, "sequence": 1},
        "objects_total": 8,
        "objects_unchanged": 5,
        "parity_score": 91.7,
    }
    _write(runs_dir, _run_dict("r1", summary=canon))
    runs = dbcompare_runs.list_runs()
    assert runs[0]["summary"] == canon


def test_list_runs_no_reescribe_el_archivo_en_disco(runs_dir):
    _write(runs_dir, _run_dict("r1", summary={"parity_score": 91.7}))
    path = runs_dir / "r1.json"
    before = path.read_bytes()
    dbcompare_runs.list_runs()
    after = path.read_bytes()
    assert before == after


def test_count_infinito_es_cero():
    # C1: int(float(float("inf"))) lanza OverflowError, no TypeError ni ValueError.
    assert dbcompare_runs._count(float("inf")) == 0
    assert dbcompare_runs._count(float("-inf")) == 0


def test_count_nan_es_cero():
    assert dbcompare_runs._count(float("nan")) == 0


def test_count_booleano_es_cero():
    # C2: en Python bool es subclase de int; sin el corte, True daría 1 y el
    # frontend (toCount) daría 0 para el mismo valor.
    assert dbcompare_runs._count(True) == 0
    assert dbcompare_runs._count(False) == 0


def test_list_runs_no_lanza_con_infinity_en_disco(runs_dir):
    # El archivo se escribe A MANO (no con json.dumps, que no puede emitir estos
    # tokens): json.loads SÍ acepta Infinity/-Infinity/NaN por default, y eso
    # puede estar realmente en el disco del operador.
    (runs_dir / "r_inf.json").write_text(
        '{"run_id": "r_inf", "source_alias": "DEV", "target_alias": "QA",'
        ' "engine": "sqlserver", "status": "done", "phase": "done",'
        ' "started_at": "2026-07-27T10:00:00Z", "finished_at": "2026-07-27T10:01:00Z",'
        ' "summary": {"parity_score": 91.7, "by_severity": {"danger": Infinity,'
        ' "warn": -Infinity, "info": NaN}}}',
        encoding="utf-8",
    )
    runs = dbcompare_runs.list_runs()  # NO debe lanzar
    assert runs[0]["summary"]["by_severity"] == {"info": 0, "warn": 0, "danger": 0}


def test_flag_off_deja_el_payload_crudo(runs_dir, monkeypatch):
    import config
    monkeypatch.setattr(config.config, "STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED", False)
    _write(runs_dir, _run_dict("r1", summary={"parity_score": 91.7}))
    runs = dbcompare_runs.list_runs()
    assert runs[0]["summary"] == {"parity_score": 91.7}


def test_flag_registrada_default_on():
    from services import harness_flags
    spec = harness_flags._REGISTRY_INDEX["STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED"]
    assert spec.default is True
    assert harness_flags.categorize("STACKY_DB_COMPARE_SUMMARY_SHAPE_ENABLED") == "comparador_bd"


# --------------------------------------------------------------------------
# F1.5 — tabla de verdad compartida: _count (Python) vs toCount (TypeScript)
# --------------------------------------------------------------------------

# tests/ -> backend/ -> "Stacky Agents"/
_TRUTH_TABLE = (
    pathlib.Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "components" / "dbcompare" / "__fixtures__"
    / "summaryShapeTruthTable.json"
)


def _materializar(v):
    if isinstance(v, dict) and set(v.keys()) == {"raw"} and isinstance(v["raw"], str):
        raw = v["raw"]
        if raw == "NaN":
            return float("nan")
        if raw == "Infinity":
            return float("inf")
        if raw == "-Infinity":
            return float("-inf")
        raise AssertionError(f"sobre raw desconocido en la tabla de verdad: {raw}")
    return v


def test_tabla_de_verdad_compartida_existe():
    # Prohibido pytest.skip por archivo faltante: un skip acá es un falso verde.
    assert _TRUTH_TABLE.is_file()


def test_tabla_de_verdad_compartida_tiene_al_menos_17_casos():
    assert len(json.loads(_TRUTH_TABLE.read_text(encoding="utf-8"))) >= 17


def test_count_cumple_cada_caso_de_la_tabla_de_verdad():
    casos = json.loads(_TRUTH_TABLE.read_text(encoding="utf-8"))
    for c in casos:
        assert dbcompare_runs._count(_materializar(c["in"])) == c["out"], c["why"]
