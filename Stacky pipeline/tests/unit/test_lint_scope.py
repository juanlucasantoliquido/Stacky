"""Tests T8 Scope Guard — Fase 2 / P2.4."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from linters.lint_scope import lint_scope
from linters.findings import Severity


def make_diff(file_path: str, added: list[str] | None = None) -> str:
    added = added or ["    nueva linea"]
    return (
        f"diff --git a/{file_path} b/{file_path}\n"
        f"--- a/{file_path}\n"
        f"+++ b/{file_path}\n"
        f"@@ -1,1 +1,{1 + len(added)} @@\n"
        f" existente\n"
        + "\n".join("+" + l for l in added) + "\n"
    )


class TestInScope:
    def test_archivo_en_scope_no_marca(self):
        diff = make_diff("trunk/OnLine/Negocio/RSFac/Cliente.cs")
        tareas = """
# Tareas

Modificar `trunk/OnLine/Negocio/RSFac/Cliente.cs` para agregar X.
"""
        assert lint_scope(diff, tareas) == []

    def test_archivo_en_scope_por_basename_no_marca(self):
        diff = make_diff("trunk/OnLine/Negocio/RSFac/Cliente.cs")
        # TAREAS menciona solo el basename, sin path
        tareas = """
# Tareas

Modificar `Cliente.cs` para validar.
"""
        assert lint_scope(diff, tareas) == []

    def test_path_con_backslash_match(self):
        diff = make_diff("trunk\\OnLine\\Negocio\\RSFac\\Cliente.cs")
        tareas = "Modificar `trunk/OnLine/Negocio/RSFac/Cliente.cs`."
        assert lint_scope(diff, tareas) == []


class TestOutOfScope:
    def test_archivo_fuera_de_scope_marca_advertencia(self):
        diff = make_diff("trunk/OnLine/Negocio/RSDalc/Cliente.cs")
        tareas = "Modificar `trunk/OnLine/Negocio/RSFac/Cliente.cs`."
        findings = lint_scope(diff, tareas)
        assert len(findings) == 1
        assert findings[0].rule_id == "R9-SCOPE"
        assert findings[0].severity == Severity.ADVERTENCIA

    def test_multiples_archivos_fuera_no_pasa_umbral(self):
        diff = (
            make_diff("trunk/OnLine/Negocio/RSDalc/A.cs")
            + make_diff("trunk/OnLine/Negocio/RSDalc/B.cs")
            + make_diff("trunk/OnLine/Negocio/RSDalc/C.cs")
        )
        tareas = "Modificar `trunk/OnLine/Negocio/RSFac/Cliente.cs`."
        findings = lint_scope(diff, tareas)
        # 3 ADVERTENCIAS, ningún BLOQUEANTE
        assert len(findings) == 3
        assert all(f.severity == Severity.ADVERTENCIA for f in findings)

    def test_mas_de_3_archivos_fuera_genera_bloqueante(self):
        diff = (
            make_diff("trunk/OnLine/Negocio/RSDalc/A.cs")
            + make_diff("trunk/OnLine/Negocio/RSDalc/B.cs")
            + make_diff("trunk/OnLine/Negocio/RSDalc/C.cs")
            + make_diff("trunk/OnLine/Negocio/RSDalc/D.cs")
        )
        tareas = "Modificar `trunk/OnLine/Negocio/RSFac/Cliente.cs`."
        findings = lint_scope(diff, tareas)
        # 4 ADVERTENCIAS + 1 BLOQUEANTE de resumen
        bloqueantes = [f for f in findings if f.severity == Severity.BLOQUEANTE]
        assert len(bloqueantes) == 1


class TestExclusiones:
    def test_archivo_designer_cs_no_cuenta(self):
        diff = make_diff("trunk/OnLine/AgendaWeb/FrmFoo.aspx.Designer.cs")
        tareas = "Modificar nada."
        # Designer.cs está excluido — no se marca como out-of-scope
        findings = lint_scope(diff, tareas)
        assert len(findings) == 0

    def test_archivo_test_excluido(self):
        diff = make_diff("trunk/OnLine/Tests/FooTest.cs")
        tareas = "Modificar nada."
        findings = lint_scope(diff, tareas)
        assert len(findings) == 0

    def test_archivo_maestro_ridioma_excluido(self):
        diff = make_diff("trunk/BD/1 - Inicializacion BD/600804 - Inserts RIDIOMA.sql")
        tareas = "Modificar nada (no menciona RIDIOMA explícitamente)."
        findings = lint_scope(diff, tareas)
        assert len(findings) == 0


class TestOverride:
    def test_override_global_no_genera_bloqueante(self):
        diff = (
            make_diff("trunk/OnLine/Negocio/RSDalc/A.cs")
            + make_diff("trunk/OnLine/Negocio/RSDalc/B.cs")
            + make_diff("trunk/OnLine/Negocio/RSDalc/C.cs")
            + make_diff("trunk/OnLine/Negocio/RSDalc/D.cs")
        )
        tareas = """
Modificar `trunk/OnLine/Negocio/RSFac/Cliente.cs`.

# scope-override: refactor cross-cutting autorizado por PM
"""
        findings = lint_scope(diff, tareas)
        # Las ADVERTENCIAS por archivo siguen apareciendo, pero el BLOQUEANTE de resumen no
        bloqueantes = [f for f in findings if f.severity == Severity.BLOQUEANTE]
        assert len(bloqueantes) == 0


class TestEdge:
    def test_tareas_vacio_no_marca(self):
        diff = make_diff("trunk/OnLine/Foo.cs")
        findings = lint_scope(diff, "")
        assert findings == []

    def test_diff_vacio_no_marca(self):
        findings = lint_scope("", "Modificar `Foo.cs`.")
        assert findings == []
