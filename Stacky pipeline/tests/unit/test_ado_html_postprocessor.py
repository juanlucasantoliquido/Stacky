"""Tests de ado_html_postprocessor — Fase 1 / P1.6."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from ado_html_postprocessor import md_to_ado_html


class TestBasicos:
    def test_vacio(self):
        assert md_to_ado_html('') == ''
        assert md_to_ado_html('   \n\n   ') == ''

    def test_parrafo_simple(self):
        assert md_to_ado_html('Hola mundo') == '<p>Hola mundo</p>'

    def test_parrafo_multilinea(self):
        result = md_to_ado_html('linea uno\nlinea dos')
        assert result == '<p>linea uno linea dos</p>'

    def test_dos_parrafos(self):
        result = md_to_ado_html('p1\n\np2')
        assert '<p>p1</p>' in result
        assert '<p>p2</p>' in result


class TestHeadings:
    def test_h1_a_h6(self):
        for level in range(1, 7):
            md = '#' * level + ' Titulo'
            html = md_to_ado_html(md)
            assert html == f'<h{level}>Titulo</h{level}>'

    def test_h2_con_inline(self):
        assert md_to_ado_html('## Bold **dentro**') == '<h2>Bold <strong>dentro</strong></h2>'


class TestInline:
    def test_bold(self):
        assert md_to_ado_html('texto **negrita** fin') == '<p>texto <strong>negrita</strong> fin</p>'

    def test_italic(self):
        assert md_to_ado_html('texto *cursiva* fin') == '<p>texto <em>cursiva</em> fin</p>'

    def test_code_inline(self):
        assert md_to_ado_html('llama a `Foo.Bar()`') == '<p>llama a <code>Foo.Bar()</code></p>'

    def test_link(self):
        assert md_to_ado_html('ver [aquí](http://x.com)') == '<p>ver <a href="http://x.com">aquí</a></p>'

    def test_escape_html_en_texto_plano(self):
        # Caracteres < y > en texto plano deben escaparse
        result = md_to_ado_html('comparar a < b')
        assert '&lt;' in result

    def test_code_protege_de_otros_inline(self):
        # ** dentro de code NO debe convertirse a strong
        result = md_to_ado_html('mira `**no_bold**`')
        assert '<strong>' not in result
        assert '<code>**no_bold**</code>' in result


class TestHr:
    def test_hr_solo(self):
        assert md_to_ado_html('---') == '<hr>'

    def test_hr_entre_parrafos(self):
        result = md_to_ado_html('antes\n\n---\n\ndespues')
        assert '<p>antes</p>' in result
        assert '<hr>' in result
        assert '<p>despues</p>' in result


class TestListas:
    def test_ul_simple(self):
        result = md_to_ado_html('- uno\n- dos\n- tres')
        assert result == '<ul><li>uno</li><li>dos</li><li>tres</li></ul>'

    def test_ol_simple(self):
        result = md_to_ado_html('1. uno\n2. dos\n3. tres')
        assert result == '<ol><li>uno</li><li>dos</li><li>tres</li></ol>'

    def test_ul_con_inline(self):
        result = md_to_ado_html('- archivo `Foo.cs`\n- método **Bar()**')
        assert '<li>archivo <code>Foo.cs</code></li>' in result
        assert '<li>método <strong>Bar()</strong></li>' in result


class TestCodeFence:
    def test_fence_sql(self):
        md = '```sql\nSELECT * FROM RCLIE;\n```'
        result = md_to_ado_html(md)
        assert '<pre><code>SELECT * FROM RCLIE;</code></pre>' == result

    def test_fence_csharp_con_html_chars(self):
        md = '```csharp\nif (x < 10 && y > 0) {}\n```'
        result = md_to_ado_html(md)
        # Caracteres especiales escapados dentro de code
        assert '&lt;' in result
        assert '&gt;' in result
        assert '&amp;' in result


class TestBlockquote:
    def test_blockquote_simple(self):
        result = md_to_ado_html('> nota importante')
        assert result == '<blockquote>nota importante</blockquote>'

    def test_blockquote_multilinea(self):
        result = md_to_ado_html('> linea 1\n> linea 2')
        assert '<blockquote>' in result
        assert 'linea 1' in result
        assert 'linea 2' in result


class TestTablas:
    def test_tabla_basica(self):
        md = '| A | B |\n|---|---|\n| 1 | 2 |'
        result = md_to_ado_html(md)
        assert '<table style="border-collapse:collapse;width:100%">' in result
        assert '<th style="border:1px solid #ccc;padding:6px;background:#f0f0f0">A</th>' in result
        assert '<td style="border:1px solid #ccc;padding:6px">1</td>' in result

    def test_tabla_con_inline(self):
        md = '| Archivo | Cambio |\n|---|---|\n| `Foo.cs` | **agregar** |'
        result = md_to_ado_html(md)
        assert '<code>Foo.cs</code>' in result
        assert '<strong>agregar</strong>' in result


class TestPreservaHtml:
    def test_preserva_html_inline_legacy(self):
        # Si un agente legacy devuelve HTML directo, no romperlo
        md = '<h2>Ya en HTML</h2>'
        result = md_to_ado_html(md)
        assert '<h2>Ya en HTML</h2>' in result
        assert '&lt;h2&gt;' not in result


class TestTechnicalAnalystSnapshot:
    def test_estructura_completa(self):
        """Snapshot reducido del comentario que produce TechnicalAnalyst."""
        md = """## ANÁLISIS TÉCNICO — ADO-1234

> Generado por: Analista Técnico Agéntico
> Fecha: 2026-05-01

---

### Resumen rápido

Agregar validación en `ClaseBus.MetodoX()` para rechazar X cuando Y.

### Cambios

| Archivo | Capa | Cambio |
|---|---|---|
| `Foo.cs` | RSBus | Modificar |
| `Bar.cs` | RSDalc | Agregar query |

### Pasos

1. Abrir `Foo.cs`
2. Modificar línea ~89

```sql
SELECT * FROM RCLIE WHERE CLCOD = @p_cod;
```
"""
        result = md_to_ado_html(md)
        # Los elementos clave deben estar
        assert '<h2>ANÁLISIS TÉCNICO — ADO-1234</h2>' in result
        assert '<blockquote>' in result
        assert '<hr>' in result
        assert '<h3>Resumen rápido</h3>' in result
        assert '<table style="border-collapse:collapse;width:100%">' in result
        assert '<ol><li>' in result
        assert '<pre><code>' in result
        # Sin contenido sin convertir
        assert '|---|---|' not in result
        assert '##' not in result.replace('## ', '## ')  # markdown raw fuera


class TestSeguridad:
    def test_no_inyecta_script(self):
        # Si llega texto con tag script literal, debe escaparse en párrafo plano
        result = md_to_ado_html('texto <script>alert(1)</script>')
        # NO debe quedar el tag script ejecutable
        assert '<script>' not in result
        # Debe estar escapado
        assert '&lt;script&gt;' in result
