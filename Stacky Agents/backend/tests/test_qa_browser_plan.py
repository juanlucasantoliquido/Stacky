from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture
def qa_browser_client():
    from flask import Flask

    from api import api_bp
    from db import init_db

    init_db()
    app = Flask(__name__)
    app.config.update(TESTING=True)
    app.register_blueprint(api_bp)
    with app.test_client() as client:
        yield client


def test_browser_spec_uses_description_comments_and_attachments():
    from services.qa_browser_plan import BrowserRunInput, build_guarded_browser_spec

    context = {
        "stats": {"comments_count": 1, "attachments_count": 1, "attachments_text_inlined": 1},
        "plan_candidates": [
            {
                "kind": "ticket_description",
                "title": "Descripcion del ticket",
                "source_id": "ticket.description",
                "confidence": 0.58,
                "reason": "descripcion con potencial plan de pruebas",
                "text": (
                    "P03: Validar criterio de aceptacion desde descripcion\n"
                    "- Abrir la agenda\n"
                    "- Verificar que se muestre el mensaje de validacion\n"
                    "Resultado esperado: el mensaje de validacion queda visible."
                ),
            },
            {
                "kind": "ado_comment",
                "title": "Comentario ADO - Analista funcional",
                "source_id": "comment:7",
                "confidence": 0.82,
                "reason": "comentario contiene senales de plan de pruebas",
                "text": (
                    "P01: Validar busqueda de agenda\n"
                    "- Ingresar a AgendaWeb\n"
                    "- Buscar paciente Juan\n"
                    "Resultado esperado: debe mostrar el turno activo."
                ),
            },
            {
                "kind": "ado_attachment",
                "title": "Adjunto ADO - Plan_UAT.md",
                "source_id": "attachment:Plan_UAT.md",
                "confidence": 0.92,
                "reason": "adjunto priorizado por nombre/contenido de pruebas",
                "text": (
                    "TC01: Verificar filtro por profesional\n"
                    "- Abrir el filtro de profesionales\n"
                    "- Seleccionar Dra Gomez\n"
                    "Resultado esperado: solo se ven turnos de Dra Gomez."
                ),
            },
        ],
    }

    spec = build_guarded_browser_spec(
        BrowserRunInput(
            ticket_id=12,
            ticket_ado_id=122,
            ticket_title="Validar agenda",
            ticket_state="Active",
            ticket_url="https://dev.azure.com/org/project/_workitems/edit/122",
            allowed_base_url="http://localhost:35017/AgendaWeb/",
            context=context,
            max_scenarios=6,
        )
    )

    titles = [scenario["title"] for scenario in spec["scenarios"]]
    source_kinds = {source["kind"] for source in spec["plan_source"]["used_sources"]}

    assert len(spec["scenarios"]) == 3
    assert any("busqueda de agenda" in title.lower() for title in titles)
    assert any("filtro por profesional" in title.lower() for title in titles)
    assert any("descripcion" in title.lower() for title in titles)
    assert source_kinds == {"ticket_description", "ado_comment", "ado_attachment"}
    assert spec["guardrails"]["browser"] == "codex_browser"
    assert spec["guardrails"]["ado_comment_policy"] == "browser_runner_never_publishes"
    assert spec["runner_contract"]["must_publish_ado_comment"] is False
    assert spec["runner_contract"]["must_leave_stacky_artifacts"] is True
    assert "/api/qa-browser/runs/{execution_id}/complete" in spec["codex_browser_prompt"]
    assert "No publiques en ADO ni llames APIs de ADO" in spec["codex_browser_prompt"]
    assert "publique el comentario en ADO" not in spec["codex_browser_prompt"]


