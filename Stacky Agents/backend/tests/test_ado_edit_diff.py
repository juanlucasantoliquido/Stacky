"""Plan 60 F0 — Tests del diff puro de ediciones HTML (harness/ado_edit_diff.py).

Función pura sin red ni BD. Los 6 casos del plan, más borde.
"""
from __future__ import annotations


def test_identical_html_is_not_material():
    """diff_edit(html, html) idéntico → is_material=False, added/removed vacíos."""
    from harness.ado_edit_diff import diff_edit
    html = "<h1>Épica</h1><p>Descripción del proyecto.</p>"
    r = diff_edit(html, html)
    assert r.is_material is False
    assert r.added_snippets == []
    assert r.removed_snippets == []


def test_added_phrase_is_material():
    """baseline + frase nueva en edited → is_material=True, frase en added_snippets."""
    from harness.ado_edit_diff import diff_edit
    baseline = "<h1>Épica</h1><p>Descripción inicial.</p>"
    edited = "<h1>Épica</h1><p>Descripción inicial. Nueva cláusula de seguridad requerida.</p>"
    r = diff_edit(baseline, edited)
    assert r.is_material is True
    joined_added = " ".join(r.added_snippets)
    assert "seguridad" in joined_added or "cláusula" in joined_added


def test_whitespace_only_change_not_material():
    """Solo cambio de whitespace/&nbsp; → is_material=False."""
    from harness.ado_edit_diff import diff_edit
    baseline = "<p>Descripción del sistema.</p>"
    edited = "<p>Descripción  del  sistema.</p>"  # extra spaces
    r = diff_edit(baseline, edited)
    assert r.is_material is False


def test_empty_baseline_with_content_is_material():
    """baseline '', edited con contenido → is_material=True."""
    from harness.ado_edit_diff import diff_edit
    r = diff_edit("", "<p>Contenido completamente nuevo agregado por el humano.</p>")
    assert r.is_material is True


def test_removed_phrase_appears_in_removed_snippets():
    """Eliminación de una frase → aparece en removed_snippets."""
    from harness.ado_edit_diff import diff_edit
    baseline = "<p>Primero. Segundo. Tercero.</p>"
    edited = "<p>Primero. Tercero.</p>"
    r = diff_edit(baseline, edited)
    joined_removed = " ".join(r.removed_snippets)
    assert "Segundo" in joined_removed


def test_strip_html_to_text_decodes_entities():
    """strip_html_to_text('<h1>A</h1><p>b&amp;c</p>') → 'A b&c'."""
    from harness.ado_edit_diff import strip_html_to_text
    result = strip_html_to_text("<h1>A</h1><p>b&amp;c</p>")
    assert result == "A b&c"


def test_strip_html_nbsp():
    """&nbsp; se trata como espacio."""
    from harness.ado_edit_diff import strip_html_to_text
    result = strip_html_to_text("<p>A&nbsp;B</p>")
    assert "A B" in result


def test_diff_returns_edit_delta_type():
    """diff_edit devuelve un EditDelta con los campos esperados."""
    from harness.ado_edit_diff import diff_edit, EditDelta
    r = diff_edit("<p>x</p>", "<p>y</p>")
    assert isinstance(r, EditDelta)
    assert hasattr(r, "is_material")
    assert hasattr(r, "baseline_text")
    assert hasattr(r, "edited_text")
    assert hasattr(r, "added_snippets")
    assert hasattr(r, "removed_snippets")
    assert hasattr(r, "net_char_delta")
