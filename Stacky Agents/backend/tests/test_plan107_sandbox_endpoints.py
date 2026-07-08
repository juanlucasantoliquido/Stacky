"""tests/test_plan107_sandbox_endpoints.py — F2: root_override + sandbox_ack en
/api/devops/environments/plan y /apply. Patrón de fixtures: idéntico a
test_plan89_environments_endpoints.py (LOADER patcheado en api.devops.load_client_profile).
"""
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

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


def _profile(root):
    settings = dict(_SETTINGS)
    settings["environment_root"] = root
    return {"process_catalog": _CATALOG, "devops_environment_settings": settings}


@pytest.fixture
def app_sandbox_off():
    """ENVIRONMENTS_ENABLED=True (para no 404 en /plan,/apply) + SANDBOX_ENABLED=False (default)."""
    import config as cfg
    orig_env = getattr(cfg.config, "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", False)
    orig_sandbox = getattr(cfg.config, "STACKY_DEVOPS_ENV_SANDBOX_ENABLED", False)
    cfg.config.STACKY_DEVOPS_ENVIRONMENTS_ENABLED = True
    cfg.config.STACKY_DEVOPS_ENV_SANDBOX_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_ENVIRONMENTS_ENABLED = orig_env
    cfg.config.STACKY_DEVOPS_ENV_SANDBOX_ENABLED = orig_sandbox


@pytest.fixture
def app_sandbox_on():
    """ENVIRONMENTS_ENABLED=True + SANDBOX_ENABLED=True."""
    import config as cfg
    orig_env = getattr(cfg.config, "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", False)
    orig_sandbox = getattr(cfg.config, "STACKY_DEVOPS_ENV_SANDBOX_ENABLED", False)
    cfg.config.STACKY_DEVOPS_ENVIRONMENTS_ENABLED = True
    cfg.config.STACKY_DEVOPS_ENV_SANDBOX_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_ENVIRONMENTS_ENABLED = orig_env
    cfg.config.STACKY_DEVOPS_ENV_SANDBOX_ENABLED = orig_sandbox


def test_plan_without_override_is_bytewise_like_today(app_sandbox_off, tmp_path):
    """Sin root_override, /plan se comporta EXACTO a Plan 89 salvo la key
    aditiva sandbox_active=False."""
    client = app_sandbox_off.test_client()
    root = str(tmp_path)
    with patch("api.devops.load_client_profile", return_value=_profile(root)):
        resp = client.post("/api/devops/environments/plan", json={"project": "RSPACIFICO"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["root"] == root
    assert data["summary"]["to_create"] == 3
    assert isinstance(data["layout_fingerprint"], str) and data["layout_fingerprint"]
    assert data["sandbox_active"] is False


def test_plan_override_rejected_when_flag_off(app_sandbox_off, tmp_path):
    client = app_sandbox_off.test_client()
    prod = str(tmp_path / "prod")
    sandbox = str(tmp_path / "sandbox")
    with patch("api.devops.load_client_profile", return_value=_profile(prod)):
        resp = client.post("/api/devops/environments/plan", json={
            "project": "RSPACIFICO", "root_override": sandbox,
        })
    assert resp.status_code == 400
    assert resp.get_json()["kind"] == "sandbox_disabled"


def test_plan_override_overlapping_rejected(app_sandbox_on, tmp_path):
    client = app_sandbox_on.test_client()
    prod = str(tmp_path / "prod")
    override = str(tmp_path / "prod" / "sub")  # dentro de produccion
    with patch("api.devops.load_client_profile", return_value=_profile(prod)):
        resp = client.post("/api/devops/environments/plan", json={
            "project": "RSPACIFICO", "root_override": override,
        })
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["kind"] == "sandbox_invalid"
    assert data["reason"] == "sandbox_dentro_de_produccion"


def test_plan_override_valid_uses_sandbox_root(app_sandbox_on, tmp_path):
    client = app_sandbox_on.test_client()
    prod = str(tmp_path / "prod")
    sandbox = str(tmp_path / "sandbox")  # hermano disjunto
    with patch("api.devops.load_client_profile", return_value=_profile(prod)):
        resp = client.post("/api/devops/environments/plan", json={
            "project": "RSPACIFICO", "root_override": sandbox,
        })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["root"] == sandbox
    assert data["sandbox_active"] is True


def test_apply_override_requires_ack(app_sandbox_on, tmp_path):
    client = app_sandbox_on.test_client()
    prod = str(tmp_path / "prod")
    sandbox = str(tmp_path / "sandbox")
    with patch("api.devops.load_client_profile", return_value=_profile(prod)):
        resp = client.post("/api/devops/environments/apply", json={
            "project": "RSPACIFICO", "confirm": True, "fingerprint": "x",
            "paths": ["IN_"], "root_override": sandbox,
        })
    assert resp.status_code == 400
    assert resp.get_json()["kind"] == "sandbox_ack_required"


def test_apply_override_creates_in_sandbox_only(app_sandbox_on, tmp_path):
    client = app_sandbox_on.test_client()
    prod_dir = tmp_path / "prod"
    prod_dir.mkdir()
    sandbox_dir = tmp_path / "sandbox"
    prod = str(prod_dir)
    sandbox = str(sandbox_dir)
    with patch("api.devops.load_client_profile", return_value=_profile(prod)):
        plan_resp = client.post("/api/devops/environments/plan", json={
            "project": "RSPACIFICO", "root_override": sandbox,
        })
        fp = plan_resp.get_json()["layout_fingerprint"]
        apply_resp = client.post("/api/devops/environments/apply", json={
            "project": "RSPACIFICO", "confirm": True, "fingerprint": fp,
            "paths": ["IN_", "productivas", "salida"],
            "root_override": sandbox, "sandbox_ack": True,
        })
    assert apply_resp.status_code == 200
    data = apply_resp.get_json()
    assert len(data["created"]) == 3
    assert data["sandbox_active"] is True
    for rel in ("IN_", "productivas", "salida"):
        assert (sandbox_dir / rel).is_dir()
        assert not (prod_dir / rel).exists()


def test_apply_fingerprint_stale_on_sandbox(app_sandbox_on, tmp_path):
    """Fingerprint calculado sobre produccion (sin override) no sirve para
    aplicar contra el sandbox -> 409 plan_stale (layout_fingerprint incluye
    abspath(root))."""
    client = app_sandbox_on.test_client()
    prod = str(tmp_path / "prod")
    sandbox = str(tmp_path / "sandbox")
    with patch("api.devops.load_client_profile", return_value=_profile(prod)):
        prod_plan_resp = client.post("/api/devops/environments/plan", json={"project": "RSPACIFICO"})
        stale_fp = prod_plan_resp.get_json()["layout_fingerprint"]
        apply_resp = client.post("/api/devops/environments/apply", json={
            "project": "RSPACIFICO", "confirm": True, "fingerprint": stale_fp,
            "paths": ["IN_"], "root_override": sandbox, "sandbox_ack": True,
        })
    assert apply_resp.status_code == 409
    assert apply_resp.get_json()["kind"] == "plan_stale"
