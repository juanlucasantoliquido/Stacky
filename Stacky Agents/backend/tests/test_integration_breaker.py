"""Plan 148 F1 — Núcleo del circuit-breaker persistido + clasificador de errores.

Cubre: cerrado por defecto, apertura+skip, dedup de WARNING solo en transición,
backoff exponencial, ventana half-open, cierre por éxito/reset, clasificador de
AdoApiError, persistencia entre recargas, degradación ante fallas de IO [R4],
supervivencia ante keys malformadas [C6] y estabilidad de la key ADO [C3].
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import integration_breaker as brk  # noqa: E402
from services.ado_client import AdoApiError  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """Aísla el JSON del breaker en un tmp_path por test (nunca toca data real)."""
    monkeypatch.setattr(brk, "data_dir", lambda: tmp_path)
    return tmp_path


def test_closed_by_default():
    assert brk.should_skip("ado_sync", "RSPACIFICO") is False
    assert brk.get_state("ado_sync", "RSPACIFICO").open is False


def test_record_failure_opens_and_skips():
    state = brk.record_failure("ado_sync", "RSPACIFICO", brk.REASON_PAT_EXPIRED, "x")
    assert state.open is True
    assert brk.should_skip("ado_sync", "RSPACIFICO") is True


def test_warning_only_on_transition(caplog):
    caplog.set_level(logging.DEBUG, logger="stacky_agents.integration_breaker")
    brk.record_failure("ado_sync", "RSPACIFICO", brk.REASON_PAT_EXPIRED, "x")
    brk.record_failure("ado_sync", "RSPACIFICO", brk.REASON_PAT_EXPIRED, "x")
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1


def test_backoff_doubles():
    s1 = brk.record_failure("ado_sync", "RSPACIFICO", brk.REASON_PAT_EXPIRED, "x")
    s2 = brk.record_failure("ado_sync", "RSPACIFICO", brk.REASON_PAT_EXPIRED, "x")
    assert s2.seconds_until_retry >= s1.seconds_until_retry


def test_retry_window_expires(monkeypatch):
    brk.record_failure("ado_sync", "RSPACIFICO", brk.REASON_PAT_EXPIRED, "x")
    assert brk.should_skip("ado_sync", "RSPACIFICO") is True
    future = brk._now() + brk._BACKOFF_MAX_SEC + 1
    monkeypatch.setattr(brk, "_now", lambda: future)
    assert brk.should_skip("ado_sync", "RSPACIFICO") is False


def test_record_success_closes():
    brk.record_failure("ado_sync", "RSPACIFICO", brk.REASON_PAT_EXPIRED, "x")
    brk.record_success("ado_sync", "RSPACIFICO")
    assert brk.should_skip("ado_sync", "RSPACIFICO") is False
    assert brk.get_state("ado_sync", "RSPACIFICO").open is False


def test_reset_closes():
    brk.record_failure("ado_sync", "RSPACIFICO", brk.REASON_PAT_EXPIRED, "x")
    brk.reset("ado_sync", "RSPACIFICO")
    assert brk.should_skip("ado_sync", "RSPACIFICO") is False
    assert brk.get_state("ado_sync", "RSPACIFICO").open is False


def test_classify_pat_expired():
    exc = AdoApiError("... The Personal Access Token used has expired.")
    reason, _msg = brk.classify_ado_error(exc)
    assert reason == brk.REASON_PAT_EXPIRED


def test_classify_project_missing():
    exc = AdoApiError("The following project does not exist: RSPACIFICO")
    reason, _msg = brk.classify_ado_error(exc)
    assert reason == brk.REASON_ADO_PROJECT_MISSING


def test_persistence_across_reload(tmp_path):
    brk.record_failure("ado_sync", "RSPACIFICO", brk.REASON_PAT_EXPIRED, "x")
    # "recarga" = leer fresco desde disco, sin depender de estado en memoria.
    fresh = brk._load()
    assert fresh.get(brk.integration_key("ado_sync", "RSPACIFICO"), {}).get("open") is True
    assert brk.get_state("ado_sync", "RSPACIFICO").open is True


def test_io_failure_degrades_closed(tmp_path, monkeypatch):
    # Ruta imposible: un archivo regular ocupa el lugar de un directorio padre,
    # por lo que mkdir(parents=True) en _save() debe fallar con OSError y
    # degradar en silencio (invariante "NUNCA lanza").
    blocked_file = tmp_path / "blocked"
    blocked_file.write_text("soy un archivo, no un directorio", encoding="utf-8")
    impossible = blocked_file / "nested"
    monkeypatch.setattr(brk, "data_dir", lambda: impossible)

    # record_failure no debe lanzar aunque _save falle internamente.
    brk.record_failure("ado_sync", "RSPACIFICO", brk.REASON_PAT_EXPIRED, "x")

    # Como el write nunca persistió, el estado sigue "cerrado" (degradado).
    assert brk.should_skip("ado_sync", "RSPACIFICO") is False


def test_all_states_survives_malformed_key(tmp_path):
    p = tmp_path / brk._FILENAME
    p.write_text(json.dumps({"basura": {"open": True}}), encoding="utf-8")
    out = brk.all_states()
    assert isinstance(out, dict)


def test_ado_breaker_project_stable_key(monkeypatch):
    class _Ctx:
        tracker_project = "RSPACIFICO-TRACKER"

    monkeypatch.setattr(
        "services.project_context.resolve_project_context",
        lambda project_name=None, **kw: _Ctx(),
    )
    assert brk.ado_breaker_project("RSPACIFICO") == "RSPACIFICO-TRACKER"

    def _raise(project_name=None, **kw):
        raise RuntimeError("sin contexto")

    monkeypatch.setattr("services.project_context.resolve_project_context", _raise)
    assert brk.ado_breaker_project("RAW-NAME") == "RAW-NAME"
