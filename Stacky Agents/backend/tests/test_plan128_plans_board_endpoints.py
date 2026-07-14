"""tests/test_plan128_plans_board_endpoints.py — F3 tests (blueprint /api/plans-board)."""
import json

import pytest


# Fixtures COPIADAS del patrón real tests/test_plan87_devops_endpoints.py:6-29
@pytest.fixture
def app_flag_off():
    import config as cfg
    original = getattr(cfg.config, "STACKY_PLANS_BOARD_ENABLED", False)
    cfg.config.STACKY_PLANS_BOARD_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_PLANS_BOARD_ENABLED = original


@pytest.fixture
def app_flag_on():
    import config as cfg
    original = getattr(cfg.config, "STACKY_PLANS_BOARD_ENABLED", False)
    cfg.config.STACKY_PLANS_BOARD_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_PLANS_BOARD_ENABLED = original


def test_health_200_flag_off(app_flag_off):
    client = app_flag_off.test_client()
    resp = client.get("/api/plans-board/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["flag_enabled"] is False


def test_health_200_flag_on(app_flag_on):
    client = app_flag_on.test_client()
    resp = client.get("/api/plans-board/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["flag_enabled"] is True


def test_list_404_flag_off(app_flag_off):
    client = app_flag_off.test_client()
    resp = client.get("/api/plans-board/list")
    assert resp.status_code == 404
    data = resp.get_json()
    assert data["error"] == "plans_board_disabled"


def test_list_200_flag_on(app_flag_on):
    client = app_flag_on.test_client()
    resp = client.get("/api/plans-board/list")
    assert resp.status_code == 200
    data = resp.get_json()
    for key in ("ok", "generated_at", "docs_dir_found", "git_available", "next_free_number", "totals", "plans"):
        assert key in data


def test_detail_404_not_found(app_flag_on):
    client = app_flag_on.test_client()
    resp = client.get("/api/plans-board/detail/99999")
    assert resp.status_code == 404
    data = resp.get_json()
    assert data["error"] == "plan_not_found"


def test_refresh_invalida_cache(app_flag_on, monkeypatch):
    from services import plans_board

    counter = {"n": 0}
    original_build_board = plans_board.build_board

    def _counting_build_board(*args, **kwargs):
        counter["n"] += 1
        return original_build_board(*args, **kwargs)

    monkeypatch.setattr(plans_board, "build_board", _counting_build_board)
    plans_board._BOARD_CACHE = None

    client = app_flag_on.test_client()
    client.get("/api/plans-board/list")
    client.get("/api/plans-board/list")
    assert counter["n"] == 1

    client.get("/api/plans-board/list?refresh=1")
    assert counter["n"] == 2


def test_rutas_sin_doble_prefijo(app_flag_on):
    rules = [r.rule for r in app_flag_on.url_map.iter_rules()]
    assert "/api/plans-board/list" in rules
    assert "/api/api/plans-board/list" not in rules


def test_health_next_free_number_sin_gate(app_flag_off, monkeypatch, tmp_path):
    from services import plans_board

    (tmp_path / "10_PLAN_A.md").write_text("x", encoding="utf-8")
    (tmp_path / "20_PLAN_B.md").write_text("x", encoding="utf-8")
    monkeypatch.setattr(plans_board, "docs_dir_default", lambda: tmp_path)

    client = app_flag_off.test_client()
    resp = client.get("/api/plans-board/health")
    data = resp.get_json()
    assert data["next_free_number"] == 21

    missing_dir = tmp_path / "does_not_exist"
    monkeypatch.setattr(plans_board, "docs_dir_default", lambda: missing_dir)
    resp2 = client.get("/api/plans-board/health")
    assert resp2.get_json()["next_free_number"] is None
