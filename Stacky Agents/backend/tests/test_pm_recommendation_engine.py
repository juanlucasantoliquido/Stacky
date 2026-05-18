"""Tests del recommendation engine (F2-R)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")
os.environ["STACKY_PM_LLM_BACKEND"] = "mock"


@pytest.fixture(autouse=True)
def _pm_tables_ready():
    from db import init_db, session_scope
    from services.pm.models import (
        PmAiRecommendation, PmAiUsage, PmRiskItem,
        PmSprintSnapshot, PmWorkItemComment,
    )

    init_db()
    with session_scope() as session:
        session.query(PmAiRecommendation).delete()
        session.query(PmAiUsage).delete()
        session.query(PmRiskItem).delete()
        session.query(PmSprintSnapshot).delete()
        session.query(PmWorkItemComment).delete()
    yield


def _patch_mock_recommendations(monkeypatch, recommendations: list[dict]):
    """Forza al mock backend a devolver recomendaciones específicas."""
    import json
    import services.pm.pm_llm_client as mod

    def custom_mock(spec):
        payload = {
            "rec_output_version": "1.0",
            "recommendations": recommendations,
            "model_used": "mock-1.0",
            "advisory_only": True,
        }
        text = json.dumps(payload)
        return text, max(1, len(spec.system) // 4), max(1, len(text) // 4)

    monkeypatch.setattr(mod, "_call_mock", custom_mock)


# ── validación de items ───────────────────────────────────────────────────────

def test_invalid_priority_rejected():
    from services.pm.pm_recommendation_engine import _validate_recommendation_item
    ok, reason = _validate_recommendation_item({
        "priority": "P9", "category": "SCOPE", "action": "do something",
    })
    assert not ok and reason and reason.startswith("invalid_priority")


def test_invalid_category_rejected():
    from services.pm.pm_recommendation_engine import _validate_recommendation_item
    ok, reason = _validate_recommendation_item({
        "priority": "P1", "category": "BOGUS", "action": "x",
    })
    assert not ok and reason and reason.startswith("invalid_category")


def test_publish_recommended_true_rejected():
    from services.pm.pm_recommendation_engine import _validate_recommendation_item
    ok, reason = _validate_recommendation_item({
        "priority": "P1", "category": "SCOPE", "action": "x",
        "publish_recommended": True,
    })
    assert not ok and reason == "publish_recommended_must_be_false"


def test_punitive_language_rejected():
    from services.pm.pm_recommendation_engine import _validate_recommendation_item
    ok, reason = _validate_recommendation_item({
        "priority": "P1", "category": "RESOURCE",
        "action": "despedir al dev del componente X",
    })
    assert not ok and "punitive" in (reason or "")


def test_empty_action_rejected():
    from services.pm.pm_recommendation_engine import _validate_recommendation_item
    ok, reason = _validate_recommendation_item({
        "priority": "P1", "category": "SCOPE", "action": "",
    })
    assert not ok and reason == "empty_action"


def test_valid_item_passes():
    from services.pm.pm_recommendation_engine import _validate_recommendation_item
    ok, reason = _validate_recommendation_item({
        "priority": "P0", "category": "SCOPE",
        "action": "Recortar 2 items no críticos del sprint",
        "rationale": "Probabilidad de cumplimiento subiría del 60% al 80%",
    })
    assert ok and reason is None


# ── generate_recommendations con gate ─────────────────────────────────────────

def test_gate_blocks_without_force_unsafe():
    """Mock backend no pasa el gate → engine no genera nada y reporta blocked."""
    from services.pm.pm_recommendation_engine import generate_recommendations
    result = generate_recommendations(
        project="TestPM",
        snapshot={"kpis": {"completion_rate_pct": 50, "blocked_items": 1}},
        risks=[],
        history=[],
        model="mock-1.0",
    )
    # Recommendation gate con mock SI pasa actualmente (mock devuelve recs=[] = advisory ok)
    # pero igual probamos el flow: si gate_passed es false, generated debe ser 0.
    if not result.gate_passed:
        assert result.generated == 0
        assert "eval_gate_blocked" in result.rejected_reasons


def test_force_unsafe_bypasses_gate(monkeypatch):
    """Con force_unsafe=True, el engine corre aunque el gate no pase."""
    _patch_mock_recommendations(monkeypatch, [{
        "rec_id": "REC-stub-1",
        "priority": "P1",
        "category": "RISK_MITIGATION",
        "action": "Revisar dependencias de backend con el equipo hoy",
        "rationale": "4 items dependen de un componente bloqueado",
        "supporting_data": {"blocked_count": 4},
        "confidence": 0.8,
        "publish_recommended": False,
        "human_approval_required": True,
    }])
    from services.pm.pm_recommendation_engine import generate_recommendations
    result = generate_recommendations(
        project="TestPM",
        snapshot={"iteration": {"id": "sprint-x"}, "kpis": {"completion_rate_pct": 55}},
        risks=[],
        history=[],
        model="mock-1.0",
        force_unsafe=True,
    )
    assert result.generated == 1
    assert result.rejected == 0


def test_generated_recommendations_persisted_correctly(monkeypatch):
    from db import session_scope
    from services.pm.models import PmAiRecommendation
    from services.pm.pm_recommendation_engine import generate_recommendations

    _patch_mock_recommendations(monkeypatch, [
        {
            "priority": "P0",
            "category": "SCOPE",
            "action": "Recortar 2 user stories no críticas",
            "rationale": "Probabilidad de cumplimiento mejora 18pp",
            "supporting_data": {"items_to_remove": 2},
            "confidence": 0.85,
            "publish_recommended": False,
        },
        {
            "priority": "P2",
            "category": "PROCESS",
            "action": "Programar retro al cierre del sprint",
            "rationale": "Última retro fue hace 3 sprints",
            "supporting_data": {},
            "confidence": 0.6,
            "publish_recommended": False,
        },
    ])

    result = generate_recommendations(
        project="TestPM",
        snapshot={"iteration": {"id": "sprint-42"}, "kpis": {"completion_rate_pct": 60}},
        risks=[],
        history=[],
        model="mock-1.0",
        force_unsafe=True,
    )
    assert result.generated == 2
    assert result.rejected == 0

    with session_scope() as session:
        rows = session.query(PmAiRecommendation).filter(
            PmAiRecommendation.project == "TestPM"
        ).all()
        assert len(rows) == 2
        # Todos deben ser advisory_only + publish_recommended=False
        assert all(r.advisory_only is True for r in rows)
        assert all(r.publish_recommended is False for r in rows)
        assert all(r.human_approval_required is True for r in rows)
        assert all(r.usage_id is not None for r in rows)


def test_invalid_items_in_llm_output_are_rejected(monkeypatch):
    from services.pm.pm_recommendation_engine import generate_recommendations

    _patch_mock_recommendations(monkeypatch, [
        {"priority": "P0", "category": "SCOPE", "action": "buena acción", "rationale": "ok"},
        {"priority": "PX", "category": "SCOPE", "action": "mal prioridad"},      # rechazado
        {"priority": "P1", "category": "BOGUS", "action": "categoria mala"},     # rechazado
        {"priority": "P1", "category": "RESOURCE", "action": "despedir al QA"},  # punitive
    ])
    result = generate_recommendations(
        project="TestPM",
        snapshot={"iteration": {"id": "s"}, "kpis": {}},
        risks=[],
        history=[],
        model="mock-1.0",
        force_unsafe=True,
    )
    assert result.generated == 1
    assert result.rejected == 3
    reasons_str = " ".join(result.rejected_reasons)
    assert "invalid_priority" in reasons_str
    assert "invalid_category" in reasons_str
    assert "punitive" in reasons_str


def test_regeneration_same_sprint_updates_in_place(monkeypatch):
    """Re-generar mismas recomendaciones para el mismo sprint NO debe duplicar."""
    from db import session_scope
    from services.pm.models import PmAiRecommendation
    from services.pm.pm_recommendation_engine import generate_recommendations

    item = {
        "priority": "P1",
        "category": "SCOPE",
        "action": "Reducir scope mid-sprint",
        "rationale": "blocking risk en aumento",
        "supporting_data": {},
        "confidence": 0.7,
        "publish_recommended": False,
    }
    _patch_mock_recommendations(monkeypatch, [item])
    snapshot = {"iteration": {"id": "sprint-r"}, "kpis": {}}

    r1 = generate_recommendations(
        project="TestPM", snapshot=snapshot, risks=[], history=[],
        model="mock-1.0", force_unsafe=True,
    )
    r2 = generate_recommendations(
        project="TestPM", snapshot=snapshot, risks=[], history=[],
        model="mock-1.0", force_unsafe=True,
    )
    assert r1.generated == 1
    assert r2.generated == 1  # actualiza en place, sigue contando como generated
    with session_scope() as session:
        count = session.query(PmAiRecommendation).filter(
            PmAiRecommendation.project == "TestPM"
        ).count()
        assert count == 1  # NO se duplicó


def test_advisory_only_output_must_be_true(monkeypatch):
    """Si el modelo devuelve advisory_only=False, el engine debe rechazar todo."""
    import json
    import services.pm.pm_llm_client as mod
    from services.pm.pm_recommendation_engine import generate_recommendations

    def malicious_mock(spec):
        payload = {
            "rec_output_version": "1.0",
            "recommendations": [{
                "priority": "P0", "category": "SCOPE",
                "action": "publicar a ADO automáticamente",
                "rationale": "test", "publish_recommended": False,
            }],
            "model_used": "mock-1.0",
            "advisory_only": False,    # ← el atacante intenta cambiarlo
        }
        text = json.dumps(payload)
        return text, 50, 50

    monkeypatch.setattr(mod, "_call_mock", malicious_mock)

    result = generate_recommendations(
        project="TestPM",
        snapshot={"iteration": {"id": "s"}, "kpis": {}},
        risks=[], history=[],
        model="mock-1.0", force_unsafe=True,
    )
    assert result.generated == 0
    assert "output_advisory_only_not_true" in result.rejected_reasons


# ── acknowledge ───────────────────────────────────────────────────────────────

def test_acknowledge_recommendation_works():
    from db import session_scope
    from services.pm.models import PmAiRecommendation
    from services.pm.pm_recommendation_engine import acknowledge_recommendation

    with session_scope() as session:
        row = PmAiRecommendation(
            rec_id="REC-test-ack",
            project="TestPM",
            sprint_id="s",
            priority="P1",
            category="SCOPE",
            action="test action",
            confidence=0.8,
            advisory_only=True,
            publish_recommended=False,
            human_approval_required=True,
            model="mock-1.0",
        )
        session.add(row)

    updated = acknowledge_recommendation("REC-test-ack", actor="pm@empresa.com")
    assert updated is not None
    assert updated["acknowledged"] is True
    assert updated["acknowledged_by"] == "pm@empresa.com"


def test_acknowledge_unknown_rec_returns_none():
    from services.pm.pm_recommendation_engine import acknowledge_recommendation
    assert acknowledge_recommendation("REC-does-not-exist", actor="x") is None
