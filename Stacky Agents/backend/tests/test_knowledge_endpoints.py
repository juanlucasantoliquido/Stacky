"""Plan 170 F5 — API Flask del flywheel (gating, contratos §4.8-§4.10, preview dry-run).

REGLA DURA: invoke_local_llm SIEMPRE monkeypatcheado — cero red.
"""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import runtime_paths
from services import incident_store, knowledge_store as ks

_BASE = "/api/evolution/knowledge"


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    import copilot_bridge
    monkeypatch.setattr(
        copilot_bridge, "invoke_local_llm",
        lambda **kw: SimpleNamespace(text='{"title": "Lección auto", "body": "cuerpo accionable distinto", "tags": []}'),
    )

    def _factory(flywheel=True, injection=True):
        import config as cfg
        monkeypatch.setattr(cfg.config, "STACKY_EVOLUTION_CENTER_ENABLED", True)
        monkeypatch.setattr(cfg.config, "STACKY_KNOWLEDGE_FLYWHEEL_ENABLED", flywheel)
        monkeypatch.setattr(cfg.config, "STACKY_KNOWLEDGE_INJECTION_ENABLED", injection)
        from app import create_app
        from db import init_db
        app = create_app()
        app.config["TESTING"] = True
        init_db()
        return app.test_client()

    return _factory


@pytest.fixture(autouse=True)
def _clean_db():
    yield
    try:
        from db import session_scope
        from models import AgentExecution, Ticket
        with session_scope() as s:
            s.query(AgentExecution).delete()
            s.query(Ticket).delete()
    except Exception:
        pass


