"""Plan 56 F2 — Captura: aprobar/rechazar → derivar+guardar golden.

Tests PRIMERO (TDD).
Prueba que human_review_route dispara la captura de goldens al aprobar/rechazar.
Usa monkeypatch para aislar disco y DB.
"""
from __future__ import annotations

import pytest


# ── fixture: redirigir _GOLDENS_DIR a tmp_path ───────────────────────────────

@pytest.fixture(autouse=True)
def _isolated_goldens_dir(tmp_path, monkeypatch):
    import harness.regression_goldens as mod
    monkeypatch.setattr(mod, "_GOLDENS_DIR", tmp_path)
    yield


# ── helpers: mocks mínimos ────────────────────────────────────────────────────

class _FakeTicket:
    stacky_project_name = "Pacifico"
    work_item_type = "Epic"


class _FakeExecution:
    id = 99
    agent_type = "BusinessAgent"
    status = "needs_review"
    output = "<h1>Épica</h1><h2>RF-01 Descripción</h2><p>Contenido.</p>"
    ticket = _FakeTicket()

    def __init__(self, metadata: dict | None = None):
        self._meta = metadata or {}

    @property
    def metadata_dict(self):
        return self._meta


def _make_capture_kwargs(exec_obj, verdict: str, note: str = ""):
    """Parametros que la función de captura (save_goldens_from_review) espera."""
    return {
        "execution": exec_obj,
        "verdict": verdict,
        "note": note,
    }


# ── Tests F2 ─────────────────────────────────────────────────────────────────

def test_reject_creates_negative_golden():
    """Rechazar una ejecución con nota → load_goldens devuelve un golden negativo."""
    from services.regression_capture import save_goldens_from_review
    from harness.regression_goldens import load_goldens

    exec_obj = _FakeExecution()
    save_goldens_from_review(
        execution=exec_obj,
        verdict="rejected",
        note="El RF-01 no describe criterios de aceptación",
    )

    goldens = load_goldens(
        project="Pacifico",
        agent_type="BusinessAgent",
        work_item_type="Epic",
    )
    assert len(goldens) == 1
    assert goldens[0].kind == "negative"
    assert "rf-01" in goldens[0].value


def test_approve_creates_positive_golden():
    """Aprobar una épica → load_goldens devuelve un golden positivo."""
    from services.regression_capture import save_goldens_from_review
    from harness.regression_goldens import load_goldens

    exec_obj = _FakeExecution()
    save_goldens_from_review(
        execution=exec_obj,
        verdict="approved",
        note="",
    )

    goldens = load_goldens(
        project="Pacifico",
        agent_type="BusinessAgent",
        work_item_type="Epic",
    )
    assert len(goldens) == 1
    assert goldens[0].kind == "positive"
    assert goldens[0].check == "present_heading"


def test_approve_high_confidence_adds_band():
    """Aprobar con confidence >= 0.75 → golden con confidence_band='high'."""
    from services.regression_capture import save_goldens_from_review
    from harness.regression_goldens import load_goldens

    exec_obj = _FakeExecution(metadata={"epic_summary": {"confidence": 0.85}})
    save_goldens_from_review(
        execution=exec_obj,
        verdict="approved",
        note="",
    )

    goldens = load_goldens(
        project="Pacifico",
        agent_type="BusinessAgent",
        work_item_type="Epic",
    )
    assert len(goldens) == 1
    assert goldens[0].confidence_band == "high"
