"""Plan 44 F3 — Sugeridor pasivo de diccionario de procesos."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _suggest(*args, **kwargs):
    from services.grounding_observatory import suggest_process_catalog_entries
    return suggest_process_catalog_entries(*args, **kwargs)


def test_suggests_uncataloged_process():
    out = _suggest([{"cited_modules": ["proceso CargaNomina"]}], [])
    assert out == [{"name": "CargaNomina", "occurrences": 1}]


def test_excludes_cataloged_process():
    out = _suggest(
        [{"cited_modules": ["proceso CargaNomina"]}],
        [{"name": "CargaNomina", "kind": "processing", "purpose": "x"}],
    )
    assert out == []


def test_case_insensitive_dedup():
    out = _suggest(
        [{"cited_modules": ["proceso cargaNomina"]}],
        [{"name": "CargaNomina"}],
    )
    assert out == []


def test_ignores_modules_only_processes():
    out = _suggest([{"cited_modules": ["módulo 12"]}], [])
    assert out == []


def test_counts_occurrences_and_sorts():
    summaries = [
        {"cited_modules": ["proceso A"]},
        {"cited_modules": ["proceso A"]},
        {"cited_modules": ["proceso A", "proceso B"]},
    ]
    out = _suggest(summaries, [])
    assert out == [{"name": "A", "occurrences": 3}, {"name": "B", "occurrences": 1}]


def test_endpoint_returns_suggestions():
    from config import config
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    summaries = [{"cited_modules": ["proceso CargaNomina"]}]
    with patch.object(config, "STACKY_PROCESS_CATALOG_SUGGESTIONS_ENABLED", True), \
         patch("api.agents._collect_epic_summaries", return_value=(summaries, [])), \
         patch("api.agents._load_process_catalog", return_value=[]):
        with app.test_client() as c:
            r = c.get("/api/agents/projects/RSPACIFICO/process-catalog-suggestions")
    assert r.status_code == 200
    d = r.get_json()
    assert d["project"] == "RSPACIFICO"
    assert d["suggestions"] == [{"name": "CargaNomina", "occurrences": 1}]


def test_endpoint_404_when_flag_off():
    from config import config
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with patch.object(config, "STACKY_PROCESS_CATALOG_SUGGESTIONS_ENABLED", False):
        with app.test_client() as c:
            r = c.get("/api/agents/projects/RSPACIFICO/process-catalog-suggestions")
    assert r.status_code == 404
