"""Tests del T1 Golden Rules Linter — Fase 2 / P2.1."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from linters.lint_golden_rules import lint_diff
from linters.findings import Severity, is_blocking


# ── Helpers para construir diffs en tests ──────────────────────────────────

def make_diff(file_path: str, added_lines: list[str], context_before: list[str] | None = None) -> str:
    """Construye un unified diff minimal con `added_lines` agregadas a `file_path`."""
    cb = context_before or [" public class C {"]
    cb_str = "\n".join(" " + l.lstrip() if not l.startswith(" ") else l for l in cb)
    added_str = "\n".join("+" + l for l in added_lines)
    n_context = len(cb)
    n_added = len(added_lines)
    return (
        f"diff --git a/{file_path} b/{file_path}\n"
        f"--- a/{file_path}\n"
        f"+++ b/{file_path}\n"
        f"@@ -1,{n_context} +1,{n_context + n_added} @@\n"
        f"{cb_str}\n"
        f"{added_str}\n"
    )


# ── R2 — cConexion solo en Facade ─────────────────────────────────────────

class TestR2:
    def test_new_cconexion_en_bus_es_bloqueante(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSBus/Convenio.cs",
            ["    cConexion conn = new cConexion();"],
        )
        findings = lint_diff(diff, rules=["R2"])
        assert len(findings) == 1
        assert findings[0].rule_id == "R2"
        assert findings[0].severity == Severity.BLOQUEANTE
        assert is_blocking(findings)

    def test_new_cconexion_en_dalc_es_bloqueante(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSDalc/Convenio.cs",
            ["    cConexion conn = new cConexion();"],
        )
        findings = lint_diff(diff, rules=["R2"])
        assert len(findings) == 1
        assert findings[0].rule_id == "R2"

    def test_new_cconexion_en_facade_es_ok(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSFac/Convenio.cs",
            ["    cConexion conn = new cConexion();"],
        )
        findings = lint_diff(diff, rules=["R2"])
        assert len(findings) == 0

    def test_new_cconexion_en_orquestador_batch_ok(self):
        diff = make_diff(
            "trunk/Batch/RSProcIN/Program.cs",
            ["    cConexion conn = new cConexion();"],
        )
        findings = lint_diff(diff, rules=["R2"])
        assert len(findings) == 0

    def test_new_cconexion_en_motor_batch_ok(self):
        diff = make_diff(
            "trunk/Batch/Motor/MotorRS.cs",
            ["    cConexion conn = new cConexion();"],
        )
        findings = lint_diff(diff, rules=["R2"])
        assert len(findings) == 0

    def test_disable_inline_suprime_finding(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSBus/Convenio.cs",
            ["    cConexion conn = new cConexion(); // golden-rules-disable: R2 — bypass autorizado"],
        )
        findings = lint_diff(diff, rules=["R2"])
        assert len(findings) == 0

    def test_archivo_no_bus_ni_dalc_no_aplica(self):
        diff = make_diff(
            "trunk/OnLine/AgendaWeb/FrmConvenio.aspx.cs",
            ["    cConexion conn = new cConexion();"],
        )
        # Code-behind no es Bus/Dalc — R7 lo cubrirá; R2 no aplica acá.
        findings = lint_diff(diff, rules=["R2"])
        assert len(findings) == 0


# ── R3 — Transacciones solo en Facade ─────────────────────────────────────

class TestR3:
    def test_comienzo_transaccion_en_bus_bloqueante(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSBus/Convenio.cs",
            ["    conn.ComienzoTransaccion();"],
        )
        findings = lint_diff(diff, rules=["R3"])
        assert len(findings) == 1
        assert findings[0].rule_id == "R3"
        assert findings[0].severity == Severity.BLOQUEANTE

    def test_commit_en_dalc_bloqueante(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSDalc/Convenio.cs",
            ["    conn.CommitTransaccion();"],
        )
        findings = lint_diff(diff, rules=["R3"])
        assert len(findings) == 1
        assert findings[0].rule_id == "R3"

    def test_rollback_en_facade_ok(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSFac/Convenio.cs",
            ["    conn.RollbackTransaccion();"],
        )
        findings = lint_diff(diff, rules=["R3"])
        assert len(findings) == 0


# ── R4 — SQL parametrizado ─────────────────────────────────────────────────

class TestR4:
    def test_concatenacion_string_sql_con_variable_bloqueante(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSDalc/Cliente.cs",
            ['    string sql = "SELECT * FROM RCLIE WHERE CLCOD = \'" + codigoCliente + "\'";'],
        )
        findings = lint_diff(diff, rules=["R4"])
        assert len(findings) >= 1
        assert findings[0].rule_id == "R4"
        assert findings[0].severity == Severity.BLOQUEANTE
        assert "codigoCliente" in findings[0].fix_hint

    def test_concatenacion_con_constante_no_marca(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSDalc/Cliente.cs",
            ['    string sql = "SELECT * FROM " + Const.TABLA_CLIENTE + " WHERE 1=1";'],
        )
        findings = lint_diff(diff, rules=["R4"])
        assert len(findings) == 0

    def test_concatenacion_con_constante_mayusculas_no_marca(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSDalc/Cliente.cs",
            ['    string sql = "SELECT * FROM " + TABLA_CLIENTE + " WHERE 1=1";'],
        )
        findings = lint_diff(diff, rules=["R4"])
        assert len(findings) == 0

    def test_parametrizado_no_marca(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSDalc/Cliente.cs",
            [
                '    string sql = "SELECT * FROM RCLIE WHERE CLCOD = @p_codigo";',
                '    conn.AgregarParametro("@p_codigo", codigoCliente);',
            ],
        )
        findings = lint_diff(diff, rules=["R4"])
        assert len(findings) == 0

    def test_concat_con_request_querystring_marca(self):
        diff = make_diff(
            "trunk/OnLine/AgendaWeb/FrmFoo.aspx.cs",
            ['    string sql = "SELECT * FROM TABLA WHERE ID = " + Request.QueryString["id"];'],
        )
        findings = lint_diff(diff, rules=["R4"])
        assert len(findings) >= 1
        assert findings[0].rule_id == "R4"

    def test_disable_inline_suprime_r4(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSDalc/Cliente.cs",
            ['    string sql = "SELECT * FROM RCLIE WHERE X = \'" + var + "\'"; // golden-rules-disable: R4'],
        )
        findings = lint_diff(diff, rules=["R4"])
        assert len(findings) == 0

    def test_concat_variable_antes_del_string(self):
        # Patrón: `var + " WHERE X"` (variable antes del string SQL)
        diff = make_diff(
            "trunk/OnLine/Negocio/RSDalc/Cliente.cs",
            ['    string sql = baseQuery + " WHERE CLCOD = something";'],
        )
        findings = lint_diff(diff, rules=["R4"])
        # baseQuery no es constante (es camelCase) → debe marcar
        assert len(findings) >= 1

    def test_string_sin_keywords_sql_no_marca(self):
        diff = make_diff(
            "trunk/OnLine/AgendaWeb/FrmFoo.aspx.cs",
            ['    string mensaje = "Hola " + nombre + "!";'],
        )
        findings = lint_diff(diff, rules=["R4"])
        assert len(findings) == 0

    def test_concat_simple_string_no_sql_no_marca(self):
        # Strings de path, label, etc.
        diff = make_diff(
            "trunk/OnLine/AgendaWeb/FrmFoo.aspx.cs",
            ['    string ruta = "C:\\datos\\" + archivo + ".txt";'],
        )
        findings = lint_diff(diff, rules=["R4"])
        assert len(findings) == 0


# ── R1 — RIDIOMA ───────────────────────────────────────────────────────────

class TestR1:
    def test_error_agregar_con_literal_marca(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSBus/Convenio.cs",
            ['    Error.Agregar(Const.ERROR_VALID, "Fecha inválida", "Validacion", Const.SEVERIDAD_Baja);'],
        )
        findings = lint_diff(diff, rules=["R1"])
        assert len(findings) == 1
        assert findings[0].rule_id == "R1"
        assert findings[0].severity == Severity.BLOQUEANTE

    def test_error_agregar_con_idm_texto_no_marca(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSBus/Convenio.cs",
            ['    Error.Agregar(Const.ERROR_VALID, Idm.Texto(coMens.m0234, "Fecha inválida"), "Validacion", Const.SEVERIDAD_Baja);'],
        )
        findings = lint_diff(diff, rules=["R1"])
        assert len(findings) == 0

    def test_errores_agregarerror_con_literal_marca(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSBus/Cliente.cs",
            ['    this.Errores.AgregarError("No se encontró el cliente");'],
        )
        findings = lint_diff(diff, rules=["R1"])
        assert len(findings) == 1
        assert findings[0].rule_id == "R1"

    def test_label_text_con_literal_marca(self):
        diff = make_diff(
            "trunk/OnLine/AgendaWeb/FrmFoo.aspx.cs",
            ['    lblTitulo.Text = "Bienvenido al sistema";'],
        )
        findings = lint_diff(diff, rules=["R1"])
        assert len(findings) == 1
        assert findings[0].rule_id == "R1"

    def test_log_no_marca(self):
        # Log no es uno de los call-sites donde marcamos R1, así que naturalmente no lo cubre.
        diff = make_diff(
            "trunk/Batch/RSProcIN/Program.cs",
            ['    Log.Error("Error al procesar archivo", ex);'],
        )
        findings = lint_diff(diff, rules=["R1"])
        assert len(findings) == 0

    def test_string_vacio_no_marca(self):
        diff = make_diff(
            "trunk/OnLine/AgendaWeb/FrmFoo.aspx.cs",
            ['    lblError.Text = "";'],
        )
        findings = lint_diff(diff, rules=["R1"])
        assert len(findings) == 0

    def test_disable_inline_suprime_r1(self):
        diff = make_diff(
            "trunk/OnLine/AgendaWeb/FrmFoo.aspx.cs",
            ['    lblError.Text = "literal a propósito"; // golden-rules-disable: R1'],
        )
        findings = lint_diff(diff, rules=["R1"])
        assert len(findings) == 0

    def test_msgd_show_con_literal_marca(self):
        diff = make_diff(
            "trunk/OnLine/AgendaWeb/FrmFoo.aspx.cs",
            ['    msgd.Show("Operación completada con éxito");'],
        )
        findings = lint_diff(diff, rules=["R1"])
        assert len(findings) == 1


# ── R10 — Verificación post-query ──────────────────────────────────────────

class TestR10:
    def test_ejecutar_query_sin_verificacion_marca(self):
        # Construyo un diff donde EjecutarQuery NO tiene verificación cercana
        diff = """diff --git a/trunk/OnLine/Negocio/RSDalc/Cliente.cs b/trunk/OnLine/Negocio/RSDalc/Cliente.cs
