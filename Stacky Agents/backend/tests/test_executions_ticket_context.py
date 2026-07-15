"""Plan 134 F1 — project/ticket_title en la serialización de AgentExecution.

Patrón de blueprint aislado: tests/test_plan117_insights_api.py:16-79
(DATABASE_URL=sqlite:///:memory: antes de importar, _stub_api_pkg() + carga
de api/executions.py vía importlib, blueprint montado en /api/executions).
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from sqlalchemy import delete

import db
from models import AgentExecution, Ticket

db.init_db()


def _stub_api_pkg():
    if "api" not in sys.modules or not hasattr(sys.modules.get("api"), "__path__"):
        pkg = types.ModuleType("api")
        pkg.__path__ = [str(_BACKEND / "api")]
        sys.modules["api"] = pkg
    helpers = types.ModuleType("api._helpers")
    helpers.current_user = lambda: "op"
    sys.modules["api._helpers"] = helpers


def _load(modname, relpath):
    spec = importlib.util.spec_from_file_location(modname, str(_BACKEND / relpath))
    m = importlib.util.module_from_spec(spec)
    sys.modules[modname] = m
    spec.loader.exec_module(m)
    return m


def _exec_client():
    from flask import Flask
    _stub_api_pkg()
    m = _load("api.executions", "api/executions.py")
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(m.bp, url_prefix="/api/executions")
    return app.test_client()


def test_list_incluye_project_y_ticket_title():
    with db.session_scope() as s:
        s.add(Ticket(id=1001, ado_id=999001, project="P", stacky_project_name="proj-x", title="Mi ticket"))
        s.add(AgentExecution(
            ticket_id=1001, status="running", agent_type="developer",
            input_context_json="[]", started_by="t",
        ))
    client = _exec_client()
    resp = client.get("/api/executions?all_projects=true&status=running")
    assert resp.status_code == 200
    rows = resp.get_json()
    row = next(r for r in rows if r["ticket_id"] == 1001)
    assert row["project"] == "proj-x"
    assert row["ticket_title"] == "Mi ticket"


def test_ticket_title_truncado_a_120():
    with db.session_scope() as s:
        s.add(Ticket(id=1002, ado_id=999002, project="P", stacky_project_name="proj-y", title="x" * 200))
        s.add(AgentExecution(
            ticket_id=1002, status="running", agent_type="developer",
            input_context_json="[]", started_by="t",
        ))
    client = _exec_client()
    resp = client.get("/api/executions?all_projects=true&status=running")
    rows = resp.get_json()
    row = next(r for r in rows if r["ticket_id"] == 1002)
    assert len(row["ticket_title"]) == 120


def test_to_dict_default_sin_ticket_context():
    with db.session_scope() as s:
        s.add(Ticket(id=1003, ado_id=999003, project="P", stacky_project_name="proj-z", title="t3"))
        s.add(AgentExecution(
            ticket_id=1003, status="completed", agent_type="developer",
            input_context_json="[]", started_by="t",
        ))
    with db.session_scope() as s:
        row = s.query(AgentExecution).filter_by(ticket_id=1003).one()
        d = row.to_dict()
        assert "project" not in d
        assert "ticket_title" not in d


def test_exec_con_ticket_borrado_no_rompe():
    with db.session_scope() as s:
        s.add(Ticket(id=1004, ado_id=999004, project="P", stacky_project_name="proj-w", title="t4"))
        s.add(AgentExecution(
            ticket_id=1004, status="running", agent_type="developer",
            input_context_json="[]", started_by="t",
        ))
    # DELETE en una sesion NUEVA que solo toca Ticket (nunca carga la relacion
    # .executions): evita que el unit-of-work del ORM intente poner ticket_id=NULL
    # en el AgentExecution dependiente (violaria nullable=False). Deja un FK
    # colgante real, igual que "sqlite en memoria no fuerza FKs por default".
    with db.session_scope() as s:
        s.execute(delete(Ticket).where(Ticket.id == 1004))
    client = _exec_client()
    resp = client.get("/api/executions?all_projects=true&status=running")
    assert resp.status_code == 200
    rows = resp.get_json()
    row = next(r for r in rows if r["ticket_id"] == 1004)
    assert row["project"] is None
    assert row["ticket_title"] is None


def test_get_execution_incluye_ticket_context():
    with db.session_scope() as s:
        s.add(Ticket(id=1005, ado_id=999005, project="P", stacky_project_name="proj-v", title="t5"))
        s.add(AgentExecution(
            ticket_id=1005, status="running", agent_type="developer",
            input_context_json="[]", started_by="t",
        ))
        s.flush()
        exec_id = s.query(AgentExecution).filter_by(ticket_id=1005).one().id
    client = _exec_client()
    resp = client.get(f"/api/executions/{exec_id}")
    assert resp.status_code == 200
    row = resp.get_json()
    assert "project" in row
    assert "ticket_title" in row
