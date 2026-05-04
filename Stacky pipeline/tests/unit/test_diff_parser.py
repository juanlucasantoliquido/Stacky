"""Tests del diff_parser compartido — Fase 2 / P2.1."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from linters.diff_parser import parse_diff, hunks_by_file


class TestParseDiff:
    def test_un_hunk_simple(self):
        diff = """diff --git a/Foo.cs b/Foo.cs
--- a/Foo.cs
+++ b/Foo.cs
@@ -10,2 +10,4 @@
 public class Foo {
     public void A() {}
+    public void B() {}
+    public void C() {}
 }
"""
        hunks = list(parse_diff(diff))
        assert len(hunks) == 1
        h = hunks[0]
        assert h.file == "Foo.cs"
        assert h.start_line == 10
        assert len(h.added) == 2
        # La primera línea agregada está en el archivo nuevo después de las 2 líneas de contexto previo
        assert h.added[0].line_no == 12
        assert h.added[0].content == "    public void B() {}"
        assert h.added[1].line_no == 13

    def test_multiples_hunks(self):
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
        hunks = list(parse_diff(diff))
        assert len(hunks) == 2
        assert hunks[0].file == "Foo.cs"
        assert hunks[1].file == "Foo.cs"

    def test_multiples_archivos(self):
        diff = """diff --git a/A.cs b/A.cs
--- a/A.cs
+++ b/A.cs
@@ -1,1 +1,2 @@
 line1
+line2
diff --git a/B.cs b/B.cs
--- a/B.cs
+++ b/B.cs
@@ -1,1 +1,2 @@
 line1
+line2
"""
        files = hunks_by_file(diff)
        assert "A.cs" in files
        assert "B.cs" in files
        assert len(files["A.cs"]) == 1
        assert len(files["B.cs"]) == 1

    def test_dev_null_creacion(self):
        diff = """diff --git a/New.cs b/New.cs
new file mode 100644
--- /dev/null
+++ b/New.cs
@@ -0,0 +1,3 @@
+public class New {
+    public void A() {}
+}
"""
        hunks = list(parse_diff(diff))
        assert len(hunks) == 1
        assert hunks[0].file == "New.cs"
        assert len(hunks[0].added) == 3

    def test_eliminacion_pura(self):
        diff = """diff --git a/Foo.cs b/Foo.cs
--- a/Foo.cs
+++ b/Foo.cs
@@ -10,3 +10,1 @@
 public class Foo {
-    public void Old() {}
-    public void OldB() {}
 }
"""
        hunks = list(parse_diff(diff))
        assert len(hunks) == 1
        assert hunks[0].added == []

    def test_context_before_y_after(self):
        diff = """diff --git a/Foo.cs b/Foo.cs
--- a/Foo.cs
+++ b/Foo.cs
@@ -10,5 +10,6 @@
 line_before_1
 line_before_2
+line_added
 line_after_1
 line_after_2
 line_after_3
"""
        hunks = list(parse_diff(diff))
        assert hunks[0].context_before == ["line_before_1", "line_before_2"]
        assert hunks[0].context_after == ["line_after_1", "line_after_2", "line_after_3"]

    def test_added_substantive_count(self):
        diff = """diff --git a/Foo.cs b/Foo.cs
--- a/Foo.cs
+++ b/Foo.cs
@@ -1,1 +1,5 @@
 line
+actual line
+
+
+another actual line
"""
        hunks = list(parse_diff(diff))
        assert hunks[0].added_substantive_count() == 2

    def test_line_numbers_correctos(self):
        # @@ -10,2 +20,4 @@: archivo nuevo arranca en línea 20
        diff = """diff --git a/Foo.cs b/Foo.cs
--- a/Foo.cs
+++ b/Foo.cs
@@ -10,2 +20,4 @@
 line a (es 20)
+line b (es 21)
+line c (es 22)
 line d (es 23)
"""
        hunks = list(parse_diff(diff))
        assert hunks[0].added[0].line_no == 21
        assert hunks[0].added[1].line_no == 22