--- a/trunk/OnLine/Negocio/RSDalc/Cliente.cs
+++ b/trunk/OnLine/Negocio/RSDalc/Cliente.cs
@@ -10,3 +10,5 @@
 public class Cliente {
+    public DataTable Get(string codigo) {
+        conn.EjecutarQuery(sql);
+        return conn.DataTable;
+    }
 }
"""
        findings = lint_diff(diff, rules=["R10"])
        assert len(findings) == 1
        assert findings[0].rule_id == "R10"
        assert findings[0].severity == Severity.ADVERTENCIA

    def test_ejecutar_query_con_verificacion_no_marca(self):
        diff = """diff --git a/trunk/OnLine/Negocio/RSDalc/Cliente.cs b/trunk/OnLine/Negocio/RSDalc/Cliente.cs
--- a/trunk/OnLine/Negocio/RSDalc/Cliente.cs
+++ b/trunk/OnLine/Negocio/RSDalc/Cliente.cs
@@ -10,3 +10,8 @@
 public class Cliente {
+    public DataTable Get(string codigo) {
+        conn.EjecutarQuery(sql);
+        if (conn.Errores.Cantidad() != 0) {
+            this.Errores = conn.Errores;
+            return null;
+        }
+        return conn.DataTable;
+    }
 }
