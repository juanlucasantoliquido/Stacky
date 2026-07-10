"""Plan 113 F2 — parse_proposals + build_context_for_mode + invoke_documenter."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import doc_documenter
from services.doc_documenter import DocumenterMode, DocumenterPlan

_WELL_FORMED = (
    'ruido antes\n'
    '<<<DOC path="modulo/nota.md" action="create" sources="a.py:10,b.ts:3">>>\n'
    '---\ntitle: Nota\n---\n# Nota\nEl login valida el RUT [V] (a.py:10).\n'
    '<<<END>>>\n'
    'ruido después'
)


def test_parse_well_formed_proposals():
    props = doc_documenter.parse_proposals(_WELL_FORMED)
    assert len(props) == 1
    p = props[0]
    assert p.path == "modulo/nota.md"
    assert p.action == "create"
    assert p.sources == ["a.py:10", "b.ts:3"]
    assert p.marks_ok is True


def test_parse_rejects_missing_marks():
    raw = ('<<<DOC path="x.md" action="create" sources="a.py:1">>>\n'
           'contenido sin marcas de confianza\n<<<END>>>')
    props = doc_documenter.parse_proposals(raw)
    assert len(props) == 1
    assert props[0].marks_ok is False


def test_parse_ignores_malformed_blocks():
    raw = ('<<<DOC path="ok.md" action="create" sources="a.py:1">>>\ncuerpo [V]\n<<<END>>>\n'
           '<<<DOC action="create" sources="a">>>\nsin attr path\n<<<END>>>\n'
           '<<<DOC path="z.md" action="borrar" sources="a">>>\ncuerpo [V]\n<<<END>>>')
    props = doc_documenter.parse_proposals(raw)
    # solo ok.md sobrevive: el 2do no tiene path (no matchea), el 3ro tiene action inválida
    assert [p.path for p in props] == ["ok.md"]


def test_build_context_normalize_includes_note_content(monkeypatch):
    monkeypatch.setattr(doc_documenter, "_read_note_content",
                        lambda proj, path: f"CONTENIDO-{path}")
    plan = DocumenterPlan("FORMATO_NO_OBSIDIAN", [DocumenterMode.NORMALIZAR],
                          notes_to_normalize=["a.md"])
    blocks = doc_documenter.build_context_for_mode(DocumenterMode.NORMALIZAR, plan, "P")
    note_blocks = [b for b in blocks if b["kind"] == "existing-note"]
    assert note_blocks and note_blocks[0]["content"] == "CONTENIDO-a.md"


def test_build_context_always_includes_sistema_readonly_block(monkeypatch):
    monkeypatch.setattr(doc_documenter, "_subgraph_block",
                        lambda proj: {"id": "doc-subgraph", "kind": "doc-subgraph",
                                      "title": "s", "content": ""})
    plan = DocumenterPlan("SANA", [DocumenterMode.ENRIQUECER])
    for mode in (DocumenterMode.ENRIQUECER, DocumenterMode.RECONSTRUIR):
        blocks = doc_documenter.build_context_for_mode(mode, plan, "P")
        assert any(b["kind"] == "canonical-index" for b in blocks)


def test_invoke_uses_selected_runtime(monkeypatch):
    captured = {}

    def _fake_run_agent(**kw):
        captured.update(kw)
        return 999

    import agent_runner
    monkeypatch.setattr(agent_runner, "run_agent", _fake_run_agent)
    monkeypatch.setattr(doc_documenter, "_ensure_documenter_ticket", lambda p: 5)
    monkeypatch.setattr(doc_documenter, "_wait_and_read_output",
                        lambda eid, timeout_s=1800: _WELL_FORMED)
    props = doc_documenter.invoke_documenter(
        DocumenterMode.RECONSTRUIR, [{"id": "x"}], "P", runtime="claude_code_cli")
    assert captured["runtime"] == "claude_code_cli"
    assert captured["agent_type"] == "Documentador"
    assert len(props) == 1  # el output se parseó
