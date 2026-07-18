"""Plan 167 F2 — tests del motor de aplicación/rollback/auto-apply (14 casos)."""
import hashlib
import json
import threading

import pytest

import runtime_paths
from services import evolution_store as st
from services import evolution_apply as ap


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def agents_dir(tmp_path, monkeypatch):
    d = tmp_path / "agents"
    d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ap, "agents_prompts_dir", lambda: d)
    return d


def _approved_note(**kw):
    base = dict(aspect_id="knowledge_rag", title="t", rationale="r", origin="manual",
                artifact_type="knowledge_note", proposed_content="una leccion",
                initial_status="draft")
    base.update(kw)
    p = st.create_proposal(**base)
    st.transition(p["id"], "submit", actor="operator")
    st.transition(p["id"], "approve", actor="operator")
    return st.get_proposal(p["id"])


def _approved_prompt(target_ref, content, base_hash=None):
    p = st.create_proposal(aspect_id="agent_prompts", title="t", rationale="r",
                           origin="manual", artifact_type="prompt_file",
                           target_ref=target_ref, proposed_content=content,
                           base_hash=base_hash, initial_status="draft")
    st.transition(p["id"], "submit", actor="operator")
    st.transition(p["id"], "approve", actor="operator")
    return st.get_proposal(p["id"])


def _lessons(tmp_path):
    path = tmp_path / "evolution" / "lessons.jsonl"
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_apply_knowledge_note_appendea_leccion(_data_dir):
    p = _approved_note()
    ap.apply_proposal(p["id"], actor="operator")
    lessons = _lessons(_data_dir)
    assert len(lessons) == 1
    assert lessons[0]["lesson_id"] == p["id"]
    fetched = st.get_proposal(p["id"])
    assert fetched["status"] == "applied"
    assert fetched["applied_at"] is not None


def test_rollback_knowledge_note_remueve_leccion(_data_dir):
    p = _approved_note()
    ap.apply_proposal(p["id"])
    ap.rollback_proposal(p["id"])
    assert _lessons(_data_dir) == []
    assert st.get_proposal(p["id"])["status"] == "rolled_back"


def test_apply_prompt_file_snapshot_y_escritura(agents_dir, _data_dir):
    target = agents_dir / "Developer.agent.md"
    target.write_text("CONTENIDO A", encoding="utf-8")
    p = _approved_prompt("Developer.agent.md", "CONTENIDO B")
    ap.apply_proposal(p["id"])
    assert target.read_text(encoding="utf-8") == "CONTENIDO B"
    snap = _data_dir / "evolution" / "snapshots" / p["id"] / "before_Developer.agent.md"
    assert snap.read_text(encoding="utf-8") == "CONTENIDO A"


def test_rollback_prompt_file_byte_identico(agents_dir, _data_dir):
    target = agents_dir / "Developer.agent.md"
    original = "CONTENIDO A\ncon acentos áéí y bytes\n"
    target.write_text(original, encoding="utf-8")
    original_bytes = target.read_bytes()
    p = _approved_prompt("Developer.agent.md", "CONTENIDO B")
    ap.apply_proposal(p["id"])
    ap.rollback_proposal(p["id"])
    assert target.read_bytes() == original_bytes  # KPI-3


def test_apply_prompt_file_ausente_y_rollback_borra(agents_dir):
    target = agents_dir / "QAUat1.agent.md"
    assert not target.exists()
    p = _approved_prompt("QAUat1.agent.md", "NUEVO")
    ap.apply_proposal(p["id"])
    assert target.exists() and target.read_text(encoding="utf-8") == "NUEVO"
    ap.rollback_proposal(p["id"])
    assert not target.exists()


def test_prompt_file_fuera_de_allowlist(agents_dir):
    p = _approved_prompt("../../config.py", "PWNED")
    with pytest.raises(ValueError) as exc:
        ap.apply_proposal(p["id"])
    assert "target_fuera_de_allowlist" in str(exc.value)


def test_apply_free_text_rechazado():
    p = st.create_proposal(aspect_id="stacky_codebase", title="t", rationale="r",
                           origin="manual", artifact_type="free_text",
                           initial_status="draft")
    st.transition(p["id"], "submit", actor="operator")
    st.transition(p["id"], "approve", actor="operator")
    with pytest.raises(ValueError) as exc:
        ap.apply_proposal(p["id"])
    assert "artifact_not_appliable" in str(exc.value)


def test_apply_desde_estado_no_aprobado():
    p = _approved_note(initial_status="draft")
    # crear otra en draft y apply directo
    d = st.create_proposal(aspect_id="knowledge_rag", title="t", rationale="r",
                           origin="manual", artifact_type="knowledge_note",
                           proposed_content="x", initial_status="draft")
    with pytest.raises(st.InvalidTransition):
        ap.apply_proposal(d["id"])


