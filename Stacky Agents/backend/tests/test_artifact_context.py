"""Tests del artifact_context — context block que resume artifacts en disco.

Cubre:
  - Ticket sin nada en disco → retorna None.
  - Non-Epic con comment.html existente → lo reporta.
  - Epic con pending-task.json (pending + consumed) → cuenta y lista correctos.
  - MANIFEST.json de última ejecución → signals reflejados en el bloque.
  - Helper inject_into_blocks es idempotente.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture
def repo_root(tmp_path, monkeypatch):
    """Configura STACKY_REPO_ROOT al tmp_path para aislar artifacts."""
    monkeypatch.setenv("STACKY_REPO_ROOT", str(tmp_path))
    # Reload del cache de repo_root si lo hubiera (no hay cache hoy, pero por las dudas)
    return tmp_path


@pytest.fixture
def codex_runs_dir(tmp_path, monkeypatch):
    """Redirige el directorio de codex_runs al tmp para tests."""
    runs_dir = tmp_path / "_codex_runs"
    runs_dir.mkdir()

    def _fake_codex_runs_dir() -> Path:
        return runs_dir

    from services import artifact_context

    monkeypatch.setattr(artifact_context, "_codex_runs_dir", _fake_codex_runs_dir)
    return runs_dir


# ── Casos vacíos ─────────────────────────────────────────────────────────────


def test_returns_none_when_no_artifacts(repo_root, codex_runs_dir):
    from services.artifact_context import build_artifact_status_block

    result = build_artifact_status_block(
        ado_id=27000,
        work_item_type="Task",
        execution_ids=[],
    )
    assert result is None


def test_returns_none_when_ado_id_missing(repo_root, codex_runs_dir):
    from services.artifact_context import build_artifact_status_block

    result = build_artifact_status_block(
        ado_id=None,
        work_item_type="Task",
        execution_ids=[],
    )
    assert result is None


# ── Comment HTML ─────────────────────────────────────────────────────────────


def test_reports_comment_html_when_present(repo_root, codex_runs_dir):
    from services.artifact_context import (
        ARTIFACT_BLOCK_ID,
        build_artifact_status_block,
    )

    output_dir = repo_root / "Agentes" / "outputs" / "27001"
    output_dir.mkdir(parents=True)
    (output_dir / "comment.html").write_text("<p>hola</p>", encoding="utf-8")

    block = build_artifact_status_block(
        ado_id=27001,
        work_item_type="Task",
        execution_ids=[],
    )
    assert block is not None
    assert block["id"] == ARTIFACT_BLOCK_ID
    assert "comment.html: existe" in block["content"]
    assert "Agentes/outputs/27001/comment.html" in block["content"]
    assert block["metadata"]["comment_html"]["size_bytes"] > 0


# ── Pending tasks (Epic) ─────────────────────────────────────────────────────


def test_lists_pending_and_consumed_tasks_for_epic(repo_root, codex_runs_dir):
    from services.artifact_context import build_artifact_status_block

    epic_dir = repo_root / "Agentes" / "outputs" / "epic-149"

    rf_pending = epic_dir / "RF-008-altabaja-cliente"
    rf_pending.mkdir(parents=True)
    (rf_pending / "pending-task.json").write_text(
        json.dumps({
            "rf_id": "RF-008",
            "title": "Alta/baja de cliente",
            "generated_at": "2026-05-10T12:00:00Z",
            "status": "pending_manual_creation",
        }),
        encoding="utf-8",
    )

    rf_consumed = epic_dir / "RF-012-busqueda"
    rf_consumed.mkdir(parents=True)
    (rf_consumed / "pending-task.json").write_text(
        json.dumps({
            "rf_id": "RF-012",
            "title": "Búsqueda",
            "status": "consumed",
            "consumed_at": "2026-05-11T09:00:00Z",
        }),
        encoding="utf-8",
    )

    block = build_artifact_status_block(
        ado_id=149,
        work_item_type="Epic",
        execution_ids=[],
    )
    assert block is not None
    content = block["content"]
    assert "1 pendiente(s), 1 consumida(s)" in content
    assert "PENDIENTE rf=RF-008" in content
    assert "CONSUMIDA rf=RF-012" in content
    # La regla anti-pregunta está presente cuando hay pendientes
    assert "NO preguntes" in content


def test_pending_tasks_only_scanned_for_epics(repo_root, codex_runs_dir):
    """Para tickets non-Epic, no se reportan pending-task aunque existan."""
    from services.artifact_context import build_artifact_status_block

    epic_dir = repo_root / "Agentes" / "outputs" / "epic-200"
    rf = epic_dir / "RF-001"
    rf.mkdir(parents=True)
    (rf / "pending-task.json").write_text(
        json.dumps({"rf_id": "RF-001", "title": "x", "status": "pending_manual_creation"}),
        encoding="utf-8",
    )

    block = build_artifact_status_block(
        ado_id=200,
        work_item_type="Task",  # no Epic
        execution_ids=[],
    )
    # Ni comment.html ni manifest ni pending: como work_item_type != Epic se ignora pending
    assert block is None


def test_skips_malformed_pending_task(repo_root, codex_runs_dir):
    """Un pending-task.json malformado no debe romper el escaneo."""
    from services.artifact_context import build_artifact_status_block

    epic_dir = repo_root / "Agentes" / "outputs" / "epic-150"
    rf_bad = epic_dir / "RF-bad"
    rf_bad.mkdir(parents=True)
    (rf_bad / "pending-task.json").write_text("{not json", encoding="utf-8")

    rf_ok = epic_dir / "RF-ok"
    rf_ok.mkdir(parents=True)
    (rf_ok / "pending-task.json").write_text(
        json.dumps({"rf_id": "RF-OK", "title": "ok", "status": "pending_manual_creation"}),
        encoding="utf-8",
    )

    block = build_artifact_status_block(
        ado_id=150,
        work_item_type="Epic",
        execution_ids=[],
    )
    assert block is not None
    # Solo cuenta el válido
    assert "1 pendiente(s)" in block["content"]
    assert "RF-OK" in block["content"]


# ── MANIFEST de última ejecución ─────────────────────────────────────────────


def test_reports_latest_manifest_signals(repo_root, codex_runs_dir):
    from services.artifact_context import build_artifact_status_block

    # Ejecuciones 10, 12, 15 — la 15 es la más nueva
    for exec_id, status, completed in [(10, "completed", True), (12, "error", False), (15, "completed", True)]:
        rd = codex_runs_dir / str(exec_id)
        rd.mkdir()
        (rd / "MANIFEST.json").write_text(
            json.dumps({
                "schema_version": "1",
                "run_id": exec_id,
                "agent_type": "developer",
                "status": status,
                "signals": {"work_completed": completed},
                "written_at": "2026-05-10T00:00:00Z",
            }),
            encoding="utf-8",
        )

    block = build_artifact_status_block(
        ado_id=27002,
        work_item_type="Task",
        execution_ids=[10, 12, 15],
    )
    assert block is not None
    assert "execution_id=15" in block["content"]
    assert "status=completed" in block["content"]
    assert "work_completed=True" in block["content"]


# ── Helper inject_into_blocks ────────────────────────────────────────────────


def test_inject_is_idempotent(repo_root, codex_runs_dir):
    from services.artifact_context import (
        ARTIFACT_BLOCK_ID,
        inject_into_blocks,
    )

    output_dir = repo_root / "Agentes" / "outputs" / "27003"
    output_dir.mkdir(parents=True)
    (output_dir / "comment.html").write_text("<p>hi</p>", encoding="utf-8")

    blocks, info1 = inject_into_blocks(
        [],
        ado_id=27003,
        work_item_type="Task",
        execution_ids=[],
    )
    assert info1 and info1.get("injected") is True
    assert any(b.get("id") == ARTIFACT_BLOCK_ID for b in blocks)
    initial_len = len(blocks)

    blocks2, info2 = inject_into_blocks(
        blocks,
        ado_id=27003,
        work_item_type="Task",
        execution_ids=[],
    )
    assert info2 == {"skipped": "already_present"}
    assert len(blocks2) == initial_len


def test_inject_returns_unchanged_when_no_artifacts(repo_root, codex_runs_dir):
    from services.artifact_context import inject_into_blocks

    initial = [{"id": "operator-note", "kind": "editable", "content": "x"}]
    blocks, info = inject_into_blocks(
        initial,
        ado_id=99999,  # sin nada en disco
        work_item_type="Task",
        execution_ids=[],
    )
    assert info is None
    assert blocks == initial
