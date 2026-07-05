"""tests/test_plan89_environments_endpoints.py — F4 tests: POST
/api/devops/environments/plan y /apply (dry-run + HITL con confirm+fingerprint).
Patrón de fixtures: test_plan73_generator_endpoint.py:8-31; el LOADER se
patchea donde se usa: api.devops.load_client_profile (patrón 88 v2 C7).
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from services.environment_init import build_environment_layout, layout_fingerprint

_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "plan88_resolution_cases.json")
    .read_text(encoding="utf-8")
)
_CATALOG = _FIXTURE["catalog"]

_SETTINGS = {
    "environment_root": None,  # se completa por test con tmp_path
    "folder_layout": {
        "entry": ["IN_"],
        "processing": ["productivas"],
        "output": ["salida"],
        "default": [],
    },
    "per_process_subfolder": False,
}


@pytest.fixture
def app_flag_on():
    import config as cfg
    original = getattr(cfg.config, "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", False)
    cfg.config.STACKY_DEVOPS_ENVIRONMENTS_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_ENVIRONMENTS_ENABLED = original


@pytest.fixture
def app_flag_off():
    import config as cfg
    original = getattr(cfg.config, "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", False)
    cfg.config.STACKY_DEVOPS_ENVIRONMENTS_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_ENVIRONMENTS_ENABLED = original


def _profile(root):
    settings = dict(_SETTINGS)
    settings["environment_root"] = root
    return {"process_catalog": _CATALOG, "devops_environment_settings": settings}


def test_f4_plan_flag_off_404(app_flag_off, tmp_path):
    client = app_flag_off.test_client()
    with patch("api.devops.load_client_profile", return_value=_profile(str(tmp_path))):
        resp = client.post("/api/devops/environments/plan", json={"project": "RSPACIFICO"})
    assert resp.status_code == 404


def test_f4_apply_flag_off_404(app_flag_off, tmp_path):
    client = app_flag_off.test_client()
    with patch("api.devops.load_client_profile", return_value=_profile(str(tmp_path))):
        resp = client.post("/api/devops/environments/apply", json={
            "project": "RSPACIFICO", "confirm": True, "fingerprint": "x", "paths": ["IN_"],
        })
    assert resp.status_code == 404


def test_f4_plan_no_root_400(app_flag_on):
    client = app_flag_on.test_client()
    with patch("api.devops.load_client_profile", return_value={"process_catalog": _CATALOG}):
        resp = client.post("/api/devops/environments/plan", json={"project": "RSPACIFICO"})
    assert resp.status_code == 400
    assert resp.get_json()["kind"] == "environment_root_invalid"


def test_f4_plan_ok(app_flag_on, tmp_path):
    client = app_flag_on.test_client()
    with patch("api.devops.load_client_profile", return_value=_profile(str(tmp_path))):
        resp = client.post("/api/devops/environments/plan", json={"project": "RSPACIFICO"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["summary"]["to_create"] == 3
    assert isinstance(data["layout_fingerprint"], str) and data["layout_fingerprint"]
    assert "root_exists" in data


def test_f4_apply_without_confirm_400(app_flag_on, tmp_path):
    client = app_flag_on.test_client()
    with patch("api.devops.load_client_profile", return_value=_profile(str(tmp_path))):
        resp = client.post("/api/devops/environments/apply", json={
            "project": "RSPACIFICO", "fingerprint": "x", "paths": ["IN_"],
        })
    assert resp.status_code == 400
    resp2 = client.post("/api/devops/environments/apply", json={
        "project": "RSPACIFICO", "confirm": False, "fingerprint": "x", "paths": ["IN_"],
    })
    assert resp2.status_code == 400


def test_f4_apply_missing_fingerprint_400(app_flag_on, tmp_path):
    client = app_flag_on.test_client()
    with patch("api.devops.load_client_profile", return_value=_profile(str(tmp_path))):
        resp = client.post("/api/devops/environments/apply", json={
            "project": "RSPACIFICO", "confirm": True, "paths": ["IN_"],
        })
    assert resp.status_code == 400


def test_f4_apply_stale_fingerprint_409(app_flag_on, tmp_path):
    client = app_flag_on.test_client()
    root = str(tmp_path)
    with patch("api.devops.load_client_profile", return_value=_profile(root)):
        plan_resp = client.post("/api/devops/environments/plan", json={"project": "RSPACIFICO"})
    old_fp = plan_resp.get_json()["layout_fingerprint"]

    changed_settings = dict(_SETTINGS)
    changed_settings["environment_root"] = root
    changed_settings["folder_layout"] = dict(_SETTINGS["folder_layout"])
    changed_settings["folder_layout"]["entry"] = ["IN_NUEVO"]
    changed_profile = {"process_catalog": _CATALOG, "devops_environment_settings": changed_settings}

    with patch("api.devops.load_client_profile", return_value=changed_profile):
        apply_resp = client.post("/api/devops/environments/apply", json={
            "project": "RSPACIFICO", "confirm": True, "fingerprint": old_fp, "paths": ["IN_"],
        })
    assert apply_resp.status_code == 409
    assert apply_resp.get_json()["kind"] == "plan_stale"
    assert list(Path(root).iterdir()) == []


def test_f4_apply_creates_and_reports(app_flag_on, tmp_path):
    client = app_flag_on.test_client()
    root = str(tmp_path)
    profile = _profile(root)
    with patch("api.devops.load_client_profile", return_value=profile):
        plan_resp = client.post("/api/devops/environments/plan", json={"project": "RSPACIFICO"})
        fp = plan_resp.get_json()["layout_fingerprint"]
        apply_resp = client.post("/api/devops/environments/apply", json={
            "project": "RSPACIFICO", "confirm": True, "fingerprint": fp,
            "paths": ["IN_", "productivas", "salida"],
        })
    assert apply_resp.status_code == 200
    data = apply_resp.get_json()
    assert len(data["created"]) == 3
    for rel in ("IN_", "productivas", "salida"):
        assert (Path(root) / rel).is_dir()


def test_f4_apply_ignored_not_in_layout_visible(app_flag_on, tmp_path):
    client = app_flag_on.test_client()
    root = str(tmp_path)
    profile = _profile(root)
    with patch("api.devops.load_client_profile", return_value=profile):
        plan_resp = client.post("/api/devops/environments/plan", json={"project": "RSPACIFICO"})
        fp = plan_resp.get_json()["layout_fingerprint"]
        apply_resp = client.post("/api/devops/environments/apply", json={
            "project": "RSPACIFICO", "confirm": True, "fingerprint": fp,
            "paths": ["../evil", "no_layout_path"],
        })
    assert apply_resp.status_code == 200
    data = apply_resp.get_json()
    assert set(data["ignored_not_in_layout"]) == {"../evil", "no_layout_path"}
    assert data["created"] == []
    assert not (tmp_path.parent / "evil").exists()


def test_f4_rerun_idempotent(app_flag_on, tmp_path):
    client = app_flag_on.test_client()
    root = str(tmp_path)
    profile = _profile(root)
    with patch("api.devops.load_client_profile", return_value=profile):
        plan_resp = client.post("/api/devops/environments/plan", json={"project": "RSPACIFICO"})
        fp = plan_resp.get_json()["layout_fingerprint"]
        client.post("/api/devops/environments/apply", json={
            "project": "RSPACIFICO", "confirm": True, "fingerprint": fp,
            "paths": ["IN_", "productivas", "salida"],
        })
        plan_resp2 = client.post("/api/devops/environments/plan", json={"project": "RSPACIFICO"})
        fp2 = plan_resp2.get_json()["layout_fingerprint"]
        apply_resp2 = client.post("/api/devops/environments/apply", json={
            "project": "RSPACIFICO", "confirm": True, "fingerprint": fp2,
            "paths": ["IN_", "productivas", "salida"],
        })
    assert apply_resp2.get_json()["created"] == []
    assert all(e["status"] == "exists_ok" for e in plan_resp2.get_json()["entries"])


def test_f4_health_exposes_environments_enabled(app_flag_on):
    client = app_flag_on.test_client()
    resp = client.get("/api/devops/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "environments_enabled" in data
    assert isinstance(data["environments_enabled"], bool)
