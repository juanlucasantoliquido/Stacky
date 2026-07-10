"""Plan 113 F1 — Selector de modos determinista plan_documenter_run."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import services.doc_graph as doc_graph_mod
from services import doc_documenter
from services.doc_documenter import DocumenterMode


def _patch_graph(monkeypatch, graph):
    monkeypatch.setattr(doc_graph_mod, "build_graph", lambda project_name=None, **k: graph)


def test_sin_docs_reconstruir(monkeypatch):
    _patch_graph(monkeypatch, {"doc_health": {"status": "SIN_DOCS"}, "nodes": []})
    plan = doc_documenter.plan_documenter_run("P")
    assert plan.modes == [DocumenterMode.RECONSTRUIR, DocumenterMode.ENRIQUECER]


def test_formato_no_obsidian_lists_notes_without_frontmatter(monkeypatch):
    nodes = [
        {"kind": "note", "path": "a.md", "source_id": "project-docs:main", "has_frontmatter": False},
        {"kind": "note", "path": "b.md", "source_id": "project-docs:main", "has_frontmatter": True},
        {"kind": "note", "path": "c.md", "source_id": "vscode-prompts", "has_frontmatter": False},
    ]
    _patch_graph(monkeypatch, {"doc_health": {"status": "FORMATO_NO_OBSIDIAN"}, "nodes": nodes})
    plan = doc_documenter.plan_documenter_run("P")
    assert plan.modes == [DocumenterMode.NORMALIZAR, DocumenterMode.ENRIQUECER]
    assert plan.notes_to_normalize == ["a.md"]  # solo project-docs sin frontmatter


def test_incompleta_carries_uncovered_modules(monkeypatch):
    _patch_graph(monkeypatch, {
        "doc_health": {"status": "INCOMPLETA", "uncovered_modules": ["mod_x", "mod_y"]},
        "nodes": []})
    plan = doc_documenter.plan_documenter_run("P")
    assert plan.modes == [DocumenterMode.COMPLETAR, DocumenterMode.ENRIQUECER]
    assert plan.uncovered_modules == ["mod_x", "mod_y"]


def test_sana_only_enriquecer(monkeypatch):
    _patch_graph(monkeypatch, {"doc_health": {"status": "SANA"}, "nodes": []})
    plan = doc_documenter.plan_documenter_run("P")
    assert plan.modes == [DocumenterMode.ENRIQUECER]


def test_modes_are_deterministic_ordered(monkeypatch):
    _patch_graph(monkeypatch, {"doc_health": {"status": "SIN_DOCS"}, "nodes": []})
    p1 = doc_documenter.plan_documenter_run("P")
    p2 = doc_documenter.plan_documenter_run("P")
    assert p1.modes == p2.modes
    assert p1.modes[0] == DocumenterMode.RECONSTRUIR
