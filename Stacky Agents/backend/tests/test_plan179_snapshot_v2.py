"""Plan 179 — Fidelidad Snapshot v2 (tipos exactos + defaults normalizados).

Cubre F0 (flag), F1 (derivación pura de type_detail), F2 (captura gated) y
F4 (golden E2E sqlite). Ver
Stacky Agents/docs/179_PLAN_FIDELIDAD_SNAPSHOT_V2_*.md
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest
from sqlalchemy import create_engine, text

FLAG = "STACKY_DB_COMPARE_SNAPSHOT_V2_ENABLED"


# ---------------------------------------------------------------------------
# F0 — Flag, config y categoría
# ---------------------------------------------------------------------------

def test_flag_registrada_bool_default_on_requires_master():
    from services import harness_flags as hf

    spec = next((s for s in hf.FLAG_REGISTRY if s.key == FLAG), None)
    assert spec is not None, "FlagSpec de Plan 179 no registrada"
    assert spec.type == "bool"
    assert spec.default is True
    assert spec.requires == "STACKY_DB_COMPARE_ENABLED"


def test_flag_en_categoria_comparador_bd():
    from services import harness_flags as hf

    assert hf.categorize(FLAG) == "comparador_bd"


def test_config_attr_existe_bool():
    import config

    assert isinstance(getattr(config.config, FLAG), bool)


# ---------------------------------------------------------------------------
# F1 — Derivación pura de type_detail
# ---------------------------------------------------------------------------

class FakeType:
    """Tipo SQLAlchemy fake: str configurable + atributos opcionales."""

    def __init__(self, s, **attrs):
        self._s = s
        for k, v in attrs.items():
            setattr(self, k, v)

    def __str__(self):
        return self._s


def test_derive_numeric_precision_scale():
    from services import dbcompare_snapshot as snap

    col = {"name": "importe", "type": FakeType("NUMERIC(10, 2)", precision=10, scale=2)}
    td = snap.derive_type_detail(col)
    assert td["base"] == "NUMERIC"
    assert td["precision"] == 10
    assert td["scale"] == 2
    assert td["length"] is None
    assert td["collation"] is None


def test_derive_varchar_length_collation():
    from services import dbcompare_snapshot as snap

    col = {"name": "nombre", "type": FakeType("VARCHAR(50)", length=50, collation="Modern_Spanish_CI_AS")}
    td = snap.derive_type_detail(col)
    assert td["base"] == "VARCHAR"
    assert td["length"] == 50
    assert td["collation"] == "Modern_Spanish_CI_AS"
    assert td["precision"] is None


def test_derive_identity_dict():
    from services import dbcompare_snapshot as snap

    col = {"name": "id", "type": FakeType("INTEGER"), "identity": {"start": 1, "increment": 1}}
    td = snap.derive_type_detail(col)
    assert td["identity"] == {"start": 1, "increment": 1}


def test_derive_computed_hashea_sqltext_normalizado():
    from services import dbcompare_snapshot as snap

    col_a = {"name": "c", "type": FakeType("INTEGER"), "computed": {"sqltext": "a + b", "persisted": True}}
    col_b = {"name": "c", "type": FakeType("INTEGER"), "computed": {"sqltext": "A  +   B", "persisted": True}}
    td_a = snap.derive_type_detail(col_a)
    td_b = snap.derive_type_detail(col_b)
    assert td_a["computed"]["sqltext_sha256"] == td_b["computed"]["sqltext_sha256"]
    assert td_a["computed"]["persisted"] is True


def test_derive_sin_atributos_todo_null():
    from services import dbcompare_snapshot as snap

    col = {"name": "x", "type": FakeType("TEXT")}
    td = snap.derive_type_detail(col)
    assert td["base"] == "TEXT"
    for k in ("precision", "scale", "length", "collation", "timezone", "identity", "computed"):
        assert td[k] is None, f"{k} debería ser None en tipo opaco"


def test_derive_keys_estables():
    from services import dbcompare_snapshot as snap

    col = {"name": "x", "type": FakeType("NUMERIC(10,2)", precision=10, scale=2)}
    td = snap.derive_type_detail(col)
    assert set(td.keys()) == set(snap.TYPE_DETAIL_KEYS)


# ---------------------------------------------------------------------------
# Fixtures sqlite (carril test-*, igual que test_plan122_dbcompare_snapshot)
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_keyring(monkeypatch, tmp_path):
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
    monkeypatch.setattr(reg, "data_dir", lambda: tmp_path)
    return store


def _snap_from_ddl(monkeypatch, tmp_path, alias, ddl):
    """Crea un sqlite con `ddl`, registra el alias y toma un snapshot."""
    import services.dbcompare_registry as reg
    from services import dbcompare_snapshot as snap

    monkeypatch.setattr(snap, "data_dir", lambda: tmp_path)
    db_path = tmp_path / f"{alias}.db"
    eng = create_engine(f"sqlite:///{db_path}")
    with eng.connect() as c:
        for stmt in ddl:
            c.execute(text(stmt))
        c.commit()
    reg.upsert_environment(alias, "sqlite", "localhost", 0, str(db_path), "user")
    reg.set_password(alias, "unused")
    return snap.take_snapshot(alias, engine=eng)


def _set_flag(monkeypatch, value):
    import config

    monkeypatch.setattr(config.config, FLAG, value, raising=False)


# ---------------------------------------------------------------------------
# F2 — Captura gated
# ---------------------------------------------------------------------------

def test_off_byte_identico_a_v1(fake_keyring, tmp_path, monkeypatch):
    _set_flag(monkeypatch, False)
    result = _snap_from_ddl(
        monkeypatch, tmp_path, "test-off",
        ["CREATE TABLE t (importe NUMERIC(10,2), nombre VARCHAR(50))"],
    )
    assert result["version"] == 1
    cols = result["schemas"]["main"]["tables"]["t"]["columns"]
    for c in cols:
        assert set(c.keys()) == {"name", "type", "nullable", "default", "autoincrement"}


def test_on_version_2_y_type_detail(fake_keyring, tmp_path, monkeypatch):
    from services import dbcompare_snapshot as snap

    _set_flag(monkeypatch, True)
    result = _snap_from_ddl(
        monkeypatch, tmp_path, "test-on",
        ["CREATE TABLE t (importe NUMERIC(10,2), nombre VARCHAR(50))"],
    )
    assert result["version"] == 2
    cols = {c["name"]: c for c in result["schemas"]["main"]["tables"]["t"]["columns"]}
    for c in cols.values():
        assert "type_detail" in c
        assert set(c["type_detail"].keys()) == set(snap.TYPE_DETAIL_KEYS)
    assert cols["importe"]["type_detail"]["precision"] == 10
    assert cols["importe"]["type_detail"]["scale"] == 2
    assert cols["nombre"]["type_detail"]["length"] == 50


def test_on_content_hash_determinista(fake_keyring, tmp_path, monkeypatch):
    import services.dbcompare_registry as reg
    from services import dbcompare_snapshot as snap

    _set_flag(monkeypatch, True)
    monkeypatch.setattr(snap, "data_dir", lambda: tmp_path)
    db_path = tmp_path / "det.db"
    eng = create_engine(f"sqlite:///{db_path}")
    with eng.connect() as c:
        c.execute(text("CREATE TABLE t (importe NUMERIC(10,2))"))
        c.commit()
    reg.upsert_environment("test-det", "sqlite", "localhost", 0, str(db_path), "user")
    reg.set_password("test-det", "unused")
    s1 = snap.take_snapshot("test-det", engine=eng)
    s2 = snap.take_snapshot("test-det", engine=eng)
    assert s1["content_hash"] == s2["content_hash"]


def test_v1_persistidos_siguen_cargando(fake_keyring, tmp_path, monkeypatch):
    import json

    from services import dbcompare_snapshot as snap

    _set_flag(monkeypatch, True)
    monkeypatch.setattr(snap, "data_dir", lambda: tmp_path)
    alias = "test-legacy"
    snap_dir = tmp_path / snap._SNAPSHOTS_DIRNAME / alias
    snap_dir.mkdir(parents=True, exist_ok=True)
    legacy = {
        "version": 1,
        "id": f"{alias}_20260101T000000Z",
        "alias": alias,
        "engine": "sqlite",
        "taken_at": "2026-01-01T00:00:00Z",
        "duration_ms": 1,
        "schemas": {"main": {"tables": {}, "views": {}, "sequences": []}},
        "counts": {"tables": 0, "views": 0, "sequences": 0, "columns": 0},
        "content_hash": "deadbeef",
    }
    (snap_dir / f"{legacy['id']}.json").write_text(json.dumps(legacy), encoding="utf-8")

    listed = snap.list_snapshots(alias)
    assert len(listed) == 1
    loaded = snap.load_snapshot(legacy["id"])
    assert loaded["version"] == 1
    assert snap.latest_snapshot(alias)["id"] == legacy["id"]


# ---------------------------------------------------------------------------
# F4 — Golden E2E sqlite (DDL real → snapshot → diff)
# ---------------------------------------------------------------------------

def test_golden_e2e_precision_change(fake_keyring, tmp_path, monkeypatch):
    from services import dbcompare_diff as diff

    _set_flag(monkeypatch, True)
    a = _snap_from_ddl(monkeypatch, tmp_path, "test-p-a", ["CREATE TABLE t (importe NUMERIC(10,2))"])
    b = _snap_from_ddl(monkeypatch, tmp_path, "test-p-b", ["CREATE TABLE t (importe NUMERIC(12,4))"])
    result = diff.diff_snapshots(a, b)
    assert len(result["items"]) == 1
    it = result["items"][0]
    assert it["object_type"] == "table" and it["action"] == "changed"
    type_changes = [c for c in it["changes"] if c["kind"] == "column_type_changed"]
    assert len(type_changes) == 1
    assert type_changes[0]["detail"]["changed_fields"] == ["precision", "scale"]


def test_golden_e2e_sin_cambios_parity_100(fake_keyring, tmp_path, monkeypatch):
    from services import dbcompare_diff as diff

    _set_flag(monkeypatch, True)
    a = _snap_from_ddl(monkeypatch, tmp_path, "test-eq-a", ["CREATE TABLE t (importe NUMERIC(10,2))"])
    b = _snap_from_ddl(monkeypatch, tmp_path, "test-eq-b", ["CREATE TABLE t (importe NUMERIC(10,2))"])
    result = diff.diff_snapshots(a, b)
    assert result["items"] == []
    assert result["summary"]["parity_score"] == 100.0


def test_golden_e2e_varchar_length(fake_keyring, tmp_path, monkeypatch):
    from services import dbcompare_diff as diff

    _set_flag(monkeypatch, True)
    a = _snap_from_ddl(monkeypatch, tmp_path, "test-v-a", ["CREATE TABLE t (nombre VARCHAR(50))"])
    b = _snap_from_ddl(monkeypatch, tmp_path, "test-v-b", ["CREATE TABLE t (nombre VARCHAR(80))"])
    result = diff.diff_snapshots(a, b)
    type_changes = [c for it in result["items"] for c in it["changes"] if c["kind"] == "column_type_changed"]
    assert len(type_changes) == 1
    assert type_changes[0]["detail"]["changed_fields"] == ["length"]


def test_golden_e2e_default_normalizado(fake_keyring, tmp_path, monkeypatch):
    from services import dbcompare_diff as diff

    # v2 ON en ambos lados: CURRENT_TIMESTAMP vs current_timestamp -> 0 items.
    _set_flag(monkeypatch, True)
    a2 = _snap_from_ddl(monkeypatch, tmp_path, "test-d-a2", ["CREATE TABLE t (ts TEXT DEFAULT CURRENT_TIMESTAMP)"])
    b2 = _snap_from_ddl(monkeypatch, tmp_path, "test-d-b2", ["CREATE TABLE t (ts TEXT DEFAULT current_timestamp)"])
    res_v2 = diff.diff_snapshots(a2, b2)
    default_changes_v2 = [c for it in res_v2["items"] for c in it["changes"] if c["kind"] == "column_default_changed"]
    assert default_changes_v2 == [], "v2 debería normalizar el case del default"

    # El MISMO par capturado con flag OFF (v1) -> 1 column_default_changed.
    _set_flag(monkeypatch, False)
    a1 = _snap_from_ddl(monkeypatch, tmp_path, "test-d-a1", ["CREATE TABLE t (ts TEXT DEFAULT CURRENT_TIMESTAMP)"])
    b1 = _snap_from_ddl(monkeypatch, tmp_path, "test-d-b1", ["CREATE TABLE t (ts TEXT DEFAULT current_timestamp)"])
    res_v1 = diff.diff_snapshots(a1, b1)
    default_changes_v1 = [c for it in res_v1["items"] for c in it["changes"] if c["kind"] == "column_default_changed"]
    assert len(default_changes_v1) == 1, "v1 (main) sí ve el falso positivo cosmético"

    # v2 ON no sobre-normaliza: 0 vs 1 sigue siendo cambio real.
    _set_flag(monkeypatch, True)
    a3 = _snap_from_ddl(monkeypatch, tmp_path, "test-d-a3", ["CREATE TABLE t (n INTEGER DEFAULT 0)"])
    b3 = _snap_from_ddl(monkeypatch, tmp_path, "test-d-b3", ["CREATE TABLE t (n INTEGER DEFAULT 1)"])
    res3 = diff.diff_snapshots(a3, b3)
    default_changes3 = [c for it in res3["items"] for c in it["changes"] if c["kind"] == "column_default_changed"]
    assert len(default_changes3) == 1


def test_golden_e2e_mezcla_con_snapshot_v1_persistido(fake_keyring, tmp_path, monkeypatch):
    from services import dbcompare_diff as diff

    # A capturado con flag OFF (v1), B del mismo esquema con ON (v2).
    _set_flag(monkeypatch, False)
    a = _snap_from_ddl(monkeypatch, tmp_path, "test-mix-a", ["CREATE TABLE t (importe NUMERIC(10,2))"])
    _set_flag(monkeypatch, True)
    b = _snap_from_ddl(monkeypatch, tmp_path, "test-mix-b", ["CREATE TABLE t (importe NUMERIC(10,2))"])
    assert a["version"] == 1 and b["version"] == 2
    result = diff.diff_snapshots(a, b)
    assert result["items"] == []
