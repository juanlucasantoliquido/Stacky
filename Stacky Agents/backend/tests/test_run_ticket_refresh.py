"""Plan 133 F1 — Refresh just-in-time del snapshot local del ticket antes del run."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db import session_scope  # noqa: E402
from models import Ticket  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def app_ctx():
    """Inicializa la app (y la DB sqlite in-memory) una vez por módulo."""
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    yield app


class _MockUpsert:
    def __init__(self):
        self.calls = 0
        self.impl = lambda client, ado_id: {"ok": True}

    def __call__(self, client, ado_id):
        self.calls += 1
        return self.impl(client, ado_id)


@pytest.fixture
def mock_upsert(monkeypatch):
    """Parchea upsert_single_work_item y build_ado_client para no tocar red real."""
    from services import ado_sync, project_context

    mock = _MockUpsert()
    monkeypatch.setattr(ado_sync, "upsert_single_work_item", mock)
    monkeypatch.setattr(project_context, "build_ado_client", lambda **kwargs: object())
    return mock


def _make_ticket(**overrides) -> int:
    defaults = dict(
        ado_id=331,
        project="Strategist_Pacifico",
        title="Task de prueba",
        ado_state="To Do",
        work_item_type="Task",
        tracker_type="azure_devops",
    )
    defaults.update(overrides)
    with session_scope() as session:
        t = Ticket(**defaults)
        session.add(t)
        session.flush()
        return t.id


def test_flag_off_es_noop(monkeypatch, mock_upsert):
    from config import config
    from services import run_ticket_refresh

    monkeypatch.setattr(config, "STACKY_RUN_TICKET_REFRESH_ENABLED", False)
    ticket_id = _make_ticket()
    result = run_ticket_refresh.refresh_ticket_snapshot(ticket_id)
    assert result == {"refreshed": False, "reason": "flag_off"}
    assert mock_upsert.calls == 0


def test_refresh_pisa_snapshot_stale(monkeypatch, mock_upsert):
    from config import config
    from services import run_ticket_refresh

    monkeypatch.setattr(config, "STACKY_RUN_TICKET_REFRESH_ENABLED", True)
    ticket_id = _make_ticket(ado_state="To Do")

    def _fake_upsert(client, ado_id):
        with session_scope() as session:
            t = session.query(Ticket).filter_by(id=ticket_id).first()
            t.ado_state = "Doing"
        return {"ado_state": "Doing"}

    mock_upsert.impl = _fake_upsert

    result = run_ticket_refresh.refresh_ticket_snapshot(ticket_id)
    assert result == {"refreshed": True, "reason": "ok"}
    with session_scope() as session:
        t = session.query(Ticket).filter_by(id=ticket_id).first()
        assert t.ado_state == "Doing"


def test_error_de_red_es_fail_open(monkeypatch, mock_upsert):
    from config import config
    from services import run_ticket_refresh

    monkeypatch.setattr(config, "STACKY_RUN_TICKET_REFRESH_ENABLED", True)
    ticket_id = _make_ticket()

    def _raise(client, ado_id):
        raise RuntimeError("timeout")

    mock_upsert.impl = _raise

    result = run_ticket_refresh.refresh_ticket_snapshot(ticket_id)
    assert result["refreshed"] is False
    assert result["reason"].startswith("tracker_error:")


@pytest.mark.parametrize("ado_id", [-6, 0])
def test_ado_id_negativo_o_cero_es_noop(monkeypatch, mock_upsert, ado_id):
    from config import config
    from services import run_ticket_refresh

    monkeypatch.setattr(config, "STACKY_RUN_TICKET_REFRESH_ENABLED", True)
    ticket_id = _make_ticket(ado_id=ado_id)
    result = run_ticket_refresh.refresh_ticket_snapshot(ticket_id)
    assert result == {"refreshed": False, "reason": "no_ado_id"}
    assert mock_upsert.calls == 0


def test_ticket_id_none_o_inexistente_es_noop(monkeypatch, mock_upsert):
    from config import config
    from services import run_ticket_refresh

    monkeypatch.setattr(config, "STACKY_RUN_TICKET_REFRESH_ENABLED", True)
    assert run_ticket_refresh.refresh_ticket_snapshot(None) == {
        "refreshed": False, "reason": "no_ado_id",
    }
    assert run_ticket_refresh.refresh_ticket_snapshot(999999) == {
        "refreshed": False, "reason": "no_ado_id",
    }
    assert mock_upsert.calls == 0


def test_tracker_no_ado_es_noop(monkeypatch, mock_upsert):
    from config import config
    from services import run_ticket_refresh

    monkeypatch.setattr(config, "STACKY_RUN_TICKET_REFRESH_ENABLED", True)
    ticket_id = _make_ticket(tracker_type="gitlab")
    result = run_ticket_refresh.refresh_ticket_snapshot(ticket_id)
    assert result == {"refreshed": False, "reason": "non_ado_tracker"}
    assert mock_upsert.calls == 0


def test_usa_cache_ttl(monkeypatch, mock_upsert):
    from config import config
    from services import ado_read_cache, run_ticket_refresh

    monkeypatch.setattr(config, "STACKY_RUN_TICKET_REFRESH_ENABLED", True)
    monkeypatch.setattr(config, "STACKY_ADO_READ_CACHE_TTL_SEC", 60)
    ado_read_cache.clear()
    ticket_id = _make_ticket()

    run_ticket_refresh.refresh_ticket_snapshot(ticket_id)
    run_ticket_refresh.refresh_ticket_snapshot(ticket_id)

    assert mock_upsert.calls == 1
    ado_read_cache.clear()