def test_ado_comment_contains_marker_sources_and_result_detail():
    from services.qa_browser_plan import BrowserRunInput, build_ado_comment_html, build_guarded_browser_spec

    spec = build_guarded_browser_spec(
        BrowserRunInput(
            ticket_id=12,
            ticket_ado_id=122,
            ticket_title="Validar agenda",
            ticket_state="Active",
            ticket_url=None,
            allowed_base_url="http://localhost:35017/AgendaWeb/",
            context={
                "plan_candidates": [
                    {
                        "kind": "ado_comment",
                        "title": "Comentario ADO - QA",
                        "source_id": "comment:9",
                        "confidence": 0.9,
                        "reason": "plan",
                        "text": "P01: Validar login\nResultado esperado: ingresa a AgendaWeb.",
                    }
                ]
            },
        )
    )

    html = build_ado_comment_html(
        execution_id=99,
        spec=spec,
        result={
            "verdict": "PASS",
            "summary": "Se ejecuto el plan funcional.",
            "scenarios": [
                {
                    "scenario_id": "QA-UAT-001",
                    "verdict": "PASS",
                    "expected": "ingresa a AgendaWeb",
                    "actual": "ingreso correcto",
                    "evidence": ["captura inicial", "captura final"],
                }
            ],
        },
    )

    assert "stacky-qa-browser-uat:run" in html
    assert "Run Stacky:</strong> #99" in html
    assert "Comentario ADO - QA" in html
    assert "QA-UAT-001" in html
    assert "captura final" in html
    assert "handoff local a Stacky Agents" in html
    assert "publicado por Stacky Agents" not in html