def _seed(tmp_path, lesson_id, text, *, title=None, scope=None):
    ev = tmp_path / "evolution"
    ev.mkdir(parents=True, exist_ok=True)
    line = {"lesson_id": lesson_id, "aspect_id": "knowledge_rag", "text": text,
            "origin": "manual", "created_at": "2026-01-01T00:00:00+00:00"}
    with (ev / "lessons.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    ks.upsert_meta(lesson_id, title=title or text[:40], scope=scope)


def _published(text="reporte", tracker_id="900"):
    inc = incident_store.create_incident(text=text, files=[])
    incident_store.update_incident(inc["id"], status="publicada", tracker_id=tracker_id)
    return inc["id"]


# 1
def test_health_siempre_200(make_client):
    c_on = make_client(flywheel=True)
    r = c_on.get(f"{_BASE}/health")
    assert r.status_code == 200 and r.get_json()["flag_enabled"] is True
    c_off = make_client(flywheel=False)
    r2 = c_off.get(f"{_BASE}/health")
    assert r2.status_code == 200 and r2.get_json()["flag_enabled"] is False


# 2
def test_flag_off_404_literal(make_client):
    c = make_client(flywheel=False)
    r = c.get(f"{_BASE}/lessons")
    assert r.status_code == 404
    assert r.get_json()["error"] == "knowledge_disabled"


# 3
def test_lessons_lista_y_retiradas(make_client, tmp_path):
    c = make_client()
    _seed(tmp_path, "a1", "activa uno")
    _seed(tmp_path, "a2", "activa dos")
    ks.upsert_meta("ret", title="retirada")  # meta sin línea = retirada
    r = c.get(f"{_BASE}/lessons")
    assert len(r.get_json()["lessons"]) == 2
    r2 = c.get(f"{_BASE}/lessons?include_retired=true")
    assert len(r2.get_json()["lessons"]) == 3


# 4
def test_patch_lesson_scope(make_client, tmp_path):
    c = make_client()
    _seed(tmp_path, "p1", "cuerpo", title="orig")
    r = c.patch(f"{_BASE}/lessons/p1", json={"scope": {"agent_types": ["qa"]}})
    assert r.status_code == 200
    assert ks.read_meta()["p1"]["scope"]["agent_types"] == ["qa"]
    r2 = c.patch(f"{_BASE}/lessons/p1", json={"usage_count": 5})
    assert r2.status_code == 400


# 5
def test_candidates_shape(make_client, tmp_path):
    c = make_client()
    pid = _published()
    _published_capturada = incident_store.create_incident(text="otra", files=[])
    r = c.get(f"{_BASE}/harvest/candidates")
    data = r.get_json()
    assert [i["incident_id"] for i in data["incidents"]] == [pid]
    assert data["incidents"][0]["already_harvested"] is False
    assert data["optimizer_lessons"] == []
    c.post(f"{_BASE}/harvest/from-incident", json={"incident_id": pid})
    r2 = c.get(f"{_BASE}/harvest/candidates")
    assert r2.get_json()["incidents"][0]["already_harvested"] is True


# 6
def test_from_incident_201_y_409(make_client, tmp_path):
    c = make_client()
    pid = _published()
    r = c.post(f"{_BASE}/harvest/from-incident", json={"incident_id": pid})
    assert r.status_code == 201
    body = r.get_json()
    assert body["proposal"]["artifact_type"] == "knowledge_note"
    assert "auto_applied" in body
    # sembrar una lección activa idéntica al draft que devuelve el mock → 409
    _seed(tmp_path, "seed", "cuerpo accionable distinto", title="Lección auto")
    pid2 = _published(tracker_id="901")
    r2 = c.post(f"{_BASE}/harvest/from-incident", json={"incident_id": pid2})
    assert r2.status_code == 409
    assert r2.get_json()["error"] == "duplicate_suspect"
    assert r2.get_json()["duplicates"]


# 7
def test_from_optimizer_endpoint(make_client, monkeypatch):
    c = make_client()
    from services import evolution_optimizer_store as eos
    monkeypatch.setattr(eos, "read_lessons_tail", lambda aspect_key=None, limit=20: [
        {"id": "les-9", "run_id": "r-9", "aspect_key": "agent_prompts/qa",
         "text": "mejora", "outcome": "mejoro", "delta": 0.03},
        {"id": "les-bad", "run_id": "r-8", "aspect_key": "agent_prompts/qa",
         "text": "peor", "outcome": "empeoro", "delta": -0.02},
    ])
    r = c.post(f"{_BASE}/harvest/from-optimizer-lesson", json={"lesson_id": "les-9"})
    assert r.status_code == 201
    assert r.get_json()["proposal"]["origin"] == "optimizer"
    r2 = c.post(f"{_BASE}/harvest/from-optimizer-lesson", json={"lesson_id": "les-bad"})
    assert r2.status_code == 409
    assert r2.get_json()["error"] == "lesson_outcome_invalido"


# 8
def test_manual_endpoint(make_client):
    c = make_client()
    r = c.post(f"{_BASE}/harvest/manual", json={"title": "Título", "body": "Cuerpo accionable"})
    assert r.status_code == 201
    assert r.get_json()["proposal"]["origin"] == "manual"
    r2 = c.post(f"{_BASE}/harvest/manual", json={"title": "", "body": "x"})
    assert r2.status_code == 400
    assert r2.get_json()["error"] == "invalid_payload"


# 9
def test_to_eval_case_endpoint(make_client, tmp_path):
    c = make_client()
    _seed(tmp_path, "L1", "no repitas el patrón", title="Lección L1")
    r = c.post(f"{_BASE}/lessons/L1/to-eval-case")
    assert r.status_code == 201
    assert r.get_json()["case"]["enabled"] is False
    assert r.get_json()["case"]["origin"] == "lesson"
    r2 = c.post(f"{_BASE}/lessons/L1/to-eval-case")
    assert r2.status_code == 409
    assert r2.get_json()["error"] == "case_already_exists"


# 10
def test_overview_shape_y_tolerancia(make_client, tmp_path, monkeypatch):
    c = make_client()
    _seed(tmp_path, "ov1", "lección overview")
    r = c.get(f"{_BASE}/overview")
    d = r.get_json()
    assert r.status_code == 200
    for key in ("lessons", "coverage", "flywheel", "usage", "fitness_knowledge",
                "retire_suggestions"):
        assert key in d
    assert d["lessons"]["active"] == 1
    # case_store roto → overview igual 200 con fitness_knowledge nulls
    from evals import case_store
    def _boom(*a, **k):
        raise RuntimeError("case_store roto")
    monkeypatch.setattr(case_store, "read_runs_tail", _boom)
    r2 = c.get(f"{_BASE}/overview")
    assert r2.status_code == 200
    assert r2.get_json()["fitness_knowledge"]["latest_score"] is None


# 11
def test_injection_preview_no_cuenta_uso(make_client, tmp_path, monkeypatch):
    c = make_client()
    # store vacío → block null
    r0 = c.get(f"{_BASE}/injection-preview?agent_type=developer")
    assert r0.status_code == 200 and r0.get_json()["block"] is None
    _seed(tmp_path, "glob", "lección global", scope={"agent_types": []})
    _seed(tmp_path, "qa1", "lección qa", scope={"agent_types": ["qa"]})
    r = c.get(f"{_BASE}/injection-preview?agent_type=developer")
    d = r.get_json()
    assert d["matched_count"] == 1
    assert "lección global" in d["block"]["content"]
    assert "lección qa" not in d["block"]["content"]
    assert ks.get_lesson("glob")["usage_count"] == 0
    assert ks.get_lesson("qa1")["usage_count"] == 0
    import config as cfg
    monkeypatch.setattr(cfg.config, "STACKY_KNOWLEDGE_INJECTION_ENABLED", False)
    r2 = c.get(f"{_BASE}/injection-preview?agent_type=developer")
    assert r2.status_code == 200
