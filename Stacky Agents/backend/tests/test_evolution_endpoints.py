"""Plan 167 F4 — tests de la API Flask (11 casos).

Fixtures app_flag_off/app_flag_on espejo de test_plan87_devops_endpoints.py,
cambiando el attr a STACKY_EVOLUTION_CENTER_ENABLED; + data_dir→tmp_path.
"""
import pytest

import runtime_paths


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def app_flag_off():
    import config as cfg
    original = getattr(cfg.config, "STACKY_EVOLUTION_CENTER_ENABLED", True)
    cfg.config.STACKY_EVOLUTION_CENTER_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_EVOLUTION_CENTER_ENABLED = original


@pytest.fixture
def app_flag_on():
    import config as cfg
    original = getattr(cfg.config, "STACKY_EVOLUTION_CENTER_ENABLED", True)
    cfg.config.STACKY_EVOLUTION_CENTER_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_EVOLUTION_CENTER_ENABLED = original


def _mock_monitor(monkeypatch):
    from services import cost_analytics, incident_store, plans_board
    monkeypatch.setattr(cost_analytics, "load_records", lambda f: [])
    monkeypatch.setattr(incident_store, "list_incidents", lambda: [])
    monkeypatch.setattr(plans_board, "get_board_cached",
                        lambda *a, **k: {"totals": {}, "plans": [], "next_free_number": 200})


def test_health_200_flag_off(app_flag_off):
    resp = app_flag_off.test_client().get("/api/evolution/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["flag_enabled"] is False


def test_overview_404_flag_off(app_flag_off):
    resp = app_flag_off.test_client().get("/api/evolution/overview")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "evolution_disabled"


def test_overview_200_con_seeds(app_flag_on):
    resp = app_flag_on.test_client().get("/api/evolution/overview")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["aspects"]) == 4
    assert set(data["counts"].keys()) == {
        "draft", "pending_review", "approved", "applied", "rejected", "rolled_back"}


def test_crear_y_listar_proposal(app_flag_on):
    client = app_flag_on.test_client()
    resp = client.post("/api/evolution/proposals", json={
        "aspect_id": "knowledge_rag", "title": "T", "rationale": "R",
        "artifact_type": "free_text", "origin": "manual"})
    assert resp.status_code == 201
    pid = resp.get_json()["proposal"]["id"]
    listed = client.get("/api/evolution/proposals").get_json()["proposals"]
    assert any(p["id"] == pid for p in listed)


def test_post_invalido_400(app_flag_on):
    resp = app_flag_on.test_client().post("/api/evolution/proposals", json={
        "aspect_id": "no_existe", "title": "T", "rationale": "R",
        "artifact_type": "free_text"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_payload"


def test_transition_flujo_completo(app_flag_on):
    client = app_flag_on.test_client()
    pid = client.post("/api/evolution/proposals", json={
        "aspect_id": "knowledge_rag", "title": "T", "rationale": "R",
        "artifact_type": "knowledge_note", "proposed_content": "una leccion",
        "initial_status": "draft"}).get_json()["proposal"]["id"]
    for action in ("submit", "approve", "apply"):
        resp = client.post(f"/api/evolution/proposals/{pid}/transition", json={"action": action})
        assert resp.status_code == 200, (action, resp.get_json())
    assert resp.get_json()["proposal"]["status"] == "applied"


def test_post_origin_optimizer(app_flag_on):
    client = app_flag_on.test_client()
    resp = client.post("/api/evolution/proposals", json={
        "aspect_id": "agent_prompts", "title": "T", "rationale": "R",
        "artifact_type": "free_text", "origin": "optimizer"})
    assert resp.status_code == 201
    pid = resp.get_json()["proposal"]["id"]
    events = client.get("/api/evolution/ledger").get_json()["events"]
    created = [e for e in events if e["proposal_id"] == pid and e["event"] == "created"]
    assert created and created[0]["actor"] == "optimizer"


def test_transition_invalida_409(app_flag_on):
    client = app_flag_on.test_client()
    pid = client.post("/api/evolution/proposals", json={
        "aspect_id": "knowledge_rag", "title": "T", "rationale": "R",
        "artifact_type": "free_text", "initial_status": "draft"}).get_json()["proposal"]["id"]
    resp = client.post(f"/api/evolution/proposals/{pid}/transition", json={"action": "approve"})
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "invalid_transition"


def test_cycle_run_gate_y_shape(app_flag_on, monkeypatch):
    import config as cfg
    client = app_flag_on.test_client()
    # CYCLE OFF → 404
    monkeypatch.setattr(cfg.config, "STACKY_EVOLUTION_CYCLE_ENABLED", False)
    resp_off = client.post("/api/evolution/cycle/run", json={"use_llm": False})
    assert resp_off.status_code == 404
    assert resp_off.get_json()["error"] == "evolution_cycle_disabled"
    # CYCLE ON + mocks del Monitor → 200 con claves §4.9
    monkeypatch.setattr(cfg.config, "STACKY_EVOLUTION_CYCLE_ENABLED", True)
    _mock_monitor(monkeypatch)
    resp_on = client.post("/api/evolution/cycle/run", json={"use_llm": False})
    assert resp_on.status_code == 200
    cycle = resp_on.get_json()["cycle"]
    for key in ("id", "started_at", "finished_at", "status", "rules_fired",
                "proposal_ids", "skipped_duplicate_rules", "llm_used",
                "tokens_est_in", "tokens_est_out", "signals_truncated"):
        assert key in cycle


def test_rutas_sin_doble_prefijo(app_flag_on):
    rules = {r.rule for r in app_flag_on.url_map.iter_rules()}
    assert "/api/evolution/overview" in rules
    assert "/api/api/evolution/overview" not in rules


def test_hard_disable_env_gana(app_flag_on, monkeypatch):
    monkeypatch.setenv("STACKY_EVOLUTION_HARD_DISABLE", "1")
    client = app_flag_on.test_client()
    resp_ov = client.get("/api/evolution/overview")
    assert resp_ov.status_code == 404
    assert resp_ov.get_json()["error"] == "evolution_disabled"
    health = client.get("/api/evolution/health").get_json()
    assert health["hard_disabled"] is True
