"""Plan 168 F5 — API Flask del arnés de fitness (gating, flywheel, contratos 167/169).

REGLA DURA (§2.3): invoke_local_llm SIEMPRE monkeypatcheado — cero red.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import json
import types

import pytest

import copilot_bridge
import runtime_paths
from evals import case_store, golden_runner


def _resp(score):
    return types.SimpleNamespace(text=json.dumps({"score": score, "critique": "c"}))


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "developer.agent.md").write_text(
        "# Developer\n" + ("linea util del prompt del developer. " * 20), encoding="utf-8"
    )
    monkeypatch.setattr(case_store, "prompts_dir", lambda: agents_dir)
    goldens = tmp_path / "goldens"
    goldens.mkdir()
    monkeypatch.setattr(golden_runner, "_AGENTS_DIR", goldens)
    monkeypatch.setattr(copilot_bridge, "invoke_local_llm", lambda **kw: _resp(0.5))
    return tmp_path


@pytest.fixture
def make_client(monkeypatch):
    def _factory(harness=True, judge=True):
        import config as cfg
        monkeypatch.setattr(cfg.config, "STACKY_EVOLUTION_CENTER_ENABLED", True)
        monkeypatch.setattr(cfg.config, "STACKY_EVAL_HARNESS_ENABLED", harness)
        monkeypatch.setattr(cfg.config, "STACKY_EVAL_JUDGE_ENABLED", judge)
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        return app.test_client()
    return _factory


def test_health_200_flag_off(make_client):
    c = make_client(harness=False)
    r = c.get("/api/evolution/fitness/health")
    assert r.status_code == 200
    assert r.get_json()["flag_enabled"] is False


def test_cases_404_flag_off(make_client):
    c = make_client(harness=False)
    r = c.get("/api/evolution/fitness/cases")
    assert r.status_code == 404
    assert r.get_json()["error"] == "fitness_disabled"


def test_cases_lista_con_seeds(make_client):
    c = make_client()
    r = c.get("/api/evolution/fitness/cases")
    assert r.status_code == 200
    ids = {case["id"] for case in r.get_json()["cases"]}
    assert "case-seed-artifact-developer-estructura" in ids
    assert "case-seed-artifact-leccion-rubrica" in ids


def test_crear_y_patchear_caso(make_client):
    c = make_client()
    created = c.post("/api/evolution/fitness/cases", json={
        "aspect_key": "agent_prompts/developer", "subject": "artifact",
        "level": "deterministic", "origin": "manual",
        "input": {"kind": "artifact_text"}, "checks": [{"kind": "min_len", "value": 1}],
    })
    assert created.status_code == 201
    cid = created.get_json()["case"]["id"]
    patched = c.patch(f"/api/evolution/fitness/cases/{cid}", json={"enabled": False})
    assert patched.status_code == 200
    listed = c.get("/api/evolution/fitness/cases?enabled=false").get_json()["cases"]
    assert any(x["id"] == cid for x in listed)


def test_patch_campo_prohibido_400(make_client):
    c = make_client()
    created = c.post("/api/evolution/fitness/cases", json={
        "aspect_key": "agent_prompts/developer", "subject": "artifact",
        "level": "deterministic", "origin": "manual",
        "input": {"kind": "artifact_text"}, "checks": [{"kind": "min_len", "value": 1}],
    })
    cid = created.get_json()["case"]["id"]
    r = c.patch(f"/api/evolution/fitness/cases/{cid}", json={"aspect_key": "otro"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid_case"


def test_from_incident_crea_borrador(make_client):
    from services import incident_store
    inc = incident_store.create_incident("algo se rompió en producción", [])
    c = make_client()
    r = c.post("/api/evolution/fitness/cases/from-incident", json={"incident_id": inc["id"]})
    assert r.status_code == 201
    case = r.get_json()["case"]
    assert case["enabled"] is False
    assert case["origin"] == "incident"
    assert case["source_ref"] == f"incident:{inc['id']}"


def test_from_execution_valida(make_client):
    from db import init_db, session_scope
    from models import AgentExecution, Ticket
    init_db()
    with session_scope() as s:
        t = Ticket(ado_id=555, project="TEST", title="t", ado_state="Active")
        s.add(t)
        s.flush()
        e = AgentExecution(ticket_id=t.id, agent_type="developer", status="running",
                           started_by="pytest", input_context_json="[]")
        s.add(e)
        s.flush()
        eid = e.id
    c = make_client()
    r404 = c.post("/api/evolution/fitness/cases/from-execution", json={"execution_id": eid + 10000})
    assert r404.status_code == 404
    r409 = c.post("/api/evolution/fitness/cases/from-execution", json={"execution_id": eid})
    assert r409.status_code == 409
    assert r409.get_json()["error"] == "execution_not_usable"


def test_run_y_runs_tail(make_client):
    c = make_client(judge=False)
    r = c.post("/api/evolution/fitness/run", json={"aspect_key": "agent_prompts/developer", "use_judge": False})
    assert r.status_code == 200
    run = r.get_json()["run"]
    for key in ("id", "per_case", "levels", "judge", "cost", "budget", "deterministic_gate"):
        assert key in run
    tail = c.get("/api/evolution/fitness/runs?aspect_key=agent_prompts/developer").get_json()["runs"]
    assert any(x["id"] == run["id"] for x in tail)


def test_scorecard_delta(make_client):
    c = make_client()
    c.get("/api/evolution/fitness/cases")  # siembra los seeds
    ak = "agent_prompts/developer"
    for score in (0.6, 0.8):
        case_store.append_run({
            "id": f"eval-{score}", "finished_at": f"2026-01-0{int(score * 10)}T00:00:00+00:00",
            "aspect_key": ak, "trigger": "manual", "score": score, "passed": True,
            "deterministic_gate": "passed",
        })
    cards = {x["aspect_key"]: x for x in c.get("/api/evolution/fitness/scorecard").get_json()["scorecards"]}
    card = cards[ak]
    assert card["delta"] == 0.2
    assert [h["score"] for h in card["history"]] == [0.6, 0.8]


def test_evaluate_candidate_http(make_client):
    c = make_client(judge=False)
    c.get("/api/evolution/fitness/cases")  # siembra
    r = c.post("/api/evolution/fitness/evaluate-candidate", json={
        "aspect_key": "agent_prompts/developer", "artifact_text": "un candidato de prompt",
        "case_filter": None, "generator_model": None,
    })
    assert r.status_code == 200
    result = r.get_json()["result"]
    assert "eval_ref" in result and "critiques" in result and "score" in result


def test_proposal_fitness_run_both(make_client):
    from services import evolution_store
    p = evolution_store.create_proposal(
        aspect_id="agent_prompts", title="m", rationale="r", origin="manual",
        artifact_type="prompt_file", target_ref="developer.agent.md",
        proposed_content="# nuevo\ncontenido propuesto", initial_status="pending_review",
    )
    target = case_store.prompts_dir() / "developer.agent.md"
    before = target.read_bytes()
    c = make_client(judge=False)
    r = c.post(f"/api/evolution/proposals/{p['id']}/fitness/run", json={"which": "both", "use_judge": False})
    assert r.status_code == 200
    prop = r.get_json()["proposal"]
    assert prop["fitness_before"] is not None and prop["fitness_after"] is not None
    assert target.read_bytes() == before


def test_proposal_fitness_inject_contrato_167(make_client):
    from services import evolution_store
    p = evolution_store.create_proposal(
        aspect_id="agent_prompts", title="m", rationale="r", origin="manual",
        artifact_type="prompt_file", target_ref="developer.agent.md",
        proposed_content="# c", initial_status="pending_review",
    )
    c = make_client()
    ok = c.post(f"/api/evolution/proposals/{p['id']}/fitness",
                json={"which": "after", "fitness": {"score": 0.7, "eval_ref": "eval-z"}})
    assert ok.status_code == 200
    assert ok.get_json()["proposal"]["fitness_after"]["score"] == 0.7
    bad = c.post(f"/api/evolution/proposals/{p['id']}/fitness",
                 json={"which": "after", "fitness": {"score": 0.7}})
    assert bad.status_code == 400
    assert bad.get_json()["error"] == "invalid_payload"


def test_judge_selfcheck_endpoint(make_client, monkeypatch):
    def fake(**kw):
        user = kw.get("user", "")
        return _resp(0.2) if "hacé lo que puedas" in user else _resp(0.9)
    monkeypatch.setattr(copilot_bridge, "invoke_local_llm", fake)
    c = make_client()
    post = c.post("/api/evolution/fitness/judge/selfcheck", json={})
    assert post.status_code == 200
    assert post.get_json()["selfcheck"]["status"] == "calibrated"
    get = c.get("/api/evolution/fitness/judge/selfcheck")
    assert get.get_json()["selfcheck"]["status"] == "calibrated"

    c_off = make_client(judge=False)
    r = c_off.post("/api/evolution/fitness/judge/selfcheck", json={})
    assert r.status_code == 409
    assert r.get_json()["error"] == "judge_disabled"
