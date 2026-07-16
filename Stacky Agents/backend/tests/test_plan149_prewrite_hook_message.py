"""Plan 149 F6 (opcional) — Paridad del refuerzo (a): feedback pre-escritura
con reason_code clasificado (hook Claude, artifact_validator)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_validate_pending_task_empty_message(tmp_path):
    from services.artifact_validator import validate_pending_task_file

    p = tmp_path / "pending-task.json"
    p.write_text("   ", encoding="utf-8")

    result = validate_pending_task_file(p, check_db=False)
    assert result.valid is False
    assert any("vacío" in str(e) for e in result.errors)


def test_validate_pending_task_truncated_message(tmp_path):
    from services.artifact_validator import validate_pending_task_file

    p = tmp_path / "pending-task.json"
    p.write_text('{"title":"x"', encoding="utf-8")

    result = validate_pending_task_file(p, check_db=False)
    assert result.valid is False
    assert any("truncad" in str(e) for e in result.errors)
