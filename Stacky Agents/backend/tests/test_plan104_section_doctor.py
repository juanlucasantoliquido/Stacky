"""Plan 104 F2 — blueprint /api/devops/sections/<id>/doctor (tests primero).

Fixtures: patrón test_plan90_devops_agent_endpoints.py (DB real en memoria vía
init_db(), monkeypatch de agent_runner.run_agent en el módulo origen).
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest


@pytest.fixture
def app_on():
    import config as cfg
    orig_doctor = getattr(cfg.config, "STACKY_DEVOPS_SECTION_DOCTOR_ENABLED", False)
    orig_agent = getattr(cfg.config, "STACKY_DEVOPS_AGENT_ENABLED", False)
    orig_panel = getattr(cfg.config, "STACKY_DEVOPS_PANEL_ENABLED", False)
    orig_gen = getattr(cfg.config, "STACKY_PIPELINE_GENERATOR_ENABLED", False)
    cfg.config.STACKY_DEVOPS_SECTION_DOCTOR_ENABLED = True
    cfg.config.STACKY_DEVOPS_AGENT_ENABLED = True
    cfg.config.STACKY_DEVOPS_PANEL_ENABLED = True
    from app import create_app
    from db import init_db
    app = create_app()
    app.config["TESTING"] = True
    init_db()
    yield app
    cfg.config.STACKY_DEVOPS_SECTION_DOCTOR_ENABLED = orig_doctor
    cfg.config.STACKY_DEVOPS_AGENT_ENABLED = orig_agent
    cfg.config.STACKY_DEVOPS_PANEL_ENABLED = orig_panel
    cfg.config.STACKY_PIPELINE_GENERATOR_ENABLED = orig_gen


@pytest.fixture
def app_off():
    import config as cfg
    orig = getattr(cfg.config, "STACKY_DEVOPS_SECTION_DOCTOR_ENABLED", False)
    cfg.config.STACKY_DEVOPS_SECTION_DOCTOR_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_SECTION_DOCTOR_ENABLED = orig


def _c(app):
    return app.test_client()


def _spy_run_agent(monkeypatch, execution_id=123):
    import agent_runner
    captured = {}

    def _spy(**kw):
        captured.update(kw)
        return execution_id

    monkeypatch.setattr(agent_runner, "run_agent", _spy)
    return captured


# ── F0/F2 flag + validaciones básicas ───────────────────────────────────────

def test_flag_off_404(app_off):
    c = _c(app_off)
    r = c.post("/api/devops/sections/pipeline/doctor", json={"project": "p", "payload": {}, "confirm": True})
    assert r.status_code == 404


def test_agent_disabled_404(app_on):
    import config as cfg
    cfg.config.STACKY_DEVOPS_AGENT_ENABLED = False
    try:
        c = _c(app_on)
        r = c.post("/api/devops/sections/pipeline/doctor", json={"project": "p", "payload": {}})
        assert r.status_code == 404
        assert r.get_json()["error"] == "devops_agent_disabled"
    finally:
        cfg.config.STACKY_DEVOPS_AGENT_ENABLED = True


def test_unknown_section_404(app_on):
    c = _c(app_on)
    r = c.post("/api/devops/sections/inventada/doctor", json={"project": "p", "payload": {}})
    assert r.status_code == 404
    assert r.get_json()["error"] == "unknown_section"


def test_missing_project_400(app_on):
    c = _c(app_on)
    r = c.post("/api/devops/sections/pipeline/doctor", json={"payload": {}})
    assert r.status_code == 400


def test_missing_payload_400(app_on):
    c = _c(app_on)
    r = c.post("/api/devops/sections/pipeline/doctor", json={"project": "p"})
    assert r.status_code == 400


def test_runtime_no_soportado_400(app_on, monkeypatch):
    _spy_run_agent(monkeypatch)
    c = _c(app_on)
    r = c.post("/api/devops/sections/pipeline/doctor", json={"project": "p", "payload": {"spec": {}}, "runtime": "foo"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "runtime_no_soportado"


# ── Lanzamiento real (mock run_agent) ───────────────────────────────────────

def test_known_section_launches_agent(app_on, monkeypatch):
    captured = _spy_run_agent(monkeypatch)
    c = _c(app_on)
    r = c.post(
        "/api/devops/sections/pipeline/doctor",
        json={"project": "proj-x", "payload": {"spec": {"name": "p1"}}, "runtime": "codex_cli"},
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["ok"] is True
    assert body["execution_id"] == 123
    assert body["runtime"] == "codex_cli"
    assert body["section"] == "pipeline"
    assert captured["agent_type"] == "devops"
    assert "p1" in captured["context_blocks"][0]["content"]


def test_doctor_creates_anchor_ticket(app_on, monkeypatch):
    """[C1 BLOQUEANTE, anti-verde-falso]: crea un Ticket con ado_id=-3 ANTES de
    invocar run_agent, y pasa su id (NO None) como ticket_id."""
    captured = _spy_run_agent(monkeypatch)
    c = _c(app_on)
    r = c.post(
        "/api/devops/sections/pipeline/doctor",
        json={"project": "proj-anchor", "payload": {"spec": {}}},
    )
    assert r.status_code == 200
    body = r.get_json()
    ticket_id = body["conversation_id"]
    assert isinstance(ticket_id, int)

    assert captured["ticket_id"] == ticket_id
    assert captured["ticket_id"] is not None

    from db import session_scope
    from models import Ticket
    with session_scope() as session:
        ticket = session.query(Ticket).filter_by(id=ticket_id).first()
        assert ticket is not None
        assert ticket.ado_id == -3
        assert ticket.title == "Doctor DevOps · pipeline · proj-anchor"


def test_two_clicks_create_two_distinct_tickets(app_on, monkeypatch):
    _spy_run_agent(monkeypatch)
    c = _c(app_on)
    r1 = c.post("/api/devops/sections/pipeline/doctor", json={"project": "proj-two", "payload": {"spec": {}}})
    r2 = c.post("/api/devops/sections/pipeline/doctor", json={"project": "proj-two", "payload": {"spec": {}}})
    assert r1.status_code == 200 and r2.status_code == 200
    id1 = r1.get_json()["conversation_id"]
    id2 = r2.get_json()["conversation_id"]
    assert id1 != id2


def test_second_doctor_ticket_same_project_no_collision(app_on, monkeypatch):
    """[C10 BLOQUEANTE, anti-crash]: dos tickets doctor del MISMO proyecto +
    backfill real de init_db -> sin IntegrityError, external_id distintos."""
    _spy_run_agent(monkeypatch)
    c = _c(app_on)
    r1 = c.post("/api/devops/sections/pipeline/doctor", json={"project": "proj-collision", "payload": {"spec": {}}})
    r2 = c.post("/api/devops/sections/pipeline/doctor", json={"project": "proj-collision", "payload": {"spec": {}}})
    assert r1.status_code == 200 and r2.status_code == 200
    id1 = r1.get_json()["conversation_id"]
    id2 = r2.get_json()["conversation_id"]

    # Corre el backfill real (mismo camino que un próximo boot de la app).
    from db import init_db
    init_db()  # no debe lanzar IntegrityError

    from db import session_scope
    from models import Ticket
    with session_scope() as session:
        t1 = session.query(Ticket).filter_by(id=id1).first()
        t2 = session.query(Ticket).filter_by(id=id2).first()
        assert t1.external_id == -id1
        assert t2.external_id == -id2
        assert t1.external_id != t2.external_id
        assert t1.external_id < 0 and t2.external_id < 0


def test_route_registered():
    from app import create_app
    app = create_app()
    rules = [str(rule) for rule in app.url_map.iter_rules()]
    assert any("/api/devops/sections/<section_id>/doctor" in rule for rule in rules)


# ── YAML server-side (C16) ──────────────────────────────────────────────────

def test_pipeline_yaml_rendered_server_side(app_on, monkeypatch):
    import config as cfg
    cfg.config.STACKY_PIPELINE_GENERATOR_ENABLED = True
    captured = _spy_run_agent(monkeypatch)
    c = _c(app_on)
    minimal_spec = {
        "name": "mi-pipeline",
        "stages": [{
            "name": "build",
            "jobs": [{"name": "job1", "steps": [{"name": "compilar", "script": "echo hola"}]}],
        }],
    }
    r = c.post("/api/devops/sections/pipeline/doctor", json={"project": "p", "payload": {"spec": minimal_spec}})
    assert r.status_code == 200
    content = captured["context_blocks"][0]["content"]
    assert "stages" in content
    # El YAML renderizado (ADO usa 'stages:', GitLab usa 'stages:' también) debe
    # aparecer serializado dentro del payload -- verificamos que el job aparece.
    assert "job1" in content


def test_invalid_spec_yaml_degrades_null(app_on, monkeypatch):
    import config as cfg
    cfg.config.STACKY_PIPELINE_GENERATOR_ENABLED = True
    captured = _spy_run_agent(monkeypatch)
    c = _c(app_on)
    # spec inválido: "stages" no es una lista de dicts -> dict_to_spec explota
    invalid_spec = {"stages": "esto-no-es-una-lista-de-dicts"}
    r = c.post("/api/devops/sections/pipeline/doctor", json={"project": "p", "payload": {"spec": invalid_spec}})
    assert r.status_code == 200
    content = captured["context_blocks"][0]["content"]
    assert '"yaml_ado": null' in content
    assert '"yaml_gitlab": null' in content


def test_generator_off_no_yaml_render(app_on, monkeypatch):
    import config as cfg
    cfg.config.STACKY_PIPELINE_GENERATOR_ENABLED = False
    captured = _spy_run_agent(monkeypatch)
    c = _c(app_on)
    r = c.post("/api/devops/sections/pipeline/doctor", json={"project": "p", "payload": {"spec": {"name": "x"}}})
    assert r.status_code == 200
    content = captured["context_blocks"][0]["content"]
    assert "yaml_ado" not in content
    assert "yaml_gitlab" not in content


# ── Errores de lanzamiento ───────────────────────────────────────────────────

def test_unknown_agent_500(app_on, monkeypatch):
    import agent_runner

    def _raise(**kw):
        raise agent_runner.UnknownAgentError("devops")

    monkeypatch.setattr(agent_runner, "run_agent", _raise)
    c = _c(app_on)
    r = c.post("/api/devops/sections/pipeline/doctor", json={"project": "p", "payload": {"spec": {}}})
    assert r.status_code == 500
    assert r.get_json()["error"] == "devops_agent_not_registered"


def test_launch_failure_502(app_on, monkeypatch):
    import agent_runner

    def _raise(**kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(agent_runner, "run_agent", _raise)
    c = _c(app_on)
    r = c.post("/api/devops/sections/pipeline/doctor", json={"project": "p", "payload": {"spec": {}}})
    assert r.status_code == 502
    assert r.get_json()["error"] == "agent_launch_failed"
