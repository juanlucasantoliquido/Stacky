"""Plan 176 F8 — Modo "snapshot histórico": comparar dos snapshots YA tomados.

Ver Stacky Agents/docs/176_PLAN_DB_COMPARE_TRIAGE_CURADO_GATES_READONLY_Y_VERIFICACION_DE_CIERRE.md §F8.

El punto del modo es reconstruir qué pasó entre dos fotos viejas SIN volver a
tocar la base. Si al pedir el modo histórico igual se tomara un snapshot nuevo, el
operador estaría comparando el presente creyendo que compara el pasado: por eso el
test de que NO se toma snapshot es bloqueante (KPI-5), con un `take_snapshot`
monkeypatcheado que revienta si alguien lo invoca.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest
from sqlalchemy import create_engine, text


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


def _seed_db(path: Path, with_index: bool = True):
    eng = create_engine(f"sqlite:///{path}")
    with eng.connect() as c:
        c.execute(text("CREATE TABLE padre (id INTEGER PRIMARY KEY, nombre TEXT NOT NULL)"))
        c.execute(text(
            "CREATE TABLE hija (id INTEGER PRIMARY KEY, "
            "padre_id INTEGER REFERENCES padre(id), valor REAL DEFAULT 0)"
        ))
        if with_index:
            c.execute(text("CREATE INDEX ix_hija_padre ON hija(padre_id)"))
        c.commit()
    return eng


@pytest.fixture
def two_envs(fake_keyring, tmp_path, monkeypatch):
    import services.dbcompare_registry as reg
    import services.dbcompare_runs as runs
    import services.dbcompare_snapshot as snap

    monkeypatch.setattr(reg, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(snap, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(runs, "data_dir", lambda: tmp_path)

    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    eng_a = _seed_db(db_a, with_index=True)
    eng_b = _seed_db(db_b, with_index=False)

    reg.upsert_environment("test-a", "sqlite", "localhost", 0, str(db_a), "user")
    reg.upsert_environment("test-b", "sqlite", "localhost", 0, str(db_b), "user")
    reg.set_password("test-a", "unused")
    reg.set_password("test-b", "unused")

    return {"eng_a": eng_a, "eng_b": eng_b, "tmp_path": tmp_path}


def _wait_done(runs_mod, run_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    final = runs_mod.get_run(run_id)
    while time.monotonic() < deadline:
        final = runs_mod.get_run(run_id)
        if final and final["status"] in ("done", "error"):
            return final
        time.sleep(0.05)
    return final


def _dos_snapshots(two_envs):
    import services.dbcompare_snapshot as snap

    a = snap.take_snapshot("test-a", engine=two_envs["eng_a"])
    b = snap.take_snapshot("test-b", engine=two_envs["eng_b"])
    return a["id"], b["id"]


def _explota_si_snapshotea(monkeypatch):
    """El corazón del KPI-5: si el modo histórico toca la base, este test rompe."""
    import services.dbcompare_snapshot as snap

    def _boom(*a, **k):
        raise AssertionError("el modo histórico NO debe tomar snapshots nuevos")

    monkeypatch.setattr(snap, "take_snapshot", _boom)


# ---------------------------------------------------------------------------
# Camino feliz
# ---------------------------------------------------------------------------

def test_modo_historico_usa_los_snapshots_dados_sin_tomar_nuevos(two_envs, monkeypatch):
    import services.dbcompare_runs as runs

    sid_a, sid_b = _dos_snapshots(two_envs)
    _explota_si_snapshotea(monkeypatch)

    run = runs.create_run(
        "test-a", "test-b",
        source_snapshot_id=sid_a,
        target_snapshot_id=sid_b,
    )
    final = _wait_done(runs, run["run_id"])

    assert final["status"] == "done", final
    assert final["mode"] == "snapshot"
    assert final["source_snapshot_id"] == sid_a
    assert final["target_snapshot_id"] == sid_b
    # Aserción discriminante: no alcanza con que termine, tiene que haber
    # diffeado de verdad (las dos bases difieren en un índice).
    assert final["diff"]["summary"]["objects_total"] == 2


def test_el_run_arranca_ya_con_los_ids_puestos(two_envs, monkeypatch):
    # En fresh/cached los ids se llenan sobre la marcha; acá se conocen de entrada
    # y la UI los necesita para rotular la corrida desde el primer render.
    import services.dbcompare_runs as runs

    sid_a, sid_b = _dos_snapshots(two_envs)
    _explota_si_snapshotea(monkeypatch)

    run = runs.create_run("test-a", "test-b", source_snapshot_id=sid_a, target_snapshot_id=sid_b)

    assert run["source_snapshot_id"] == sid_a
    assert run["target_snapshot_id"] == sid_b
    _wait_done(runs, run["run_id"])


def test_initiated_by_conserva_su_default(two_envs, monkeypatch):
    import services.dbcompare_runs as runs

    sid_a, sid_b = _dos_snapshots(two_envs)
    _explota_si_snapshotea(monkeypatch)

    run = runs.create_run("test-a", "test-b", source_snapshot_id=sid_a, target_snapshot_id=sid_b)
    _wait_done(runs, run["run_id"])

    assert run["initiated_by"] == "operator"


# ---------------------------------------------------------------------------
# Rechazos
# ---------------------------------------------------------------------------

def test_un_solo_id_es_error(two_envs):
    import services.dbcompare_runs as runs

    sid_a, _ = _dos_snapshots(two_envs)

    with pytest.raises(ValueError):
        runs.create_run("test-a", "test-b", source_snapshot_id=sid_a)
    with pytest.raises(ValueError):
        runs.create_run("test-a", "test-b", target_snapshot_id=sid_a)


def test_id_inexistente_es_error(two_envs):
    import services.dbcompare_runs as runs

    sid_a, _ = _dos_snapshots(two_envs)

    with pytest.raises(ValueError):
        runs.create_run("test-a", "test-b", source_snapshot_id=sid_a, target_snapshot_id="no_existe")


def test_alias_que_no_coincide_es_error(two_envs):
    # Comparar el snapshot de PROD contra sí mismo creyendo que es DEV es
    # exactamente la confusión que hace desconfiar del comparador entero.
    import services.dbcompare_runs as runs

    sid_a, sid_b = _dos_snapshots(two_envs)

    with pytest.raises(ValueError):
        runs.create_run("test-a", "test-b", source_snapshot_id=sid_b, target_snapshot_id=sid_a)


def test_el_par_queda_libre_tras_un_rechazo(two_envs):
    # Un rechazo no puede dejar el par tomado: el operador corrige el id y
    # reintenta, y se comería un 409 fantasma.
    import services.dbcompare_runs as runs

    sid_a, sid_b = _dos_snapshots(two_envs)

    with pytest.raises(ValueError):
        runs.create_run("test-a", "test-b", source_snapshot_id=sid_a, target_snapshot_id="no_existe")

    assert frozenset({"test-a", "test-b"}) not in runs._ACTIVE_PAIRS


# ---------------------------------------------------------------------------
# No regresión: sin los campos nuevos, todo igual que en main
# ---------------------------------------------------------------------------

def test_sin_los_campos_nuevos_el_comportamiento_es_el_de_siempre(two_envs):
    import services.dbcompare_runs as runs
    import services.dbcompare_snapshot as snap

    snap.take_snapshot("test-a", engine=two_envs["eng_a"])
    snap.take_snapshot("test-b", engine=two_envs["eng_b"])

    run = runs.create_run("test-a", "test-b", mode="cached")
    final = _wait_done(runs, run["run_id"])

    assert final["status"] == "done", final
    assert final["mode"] == "cached"
    assert final["source_snapshot_id"] is not None


def test_modo_desconocido_sigue_rechazandose(two_envs):
    import services.dbcompare_runs as runs

    with pytest.raises(runs.DbCompareRunError):
        runs.create_run("test-a", "test-b", mode="inventado")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@pytest.fixture
def client(two_envs, monkeypatch):
    import api.db_compare as api_mod

    monkeypatch.setenv("STACKY_DB_COMPARE_ENABLED", "true")
    import config as config_mod

    monkeypatch.setattr(config_mod.config, "STACKY_DB_COMPARE_ENABLED", True, raising=False)

    from flask import Flask

    app = Flask(__name__)
    app.register_blueprint(api_mod.bp, url_prefix="/api/db-compare")
    app.config["TESTING"] = True
    return app.test_client()


def test_api_acepta_los_dos_ids(client, two_envs, monkeypatch):
    import services.dbcompare_runs as runs

    sid_a, sid_b = _dos_snapshots(two_envs)
    _explota_si_snapshotea(monkeypatch)

    resp = client.post("/api/db-compare/compare", json={
        "source_alias": "test-a", "target_alias": "test-b",
        "source_snapshot_id": sid_a, "target_snapshot_id": sid_b,
    })

    assert resp.status_code == 202, resp.get_json()
    run = resp.get_json()["run"]
    assert run["mode"] == "snapshot"
    _wait_done(runs, run["run_id"])


def test_api_400_con_un_solo_id(client, two_envs):
    sid_a, _ = _dos_snapshots(two_envs)

    resp = client.post("/api/db-compare/compare", json={
        "source_alias": "test-a", "target_alias": "test-b", "source_snapshot_id": sid_a,
    })

    assert resp.status_code == 400, resp.get_json()


def test_api_400_con_id_inexistente(client, two_envs):
    sid_a, _ = _dos_snapshots(two_envs)

    resp = client.post("/api/db-compare/compare", json={
        "source_alias": "test-a", "target_alias": "test-b",
        "source_snapshot_id": sid_a, "target_snapshot_id": "no_existe",
    })

    assert resp.status_code == 400, resp.get_json()


def test_api_400_con_alias_cruzado(client, two_envs):
    sid_a, sid_b = _dos_snapshots(two_envs)

    resp = client.post("/api/db-compare/compare", json={
        "source_alias": "test-a", "target_alias": "test-b",
        "source_snapshot_id": sid_b, "target_snapshot_id": sid_a,
    })

    assert resp.status_code == 400, resp.get_json()


def test_api_sin_los_campos_nuevos_no_cambia(client, two_envs):
    import services.dbcompare_runs as runs

    resp = client.post("/api/db-compare/compare", json={
        "source_alias": "test-a", "target_alias": "test-b", "mode": "fresh",
    })

    assert resp.status_code == 202, resp.get_json()
    run = resp.get_json()["run"]
    assert run["mode"] == "fresh"
    _wait_done(runs, run["run_id"])
