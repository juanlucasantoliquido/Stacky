"""
tests/unit/test_sprint1_run_identity.py — Sprint 1: run_id & artifact isolation.

Valida los criterios de aceptación del Sprint 1 del roadmap:

  RID-1: Dos re-runs del mismo ticket generan run_id distintos con formato correcto.
  RID-2: Cada run crea su propio evidence_dir (evidence/<ticket>/<run_id>/).
  RID-3: Ningún execution.jsonl nuevo contiene más de un session_start/session_end.
  RID-4: Todos los eventos del JSONL contienen run_id.
  RID-5: session_end.data.verdict nunca es null en runs nuevos.
  RID-6: latest.json y index.json creados en evidence/<ticket>/.
  RID-7: artifact_root_created evento presente en execution.jsonl.
  RID-8: run_id y artifact_root presentes en el resultado del pipeline.
  RID-9: log_analyzer carga sesiones del nuevo formato anidado y del legacy plano.
  RID-10: _build_output normaliza verdict=None → "BLOCKED".

No requiere ADO, LLM ni browser — todo mockeado.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Agregar root del tool al path
_TOOL_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_TOOL_DIR))
sys.path.insert(0, str(_TOOL_DIR.parent.parent / "Stacky Agents" / "backend"))

os.environ.setdefault("STACKY_LLM_BACKEND", "mock")
os.environ.setdefault("QA_UAT_SKIP_SMOKE", "true")

_FIXTURES = Path(__file__).parent.parent / "fixtures"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_jsonl(path: Path) -> list[dict]:
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


def _ticket_fixture() -> dict:
    """Carga el fixture de ticket 70 si existe, sino devuelve stub mínimo."""
    ticket_path = _FIXTURES / "ticket_70.json"
    if ticket_path.is_file():
        base = json.loads(ticket_path.read_text(encoding="utf-8"))
        return {"ok": True, **base}
    return {
        "ok": True,
        "ticket_id": 70,
        "ticket": {"id": 70, "title": "Sprint 1 test ticket", "description": "FrmAgenda.aspx"},
        "description_md": "Test sprint 1",
        "plan_pruebas": [],
    }


def _run_id_format_ok(run_id: str, ticket_id: int) -> bool:
    """Verifica que run_id cumple el formato uat-<ticket>-<YYYYMMDDTHHMMSSZ>-<uuid6>."""
    pattern = rf"^uat-{ticket_id}-\d{{8}}T\d{{6}}Z-[0-9a-f]{{6}}$"
    return bool(re.match(pattern, run_id))


# ── RID-10: _build_output normaliza verdict=None ──────────────────────────────

def test_build_output_normalizes_none_verdict():
    """_build_output debe devolver 'BLOCKED' cuando verdict es None explícito."""
    from qa_uat_pipeline import _build_output

    failed_result = {
        "ok": False,
        "verdict": None,     # None explícito — bug en el runner
        "category": None,    # None explícito
        "reason": None,
        "stage": "runner",
    }
    import time
    out = _build_output(122, {}, failed_result, time.time() - 1)
    assert out["verdict"] == "BLOCKED", f"Expected BLOCKED, got {out['verdict']!r}"
    assert out["category"] == "PIP", f"Expected PIP, got {out['category']!r}"


def test_build_output_preserves_explicit_verdict():
    """_build_output no debe sobreescribir un verdict explícito válido."""
    from qa_uat_pipeline import _build_output

    import time
    out = _build_output(122, {}, {"ok": False, "verdict": "FAIL", "category": "APP"}, time.time())
    assert out["verdict"] == "FAIL"
    assert out["category"] == "APP"


# ── RID-1: run_id format ──────────────────────────────────────────────────────

def test_run_id_format_via_pipeline(tmp_path):
    """run_id generado por pipeline cumple el formato uat-<ticket>-<ts>-<uuid6>."""
    import qa_uat_pipeline as qp

    # El pipeline importa funciones dinámicamente dentro de run(),
    # por lo que patcheamos en los módulos fuente.
    mock_pf_result = MagicMock()
    mock_pf_result.ok = True
    mock_pf_result.verdict = "PASS"
    mock_pf_result.reason = None
    mock_pf_result.base_url = "http://localhost"

    with patch.object(qp, "_TOOL_ROOT", tmp_path), \
         patch("environment_preflight.run_environment_preflight", return_value=mock_pf_result), \
         patch("deployment_fingerprint.check_deployment_fingerprint", side_effect=ImportError), \
         patch("smoke_path_checker.run_smoke_path", side_effect=ImportError), \
         patch("uat_ticket_reader.run", return_value=_ticket_fixture()), \
         patch.object(qp, "_run_pipeline_stages", return_value={
             "ok": True, "verdict": "PASS", "ticket_id": 70,
             "stages": {}, "elapsed_s": 0.1,
         }):
        result = qp.run(ticket_id=70, mode="dry-run", verbose=False)

    run_id = result.get("run_id", "")
    assert _run_id_format_ok(run_id, 70), (
        f"run_id '{run_id}' no cumple formato uat-70-<YYYYMMDDTHHMMSSZ>-<uuid6>"
    )


# ── RID-2: evidence_dir anidado ───────────────────────────────────────────────

def _pipeline_run(tmp_path, ticket_id: int = 70):
    """Helper reutilizable: corre el pipeline con todo mockeado."""
    import qa_uat_pipeline as qp

    mock_pf_result = MagicMock()
    mock_pf_result.ok = True
    mock_pf_result.verdict = "PASS"
    mock_pf_result.reason = None
    mock_pf_result.base_url = "http://localhost"

    with patch.object(qp, "_TOOL_ROOT", tmp_path), \
         patch("environment_preflight.run_environment_preflight", return_value=mock_pf_result), \
         patch("deployment_fingerprint.check_deployment_fingerprint", side_effect=ImportError), \
         patch("smoke_path_checker.run_smoke_path", side_effect=ImportError), \
         patch("uat_ticket_reader.run", return_value=_ticket_fixture()), \
         patch.object(qp, "_run_pipeline_stages", return_value={
             "ok": True, "verdict": "PASS", "ticket_id": ticket_id,
             "stages": {}, "elapsed_s": 0.1,
         }):
        return qp.run(ticket_id=ticket_id, mode="dry-run", verbose=False)


def test_evidence_dir_is_nested_under_ticket(tmp_path):
    """El artifact_root debe ser evidence/<ticket>/<run_id>/."""
    result = _pipeline_run(tmp_path)
    artifact_root = Path(result.get("artifact_root", ""))
    run_id = result.get("run_id", "")
    import qa_uat_pipeline as qp
    expected = tmp_path / "evidence" / "70" / run_id
    assert artifact_root == expected, f"artifact_root={artifact_root}, expected={expected}"


# ── RID-6: latest.json y index.json ──────────────────────────────────────────

def test_latest_and_index_written(tmp_path):
    """latest.json e index.json deben crearse en evidence/<ticket>/."""
    result = _pipeline_run(tmp_path)
    ticket_dir = tmp_path / "evidence" / "70"
    run_id = result.get("run_id", "")

    latest_path = ticket_dir / "latest.json"
    assert latest_path.is_file(), "latest.json no fue creado"
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    assert latest["run_id"] == run_id

    index_path = ticket_dir / "index.json"
    assert index_path.is_file(), "index.json no fue creado"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert isinstance(index, list) and len(index) >= 1
    assert index[0]["run_id"] == run_id


def test_index_accumulates_multiple_runs(tmp_path):
    """index.json debe acumular entradas con cada run del mismo ticket."""
    import execution_logger as el

    r1 = _pipeline_run(tmp_path)
    # Limpiar registry del logger entre runs para que el segundo run cree un nuevo logger
    with el._registry_lock:
        el._registry.clear()

    r2 = _pipeline_run(tmp_path)
    with el._registry_lock:
        el._registry.clear()

    assert r1["run_id"] != r2["run_id"], "Dos runs deben tener run_id distintos"

    index = json.loads((tmp_path / "evidence" / "70" / "index.json").read_text(encoding="utf-8"))
    run_ids = [e["run_id"] for e in index]
    assert r1["run_id"] in run_ids
    assert r2["run_id"] in run_ids


# ── RID-3: un solo session_start/session_end por JSONL ───────────────────────

class TestExecutionLoggerRunId:
    """Tests directos del ExecutionLogger para validar Sprint 1."""

    def test_run_id_in_every_event(self, tmp_path):
        """Cada evento escrito debe incluir run_id como campo top-level."""
        from execution_logger import ExecutionLogger

        log_dir = tmp_path / "evidence" / "122" / "uat-122-test-abcdef"
        log = ExecutionLogger("uat-122-test-abcdef", evidence_dir=log_dir,
                              run_id="uat-122-test-abcdef")
        log.session_start({"mode": "dry-run", "ticket_id": 122})
        log.info("test message")
        log.session_end({"ok": True, "verdict": "PASS", "elapsed_s": 0.1})
        log.close()

        events = _read_jsonl(log_dir / "execution.jsonl")
        for e in events:
            assert "run_id" in e, f"Evento sin run_id: {e.get('event')}"
            assert e["run_id"] == "uat-122-test-abcdef", (
                f"run_id incorrecto en evento {e.get('event')}: {e.get('run_id')!r}"
            )

    def test_single_session_start_end(self, tmp_path):
        """Un ExecutionLogger = un session_start y un session_end."""
        from execution_logger import ExecutionLogger

        log_dir = tmp_path / "evidence" / "122" / "uat-122-test-111111"
        log = ExecutionLogger("uat-122-test-111111", evidence_dir=log_dir,
                              run_id="uat-122-test-111111")
        log.session_start({"mode": "dry-run", "ticket_id": 122})
        log.info("step 1")
        log.session_end({"ok": True, "verdict": "PASS", "elapsed_s": 0.5})
        log.close()

        events = _read_jsonl(log_dir / "execution.jsonl")
        starts = [e for e in events if e["event"] == "session_start"]
        ends   = [e for e in events if e["event"] == "session_end"]
        assert len(starts) == 1, f"Esperaba 1 session_start, encontré {len(starts)}"
        assert len(ends)   == 1, f"Esperaba 1 session_end, encontré {len(ends)}"

    def test_verdict_not_null_in_session_end(self, tmp_path):
        """session_end.data.verdict no puede ser null."""
        from execution_logger import ExecutionLogger

        log_dir = tmp_path / "evidence" / "122" / "uat-122-test-222222"
        log = ExecutionLogger("uat-122-test-222222", evidence_dir=log_dir,
                              run_id="uat-122-test-222222")
        log.session_start({"mode": "dry-run", "ticket_id": 122})
        log.session_end({"ok": False, "verdict": "BLOCKED", "category": "OPS",
                         "reason": "TEST", "elapsed_s": 0.1})
        log.close()

        events = _read_jsonl(log_dir / "execution.jsonl")
        session_end = next(e for e in events if e["event"] == "session_end")
        verdict = (session_end.get("data") or {}).get("verdict")
        assert verdict is not None, "session_end tiene verdict null"
        assert verdict in ("PASS", "FAIL", "BLOCKED", "MIXED", "SKIPPED"), (
            f"Verdict inválido: {verdict!r}"
        )

    def test_artifact_root_created_event(self, tmp_path):
        """artifact_root_created debe estar presente en execution.jsonl."""
        from execution_logger import ExecutionLogger

        run_id = "uat-122-test-333333"
        log_dir = tmp_path / "evidence" / "122" / run_id
        log = ExecutionLogger(run_id, evidence_dir=log_dir, run_id=run_id)
        log.session_start({"mode": "dry-run", "ticket_id": 122})
        log.artifact_root_created(str(log_dir))
        log.session_end({"ok": True, "verdict": "PASS", "elapsed_s": 0.1})
        log.close()

        events = _read_jsonl(log_dir / "execution.jsonl")
        arc_events = [e for e in events if e["event"] == "artifact_root_created"]
        assert len(arc_events) == 1, "artifact_root_created no encontrado"
        assert arc_events[0]["data"]["artifact_root"] == str(log_dir)


# ── RID-9: log_analyzer carga formato nuevo y legacy ─────────────────────────

class TestLogAnalyzerFormats:
    """Valida que log_analyzer lee tanto formato anidado (Sprint 1) como legacy."""

    def _write_jsonl(self, path: Path, events: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")

    def test_loads_new_nested_format(self, tmp_path):
        """log_analyzer debe cargar evidence/<ticket>/<run_id>/execution.jsonl."""
        from log_analyzer import _load_sessions

        run_id = "uat-122-20260509T120000Z-abc123"
        jsonl_path = tmp_path / "evidence" / "122" / run_id / "execution.jsonl"
        self._write_jsonl(jsonl_path, [
            {"ts": "2026-05-09T12:00:00Z", "run_id": run_id, "session_id": run_id,
             "seq": 1, "event": "session_start", "data": {"params": {}}},
            {"ts": "2026-05-09T12:01:00Z", "run_id": run_id, "session_id": run_id,
             "seq": 2, "event": "session_end", "ok": True,
             "data": {"verdict": "PASS", "elapsed_s": 60.0}},
        ])

        sessions = _load_sessions(evidence_root=tmp_path / "evidence")
        assert len(sessions) == 1
        s = sessions[0]
        assert s.session_id == run_id
        assert s.run_id == run_id
        assert s.ticket_id == "122"
        assert s.verdict == "PASS"

    def test_loads_legacy_flat_format(self, tmp_path):
        """log_analyzer debe seguir cargando evidence/<session_id>/execution.jsonl."""
        from log_analyzer import _load_sessions

        jsonl_path = tmp_path / "evidence" / "70" / "execution.jsonl"
        self._write_jsonl(jsonl_path, [
            {"ts": "2026-05-09T10:00:00Z", "session_id": "70",
             "seq": 1, "event": "session_start", "data": {"params": {}}},
            {"ts": "2026-05-09T10:01:00Z", "session_id": "70",
             "seq": 2, "event": "session_end", "ok": False,
             "data": {"verdict": "BLOCKED", "elapsed_s": 30.0}},
        ])

        sessions = _load_sessions(evidence_root=tmp_path / "evidence")
        assert len(sessions) == 1
        s = sessions[0]
        assert s.session_id == "70"
        assert s.verdict == "BLOCKED"

    def test_mixed_new_and_legacy(self, tmp_path):
        """log_analyzer debe cargar ambos formatos en la misma llamada."""
        from log_analyzer import _load_sessions

        # Legacy
        jsonl_legacy = tmp_path / "evidence" / "70" / "execution.jsonl"
        self._write_jsonl(jsonl_legacy, [
            {"ts": "2026-05-08T10:00:00Z", "session_id": "70", "seq": 1,
             "event": "session_start", "data": {"params": {}}},
            {"ts": "2026-05-08T10:01:00Z", "session_id": "70", "seq": 2,
             "event": "session_end", "ok": True, "data": {"verdict": "PASS", "elapsed_s": 60}},
        ])

        # Nuevo
        run_id = "uat-122-20260509T120000Z-def456"
        jsonl_new = tmp_path / "evidence" / "122" / run_id / "execution.jsonl"
        self._write_jsonl(jsonl_new, [
            {"ts": "2026-05-09T12:00:00Z", "run_id": run_id, "session_id": run_id,
             "seq": 1, "event": "session_start", "data": {"params": {}}},
            {"ts": "2026-05-09T12:01:00Z", "run_id": run_id, "session_id": run_id,
             "seq": 2, "event": "session_end", "ok": False,
             "data": {"verdict": "BLOCKED", "elapsed_s": 30}},
        ])

        sessions = _load_sessions(evidence_root=tmp_path / "evidence")
        assert len(sessions) == 2
        verdicts = {s.verdict for s in sessions}
        assert "PASS" in verdicts
        assert "BLOCKED" in verdicts
