"""tests/test_plan109_parsers.py — Plan 109 F1.

Parsers puros de aristas (sin I/O): links md, wikilinks, refs de código.
Un test por caso borde del plan (14 tests).
"""
from services.doc_graph import (
    parse_markdown_links,
    parse_wikilinks,
    parse_code_refs,
)


def test_md_link_with_anchor():
    assert parse_markdown_links("ver [x](a/b.md#seccion)") == ["a/b.md"]


def test_md_link_external_ignored():
    assert parse_markdown_links("[x](https://foo.com/a.md)") == []


def test_md_link_absolute_ignored():
    assert parse_markdown_links("[x](C:/docs/a.md) [y](/etc/a.md)") == []


def test_md_link_space_in_target_not_matched():
    # (C8) limitación documentada: destino con espacio no matchea.
    assert parse_markdown_links("[x](mi nota.md)") == []


def test_wikilink_alias():
    assert parse_wikilinks("texto [[Nota Motor|el motor]] fin") == ["Nota Motor"]


def test_wikilink_empty_ignored():
    assert parse_wikilinks("vacio [[]] nada") == []


def test_wikilink_dedup():
    assert parse_wikilinks("[[a]] y [[a]] otra vez") == ["a"]


def test_fenced_block_ignored_for_links_and_wikilinks_but_not_code_refs():
    text = (
        "intro\n"
        "```\n"
        "[[nota]] y [x](a.md) y backend/foo.py:1\n"
        "```\n"
        "afuera [[real]]\n"
    )
    assert parse_wikilinks(text) == ["real"]
    assert parse_markdown_links(text) == []
    assert parse_code_refs(text) == ["backend/foo.py"]


def test_unclosed_fence_ignores_rest():
    text = "antes [[uno]]\n```\n[[dentro]] [x](b.md)\n"
    # no lanza; todo lo que sigue al fence abierto se ignora para links/wikilinks
    assert parse_wikilinks(text) == ["uno"]
    assert parse_markdown_links(text) == []


def test_code_ref_with_line():
    assert parse_code_refs("ver backend/services/foo.py:123 dos veces backend/services/foo.py:123") == [
        "backend/services/foo.py"
    ]


def test_code_ref_backslashes():
    assert parse_code_refs("archivo backend\\services\\foo.py") == ["backend/services/foo.py"]


def test_code_ref_bare_filename_not_matched():
    assert parse_code_refs("solo foo.py suelto") == []


def test_code_ref_fileline_without_dir():
    assert parse_code_refs("error en foo.py:42") == ["foo.py"]


def test_none_and_empty_input():
    assert parse_markdown_links(None) == []
    assert parse_wikilinks("") == []
    assert parse_code_refs(None) == []
