"""Plan 169 F4 — API Flask del optimizador (gating, contratos §4.8, KPI-5/KPI-6).

REGLA DURA (G14): _start_run_async monkeypatcheado a ejecución SÍNCRONA con generador y
fitness mockeados — cero red/subprocess/thread.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

import runtime_paths
from evals import case_store
from services import evolution_optimizer
from services import evolution_optimizer_store as store
from services import fitness_service
from services import variant_generator

_TARGET = "developer.agent.md"
_ASPECT = "agent_prompts/developer"


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    pdir = tmp_path / "agents"
    pdir.mkdir()
    (pdir / _TARGET).write_text("# Developer\n" + ("linea util. " * 30), encoding="utf-8")
    monkeypatch.setattr(case_store, "prompts_dir", lambda: pdir)
    # Fitness y generador mockeados (cero red).
    monkeypatch.setattr(fitness_service, "evaluate_candidate", lambda *a, **k: {
        "score": 0.9, "passed": True, "eval_ref": "eval-x", "per_case": [],
        "critiques": [], "cost": {}, "deterministic_gate": "passed",
    })
    monkeypatch.setattr(variant_generator, "generate", lambda **k: {
        "text": "VARIANTE", "lesson": None, "flag_suggestion": None, "model": "qwen",
        "tokens_est_in": 10, "tokens_est_out": 10, "error": None,
    })

    # _start_run_async → ejecución SÍNCRONA (G14).
    def _sync(run_id, *, rng=None):
        evolution_optimizer._run_optimization_sync(run_id, rng=rng)

    monkeypatch.setattr(evolution_optimizer, "_start_run_async", _sync)
    return tmp_path


@pytest.fixture
def make_client(monkeypatch):
    def _factory(optimizer=True, harness=True, generator_ready=True):
        import config as cfg
        monkeypatch.setattr(cfg.config, "STACKY_EVOLUTION_CENTER_ENABLED", True)
        monkeypatch.setattr(cfg.config, "STACKY_EVOLUTION_OPTIMIZER_ENABLED", optimizer)
        monkeypatch.setattr(cfg.config, "STACKY_EVAL_HARNESS_ENABLED", harness)
        monkeypatch.setattr(cfg.config, "STACKY_EVOLUTION_OPTIMIZER_GENERATOR", "local")
        monkeypatch.setattr(cfg.config, "LOCAL_LLM_ENDPOINT",
                            "http://x/v1" if generator_ready else "")
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        return app.test_client()
    return _factory


# 1
def test_health_200_flag_off(make_client):
    c = make_client(optimizer=False)
    r = c.get("/api/evolution/optimizer/health")
    assert r.status_code == 200
    assert r.get_json()["flag_enabled"] is False


# 2
def test_targets_404_flag_off(make_client):
    c = make_client(optimizer=False)
    r = c.get("/api/evolution/optimizer/targets")
    assert r.status_code == 404
    assert r.get_json()["error"] == "optimizer_disabled"  # KPI-6


# 3
def test_targets_lista(make_client):
    c = make_client()
    r = c.get("/api/evolution/optimizer/targets")
    assert r.status_code == 200
    refs = {t["target_ref"]: t for t in r.get_json()["targets"]}
    assert _TARGET in refs
    assert refs[_TARGET]["aspect_key"] == _ASPECT


# 4
def test_run_target_inexistente_404(make_client):
    c = make_client()
    r = c.post("/api/evolution/optimizer/run", json={"target_ref": "NoExiste.agent.md"})
    assert r.status_code == 404
    assert r.get_json()["error"] == "target_not_found"


# 5
def test_run_generator_unavailable_409(make_client):
    c = make_client(generator_ready=False)
    r = c.post("/api/evolution/optimizer/run", json={"target_ref": _TARGET})
    assert r.status_code == 409
    body = r.get_json()
    assert body["error"] == "generator_unavailable"
    assert "LOCAL_LLM_ENDPOINT" in body["message"]  # KPI-5, message literal


# 6
def test_run_harness_off_409(make_client):
    c = make_client(harness=False)
    r = c.post("/api/evolution/optimizer/run", json={"target_ref": _TARGET})
    assert r.status_code == 409
    assert r.get_json()["error"] == "fitness_harness_disabled"


# 7
def test_run_feliz_202_y_get(make_client):
    c = make_client()
    r = c.post("/api/evolution/optimizer/run", json={"target_ref": _TARGET, "use_judge": True})
    assert r.status_code == 202
    run = r.get_json()["run"]
    assert run["status"] != "running"  # C4 — estado REAL (async mockeado síncrono → terminal)
    rid = run["id"]
    g = c.get(f"/api/evolution/optimizer/runs/{rid}")
    assert g.status_code == 200
    assert g.get_json()["run"]["id"] == rid
    # rng_seed no entero → 400
    bad = c.post("/api/evolution/optimizer/run", json={"target_ref": _TARGET, "rng_seed": "x"})
    assert bad.status_code == 400
    assert bad.get_json()["error"] == "invalid_payload"


# 8
def test_run_already_running_409(make_client):
    store.create_run(aspect_key=_ASPECT, target_ref=_TARGET,
                     generator={"mode": "local", "runtime": None, "model": "q"},
                     variants_planned=3)
    c = make_client()
    r = c.post("/api/evolution/optimizer/run", json={"target_ref": _TARGET})
    assert r.status_code == 409
    assert r.get_json()["error"] == "optimizer_already_running"


# 9
def test_cancel(make_client):
    c = make_client()
    running = store.create_run(aspect_key=_ASPECT, target_ref=_TARGET,
                               generator={"mode": "local", "runtime": None, "model": "q"},
                               variants_planned=3)
    r = c.post(f"/api/evolution/optimizer/runs/{running['id']}/cancel")
    assert r.status_code == 200
    assert r.get_json()["run"]["cancel_requested"] is True
    store.update_run(running["id"], status="completed")
    r2 = c.post(f"/api/evolution/optimizer/runs/{running['id']}/cancel")
    assert r2.status_code == 409
    assert r2.get_json()["error"] == "run_not_running"
    r3 = c.post("/api/evolution/optimizer/runs/opt-nope/cancel")
    assert r3.status_code == 404


# 10
def test_runs_tail_y_archive(make_client):
    c = make_client()
    posted = c.post("/api/evolution/optimizer/run", json={"target_ref": _TARGET})
    rid = posted.get_json()["run"]["id"]
    runs = c.get("/api/evolution/optimizer/runs").get_json()["runs"]
    assert any(x["id"] == rid for x in runs)
    entries = c.get(f"/api/evolution/optimizer/archive?run_id={rid}").get_json()["entries"]
    kinds = {e["kind"] for e in entries}
    assert "base" in kinds and "variant" in kinds


# 11
def test_lessons_y_pareto(make_client):
    store.append_lesson(run_id="opt-x", aspect_key=_ASPECT, variant_id="var-1",
                        text="una leccion", outcome="mejoro", delta=0.03)
    store.update_pareto(_ASPECT, [{"variant_id": "var-1", "run_id": "opt-x", "score": 0.8,
                                   "cost_proxy": 50, "artifact_hash": "sha256:h"}])
    c = make_client()
    les = c.get(f"/api/evolution/optimizer/lessons?aspect_key={_ASPECT}")
    assert les.status_code == 200
    assert any(l["text"] == "una leccion" for l in les.get_json()["lessons"])
    front = c.get(f"/api/evolution/optimizer/pareto?aspect_key={_ASPECT}")
    assert front.status_code == 200
    assert len(front.get_json()["front"]) == 1
    missing = c.get("/api/evolution/optimizer/pareto")
    assert missing.status_code == 400
    assert missing.get_json()["error"] == "aspect_key_requerido"


# 12
def test_rutas_sin_doble_prefijo(make_client):
    c = make_client()
    from app import create_app
    app = create_app()
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/api/evolution/optimizer/health" in rules
    assert "/api/api/evolution/optimizer/health" not in rules
