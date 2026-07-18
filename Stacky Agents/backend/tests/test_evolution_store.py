"""Plan 167 F1 — tests del store puro (14 casos).

Fixture común: monkeypatch de `runtime_paths.data_dir` a `tmp_path` (el store
llama `runtime_paths.data_dir()` en cada operación).
"""
import json

import pytest

import runtime_paths
from services import evolution_store as st


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    return tmp_path


def _make_proposal(**kw):
    base = dict(
        aspect_id="knowledge_rag", title="t", rationale="r",
        origin="manual", artifact_type="free_text",
    )
    base.update(kw)
    return st.create_proposal(**base)


def test_seed_aspects_idempotente():
    a1 = st.ensure_seed_aspects()
    a2 = st.ensure_seed_aspects()
    assert len(a1) == 4
    assert len(a2) == 4
    ids = sorted(a["id"] for a in a2)
    assert ids == ["agent_prompts", "config_flags_models", "knowledge_rag", "stacky_codebase"]


def test_create_proposal_shape_completo():
    p = _make_proposal()
    expected_keys = {
        "id", "aspect_id", "title", "rationale", "origin", "artifact_type",
        "target_ref", "proposed_content", "base_hash", "evidence", "status",
        "fitness_before", "fitness_after", "parent_proposal_id", "cycle_id",
        "snapshot_info", "notes", "created_at", "updated_at", "applied_at",
        "rolled_back_at",
    }
    assert set(p.keys()) == expected_keys
    assert p["fitness_before"] is None
    assert p["fitness_after"] is None
    assert p["parent_proposal_id"] is None
    assert p["id"].startswith("prop-")


def test_create_valida_aspect_inexistente():
    with pytest.raises(ValueError) as exc:
        _make_proposal(aspect_id="no_existe")
    assert "invalid_payload" in str(exc.value)


def test_create_prompt_file_exige_target_y_content():
    with pytest.raises(ValueError):
        st.create_proposal(aspect_id="agent_prompts", title="t", rationale="r",
                           origin="manual", artifact_type="prompt_file",
                           proposed_content="x")  # falta target_ref
    with pytest.raises(ValueError):
        st.create_proposal(aspect_id="agent_prompts", title="t", rationale="r",
                           origin="manual", artifact_type="prompt_file",
                           target_ref="Developer.agent.md")  # falta content


def test_create_origin_optimizer_ok():
    p = _make_proposal(origin="optimizer", parent_proposal_id="prop-parent")
    assert p["origin"] == "optimizer"
    assert p["parent_proposal_id"] == "prop-parent"
    fetched = st.get_proposal(p["id"])
    assert fetched is not None and fetched["origin"] == "optimizer"


def test_transiciones_validas_happy_path():
    p = _make_proposal(initial_status="draft", aspect_id="knowledge_rag",
                       artifact_type="knowledge_note", proposed_content="una leccion")
    st.transition(p["id"], "submit", actor="operator")
    st.transition(p["id"], "approve", actor="operator")
    applied = st.transition(p["id"], "apply", actor="operator")
    assert applied["status"] == "applied"
    assert applied["applied_at"] is not None
    rolled = st.transition(p["id"], "rollback", actor="operator")
    assert rolled["status"] == "rolled_back"
    assert rolled["rolled_back_at"] is not None


def test_transicion_invalida():
    p = _make_proposal(initial_status="draft")
    with pytest.raises(st.InvalidTransition):
        st.transition(p["id"], "apply", actor="operator")


def test_reject_archiva_no_borra():
    p = _make_proposal(initial_status="draft")
    st.transition(p["id"], "reject", actor="operator", note="no aplica")
    all_props = st.list_proposals()
    assert any(x["id"] == p["id"] and x["status"] == "rejected" for x in all_props)


def test_ledger_registra_cada_evento():
    p = _make_proposal(initial_status="draft", aspect_id="knowledge_rag",
                       artifact_type="knowledge_note", proposed_content="lx")
    st.transition(p["id"], "submit", actor="operator")
    st.transition(p["id"], "approve", actor="operator")
    st.transition(p["id"], "reject", actor="operator")
    events = st.read_ledger_tail(100)
    mine = [e for e in events if e["proposal_id"] == p["id"]]
    assert len(mine) == 4  # created + 3 transiciones
    for e in mine:
        assert set(e.keys()) == {"ts", "event", "proposal_id", "action", "from",
                                 "to", "actor", "note", "cycle_id"}


def test_ledger_y_cycles_tail_orden():
    for i in range(5):
        st.append_cycle({"id": f"cyc-{i}", "n": i})
    tail = st.read_cycles_tail(3)
    assert [c["n"] for c in tail] == [4, 3, 2]


def test_loop_mode_closed_loop_rechazado():
    with pytest.raises(ValueError) as exc:
        st.save_aspect({"id": "x", "name": "X", "target_kind": "link_only",
                        "loop_mode": "closed_loop", "links": []})
    assert "loop_mode_invalido" in str(exc.value)


def test_lecturas_tolerantes(_data_dir):
    root = _data_dir / "evolution"
    root.mkdir(parents=True, exist_ok=True)
    (root / "proposals.json").write_text("{ esto no es json valido", encoding="utf-8")
    assert st.list_proposals() == []


def test_update_fields_campo_protegido():
    p = _make_proposal()
    with pytest.raises(ValueError) as exc:
        st.update_proposal_fields(p["id"], status="applied")
    assert "campo_no_patcheable" in str(exc.value)
    # el status NO cambió
    assert st.get_proposal(p["id"])["status"] == "pending_review"
    # el ledger NO tiene evento nuevo (solo el 'created')
    events = [e for e in st.read_ledger_tail(100) if e["proposal_id"] == p["id"]]
    assert len(events) == 1
    # fitness_before SÍ es patcheable (contrato 168)
    updated = st.update_proposal_fields(
        p["id"], fitness_before={"score": 0.5, "metrics": {}, "eval_ref": "e1", "evaluated_at": "now"})
    assert updated["fitness_before"]["score"] == 0.5


def test_ledger_espejo_en_logs(caplog):
    with caplog.at_level("INFO", logger="stacky.evolution"):
        st.append_ledger({"event": "created", "proposal_id": "prop-abc",
                          "actor": "operator", "to": "draft"})
    assert any("prop-abc" in rec.getMessage() for rec in caplog.records)
