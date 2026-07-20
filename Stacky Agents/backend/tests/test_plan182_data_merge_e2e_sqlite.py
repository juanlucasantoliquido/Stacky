"""Plan 182 F3 — Prueba reina: idempotencia E2E en sqlite de las piezas DML
(data_merge + data_update + data_delete). Doble ejecución convergente, guard
anti-no-op observable con conn.total_changes, y reparación tras alterar a mano.

Ejecuta el `sql` línea por línea salteando `--` (mismo patrón que el E2E
preexistente test_plan126_dbcompare_data_scripts.py). Fixtures SIN valores
multilínea (límite C3). Ver Stacky Agents/docs/182_PLAN_*.md #F3.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import dbcompare_scripts as scripts  # noqa: E402

TS = "20260714_120000"


def _apply(conn, sql):
    for raw in sql.splitlines():
        line = raw.strip()
        if line and not line.startswith("--"):
            conn.execute(line)
    conn.commit()


def _piece(pieces, action):
    return next((p for p in pieces if p["action"] == action), None)


def _rows(conn, sql):
    return conn.execute(sql).fetchall()


def test_doble_ejecucion_y_reparacion(tmp_path):
    db = tmp_path / "target.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE PARAMS (ID INTEGER PRIMARY KEY, NOMBRE TEXT, VALOR INTEGER)")
    conn.execute("INSERT INTO PARAMS VALUES (2, 'B', 20)")  # fila preexistente (destino)
    conn.commit()

    diff = {
        "version": 1, "schema": "main", "table": "PARAMS", "pk_cols": ["ID"],
        "columns": ["ID", "NOMBRE", "VALOR"],
        "column_types": {"ID": "INTEGER", "NOMBRE": "TEXT", "VALOR": "INTEGER"},
        "only_source": [{"ID": "1", "NOMBRE": "A", "VALOR": "10"}, {"ID": "3", "NOMBRE": "C", "VALOR": "30"}],
        "changed": [{"pk": {"ID": "2"}, "cells": {"NOMBRE": {"source": "B", "target": "B-mod"}}}],
        "only_target": [], "truncated": False,
    }
    pieces = scripts.emit_data_scripts(diff, "sqlite", TS, "TEST", data_merge_mode=True)
    merge_sql = _piece(pieces, "data_merge")["sql"]
    update_sql = _piece(pieces, "data_update")["sql"]

    _apply(conn, merge_sql)
    _apply(conn, update_sql)
    snap1 = _rows(conn, "SELECT ID, NOMBRE, VALOR FROM PARAMS ORDER BY ID")
    assert snap1 == [(1, "A", 10), (2, "B-mod", 20), (3, "C", 30)]

    # 2ª ejecución: sin cambios (anti-no-op observable) y snapshot idéntico.
    tc_before = conn.total_changes
    _apply(conn, merge_sql)
    _apply(conn, update_sql)
    assert conn.total_changes == tc_before, "la 2ª pasada re-escribió filas ya sincronizadas"
    assert _rows(conn, "SELECT ID, NOMBRE, VALOR FROM PARAMS ORDER BY ID") == snap1

    # Reparación: alterar a mano una fila sincronizada; la 3ª pasada la repara.
    conn.execute("UPDATE PARAMS SET NOMBRE='hackeado' WHERE ID=3")
    conn.commit()
    _apply(conn, merge_sql)
    assert _rows(conn, "SELECT NOMBRE FROM PARAMS WHERE ID=3") == [("C",)]
    conn.close()


def test_null_safety_e2e(tmp_path):
    db = tmp_path / "target.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE PARAMS (ID INTEGER PRIMARY KEY, NOMBRE TEXT, VALOR INTEGER)")
    conn.commit()

    diff = {
        "version": 1, "schema": "main", "table": "PARAMS", "pk_cols": ["ID"],
        "columns": ["ID", "NOMBRE", "VALOR"],
        "column_types": {"ID": "INTEGER", "NOMBRE": "TEXT", "VALOR": "INTEGER"},
        "only_source": [{"ID": "5", "NOMBRE": None, "VALOR": "50"}],
        "changed": [], "only_target": [], "truncated": False,
    }
    merge_sql = _piece(scripts.emit_data_scripts(diff, "sqlite", TS, "TEST", data_merge_mode=True), "data_merge")["sql"]

    _apply(conn, merge_sql)
    assert _rows(conn, "SELECT ID, NOMBRE, VALOR FROM PARAMS") == [(5, None, 50)]
    tc_before = conn.total_changes
    _apply(conn, merge_sql)  # NULL==NULL ⇒ el guard IS NOT no re-escribe
    assert conn.total_changes == tc_before
    assert _rows(conn, "SELECT ID, NOMBRE, VALOR FROM PARAMS") == [(5, None, 50)]
    conn.close()


def test_pk_compuesta_e2e(tmp_path):
    db = tmp_path / "target.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE T (C1 INTEGER, C2 INTEGER, V INTEGER, PRIMARY KEY (C1, C2))")
    conn.commit()

    diff = {
        "version": 1, "schema": "main", "table": "T", "pk_cols": ["C1", "C2"],
        "columns": ["C1", "C2", "V"],
        "column_types": {"C1": "INTEGER", "C2": "INTEGER", "V": "INTEGER"},
        "only_source": [{"C1": "1", "C2": "2", "V": "9"}],
        "changed": [], "only_target": [], "truncated": False,
    }
    merge_sql = _piece(scripts.emit_data_scripts(diff, "sqlite", TS, "TEST", data_merge_mode=True), "data_merge")["sql"]

    _apply(conn, merge_sql)
    assert _rows(conn, "SELECT C1, C2, V FROM T") == [(1, 2, 9)]
    tc_before = conn.total_changes
    _apply(conn, merge_sql)
    assert conn.total_changes == tc_before
    assert _rows(conn, "SELECT C1, C2, V FROM T") == [(1, 2, 9)]
    conn.close()


def test_delete_intacto_e2e(tmp_path):
    db = tmp_path / "target.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE PARAMS (ID INTEGER PRIMARY KEY, NOMBRE TEXT, VALOR INTEGER)")
    conn.execute("INSERT INTO PARAMS VALUES (7, 'G', 70)")
    conn.commit()

    diff = {
        "version": 1, "schema": "main", "table": "PARAMS", "pk_cols": ["ID"],
        "columns": ["ID", "NOMBRE", "VALOR"],
        "column_types": {"ID": "INTEGER", "NOMBRE": "TEXT", "VALOR": "INTEGER"},
        "only_source": [], "changed": [],
        "only_target": [{"ID": "7", "NOMBRE": "G", "VALOR": "70"}], "truncated": False,
    }
    delete_sql = _piece(scripts.emit_data_scripts(diff, "sqlite", TS, "TEST", data_merge_mode=True), "data_delete")["sql"]

    _apply(conn, delete_sql)
    assert _rows(conn, "SELECT COUNT(*) FROM PARAMS") == [(0,)]
    _apply(conn, delete_sql)  # re-ejecutar: 0 filas, sin error
    assert _rows(conn, "SELECT COUNT(*) FROM PARAMS") == [(0,)]
    conn.close()
