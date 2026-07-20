"""Plan 169 F1 — store del optimizador (runs/archive/lessons/pareto + pareto_front + reaper).

Fixture común: data_dir → tmp_path (el store llama runtime_paths.data_dir() en cada op).
"""
import random
from datetime import datetime, timedelta, timezone

import pytest

import runtime_paths
from services import evolution_optimizer_store as store


@pytest.fixture(autouse=True)
def _tmp_data(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    return tmp_path


def _mk_run(**over):
    fields = dict(
        aspect_key="agent_prompts/developer", target_ref="Developer.agent.md",
        generator={"mode": "local", "runtime": None, "model": "qwen"},
        use_judge=True, variants_planned=3, margin_used=0.02,
        budget={"limit_tokens": 60000, "tokens_est_in": 0, "tokens_est_out": 0, "exhausted": False},
    )
    fields.update(over)
    return store.create_run(**fields)


def test_create_run_shape_completo():
    run = _mk_run()
    for key in ("id", "aspect_key", "target_ref", "status", "error", "cancel_requested",
                "generator", "use_judge", "variants_planned", "variants_done", "base",
                "winner", "proposal_id", "parent_proposal_id", "margin_used", "rng_seed",
                "base_hash", "budget", "steps", "started_at", "finished_at"):
        assert key in run, f"falta la clave {key}"
    assert run["status"] == "running"
    assert run["proposal_id"] is None
    assert run["id"].startswith("opt-")
    assert run["variants_done"] == 0


def test_create_run_valida_generador():
    with pytest.raises(ValueError):
        store.create_run(aspect_key="agent_prompts/x", target_ref="X.agent.md",
                         generator={"mode": "bogus"}, variants_planned=3)


def test_update_run_valida_claves():
    run = _mk_run()
    with pytest.raises(ValueError):
        store.update_run(run["id"], no_existe=1)
    with pytest.raises(ValueError):
        store.update_run(run["id"], status="terminado")
    with pytest.raises(KeyError):
        store.update_run("opt-nope", variants_done=1)


def test_request_cancel():
    run = _mk_run()
    updated = store.request_cancel(run["id"])
    assert updated["cancel_requested"] is True
    store.update_run(run["id"], status="completed")
    with pytest.raises(ValueError):
        store.request_cancel(run["id"])


def test_any_run_running():
    r1 = _mk_run()
    store.update_run(r1["id"], status="completed")
    assert store.any_run_running() is False
    _mk_run()
    assert store.any_run_running() is True


def test_archive_append_only_y_lineage():
    run = _mk_run()
    base = store.append_archive_entry(run_id=run["id"], aspect_key=run["aspect_key"],
                                      target_ref=run["target_ref"], kind="base",
                                      verdict="base", artifact_text="base texto",
                                      cost_proxy=10)
    for i in range(2):
        store.append_archive_entry(run_id=run["id"], aspect_key=run["aspect_key"],
                                   target_ref=run["target_ref"], kind="variant",
                                   verdict="dominated", parent_id=base["id"],
                                   artifact_text=f"var {i}", cost_proxy=12)
    entries = store.read_archive(run_id=run["id"])
    assert len(entries) == 3
    variants = [e for e in entries if e["kind"] == "variant"]
    assert all(v["parent_id"] == base["id"] for v in variants)
    # No existe API de delete: append-only garantizado por construcción.
    assert not hasattr(store, "delete_archive_entry")


def test_archive_trunca_texto_grande():
    run = _mk_run()
    big = "x" * 30000
    entry = store.append_archive_entry(run_id=run["id"], aspect_key=run["aspect_key"],
                                       target_ref=run["target_ref"], kind="variant",
                                       verdict="dominated", artifact_text=big, cost_proxy=1)
    assert entry["artifact_text"] is None
    assert entry["artifact_hash"] and entry["artifact_hash"].startswith("sha256:")


def _pt(vid, score, cost):
    return {"variant_id": vid, "score": score, "cost_proxy": cost}


def test_pareto_front_dominancia():
    pts = [_pt("a", 0.9, 100), _pt("b", 0.8, 50), _pt("c", 0.7, 200)]
    front = store.pareto_front(pts)
    ids = {p["variant_id"] for p in front}
    assert ids == {"a", "b"}  # c dominado por ambos


def test_pareto_front_empates():
    pts = [_pt("z", 0.8, 100), _pt("a", 0.8, 100)]
    front = store.pareto_front(pts)
    assert len(front) == 2
    # desempate final por variant_id ASC
    assert [p["variant_id"] for p in front] == ["a", "z"]


def test_pareto_none_score_excluido():
    pts = [_pt("a", 0.9, 100), _pt("b", None, 10)]
    front = store.pareto_front(pts)
    assert [p["variant_id"] for p in front] == ["a"]


def test_update_pareto_poda():
    # 10 puntos no dominados entre sí (score y cost crecientes juntos).
    pts = [_pt(f"v{i:02d}", 0.50 + i * 0.01, 100 + i * 10) for i in range(10)]
    front = store.update_pareto("agent_prompts/developer", pts)
    assert len(front) == 8
    scores = sorted(p["score"] for p in front)
    # se cayeron los 2 de MENOR score (0.50 y 0.51)
    assert scores[0] == pytest.approx(0.52)


def test_sample_parents_deterministico():
    pts = [{"variant_id": f"v{i}", "score": 0.5 + i * 0.05, "cost_proxy": 100 + i,
            "artifact_hash": f"sha256:h{i}"} for i in range(4)]
    store.update_pareto("agent_prompts/developer", pts)
    s1 = store.sample_parents("agent_prompts/developer", "sha256:h0", random.Random(42))
    s2 = store.sample_parents("agent_prompts/developer", "sha256:h0", random.Random(42))
    assert [p["variant_id"] for p in s1] == [p["variant_id"] for p in s2]
    assert all(p["artifact_hash"] != "sha256:h0" for p in s1)
    assert len(s1) <= 2


def test_lecturas_tolerantes(tmp_path):
    # runs.json y pareto.json corruptos → vacío sin excepción.
    (tmp_path / "evolution" / "optimizer").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evolution" / "optimizer" / "runs.json").write_text("{no json", encoding="utf-8")
    (tmp_path / "evolution" / "optimizer" / "pareto.json").write_text("]]]", encoding="utf-8")
    assert store.list_runs() == []
    assert store.get_pareto("agent_prompts/developer") == []
    # archive.jsonl: 1 línea válida + 1 basura → solo la válida (C9, no vacía el archivo).
    ap = tmp_path / "evolution" / "optimizer" / "archive.jsonl"
    ap.write_text('{"run_id": "opt-1", "kind": "base", "verdict": "base"}\n<<<basura>>>\n',
                  encoding="utf-8")
    got = store.read_archive(run_id="opt-1")
    assert len(got) == 1
    assert got[0]["run_id"] == "opt-1"


def test_stale_run_reaper():
    fresh = _mk_run()
    stale = _mk_run()
    old_iso = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    store.update_run(stale["id"], started_at=old_iso)
    assert store.any_run_running() is True  # el fresco sigue running
    reaped = store.get_run(stale["id"])
    assert reaped["status"] == "error"
    assert reaped["error"] == "stale_run_reaped"
    assert reaped["finished_at"] is not None
    assert store.get_run(fresh["id"])["status"] == "running"


def test_append_step_cap_60():
    run = _mk_run()
    for i in range(70):
        store.append_step(run["id"], f"paso {i}")
    steps = store.get_run(run["id"])["steps"]
    assert len(steps) == 60
    assert steps[59]["text"] == "log truncado"
    # los appends posteriores (61..70) fueron no-op: el paso 58 sigue siendo real.
    assert steps[58]["text"] == "paso 58"
