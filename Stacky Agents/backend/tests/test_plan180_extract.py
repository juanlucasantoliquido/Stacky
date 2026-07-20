"""Plan 180 F1 — Extracción pura: ticket y tablas (reglas literales, golden).

Ver Stacky Agents/docs/180_PLAN_PUENTE_DIFF_REPO_...md §F1 (KPI-4/KPI-5).
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.dbcompare_repo_scripts import extract_tables, infer_ticket


def test_ticket_prior_art_literal():
    # KPI-4: el ticket del nombre gana; el "1" de la carpeta no (< 4 dígitos).
    p = "trunk/BD/1 - Inicializacion BD/600804 - Inserts RIDIOMA.sql"
    assert infer_ticket(p) == "600804"


def test_ticket_en_carpeta():
    assert infer_ticket("trunk/BD/601234/alta_indice.sql") == "601234"


def test_ticket_ausente_none():
    assert infer_ticket("trunk/BD/utils/helpers.sql") is None


def test_extract_todas_las_sentencias():
    # KPI-4: familias DDL/DML con identificadores calificados, brackets y comillas.
    sql = """
    CREATE TABLE dbo.T1 (id INT);
    ALTER TABLE [dbo].[T2] ADD col INT;
    INSERT INTO T3 (id) VALUES (1);
    UPDATE "T4" SET x = 1 WHERE id = 2;
    DELETE FROM db2.T5 WHERE id = 3;
    MERGE INTO T6 AS tgt USING src ON (tgt.id = src.id);
    """
    tables, qualified = extract_tables(sql)
    assert tables == ["T1", "T2", "T3", "T4", "T5", "T6"]
    assert "DBO.T1" in qualified
    assert "DBO.T2" in qualified
    assert "DB2.T5" in qualified


def test_extract_views():
    # KPI-5 (fix C5): CREATE/ALTER/CREATE OR ALTER VIEW se extraen como tabla.
    tables_alter, _ = extract_tables("ALTER VIEW dbo.VCLIENTES AS SELECT 1")
    assert "VCLIENTES" in tables_alter
    tables_coa, _ = extract_tables("CREATE OR ALTER VIEW VX AS SELECT 1")
    assert "VX" in tables_coa
    tables_create, _ = extract_tables("CREATE VIEW dbo.VOTRA AS SELECT 1")
    assert "VOTRA" in tables_create


def test_extract_ignora_comentarios():
    # KPI-4 (fix C6): sentencias dentro de comentarios NO cuentan.
    sql = """
    -- INSERT INTO FANTASMA (x) VALUES (1)
    /* UPDATE OTRA SET x = 1 */
    INSERT INTO REAL_TABLE (x) VALUES (1);
    """
    tables, _ = extract_tables(sql)
    assert "FANTASMA" not in tables
    assert "OTRA" not in tables
    assert "REAL_TABLE" in tables


def test_extract_descarta_temporales():
    tables, _ = extract_tables("INSERT INTO #tmp (x) VALUES (1); UPDATE @var SET x = 1")
    assert tables == []


def test_extract_dedup_y_orden():
    sql = "INSERT INTO ZTAB (x) VALUES (1); INSERT INTO ZTAB (x) VALUES (2); INSERT INTO ATAB (x) VALUES (3); UPDATE ZTAB SET x = 4"
    tables, _ = extract_tables(sql)
    assert tables == ["ATAB", "ZTAB"]  # dedup + orden alfabético


def test_extract_case_insensitive():
    tables, _ = extract_tables("insert into ridioma (id) values (1)")
    assert tables == ["RIDIOMA"]
