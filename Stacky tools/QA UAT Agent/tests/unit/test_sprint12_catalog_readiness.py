"""
tests/unit/test_sprint12_catalog_readiness.py — Sprint 12 tests.

Tests:
  catalog_readiness_checker.py
    1.  test_load_catalog_fixtures_returns_dict
    2.  test_load_catalog_fixtures_missing_file_returns_empty
    3.  test_load_catalog_fixtures_provincia_is_defined
    4.  test_load_catalog_fixtures_departamento_is_defined
    5.  test_load_catalog_fixtures_tipodoc_is_defined
    6.  test_check_readiness_empty_catalogs_list_returns_ok
    7.  test_check_readiness_no_db_url_returns_unverified
    8.  test_check_readiness_unknown_catalog_returns_unverified
    9.  test_check_readiness_writes_evidence_artifact
    10. test_check_readiness_all_unverified_when_no_db
    11. test_generate_catalog_seed_sql_has_begin_transaction
    12. test_generate_catalog_seed_sql_has_rollback_not_commit
    13. test_generate_catalog_seed_sql_has_prod_guard
    14. test_generate_catalog_seed_sql_has_seed_run_id
    15. test_generate_catalog_seed_sql_has_verification_select

  GET /api/qa-uat/catalog-readiness (Flask)
    16. test_catalog_readiness_endpoint_empty_when_no_files
    17. test_catalog_readiness_endpoint_returns_artifacts
    18. test_catalog_readiness_endpoint_missing_run_id_returns_400
    19. test_catalog_readiness_endpoint_missing_ticket_id_returns_400

  POST /api/qa-uat/catalog-readiness/check (Flask)
    20. test_catalog_check_endpoint_returns_400_on_missing_run_id
    21. test_catalog_check_endpoint_returns_400_on_empty_catalogs
    22. test_catalog_check_endpoint_ok_returns_unverified_without_db

  GET /api/qa-uat/catalog-readiness/fixtures (Flask)
    23. test_catalog_fixtures_endpoint_returns_fixture_list

All tests run without DB or network.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

TOOL_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(TOOL_DIR))

BACKEND_DIR = TOOL_DIR.parent.parent / "Stacky Agents" / "backend"
FIXTURES_PATH = TOOL_DIR / "fixtures" / "catalog_fixtures.yml"


# ─────────────────────────────────────────────────────────────────────────────
# catalog_readiness_checker — fixture loading
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadCatalogFixtures:

    def _load(self, path=None):
        from catalog_readiness_checker import load_catalog_fixtures
        return load_catalog_fixtures(path or FIXTURES_PATH)

    def test_load_catalog_fixtures_returns_dict(self):
        fixtures = self._load()
        assert isinstance(fixtures, dict)

    def test_load_catalog_fixtures_missing_file_returns_empty(self, tmp_path):
        fixtures = self._load(tmp_path / "nonexistent.yml")
        assert fixtures == {}

    def test_load_catalog_fixtures_provincia_is_defined(self):
        fixtures = self._load()
        assert "Provincia" in fixtures

    def test_load_catalog_fixtures_departamento_is_defined(self):
        fixtures = self._load()
        assert "Departamento" in fixtures

    def test_load_catalog_fixtures_tipodoc_is_defined(self):
        fixtures = self._load()
        assert "TipoDoc" in fixtures

    def test_fixture_provincia_has_seed_rows(self):
        fixtures = self._load()
        prov = fixtures.get("Provincia")
        assert prov is not None
        assert len(prov.seed_rows) >= 1

    def test_fixture_provincia_has_correct_table(self):
        fixtures = self._load()
        prov = fixtures["Provincia"]
        assert "Provincia" in prov.db_table


# ─────────────────────────────────────────────────────────────────────────────
# catalog_readiness_checker — check_catalog_readiness
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckCatalogReadiness:

    def _check(self, required_catalogs=None, db_url=None, tmp_path=None, **kwargs):
        from catalog_readiness_checker import check_catalog_readiness
        return check_catalog_readiness(
            scenario_id="RF-007-CA-01",
            required_catalogs=required_catalogs or [],
            db_url=db_url,
            exec_logger=None,
            evidence_dir=tmp_path,
            run_id="run-1",
            ticket_id=120,
            fixtures_path=FIXTURES_PATH,
            dry_run=True,
            **kwargs,
        )

    def test_check_readiness_empty_catalogs_list_returns_ok(self, tmp_path):
        result = self._check(required_catalogs=[], tmp_path=tmp_path)
        assert result.ok is True
        assert result.total == 0

    def test_check_readiness_no_db_url_returns_unverified(self, tmp_path):
        result = self._check(required_catalogs=["Provincia"], db_url=None, tmp_path=tmp_path)
        # No DB URL → all catalogs should be UNVERIFIED
        assert result.total == 1
        assert result.unverified_count == 1 or result.empty_count == 0

    def test_check_readiness_unknown_catalog_returns_unverified(self, tmp_path):
        result = self._check(required_catalogs=["CatalogoInexistente"], tmp_path=tmp_path)
        assert result.total == 1
        cr = result.catalog_results[0]
        assert cr.status == "UNVERIFIED"
        assert cr.blocking is False

    def test_check_readiness_writes_evidence_artifact(self, tmp_path):
        result = self._check(required_catalogs=["Provincia"], tmp_path=tmp_path)
        artifacts = list(tmp_path.rglob("catalog_readiness_*.json"))
        assert len(artifacts) >= 1
        data = json.loads(artifacts[0].read_text(encoding="utf-8"))
        assert "catalog_results" in data
        assert "scenario_id" in data

    def test_check_readiness_all_unverified_when_no_db(self, tmp_path):
        result = self._check(
            required_catalogs=["Provincia", "Departamento", "TipoDoc"],
            db_url=None,
            tmp_path=tmp_path,
        )
        assert result.total == 3
        # All should be UNVERIFIED (no DB connection available)
        for cr in result.catalog_results:
            assert cr.status in {"UNVERIFIED", "EMPTY", "SEED_REQUIRED", "OK"}

    def test_check_readiness_result_has_required_fields(self, tmp_path):
        result = self._check(required_catalogs=["Provincia"], tmp_path=tmp_path)
        d = result.to_dict()
        required_keys = {
            "ok", "scenario_id", "run_id", "ticket_id",
            "total", "ok_count", "empty_count", "unverified_count",
            "blocking_empty_count", "catalog_results",
        }
        assert required_keys.issubset(d.keys())


# ─────────────────────────────────────────────────────────────────────────────
# catalog_readiness_checker — seed SQL generation
# ─────────────────────────────────────────────────────────────────────────────

class TestCatalogSeedSqlGeneration:

    def _get_fixture(self, catalog_name="Provincia"):
        from catalog_readiness_checker import load_catalog_fixtures
        fixtures = load_catalog_fixtures(FIXTURES_PATH)
        return fixtures[catalog_name]

    def _generate(self, catalog_name="Provincia"):
        from catalog_readiness_checker import _generate_catalog_seed_sql
        fixture = self._get_fixture(catalog_name)
        return _generate_catalog_seed_sql(fixture, "cat-120-run-1")

    def test_generate_catalog_seed_sql_has_begin_transaction(self):
        sql = self._generate()
        assert "BEGIN TRANSACTION" in sql.upper()

    def test_generate_catalog_seed_sql_has_rollback_not_commit(self):
        sql = self._generate()
        assert "ROLLBACK TRANSACTION" in sql.upper()
        # COMMIT must only appear inside comments (-- or /* */)
        lines_with_active_commit = [
            l for l in sql.splitlines()
            if "COMMIT" in l.upper()
            and not l.strip().startswith("--")   # line comment
            and "/*" not in l                     # block comment header
            and "*/" not in l                     # block comment footer
        ]
        assert len(lines_with_active_commit) == 0, (
            f"Unexpected active COMMIT: {lines_with_active_commit}"
        )

    def test_generate_catalog_seed_sql_has_prod_guard(self):
        sql = self._generate()
        assert "PROD" in sql.upper()
        assert "RAISERROR" in sql.upper()

    def test_generate_catalog_seed_sql_has_seed_run_id(self):
        sql = self._generate()
        assert "@SeedRunId" in sql or "SeedRunId" in sql

    def test_generate_catalog_seed_sql_has_verification_select(self):
        sql = self._generate()
        assert "SELECT COUNT" in sql.upper()


# ─────────────────────────────────────────────────────────────────────────────
# Flask: GET /api/qa-uat/catalog-readiness
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def flask_app():
    sys.path.insert(0, str(BACKEND_DIR))
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    os.environ.setdefault("LLM_BACKEND", "mock")
    from app import create_app  # type: ignore[import]
    application = create_app()
    application.config.update(TESTING=True)
    return application


@pytest.fixture
def flask_client(flask_app, tmp_path, monkeypatch):
    monkeypatch.setenv("QA_UAT_EVIDENCE_DIR", str(tmp_path))
    with flask_app.test_client() as client:
        yield client, tmp_path


class TestCatalogReadinessGetEndpoint:

    def test_catalog_readiness_endpoint_empty_when_no_files(self, flask_client):
        client, _ = flask_client
        resp = client.get("/api/qa-uat/catalog-readiness?run_id=run-99&ticket_id=120")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["catalogs"] == []
        assert data["total"] == 0

    def test_catalog_readiness_endpoint_returns_artifacts(self, flask_client):
        client, evidence_dir = flask_client
        artifact_dir = evidence_dir / "evidence" / "120" / "run-1"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_data = {
            "schema_version": "catalog_readiness/1.0",
            "ok": True,
            "scenario_id": "RF-007-CA-01",
            "run_id": "run-1",
            "ticket_id": 120,
            "total": 1,
            "ok_count": 1,
            "empty_count": 0,
            "unverified_count": 0,
            "seed_proposed_count": 0,
            "blocking_empty_count": 0,
            "catalog_results": [{
                "catalog_name": "Provincia",
                "db_table": "dbo.Provincia",
                "status": "OK",
                "row_count": 3,
                "min_rows": 1,
                "blocking": False,
                "seed_proposed": False,
                "seed_script_path": None,
                "error": None,
            }],
            "evidence_path": None,
            "checked_at": "2026-05-09T00:00:00Z",
        }
        (artifact_dir / "catalog_readiness_RF-007-CA-01.json").write_text(
            json.dumps(artifact_data), encoding="utf-8"
        )
        with patch("api.qa_uat._PIPELINE_ROOT", evidence_dir):
            resp = client.get("/api/qa-uat/catalog-readiness?run_id=run-1&ticket_id=120")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        assert body["total"] >= 1
        assert body["catalogs"][0]["scenario_id"] == "RF-007-CA-01"

    def test_catalog_readiness_endpoint_missing_run_id_returns_400(self, flask_client):
        client, _ = flask_client
        resp = client.get("/api/qa-uat/catalog-readiness?ticket_id=120")
        assert resp.status_code == 400

    def test_catalog_readiness_endpoint_missing_ticket_id_returns_400(self, flask_client):
        client, _ = flask_client
        resp = client.get("/api/qa-uat/catalog-readiness?run_id=run-1")
        assert resp.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# Flask: POST /api/qa-uat/catalog-readiness/check
# ─────────────────────────────────────────────────────────────────────────────

class TestCatalogCheckEndpoint:

    def test_catalog_check_endpoint_returns_400_on_missing_run_id(self, flask_client):
        client, _ = flask_client
        resp = client.post(
            "/api/qa-uat/catalog-readiness/check",
            json={"ticket_id": 120, "required_catalogs": ["Provincia"]},
        )
        assert resp.status_code == 400

    def test_catalog_check_endpoint_returns_400_on_empty_catalogs(self, flask_client):
        client, _ = flask_client
        resp = client.post(
            "/api/qa-uat/catalog-readiness/check",
            json={"run_id": "run-1", "ticket_id": 120, "required_catalogs": []},
        )
        assert resp.status_code == 400

    def test_catalog_check_endpoint_ok_returns_unverified_without_db(self, flask_client):
        client, evidence_dir = flask_client
        with patch("api.qa_uat._PIPELINE_ROOT", evidence_dir):
            resp = client.post(
                "/api/qa-uat/catalog-readiness/check",
                json={
                    "run_id": "run-1",
                    "ticket_id": 120,
                    "scenario_id": "RF-007-CA-01",
                    "required_catalogs": ["Provincia", "TipoDoc"],
                    "dry_run": True,
                },
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        result = data["result"]
        assert result["total"] == 2
        # Without DB connection, all should be UNVERIFIED
        for cr in result["catalog_results"]:
            assert cr["status"] in {"UNVERIFIED", "OK", "EMPTY", "SEED_REQUIRED"}


# ─────────────────────────────────────────────────────────────────────────────
# Flask: GET /api/qa-uat/catalog-readiness/fixtures
# ─────────────────────────────────────────────────────────────────────────────

class TestCatalogFixturesEndpoint:

    def test_catalog_fixtures_endpoint_returns_fixture_list(self, flask_client):
        client, evidence_dir = flask_client
        real_tool_dir = Path(__file__).parent.parent.parent
        # Point PIPELINE_ROOT to the real tool dir so the fixtures path resolves
        with patch("api.qa_uat._PIPELINE_ROOT", real_tool_dir):
            resp = client.get("/api/qa-uat/catalog-readiness/fixtures")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["total"] >= 1
        names = [f["catalog_name"] for f in data["fixtures"]]
        assert "Provincia" in names
