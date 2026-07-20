"""Plan 122 F3 — Snapshot canónico de esquema (services/dbcompare_snapshot.py).

Ver Stacky Agents/docs/122_PLAN_DB_COMPARE_NUCLEO_AMBIENTES_CONEXION_READONLY_Y_SNAPSHOT.md
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest
from sqlalchemy import create_engine, text


@pytest.fixture
def fake_keyring(monkeypatch, tmp_path):
    import services.dbcompare_registry as reg

    store: dict[tuple[str, str], str] = {}

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
    monkeypatch.setattr(reg, "data_dir", lambda: tmp_path)
    return store


def _seed_engine(db_path: Path):
    eng = create_engine(f"sqlite:///{db_path}")
    with eng.connect() as c:
        c.execute(text("CREATE TABLE padre (id INTEGER PRIMARY KEY, nombre TEXT NOT NULL)"))
        c.execute(text(
            "CREATE TABLE hija (id INTEGER PRIMARY KEY, "
            "padre_id INTEGER REFERENCES padre(id), valor REAL DEFAULT 0)"
        ))
        c.execute(text("CREATE INDEX ix_hija_padre ON hija(padre_id)"))
        c.execute(text("CREATE VIEW v_padre AS SELECT id, nombre FROM padre"))
        c.commit()
    return eng


@pytest.fixture
def seeded_env(fake_keyring, tmp_path):
    import services.dbcompare_registry as reg

    db_path = tmp_path / "seed.db"
    eng = _seed_engine(db_path)
    reg.upsert_environment("test-snap", "sqlite", "localhost", 0, str(db_path), "user")
    reg.set_password("test-snap", "unused")
    return eng, db_path


def test_snapshot_estructura_v1(seeded_env, monkeypatch):
    from services import dbcompare_snapshot as snap

    import config  # Plan 179: este test es el golden del SHAPE v1; se pinea la flag OFF.
    monkeypatch.setattr(config.config, "STACKY_DB_COMPARE_SNAPSHOT_V2_ENABLED", False, raising=False)
    monkeypatch.setattr(snap, "data_dir", lambda: seeded_env[1].parent)
    eng, _ = seeded_env
    result = snap.take_snapshot("test-snap", engine=eng)

    assert result["version"] == 1
    assert result["alias"] == "test-snap"
    assert result["engine"] == "sqlite"
    assert set(result.keys()) >= {
        "version", "id", "alias", "engine", "taken_at", "duration_ms",
        "schemas", "counts", "content_hash",
    }
    assert result["counts"]["tables"] == 2
    assert result["counts"]["views"] == 1
    main = result["schemas"]["main"]
    assert set(main["tables"]["padre"]["primary_key"]["columns"]) == {"id"}
    assert main["tables"]["hija"]["foreign_keys"][0]["referred_table"] == "padre"
    assert main["tables"]["hija"]["indexes"][0]["name"] == "ix_hija_padre"
    assert main["views"]["v_padre"]["definition_sha256"] is not None


def test_snapshot_determinista(seeded_env, monkeypatch):
    from services import dbcompare_snapshot as snap

    monkeypatch.setattr(snap, "data_dir", lambda: seeded_env[1].parent)
    eng, _ = seeded_env
    s1 = snap.take_snapshot("test-snap", engine=eng)
    s2 = snap.take_snapshot("test-snap", engine=eng)
    assert s1["content_hash"] == s2["content_hash"]
    assert s1["id"] != s2["id"]


def test_snapshot_detecta_cambio(seeded_env, monkeypatch):
    from services import dbcompare_snapshot as snap

    monkeypatch.setattr(snap, "data_dir", lambda: seeded_env[1].parent)
    eng, _ = seeded_env
    s1 = snap.take_snapshot("test-snap", engine=eng)
    with eng.connect() as c:
        c.execute(text("ALTER TABLE padre ADD COLUMN extra TEXT"))
        c.commit()
    s2 = snap.take_snapshot("test-snap", engine=eng)
    assert s1["content_hash"] != s2["content_hash"]


def test_snapshot_id_colision_mismo_segundo(seeded_env, tmp_path, monkeypatch):
    from services import dbcompare_snapshot as snap

    monkeypatch.setattr(snap, "data_dir", lambda: tmp_path)
    same_ts = datetime(2026, 7, 12, 14, 0, 0, tzinfo=timezone.utc)
    id1 = snap._next_snapshot_id("test-snap", same_ts)
    # simular que id1 ya fue persistido en disco antes de pedir el siguiente
    snap_dir = tmp_path / snap._SNAPSHOTS_DIRNAME / "test-snap"
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / f"{id1}.json").write_text("{}", encoding="utf-8")
    id2 = snap._next_snapshot_id("test-snap", same_ts)
    assert id2 != id1
    assert id2 == f"{id1}_2"
    (snap_dir / f"{id2}.json").write_text("{}", encoding="utf-8")
    id3 = snap._next_snapshot_id("test-snap", same_ts)
    assert id3 == f"{id1}_3"


def test_prune_mantiene_max(seeded_env, monkeypatch):
    from services import dbcompare_snapshot as snap

    monkeypatch.setattr(snap, "data_dir", lambda: seeded_env[1].parent)
    eng, _ = seeded_env
    for _ in range(22):
        snap.take_snapshot("test-snap", engine=eng)
    remaining = snap.list_snapshots("test-snap")
    assert len(remaining) == 20


def test_view_definition_error_no_rompe(seeded_env, monkeypatch):
    from services import dbcompare_snapshot as snap
    from sqlalchemy.engine import Inspector

    monkeypatch.setattr(snap, "data_dir", lambda: seeded_env[1].parent)

    def _boom(self, view_name, schema=None, **kw):
        raise RuntimeError("no se pudo leer la definición")

    monkeypatch.setattr(Inspector, "get_view_definition", _boom)
    eng, _ = seeded_env
    result = snap.take_snapshot("test-snap", engine=eng)
    view = result["schemas"]["main"]["views"]["v_padre"]
    assert view["definition"] is None
    assert view["error"] is not None


def test_sequences_ordenadas(seeded_env, monkeypatch):
    from services import dbcompare_snapshot as snap
    from sqlalchemy.engine import Inspector

    monkeypatch.setattr(snap, "data_dir", lambda: seeded_env[1].parent)
    monkeypatch.setattr(
        Inspector, "get_sequence_names", lambda self, schema=None, **kw: ["z_seq", "a_seq", "m_seq"]
    )
    eng, _ = seeded_env
    result = snap.take_snapshot("test-snap", engine=eng)
    assert result["schemas"]["main"]["sequences"] == ["a_seq", "m_seq", "z_seq"]

    result2 = snap.take_snapshot("test-snap", engine=eng)
    assert result["content_hash"] == result2["content_hash"]
