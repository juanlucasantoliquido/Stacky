"""tests/test_persist_incident_ticket.py — Plan 166 F1.

Publicar una Issue de incidencia persiste su Ticket local al instante (no
espera al sync de ADO). Espeja los helpers de
tests/test_plan131_incident_preview_publish.py (_make_app/_flag/_patch_run/
FakeProvider) — C10 del plan.
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import runtime_paths
from db import session_scope
from models import Ticket
from services import doc_indexer, incident_store
from services.tracker_provider import TrackerItem


@pytest.fixture(autouse=True)
def _isolate_docs_root(tmp_path, monkeypatch):
    monkeypatch.setattr(doc_indexer, "STACKY_AGENTS_ROOT", tmp_path)


OUTPUT_FULL_HTML = """
<h1>[INC] La pantalla de login se rompe</h1>
<h2>RESUMEN EJECUTIVO</h2><p>Los usuarios no pueden ingresar.</p>
<h2>CONTEXTO DE NEGOCIO</h2><p>Afecta el proceso de alta de clientes.</p>
<h2>ANALISIS FUNCIONAL</h2><p>Comportamiento esperado vs observado.</p>
<h2>ANALISIS TECNICO</h2><p>Hipotesis de causa raiz en backend/services/foo.py.</p>
<h2>PASOS DE REPRODUCCION</h2><ol><li>Entrar a login</li></ol>
<h2>CRITERIOS DE ACEPTACION</h2><ul><li>El login funciona</li></ul>
<h2>ARCHIVOS Y MODULOS PROBABLES</h2><ul><li>backend/services/foo.py</li></ul>
<h2>EPICA RELACIONADA</h2><p>EPICA: 267 | CONFIANZA: 85 | RAZON: afecta el alta de clientes</p>
<h2>PRIORIDAD Y ESTIMACION</h2><p>Prioridad: alta. Estimacion: S.</p>
"""


class FakeProvider:
    def __init__(self):
        self.created_items: list[TrackerItem] = []
        self._next_id = 999

    def create_item(self, item: TrackerItem) -> dict:
        self.created_items.append(item)
        self._next_id += 1
        return {"id": self._next_id, "web_url": f"https://fake.tracker/{self._next_id}"}

    def item_url(self, item_id: str) -> str:
        return f"https://fake.tracker/{item_id}"

    def post_comment(self, item_id: str, body_html: str) -> dict:
        return {"ok": True}

    def upload_attachment(self, file_path: str, file_name: str) -> dict:
        return {"id": f"att-{file_name}"}

    def link_attachment(self, item_id: str, attachment: dict) -> dict:
        return {"ok": True}


def _make_app():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@contextmanager
def _flag(enabled: bool, *, persist: bool = True):
    import config as cfg
    original_resolver = getattr(cfg.config, "STACKY_INCIDENT_RESOLVER_ENABLED", False)
    original_persist = getattr(cfg.config, "STACKY_INCIDENT_TICKET_PERSIST_ENABLED", True)
    cfg.config.STACKY_INCIDENT_RESOLVER_ENABLED = enabled
    cfg.config.STACKY_INCIDENT_TICKET_PERSIST_ENABLED = persist
    try:
        yield
    finally:
        cfg.config.STACKY_INCIDENT_RESOLVER_ENABLED = original_resolver
        cfg.config.STACKY_INCIDENT_TICKET_PERSIST_ENABLED = original_persist


def _patch_run(monkeypatch, output: str | None, execution_id: int = 1):
    import api.tickets as t_mod
    fake_run = MagicMock()
    fake_run.id = execution_id
    fake_run.output = output
    fake_run.project_name = None
    fake_run.metadata_dict = {}
    monkeypatch.setattr(t_mod, "_get_run_for_preview", lambda eid, *, db: fake_run, raising=False)


def _create_incident(tmp_path, monkeypatch, text="incidencia de prueba", files=None):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    return incident_store.create_incident(text, files or [])


def _publish(client, incident_id, execution_id=1, extra=None):
    payload = {"incident_id": incident_id, "execution_id": execution_id, "confirm": True}
    if extra:
        payload.update(extra)
    return client.post("/api/tickets/incidents/publish", json=payload)


def test_publish_persists_local_issue_ticket(tmp_path, monkeypatch):
    incident = _create_incident(tmp_path, monkeypatch)
    _patch_run(monkeypatch, OUTPUT_FULL_HTML)
    fake_provider = FakeProvider()
    monkeypatch.setattr("services.tracker_provider.get_tracker_provider", lambda project: fake_provider)

    app = _make_app()
    with _flag(True):
        with app.test_client() as client:
            resp = _publish(client, incident["id"])
    assert resp.status_code == 201, resp.get_json()
    tracker_id = resp.get_json()["tracker_id"]

    with session_scope() as session:
        row = session.query(Ticket).filter(Ticket.ado_id == int(tracker_id)).first()
        assert row is not None
        assert row.work_item_type == "Issue"


def test_persist_sets_parent_when_epic_linked(tmp_path, monkeypatch):
    incident = _create_incident(tmp_path, monkeypatch)
    _patch_run(monkeypatch, OUTPUT_FULL_HTML)
    fake_provider = FakeProvider()
    monkeypatch.setattr("services.tracker_provider.get_tracker_provider", lambda project: fake_provider)

    app = _make_app()
    with _flag(True):
        with app.test_client() as client:
            resp = _publish(client, incident["id"], extra={"override_epic_id": 267})
    assert resp.status_code == 201, resp.get_json()
    tracker_id = resp.get_json()["tracker_id"]

    with session_scope() as session:
        row = session.query(Ticket).filter(Ticket.ado_id == int(tracker_id)).first()
        assert row is not None
        assert row.parent_ado_id == 267


def test_persist_idempotent(tmp_path, monkeypatch):
    from api.tickets import _persist_incident_ticket
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)

    _persist_incident_ticket(
        ado_id=4242, title="t1", description_html="<p>d</p>", url="https://x/4242",
        project_name=None, work_item_type="Issue", parent_ado_id=None,
    )
    _persist_incident_ticket(
        ado_id=4242, title="t1-again", description_html="<p>d</p>", url="https://x/4242",
        project_name=None, work_item_type="Issue", parent_ado_id=None,
    )

    with session_scope() as session:
        rows = session.query(Ticket).filter(Ticket.ado_id == 4242).all()
        assert len(rows) == 1


def test_persist_disabled_flag_noop(tmp_path, monkeypatch):
    incident = _create_incident(tmp_path, monkeypatch)
    _patch_run(monkeypatch, OUTPUT_FULL_HTML)
    fake_provider = FakeProvider()
    monkeypatch.setattr("services.tracker_provider.get_tracker_provider", lambda project: fake_provider)

    app = _make_app()
    with _flag(True, persist=False):
        with app.test_client() as client:
            resp = _publish(client, incident["id"])
    assert resp.status_code == 201, resp.get_json()
    tracker_id = resp.get_json()["tracker_id"]

    with session_scope() as session:
        row = session.query(Ticket).filter(Ticket.ado_id == int(tracker_id)).first()
        assert row is None
