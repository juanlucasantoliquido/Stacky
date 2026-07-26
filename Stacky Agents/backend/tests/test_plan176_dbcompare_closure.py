"""Plan 176 F7 — Verificación de cierre: la migración se aplicó y no tocó lo demás.

Lo interesante es la asimetría: que una diferencia EXCLUIDA siga ahí no es un
fallo, es la prueba de que la migración respetó la curación. Al revés —un
excluido que desapareció— sí lo es: alguien tocó lo que no debía.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import dbcompare_closure as C  # noqa: E402

_VIEJO = "run_viejo_src_vs_dst"
_NUEVO = "run_verif_src_vs_dst"


def _item(nombre: str, tipo: str = "table") -> dict:
    return {"object_type": tipo, "schema": "dbo", "name": nombre,
            "action": "changed", "severity": "danger", "changes": []}


def _run(run_id: str, nombres: list) -> dict:
    return {"run_id": run_id, "status": "done",
            "diff": {"items": [_item(n) for n in nombres]}}


def _triage(decisiones: dict) -> dict:
    return {"version": 1, "items": {
        f"table:dbo.{n}": {"decision": d} for n, d in decisiones.items()}}


# ---------------------------------------------------------------------------
# Expectativas
# ---------------------------------------------------------------------------

def test_confirmado_espera_resuelto_y_excluido_espera_persiste():
    esperadas = C.derive_expectations(
        _run(_VIEJO, ["A", "B"])["diff"],
        _triage({"A": "confirmado", "B": "excluido"}))

    assert esperadas == [
        {"item_key": "table:dbo.A", "expectation": "resuelto"},
        {"item_key": "table:dbo.B", "expectation": "persiste"},
    ]


def test_pendiente_no_genera_expectativa():
    """No decidir no es decidir: inventarle un veredicto sería fabricarlo."""
    esperadas = C.derive_expectations(
        _run(_VIEJO, ["A"])["diff"], _triage({"A": "pendiente"}))

    assert esperadas == []


def test_item_sin_decision_no_genera_expectativa():
    assert C.derive_expectations(_run(_VIEJO, ["A"])["diff"], {"items": {}}) == []


def test_expectativas_ordenadas_por_item_key():
    esperadas = C.derive_expectations(
        _run(_VIEJO, ["Z", "A"])["diff"],
        _triage({"Z": "confirmado", "A": "confirmado"}))

    assert [e["item_key"] for e in esperadas] == ["table:dbo.A", "table:dbo.Z"]


# ---------------------------------------------------------------------------
# Evaluación
# ---------------------------------------------------------------------------

def test_confirmado_resuelto_es_ok():
    reporte = C.evaluate_closure(_run(_VIEJO, ["A"]), _run(_NUEVO, []),
                                 _triage({"A": "confirmado"}))

    assert reporte["results"][0]["status"] == "ok"
    assert reporte["summary"] == {"ok": 1, "violado": 0, "sin_expectativa": 0}


def test_confirmado_que_sigue_presente_es_violado():
    """Se confirmó migrarlo y sigue difiriendo: la migración quedó incompleta."""
    reporte = C.evaluate_closure(_run(_VIEJO, ["A"]), _run(_NUEVO, ["A"]),
                                 _triage({"A": "confirmado"}))

    assert reporte["results"][0]["status"] == "violado"


def test_excluido_que_persiste_es_ok():
    """Que siga difiriendo es EXACTAMENTE lo que se pidió."""
    reporte = C.evaluate_closure(_run(_VIEJO, ["B"]), _run(_NUEVO, ["B"]),
                                 _triage({"B": "excluido"}))

    assert reporte["results"][0]["status"] == "ok"


def test_excluido_que_desaparecio_es_violado():
    """Alguien tocó lo que el operador dijo explícitamente que no se tocara."""
    reporte = C.evaluate_closure(_run(_VIEJO, ["B"]), _run(_NUEVO, []),
                                 _triage({"B": "excluido"}))

    assert reporte["results"][0]["status"] == "violado"


def test_summary_cuenta_los_sin_expectativa():
    reporte = C.evaluate_closure(
        _run(_VIEJO, ["A", "B", "C"]), _run(_NUEVO, ["B"]),
        _triage({"A": "confirmado", "B": "excluido", "C": "pendiente"}))

    assert reporte["summary"] == {"ok": 2, "violado": 0, "sin_expectativa": 1}


def test_reporte_lleva_los_dos_run_ids():
    reporte = C.evaluate_closure(_run(_VIEJO, ["A"]), _run(_NUEVO, []),
                                 _triage({"A": "confirmado"}))

    assert reporte["old_run_id"] == _VIEJO
    assert reporte["verification_run_id"] == _NUEVO
    assert reporte["version"] == C.CLOSURE_VERSION


def test_determinista():
    args = (_run(_VIEJO, ["A", "B"]), _run(_NUEVO, ["B"]),
            _triage({"A": "confirmado", "B": "excluido"}))

    assert C.evaluate_closure(*args) == C.evaluate_closure(*args)


def test_tolera_runs_vacios():
    reporte = C.evaluate_closure({}, {}, {})

    assert reporte["results"] == []
    assert reporte["summary"]["ok"] == 0


def test_distingue_por_tipo_de_objeto():
    """Una vista y una tabla con el mismo nombre no son el mismo ítem."""
    viejo = {"run_id": _VIEJO, "status": "done", "diff": {"items": [
        _item("X", "table"), _item("X", "view")]}}
    nuevo = {"run_id": _NUEVO, "status": "done",
             "diff": {"items": [_item("X", "view")]}}
    triage = {"items": {
        "table:dbo.X": {"decision": "confirmado"},
        "view:dbo.X": {"decision": "excluido"}}}

    reporte = C.evaluate_closure(viejo, nuevo, triage)

    assert reporte["summary"] == {"ok": 2, "violado": 0, "sin_expectativa": 0}


# ---------------------------------------------------------------------------
# Linkage
# ---------------------------------------------------------------------------

@pytest.fixture
def almacen(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "_closure_dir", lambda: tmp_path / "closure")
    return tmp_path / "closure"


def test_linkage_ausente_devuelve_none(almacen):
    assert C.load_linkage(_VIEJO) is None


def test_start_closure_lanza_y_linkea(almacen, monkeypatch):
    from services import dbcompare_runs

    monkeypatch.setattr(dbcompare_runs, "get_run",
                        lambda rid: {"run_id": rid, "status": "done",
                                     "source_alias": "src", "target_alias": "dst"})
    creado = {}

    def _crear(source, target, **kw):
        creado.update({"source": source, "target": target, **kw})
        return {"run_id": _NUEVO}

    monkeypatch.setattr(dbcompare_runs, "create_run", _crear)

    resultado = C.start_closure(_VIEJO)

    assert resultado["verification_run_id"] == _NUEVO
    assert creado["initiated_by"] == "closure", \
        "el run de verificación tiene que distinguirse del radar y del operador"
    assert C.load_linkage(_VIEJO)["verification_run_id"] == _NUEVO


def test_start_closure_exige_run_done(almacen, monkeypatch):
    from services import dbcompare_runs

    monkeypatch.setattr(dbcompare_runs, "get_run",
                        lambda rid: {"run_id": rid, "status": "running"})

    with pytest.raises(ValueError, match="run_not_done"):
        C.start_closure(_VIEJO)


def test_start_closure_run_inexistente(almacen, monkeypatch):
    from services import dbcompare_runs

    monkeypatch.setattr(dbcompare_runs, "get_run", lambda rid: None)

    with pytest.raises(ValueError, match="run_not_found"):
        C.start_closure(_VIEJO)


def test_run_id_no_escapa_del_directorio(almacen):
    with pytest.raises(ValueError):
        C._path_for("../../etc/passwd")