def test_complete_endpoint_delegates_ado_publish_to_stacky(qa_browser_client, monkeypatch, tmp_path):
    from db import session_scope
    from models import AgentExecution, Ticket
    from services.qa_browser_plan import BrowserRunInput, build_guarded_browser_spec

    ado_id = 980000 + int(time.time_ns() % 10_000)
    spec = build_guarded_browser_spec(
        BrowserRunInput(
            ticket_id=1,
            ticket_ado_id=ado_id,
            ticket_title="Validar cierre con comentario",
            ticket_state="Active",
            ticket_url=None,
            allowed_base_url="http://localhost:35017/AgendaWeb/",
            context={
                "plan_candidates": [
                    {
                        "kind": "ado_attachment",
                        "title": "Adjunto ADO - Plan_UAT.md",
                        "source_id": "attachment:Plan_UAT.md",
                        "confidence": 0.95,
                        "reason": "plan",
                        "text": "P01: Validar agenda\nResultado esperado: agenda visible.",
                    }
                ]
            },
        )
    )

    with session_scope() as session:
        ticket = Ticket(
            ado_id=ado_id,
            project="TEST",
            title="Validar cierre con comentario",
            ado_state="Active",
            stacky_status="running",
        )
        session.add(ticket)
        session.flush()
        ticket_id = ticket.id
        spec["ticket"]["id"] = ticket.id
        execution = AgentExecution(
            ticket_id=ticket.id,
            agent_type="qa-browser",
            status="running",
            started_by="pytest",
        )
        execution.input_context = []
        execution.metadata_dict = {"spec": spec, "events": [], "evidence": []}
        session.add(execution)
        session.flush()
        execution_id = execution.id

    calls: list[dict] = []

    class FakeAdoClient:
        def post_comment(self, received_ado_id, text, fmt="html"):
            calls.append({"ado_id": received_ado_id, "text": text, "fmt": fmt})
            return {"id": 1234, "text": "ok"}

    monkeypatch.setenv("STACKY_REPO_ROOT", str(tmp_path))
    monkeypatch.setattr("services.ado_client.AdoClient", FakeAdoClient)
    monkeypatch.setattr("api.qa_browser.ticket_status.on_execution_end", lambda **kwargs: None)

    response = qa_browser_client.post(
        f"/api/qa-browser/runs/{execution_id}/complete",
        json={
            "verdict": "PASS",
            "summary": "Plan ejecutado desde Codex Browser.",
            "scenarios": [
                {
                    "scenario_id": "QA-UAT-001",
                    "verdict": "PASS",
                    "expected": "agenda visible",
                    "actual": "agenda visible",
                    "evidence": ["screenshot final"],
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.get_json()["ado_comment"]["ok"] is True
    assert response.get_json()["ado_comment"]["html_output_path"] == f"Agentes/outputs/{ado_id}/comment.html"
    assert calls
    assert calls[0]["ado_id"] == ado_id
    assert calls[0]["fmt"] == "html"
    assert "stacky-qa-browser-uat:run" in calls[0]["text"]
    assert "screenshot final" in calls[0]["text"]
    assert (tmp_path / "Agentes" / "outputs" / str(ado_id) / "comment.html").is_file()

    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        assert row.status == "completed"
        assert row.metadata_dict["ado_comment"]["attempted"] is True
        assert row.metadata_dict["ado_comment"]["delegated_to_stacky"] is True


def test_create_run_auto_starts_codex_runner_and_marks_ticket_running(qa_browser_client, monkeypatch):
    from db import session_scope
    from models import AgentExecution, Ticket

    class FakeAdoClient:
        def fetch_comments(self, ado_id, top=50):
            return [
                {
                    "id": 1,
                    "author": "Funcional",
                    "date": "2026-05-12",
                    "text": "<p>P01: Validar agenda<br>Resultado esperado: agenda visible.</p>",
                }
            ]

        def fetch_attachments(self, ado_id, max_text_bytes=131_072):
            return [
                {
                    "name": "Plan_UAT.md",
                    "url": "https://example.test/plan",
                    "size": 128,
                    "text_content": "TC01: Buscar turno\nResultado esperado: se muestra el turno.",
                }
            ]

    monkeypatch.setattr("services.ado_client.AdoClient", FakeAdoClient)
    from services import ticket_status as ticket_status_service

    starts: list[dict] = []

    def fake_execution_start(**kwargs):
        starts.append(kwargs)
        ticket_status_service.set_status(
            kwargs["ticket_id"],
            "running",
            changed_by=kwargs["user"],
            execution_id=kwargs["execution_id"],
            agent_type=kwargs["agent_type"],
        )

    monkeypatch.setattr("api.qa_browser.ticket_status.on_execution_start", fake_execution_start)
    runner_starts: list[dict] = []
    monkeypatch.setattr("api.qa_browser.qa_browser_runner.start_run", lambda **kwargs: runner_starts.append(kwargs))

    with session_scope() as session:
        ticket = Ticket(
            ado_id=991122,
            project="TEST",
            title="Validar agenda",
            description="P02: Abrir agenda\nResultado esperado: carga la pantalla.",
            ado_state="Active",
            stacky_status="idle",
        )
        session.add(ticket)
        session.flush()
        ticket_id = ticket.id

    response = qa_browser_client.post(
        "/api/qa-browser/runs",
        json={"ticket_id": ticket_id, "allowed_base_url": "http://localhost:35017/AgendaWeb/"},
    )

    body = response.get_json()
    assert response.status_code == 202
    assert body["status"] == "running"
    assert body["runner_prompt"].count(f"/api/qa-browser/runs/{body['execution_id']}/complete") == 1
    assert len(starts) == 1
    assert starts[0]["ticket_id"] == ticket_id
    assert starts[0]["execution_id"] == body["execution_id"]
    assert len(runner_starts) == 1
    assert runner_starts[0]["execution_id"] == body["execution_id"]
    assert str(body["execution_id"]) in runner_starts[0]["prompt"]

    with session_scope() as session:
        ticket = session.get(Ticket, ticket_id)
        execution = session.get(AgentExecution, body["execution_id"])
        assert ticket.stacky_status == "running"
        assert execution.status == "running"
        assert execution.metadata_dict["runner"]["auto_start"] is True


def test_create_run_manual_mode_keeps_prepared_run_queued(qa_browser_client, monkeypatch):
    from db import session_scope
    from models import AgentExecution, Ticket

    class FakeAdoClient:
        def fetch_comments(self, ado_id, top=50):
            return [
                {
                    "id": 1,
                    "author": "Funcional",
                    "date": "2026-05-12",
                    "text": "<p>P01: Validar agenda<br>Resultado esperado: agenda visible.</p>",
                }
            ]

        def fetch_attachments(self, ado_id, max_text_bytes=131_072):
            return []

    monkeypatch.setattr("services.ado_client.AdoClient", FakeAdoClient)
    starts: list[dict] = []
    runner_starts: list[dict] = []
    monkeypatch.setattr("api.qa_browser.ticket_status.on_execution_start", lambda **kwargs: starts.append(kwargs))
    monkeypatch.setattr("api.qa_browser.qa_browser_runner.start_run", lambda **kwargs: runner_starts.append(kwargs))

    with session_scope() as session:
        ticket = Ticket(
            ado_id=991124,
            project="TEST",
            title="Validar agenda manual",
            description="P01: Abrir agenda\nResultado esperado: carga la pantalla.",
            ado_state="Active",
            stacky_status="idle",
        )
        session.add(ticket)
        session.flush()
        ticket_id = ticket.id

    response = qa_browser_client.post(
        "/api/qa-browser/runs",
        json={
            "ticket_id": ticket_id,
            "allowed_base_url": "http://localhost:35017/AgendaWeb/",
            "auto_start": False,
        },
    )

    body = response.get_json()
    assert response.status_code == 202
    assert body["status"] == "queued"
    assert starts == []
    assert runner_starts == []

    with session_scope() as session:
        ticket = session.get(Ticket, ticket_id)
        execution = session.get(AgentExecution, body["execution_id"])
        assert ticket.stacky_status == "idle"
        assert execution.status == "queued"
        assert execution.metadata_dict["runner"]["auto_start"] is False


def test_first_browser_event_activates_prepared_run(qa_browser_client, monkeypatch):
    from db import session_scope
    from models import AgentExecution, Ticket
    from services.qa_browser_plan import BrowserRunInput, build_guarded_browser_spec

    starts: list[dict] = []
    monkeypatch.setattr("api.qa_browser.ticket_status.on_execution_start", lambda **kwargs: starts.append(kwargs))

    spec = build_guarded_browser_spec(
        BrowserRunInput(
            ticket_id=1,
            ticket_ado_id=991123,
            ticket_title="Validar agenda",
            ticket_state="Active",
            ticket_url=None,
            allowed_base_url="http://localhost:35017/AgendaWeb/",
            context={
                "plan_candidates": [
                    {
                        "kind": "ado_comment",
                        "title": "Comentario ADO - QA",
                        "source_id": "comment:1",
                        "confidence": 0.9,
                        "reason": "plan",
                        "text": "P01: Validar agenda\nResultado esperado: agenda visible.",
                    }
                ]
            },
        )
    )

    with session_scope() as session:
        ticket = Ticket(
            ado_id=991123,
            project="TEST",
            title="Validar agenda",
            ado_state="Active",
            stacky_status="idle",
        )
        session.add(ticket)
        session.flush()
        ticket_id = ticket.id
        spec["ticket"]["id"] = ticket.id
        execution = AgentExecution(
            ticket_id=ticket.id,
            agent_type="qa-browser",
            status="queued",
            started_by="pytest",
        )
        execution.input_context = []
        execution.metadata_dict = {"spec": spec, "events": [], "evidence": []}
        session.add(execution)
        session.flush()
        execution_id = execution.id

    response = qa_browser_client.post(
        f"/api/qa-browser/runs/{execution_id}/events",
        json={"type": "browser.started", "message": "Browser visible iniciado"},
        headers={"X-User-Email": "qa@local"},
    )

    assert response.status_code == 200
    assert len(starts) == 1
    assert starts[0] == {
        "ticket_id": ticket_id,
        "execution_id": execution_id,
        "agent_type": "qa-browser",
        "user": "qa@local",
    }
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        assert row.status == "running"
        assert row.metadata_dict["events"][0]["type"] == "browser.started"
