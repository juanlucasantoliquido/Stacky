"""Tests del hook pre-commit de trazabilidad ADO — Fase 1 / P1.5."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))

from pre_commit_traceability import (
    TRACEABILITY_RE,
    _is_relevant_file,
    _parse_diff,
    _has_substantive_changes,
    _has_traceability,
    _Hunk,
)


class TestRegexTrazabilidad:
    def test_matches_format_canonico(self):
        assert TRACEABILITY_RE.search('// ADO-1234 | 2026-04-25 | Validar fecha')

    def test_matches_con_espacios_extra(self):
        assert TRACEABILITY_RE.search('//  ADO-1234  |  2026-04-25  |  desc')

    def test_no_matches_sin_id(self):
        assert not TRACEABILITY_RE.search('// ADO- | 2026-04-25 | desc')

    def test_no_matches_sin_fecha(self):
        assert not TRACEABILITY_RE.search('// ADO-1234 | desc')

    def test_no_matches_sin_descripcion(self):
        assert not TRACEABILITY_RE.search('// ADO-1234 | 2026-04-25 |')

    def test_no_matches_fecha_invalida(self):
        assert not TRACEABILITY_RE.search('// ADO-1234 | 04-2026-25 | desc')


class TestRelevantFile:
    def test_cs_normal_relevante(self):
        assert _is_relevant_file('trunk/OnLine/Negocio/RSFac/Foo.cs')

    def test_aspx_relevante(self):
        assert _is_relevant_file('trunk/OnLine/AgendaWeb/FrmFoo.aspx')

    def test_aspx_cs_relevante(self):
        assert _is_relevant_file('trunk/OnLine/AgendaWeb/FrmFoo.aspx.cs')

    def test_md_no_relevante(self):
        assert not _is_relevant_file('docs/README.md')

    def test_test_dir_excluido(self):
        assert not _is_relevant_file('trunk/OnLine/Tests/FooTest.cs')
        assert not _is_relevant_file('trunk/OnLine/Test/FooTest.cs')
        assert not _is_relevant_file('trunk/OnLine/Foo.Tests/Bar.cs')

    def test_designer_cs_excluido(self):
        assert not _is_relevant_file('trunk/OnLine/AgendaWeb/FrmFoo.aspx.Designer.cs')

    def test_assembly_info_excluido(self):
        assert not _is_relevant_file('trunk/OnLine/Properties/AssemblyInfo.cs')

    def test_obj_bin_excluidos(self):
        assert not _is_relevant_file('trunk/OnLine/obj/Debug/Foo.cs')
        assert not _is_relevant_file('trunk/OnLine/bin/Debug/Foo.cs')


class TestSubstantive:
    def test_hunk_3_lineas_significativo(self):
        h = _Hunk(file='Foo.cs', start_line=10,
                  added_lines=['linea uno', 'linea dos', 'linea tres'],
                  context_before=[])
        assert _has_substantive_changes(h)

    def test_hunk_2_lineas_no_significativo(self):
        h = _Hunk(file='Foo.cs', start_line=10,
                  added_lines=['linea uno', 'linea dos'],
                  context_before=[])
        assert not _has_substantive_changes(h)

    def test_hunk_con_lineas_vacias_no_cuenta(self):
        h = _Hunk(file='Foo.cs', start_line=10,
                  added_lines=['linea uno', '', '   ', 'linea dos'],
                  context_before=[])
        # Sólo 2 líneas no-whitespace
        assert not _has_substantive_changes(h)


class TestTrazabilidadDetectada:
    def test_dentro_del_hunk_added(self):
        h = _Hunk(file='Foo.cs', start_line=10,
                  added_lines=[
                      '// ADO-1234 | 2026-04-25 | nuevo método',
                      'public void Foo() {',
                      '    // body',
                      '}',
                  ],
                  context_before=[])
        assert _has_traceability(h)

    def test_en_contexto_previo(self):
        h = _Hunk(file='Foo.cs', start_line=10,
                  added_lines=[
                      '    var x = ObtenerX();',
                      '    var y = ObtenerY();',
                      '    return x + y;',
                  ],
                  context_before=[
                      '// ADO-1234 | 2026-04-25 | refactor cálculo',
                      'public int Calcular() {',
                  ])
        assert _has_traceability(h)

    def test_sin_trazabilidad(self):
        h = _Hunk(file='Foo.cs', start_line=10,
                  added_lines=[
                      'public void NuevaCosa() {',
                      '    DoStuff();',
                      '    return;',
                      '}',
                  ],
                  context_before=['public class Bar {'])
        assert not _has_traceability(h)


class TestParseDiff:
    def test_diff_basico(self):
        diff = """diff --git a/Foo.cs b/Foo.cs
