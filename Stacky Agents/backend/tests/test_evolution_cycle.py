"""Plan 167 F3 — tests del ciclo MAPE (12 casos).

Fixture: data_dir→tmp_path + mocks benignos de las 3 fuentes del Monitor.
Cada test que necesita disparar una regla sobreescribe su fuente.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import runtime_paths
from services import evolution_store as st
from services import evolution_cycle as cyc


def _rec(agent_type, status, cost_usd=0.0, cost_kind="unknown", model="m"):
    return SimpleNamespace(
        agent_type=agent_type, status=status,
        row=SimpleNamespace(cost_usd=cost_usd, cost_kind=cost_kind, model=model),
    )


def _benign_board():
    return {"totals": {"total": 0, "PROPUESTO": 0, "CRITICADO": 0, "unpushed": 0},
            "plans": [], "next_free_number": 200}


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    from services import cost_analytics, incident_store, plans_board
    monkeypatch.setattr(cost_analytics, "load_records", lambda f: [])
    monkeypatch.setattr(incident_store, "list_incidents", lambda: [])
    monkeypatch.setattr(plans_board, "get_board_cached", lambda *a, **k: _benign_board())
    return tmp_path


def _set_records(monkeypatch, records):
    from services import cost_analytics
    monkeypatch.setattr(cost_analytics, "load_records", lambda f: records)


def _set_incidents(monkeypatch, items):
    from services import incident_store
    monkeypatch.setattr(incident_store, "list_incidents", lambda: items)


def _set_board(monkeypatch, board):
    from services import plans_board
    monkeypatch.setattr(plans_board, "get_board_cached", lambda *a, **k: board)


def test_collect_signals_shape():
    s = cyc.collect_signals()
    assert set(s.keys()) == {"generated_at", "window_days", "executions", "costs", "incidents", "plans"}
    assert set(s["executions"].keys()) == {"total", "by_agent_type"}
    assert set(s["costs"].keys()) == {"total_usd", "by_model", "top_model", "top_model_share"}
    assert set(s["incidents"].keys()) == {"total", "non_terminal", "stale_48h"}
    assert set(s["plans"].keys()) == {"total", "propuestos", "criticados", "drift", "unpushed", "next_free_number"}


def test_fuente_caida_no_tumba(monkeypatch):
    from services import incident_store
    def _boom():
        raise RuntimeError("db caida")
    monkeypatch.setattr(incident_store, "list_incidents", _boom)
    s = cyc.collect_signals()
    assert "error" in s["incidents"]
    assert set(s["plans"].keys()) == {"total", "propuestos", "criticados", "drift", "unpushed", "next_free_number"}
    assert "error" not in s["executions"]


def test_ra1_error_rate(monkeypatch):
    records = (
        [_rec("developer", "completed")] * 3
        + [_rec("developer", "error")] * 2
        + [_rec("developer", "failed")]  # C4: failed cuenta como error
    )
    _set_records(monkeypatch, records)
    rec = cyc.run_cycle(use_llm=False)
    assert "R-A1" in rec["rules_fired"]
    props = st.list_proposals()
    assert len(props) == 1
    assert props[0]["aspect_id"] == "agent_prompts"
    assert props[0]["evidence"][0] == "R-A1"


def test_ra2_concentracion_costo(monkeypatch):
    records = [
        _rec("a", "completed", cost_usd=0.7, cost_kind="reported", model="caro"),
        _rec("a", "completed", cost_usd=0.3, cost_kind="reported", model="barato"),
    ]
    _set_records(monkeypatch, records)
    rec = cyc.run_cycle(use_llm=False)
    assert "R-A2" in rec["rules_fired"]
    props = st.list_proposals()
    assert any(p["aspect_id"] == "config_flags_models" and p["evidence"][0] == "R-A2" for p in props)


def test_ra3_incidencias_stale(monkeypatch):
    old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    items = [{"id": f"inc-{i}", "title": f"t{i}", "status": "en_proceso", "created_at": old}
             for i in range(3)]
    _set_incidents(monkeypatch, items)
    rec = cyc.run_cycle(use_llm=False)
    assert "R-A3" in rec["rules_fired"]
    props = st.list_proposals()
    p = next(x for x in props if x["evidence"][0] == "R-A3")
    assert p["artifact_type"] == "knowledge_note"
    assert p["proposed_content"]


def test_ra4_drift_planes(monkeypatch):
    board = _benign_board()
    board["plans"] = [
        {"number": 1, "ledger": {"doc_drift": True}},
        {"number": 2, "ledger": {"doc_drift": True}},
        {"number": 3, "ledger": {"doc_drift": False}},
    ]
    _set_board(monkeypatch, board)
    rec = cyc.run_cycle(use_llm=False)
    assert "R-A4" in rec["rules_fired"]
    props = st.list_proposals()
    assert any(p["aspect_id"] == "stacky_codebase" and p["evidence"][0] == "R-A4" for p in props)


def test_sin_senales_sin_drafts():
    rec = cyc.run_cycle(use_llm=False)
    assert rec["rules_fired"] == []
    assert st.list_proposals() == []


def test_llm_no_configurado_degrada(monkeypatch):
    _set_records(monkeypatch, [_rec("developer", "error")] * 5 + [_rec("developer", "completed")])
    import copilot_bridge
    def _boom(**kw):
        raise RuntimeError("LOCAL_LLM_ENDPOINT no está configurado")
    monkeypatch.setattr(copilot_bridge, "invoke_local_llm", _boom)
    rec = cyc.run_cycle(use_llm=True)
    assert rec["llm_used"] is False
    assert rec["llm_error"] is not None
    props = st.list_proposals()
    assert len(props) == 1 and props[0]["evidence"][0] == "R-A1"


def test_llm_reescribe_solo_titulo_rationale(monkeypatch):
    _set_records(monkeypatch, [_rec("developer", "error")] * 5 + [_rec("developer", "completed")])
    import copilot_bridge
    def _fake(**kw):
        return SimpleNamespace(
            text='{"proposals": [{"index": 0, "title": "TITULO NUEVO", "rationale": "RATIONALE NUEVO"}]}')
    monkeypatch.setattr(copilot_bridge, "invoke_local_llm", _fake)
    cyc.run_cycle(use_llm=True)
    p = st.list_proposals()[0]
    assert p["title"] == "TITULO NUEVO"
    assert p["rationale"] == "RATIONALE NUEVO"
    assert p["aspect_id"] == "agent_prompts"
    assert p["artifact_type"] == "free_text"
    assert p["evidence"][0] == "R-A1"


def test_presupuesto_trunca(monkeypatch):
    _set_records(monkeypatch, [_rec("developer", "error")] * 5 + [_rec("developer", "completed")])
    import config
    monkeypatch.setattr(config.config, "STACKY_EVOLUTION_CYCLE_TOKEN_BUDGET", 5)
    captured = {}
    import copilot_bridge
    def _fake(**kw):
        captured["user"] = kw["user"]
        return SimpleNamespace(text="{}")
    monkeypatch.setattr(copilot_bridge, "invoke_local_llm", _fake)
    rec = cyc.run_cycle(use_llm=True)
    assert rec["signals_truncated"] is True
    assert len(captured["user"]) <= 5 * 4 + len("[TRUNCADO_POR_PRESUPUESTO]")


def test_single_flight():
    assert cyc._CYCLE_LOCK.acquire(blocking=False) is True
    try:
        with pytest.raises(RuntimeError) as exc:
            cyc.run_cycle(use_llm=False)
        assert "cycle_already_running" in str(exc.value)
    finally:
        cyc._CYCLE_LOCK.release()


def test_ciclo_dedup_no_duplica_drafts(monkeypatch):
    _set_records(monkeypatch, [_rec("developer", "error")] * 5 + [_rec("developer", "completed")])
    rec1 = cyc.run_cycle(use_llm=False)
    assert rec1["rules_fired"] == ["R-A1"]
    rec2 = cyc.run_cycle(use_llm=False)
    assert rec2["rules_fired"] == []
    assert rec2["skipped_duplicate_rules"] == ["R-A1"]
    assert len(st.list_proposals()) == 1