"""
        findings = lint_diff(diff, rules=["R10"])
        assert len(findings) == 0

    def test_ejecutar_non_query_sin_verificacion_marca(self):
        diff = """diff --git a/trunk/OnLine/Negocio/RSDalc/Cliente.cs b/trunk/OnLine/Negocio/RSDalc/Cliente.cs
--- a/trunk/OnLine/Negocio/RSDalc/Cliente.cs
+++ b/trunk/OnLine/Negocio/RSDalc/Cliente.cs
@@ -10,3 +10,4 @@
 public class Cliente {
+    public void Insert() {
+        conn.EjecutarNonQuery(sql);
+    }
 }
"""
        findings = lint_diff(diff, rules=["R10"])
        assert len(findings) == 1
        assert findings[0].rule_id == "R10"

    def test_disable_inline_suprime_r10(self):
        diff = """diff --git a/trunk/OnLine/Negocio/RSDalc/Cliente.cs b/trunk/OnLine/Negocio/RSDalc/Cliente.cs
--- a/trunk/OnLine/Negocio/RSDalc/Cliente.cs
+++ b/trunk/OnLine/Negocio/RSDalc/Cliente.cs
@@ -10,3 +10,4 @@
 public class Cliente {
+    public void Insert() {
+        conn.EjecutarNonQuery(sql); // golden-rules-disable: R10
+    }
 }
