"""Plan 163 F5 — scanner de huellas + boot-scan automatico.

scan_text detecta huellas guardadas (resolved+log_guarded); run_boot_scan
escanea el tail del log mas reciente y REGISTRA hits en system_logs (AVISA, no
actua), no-op bajo STACKY_TEST_MODE. DB real en memoria (shared-cache).
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/

import pytest

from db import session_scope, init_db
from models import SystemLog
import services.error_fingerprints as ef

_ESC = chr(27)


@pytest.fixture(autouse=True)
def _reset_db():
    init_db()
    with session_scope() as s:
        s.query(SystemLog).filter_by(source="fingerprint_scan").delete()
    yield


def _fp(fid: str) -> dict:
    return next(f for f in ef.load_fingerprints() if f["id"] == fid)


def test_scan_log_sucio():
    sample = _fp("pipeline_status_404")["self_test"]["matches"][0]
    assert ef.scan_text(sample) == ["pipeline_status_404"]


def test_scan_log_limpio():
    clean = "\n".join(fp["self_test"]["clean"][0] for fp in ef.guarded_fingerprints())
    assert ef.scan_text(clean) == []


def test_scan_ansi():
    text = f"2026 INFO {_ESC}[32mx{_ESC}[0m fin"
    assert "ansi_in_file_log" in ef.scan_text(text)


def test_solo_guardadas():
    guarded = ef.guarded_fingerprints()
    ids = [fp["id"] for fp in guarded]
    assert "ado_workitem_type_vs402323" not in ids  # open
    assert "pm_no_snapshot_404" not in ids           # by_design
    assert all(fp["status"] == "resolved" and fp["log_guarded"] is True for fp in guarded)


def test_scan_multiple():
    guarded = ef.guarded_fingerprints()
    text = "\n".join(fp["self_test"]["matches"][0] for fp in guarded)
    hits = ef.scan_text(text)
    assert set(hits) == {fp["id"] for fp in guarded}


def test_boot_scan_escribe_warning(monkeypatch, tmp_path):
    monkeypatch.setenv("STACKY_TEST_MODE", "0")
    sample = _fp("pipeline_status_404")["self_test"]["matches"][0]
    logf = tmp_path / "stacky-2026-07-14.log"
    logf.write_text(sample, encoding="utf-8")
    monkeypatch.setattr(ef, "_latest_log_file", lambda: logf)
    hits = ef.run_boot_scan()
    assert hits == ["pipeline_status_404"]
    with session_scope() as s:
        rows = s.query(SystemLog).filter_by(source="fingerprint_scan", action="regression_detected").all()
        assert len(rows) == 1
        ctx = json.loads(rows[0].context_json)
    assert "pipeline_status_404" in ctx["hits"]


def test_boot_scan_limpio_no_escribe(monkeypatch, tmp_path):
    monkeypatch.setenv("STACKY_TEST_MODE", "0")
    clean = _fp("pipeline_status_404")["self_test"]["clean"][0]
    logf = tmp_path / "stacky-2026-07-16.log"
    logf.write_text(clean, encoding="utf-8")
    monkeypatch.setattr(ef, "_latest_log_file", lambda: logf)
    assert ef.run_boot_scan() == []
    with session_scope() as s:
        rows = s.query(SystemLog).filter_by(source="fingerprint_scan").all()
    assert len(rows) == 0


def test_boot_scan_noop_en_test_mode(monkeypatch):
    monkeypatch.setenv("STACKY_TEST_MODE", "1")
    called = []
    monkeypatch.setattr(ef, "_latest_log_file", lambda: called.append(1))
    assert ef.run_boot_scan() == []
    assert called == []


def test_boot_scan_sin_logs(monkeypatch):
    monkeypatch.setenv("STACKY_TEST_MODE", "0")
    monkeypatch.setattr(ef, "_latest_log_file", lambda: None)
    assert ef.run_boot_scan() == []
