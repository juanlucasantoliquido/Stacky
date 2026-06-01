"""Tests de services.db_query (plan 16, Fase 1)."""
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


@pytest.fixture()
def env(tmp_path, monkeypatch):
    import project_manager
    import services.client_profile as cp
    import services.db_query as dbq

    projects_dir = tmp_path / "projects"
    data_dir = tmp_path / "data"
    projects_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(project_manager, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(cp, "projects_dir", lambda: projects_dir)
    monkeypatch.setattr(dbq, "data_dir", lambda: data_dir)

    return {"projects_dir": projects_dir, "data_dir": data_dir, "dbq": dbq, "cp": cp}


def _setup_project_with_db(env, *, name: str = "DEMO", with_auth: bool = True, with_profile: bool = True):
    pdir = env["projects_dir"] / name.upper()
    pdir.mkdir(parents=True, exist_ok=True)
    cfg = {"name": name.upper()}
    if with_profile:
        cfg["client_profile"] = {
            "schema_version": 1,
            "database": {
                "type": "sqlserver",
                "server": "demo.local",
                "readonly_auth_ref": "auth/db_readonly.json",
                "readonly_user_hint": "DEMOREAD",
            },
        }
    (pdir / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    if with_auth:
        auth_dir = pdir / "auth"
        auth_dir.mkdir(parents=True, exist_ok=True)
        # Stub: DPAPI no funciona en CI/Linux; sustituimos read_secret_from_file
        # con un monkeypatch para que devuelva un value no vacío.
        (auth_dir / "db_readonly.json").write_text(
            json.dumps({"password": "dummy-encrypted", "password_format": "dpapi", "user": "DEMOREAD"}),
            encoding="utf-8",
        )


def _stub_secret_resolver(monkeypatch, env, *, value: str = "plain-password"):
    """Evita la dependencia de DPAPI (que no funciona en CI/Linux)."""
    import services.db_query as dbq
    from services.secrets_store import ResolvedSecret

    def _fake(path, field, **kwargs):
        return ResolvedSecret(value=value, storage_format="dpapi")

    monkeypatch.setattr(dbq, "read_secret_from_file", _fake)


def test_select_passes(env):
    dbq = env["dbq"]
    v = dbq.validate_select_only("SELECT 1")
    assert v.ok
    assert v.statement_kind == "select"


def test_select_with_comments_passes(env):
    dbq = env["dbq"]
    sql = "-- header comment\n/* block */\nSELECT name FROM RIDIOMA WHERE id = 1"
    v = dbq.validate_select_only(sql)
    assert v.ok, v.errors
    assert v.statement_kind == "select"


def test_with_cte_passes(env):
    dbq = env["dbq"]
    sql = "WITH x AS (SELECT 1 AS a) SELECT * FROM x"
    v = dbq.validate_select_only(sql)
    assert v.ok, v.errors
    assert v.statement_kind == "with"


@pytest.mark.parametrize("statement", [
    "INSERT INTO T VALUES (1)",
    "UPDATE T SET a = 1",
    "DELETE FROM T",
    "MERGE INTO T USING S ON ...",
    "DROP TABLE T",
    "ALTER TABLE T ADD COLUMN x INT",
    "CREATE TABLE T (a INT)",
    "TRUNCATE TABLE T",
    "EXEC sp_who",
    "EXECUTE sp_who",
    "GRANT SELECT ON T TO public",
    "REVOKE SELECT ON T FROM public",
])
def test_dml_ddl_rejected(env, statement):
    dbq = env["dbq"]
    v = dbq.validate_select_only(statement)
    assert not v.ok
    assert v.errors


def test_multi_statement_rejected(env):
    dbq = env["dbq"]
    v = dbq.validate_select_only("SELECT 1; SELECT 2")
    assert not v.ok
    assert any("multi-statement" in e for e in v.errors)


def test_with_containing_insert_rejected(env):
    dbq = env["dbq"]
    sql = "WITH x AS (INSERT INTO T VALUES(1) RETURNING *) SELECT * FROM x"
    v = dbq.validate_select_only(sql)
    assert not v.ok
    assert any("mutante" in e.lower() or "insert" in e.lower() for e in v.errors)


def test_empty_query_rejected(env):
    dbq = env["dbq"]
    v = dbq.validate_select_only("")
    assert not v.ok
    v2 = dbq.validate_select_only("   \n\t  ")
    assert not v2.ok
    v3 = dbq.validate_select_only("-- only comment\n/* nothing */")
    assert not v3.ok


def test_oversized_query_rejected(env):
    dbq = env["dbq"]
    huge = "SELECT '" + ("a" * 70_000) + "'"
    v = dbq.validate_select_only(huge)
    assert not v.ok


def test_execute_logs_rejected_dml(env, monkeypatch):
    dbq = env["dbq"]
    _setup_project_with_db(env, with_auth=True, with_profile=True)
    _stub_secret_resolver(monkeypatch, env)
    with pytest.raises(dbq.DbQueryError):
        dbq.execute_query(project="DEMO", ticket_id=42, sql="DELETE FROM T")
    audit = dbq.list_audit_events(ticket_id=42)
    assert len(audit) == 1
    assert audit[0]["result"] == "rejected"
    assert audit[0]["ticket_id"] == 42


def test_execute_logs_missing_credentials(env, monkeypatch):
    dbq = env["dbq"]
    _setup_project_with_db(env, with_auth=False, with_profile=True)
    with pytest.raises(dbq.DbQueryError):
        dbq.execute_query(project="DEMO", ticket_id="t1", sql="SELECT 1")
    audit = dbq.list_audit_events(ticket_id="t1")
    assert len(audit) == 1
    assert audit[0]["result"] == "missing_credentials"


def test_execute_would_execute_when_all_ok(env, monkeypatch):
    dbq = env["dbq"]
    _setup_project_with_db(env, with_auth=True, with_profile=True)
    _stub_secret_resolver(monkeypatch, env)
    result = dbq.execute_query(project="DEMO", ticket_id=7, sql="SELECT name FROM RIDIOMA WHERE id = 1")
    assert result["ok"] is True
    assert result["would_execute"] is True
    assert result["statement_kind"] == "select"
    assert result["dialect"] == "sqlserver"
    assert result["server"] == "demo.local"
    audit = dbq.list_audit_events(ticket_id=7)
    assert len(audit) == 1
    assert audit[0]["result"] == "would_execute"
    # El password NUNCA debe aparecer en el audit log.
    raw = json.dumps(audit[0])
    assert "plain-password" not in raw


def test_list_audit_filters_by_project(env, monkeypatch):
    dbq = env["dbq"]
    _setup_project_with_db(env, name="DEMO", with_auth=True, with_profile=True)
    _setup_project_with_db(env, name="OTHER", with_auth=True, with_profile=True)
    _stub_secret_resolver(monkeypatch, env)
    dbq.execute_query(project="DEMO", ticket_id=1, sql="SELECT 1")
    dbq.execute_query(project="OTHER", ticket_id=2, sql="SELECT 2")

    demo_events = dbq.list_audit_events(project="DEMO")
    other_events = dbq.list_audit_events(project="OTHER")
    assert len(demo_events) == 1
    assert len(other_events) == 1
    assert demo_events[0]["project"] == "DEMO"
    assert other_events[0]["project"] == "OTHER"
