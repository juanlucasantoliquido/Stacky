"""Plan 176 F1 — Triage del diff: la decisión humana, persistida por corrida.

El prior art de RSPACIFICO curaba el diff a mano en un PLAN-replay-a-TEST.md.
Esto lo convierte en capacidad del producto: cada ítem se marca confirmado o
excluido con nota, y los scripts respetan esa curación.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import dbcompare_triage as T  # noqa: E402

_RUN = "run_2026_src_vs_dst"


@pytest.fixture
def almacen(tmp_path, monkeypatch):
    """Aísla el directorio de triage: ningún test escribe en el de verdad."""
    monkeypatch.setattr(T, "_triage_dir", lambda: tmp_path / "triage")
    return tmp_path / "triage"


def test_item_key_schema_estable_y_literal():
    key = T.item_key_for_schema_item(
        {"object_type": "table", "schema": "dbo", "name": "RCONTROLES"})

    assert key == "table:dbo.RCONTROLES"


def test_item_key_schema_no_depende_de_la_corrida():
    """La key tiene que sobrevivir a re-comparar: sin run_id ni timestamps."""
    base = {"object_type": "table", "schema": "dbo", "name": "T"}

    assert T.item_key_for_schema_item({**base, "run_id": "a", "ts": 1}) == \
        T.item_key_for_schema_item({**base, "run_id": "b", "ts": 2})


def test_item_key_data_canonico_ordenado():
    key = T.item_key_for_data_row("dbo", "RCONTROLES", {"b": 1, "a": "x"})

    assert key.startswith("data:dbo.RCONTROLES:")
    sufijo = key.split(":", 2)[2]
    assert sufijo == '{"a":"x","b":"1"}', sufijo


def test_load_sin_archivo_devuelve_vacio(almacen):
    doc = T.load_triage(_RUN)

    assert doc == {"version": T.TRIAGE_VERSION, "run_id": _RUN,
                   "items": {}, "updated_at": None}


def test_set_decision_persiste_y_es_atomico(almacen):
    T.set_decision(_RUN, "table:dbo.T", "confirmado", note="revisado con el DBA")

    doc = T.load_triage(_RUN)
    assert doc["items"]["table:dbo.T"]["decision"] == "confirmado"
    assert doc["items"]["table:dbo.T"]["note"] == "revisado con el DBA"
    assert doc["items"]["table:dbo.T"]["decided_at"]
    assert not list(almacen.glob("*.tmp")), "quedó un temporal sin renombrar"


def test_decision_invalida_lanza_valueerror(almacen):
    with pytest.raises(ValueError):
        T.set_decision(_RUN, "table:dbo.T", "mas_o_menos")


def test_volver_a_pendiente_borra_la_entrada(almacen):
    T.set_decision(_RUN, "table:dbo.T", "excluido", note="no aplica")

    T.set_decision(_RUN, "table:dbo.T", "pendiente")

    assert T.load_triage(_RUN)["items"] == {}, \
        "volver a pendiente es borrar la decisión, no guardar una"


def test_note_se_trunca_a_2000(almacen):
    T.set_decision(_RUN, "table:dbo.T", "excluido", note="x" * 5000)

    assert len(T.load_triage(_RUN)["items"]["table:dbo.T"]["note"]) == T._NOTE_MAX_CHARS


def test_summary_cuenta_bien(almacen):
    T.set_decision(_RUN, "table:dbo.A", "confirmado")
    T.set_decision(_RUN, "table:dbo.B", "excluido")

    resumen = T.triage_summary(T.load_triage(_RUN), total_items=5)

    assert resumen == {"confirmado": 1, "excluido": 1, "pendiente": 3}


def test_summary_nunca_da_pendientes_negativos(almacen):
    """Si el diff encogió entre corridas, el resumen no puede mentir con un negativo."""
    for i in range(4):
        T.set_decision(_RUN, f"table:dbo.T{i}", "confirmado")

    assert T.triage_summary(T.load_triage(_RUN), total_items=2)["pendiente"] == 0


def test_excluded_keys(almacen):
    T.set_decision(_RUN, "table:dbo.A", "confirmado")
    T.set_decision(_RUN, "table:dbo.B", "excluido")

    assert T.excluded_keys(T.load_triage(_RUN)) == {"table:dbo.B"}


def test_attach_item_keys_enriquece_schema_y_data():
    run = {
        "diff": {"items": [
            {"object_type": "table", "schema": "dbo", "name": "RCONTROLES"},
            {"object_type": "view", "schema": "dbo", "name": "V_X"},
        ]},
        # Forma REAL (dbcompare_data): tables es un dict por "schema.table", las
        # filas de only_* vienen PLANAS (la PK mezclada con el resto de columnas)
        # y la PK se deriva de pk_cols; solo `changed` trae "pk" explícita.
        "data_diff": {"tables": {"dbo.RCONTROLES": {
            "schema": "dbo", "table": "RCONTROLES", "pk_cols": ["id"],
            "only_source": [{"id": "1", "nombre": "a"}],
            "only_target": [{"id": "2", "nombre": "b"}],
            "changed": [{"pk": {"id": "3"}, "cells": {}}],
        }}},
    }

    devuelto = T.attach_item_keys(run)

    assert devuelto is run, "enriquece in place"
    assert run["diff"]["items"][0]["item_key"] == "table:dbo.RCONTROLES"
    assert run["diff"]["items"][1]["item_key"] == "view:dbo.V_X"
    tabla = run["data_diff"]["tables"]["dbo.RCONTROLES"]
    assert tabla["only_source"][0]["item_key"] == 'data:dbo.RCONTROLES:{"id":"1"}'
    assert tabla["only_target"][0]["item_key"] == 'data:dbo.RCONTROLES:{"id":"2"}'
    assert tabla["changed"][0]["item_key"] == 'data:dbo.RCONTROLES:{"id":"3"}'


def test_attach_item_keys_tolera_runs_incompletos():
    """Un run a medias (sin diff, sin data_diff) no puede tumbar el GET."""
    for run in ({}, {"diff": {}}, {"diff": {"items": []}}, {"data_diff": {"tables": {}}},
                {"diff": None, "data_diff": None},
                {"data_diff": {"tables": {"x.y": {"error": "boom"}}}}):
        assert T.attach_item_keys(dict(run)) is not None


def test_load_tolera_archivo_corrupto(almacen):
    almacen.mkdir(parents=True, exist_ok=True)
    (almacen / f"{_RUN}.json").write_text("no soy json", encoding="utf-8")

    doc = T.load_triage(_RUN)

    assert doc["items"] == {}, "un archivo corrupto se trata como vacío, no revienta"


def test_run_id_no_escapa_del_directorio(almacen):
    """El run_id llega por URL: no puede escribir fuera de su carpeta."""
    with pytest.raises(ValueError):
        T.set_decision("../../etc/passwd", "table:dbo.T", "confirmado")


def test_exclusions_markdown_determinista(almacen):
    T.set_decision(_RUN, "table:dbo.B", "excluido", note="ya migrada a mano")
    T.set_decision(_RUN, "table:dbo.A", "excluido", note="obsoleta")
    T.set_decision(_RUN, "table:dbo.C", "confirmado")

    md = T.exclusions_markdown(_RUN, T.load_triage(_RUN))

    assert md.index("dbo.A") < md.index("dbo.B"), "ordenado por item_key"
    assert "obsoleta" in md and "ya migrada a mano" in md
    assert "dbo.C" not in md, "lo confirmado no es una exclusión"


def test_exclusions_markdown_sin_exclusiones(almacen):
    assert "Sin exclusiones." in T.exclusions_markdown(_RUN, T.load_triage(_RUN))


def test_documento_es_json_serializable(almacen):
    T.set_decision(_RUN, "table:dbo.T", "confirmado", note="ok")

    crudo = (almacen / f"{_RUN}.json").read_text(encoding="utf-8")

    assert json.loads(crudo)["version"] == T.TRIAGE_VERSION
