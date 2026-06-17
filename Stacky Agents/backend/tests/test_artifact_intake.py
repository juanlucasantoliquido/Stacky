"""V1.3 — Tests del contrato universal de intake de outputs file-based."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


def _valid_payload() -> dict:
    return {
        "generated_at": "2026-06-11T00:00:00Z",
        "generated_by": "developer",
        "epic_id": 1234,
        "rf_id": "RF-1",
        "title": "Tarea X",
        "description_html": "<p>desc</p>",
        "plan_de_pruebas_path": "plan.md",
        "parent_link_type": "child",
        "status": "pending_manual_creation",
    }


def test_clean_json_passes():
    from services import artifact_intake as ai

    raw = json.dumps(_valid_payload())
    r = ai.validate_and_normalize(raw=raw, kind="pending_task_json")
    assert r.ok
    assert not r.repaired
    assert isinstance(r.normalized, dict)


def test_code_fence_repaired():
    from services import artifact_intake as ai

    raw = "```json\n" + json.dumps(_valid_payload()) + "\n```"
    r = ai.validate_and_normalize(raw=raw, kind="pending_task_json")
    assert r.ok
    assert r.repaired
    assert "stripped_code_fence" in r.repairs


def test_trailing_comma_repaired():
    from services import artifact_intake as ai

    raw = json.dumps(_valid_payload())
    # inyectar coma final antes del }
    raw = raw[:-1] + ",}"
    r = ai.validate_and_normalize(raw=raw, kind="pending_task_json")
    assert r.ok
    assert r.repaired
    assert "stripped_trailing_comma" in r.repairs


def test_bom_repaired():
    from services import artifact_intake as ai

    raw = "﻿" + json.dumps(_valid_payload())
    r = ai.validate_and_normalize(raw=raw, kind="pending_task_json")
    assert r.ok
    assert "stripped_bom" in r.repairs


def test_prose_around_json_repaired():
    from services import artifact_intake as ai

    raw = "Aquí está el resultado:\n" + json.dumps(_valid_payload()) + "\nListo!"
    r = ai.validate_and_normalize(raw=raw, kind="pending_task_json")
    assert r.ok
    assert "extracted_json_object" in r.repairs


def test_smart_quotes_repaired():
    from services import artifact_intake as ai

    raw = json.dumps(_valid_payload()).replace('"', "“", 1)
    raw = raw.replace('"', "”", 1) if "”" not in raw else raw
    r = ai.validate_and_normalize(raw=raw, kind="pending_task_json")
    # con al menos una comilla tipográfica reemplazada, debe parsear
    assert r.ok


def test_irreparable_json_fails():
    from services import artifact_intake as ai

    r = ai.validate_and_normalize(raw="{not json at all <<<", kind="pending_task_json")
    assert not r.ok
    assert r.errors
    assert r.normalized is None


def test_missing_required_fields_fails():
    from services import artifact_intake as ai

    payload = {"title": "x"}
    r = ai.validate_and_normalize(raw=json.dumps(payload), kind="pending_task_json")
    assert not r.ok
    assert any("requerido" in e.lower() or "falta" in e.lower() for e in r.errors)


def test_anti_ordinal_rule():
    """Un parent/epic_id ordinal (no presente en el contexto del ticket) → error específico."""
    from services import artifact_intake as ai

    payload = _valid_payload()
    payload["epic_id"] = 3  # ordinal, no es un ADO id real del contexto
    ctx = {"valid_ado_ids": [1234, 5678]}
    r = ai.validate_and_normalize(
        raw=json.dumps(payload), kind="pending_task_json", ticket_context=ctx
    )
    assert not r.ok
    assert any("no existe" in e.lower() or "ordinal" in e.lower() for e in r.errors)


def test_anti_ordinal_passes_with_real_id():
    from services import artifact_intake as ai

    payload = _valid_payload()
    payload["epic_id"] = 1234
    ctx = {"valid_ado_ids": [1234, 5678]}
    r = ai.validate_and_normalize(
        raw=json.dumps(payload), kind="pending_task_json", ticket_context=ctx
    )
    assert r.ok


def test_html_valid_passes_intact():
    from services import artifact_intake as ai

    html = "<html><body><p>comentario</p></body></html>"
    r = ai.validate_and_normalize(raw=html, kind="comment_html")
    assert r.ok
    assert r.normalized == html
    assert not r.repaired


def test_html_empty_fails():
    from services import artifact_intake as ai

    r = ai.validate_and_normalize(raw="   ", kind="comment_html")
    assert not r.ok


def test_unknown_kind_raises():
    from services import artifact_intake as ai

    with pytest.raises(ValueError):
        ai.validate_and_normalize(raw="x", kind="bogus")


def test_watcher_intake_quarantines_irreparable(tmp_path, monkeypatch):
    """Con intake ON, un pending-task irreparable se cuarentena (skipped), sin HTTP."""
    from services import output_watcher as ow

    monkeypatch.setenv("STACKY_ARTIFACT_INTAKE_ENABLED", "true")
    monkeypatch.setenv("STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS", "true")
    ow._SEEN_TERMINAL_PENDING.clear()

    pt = tmp_path / "pending-task.json"
    pt.write_text("{ totally broken <<<", encoding="utf-8")

    summary = ow._auto_create_pending_tasks(epic_ado_id=1234, pending_files=[pt])
    assert summary["created"] == 0
    assert summary["skipped"] == 1
    assert summary["errors"] == 0


def test_watcher_intake_off_byte_identical(tmp_path, monkeypatch):
    """Con intake OFF, un JSON inválido también se cuarentena por el path actual."""
    from services import output_watcher as ow

    monkeypatch.setenv("STACKY_ARTIFACT_INTAKE_ENABLED", "false")
    monkeypatch.setenv("STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS", "true")
    ow._SEEN_TERMINAL_PENDING.clear()

    pt = tmp_path / "pending-task.json"
    pt.write_text("{ totally broken <<<", encoding="utf-8")

    summary = ow._auto_create_pending_tasks(epic_ado_id=1234, pending_files=[pt])
    assert summary["skipped"] == 1


def test_incident_doc20_regression():
    """Caso real del incidente: JSON dentro de fence + texto + coma final → reparable."""
    from services import artifact_intake as ai

    body = json.dumps(_valid_payload())
    body = body[:-1] + ",}"  # coma final
    raw = "He creado la tarea:\n```json\n" + body + "\n```\nFin."
    r = ai.validate_and_normalize(raw=raw, kind="pending_task_json")
    assert r.ok
    assert r.repaired
    # JSON recuperado de entre prosa+fence, y coma final eliminada.
    assert "stripped_trailing_comma" in r.repairs
    assert ("stripped_code_fence" in r.repairs) or ("extracted_json_object" in r.repairs)
