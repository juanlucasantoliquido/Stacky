"""Plan 163 F1 — identidad de build en app_version.py y /api/diag/health.

source_commit + built_at (manifest en deploy, git cacheado en dev) + repo_head
(vivo, solo dev, TTL) + build_drift. Cachés de módulo: la fixture autouse
resetea las 6 (C9 incluye _MANIFEST_PRESENT) antes de cada test.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/

import pytest

import services.app_version as app_version


@pytest.fixture(autouse=True)
def _reset_caches():
    """Resetea las 6 cachés de módulo antes de cada test (R9 / C9)."""
    app_version._CACHED_SOURCE_COMMIT = None
    app_version._SOURCE_COMMIT_RESOLVED = False
    app_version._CACHED_BUILT_AT = None
    app_version._BUILT_AT_RESOLVED = False
    app_version._REPO_HEAD_CACHE = None
    app_version._MANIFEST_PRESENT = None
    yield


def test_deploy_lee_manifest(monkeypatch, tmp_path):
    manifest = tmp_path / "release-manifest.json"
    manifest.write_text(
        '{"source_commit":"abc1234","generated_at":"2026-07-14 18:00:00"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(app_version, "_release_manifest_path", lambda: manifest)
    assert app_version.get_source_commit() == "abc1234"
    assert app_version.get_built_at() == "2026-07-14 18:00:00"


def test_dev_usa_git(monkeypatch):
    monkeypatch.setattr(app_version, "_read_manifest", lambda: None)
    monkeypatch.setattr(app_version, "_git_short_head", lambda: "deadbee")
    assert app_version.get_source_commit() == "deadbee"


def test_drift_true_cuando_head_difiere(monkeypatch):
    monkeypatch.setattr("runtime_paths.is_frozen", lambda: False)
    monkeypatch.setattr(app_version, "_manifest_present", lambda: False)
    monkeypatch.setattr(app_version, "get_source_commit", lambda: "aaa1111")
    monkeypatch.setattr(app_version, "_git_short_head", lambda: "bbb2222")
    app_version._REPO_HEAD_CACHE = None
    assert app_version.get_build_drift() is True


def test_drift_false_en_deploy(monkeypatch):
    monkeypatch.setattr("runtime_paths.is_frozen", lambda: True)
    assert app_version.get_repo_head() is None
    assert app_version.get_build_drift() is False


def test_health_expone_campos(monkeypatch):
    monkeypatch.setattr("project_manager.get_active_project", lambda: None)
    import app as app_module

    flask_app = app_module.create_app()
    flask_app.config.update(TESTING=True)
    client = flask_app.test_client()
    resp = client.get("/api/diag/health")
    assert resp.status_code == 200
    data = resp.get_json()
    for key in ("source_commit", "built_at", "repo_head", "build_drift"):
        assert key in data
