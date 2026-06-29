"""Tests F5 — endpoints /preview y /commit. Plan 73."""
from unittest.mock import MagicMock, patch
import pytest


# ── Fixture de app con flag ON ─────────────────────────────────────────────────

@pytest.fixture
def app_flag_on():
    """Flask app con STACKY_PIPELINE_GENERATOR_ENABLED=True."""
    import config as cfg
    original = getattr(cfg.config, "STACKY_PIPELINE_GENERATOR_ENABLED", False)
    cfg.config.STACKY_PIPELINE_GENERATOR_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_PIPELINE_GENERATOR_ENABLED = original


@pytest.fixture
def app_flag_off():
    """Flask app con STACKY_PIPELINE_GENERATOR_ENABLED=False."""
    import config as cfg
    original = getattr(cfg.config, "STACKY_PIPELINE_GENERATOR_ENABLED", False)
    cfg.config.STACKY_PIPELINE_GENERATOR_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_PIPELINE_GENERATOR_ENABLED = original


_VALID_SPEC = {
    "name": "my-pipeline",
    "stages": [
        {"name": "build", "jobs": [{"name": "build-job", "steps": [{"name": "s", "script": "make"}]}]}
    ],
}

_INVALID_SPEC = {
    "name": "",  # nombre vacío → error de validación
    "stages": [],
}


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_f5_flag_off_preview_404(app_flag_off):
    """Flag OFF → /preview devuelve 404 (guard per-request)."""
    with app_flag_off.test_client() as c:
        r = c.post("/api/pipeline-generator/preview", json=_VALID_SPEC)
        assert r.status_code == 404


def test_f5_flag_off_commit_404(app_flag_off):
    """Flag OFF → /commit devuelve 404 (guard per-request)."""
    with app_flag_off.test_client() as c:
        r = c.post("/api/pipeline-generator/commit", json={"confirm": True, **_VALID_SPEC})
        assert r.status_code == 404


def test_f5_preview_valid_spec(app_flag_on):
    """/preview con spec válido → 200 con 'ado' y 'gitlab'."""
    with app_flag_on.test_client() as c:
        r = c.post("/api/pipeline-generator/preview", json=_VALID_SPEC)
        assert r.status_code == 200
        data = r.get_json()
        assert "ado" in data
        assert "gitlab" in data
        assert isinstance(data["ado"], str)
        assert isinstance(data["gitlab"], str)


def test_f5_preview_invalid_spec(app_flag_on):
    """/preview con spec inválido → 400 con errors (field/message)."""
    with app_flag_on.test_client() as c:
        r = c.post("/api/pipeline-generator/preview", json=_INVALID_SPEC)
        assert r.status_code == 400
        data = r.get_json()
        assert "errors" in data
        assert all("field" in e and "message" in e for e in data["errors"])


def test_f5_commit_without_confirm_returns_400(app_flag_on):
    """[HITL GATE] /commit sin confirm → 400; commit_file NUNCA se llama."""
    with app_flag_on.test_client() as c:
        with patch("api.pipeline_generator.get_repo_writer") as mock_gw:
            mock_writer = MagicMock()
            mock_gw.return_value = mock_writer
            r = c.post("/api/pipeline-generator/commit", json={**_VALID_SPEC, "target": "gitlab"})
            assert r.status_code == 400
            mock_writer.commit_file.assert_not_called()


def test_f5_commit_with_confirm_true(app_flag_on):
    """/commit con confirm=True → llama commit_file; response con sha/branch/status."""
    with app_flag_on.test_client() as c:
        with patch("api.pipeline_generator.get_repo_writer") as mock_gw:
            mock_writer = MagicMock()
            mock_writer.commit_file.return_value = {
                "sha": "abc123", "branch": "main", "path": ".gitlab-ci.yml",
                "web_url": "https://gitlab.com/commit/abc", "status": "create",
            }
            mock_gw.return_value = mock_writer
            r = c.post("/api/pipeline-generator/commit", json={
                **_VALID_SPEC, "confirm": True, "target": "gitlab",
            })
            assert r.status_code == 200
            data = r.get_json()
            assert data["sha"] == "abc123"
            mock_writer.commit_file.assert_called_once()


def test_f5_commit_branch_slug(app_flag_on):
    """/commit sin branch explícito → branch slugificado de spec.name con espacios/mayúsculas (C11)."""
    with app_flag_on.test_client() as c:
        with patch("api.pipeline_generator.get_repo_writer") as mock_gw:
            mock_writer = MagicMock()
            mock_writer.commit_file.return_value = {
                "sha": "x", "branch": "feature/pipeline-my-pipeline", "path": ".gitlab-ci.yml",
                "web_url": "", "status": "create",
            }
            mock_gw.return_value = mock_writer
            spec_with_spaces = {**_VALID_SPEC, "name": "My Pipeline", "confirm": True, "target": "gitlab"}
            r = c.post("/api/pipeline-generator/commit", json=spec_with_spaces)
            assert r.status_code == 200
            call_kwargs = mock_writer.commit_file.call_args
            branch_used = call_kwargs[1].get("branch") or call_kwargs[0][2]
            # branch debe ser nombre git válido (sin espacios/mayúsculas)
            import re
            assert re.match(r"^[a-zA-Z0-9._\-/]+$", branch_used), f"branch inválido: {branch_used}"
            assert "my" in branch_used.lower() or "pipeline" in branch_used.lower()


def test_f5_c1_tracker_api_error_403(app_flag_on):
    """[C1] commit_file lanza TrackerApiError(403) → response 403 con kind."""
    from services.tracker_provider import TrackerApiError
    with app_flag_on.test_client() as c:
        with patch("api.pipeline_generator.get_repo_writer") as mock_gw:
            mock_writer = MagicMock()
            mock_writer.commit_file.side_effect = TrackerApiError(403, "forbidden", kind="forbidden")
            mock_gw.return_value = mock_writer
            r = c.post("/api/pipeline-generator/commit", json={
                **_VALID_SPEC, "confirm": True, "target": "gitlab",
            })
            assert r.status_code == 403
            data = r.get_json()
            assert "kind" in data


def test_f5_c12_ado_not_implemented_501(app_flag_on):
    """[C12] commit_file ADO lanza NotImplementedError → response 501."""
    with app_flag_on.test_client() as c:
        with patch("api.pipeline_generator.get_repo_writer") as mock_gw:
            mock_writer = MagicMock()
            mock_writer.commit_file.side_effect = NotImplementedError("ADO commit no implementado en v1")
            mock_gw.return_value = mock_writer
            r = c.post("/api/pipeline-generator/commit", json={
                **_VALID_SPEC, "confirm": True, "target": "ado",
            })
            assert r.status_code == 501
