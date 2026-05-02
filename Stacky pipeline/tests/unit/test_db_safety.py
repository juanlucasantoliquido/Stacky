"""
Tests para safety.db_safety — T4 DB Safety Wrapper.

Cobertura: SELECT ok, WITH ok, DML rechazado, comentarios, múltiples statements,
EXEC rechazado, force_allow_dml, verbos desconocidos, SQL vacío.
"""

from __future__ import annotations

import pytest
import sys
import os

# Asegurar que el pipeline root está en el path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from safety.db_safety import is_safe_sql, SqlSafetyDecision


# ── SELECT ────────────────────────────────────────────────────────────────────


def test_select_simple_allowed():
    d = is_safe_sql("SELECT * FROM RCLIE WHERE CLEMPRESA = '01'")
    assert d.allowed is True
    assert d.verb == "SELECT"
    assert d.reason == "OK"


def test_select_multiline_allowed():
    sql = """
    SELECT
        CLNOMBRE,
        CLEMPRESA
    FROM RCLIE
    WHERE CLEMPRESA = '01'
    """
    d = is_safe_sql(sql)
    assert d.allowed is True
    assert d.verb == "SELECT"


def test_select_with_join_allowed():
    sql = "SELECT a.CLNOMBRE, b.DGVALOR FROM RCLIE a JOIN RDEUDA b ON a.CLID = b.DLID"
    d = is_safe_sql(sql)
    assert d.allowed is True


# ── WITH (CTE) ────────────────────────────────────────────────────────────────


def test_with_cte_allowed():
    sql = """
    WITH CTE AS (
        SELECT CLID, CLNOMBRE FROM RCLIE WHERE CLEMPRESA = '01'
    )
    SELECT * FROM CTE
    """
    d = is_safe_sql(sql)
    assert d.allowed is True
    assert d.verb == "WITH"


def test_with_in_allowed_list():
    d = is_safe_sql("WITH x AS (SELECT 1) SELECT * FROM x", allowed=("SELECT", "WITH"))
    assert d.allowed is True


# ── DML rechazado ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "sql,expected_verb",
    [
        ("UPDATE RCLIE SET CLNOMBRE = 'X' WHERE CLID = 1", "UPDATE"),
        ("INSERT INTO RCLIE (CLID) VALUES (1)", "INSERT"),
        ("DELETE FROM RCLIE WHERE CLID = 1", "DELETE"),
        ("MERGE RCLIE USING ...", "MERGE"),
        ("TRUNCATE TABLE RCLIE", "TRUNCATE"),
        ("DROP TABLE RCLIE", "DROP"),
        ("ALTER TABLE RCLIE ADD COLUMN X INT", "ALTER"),
        ("CREATE TABLE TMP (ID INT)", "CREATE"),
        ("EXEC sp_refreshview 'RCLIE'", "EXEC"),
        ("EXECUTE sp_executesql N'SELECT 1'", "EXECUTE"),
        ("GRANT SELECT ON RCLIE TO PUBLIC", "GRANT"),
        ("REVOKE SELECT ON RCLIE FROM PUBLIC", "REVOKE"),
        ("DENY SELECT ON RCLIE TO PUBLIC", "DENY"),
    ],
)
def test_dml_rejected(sql: str, expected_verb: str):
    d = is_safe_sql(sql)
    assert d.allowed is False
    assert d.verb == expected_verb
    assert "DML prohibido" in d.reason or "prohibido" in d.reason.lower()


# ── Comentarios no engañan al parser ──────────────────────────────────────────


def test_line_comment_before_select():
    sql = "-- UPDATE RCLIE SET ...\nSELECT * FROM RCLIE"
    d = is_safe_sql(sql)
    assert d.allowed is True
    assert d.verb == "SELECT"


def test_block_comment_before_select():
    sql = "/* UPDATE RCLIE */ SELECT * FROM RCLIE"
    d = is_safe_sql(sql)
    assert d.allowed is True
    assert d.verb == "SELECT"


def test_block_comment_hides_select_shows_update():
    sql = "/* SELECT * FROM X */ UPDATE RCLIE SET CLNOMBRE = 'X'"
    d = is_safe_sql(sql)
    assert d.allowed is False
    assert d.verb == "UPDATE"


def test_nested_comment_injection():
    """Intento de inyectar DML ocultándolo en comentario."""
    sql = "SELECT * FROM RCLIE /* ; DROP TABLE RCLIE */ WHERE CLID = 1"
    d = is_safe_sql(sql)
    assert d.allowed is True


# ── Múltiples statements ──────────────────────────────────────────────────────


def test_multiple_selects_allowed():
    sql = "SELECT 1; SELECT 2; SELECT 3"
    d = is_safe_sql(sql)
    assert d.allowed is True


def test_select_then_dml_rejected():
    sql = "SELECT * FROM RCLIE; DELETE FROM RCLIE WHERE CLID = 1"
    d = is_safe_sql(sql)
    assert d.allowed is False
    assert d.verb == "DELETE"


def test_dml_then_select_rejected():
    sql = "DROP TABLE TMP; SELECT * FROM RCLIE"
    d = is_safe_sql(sql)
    assert d.allowed is False
    assert d.verb == "DROP"


# ── Allowlist configurable ────────────────────────────────────────────────────


def test_custom_allowlist_blocks_select():
    d = is_safe_sql("SELECT * FROM RCLIE", allowed=("WITH",))
    assert d.allowed is False


def test_custom_allowlist_permits_with():
    d = is_safe_sql("WITH x AS (SELECT 1) SELECT * FROM x", allowed=("WITH", "SELECT"))
    assert d.allowed is True


# ── force_allow_dml ───────────────────────────────────────────────────────────


def test_force_allow_dml_without_actor_rejected():
    d = is_safe_sql("DELETE FROM TMP", force_allow_dml=True, actor=None)
    assert d.allowed is False
    assert "actor" in d.reason.lower()


def test_force_allow_dml_with_actor_allowed():
    d = is_safe_sql(
        "DELETE FROM TMP WHERE ID = 999",
        force_allow_dml=True,
        actor="DevPacifico",
    )
    assert d.allowed is True


# ── SQL vacío ────────────────────────────────────────────────────────────────


def test_empty_sql():
    d = is_safe_sql("")
    assert d.allowed is False


def test_whitespace_only_sql():
    d = is_safe_sql("   \n   ")
    assert d.allowed is False


# ── Normalized SQL ────────────────────────────────────────────────────────────


def test_normalized_sql_strips_comments():
    sql = "-- comentario\nSELECT * FROM RCLIE /* inline */"
    d = is_safe_sql(sql)
    assert "--" not in d.normalized_sql
    assert "/*" not in d.normalized_sql


# ── Statements detectados ────────────────────────────────────────────────────


def test_statements_list_populated():
    sql = "SELECT 1; SELECT 2"
    d = is_safe_sql(sql)
    assert len(d.statements) == 2


def test_single_statement_list():
    sql = "SELECT * FROM RCLIE"
    d = is_safe_sql(sql)
    assert len(d.statements) == 1