"""
        findings = lint_diff(diff, rules=["R10"])
        assert len(findings) == 0


# ── Tests transversales ────────────────────────────────────────────────────

class TestRulesFiltering:
    def test_aplicar_solo_un_subset_de_reglas(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSBus/Convenio.cs",
            [
                '    cConexion conn = new cConexion();',
                '    conn.ComienzoTransaccion();',
            ],
        )
        # Solo R2 → ignora R3
        findings = lint_diff(diff, rules=["R2"])
        assert all(f.rule_id == "R2" for f in findings)
        assert len(findings) == 1

        # Solo R3 → ignora R2
        findings = lint_diff(diff, rules=["R3"])
        assert all(f.rule_id == "R3" for f in findings)
        assert len(findings) == 1

    def test_findings_ordenados_por_archivo_y_linea(self):
        diff_a = make_diff(
            "trunk/OnLine/Negocio/RSBus/A.cs",
            ['    cConexion conn = new cConexion();'],
        )
        diff_b = make_diff(
            "trunk/OnLine/Negocio/RSBus/B.cs",
            ['    cConexion conn = new cConexion();'],
        )
        findings = lint_diff(diff_a + diff_b, rules=["R2"])
        assert len(findings) == 2
        assert findings[0].file < findings[1].file


class TestFindingShape:
    def test_finding_to_dict(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSBus/Convenio.cs",
            ["    cConexion conn = new cConexion();"],
        )
        findings = lint_diff(diff, rules=["R2"])
        d = findings[0].to_dict()
        assert d["rule_id"] == "R2"
        assert d["severity"] == "BLOQUEANTE"
        assert d["file"].endswith("Convenio.cs")
        assert d["anchor"] == "core_rules.md#r2-cconexion-facade"
        assert "fix_hint" in d


class TestCLI:
    def test_cli_exit_code_1_si_bloqueante(self, monkeypatch, capsys):
        from linters.lint_golden_rules import main
        diff = make_diff(
            "trunk/OnLine/Negocio/RSBus/Convenio.cs",
            ["    cConexion conn = new cConexion();"],
        )
        monkeypatch.setattr("sys.stdin", _StdinFake(diff))
        result = main(["--format", "json"])
        assert result == 1

    def test_cli_exit_code_0_sin_findings(self, monkeypatch):
        from linters.lint_golden_rules import main
        diff = make_diff(
            "trunk/OnLine/Negocio/RSFac/Convenio.cs",
            ["    cConexion conn = new cConexion();"],
        )
        monkeypatch.setattr("sys.stdin", _StdinFake(diff))
        result = main(["--format", "json"])
        assert result == 0


class _StdinFake:
    def __init__(self, content): self._c = content
    def read(self): return self._c
