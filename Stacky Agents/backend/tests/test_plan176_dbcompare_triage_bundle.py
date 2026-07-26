"""Plan 176 F3 — La curación del operador se vuelve efectiva en el bundle.

Hasta acá el triage era una anotación. Esta fase hace que un ítem excluido NO
emita script ni backup, sin que nadie tenga que borrar bloques de SQL a mano.

Dos casos son innegociables: sin exclusiones el bundle debe salir IDÉNTICO al de
antes (KPI-5), y un ítem excluido no puede aparecer en ningún archivo (KPI-1).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import dbcompare_scripts as scripts  # noqa: E402
from services import dbcompare_sqlnames as sqlnames  # noqa: E402
from tests._plan125_fixtures import make_col, make_schema_obj, make_table  # noqa: E402

TS = "20260726_120000"
RUN_ID = "run_plan176_bundle"


def _diff():
    return {
        "version": 1,
        "engine": "sqlserver",
        "source": {"alias": "DEV", "snapshot_id": "s1", "content_hash": "h1"},
        "target": {"alias": "TEST", "snapshot_id": "s2", "content_hash": "h2"},
        "items": [
            {"object_type": "table", "schema": "dbo", "name": "NUEVA",
             "action": "added", "severity": "warn", "changes": []},
            {"object_type": "table", "schema": "dbo", "name": "VIEJA",
             "action": "removed", "severity": "danger", "changes": []},
        ],
        "summary": {},
    }


def _source():
    return make_schema_obj("DEV", "dbo", tables={
        "NUEVA": make_table(columns=[make_col("ID", "INT", nullable=False)],
                            pk_columns=["ID"], pk_name="PK_NUEVA"),
    })


def _target():
    return make_schema_obj("TEST", "dbo", tables={
        "VIEJA": make_table(columns=[make_col("ID", "INT", nullable=False)],
                            pk_columns=["ID"], pk_name="PK_VIEJA"),
    })


def _data_diff():
    return {"status": "done", "tables": {"dbo.PARAM": {
        "schema": "dbo", "table": "PARAM", "pk_cols": ["ID"],
        "columns": ["ID", "VALOR"],
        "column_types": {"ID": "int", "VALOR": "varchar"},
        "only_source": [{"ID": "1", "VALOR": "a"}, {"ID": "2", "VALOR": "b"}],
        "only_target": [],
        "changed": [],
        "identical": False,
    }}}


@pytest.fixture(autouse=True)
def bundle_aislado(tmp_path, monkeypatch):
    """Ningún test escribe en el directorio de bundles real.

    OJO: `_write_bundle_atomic` arma la ruta con `data_dir()` directo, NO con
    `_bundle_dir`. Parchear solo `_bundle_dir` deja los bundles en el directorio
    del operador y hace que los asserts corran sobre una carpeta vacía — falso
    verde. Se parchea `data_dir` en el módulo, que es lo que de verdad se usa.
    """
    from services import dbcompare_triage

    monkeypatch.setattr(scripts, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(scripts, "_bundle_dir", lambda run_id: _base(tmp_path) / run_id)
    monkeypatch.setattr(dbcompare_triage, "_triage_dir", lambda: tmp_path / "triage")
    return tmp_path


def _base(tmp_path: Path) -> Path:
    return tmp_path / scripts._BUNDLES_DIRNAME


def _generar(excluded=None, data_merge_mode=False, data_diff=None):
    return scripts.generate_parity_bundle_from_diff(
        _diff(), RUN_ID, _source(), _target(), "sqlserver", ts=TS,
        data_diff=data_diff, data_merge_mode=data_merge_mode,
        excluded_keys=excluded,
    )


def _archivos(tmp_path) -> dict:
    base = _base(tmp_path) / RUN_ID
    assert base.is_dir(), "el bundle no se escribió donde el test mira"
    archivos = {p.relative_to(base).as_posix(): p.read_text(encoding="utf-8")
                for p in base.rglob("*") if p.is_file()}
    assert archivos, "bundle vacío: los asserts de abajo no probarían nada"
    return archivos


@pytest.mark.parametrize("merge", [False, True])
def test_sin_triage_bundle_identico(bundle_aislado, merge):
    """KPI-5: sin decisiones, el bundle es byte a byte el de siempre."""
    manifest_none = _generar(excluded=None, data_merge_mode=merge,
                             data_diff=_data_diff())
    archivos_none = _archivos(bundle_aislado)

    manifest_vacio = _generar(excluded=set(), data_merge_mode=merge,
                              data_diff=_data_diff())
    archivos_vacio = _archivos(bundle_aislado)

    assert manifest_none == manifest_vacio
    assert archivos_none == archivos_vacio
    assert "TRIAGE_EXCLUSIONS.md" not in archivos_none


def test_item_excluido_no_emite_script(bundle_aislado):
    """KPI-1: el nombre calificado del ítem excluido no aparece en NINGÚN archivo."""
    _generar(excluded={"table:dbo.VIEJA"})

    calificado = sqlnames.qualified("dbo", "VIEJA", "sqlserver")
    for nombre, contenido in _archivos(bundle_aislado).items():
        if nombre == "TRIAGE_EXCLUSIONS.md":
            continue  # justamente documenta lo excluido
        assert calificado not in contenido, f"{nombre} todavía toca la tabla excluida"


def test_item_excluido_sale_del_manifest(bundle_aislado):
    manifest = _generar(excluded={"table:dbo.VIEJA"})

    nombres = {f"{e['schema']}.{e['name']}" for e in manifest["entries"]}
    assert "dbo.VIEJA" not in nombres
    assert "dbo.NUEVA" in nombres, "lo NO excluido tiene que seguir emitiendo"


def test_exclusiones_md_presente_y_ordenado(bundle_aislado):
    from services import dbcompare_triage

    dbcompare_triage.set_decision(RUN_ID, "table:dbo.VIEJA", "excluido",
                                  note="la borramos el mes pasado")
    dbcompare_triage.set_decision(RUN_ID, "table:dbo.NUEVA", "excluido",
                                  note="todavía no va")

    _generar(excluded={"table:dbo.VIEJA", "table:dbo.NUEVA"})

    md = _archivos(bundle_aislado)["TRIAGE_EXCLUSIONS.md"]
    assert md.index("dbo.NUEVA") < md.index("dbo.VIEJA"), "ordenado por item_key"
    assert "la borramos el mes pasado" in md and "todavía no va" in md


def test_regla_de_oro_se_mantiene_con_exclusiones(bundle_aislado):
    """Un destructivo excluido no deja ni script ni backup huérfano."""
    manifest = _generar(excluded={"table:dbo.VIEJA"})

    # El invariante del 125 corre dentro de la generación; si algo quedara
    # despareado, generate_* habría lanzado. Se re-afirma explícitamente:
    scripts._assert_pairing_invariant(manifest["entries"])
    for entrada in manifest["entries"]:
        if entrada["destructive"]:
            assert entrada.get("backup_file"), entrada


def test_fila_datos_excluida_no_emite_dml(bundle_aislado):
    from services import dbcompare_triage

    key = dbcompare_triage.item_key_for_data_row("dbo", "PARAM", {"ID": "1"})
    _generar(excluded={key}, data_diff=_data_diff(), data_merge_mode=False)

    datos = "\n".join(v for k, v in _archivos(bundle_aislado).items()
                      if k.startswith("03_datos/"))
    assert datos, "el fixture debe emitir algo de datos para que el test valga"
    assert "'b'" in datos, "la fila NO excluida sigue emitiendo"
    assert "'a'" not in datos, "la fila excluida no puede emitir DML"


def test_fila_excluida_no_emite_merge(bundle_aislado):
    """Mismo filtro en el modo merge del plan 182: se filtra ANTES de emitir."""
    from services import dbcompare_triage

    key = dbcompare_triage.item_key_for_data_row("dbo", "PARAM", {"ID": "1"})
    _generar(excluded={key}, data_diff=_data_diff(), data_merge_mode=True)

    datos = "\n".join(v for k, v in _archivos(bundle_aislado).items()
                      if k.startswith("03_datos/"))
    assert "'a'" not in datos


def test_tabla_entera_excluida_no_pide_backup(bundle_aislado):
    """Si ninguna fila sobrevive, la tabla no se toca ⇒ no necesita resguardo."""
    from services import dbcompare_triage

    claves = {dbcompare_triage.item_key_for_data_row("dbo", "PARAM", {"ID": v})
              for v in ("1", "2")}
    manifest = _generar(excluded=claves, data_diff=_data_diff())

    tocadas = {f"{e['schema']}.{e['name']}" for e in manifest["entries"]}
    assert "dbo.PARAM" not in tocadas


def test_filter_data_rows_no_muta_el_original():
    """El mismo diff alimenta la pantalla: mutarlo borraría filas de la vista."""
    from services import dbcompare_triage

    original = _data_diff()["tables"]["dbo.PARAM"]
    antes = len(original["only_source"])
    key = dbcompare_triage.item_key_for_data_row("dbo", "PARAM", {"ID": "1"})

    copia = scripts.filter_data_rows_by_triage(original, {key})

    assert len(original["only_source"]) == antes
    assert len(copia["only_source"]) == antes - 1


def test_filter_pieces_devuelve_ambas_listas():
    piezas = [
        {"object_type": "table", "schema": "dbo", "name": "A"},
        {"object_type": "table", "schema": "dbo", "name": "B"},
    ]

    quedan, fuera = scripts.filter_pieces_by_triage(piezas, {"table:dbo.B"})

    assert [p["name"] for p in quedan] == ["A"]
    assert [p["name"] for p in fuera] == ["B"]
