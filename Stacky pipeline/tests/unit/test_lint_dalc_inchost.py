"""Tests T9 Cross-Module Dalc Linker — Fase 2 / P2.3."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from linters.lint_dalc_inchost import (
    lint_dalc_consistency,
    load_table_to_dalc,
    DEFAULT_TABLE_TO_DALC,
)
from linters.findings import Severity


# ── Helpers ─────────────────────────────────────────────────────────────────

def make_diff(file_path: str, added: list[str], context_before: list[str] | None = None) -> str:
    cb = context_before or [" -- start"]
    cb_str = "\n".join(" " + l.lstrip() if not l.startswith(" ") else l for l in cb)
    added_str = "\n".join("+" + l for l in added)
    return (
        f"diff --git a/{file_path} b/{file_path}\n"
        f"--- a/{file_path}\n"
        f"+++ b/{file_path}\n"
        f"@@ -1,{len(cb)} +1,{len(cb) + len(added)} @@\n"
        f"{cb_str}\n"
        f"{added_str}\n"
    )


# ── Mapping ─────────────────────────────────────────────────────────────────

class TestMapping:
    def test_load_default_si_no_existe(self, tmp_path):
        m = load_table_to_dalc(str(tmp_path / "nonexistent.md"))
        assert m == DEFAULT_TABLE_TO_DALC

    def test_load_real_glossary(self):
        # Si existe el glossary del repo, debe parsear y contener al menos RCLIE
        m = load_table_to_dalc()
        assert "RCLIE" in m
        assert m["RCLIE"] == "ClientesDalc.cs"


# ── PAC-DALC-1: Dalc faltante ───────────────────────────────────────────────

class TestPacDalc1:
    def test_alter_table_sin_dalc_en_diff_marca(self):
        diff = make_diff(
            "trunk/BD/scripts/add_col.sql",
            ["ALTER TABLE RCLIE ADD COL_NUEVO VARCHAR(50);"],
        )
        findings = lint_dalc_consistency(diff)
        assert len(findings) == 1
        assert findings[0].rule_id == "PAC-DALC-1"
        assert findings[0].severity == Severity.BLOQUEANTE
        assert "ClientesDalc.cs" in findings[0].fix_hint

    def test_alter_table_no_inchost_no_marca(self):
        # Si la tabla no es Inchost (no está en el mapping), no aplica.
        diff = make_diff(
            "trunk/BD/scripts/add_col.sql",
            ["ALTER TABLE TABLA_NO_INCHOST ADD COL_NUEVO VARCHAR(50);"],
        )
        findings = lint_dalc_consistency(diff)
        assert len(findings) == 0

    def test_alter_table_diferentes_tablas(self):
        diff = (
            make_diff(
                "trunk/BD/scripts/add_col_clie.sql",
                ["ALTER TABLE RCLIE ADD COL_A VARCHAR(50);"],
            )
            + make_diff(
                "trunk/BD/scripts/add_col_oblg.sql",
                ["ALTER TABLE ROBLG ADD COL_B VARCHAR(50);"],
            )
        )
        findings = lint_dalc_consistency(diff)
        # 2 PAC-DALC-1 — uno por tabla
        assert len(findings) == 2
        assert all(f.rule_id == "PAC-DALC-1" for f in findings)


# ── PAC-DALC-2 / PAC-DALC-3: INSERT/UPDATE no incluye columna ───────────────

class TestPacDalc23:
    def test_dalc_en_diff_pero_insert_no_menciona_columna(self):
        # DDL agrega COL_NUEVO a RCLIE, ClientesDalc.cs en diff, pero
        # el INSERT no menciona COL_NUEVO.
        diff = (
            make_diff(
                "trunk/BD/scripts/add_col.sql",
                ["ALTER TABLE RCLIE ADD COL_NUEVO VARCHAR(50);"],
            )
            + make_diff(
                "trunk/Batch/Negocio/BusInchost/ClientesDalc.cs",
                [
                    'string sql = "INSERT INTO RCLIE (CLCOD, CLNOMBRE) VALUES (@p_cod, @p_nom)";',
                    'conn.AgregarParametro("@p_cod", c.Codigo);',
                    'conn.AgregarParametro("@p_nom", c.Nombre);',
                    'string sql2 = "UPDATE RCLIE SET CLNOMBRE = @p_nom WHERE CLCOD = @p_cod";',
                ],
            )
        )
        findings = lint_dalc_consistency(diff)
        rule_ids = [f.rule_id for f in findings]
        # Debería haber al menos PAC-DALC-2 (INSERT no menciona) y PAC-DALC-3 (UPDATE no menciona)
        assert "PAC-DALC-2" in rule_ids
        assert "PAC-DALC-3" in rule_ids

    def test_dalc_completo_no_marca(self):
        diff = (
            make_diff(
                "trunk/BD/scripts/add_col.sql",
                ["ALTER TABLE RCLIE ADD COL_NUEVO VARCHAR(50);"],
            )
            + make_diff(
                "trunk/Batch/Negocio/BusInchost/ClientesDalc.cs",
                [
                    'string sql = "INSERT INTO RCLIE (CLCOD, CLNOMBRE, COL_NUEVO) VALUES (@p_cod, @p_nom, @p_nuevo)";',
                    'conn.AgregarParametro("@p_cod", c.Codigo);',
                    'conn.AgregarParametro("@p_nom", c.Nombre);',
                    'conn.AgregarParametro("@p_nuevo", c.ColNuevo);',
                    'string sql2 = "UPDATE RCLIE SET CLNOMBRE = @p_nom, COL_NUEVO = @p_nuevo WHERE CLCOD = @p_cod";',
                ],
            )
        )
        findings = lint_dalc_consistency(diff)
        assert len(findings) == 0

    def test_solo_insert_no_solo_update_marca_solo_uno(self):
        diff = (
            make_diff(
                "trunk/BD/scripts/add_col.sql",
                ["ALTER TABLE RCLIE ADD COL_NUEVO VARCHAR(50);"],
            )
            + make_diff(
                "trunk/Batch/Negocio/BusInchost/ClientesDalc.cs",
                [
                    'string sql = "INSERT INTO RCLIE (CLCOD, COL_NUEVO) VALUES (@p_cod, @p_nuevo)";',
                    'string sql2 = "UPDATE RCLIE SET CLNOMBRE = @p_nom WHERE CLCOD = @p_cod";',
                ],
            )
        )
        findings = lint_dalc_consistency(diff)
        rule_ids = [f.rule_id for f in findings]
        # INSERT incluye COL_NUEVO, UPDATE no
        assert "PAC-DALC-2" not in rule_ids
        assert "PAC-DALC-3" in rule_ids


# ── Casos sin DDL ───────────────────────────────────────────────────────────

class TestNoDdl:
    def test_diff_sin_alter_no_marca(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSFac/Cliente.cs",
            ['conn.ComienzoTransaccion();'],
        )
        findings = lint_dalc_consistency(diff)
        assert len(findings) == 0
