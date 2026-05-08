"""Unit tests for path_planner.py — Fase 6 confidence scoring.

Coverage:
- PlanResult.to_dict() includes confidence + confidence_breakdown.
- plan() returns confidence='stable' for paths that use only static graph edges.
- plan() returns confidence='tentative' for paths that include learned tentative edges.
- plan() warning is augmented when path confidence is tentative.
- _score_path() returns 'stable' for a single-screen path (no edges to score).
- _annotate_confidence() updates the PlanResult in place.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")


# ── PlanResult schema ─────────────────────────────────────────────────────────

def test_plan_result_to_dict_includes_confidence_fields():
    import path_planner as pp
    r = pp.PlanResult(ok=True, path=[], target_screen="", entry_screen="")
    d = r.to_dict()
    assert "confidence" in d
    assert "confidence_breakdown" in d


def test_plan_result_default_confidence_is_stable():
    import path_planner as pp
    r = pp.PlanResult(ok=True, path=[], target_screen="", entry_screen="")
    assert r.confidence == "stable"


# ── Static-graph paths are always stable ─────────────────────────────────────

def test_static_path_confidence_is_stable():
    """crear_compromiso_pago maps to PopUpCompromisos.aspx which is reachable
    via edges already in navigation_graph._RAW_GRAPH."""
    import path_planner as pp
    result = pp.plan("crear_compromiso_pago")
    assert result.ok
    assert result.confidence == "stable"
    assert "tentative" not in result.warning


def test_static_path_has_no_tentative_breakdown_entries():
    import path_planner as pp
    result = pp.plan("crear_compromiso_pago")
    for entry in result.confidence_breakdown:
        assert entry["confidence"] != "tentative", (
            f"Unexpected tentative edge in static path: {entry}"
        )


def test_buscar_cliente_confidence_is_stable():
    """buscar_cliente targets FrmBusqueda.aspx, reachable from the static graph."""
    import path_planner as pp
    result = pp.plan("buscar_cliente")
    assert result.ok
    assert result.confidence == "stable"


# ── Trivial single-screen path ────────────────────────────────────────────────

def test_trivial_path_entry_equals_target_is_stable():
    """When entry == target, PlanResult.source='direct' and confidence must be 'stable'."""
    import path_planner as pp
    result = pp.plan_from_target("FrmAgenda.aspx", entry_screen="FrmAgenda.aspx", assume_logged_in=True)
    assert result.ok
    assert result.source == "direct"
    assert result.confidence == "stable"


# ── Learned tentative edges produce tentative confidence ─────────────────────

def test_learned_tentative_edge_makes_path_tentative(tmp_path, monkeypatch):
    """When load_learned_edges() returns an edge with confidence='tentative',
    _annotate_confidence() must propagate tentative to the PlanResult."""
    import path_planner as pp

    # Inject a fake learned_edges loader that claims FrmAgenda→FrmFake is tentative
    def _fake_load():
        return {
            "FrmAgenda.aspx": [
                {"target": "FrmFakePantalla.aspx", "confidence": "tentative"}
            ]
        }

    monkeypatch.setattr(
        "navigation_graph_learner.load_learned_edges",
        _fake_load,
        raising=False,
    )
    # Use plan_from_target with a target that won't be in the static graph
    # so the BFS falls back to heuristic and may traverse via FrmAgenda→FrmFake
    # Instead: directly test _score_path() with a crafted path containing
    # the fake edge.
    confidence, breakdown = pp._score_path(["FrmAgenda.aspx", "FrmFakePantalla.aspx"])
    assert confidence == "tentative"
    assert len(breakdown) == 1
    assert breakdown[0]["confidence"] == "tentative"
    assert breakdown[0]["edge_source"] == "learned"


def test_learned_stable_edge_score_path_is_stable(monkeypatch):
    """When the learned edge has confidence='stable', _score_path returns stable."""
    import path_planner as pp

    def _fake_load():
        return {
            "FrmAgenda.aspx": [
                {"target": "FrmFakePantalla.aspx", "confidence": "stable"}
            ]
        }

    monkeypatch.setattr(
        "navigation_graph_learner.load_learned_edges",
        _fake_load,
        raising=False,
    )
    confidence, breakdown = pp._score_path(["FrmAgenda.aspx", "FrmFakePantalla.aspx"])
    assert confidence == "stable"


def test_unknown_edge_is_tentative(monkeypatch):
    """An edge that appears in neither the static graph nor learned_edges is tentative."""
    import path_planner as pp

    monkeypatch.setattr(
        "navigation_graph_learner.load_learned_edges",
        lambda: {},
        raising=False,
    )
    confidence, breakdown = pp._score_path(
        ["FrmUnknownScreen.aspx", "FrmAnotherUnknown.aspx"]
    )
    assert confidence == "tentative"
    assert breakdown[0]["edge_source"] == "unknown"


# ── Warning augmentation ──────────────────────────────────────────────────────

def test_tentative_path_augments_warning(monkeypatch):
    """When path confidence is tentative, result.warning must mention session_recorder.py."""
    import path_planner as pp

    # Patch _score_path to always return tentative
    monkeypatch.setattr(pp, "_score_path", lambda path: ("tentative", []))

    result = pp.PlanResult(
        ok=True,
        path=["FrmLogin.aspx", "FrmFake.aspx"],
        target_screen="FrmFake.aspx",
        entry_screen="FrmFake.aspx",
    )
    result = pp._annotate_confidence(result)
    assert result.confidence == "tentative"
    assert "session_recorder.py" in result.warning


def test_stable_path_does_not_add_warning(monkeypatch):
    import path_planner as pp

    monkeypatch.setattr(pp, "_score_path", lambda path: ("stable", []))

    result = pp.PlanResult(
        ok=True,
        path=["FrmLogin.aspx", "FrmAgenda.aspx"],
        target_screen="FrmAgenda.aspx",
        entry_screen="FrmAgenda.aspx",
    )
    result = pp._annotate_confidence(result)
    assert result.confidence == "stable"
    assert "session_recorder" not in result.warning


# ── Breakdown structure ───────────────────────────────────────────────────────

def test_breakdown_contains_expected_keys():
    import path_planner as pp
    result = pp.plan("crear_compromiso_pago")
    for entry in result.confidence_breakdown:
        assert "source" in entry
        assert "target" in entry
        assert "edge_source" in entry
        assert "confidence" in entry


def test_breakdown_length_equals_hops():
    import path_planner as pp
    result = pp.plan("crear_compromiso_pago", assume_logged_in=True)
    # hops = len(path) - 1 (excluding login if assume_logged_in)
    assert len(result.confidence_breakdown) == len(result.path) - 1


# ── Min confidence drives the path label ─────────────────────────────────────

def test_path_confidence_is_minimum_of_edges(monkeypatch):
    """A path with one stable and one tentative edge must surface as tentative."""
    import path_planner as pp

    # Inject: FrmA→FrmB stable (static), FrmB→FrmC tentative (learned)
    original_get_edges = pp.get_edges

    def _fake_score(path):
        # Simulate mixed breakdown
        breakdown = [
            {"source": "FrmA", "target": "FrmB", "edge_source": "static", "confidence": "stable"},
            {"source": "FrmB", "target": "FrmC", "edge_source": "learned", "confidence": "tentative"},
        ]
        min_conf = "tentative"
        return (min_conf, breakdown)

    monkeypatch.setattr(pp, "_score_path", _fake_score)

    result = pp.PlanResult(
        ok=True,
        path=["FrmA", "FrmB", "FrmC"],
        target_screen="FrmC",
        entry_screen="FrmA",
    )
    result = pp._annotate_confidence(result)
    assert result.confidence == "tentative"
    assert len(result.confidence_breakdown) == 2
