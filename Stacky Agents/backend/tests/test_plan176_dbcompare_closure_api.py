"""Plan 176 F7 — Endpoints de verificación de cierre.

Ver Stacky Agents/docs/176_PLAN_DB_COMPARE_TRIAGE_CURADO_GATES_READONLY_Y_VERIFICACION_DE_CIERRE.md §F7.

El cierre responde una pregunta concreta: después de que el operador ejecutó los
scripts, ¿se resolvió lo que confirmó Y sigue difiriendo lo que excluyó? La
segunda mitad es la que importa: si lo excluido también desapareció, alguien
ejecutó de más y el diff "limpio" está tapando un cambio no querido.

El flujo completo de este archivo MUTA la base sqlite de destino entre las dos
comparaciones — sin esa mutación el test pasaría con un motor que no compara
nada.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture
def fake_keyring(monkeypatch):
    import services.dbcompare_registry as reg

    store: dict = {}

    class _FakeKeyring:
        @staticmethod
        def set_password(service, alias, password):
            store[(service, alias)] = password

        @staticmethod
        def get_password(service, alias):
            return store.get((service, alias))

        @staticmethod
        def delete_password(service, alias):
            store.pop((service, alias), None)

    monkeypatch.setattr(reg, "keyring", _FakeKeyring())
    return store


@pytest.fixture
def entorno(fake_keyring, tmp_path, monkeypatch):
    """Origen con 2 tablas de más; destino sin ellas ⇒ 2 ítems en el diff."""
    from sqlalchemy import create_engine

    import services.dbcompare_closure as closure
    import services.dbcompare_registry as reg
    import services.dbcompare_runs as runs
    import services.dbcompare_snapshot as snap
    import services.dbcompare_triage as triage

    for mod in (reg, snap, runs, triage, closure):
        monkeypatch.setattr(mod, "data_dir", lambda: tmp_path, raising=False)

    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    for archivo, tablas in ((db_a, ["CONFIRMADA", "EXCLUIDA"]), (db_b, [])):
        con = sqlite3.connect(archivo)
        for t in tablas:
            con.execute(f"CREATE TABLE {t} (ID INTEGER PRIMARY KEY)")
        con.commit()
        con.close()

    reg.upsert_environment("test-a", "sqlite", "localhost", 0, str(db_a), "user")
    reg.upsert_environment("test-b", "sqlite", "localhost", 0, str(db_b), "user")
    reg.set_password("test-a", "unused")
    reg.set_password("test-b", "unused")

    eng_a = create_engine(f"sqlite:///{db_a}")
    eng_b = create_engine(f"sqlite:///{db_b}")

    import services.dbcompare_engine as engine_mod

    monkeypatch.setattr(engine_mod, "open_engine",
                        lambda alias, **kw: eng_a if alias == "test-a" else eng_b)
    monkeypatch.setattr(snap, "open_engine",
                        lambda alias, **kw: eng_a if alias == "test-a" else eng_b, raising=False)

    return {"db_b": db_b, "tmp_path": tmp_path}


def _flag(monkeypatch, valor: bool):
    import config as config_mod

    monkeypatch.setattr(config_mod.config, "STACKY_DB_COMPARE_ENABLED", True, raising=False)
    monkeypatch.setattr(config_mod.config, "STACKY_DB_COMPARE_TRIAGE_ENABLED", valor, raising=False)


@pytest.fixture
def client(entorno, monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")

    import runtime_paths

    monkeypatch.setattr(runtime_paths, "data_dir", lambda: entorno["tmp_path"])

    from app import create_app
    from services.manifest_watcher import stop_manifest_watcher
    from services.ticket_status import stop_stale_recovery

    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()
    stop_manifest_watcher()


@pytest.fixture(autouse=True)
def sin_hilos_colgados():
    """Ningún hilo de corrida puede sobrevivir al test que lo lanzó.

    Si sobrevive, sigue escribiendo en el tmp_path del test anterior y hace
    fallar a otro test por un motivo que no tiene nada que ver con él — el peor
    tipo de rojo, porque manda a investigar el archivo equivocado.
    """
    yield
    import services.dbcompare_runs as runs

    limite = time.monotonic() + 10
    while time.monotonic() < limite and runs._ACTIVE_PAIRS:
        time.sleep(0.05)


def _esperar(run_id, timeout=6.0):
    import services.dbcompare_runs as runs

    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        actual = runs.get_run(run_id)
        if actual and actual["status"] in ("done", "error"):
            # Terminar en error y seguir sería leer el reporte de una
            # verificación que no ocurrió: el KeyError posterior mandaría a
            # investigar el endpoint en vez del motor.
            assert actual["status"] == "done", actual.get("error")
            return actual
        time.sleep(0.05)
    raise AssertionError(f"la corrida {run_id} no terminó")


def _comparar():
    import services.dbcompare_runs as runs

    run = runs.create_run("test-a", "test-b", mode="fresh")
    final = _esperar(run["run_id"])
    assert final["status"] == "done", final
    return final


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

def test_403_con_la_flag_apagada(client, entorno, monkeypatch):
    _flag(monkeypatch, False)

    assert client.post("/api/db-compare/runs/lo_que_sea/verify-closure").status_code == 403
    assert client.get("/api/db-compare/runs/lo_que_sea/closure").status_code == 403


def test_404_si_la_corrida_no_existe(client, entorno, monkeypatch):
    _flag(monkeypatch, True)

    assert client.post("/api/db-compare/runs/no_existe/verify-closure").status_code == 404


def test_404_sin_verificacion_lanzada(client, entorno, monkeypatch):
    # Pedir el reporte antes de verificar no es un error del servidor: es que
    # todavía no hay nada que contar.
    _flag(monkeypatch, True)
    run = _comparar()

    resp = client.get(f"/api/db-compare/runs/{run['run_id']}/closure")

    assert resp.status_code == 404
    assert resp.get_json()["error"] == "sin_verificacion"


def test_409_si_la_corrida_vieja_no_esta_done(client, entorno, monkeypatch):
    import services.dbcompare_runs as runs

    _flag(monkeypatch, True)
    run = _comparar()
    runs._update(run["run_id"], status="running")

    resp = client.post(f"/api/db-compare/runs/{run['run_id']}/verify-closure")

    assert resp.status_code == 409, resp.get_json()


def test_409_mientras_la_verificacion_esta_en_curso(client, entorno, monkeypatch):
    # El reporte no puede leerse a mitad de camino: daría un cierre parcial que
    # parece definitivo.
    import services.dbcompare_closure as closure
    import services.dbcompare_runs as runs

    _flag(monkeypatch, True)
    viejo = _comparar()
    nuevo = _comparar()
    closure._persistir_linkage(viejo["run_id"], nuevo["run_id"])
    runs._update(nuevo["run_id"], status="running")

    resp = client.get(f"/api/db-compare/runs/{viejo['run_id']}/closure")

    assert resp.status_code == 409
    assert resp.get_json()["error"] == "verificacion_en_curso"


# ---------------------------------------------------------------------------
# Flujo completo
# ---------------------------------------------------------------------------

def test_flujo_completo_ok_y_violado(client, entorno, monkeypatch):
    """Comparar → decidir → MUTAR la BD destino → verificar."""
    import services.dbcompare_closure as closure
    import services.dbcompare_triage as triage

    _flag(monkeypatch, True)
    viejo = _comparar()
    assert len(viejo["diff"]["items"]) == 2, viejo["diff"]["items"]

    for item in viejo["diff"]["items"]:
        decision = "confirmado" if item["name"] == "CONFIRMADA" else "excluido"
        triage.set_decision(viejo["run_id"], f"table:main.{item['name']}", decision)

    # El operador ejecuta el script: crea SOLO la tabla confirmada.
    con = sqlite3.connect(entorno["db_b"])
    con.execute("CREATE TABLE CONFIRMADA (ID INTEGER PRIMARY KEY)")
    con.commit()
    con.close()

    lanzado = client.post(f"/api/db-compare/runs/{viejo['run_id']}/verify-closure")
    assert lanzado.status_code == 202, lanzado.get_json()
    verification_run_id = lanzado.get_json()["verification_run_id"]
    _esperar(verification_run_id)

    reporte = client.get(f"/api/db-compare/runs/{viejo['run_id']}/closure").get_json()

    assert reporte["ok"] is True
    assert reporte["summary"]["ok"] == 2, reporte["results"]
    assert reporte["summary"]["violado"] == 0, reporte["results"]
    # Aserción discriminante: las dos expectativas son de signo OPUESTO. Un motor
    # que devolviera siempre "ok" pasaría un caso pero no los dos.
    por_key = {r["item_key"]: r for r in reporte["results"]}
    assert por_key["table:main.CONFIRMADA"]["expectation"] == "resuelto"
    assert por_key["table:main.EXCLUIDA"]["expectation"] == "persiste"
    assert closure.load_linkage(viejo["run_id"])["verification_run_id"] == verification_run_id


def test_detecta_que_se_ejecuto_de_mas(client, entorno, monkeypatch):
    """Lo excluido que desaparece es la señal más valiosa del cierre."""
    import services.dbcompare_triage as triage

    _flag(monkeypatch, True)
    viejo = _comparar()
    triage.set_decision(viejo["run_id"], "table:main.EXCLUIDA", "excluido")

    # Alguien creó también la tabla que se había decidido NO migrar.
    con = sqlite3.connect(entorno["db_b"])
    con.execute("CREATE TABLE EXCLUIDA (ID INTEGER PRIMARY KEY)")
    con.commit()
    con.close()

    lanzado = client.post(f"/api/db-compare/runs/{viejo['run_id']}/verify-closure")
    _esperar(lanzado.get_json()["verification_run_id"])

    reporte = client.get(f"/api/db-compare/runs/{viejo['run_id']}/closure").get_json()

    assert reporte["summary"]["violado"] == 1, reporte["results"]
    violado = next(r for r in reporte["results"] if r["status"] == "violado")
    assert violado["item_key"] == "table:main.EXCLUIDA"


def test_la_verificacion_queda_marcada_como_de_cierre(client, entorno, monkeypatch):
    # Sin la marca, en la línea de tiempo se confunde con una comparación que
    # pidió el operador o con la del radar automático.
    import services.dbcompare_runs as runs
    import services.dbcompare_triage as triage

    _flag(monkeypatch, True)
    viejo = _comparar()
    triage.set_decision(viejo["run_id"], "table:main.CONFIRMADA", "confirmado")

    lanzado = client.post(f"/api/db-compare/runs/{viejo['run_id']}/verify-closure")
    nuevo_id = lanzado.get_json()["verification_run_id"]
    _esperar(nuevo_id)

    assert runs.get_run(nuevo_id)["initiated_by"] == "closure"
