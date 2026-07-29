"""Plan 269 F1 — Tests de los colectores de evidencia.

NO TOCAN LA BASE REAL: los "tickets"/"ejecuciones" son objetos falsos con los
mismos atributos, y la `session` es un doble que revienta si alguien intenta
escribir. Cero red.

15 casos (§5 F1 del plan 269).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import run_evidence as re_mod  # noqa: E402
from services.run_evidence import _Budget, collect_for_executions  # noqa: E402

FLAG = "STACKY_RUN_EVIDENCE_COLLECTORS_ENABLED"


def _ex(ex_id=1, *, output=None, html=None, contract=None, meta=None):
    return SimpleNamespace(
        id=ex_id, output=output, html_output_path=html,
        contract_result=contract, metadata_dict=(meta if meta is not None else {}),
    )


class _SessionQueMataSiLaTocan:
    """Si el colector la usa, revienta: sirve para probar que NO hay query."""

    def query(self, *a, **kw):
        raise AssertionError("no debia hacerse ninguna query")

    def add(self, *a, **kw):
        raise AssertionError("un colector JAMAS escribe")

    add_all = merge = delete = commit = flush = add


class _SessionFalsa:
    """Cuenta queries y devuelve los ids publicados que se le configuren."""

    def __init__(self, publicados=(), lanzar=False):
        self.publicados = list(publicados)
        self.lanzar = lanzar
        self.queries = 0

    def query(self, *a, **kw):
        self.queries += 1
        if self.lanzar:
            raise RuntimeError("db caida")
        return self

    def filter(self, *a, **kw):
        return self

    def all(self):
        return [(i,) for i in self.publicados]

    def add(self, *a, **kw):
        raise AssertionError("un colector JAMAS escribe")

    add_all = merge = delete = commit = flush = add


def test_1_flag_off_devuelve_dict_vacio(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, FLAG, False)
    assert collect_for_executions(_SessionQueMataSiLaTocan(), [_ex(1)]) == {}


def test_2_entregable_por_output_no_toca_disco(monkeypatch):
    def _boom(self):
        raise AssertionError("no debia tocarse el disco")

    monkeypatch.setattr(Path, "is_file", _boom)
    out = collect_for_executions(_SessionFalsa(), [_ex(1, output="resultado")])
    assert out[1].entregable_presente is True


def test_3_entregable_por_html_existente(tmp_path):
    lleno = tmp_path / "lleno.html"
    lleno.write_text("<p>x</p>", encoding="utf-8")
    vacio = tmp_path / "vacio.html"
    vacio.write_text("", encoding="utf-8")
    inexistente = tmp_path / "no_esta.html"

    out = collect_for_executions(_SessionFalsa(), [
        _ex(1, html=str(lleno)), _ex(2, html=str(vacio)), _ex(3, html=str(inexistente)),
    ])
    assert out[1].entregable_presente is True
    assert out[2].entregable_presente is False
    assert out[3].entregable_presente is False


def test_4_entregable_oserror_es_desconocido(monkeypatch, tmp_path):
    def _boom(self):
        raise OSError("disco ilegible")

    monkeypatch.setattr(Path, "is_file", _boom)
    out = collect_for_executions(_SessionFalsa(), [_ex(1, html=str(tmp_path / "x.html"))])
    assert out[1].entregable_presente is None, "un OSError debe dar None, nunca False"


def test_5_colector_lento_degrada_a_desconocido(monkeypatch, tmp_path):
    """Presupuesto agotado desde el arranque: nada cuelga y nada se inventa."""
    monkeypatch.setattr(re_mod, "_Budget", lambda _s: _Budget(-1))
    archivo = tmp_path / "hay.html"
    archivo.write_text("x", encoding="utf-8")
    out = collect_for_executions(_SessionFalsa(), [_ex(1, html=str(archivo))])
    assert out[1].entregable_presente is None
    assert out[1].cambio_en_repo is None


def test_6_publicado_en_una_sola_query():
    ses = _SessionFalsa(publicados=[3, 7])
    ejecuciones = [_ex(i) for i in range(1, 51)]
    out = collect_for_executions(ses, ejecuciones)
    assert ses.queries == 1, f"se hicieron {ses.queries} queries para 50 ejecuciones"
    assert out[3].publicado_en_tracker is True
    assert out[7].publicado_en_tracker is True
    assert out[4].publicado_en_tracker is False


def test_7_publicado_query_que_lanza_es_desconocido():
    ses = _SessionFalsa(lanzar=True)
    out = collect_for_executions(ses, [_ex(1, output="algo")])
    assert out[1].publicado_en_tracker is None, "la query fallo: None, no False"
    # Las demas señales se siguen computando igual.
    assert out[1].entregable_presente is True


def test_8_publicado_cuenta_idempotent_replay():
    """El dedupe deja la fila 'ok' en la PRIMERA ejecucion; la re-corrida solo
    tiene 'idempotent_replay' — y eso SI significa publicado."""
    assert "idempotent_replay" in re_mod.PUBLISHED_STATUSES
    assert "ok" in re_mod.PUBLISHED_STATUSES
    assert "failed" not in re_mod.PUBLISHED_STATUSES
    assert "skipped" not in re_mod.PUBLISHED_STATUSES

    class _SesionPorStatus:
        def __init__(self, filas):
            self.filas = filas
            self._ids = None
            self._statuses = None

        def query(self, *a, **kw):
            return self

        def filter(self, crit=None, *a, **kw):
            return self

        def all(self):
            return [
                (eid,) for eid, st in self.filas
                if st in re_mod.PUBLISHED_STATUSES
            ]

    ses = _SesionPorStatus([(1, "idempotent_replay"), (2, "failed"), (3, "skipped"), (4, "ok")])
    out = collect_for_executions(ses, [_ex(1), _ex(2), _ex(3), _ex(4)])
    assert out[1].publicado_en_tracker is True, "idempotent_replay debe contar"
    assert out[2].publicado_en_tracker is False
    assert out[3].publicado_en_tracker is False
    assert out[4].publicado_en_tracker is True


def test_9_cambio_en_repo_sin_sidecar_es_false(monkeypatch, tmp_path):
    monkeypatch.setattr(re_mod, "_sidecar_path", lambda eid: tmp_path / f"{eid}.json")
    out = collect_for_executions(_SessionFalsa(), [_ex(1)])
    assert out[1].cambio_en_repo is False, "ausencia informada, no ignorancia"


def test_10_cambio_en_repo_con_pr_url_es_true(monkeypatch, tmp_path):
    (tmp_path / "1.json").write_text('{"pr_url": "https://gitlab/x/-/merge_requests/1"}', encoding="utf-8")
    (tmp_path / "2.json").write_text('{"files_committed": 3}', encoding="utf-8")
    (tmp_path / "3.json").write_text('{"files_committed": 0}', encoding="utf-8")
    monkeypatch.setattr(re_mod, "_sidecar_path", lambda eid: tmp_path / f"{eid}.json")
    out = collect_for_executions(_SessionFalsa(), [_ex(1), _ex(2), _ex(3)])
    assert out[1].cambio_en_repo is True
    assert out[2].cambio_en_repo is True
    assert out[3].cambio_en_repo is False


def test_11_cambio_en_repo_no_crea_directorios(monkeypatch, tmp_path):
    """El colector NO crea el directorio (lo que si haria el getter de intents)."""
    destino = tmp_path / "no_existe"
    monkeypatch.setattr(re_mod, "_sidecar_path", lambda eid: destino / f"{eid}.json")
    collect_for_executions(_SessionFalsa(), [_ex(7)])
    assert destino.exists() is False, "el colector creo un directorio en disco"
    # Y el getter prohibido no se nombra en el modulo.
    src = Path(re_mod.__file__).read_text(encoding="utf-8")
    assert "get_intent" not in src


def test_12_cambio_en_repo_json_roto_es_desconocido(monkeypatch, tmp_path):
    (tmp_path / "1.json").write_text("{esto no es json", encoding="utf-8")
    monkeypatch.setattr(re_mod, "_sidecar_path", lambda eid: tmp_path / f"{eid}.json")
    out = collect_for_executions(_SessionFalsa(), [_ex(1)])
    assert out[1].cambio_en_repo is None, "json roto: None, no False"


def test_13_gate_lee_ambas_formas_y_desconoce_el_resto():
    """H1 declarada: dos formas conocidas; una tercera NO se inventa como True."""
    out = collect_for_executions(_SessionFalsa(), [
        _ex(1, contract={"passed": True}),
        _ex(2, contract={"status": "passed"}),
        _ex(3, contract={"passed": False}),
        _ex(4, contract=None),
        _ex(5, contract={"resultado": "ok"}),
    ])
    assert out[1].gate_aceptacion_ok is True
    assert out[2].gate_aceptacion_ok is True
    assert out[3].gate_aceptacion_ok is False
    assert out[4].gate_aceptacion_ok is None
    assert out[5].gate_aceptacion_ok is False, "una forma desconocida NO es True"


def test_14_verificacion_lee_passed_tri_estado():
    """El campo es `passed`, NO `ok`: leer `ok` daba SIEMPRE False."""
    out = collect_for_executions(_SessionFalsa(), [
        _ex(1, meta={"exec_verification": {"passed": True}}),
        _ex(2, meta={"exec_verification": {"passed": False}}),
        _ex(3, meta={"exec_verification": {"passed": None}}),
        _ex(4, meta={}),
        _ex(5, meta={"exec_verification": {"ok": True}}),
    ])
    assert out[1].verificacion_ok is True
    assert out[2].verificacion_ok is False
    assert out[3].verificacion_ok is None
    assert out[4].verificacion_ok is None
    assert out[5].verificacion_ok is None, "el campo `ok` no existe: no se lee"


def test_15_no_escribe_nada(monkeypatch, tmp_path):
    """add/merge/delete/commit/flush revientan; la corrida completa pasa igual."""
    monkeypatch.setattr(re_mod, "_sidecar_path", lambda eid: tmp_path / f"{eid}.json")
    ses = _SessionFalsa(publicados=[1])
    out = collect_for_executions(ses, [
        _ex(1, output="x", contract={"passed": True},
            meta={"exec_verification": {"passed": True}}),
        _ex(2),
    ])
    assert set(out) == {1, 2}
    with pytest.raises(AssertionError):
        ses.add()
