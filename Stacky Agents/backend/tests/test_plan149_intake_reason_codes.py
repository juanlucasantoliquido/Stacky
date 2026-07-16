"""Plan 149 F3 — Clasificación de la causa de fallo de intake (reason_code)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

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


def _r(raw: str):
    from services.artifact_intake import validate_and_normalize
    return validate_and_normalize(raw=raw, kind="pending_task_json")


def test_empty_file_reason_empty():
    assert _r("   \n ").reason_code == "empty"
    assert not _r("   ").ok


def test_truncated_object_reason_truncated():
    assert _r('{"title": "x"').reason_code == "truncated"


def test_missing_value_reason_malformed():
    assert _r('{"a": }').reason_code == "malformed"


def test_trailing_comma_still_repaired_ok():
    # el reparador arregla la coma final; lo que quede después puede fallar por
    # schema (faltan campos), pero NUNCA por "malformed" (el JSON ya es válido).
    res = _r('{"title":"x",}')
    assert res.reason_code in (None, "schema")


def test_reason_code_in_to_dict():
    assert "reason_code" in _r("").to_dict()


def test_valid_full_payload_no_reason():
    import json
    res = _r(json.dumps(_valid_payload()))
    assert res.ok
    assert res.reason_code is None


def test_classify_json_failure_is_public_symbol():
    """C8 — contrato compartido: classify_json_failure es público (sin underscore),
    lo consume también artifact_validator (F6)."""
    from services.artifact_intake import classify_json_failure
    assert classify_json_failure("") == "empty"
    assert classify_json_failure("   ") == "empty"
    assert classify_json_failure('{"a": 1') == "truncated"
    assert classify_json_failure('{"a": }') == "malformed"
