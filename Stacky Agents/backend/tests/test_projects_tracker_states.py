from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture(autouse=True)
def _clean_tables():
    from db import init_db, session_scope
    from models import Ticket, TicketStateHistory

    init_db()
    with session_scope() as session:
        session.query(TicketStateHistory).delete()
        session.query(Ticket).delete()
    yield


@pytest.fixture()
def harness(tmp_path, monkeypatch):
    from flask import Flask

    import api.projects as projects_api
    import project_manager
    import services.flow_config_store as flow_store

    projects_dir = tmp_path / "projects"
    active_file = tmp_path / "data" / "active_project.json"
    legacy_flow_file = tmp_path / "data" / "flow_config.json"

    monkeypatch.setattr(project_manager, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(project_manager, "ACTIVE_FILE", active_file)
    monkeypatch.setattr(projects_api, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(flow_store, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(flow_store, "_DEFAULT_CONFIG_FILE", legacy_flow_file)
    monkeypatch.setattr(flow_store, "_CONFIG_FILE", legacy_flow_file)

    app = Flask(__name__)
    app.register_blueprint(projects_api.bp, url_prefix="/api")
    app.config["TESTING"] = True

    with app.test_client() as client:
        yield {
            "client": client,
            "projects_dir": projects_dir,
            "legacy_flow_file": legacy_flow_file,
        }


def test_tracker_states_include_db_history_workflow_and_flow_config(harness):
    from db import session_scope
    from models import Ticket, TicketStateHistory

    client = harness["client"]
    projects_dir = harness["projects_dir"]

    project_dir = projects_dir / "RSPACIFICO"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "config.json").write_text(
        json.dumps(
            {
                "name": "RSPACIFICO",
                "display_name": "RSPACIFICO",
                "issue_tracker": {
                    "type": "azure_devops",
                    "organization": "UbimiaPacifico",
                    "project": "Strategist_Pacifico",
                },
                "agent_workflow_configs": {
                    "TechnicalAnalyst.agent.md": {
                        "allowed_states": ["Technical review"],
                        "transition_state": "To Do",
                        "requires_prior_output": False,
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (project_dir / "flow_config.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "updated_at": "2026-05-21T00:00:00+00:00",
                "rules": [
                    {
                        "id": "rule-1",
                        "ado_state": "Reviewed by Dev",
                        "agent_type": "qa",
                        "created_at": "2026-05-21T00:00:00+00:00",
                        "updated_at": "2026-05-21T00:00:00+00:00",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with session_scope() as session:
        ticket = Ticket(
            ado_id=101,
            external_id=101,
            project="Strategist_Pacifico",
            stacky_project_name="RSPACIFICO",
            tracker_type="azure_devops",
            title="Ticket de prueba",
            ado_state="Doing",
        )
        session.add(ticket)
        session.flush()
        session.add(
            TicketStateHistory(
                ticket_id=ticket.id,
                ado_id=ticket.ado_id,
                stacky_project_name="RSPACIFICO",
                old_state="To Do",
                new_state="Done by AI",
            )
        )

    response = client.get("/api/projects/RSPACIFICO/tracker-states")
    assert response.status_code == 200

    states = response.get_json()["states"]
    assert "Doing" in states
    assert "Done by AI" in states
    assert "Technical review" in states
    assert "To Do" in states
    assert "Reviewed by Dev" in states
    assert "Active" in states


def test_tracker_states_include_ado_process_states(harness, monkeypatch):
    """Estados definidos en el proceso de ADO aparecen aunque no haya tickets."""
    import services.project_context as project_context

    client = harness["client"]
    projects_dir = harness["projects_dir"]

    project_dir = projects_dir / "RSPACIFICO"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "config.json").write_text(
        json.dumps(
            {
                "name": "RSPACIFICO",
                "display_name": "RSPACIFICO",
                "issue_tracker": {
                    "type": "azure_devops",
                    "organization": "UbimiaPacifico",
                    "project": "Strategist_Pacifico",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    class _FakeClient:
        def fetch_states(self):
            return ["New", "Technical Review", "Done"]

    monkeypatch.setattr(
        project_context, "build_ado_client", lambda **kwargs: _FakeClient()
    )

    response = client.get("/api/projects/RSPACIFICO/tracker-states")
    assert response.status_code == 200

    states = response.get_json()["states"]
    assert "Technical Review" in states
    # Orden: los estados del proceso de ADO van primero.
    assert states[:3] == ["New", "Technical Review", "Done"]
