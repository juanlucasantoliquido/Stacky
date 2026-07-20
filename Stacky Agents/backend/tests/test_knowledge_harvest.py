"""Plan 170 F2 — cosecha: 3 fuentes + degradación LLM + PII total + gate del 167.

TODO test que alcance el redactor monkeypatchea copilot_bridge.invoke_local_llm.
Ningún test abre red (guard del 154 + STACKY_TEST_MODE).
"""
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
from services import incident_store, knowledge_harvest as kh, knowledge_store as ks


@pytest.fixture
def _env(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    from db import init_db
    init_db()
    return tmp_path


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


def _mock_llm(monkeypatch, *, body_json=None, raise_exc=None, capture=None):
    import copilot_bridge

    def _fake(*, agent_type, system, user, on_log, execution_id=None, model=None):
        if capture is not None:
            capture["user"] = user
        if raise_exc is not None:
            raise raise_exc
        return SimpleNamespace(text=body_json)

    monkeypatch.setattr(copilot_bridge, "invoke_local_llm", _fake)


def _published(text="reporte de la incidencia", tracker_id="777"):
    inc = incident_store.create_incident(text=text, files=[])
    incident_store.update_incident(inc["id"], status="publicada", tracker_id=tracker_id)
    return incident_store.get_incident(inc["id"])


# 1
def test_from_incident_crea_propuesta_pending(_env, monkeypatch):
    _mock_llm(monkeypatch, body_json='{"title": "Titulo", "body": "Cuerpo accionable", "tags": ["x"]}')
    inc = _published()
    out = kh.harvest_from_incident(inc["id"])
    p = out["proposal"]
    assert p["artifact_type"] == "knowledge_note"
    assert p["aspect_id"] == "knowledge_rag"
    assert p["origin"] == "agent"
    assert p["status"] == "pending_review"
    assert p["proposed_content"] == "Cuerpo accionable"
    assert p["evidence"][:2] == [f"incident:{inc['id']}", "harvest:llm_local"]
    meta = ks.read_meta()[p["id"]]
    assert meta["source"]["kind"] == "incident"


# 2
def test_from_incident_no_publicada_rechaza(_env, monkeypatch):
    _mock_llm(monkeypatch, body_json='{"title":"t","body":"b","tags":[]}')
    inc = incident_store.create_incident(text="x", files=[])
    with pytest.raises(ValueError, match="incident_not_harvestable"):
        kh.harvest_from_incident(inc["id"])


# 3
def test_from_incident_inexistente(_env):
    with pytest.raises(KeyError, match="incident_not_found"):
        kh.harvest_from_incident("inc-no-existe")


# 4
def test_degradacion_sin_llm(_env, monkeypatch):
    _mock_llm(monkeypatch, raise_exc=RuntimeError("LOCAL_LLM_ENDPOINT vacío"))
    inc = _published()
    out = kh.harvest_from_incident(inc["id"])
    p = out["proposal"]
    assert "harvest:plantilla" in p["evidence"]
    assert "Regla:" in p["proposed_content"]


# 5
def test_root_cause_del_dev_run(_env, monkeypatch):
    from db import session_scope
    from models import AgentExecution, Ticket
    with session_scope() as s:
        t = Ticket(ado_id=777, project="P", title="T")
        s.add(t)
        s.flush()
        s.add(AgentExecution(
            ticket_id=t.id, agent_type="incident_dev", status="completed",
            input_context_json="[]", started_by="test",
            output="CAUSA RAIZ: el archivo x rompe por y\nARCHIVOS MODIFICADOS: x.py",
        ))
    cap = {}
    _mock_llm(monkeypatch, body_json='{"title":"t","body":"b","tags":[]}', capture=cap)
    spy_calls = []
    import services.pii_masker as pm
    real = pm.redact_irreversible
    monkeypatch.setattr(pm, "redact_irreversible", lambda t: spy_calls.append(t) or real(t))
    inc = _published(tracker_id="777")
    out = kh.harvest_from_incident(inc["id"])
    assert "el archivo x rompe por y" in cap["user"]
    assert any(e.startswith("execution:") for e in out["proposal"]["evidence"])
    assert any("CAUSA RAIZ" in c for c in spy_calls)  # el output pasó por el masker


# 6
def test_dedup_bloquea_y_force_pasa(_env, monkeypatch):
    # sembrar lección activa similar
    ev = _env / "evolution"
    ev.mkdir(parents=True, exist_ok=True)
    import json
    with (ev / "lessons.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"lesson_id": "prop-seed", "aspect_id": "knowledge_rag",
                             "text": "No uses eval con input del usuario",
                             "origin": "manual", "created_at": "2026-01-01T00:00:00+00:00"}) + "\n")
    ks.upsert_meta("prop-seed", title="No uses eval con input externo")
    _mock_llm(monkeypatch, body_json='{"title": "No uses eval con input externo", "body": "cuerpo", "tags": []}')
    inc = _published()
    with pytest.raises(kh.DuplicateSuspect):
        kh.harvest_from_incident(inc["id"])
    out = kh.harvest_from_incident(inc["id"], force=True)
    assert out["duplicates"]


