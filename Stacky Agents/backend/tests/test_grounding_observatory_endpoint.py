"""Plan 44 F2 — Endpoint del observatorio de grounding."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_URL = "/api/agents/epics/grounding-observatory"


def _make_app():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


def test_endpoint_returns_aggregated_metrics():
    from config import config
    app = _make_app()
    summaries = [
        {"warnings": ["x"], "confidence": 0.8, "cited_modules": []},
        {"warnings": [], "confidence": 0.6, "cited_modules": []},
    ]
    runtimes = ["claude_code_cli", "claude_code_cli"]
    with patch.object(config, "STACKY_GROUNDING_OBSERVATORY_ENABLED", True), \
         patch("api.agents._collect_epic_summaries", return_value=(summaries, runtimes)):
        with app.test_client() as c:
            r = c.get(_URL)
    assert r.status_code == 200
    d = r.get_json()
    assert d["total_epics"] == 2
    assert d["epics_with_warnings"] == 1
    assert abs(d["avg_confidence"] - 0.7) < 1e-9
    assert d["runtime_coverage"] == ["claude_code_cli"]


def test_endpoint_404_when_flag_off():
    from config import config
    app = _make_app()
    with patch.object(config, "STACKY_GROUNDING_OBSERVATORY_ENABLED", False):
        with app.test_client() as c:
            r = c.get(_URL)
    assert r.status_code == 404
    assert r.get_json()["error"] == "feature_disabled"


def test_endpoint_empty_when_no_epics():
    from config import config
    app = _make_app()
    with patch.object(config, "STACKY_GROUNDING_OBSERVATORY_ENABLED", True), \
         patch("api.agents._collect_epic_summaries", return_value=([], [])):
        with app.test_client() as c:
            r = c.get(_URL)
    assert r.status_code == 200
    d = r.get_json()
    assert d["total_epics"] == 0
    assert d["runtime_coverage"] == []


def test_endpoint_echoes_project_filter():
    from config import config
    app = _make_app()
    with patch.object(config, "STACKY_GROUNDING_OBSERVATORY_ENABLED", True), \
         patch("api.agents._collect_epic_summaries", return_value=([], [])) as mock_collect:
        with app.test_client() as c:
            r = c.get(_URL + "?project=RSPACIFICO")
    assert r.status_code == 200
    assert r.get_json()["project"] == "RSPACIFICO"
    mock_collect.assert_called_once_with("RSPACIFICO")
