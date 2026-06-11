"""Tests de services/artifact_validator.py (F1.3/F1.4 — plan robustecimiento arnés).

Cubre la causa raíz confirmada de "crea archivos pero no la task":
JSON inválido + mismatch ADO id real vs ordinal.
"""
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


def _write_pending(tmp_path: Path, epic_dir: str, payload) -> Path:
    rf_dir = tmp_path / epic_dir / "RF-001"
    rf_dir.mkdir(parents=True, exist_ok=True)
    pt = rf_dir / "pending-task.json"
    if isinstance(payload, str):
        pt.write_text(payload, encoding="utf-8")
    else:
        pt.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return pt


def test_invalid_json_is_hard_error(tmp_path):
    from services import artifact_validator as av

    pt = _write_pending(tmp_path, "epic-206", '{"epic_id": 206,,}')
    res = av.validate_pending_task_file(pt, check_db=False)
    assert not res.valid
    assert any("JSON inválido" in e for e in res.errors)


def test_missing_required_fields_listed(tmp_path):
    from services import artifact_validator as av

    payload = _valid_payload()
    del payload["title"]
    del payload["plan_de_pruebas_path"]
    pt = _write_pending(tmp_path, "epic-206", payload)
    res = av.validate_pending_task_file(pt, check_db=False)
    assert not res.valid
    joined = " ".join(res.errors)
    assert "title" in joined and "plan_de_pruebas_path" in joined


def test_epic_dir_vs_payload_mismatch_is_error(tmp_path):
    from services import artifact_validator as av

    # Directorio con el ordinal (epic-1) pero epic_id real en el payload.
    pt = _write_pending(tmp_path, "epic-1", _valid_payload(epic_id=206))
    res = av.validate_pending_task_file(pt, check_db=False)
    assert not res.valid
    assert any("ordinal" in e for e in res.errors)


def test_unknown_epic_id_flags_ordinal_root_cause(tmp_path, monkeypatch):
    from services import artifact_validator as av

    # DB dice que el ticket NO existe → error con la pista de ordinal vs ADO id.
    monkeypatch.setattr(av, "_ticket_exists", lambda ado_id: False)
    pt = _write_pending(tmp_path, "epic-3", _valid_payload(epic_id=3))
    res = av.validate_pending_task_file(pt, check_db=True)
    assert not res.valid
    assert any("ordinal" in e for e in res.errors)


def test_valid_pending_task_passes(tmp_path, monkeypatch):
    from services import artifact_validator as av

    monkeypatch.setattr(av, "_ticket_exists", lambda ado_id: True)
    pt = _write_pending(tmp_path, "epic-206", _valid_payload())
    (pt.parent / "plan-de-pruebas.md").write_text("# plan", encoding="utf-8")
    res = av.validate_pending_task_file(pt, check_db=True)
    assert res.valid, res.errors
    assert res.warnings == []


def test_missing_plan_file_is_warning_not_error(tmp_path):
    from services import artifact_validator as av

    pt = _write_pending(tmp_path, "epic-206", _valid_payload())
    res = av.validate_pending_task_file(pt, check_db=False)
    assert res.valid
    assert any("plan_de_pruebas_path" in w for w in res.warnings)


def test_invalid_status_rejected(tmp_path):
    from services import artifact_validator as av

    payload = _valid_payload()
    payload["status"] = "done"
    pt = _write_pending(tmp_path, "epic-206", payload)
    res = av.validate_pending_task_file(pt, check_db=False)
    assert not res.valid
    assert any("status" in e for e in res.errors)


def test_comment_html_empty_is_error(tmp_path):
    from services import artifact_validator as av

    f = tmp_path / "comment.html"
    f.write_text("   \n", encoding="utf-8")
    res = av.validate_comment_html_file(f)
    assert not res.valid

    f.write_text("<p>ok</p>", encoding="utf-8")
    assert av.validate_comment_html_file(f).valid


def test_validate_artifact_path_dispatch(tmp_path):
    from services import artifact_validator as av

    other = tmp_path / "notas.md"
    other.write_text("x", encoding="utf-8")
    assert av.validate_artifact_path(other).kind == "other"
    assert av.validate_artifact_path(other).valid


def test_validate_run_artifacts_scans_present_artifacts_only(tmp_path):
    from services import artifact_validator as av

    # Sin artifacts → reporte vacío y ok (la ausencia no dispara corrección).
    report = av.validate_run_artifacts(ado_id=206, outputs_root=tmp_path, check_db=False)
    assert report.checked == 0 and report.ok

    # comment.html vacío + pending inválido → ambos reportados.
    (tmp_path / "206").mkdir()
    (tmp_path / "206" / "comment.html").write_text("", encoding="utf-8")
    _write_pending(tmp_path, "epic-206", "{broken")
    report = av.validate_run_artifacts(ado_id=206, outputs_root=tmp_path, check_db=False)
    assert report.checked == 2
    assert len(report.invalid) == 2


def test_validate_run_artifacts_catches_ordinal_epic_dir_via_since(tmp_path):
    from services import artifact_validator as av

    # El agente escribió en epic-1 (ordinal) en vez de epic-206: el escaneo
    # por mtime (since_epoch) lo atrapa igual.
    _write_pending(tmp_path, "epic-1", _valid_payload(epic_id=206))
    report = av.validate_run_artifacts(
        ado_id=206, outputs_root=tmp_path, since_epoch=0.0, check_db=False
    )
    assert report.checked == 1
    assert not report.ok