def test_auto_apply_flag_off_noop(monkeypatch):
    import config
    monkeypatch.setattr(config.config, "STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED", False)
    p = st.create_proposal(aspect_id="knowledge_rag", title="t", rationale="r",
                           origin="mape", artifact_type="knowledge_note",
                           proposed_content="x", initial_status="draft")
    assert ap.maybe_auto_apply(p) is False
    assert st.get_proposal(p["id"])["status"] == "draft"


def test_auto_apply_on_solo_knowledge(monkeypatch, _data_dir):
    import config
    monkeypatch.setattr(config.config, "STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED", True)
    note = st.create_proposal(aspect_id="knowledge_rag", title="t", rationale="r",
                              origin="mape", artifact_type="knowledge_note",
                              proposed_content="leccion auto", initial_status="draft")
    assert ap.maybe_auto_apply(note) is True
    fetched = st.get_proposal(note["id"])
    assert fetched["status"] == "applied"
    events = [e for e in st.read_ledger_tail(100) if e["proposal_id"] == note["id"]]
    assert any(e["actor"] == "auto_hotl" for e in events)
    # un prompt_file NO se toca (no está en la allowlist HOTL)
    pf = st.create_proposal(aspect_id="agent_prompts", title="t", rationale="r",
                            origin="mape", artifact_type="prompt_file",
                            target_ref="Developer.agent.md", proposed_content="x",
                            initial_status="draft")
    assert ap.maybe_auto_apply(pf) is False
    assert st.get_proposal(pf["id"])["status"] == "draft"


def test_doble_apply_secuencial_no_duplica(_data_dir):
    assert isinstance(ap._APPLY_LOCK, type(threading.Lock()))
    p = _approved_note()
    ap.apply_proposal(p["id"])
    with pytest.raises(st.InvalidTransition):
        ap.apply_proposal(p["id"])
    assert len(_lessons(_data_dir)) == 1


def test_apply_base_hash_drift(agents_dir):
    target = agents_dir / "Developer.agent.md"
    target.write_text("CONTENIDO A", encoding="utf-8")
    base_hash = hashlib.sha256("CONTENIDO A".encode("utf-8")).hexdigest()
    p = _approved_prompt("Developer.agent.md", "CONTENIDO B", base_hash=base_hash)
    # editar ANTES del apply
    target.write_text("CONTENIDO A PRIMA", encoding="utf-8")
    with pytest.raises(RuntimeError) as exc:
        ap.apply_proposal(p["id"])
    assert "target_drifted" in str(exc.value)
    assert target.read_text(encoding="utf-8") == "CONTENIDO A PRIMA"
    assert st.get_proposal(p["id"])["status"] == "approved"
    # con base_hash=None pasa (backward-compat)
    p2 = _approved_prompt("Developer.agent.md", "CONTENIDO C", base_hash=None)
    ap.apply_proposal(p2["id"])
    assert target.read_text(encoding="utf-8") == "CONTENIDO C"


def test_rollback_drift_requiere_force(agents_dir):
    target = agents_dir / "Developer.agent.md"
    target.write_text("CONTENIDO A", encoding="utf-8")
    p = _approved_prompt("Developer.agent.md", "CONTENIDO B")
    ap.apply_proposal(p["id"])
    assert target.read_text(encoding="utf-8") == "CONTENIDO B"
    # editar a mano DESPUÉS del apply
    target.write_text("CONTENIDO B PRIMA", encoding="utf-8")
    with pytest.raises(RuntimeError) as exc:
        ap.rollback_proposal(p["id"])
    assert "target_drifted" in str(exc.value)
    assert target.read_text(encoding="utf-8") == "CONTENIDO B PRIMA"
    # con force restaura el snapshot A byte-idéntico
    ap.rollback_proposal(p["id"], force=True)
    assert target.read_text(encoding="utf-8") == "CONTENIDO A"
    assert st.get_proposal(p["id"])["status"] == "rolled_back"


def test_hard_disable_bloquea_apply_y_hotl(monkeypatch):
    import config
    monkeypatch.setattr(config.config, "STACKY_EVOLUTION_AUTO_APPLY_KNOWLEDGE_ENABLED", True)
    monkeypatch.setenv("STACKY_EVOLUTION_HARD_DISABLE", "true")
    p = _approved_note()
    with pytest.raises(RuntimeError) as exc:
        ap.apply_proposal(p["id"])
    assert "evolution_hard_disabled" in str(exc.value)
    d = st.create_proposal(aspect_id="knowledge_rag", title="t", rationale="r",
                           origin="mape", artifact_type="knowledge_note",
                           proposed_content="x", initial_status="draft")
    assert ap.maybe_auto_apply(d) is False
