"""Tests para GET /api/tickets/unblocker-board (vista "Desatascador").

UB-01  Epic con pending-task.json pendiente → readiness=task_ready + lista RFs.
UB-02  Ticket con comment.html → readiness=comment_ready.
UB-03  Ticket running sin archivos → readiness=waiting_files + blockers.
UB-04  Ticket idle sin archivos → NO aparece en el board.
UB-05  Plan de pruebas faltante → blocker reportado en el item task_ready.
"""
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


@pytest.fixture(scope="session")
def flask_app():
    from app import create_app
    application = create_app()
    application.config["TESTING"] = True
    try:
        from services.ticket_status import stop_stale_recovery
        stop_stale_recovery()
    except Exception:
        pass
    return application


@pytest.fixture(scope="session", autouse=True)
def init_db(flask_app):
    from db import Base, engine
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client(flask_app):
    with flask_app.test_client() as c:
        yield c


@pytest.fixture
def tmp_repo(monkeypatch, tmp_path):
    import api.tickets as tickets_mod
    monkeypatch.setattr(tickets_mod, "REPO_ROOT", tmp_path)
    return tmp_path


def _seed_ticket(ado_id: int, **kw):
    from db import session_scope
    from models import Ticket
    with session_scope() as session:
        existing = session.query(Ticket).filter(Ticket.ado_id == ado_id).first()
        if existing:
            for k, v in kw.items():
                setattr(existing, k, v)
            return existing.id
        t = Ticket(
            ado_id=ado_id,
            project=kw.pop("project", "TestProject"),
            stacky_project_name=kw.pop("stacky_project_name", None),
            title=kw.pop("title", f"Ticket {ado_id}"),
            work_item_type=kw.pop("work_item_type", "Task"),
            ado_state=kw.pop("ado_state", "Active"),
            **kw,
        )
        session.add(t)
        session.flush()
        return t.id


def _write_pending(repo: Path, epic_id: int, rf_id: str, slug: str, plan: bool = True):
    rf_dir = repo / "Agentes" / "outputs" / f"epic-{epic_id}" / f"{rf_id.lower()}-{slug}"
    rf_dir.mkdir(parents=True, exist_ok=True)
    plan_rel = f"output/tickets/epic-{epic_id}/{rf_id.lower()}-{slug}/plan-de-pruebas.md"
    if plan:
        plan_path = repo / plan_rel
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text("# plan", encoding="utf-8")
    (rf_dir / "pending-task.json").write_text(json.dumps({
        "generated_at": "2026-06-01T00:00:00",
        "generated_by": "FunctionalAnalyst v2.0.1",
        "epic_id": str(epic_id),
        "rf_id": rf_id,
        "title": f"{rf_id} — algo",
        "description_html": "<p>x</p>",
        "plan_de_pruebas_path": plan_rel,
        "parent_link_type": "System.LinkTypes.Hierarchy-Reverse",
        "status": "pending_manual_creation",
    }), encoding="utf-8")


def _write_pending_alt_base(repo: Path, epic_id: int, rf_id: str, slug: str, plan: bool = True):
    """Escribe el pending-task.json en la base ALTERNATIVA output/tickets/epic-{id}/
    (donde el agente funcional a veces lo co-loca con el análisis)."""
    rf_dir = repo / "output" / "tickets" / f"epic-{epic_id}" / f"{rf_id.lower()}-{slug}"
    rf_dir.mkdir(parents=True, exist_ok=True)
    plan_rel = f"output/tickets/epic-{epic_id}/{rf_id.lower()}-{slug}/plan-de-pruebas.md"
    if plan:
        plan_path = repo / plan_rel
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text("# plan", encoding="utf-8")
    (rf_dir / "pending-task.json").write_text(json.dumps({
        "generated_at": "2026-06-01T00:00:00",
        "generated_by": "FunctionalAnalyst v2.0.1",
        "epic_id": str(epic_id),
        "rf_id": rf_id,
        "title": f"{rf_id} — algo",
        "description_html": "<p>x</p>",
        "plan_de_pruebas_path": plan_rel,
        "parent_link_type": "System.LinkTypes.Hierarchy-Reverse",
        "status": "pending_manual_creation",
    }), encoding="utf-8")


