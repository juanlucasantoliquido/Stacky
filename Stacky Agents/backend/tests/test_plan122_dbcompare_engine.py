"""Plan 122 F2 — Motor de conexión read-only (services/dbcompare_engine.py).

Ver Stacky Agents/docs/122_PLAN_DB_COMPARE_NUCLEO_AMBIENTES_CONEXION_READONLY_Y_SNAPSHOT.md
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


def test_build_url_sqlserver_exacta():
    from services.dbcompare_engine import build_sqlalchemy_url

    env = {
        "engine": "sqlserver", "host": "host1", "port": 1433, "database": "RSPACIFICO",
        "username": "ro_user", "odbc_driver": "ODBC Driver 17 for SQL Server",
    }
    url = build_sqlalchemy_url(env, "s3cr3t")
    rendered = url.render_as_string(hide_password=False)
    assert rendered.startswith("mssql+pyodbc://ro_user:s3cr3t@host1:1433/RSPACIFICO")
    assert "driver=ODBC+Driver+17+for+SQL+Server" in rendered or "driver=ODBC%20Driver%2017%20for%20SQL%20Server" in rendered
    assert "TrustServerCertificate=yes" in rendered


def test_build_url_oracle_exacta():
    from services.dbcompare_engine import build_sqlalchemy_url

    env = {"engine": "oracle", "host": "host2", "port": 1521, "database": "ORCLPDB", "username": "ro_user"}
    url = build_sqlalchemy_url(env, "s3cr3t")
    rendered = url.render_as_string(hide_password=False)
    assert rendered.startswith("oracle+oracledb://ro_user:s3cr3t@host2:1521")
    assert "service_name=ORCLPDB" in rendered


def test_driver_status_reporta_hint(monkeypatch):
    import importlib.util
    from services import dbcompare_engine

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    status = dbcompare_engine.driver_status()
    assert status["sqlserver"]["available"] is False
    assert "pyodbc" in status["sqlserver"]["install_hint"]
    assert status["oracle"]["available"] is False
    assert "oracledb" in status["oracle"]["install_hint"]


def test_open_engine_sin_credencial_error_claro(fake_keyring):
    from services.dbcompare_engine import open_engine, DbCompareEngineError

    with pytest.raises(DbCompareEngineError):
        open_engine("no-existe")


def test_test_connection_sqlite_ok(fake_keyring, tmp_path):
    import services.dbcompare_registry as reg
    from services.dbcompare_engine import test_connection

    db_path = tmp_path / "x.db"
    reg.upsert_environment("test-sqlite", "sqlite", "localhost", 0, str(db_path), "user")
    reg.set_password("test-sqlite", "unused")

    result = test_connection("test-sqlite")
    assert result["ok"] is True
    assert result["latency_ms"] >= 0
    assert result["engine"] == "sqlite"


def test_error_no_filtra_password(fake_keyring, monkeypatch, tmp_path):
    import services.dbcompare_registry as reg
    from services import dbcompare_engine

    reg.upsert_environment("PACIFICO-DEV", "sqlserver", "host1", 1433, "db", "user")
    reg.set_password("PACIFICO-DEV", "s3cr3t")

    def _boom(*a, **kw):
        raise RuntimeError("login failed for user with password s3cr3t")

    monkeypatch.setattr(dbcompare_engine, "open_engine", _boom)
    result = dbcompare_engine.test_connection("PACIFICO-DEV")
    assert result["ok"] is False
    assert "s3cr3t" not in result["error"]
    assert "***" in result["error"]


def test_likely_network_clasifica():
    from services.dbcompare_engine import _classify_likely_network

    assert _classify_likely_network("Timeout expired while connecting") is True
    assert _classify_likely_network("A network-related or instance-specific error occurred") is True
    assert _classify_likely_network("Login failed for user 'ro_user'") is False
