"""Tests del loop de autocorrección F1.3 (services/cli_autocorrect.py)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _valid_payload(epic_id: int = 206) -> dict:
    return {
        "generated_at": "2026-06-09T12:00:00Z",
        "generated_by": "AnalistaFuncional",
        "epic_id": epic_id,
        "rf_id": "RF-001",
        "title": "Alta de marca oficial",
        "description_html": "<p>detalle</p>",
        "plan_de_pruebas_path": "plan-de-pruebas.md",
        "parent_link_type": "Hierarchy-Reverse",
        "status": "pending_manual_creation",
    }


def _pending_path(root: Path, ado_id: int = 206) -> Path:
    rf = root / f"epic-{ado_id}" / "RF-001"
    rf.mkdir(parents=True, exist_ok=True)
    return rf / "pending-task.json"


def _make_loop(root: Path, sent: list[str], max_retries: int = 2):
    from services.cli_autocorrect import AutocorrectLoop

    return AutocorrectLoop(
        ado_id=206,
        max_retries=max_retries,
        send=lambda text: (sent.append(text) or True),
        outputs_root=root,
        check_db=False,
    )


def test_no_artifacts_no_correction(tmp_path):
    from services import cli_autocorrect as ca

    sent: list[str] = []
    loop = _make_loop(tmp_path, sent)
    assert loop.on_turn_end() == ca.ACTION_NO_ARTIFACTS
    assert sent == []
    assert loop.attempts == 0


def test_invalid_artifact_sends_one_exact_correction(tmp_path):
    from services import cli_autocorrect as ca

    pt = _pending_path(tmp_path)
    pt.write_text("{not json", encoding="utf-8")
    sent: list[str] = []
    loop = _make_loop(tmp_path, sent)

    assert loop.on_turn_end() == ca.ACTION_CORRECTED
    assert len(sent) == 1
    # El mensaje correctivo lleva el path y el error exacto
    assert "pending-task.json" in sent[0]
    assert "JSON inválido" in sent[0]
    assert "No toques Azure DevOps" in sent[0]
    assert loop.attempts == 1


def test_valid_after_correction_terminates_loop(tmp_path):
    from services import cli_autocorrect as ca

    pt = _pending_path(tmp_path)
    pt.write_text("{broken", encoding="utf-8")
    sent: list[str] = []
    loop = _make_loop(tmp_path, sent)
    assert loop.on_turn_end() == ca.ACTION_CORRECTED

    # El agente "corrige" el archivo y escribe el plan referenciado.
    pt.write_text(json.dumps(_valid_payload()), encoding="utf-8")
    (pt.parent / "plan-de-pruebas.md").write_text("# plan", encoding="utf-8")
    assert loop.on_turn_end() == ca.ACTION_OK
    # Loop terminal: turnos posteriores no re-validan ni escriben más.
    assert loop.on_turn_end() == ca.ACTION_DONE
    assert len(sent) == 1


def test_retry_cap_is_respected(tmp_path):
    from services import cli_autocorrect as ca

    pt = _pending_path(tmp_path)
    pt.write_text("{broken", encoding="utf-8")
    sent: list[str] = []
    loop = _make_loop(tmp_path, sent, max_retries=2)

    assert loop.on_turn_end() == ca.ACTION_CORRECTED
    assert loop.on_turn_end() == ca.ACTION_CORRECTED
    assert loop.on_turn_end() == ca.ACTION_EXHAUSTED
    # Terminal después de agotar el cap: nada más se escribe.
    assert loop.on_turn_end() == ca.ACTION_DONE
    assert len(sent) == 2
    summary = loop.summary()
    assert summary["attempts"] == 2
    assert summary["last_action"] == ca.ACTION_EXHAUSTED
    assert summary["last_errors"]


def test_send_failure_terminates_loop(tmp_path):
    from services import cli_autocorrect as ca
    from services.cli_autocorrect import AutocorrectLoop

    pt = _pending_path(tmp_path)
    pt.write_text("{broken", encoding="utf-8")
    loop = AutocorrectLoop(
        ado_id=206,
        max_retries=2,
        send=lambda text: False,  # stdin cerrado
        outputs_root=tmp_path,
        check_db=False,
    )
    assert loop.on_turn_end() == ca.ACTION_SEND_FAILED
    assert loop.on_turn_end() == ca.ACTION_DONE
