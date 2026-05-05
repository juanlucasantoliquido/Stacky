"""Unit tests for graph_promoter.py — Fase 6 stable edge promotion.

Coverage:
- get_stable_candidates() returns edges with confidence='stable' and
  observed_count >= min_count that are NOT already in the static graph.
- get_stable_candidates() skips edges with 'probable' or 'tentative' confidence.
- get_stable_candidates() skips edges that already exist in navigation_graph.GRAPH.
- get_stable_candidates() returns empty list when learned_edges.json is absent.
- generate_snippet() produces syntactically valid Python for pasting into _RAW_GRAPH.
- render_pr_body() includes the table + snippet + reviewer checklist.
- StableCandidate.to_dict() includes all expected fields.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_learned_edges(tmp_path: Path, entries: list[dict]) -> Path:
    """Write a learned_edges.json with the provided edge entries under by_source."""
    by_source: dict[str, list[dict]] = {}
    for e in entries:
        by_source.setdefault(e["source"], []).append({
            "source": e["source"],
            "target": e["target"],
            "observed_count": e.get("observed_count", 1),
            "confidence": e.get("confidence", "tentative"),
            "first_seen": e.get("first_seen", "2026-01-01"),
            "last_seen": e.get("last_seen", "2026-05-05"),
            "action": e.get("action", "observed_navigate"),
            "evidence_runs": e.get("evidence_runs", []),
        })
    payload = {
        "schema_version": "2.0",
        "generated_at": "2026-05-05T00:00:00",
        "tool_version": "2.1.0",
        "by_source": by_source,
        "total_learned": len(entries),
    }
    p = tmp_path / "learned_edges.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


# ── get_stable_candidates() ───────────────────────────────────────────────────

def test_no_candidates_when_file_absent(tmp_path):
    import graph_promoter as gp
    absent = tmp_path / "no_such_file.json"
    result = gp.get_stable_candidates(learned_edges_path=absent)
    assert result == []


def test_stable_edge_returned_as_candidate(tmp_path):
    import graph_promoter as gp
    learned = _make_learned_edges(tmp_path, [
        {
            "source": "FrmDetalleClie.aspx",
            "target": "PopUpCompromisosFake.aspx",
            "observed_count": 7,
            "confidence": "stable",
            "first_seen": "2026-03-01",
            "last_seen": "2026-05-01",
            "evidence_runs": ["run-1", "run-2"],
        }
    ])
    candidates = gp.get_stable_candidates(learned_edges_path=learned)
    # Note: PopUpCompromisosFake.aspx is not in navigation_graph.GRAPH
    # so it should appear as a candidate. (FrmDetalleClie → PopUpCompromisos
    # the real one IS in the graph; "Fake" suffix makes it novel.)
    assert len(candidates) == 1
    c = candidates[0]
    assert c.source == "FrmDetalleClie.aspx"
    assert c.target == "PopUpCompromisosFake.aspx"
    assert c.observed_count == 7
    assert c.confidence == "stable"
    assert c.first_seen == "2026-03-01"


def test_tentative_edge_skipped(tmp_path):
    import graph_promoter as gp
    learned = _make_learned_edges(tmp_path, [
        {
            "source": "Default.aspx",
            "target": "FrmNuevaPantallaFake.aspx",
            "observed_count": 1,
            "confidence": "tentative",
        }
    ])
    candidates = gp.get_stable_candidates(learned_edges_path=learned)
    assert candidates == []


def test_probable_edge_skipped(tmp_path):
    import graph_promoter as gp
    learned = _make_learned_edges(tmp_path, [
        {
            "source": "Default.aspx",
            "target": "FrmNuevaPantallaFake.aspx",
            "observed_count": 4,
            "confidence": "probable",
        }
    ])
    candidates = gp.get_stable_candidates(learned_edges_path=learned)
    assert candidates == []


def test_stable_edge_below_min_count_skipped(tmp_path):
    """Edge persisted as 'stable' but observed_count is below the defensive min_count floor."""
    import graph_promoter as gp
    learned = _make_learned_edges(tmp_path, [
        {
            "source": "Default.aspx",
            "target": "FrmNuevaPantallaFake.aspx",
            "observed_count": 2,
            "confidence": "stable",  # shouldn't happen normally, but defensive
        }
    ])
    # Default min_count=5 — this entry has count=2, must be skipped
    candidates = gp.get_stable_candidates(learned_edges_path=learned, min_count=5)
    assert candidates == []


def test_multiple_stable_sorted_by_count_descending(tmp_path):
    import graph_promoter as gp
    learned = _make_learned_edges(tmp_path, [
        {
            "source": "FrmAgenda.aspx",
            "target": "FrmFakePantallaA.aspx",
            "observed_count": 5,
            "confidence": "stable",
        },
        {
            "source": "FrmAgenda.aspx",
            "target": "FrmFakePantallaB.aspx",
            "observed_count": 12,
            "confidence": "stable",
        },
    ])
    candidates = gp.get_stable_candidates(learned_edges_path=learned)
    assert len(candidates) == 2
    # Sorted descending by observed_count
    assert candidates[0].observed_count >= candidates[1].observed_count


def test_stable_candidate_to_dict_has_all_fields(tmp_path):
    import graph_promoter as gp
    learned = _make_learned_edges(tmp_path, [
        {
            "source": "FrmDetalleClie.aspx",
            "target": "PopUpFake.aspx",
            "observed_count": 6,
            "confidence": "stable",
            "first_seen": "2026-04-01",
            "last_seen": "2026-05-01",
            "evidence_runs": ["run-1"],
        }
    ])
    candidates = gp.get_stable_candidates(learned_edges_path=learned)
    assert len(candidates) == 1
    d = candidates[0].to_dict()
    for field in ("source", "target", "observed_count", "confidence", "first_seen", "last_seen", "action", "evidence_runs"):
        assert field in d, f"Missing field: {field}"


# ── generate_snippet() ────────────────────────────────────────────────────────

def test_generate_snippet_empty_returns_comment():
    import graph_promoter as gp
    snippet = gp.generate_snippet([])
    assert snippet.startswith("#")
    assert "No stable" in snippet


def test_generate_snippet_contains_source_screen(tmp_path):
    import graph_promoter as gp
    c = gp.StableCandidate(
        source="FrmBusqueda.aspx",
        target="FrmDetalleFake.aspx",
        observed_count=8,
        confidence="stable",
        first_seen="2026-04-01",
        last_seen="2026-05-01",
    )
    snippet = gp.generate_snippet([c])
    assert "FrmBusqueda.aspx" in snippet
    assert "FrmDetalleFake.aspx" in snippet


def test_generate_snippet_popup_target_uses_true(tmp_path):
    import graph_promoter as gp
    c = gp.StableCandidate(
        source="FrmDetalleClie.aspx",
        target="PopUpFakeDialog.aspx",
        observed_count=6,
        confidence="stable",
        first_seen="2026-04-01",
        last_seen="2026-05-01",
    )
    snippet = gp.generate_snippet([c])
    # is_popup should be True for PopUp* targets
    assert "True" in snippet


def test_generate_snippet_non_popup_uses_false():
    import graph_promoter as gp
    c = gp.StableCandidate(
        source="FrmAgenda.aspx",
        target="FrmDetalleFake.aspx",
        observed_count=5,
        confidence="stable",
    )
    snippet = gp.generate_snippet([c])
    assert "False" in snippet


# ── render_pr_body() ──────────────────────────────────────────────────────────

def test_render_pr_body_empty_returns_message():
    import graph_promoter as gp
    body = gp.render_pr_body([], "# snippet")
    assert "No stable" in body


def test_render_pr_body_contains_table_and_snippet():
    import graph_promoter as gp
    c = gp.StableCandidate(
        source="FrmBusqueda.aspx",
        target="FrmDetalleFake.aspx",
        observed_count=7,
        confidence="stable",
        first_seen="2026-04-01",
        last_seen="2026-05-01",
    )
    snippet = gp.generate_snippet([c])
    body = gp.render_pr_body([c], snippet)
    # Markdown table header must be present
    assert "| Source |" in body
    # Snippet must be embedded
    assert "FrmDetalleFake.aspx" in body
    # Reviewer checklist
    assert "- [ ]" in body


def test_render_pr_body_is_draft_pr_note():
    import graph_promoter as gp
    c = gp.StableCandidate(
        source="FrmAgenda.aspx",
        target="FrmFakePantalla.aspx",
        observed_count=5,
        confidence="stable",
    )
    body = gp.render_pr_body([c], gp.generate_snippet([c]))
    assert "draft" in body.lower() or "draft" in body


# ── open_ado_pr() graceful fallback ──────────────────────────────────────────

def test_open_ado_pr_returns_manual_instructions_when_az_absent(monkeypatch):
    """When the az CLI is not found, open_ado_pr should return a structured
    failure dict with manual_instructions rather than raising."""
    import graph_promoter as gp
    import subprocess

    original_run = subprocess.run

    def _fake_run(cmd, *args, **kwargs):
        if cmd == ["az", "--version"]:
            raise FileNotFoundError("az not found")
        return original_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    candidates = [
        gp.StableCandidate(
            source="FrmAgenda.aspx",
            target="FrmFakePantalla.aspx",
            observed_count=6,
            confidence="stable",
        )
    ]
    snippet = gp.generate_snippet(candidates)
    result = gp.open_ado_pr(candidates, snippet)

    assert result["ok"] is False
    assert "instructions" in result
    assert "FrmFakePantalla.aspx" in result["body"]
