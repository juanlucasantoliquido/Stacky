"""Plan 61 F1 — Tests de harness/task_gate.py (funciones puras).

10 casos: clean pass, defectos individuales, blocking mode, garbage input, determinismo.
"""
from __future__ import annotations


def _valid_payload(**overrides) -> dict:
    """Payload mínimo válido para la gate."""
    base = {
        "generated_at": "2026-06-21T00:00:00Z",
        "generated_by": "stacky",
        "epic_id": "149",
        "rf_id": "RF-001",
        "title": "Gestión de perfiles de clientes",
        "description_html": "<p>RF-001 Descripción de la tarea.</p>",
        "plan_de_pruebas_path": "plan-de-pruebas.md",
        "parent_link_type": "Child",
        "status": "pending_manual_creation",
    }
    base.update(overrides)
    return base


_PLAN_TEXT = "## Pruebas\nVerificar que RF-001 funcione correctamente."


# ── F1-01: payload limpio pasa sin defectos ──────────────────────────────────


def test_clean_payload_passes():
    from harness.task_gate import evaluate_task_gate, TaskGateDecision
    v = evaluate_task_gate(payload=_valid_payload(), plan_de_pruebas_text=_PLAN_TEXT, blocking_enabled=False)
    assert v.decision == TaskGateDecision.PASS
    assert v.defects == []
    assert v.blocking is False


# ── F1-02: title vacío → severity repair → REPAIR ───────────────────────────


def test_title_empty_is_repair():
    from harness.task_gate import evaluate_task_gate, TaskGateDecision
    v = evaluate_task_gate(payload=_valid_payload(title=""), plan_de_pruebas_text=_PLAN_TEXT, blocking_enabled=False)
    assert v.decision == TaskGateDecision.REPAIR
    assert "title_empty" in v.defects


# ── F1-03: rf_id vacío → needs_review ────────────────────────────────────────


def test_rf_id_empty_is_needs_review():
    from harness.task_gate import evaluate_task_gate, TaskGateDecision
    v = evaluate_task_gate(payload=_valid_payload(rf_id=""), plan_de_pruebas_text=_PLAN_TEXT, blocking_enabled=True)
    assert v.decision == TaskGateDecision.NEEDS_REVIEW
    assert v.blocking is True
    assert "rf_id_empty" in v.defects


# ── F1-04: plan vacío → needs_review ─────────────────────────────────────────


def test_plan_de_pruebas_empty_is_needs_review():
    from harness.task_gate import evaluate_task_gate, TaskGateDecision
    v = evaluate_task_gate(payload=_valid_payload(), plan_de_pruebas_text="   ", blocking_enabled=False)
    assert v.decision == TaskGateDecision.NEEDS_REVIEW
    assert "plan_de_pruebas_empty" in v.defects


# ── F1-05: descripción no menciona rf_id → repair ────────────────────────────


def test_description_missing_rf_is_repair():
    from harness.task_gate import evaluate_task_gate, TaskGateDecision
    payload = _valid_payload(description_html="<p>Sin referencia al requisito.</p>", rf_id="RF-007")
    v = evaluate_task_gate(payload=payload, plan_de_pruebas_text=_PLAN_TEXT, blocking_enabled=False)
    assert v.decision == TaskGateDecision.REPAIR
    assert "description_missing_rf" in v.defects


# ── F1-06: description vacía → repair (severity propia) ──────────────────────


def test_description_empty_is_repair():
    from harness.task_gate import evaluate_task_gate, TaskGateDecision
    v = evaluate_task_gate(payload=_valid_payload(description_html=""), plan_de_pruebas_text=_PLAN_TEXT, blocking_enabled=False)
    assert v.decision == TaskGateDecision.REPAIR
    assert "description_empty" in v.defects


# ── F1-07: epic_id "RF-149" (no numérico) → needs_review ─────────────────────


def test_epic_id_not_numeric_is_needs_review():
    from harness.task_gate import evaluate_task_gate, TaskGateDecision
    v = evaluate_task_gate(payload=_valid_payload(epic_id="RF-149"), plan_de_pruebas_text=_PLAN_TEXT, blocking_enabled=False)
    assert v.decision == TaskGateDecision.NEEDS_REVIEW
    assert "epic_id_not_numeric" in v.defects


# ── F1-08: epic_id "0149" (numérico con ceros) → PASS ────────────────────────


def test_epic_id_numeric_with_leading_zeros_passes():
    from harness.task_gate import evaluate_task_gate, TaskGateDecision
    v = evaluate_task_gate(payload=_valid_payload(epic_id="0149"), plan_de_pruebas_text=_PLAN_TEXT, blocking_enabled=False)
    assert v.decision == TaskGateDecision.PASS


# ── F1-09: blocking=False NUNCA bloquea aunque haya needs_review ─────────────


def test_blocking_disabled_never_blocks_even_with_needs_review():
    from harness.task_gate import evaluate_task_gate, TaskGateDecision
    v = evaluate_task_gate(payload=_valid_payload(rf_id=""), plan_de_pruebas_text=_PLAN_TEXT, blocking_enabled=False)
    assert v.blocking is False
    # El defecto sigue detectándose
    assert "rf_id_empty" in v.defects


# ── F1-10: entrada basura no lanza excepción ─────────────────────────────────


def test_garbage_input_never_raises():
    from harness.task_gate import evaluate_task_gate
    try:
        evaluate_task_gate(payload=None, plan_de_pruebas_text=None, blocking_enabled=True)  # type: ignore[arg-type]
    except Exception as exc:
        raise AssertionError(f"evaluate_task_gate lanzó excepción con basura: {exc}") from exc


# ── F1-11: defectos lista siempre ordenada (determinismo) ────────────────────


def test_defects_list_is_deterministic():
    from harness.task_gate import evaluate_task_gate
    payload = _valid_payload(title="", rf_id="", description_html="")
    v1 = evaluate_task_gate(payload=payload, plan_de_pruebas_text=_PLAN_TEXT, blocking_enabled=False)
    v2 = evaluate_task_gate(payload=payload, plan_de_pruebas_text=_PLAN_TEXT, blocking_enabled=False)
    assert v1.defects == v2.defects
    assert v1.defects == sorted(v1.defects)
