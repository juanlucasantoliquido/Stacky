"""Plan 148 F3 — Circuit-breaker cableado en el sync ADO (_startup_sync +
_ado_sync_error_response). Cubre: abre por PAT expirado, omite red cuando ya
esta abierto, preserva el warning legado con la flag OFF (revert byte-a-byte),
sync-v2 alimenta el breaker sin cambiar su 502, y un exito cierra el breaker.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import app as app_module  # noqa: E402
import services.project_context as _project_context_module  # noqa: E402
from config import config as _cfg  # noqa: E402
from services import integration_breaker as brk  # noqa: E402
from services.ado_client import AdoApiError  # noqa: E402

_PROJECT = "TESTPROJ148"


@pytest.fixture(autouse=True)
def _isolated_breaker(tmp_path, monkeypatch):
    """Aisla el JSON del breaker y desactiva la purga real de tickets.

    `resolve_project_context` cae a la sombra del proyecto activo REAL de la
    maquina si no encuentra config para el nombre dummy (fallback "helpful" de
    produccion) -> se neutraliza tambien ahi para que la key del breaker sea
    determinista y no dependa de que proyecto este activo en este checkout.
    """
    monkeypatch.setattr(brk, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(app_module, "get_active_project", lambda: _PROJECT)
    monkeypatch.setattr(app_module, "get_project_config", lambda name: {})
    monkeypatch.setattr(app_module, "purge_non_project_tickets", lambda keep_project: 0)
    monkeypatch.setattr(_project_context_module, "get_active_project", lambda: None)
    # build_ado_client resuelve contexto real (require_project_context) y lanza
    # ProjectContextError para un proyecto dummy sin config en disco; se
    # neutraliza porque lo que se ejercita aca es _ado_sync (mockeado por test),
    # no la construccion del cliente.
    monkeypatch.setattr(_project_context_module, "build_ado_client", lambda project_name=None: object())
    yield


def test_startup_sync_records_failure_on_pat_expired(monkeypatch):
    def _raise(client=None):
        raise AdoApiError(
            "TF400813: The Personal Access Token used has expired.",
            status_code=401,
        )

    monkeypatch.setattr(app_module, "_ado_sync", _raise)
    app_module._startup_sync(logging.getLogger("test.plan148.f3"))

    state = brk.get_state("ado_sync", _PROJECT)
    assert state.open is True
    assert state.reason == brk.REASON_PAT_EXPIRED


def test_startup_sync_skips_when_open(monkeypatch):
    brk.record_failure("ado_sync", _PROJECT, brk.REASON_PAT_EXPIRED, "PAT vencido")

    called = {"n": 0}

    def _spy(client=None):
        called["n"] += 1
        return {"project": _PROJECT, "fetched": 0, "created": 0, "updated": 0, "removed": 0}

    monkeypatch.setattr(app_module, "_ado_sync", _spy)
    app_module._startup_sync(logging.getLogger("test.plan148.f3"))

    assert called["n"] == 0


def test_flag_off_preserves_legacy_warning(monkeypatch, caplog):
    monkeypatch.setattr(_cfg, "STACKY_INTEGRATION_DEGRADATION_ENABLED", False)

    def _raise(client=None):
        raise AdoApiError("TF400813: The Personal Access Token used has expired.", status_code=401)

    monkeypatch.setattr(app_module, "_ado_sync", _raise)
    caplog.set_level(logging.WARNING)

    app_module._startup_sync(logging.getLogger("test.plan148.f3"))

    assert any("sync ADO falló:" in r.message for r in caplog.records)
    assert brk.get_state("ado_sync", _PROJECT).open is False


def test_sync_v2_feeds_breaker(monkeypatch):
    from app import create_app
    monkeypatch.setattr(app_module, "_startup_sync", lambda logger: None)
    flask_app = create_app()

    from api import tickets as tickets_module

    exc = AdoApiError("TF400813: The Personal Access Token used has expired.", status_code=401)
    with flask_app.app_context():
        resp, status = tickets_module._ado_sync_error_response(
            exc, route_label="sync-v2", project_name="RSPACIFICO"
        )

    assert status == 502
    assert brk.get_state("ado_sync", brk.ado_breaker_project("RSPACIFICO")).open is True


def test_sync_v2_skips_when_breaker_open(monkeypatch):
    """[F3.1 aditivo] Con el breaker ADO abierto, sync-v2 responde 200 degradado
    sin tocar la red (backoff honesto del board)."""
    from app import create_app
    monkeypatch.setattr(app_module, "_startup_sync", lambda logger: None)
    flask_app = create_app()

    brk.record_failure("ado_sync", brk.ado_breaker_project("RSPACIFICO"),
                        brk.REASON_PAT_EXPIRED, "PAT vencido")

    called = {"n": 0}
    import api.tickets as tickets_module
    monkeypatch.setattr(
        tickets_module, "_sync_via_provider_or_ado",
        lambda **kw: called.__setitem__("n", called["n"] + 1),
    )

    client = flask_app.test_client()
    resp = client.post("/api/tickets/sync-v2?project=RSPACIFICO")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["degraded"] is True
    assert body["reason"] == brk.REASON_PAT_EXPIRED
    assert called["n"] == 0  # nunca llego a golpear la red


def test_success_closes_breaker(monkeypatch):
    brk.record_failure("ado_sync", _PROJECT, brk.REASON_PAT_EXPIRED, "PAT vencido")
    # should_skip() esta True recien abierto (dentro de la ventana de backoff) ->
    # _startup_sync jamas llamaria a _ado_sync. Simular la ventana half-open
    # vencida (mismo criterio que test_retry_window_expires de F1) para poder
    # ejercitar el camino de exito -> record_success.
    future = brk._now() + brk._BACKOFF_MAX_SEC + 1
    monkeypatch.setattr(brk, "_now", lambda: future)

    def _ok(client=None):
        return {"project": _PROJECT, "fetched": 1, "created": 0, "updated": 1, "removed": 0}

    monkeypatch.setattr(app_module, "_ado_sync", _ok)
    app_module._startup_sync(logging.getLogger("test.plan148.f3"))

    assert brk.get_state("ado_sync", _PROJECT).open is False