def _write_misnamed_pending_with_parent(repo: Path, folder_epic_id: int, real_parent_id: int, rf_id: str):
    rf_dir = repo / "Agentes" / "outputs" / f"epic-{folder_epic_id}" / rf_id.lower()
    rf_dir.mkdir(parents=True, exist_ok=True)
    plan_rel = f"Agentes/outputs/epic-{folder_epic_id}/{rf_id.lower()}/plan-de-pruebas.md"
    plan_path = repo / plan_rel
    plan_path.write_text("# plan", encoding="utf-8")
    (rf_dir / "pending-task.json").write_text(json.dumps({
        "generated_at": "2026-06-05",
        "generated_by": "FunctionalAnalyst legacy",
        "epic_id": str(folder_epic_id),
        "parent_id": real_parent_id,
        "rf_id": rf_id,
        "title": f"{rf_id} — legacy mal nombrado",
        "description_html": "<p>x</p>",
        "plan_de_pruebas_path": plan_rel,
        "parent_link_type": "System.LinkTypes.Hierarchy-Reverse",
        "status": "pending_manual_creation",
    }), encoding="utf-8")


def _write_comment(repo: Path, ado_id: int):
    d = repo / "Agentes" / "outputs" / str(ado_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "comment.html").write_text("<h2>resultado</h2>", encoding="utf-8")


def _get_board(client):
    resp = client.get("/api/tickets/unblocker-board")
    assert resp.status_code == 200
    return resp.get_json()


def _item(board, ado_id):
    return next((it for it in board["items"] if it["ado_id"] == ado_id), None)


def test_ub01_epic_pending_task_ready(client, tmp_repo):
    _seed_ticket(7001, work_item_type="Epic", title="Epic 7001")
    _write_pending(tmp_repo, 7001, "RF-001", "uno", plan=True)

    board = _get_board(client)
    it = _item(board, 7001)
    assert it is not None
    assert it["readiness"] == "task_ready"
    assert it["total_pending"] == 1
    assert it["pending_tasks"][0]["rf_id"] == "RF-001"
    assert it["pending_tasks"][0]["plan_exists"] is True
    assert it["blockers"] == []


def test_ub02_comment_ready(client, tmp_repo):
    _seed_ticket(7002, work_item_type="Task", title="Task 7002")
    _write_comment(tmp_repo, 7002)

    board = _get_board(client)
    it = _item(board, 7002)
    assert it is not None
    assert it["readiness"] == "comment_ready"
    assert it["comment"]["exists"] is True
    assert it["comment"]["size_bytes"] > 0


def test_ub03_running_without_files_waiting(client, tmp_repo):
    _seed_ticket(7003, work_item_type="Task", title="Task 7003", stacky_status="running")

    board = _get_board(client)
    it = _item(board, 7003)
    assert it is not None
    assert it["running"] is True
    assert it["readiness"] == "waiting_files"
    assert len(it["blockers"]) >= 1


def test_ub04_idle_without_files_excluded(client, tmp_repo):
    _seed_ticket(7004, work_item_type="Task", title="Task 7004", stacky_status="idle")

    board = _get_board(client)
    assert _item(board, 7004) is None


def test_ub06_detects_pending_task_in_alt_base(client, tmp_repo):
    """Regresión (ADO 3, 2026-06-01): el agente escribió el pending-task.json en
    output/tickets/epic-{id}/ en vez de Agentes/outputs/epic-{id}/. El board debe
    detectarlo igual (escanea ambas bases) para poder desatascar sin re-ejecutar."""
    _seed_ticket(7006, work_item_type="Epic", title="Epic 7006")
    _write_pending_alt_base(tmp_repo, 7006, "RF-001", "filtro-rfc", plan=True)

    board = _get_board(client)
    it = _item(board, 7006)
    assert it is not None
    assert it["readiness"] == "task_ready"
    assert it["total_pending"] == 1
    pt = it["pending_tasks"][0]
    assert pt["rf_id"] == "RF-001"
    # La ruta devuelta apunta a la base alternativa y create-child-task la resuelve.
    assert pt["pending_task_path"].startswith("output/tickets/epic-7006/")
    assert pt["plan_exists"] is True


def test_ub05_missing_plan_reported_as_blocker(client, tmp_repo):
    _seed_ticket(7005, work_item_type="Epic", title="Epic 7005")
    _write_pending(tmp_repo, 7005, "RF-009", "sinplan", plan=False)

    board = _get_board(client)
    it = _item(board, 7005)
    assert it is not None
    assert it["readiness"] == "task_ready"
    assert it["pending_tasks"][0]["plan_exists"] is False
    assert any("Plan de pruebas no encontrado" in b for b in it["blockers"])


def _write_malformed_pending(repo: Path, epic_id: int, rf_id: str, slug: str):
    """pending-task.json con JSON inválido: comillas dobles sin escapar dentro de
    description_html (replica el bug real de FunctionalAnalyst v2.0.0)."""
    rf_dir = repo / "output" / "tickets" / f"epic-{epic_id}" / f"{rf_id.lower()}-{slug}"
    rf_dir.mkdir(parents=True, exist_ok=True)
    raw = (
        "{\n"
        '  "generated_at": "2026-06-01",\n'
        '  "rf_id": "' + rf_id + '",\n'
        '  "description_html": "<p>campo "RFC" libre</p>",\n'  # ← comillas sin escapar
        '  "status": "pending_manual_creation"\n'
        "}\n"
    )
    (rf_dir / "pending-task.json").write_text(raw, encoding="utf-8")


