"""tests/test_plan88_materialize_endpoint.py — F3 tests: POST
/api/devops/publications/materialize (solo-lectura) + health key
publications_enabled. Patron de fixtures: test_plan73_generator_endpoint.py:8-31.
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "plan88_resolution_cases.json")
    .read_text(encoding="utf-8")
)


@pytest.fixture
def app_flag_on():
    import config as cfg
    original = getattr(cfg.config, "STACKY_DEVOPS_PUBLICATIONS_ENABLED", False)
    cfg.config.STACKY_DEVOPS_PUBLICATIONS_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_PUBLICATIONS_ENABLED = original


@pytest.fixture
def app_flag_off():
    import config as cfg
    original = getattr(cfg.config, "STACKY_DEVOPS_PUBLICATIONS_ENABLED", False)
    cfg.config.STACKY_DEVOPS_PUBLICATIONS_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_PUBLICATIONS_ENABLED = original


_TODO_PRESET = {"name": "todo-completo", "mode": "todo", "groups": [], "target": "gitlab"}


def test_f3_flag_off_404(app_flag_off):
    client = app_flag_off.test_client()
    resp = client.post("/api/devops/publications/materialize",
                        json={"project": "RSPACIFICO", "preset_name": "todo-completo"})
    assert resp.status_code == 404


def test_f3_missing_params_400(app_flag_on):
    client = app_flag_on.test_client()
    resp = client.post("/api/devops/publications/materialize", json={"preset_name": "x"})
    assert resp.status_code == 400
    resp2 = client.post("/api/devops/publications/materialize", json={"project": "RSPACIFICO"})
    assert resp2.status_code == 400


def test_f3_preset_not_found_404(app_flag_on):
    client = app_flag_on.test_client()
    with patch("api.devops.load_client_profile", return_value={"devops_publication_presets": []}):
        resp = client.post("/api/devops/publications/materialize",
                            json={"project": "RSPACIFICO", "preset_name": "no-existe"})
    assert resp.status_code == 404
    assert resp.get_json()["kind"] == "preset_not_found"


def test_f3_materialize_ok(app_flag_on):
    client = app_flag_on.test_client()
    profile = {
        "devops_publication_presets": [_TODO_PRESET],
        "process_catalog": _FIXTURE["catalog"],
    }
    with patch("api.devops.load_client_profile", return_value=profile):
        resp = client.post("/api/devops/publications/materialize",
                            json={"project": "RSPACIFICO", "preset_name": "todo-completo"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["resolved"]) == 6
    assert data["spec"]["name"].startswith("publicacion-")


def test_f3_corrupt_presets_no_500(app_flag_on):
    client = app_flag_on.test_client()
    with patch("api.devops.load_client_profile", return_value={"devops_publication_presets": {"no": "lista"}}):
        resp = client.post("/api/devops/publications/materialize",
                            json={"project": "RSPACIFICO", "preset_name": "todo-completo"})
    assert resp.status_code == 404
    assert resp.get_json()["kind"] == "preset_not_found"

    with patch("api.devops.load_client_profile", return_value={"devops_publication_presets": ["str1", "str2"]}):
        resp2 = client.post("/api/devops/publications/materialize",
                             json={"project": "RSPACIFICO", "preset_name": "todo-completo"})
    assert resp2.status_code == 404
    assert resp2.get_json()["kind"] == "preset_not_found"


def test_f3_readonly_no_writes(app_flag_on):
    client = app_flag_on.test_client()
    profile = {
        "devops_publication_presets": [_TODO_PRESET],
        "process_catalog": _FIXTURE["catalog"],
    }
    with patch("api.devops.load_client_profile", return_value=profile), \
         patch("services.client_profile.save_client_profile") as mock_save:
        resp = client.post("/api/devops/publications/materialize",
                            json={"project": "RSPACIFICO", "preset_name": "todo-completo"})
    assert resp.status_code == 200
    mock_save.assert_not_called()


def test_f3_health_exposes_publications_enabled(app_flag_on):
    client = app_flag_on.test_client()
    resp = client.get("/api/devops/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "publications_enabled" in data
    assert isinstance(data["publications_enabled"], bool)