# 7
def test_auto_apply_respetado(_env, monkeypatch):
    _mock_llm(monkeypatch, body_json='{"title":"t","body":"b","tags":[]}')
    inc = _published()
    out = kh.harvest_from_incident(inc["id"])
    assert out["auto_applied"] is False
    assert out["proposal"]["status"] == "pending_review"
    from services import evolution_apply
    monkeypatch.setattr(evolution_apply, "maybe_auto_apply", lambda p: True)
    inc2 = _published(tracker_id="778")
    out2 = kh.harvest_from_incident(inc2["id"])
    assert out2["auto_applied"] is True


# 8
def test_from_optimizer_promocion(_env, monkeypatch):
    from services import evolution_optimizer_store as eos
    monkeypatch.setattr(eos, "read_lessons_tail", lambda aspect_key=None, limit=20: [
        {"id": "les-1", "run_id": "run-9", "aspect_key": "agent_prompts/developer",
         "variant_id": "v1", "text": "mejora verificada", "outcome": "mejoro",
         "delta": 0.05, "created_at": "2026-06-01T00:00:00+00:00"},
    ])
    out = kh.harvest_from_optimizer_lesson("les-1")
    p = out["proposal"]
    assert p["origin"] == "optimizer"
    assert p["evidence"] == ["optimizer_lesson:les-1", "optimizer_run:run-9", "harvest:promocion_determinista"]
    meta = ks.read_meta()[p["id"]]
    assert meta["scope"]["agent_types"] == ["developer"]


# 9
def test_from_optimizer_sin_169_degrada(_env, monkeypatch):
    monkeypatch.setitem(sys.modules, "services.evolution_optimizer_store", None)
    with pytest.raises(RuntimeError, match="optimizer_unavailable"):
        kh.harvest_from_optimizer_lesson("les-1")


# 10
def test_manual_valida_limites(_env):
    with pytest.raises(ValueError, match="invalid_payload:title"):
        kh.harvest_manual("", "cuerpo")
    with pytest.raises(ValueError, match="invalid_payload:body"):
        kh.harvest_manual("titulo", "x" * 5000)
    out = kh.harvest_manual("Título válido", "Cuerpo accionable de la lección.")
    assert out["proposal"]["origin"] == "manual"
    assert out["proposal"]["evidence"] == ["harvest:manual"]


# 11
def test_pii_enmascarada_en_todos_los_insumos(_env, monkeypatch):
    sec1 = "SEC" + "RETO_INTAKE_9137"
    sec2 = "SEC" + "RETO_DOC_4521"
    sec3 = "SEC" + "RETO_BODY_7788"
    doc = _env / "doc_incidencia.md"
    doc.write_text(f"detalle con {sec2} adentro", encoding="utf-8")
    import services.pii_masker as pm
    monkeypatch.setattr(pm, "redact_irreversible",
                        lambda t: (t or "").replace(sec1, "[MASKED]").replace(sec2, "[MASKED]").replace(sec3, "[MASKED]"))
    cap = {}
    _mock_llm(monkeypatch, body_json=f'{{"title": "t", "body": "cuerpo con {sec3}", "tags": []}}', capture=cap)
    inc = _published(text=f"reporte con {sec1} incrustado")
    incident_store.update_incident(inc["id"], doc_path=str(doc))
    out = kh.harvest_from_incident(inc["id"])
    assert sec1 not in cap["user"] and sec2 not in cap["user"]
    assert "[MASKED]" in cap["user"]
    assert sec3 not in out["proposal"]["proposed_content"]
    assert "[MASKED]" in out["proposal"]["proposed_content"]