def test_ub07_malformed_pending_task_surfaced(client, tmp_repo):
    """Regresión (incidente RSSICREA 2026-06-01): el agente escribió un
    pending-task.json con comillas sin escapar → JSON inválido. Antes TODOS los
    consumidores lo descartaban en silencio y el board mostraba 0 ('el desatascador
    no encuentra los archivos'). Ahora debe surfacearlo: readiness=files_error,
    total_errors=1 y un blocker accionable que dice cómo arreglarlo."""
    _seed_ticket(7007, work_item_type="Epic", title="Epic 7007")
    _write_malformed_pending(tmp_repo, 7007, "RF-001", "rfc")

    board = _get_board(client)
    it = _item(board, 7007)
    assert it is not None, "el epic con pending malformado debe aparecer en el board"
    assert it["readiness"] == "files_error"
    assert it["total_pending"] == 0
    assert it["total_errors"] == 1
    assert it["parse_errors"][0]["pending_task_path"].startswith("output/tickets/epic-7007/")
    assert any("MALFORMADO" in b for b in it["blockers"])
    assert board["counts"]["files_error"] >= 1


def test_ub08_detects_misnamed_epic_folder_by_parent_id(client, tmp_repo):
    """Caso ADO-241: archivo bajo epic-26, pero parent_id apunta al Epic real."""
    _seed_ticket(241, work_item_type="Epic", title="EP-26 - Busqueda Cliente", stacky_status="running")
    _write_misnamed_pending_with_parent(tmp_repo, folder_epic_id=26, real_parent_id=241, rf_id="RF-026")

    board = _get_board(client)
    it = _item(board, 241)
    assert it is not None
    assert it["readiness"] == "task_ready"
    assert it["total_pending"] == 1
    assert "epic-26" in it["pending_tasks"][0]["pending_task_path"]
    assert board["scan"]["outputs_dir"].endswith("Agentes\\outputs") or board["scan"]["outputs_dir"].endswith("Agentes/outputs")


def test_rescue_artifact_stages_pending_task(client, tmp_repo):
    _seed_ticket(7101, work_item_type="Epic", title="Epic 7101")
    payload = {
        "generated_at": "2026-06-05",
        "generated_by": "drag-drop",
        "epic_id": "26",
        "parent_id": 7101,
        "rf_id": "RF-7101",
        "title": "RF-7101 — subida manual",
        "description_html": "<p>x</p>",
        "plan_de_pruebas_path": "",
        "parent_link_type": "System.LinkTypes.Hierarchy-Reverse",
        "status": "pending_manual_creation",
    }

    resp = client.post("/api/tickets/by-ado/7101/rescue-artifact", json={
        "repo_root": str(tmp_repo),
        "files": [
            {"name": "pending-task.json", "content": json.dumps(payload)},
            {"name": "plan-de-pruebas.md", "content": "# plan"},
        ],
    })

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["artifact_type"] == "pending_task"
    assert data["pending_task_path"].startswith("Agentes/outputs/epic-7101/")
    staged = tmp_repo / data["pending_task_path"]
    saved = json.loads(staged.read_text(encoding="utf-8"))
    assert saved["epic_id"] == "7101"
    assert saved["rescue_original_epic_id"] == "26"


def test_rescue_artifact_stages_comment_html(client, tmp_repo):
    _seed_ticket(7102, work_item_type="Task", title="Task 7102")

    resp = client.post("/api/tickets/by-ado/7102/rescue-artifact", json={
        "repo_root": str(tmp_repo),
        "artifact_type": "comment",
        "files": [
            {"name": "comment.html", "content": "<h2>ok</h2>"},
            {"name": "comment.meta.json", "content": json.dumps({"source": "drag-drop"})},
        ],
    })

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["artifact_type"] == "comment"
    assert data["html_output_path"] == "Agentes/outputs/7102/comment.html"
    staged = tmp_repo / data["html_output_path"]
    assert staged.read_text(encoding="utf-8") == "<h2>ok</h2>"
    meta = json.loads((staged.parent / "comment.meta.json").read_text(encoding="utf-8"))
    assert meta["source"] == "drag-drop"


# ---------------------------------------------------------------------------
# Stale consumed (caso ADO-241, 2026-06-11): pending-task consumido cuya Task
# fue borrada en ADO. Antes era invisible (el board saltea consumed) y el flujo
# automatico respondia idempotente sin crear nada.
# ---------------------------------------------------------------------------

