"""Plan 122 F1 — Registro de ambientes de BD (services/dbcompare_registry.py).

Ver Stacky Agents/docs/122_PLAN_DB_COMPARE_NUCLEO_AMBIENTES_CONEXION_READONLY_Y_SNAPSHOT.md
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest


@pytest.fixture
def fake_keyring(monkeypatch, tmp_path):
    """Monkeypatch de keyring sobre un dict en memoria — mismo enfoque que Plan 91."""
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


def test_upsert_and_list_public_sin_password(fake_keyring):
    import services.dbcompare_registry as reg

    env = reg.upsert_environment(
        "PACIFICO-DEV", "sqlserver", "host1", 1433, "RSPACIFICO", "ro_user",
    )
    assert env["alias"] == "PACIFICO-DEV"
    assert "password" not in env

    envs = reg.list_environments()
    assert len(envs) == 1
    assert "password" not in envs[0]
    assert envs[0]["has_password"] is False

    # el JSON en disco tampoco tiene password
    raw = json.loads(reg._registry_path().read_text(encoding="utf-8"))
    assert all("password" not in e for e in raw)


def test_engine_invalido_rechaza(fake_keyring):
    import services.dbcompare_registry as reg

    with pytest.raises(ValueError):
        reg.upsert_environment("X", "mysql", "host1", 3306, "db", "user")


def test_alias_invalido_rechaza(fake_keyring):
    import services.dbcompare_registry as reg

    with pytest.raises(ValueError):
        reg.upsert_environment("bad alias!", "sqlserver", "host1", 1433, "db", "user")


def test_password_roundtrip_y_clear(fake_keyring):
    import services.dbcompare_registry as reg

    reg.upsert_environment("PACIFICO-DEV", "sqlserver", "host1", 1433, "db", "user")
    assert reg.has_password("PACIFICO-DEV") is False

    reg.set_password("PACIFICO-DEV", "s3cr3t")
    assert reg.has_password("PACIFICO-DEV") is True
    cred = reg.get_credential("PACIFICO-DEV")
    assert cred is not None
    assert cred["password"] == "s3cr3t"
    assert cred["alias"] == "PACIFICO-DEV"

    reg.clear_password("PACIFICO-DEV")
    assert reg.has_password("PACIFICO-DEV") is False
    assert reg.get_credential("PACIFICO-DEV") is None


def test_delete_borra_registro_y_password(fake_keyring):
    import services.dbcompare_registry as reg

    reg.upsert_environment("PACIFICO-DEV", "sqlserver", "host1", 1433, "db", "user")
    reg.set_password("PACIFICO-DEV", "s3cr3t")

    assert reg.delete_environment("PACIFICO-DEV") is True
    assert reg.get_environment("PACIFICO-DEV") is None
    assert reg.has_password("PACIFICO-DEV") is False
    assert reg.delete_environment("PACIFICO-DEV") is False  # ya no existe


def test_sqlite_solo_para_alias_test(fake_keyring):
    import services.dbcompare_registry as reg

    env = reg.upsert_environment("test-local", "sqlite", "localhost", 0, "/tmp/x.db", "user")
    assert env["engine"] == "sqlite"

    with pytest.raises(ValueError):
        reg.upsert_environment("PACIFICO-DEV", "sqlite", "host1", 0, "db", "user")


def test_touch_last_used(fake_keyring):
    import services.dbcompare_registry as reg

    reg.upsert_environment("PACIFICO-DEV", "sqlserver", "host1", 1433, "db", "user")
    assert reg.get_environment("PACIFICO-DEV")["last_used_at"] is None
    reg.touch_last_used("PACIFICO-DEV")
    assert reg.get_environment("PACIFICO-DEV")["last_used_at"] is not None
