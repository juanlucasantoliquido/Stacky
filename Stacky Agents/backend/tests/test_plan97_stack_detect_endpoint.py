"""tests/test_plan97_stack_detect_endpoint.py — Plan 97 F2, endpoint /api/devops/detect-stack."""
import pytest


@pytest.fixture
def app_flag_off():
    """App con flag STACKY_DEVOPS_STACK_DETECT_ENABLED=False."""
    import config as cfg
    original = getattr(cfg.config, "STACKY_DEVOPS_STACK_DETECT_ENABLED", False)
    cfg.config.STACKY_DEVOPS_STACK_DETECT_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_STACK_DETECT_ENABLED = original


@pytest.fixture
def app_flag_on():
    """App con flag STACKY_DEVOPS_STACK_DETECT_ENABLED=True."""
    import config as cfg
    original = getattr(cfg.config, "STACKY_DEVOPS_STACK_DETECT_ENABLED", False)
    cfg.config.STACKY_DEVOPS_STACK_DETECT_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_STACK_DETECT_ENABLED = original


def test_flag_off_404(app_flag_off):
    client = app_flag_off.test_client()
    resp = client.get("/api/devops/detect-stack?project=x")
    assert resp.status_code == 404


def test_missing_project_400(app_flag_on):
    client = app_flag_on.test_client()
    resp = client.get("/api/devops/detect-stack")
    assert resp.status_code == 400


def test_unknown_project_returns_null_detected(app_flag_on, monkeypatch):
    monkeypatch.setattr("project_manager.get_project_config", lambda project: None)
    client = app_flag_on.test_client()
    resp = client.get("/api/devops/detect-stack?project=nope")
    assert resp.status_code == 200
    assert resp.get_json() == {"detected": None}


def test_detects_and_returns_stack(app_flag_on, monkeypatch, tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "project_manager.get_project_config",
        lambda project: {"workspace_root": str(tmp_path)},
    )
    client = app_flag_on.test_client()
    resp = client.get("/api/devops/detect-stack?project=demo")
    assert resp.status_code == 200
    assert resp.get_json() == {"detected": "node"}


def test_endpoint_uses_workspace_root_key(app_flag_on, monkeypatch, tmp_path):
    """C1 anti-verde-falso: si alguien vuelve a leer local_path/path, este test se pone rojo."""
    (tmp_path / "requirements.txt").write_text("flask\n", encoding="utf-8")
    monkeypatch.setattr(
        "project_manager.get_project_config",
        lambda project: {
            "workspace_root": str(tmp_path),
            "local_path": "/no/existe",
            "path": "/no/existe",
        },
    )
    client = app_flag_on.test_client()
    resp = client.get("/api/devops/detect-stack?project=demo")
    assert resp.status_code == 200
    assert resp.get_json() == {"detected": "python"}


def test_route_registered():
    from app import create_app
    app = create_app()
    rules = [r.rule for r in app.url_map.iter_rules()]
    assert "/api/devops/detect-stack" in rules