def _write_consumed(
    repo: Path, epic_id: int, rf_id: str, slug: str,
    task_ado_id: int, consumed_at: str = "2020-01-01T00:00:00+00:00",
):
    rf_dir = repo / "Agentes" / "outputs" / f"epic-{epic_id}" / f"{rf_id.lower()}-{slug}"
    rf_dir.mkdir(parents=True, exist_ok=True)
    (rf_dir / "pending-task.json").write_text(json.dumps({
        "generated_at": "2026-06-01T00:00:00",
        "generated_by": "FunctionalAnalyst v2.0.3",
        "epic_id": str(epic_id),
        "rf_id": rf_id,
        "title": f"{rf_id} — algo",
        "description_html": "<p>x</p>",
        "plan_de_pruebas_path": "",
        "parent_link_type": "System.LinkTypes.Hierarchy-Reverse",
        "status": "consumed",
        "consumed_at": consumed_at,
        "task_ado_id": task_ado_id,
        "attachment_id": f"attach-{task_ado_id}",
    }), encoding="utf-8")


def test_ub09_stale_consumed_surfaced(client, tmp_repo):
    """Consumed apuntando a Task inexistente en la sync -> stale_consumed accionable."""
    _seed_ticket(8101, work_item_type="Epic", title="Epic 8101")
    _write_consumed(tmp_repo, 8101, "RF-026", "filtros", task_ado_id=8888)

    board = _get_board(client)
    it = _item(board, 8101)
    assert it is not None, "el epic con consumed stale debe aparecer en el board"
    assert it["readiness"] == "stale_consumed"
    assert it["total_stale_consumed"] == 1
    stale = it["stale_consumed"][0]
    assert stale["rf_id"] == "RF-026"
    assert stale["task_ado_id"] == 8888
    assert any("borrada" in b for b in it["blockers"])
    assert board["counts"]["stale_consumed"] >= 1


def test_ub10_consumed_with_live_task_not_stale(client, tmp_repo):
    """Si la Task del consumed existe en la sync local, NO es stale (caso sano)."""
    _seed_ticket(8102, work_item_type="Epic", title="Epic 8102")
    _seed_ticket(8103, work_item_type="Task", title="RF-027 task viva", parent_ado_id=8102)
    _write_consumed(tmp_repo, 8102, "RF-027", "sano", task_ado_id=8103)

    board = _get_board(client)
    assert _item(board, 8102) is None, "consumed con Task viva no genera item accionable"


def test_ub11_recent_consume_not_flagged_before_next_sync(client, tmp_repo):
    """Consumed posterior a la ultima sync -> NO flag (la sync aun no vio la Task).

    consumed_at en el futuro garantiza consumed_at >= max(last_synced_at) sin
    depender de cuando corre la suite (el demo seed setea last_synced_at=now).
    """
    from datetime import datetime
    _seed_ticket(
        8104, work_item_type="Epic", title="Epic 8104",
        last_synced_at=datetime(2026, 6, 11, 12, 0, 0),
    )
    _write_consumed(
        tmp_repo, 8104, "RF-028", "recien",
        task_ado_id=9999, consumed_at="2030-01-01T00:00:00+00:00",
    )

    board = _get_board(client)
    assert _item(board, 8104) is None, "consume reciente no debe alarmar antes de la proxima sync"


def test_ub12_stale_dedup_por_rf_y_prioridad_pending(client, tmp_repo):
    """Dedupe por RF (gana el consumed mas reciente) y un pending del mismo RF lo tapa."""
    # Epic con pending + stale del mismo RF -> task_ready, sin stale.
    _seed_ticket(8105, work_item_type="Epic", title="Epic 8105")
    _write_pending(tmp_repo, 8105, "RF-030", "fresco", plan=True)
    _write_consumed(tmp_repo, 8105, "RF-030", "viejo", task_ado_id=8881)

    # Epic con dos stale del mismo RF -> un solo item con el mas reciente.
    _seed_ticket(8106, work_item_type="Epic", title="Epic 8106")
    _write_consumed(
        tmp_repo, 8106, "RF-031", "mas-viejo",
        task_ado_id=8882, consumed_at="2020-01-01T00:00:00+00:00",
    )
    _write_consumed(
        tmp_repo, 8106, "RF-031", "mas-nuevo",
        task_ado_id=8883, consumed_at="2021-01-01T00:00:00+00:00",
    )

    board = _get_board(client)

    it_5 = _item(board, 8105)
    assert it_5 is not None
    assert it_5["readiness"] == "task_ready"
    assert it_5["total_stale_consumed"] == 0

    it_6 = _item(board, 8106)
    assert it_6 is not None
    assert it_6["readiness"] == "stale_consumed"
    assert it_6["total_stale_consumed"] == 1
    assert it_6["stale_consumed"][0]["task_ado_id"] == 8883
    assert "mas-nuevo" in it_6["stale_consumed"][0]["pending_task_path"]
