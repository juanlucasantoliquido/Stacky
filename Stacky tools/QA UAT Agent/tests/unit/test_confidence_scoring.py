"""Unit tests for navigation_graph_learner Fase 6 — confidence scoring.

Coverage:
- compute_confidence() classifies observed_count into the right bucket.
- ObservedEdge.to_dict() includes the new confidence/first_seen/last_seen fields.
- _write_learned_edges() persists confidence based on the post-merge
  observed_count, including the case where multiple incremental scans push
  an edge over the stable threshold.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")


# ── compute_confidence() boundaries ──────────────────────────────────────────


def test_compute_confidence_one_is_tentative():
    import navigation_graph_learner as ngl
    assert ngl.compute_confidence(1) == "tentative"


def test_compute_confidence_two_is_tentative():
    import navigation_graph_learner as ngl
    assert ngl.compute_confidence(2) == "tentative"


def test_compute_confidence_three_is_probable():
    import navigation_graph_learner as ngl
    assert ngl.compute_confidence(3) == "probable"


def test_compute_confidence_four_is_probable():
    import navigation_graph_learner as ngl
    assert ngl.compute_confidence(4) == "probable"


def test_compute_confidence_five_is_stable():
    import navigation_graph_learner as ngl
    assert ngl.compute_confidence(5) == "stable"


def test_compute_confidence_one_hundred_is_stable():
    import navigation_graph_learner as ngl
    assert ngl.compute_confidence(100) == "stable"


# ── ObservedEdge.to_dict() schema ────────────────────────────────────────────


def test_observed_edge_to_dict_includes_confidence_fields():
    import navigation_graph_learner as ngl
    edge = ngl.ObservedEdge(source="A.aspx", target="B.aspx")
    d = edge.to_dict()
    assert "confidence" in d
    assert "first_seen" in d
    assert "last_seen" in d


def test_observed_edge_default_confidence_is_tentative():
    import navigation_graph_learner as ngl
    edge = ngl.ObservedEdge(source="A.aspx", target="B.aspx")
    assert edge.confidence == "tentative"


# ── _write_learned_edges() persists confidence ───────────────────────────────


def test_write_learned_edges_persists_stable_for_high_count(tmp_path, monkeypatch):
    """An edge with observed_count=6 should land on disk with confidence=stable."""
    import navigation_graph_learner as ngl
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    learned_file = cache_dir / "learned_edges.json"
    monkeypatch.setattr(ngl, "_CACHE_DIR", cache_dir)
    monkeypatch.setattr(ngl, "_LEARNED_EDGES_PATH", learned_file)

    edge = ngl.ObservedEdge(
        source="FrmDetalleClie.aspx",
        target="PopUpCompromisos.aspx",
        observed_count=6,
        evidence_runs=["run-a"],
    )
    ngl._write_learned_edges([edge], learned_file)

    data = json.loads(learned_file.read_text(encoding="utf-8"))
    assert data["schema_version"] == "2.0"
    entries = data["by_source"]["FrmDetalleClie.aspx"]
    assert len(entries) == 1
    persisted = entries[0]
    assert persisted["confidence"] == "stable"
    assert persisted["observed_count"] == 6
    assert persisted["first_seen"], "first_seen must be populated"
    assert persisted["last_seen"], "last_seen must be populated"


def test_write_learned_edges_merges_count_and_recomputes_confidence(tmp_path, monkeypatch):
    """An edge first seen with count=4 (probable), re-scanned twice more,
    must end up with count=6 and confidence=stable."""
    import navigation_graph_learner as ngl
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    learned_file = cache_dir / "learned_edges.json"
    monkeypatch.setattr(ngl, "_CACHE_DIR", cache_dir)
    monkeypatch.setattr(ngl, "_LEARNED_EDGES_PATH", learned_file)

    first = ngl.ObservedEdge(
        source="FrmDetalleClie.aspx",
        target="PopUpAgendar.aspx",
        observed_count=4,
        evidence_runs=["run-1"],
    )
    ngl._write_learned_edges([first], learned_file)

    data = json.loads(learned_file.read_text(encoding="utf-8"))
    persisted = data["by_source"]["FrmDetalleClie.aspx"][0]
    assert persisted["confidence"] == "probable"
    assert persisted["observed_count"] == 4

    # Second incremental scan: same edge seen 2 more times.
    second = ngl.ObservedEdge(
        source="FrmDetalleClie.aspx",
        target="PopUpAgendar.aspx",
        observed_count=2,
        evidence_runs=["run-2"],
    )
    ngl._write_learned_edges([second], learned_file)

    data = json.loads(learned_file.read_text(encoding="utf-8"))
    persisted = data["by_source"]["FrmDetalleClie.aspx"][0]
    assert persisted["observed_count"] == 6
    assert persisted["confidence"] == "stable"
    assert "run-1" in persisted["evidence_runs"]
    assert "run-2" in persisted["evidence_runs"]


def test_write_learned_edges_tentative_for_single_observation(tmp_path, monkeypatch):
    import navigation_graph_learner as ngl
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    learned_file = cache_dir / "learned_edges.json"
    monkeypatch.setattr(ngl, "_CACHE_DIR", cache_dir)
    monkeypatch.setattr(ngl, "_LEARNED_EDGES_PATH", learned_file)

    edge = ngl.ObservedEdge(
        source="Default.aspx",
        target="FrmAdministrador.aspx",
        observed_count=1,
        evidence_runs=["run-x"],
    )
    ngl._write_learned_edges([edge], learned_file)

    data = json.loads(learned_file.read_text(encoding="utf-8"))
    persisted = data["by_source"]["Default.aspx"][0]
    assert persisted["confidence"] == "tentative"