index abc..def 100644
--- a/Foo.cs
+++ b/Foo.cs
@@ -10,3 +10,5 @@
 public class Foo {
     public void Existing() {}
+    // ADO-1234 | 2026-04-25 | nuevo método
+    public void New() {
+    }
 }
"""
        hunks = list(_parse_diff(diff))
        assert len(hunks) == 1
        assert hunks[0].file == 'Foo.cs'
        assert len(hunks[0].added_lines) == 3
        assert any('ADO-1234' in l for l in hunks[0].added_lines)

    def test_diff_multiples_hunks(self):
        diff = """diff --git a/Foo.cs b/Foo.cs
--- a/Foo.cs
+++ b/Foo.cs
@@ -10,3 +10,4 @@
 public class Foo {
+    public void A() {}
     public void B() {}
 }
@@ -50,3 +51,4 @@
 public class Bar {
+    public void C() {}
     public void D() {}
 }
"""
        hunks = list(_parse_diff(diff))
        assert len(hunks) == 2

    def test_diff_eliminacion_sin_added(self):
        diff = """diff --git a/Foo.cs b/Foo.cs
--- a/Foo.cs
+++ b/Foo.cs
@@ -10,3 +10,1 @@
 public class Foo {
-    public void Old() {}
-    public void OldB() {}
 }
"""
        hunks = list(_parse_diff(diff))
        # El hunk se crea pero sin líneas agregadas → no significativo
        assert len(hunks) == 1
        assert len(hunks[0].added_lines) == 0


class TestEndToEnd:
    """Pruebas de integración del flujo completo via main()."""

    def test_main_sin_violaciones_pasa(self, monkeypatch):
        from pre_commit_traceability import main

        # Mockear git diff para simular un diff con trazabilidad
        diff_con_traza = """diff --git a/Foo.cs b/Foo.cs
--- a/Foo.cs
+++ b/Foo.cs
@@ -10,3 +10,7 @@
 public class Foo {
     public void Existing() {}
+    // ADO-1234 | 2026-04-25 | nuevo método
+    public void New() {
+        DoStuff();
+        return;
+    }
 }
"""
        monkeypatch.setattr(
            'pre_commit_traceability._git_diff_cached',
            lambda: diff_con_traza
        )
        assert main() == 0

    def test_main_con_violacion_falla(self, monkeypatch, capsys):
        from pre_commit_traceability import main

        diff_sin_traza = """diff --git a/Foo.cs b/Foo.cs
--- a/Foo.cs
+++ b/Foo.cs
@@ -10,3 +10,7 @@
 public class Foo {
     public void Existing() {}
+    public void Sin_Trazabilidad() {
+        DoStuff();
+        Otra();
+        return;
+    }
 }
"""
        monkeypatch.setattr(
            'pre_commit_traceability._git_diff_cached',
            lambda: diff_sin_traza
        )
        result = main()
        assert result == 1
        captured = capsys.readouterr()
        assert 'TRAZABILIDAD' in captured.err

    def test_main_con_bypass(self, monkeypatch):
        from pre_commit_traceability import main

        monkeypatch.setenv('SKIP_TRACEABILITY', '1')
        # No importa el diff: bypass corta antes
        assert main() == 0

    def test_main_archivo_test_ignorado(self, monkeypatch):
        from pre_commit_traceability import main

        diff_test_file = """diff --git a/trunk/OnLine/Tests/FooTest.cs b/trunk/OnLine/Tests/FooTest.cs
--- a/trunk/OnLine/Tests/FooTest.cs
+++ b/trunk/OnLine/Tests/FooTest.cs
@@ -10,3 +10,7 @@
 public class FooTest {
+    [Test]
+    public void Sin_Trazabilidad_Pero_Es_Test() {
+        Assert.IsTrue(true);
+    }
 }
"""
        monkeypatch.setattr(
            'pre_commit_traceability._git_diff_cached',
            lambda: diff_test_file
        )
        # El archivo de test se ignora aunque no tenga trazabilidad
        assert main() == 0
