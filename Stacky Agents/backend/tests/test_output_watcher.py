"""Tests del output_watcher — cierre automático de runs VSCode huérfanos.

Cubre los casos del plan STACKY_OUTPUT_WATCHER_PLAN.md sección 9:
  - Modo B: happy path, dedupe SHA, stable_delay, no_running, mtime viejo, retry
  - Modo A: debounce, no crea tasks, idempotente, sin pending tasks
  - Robustez: nombres de dir malformados, race con PATCH endpoint
  - Endpoints: POST /api/diag/output-watcher/scan-now + GET stats
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def repo_root_dir(tmp_path, monkeypatch):
    """Aísla Agentes/outputs en tmp y patchea STACKY_REPO_ROOT."""
    monkeypatch.setenv("STACKY_REPO_ROOT", str(tmp_path))
    outputs = tmp_path / "Agentes" / "outputs"
    outputs.mkdir(parents=True)
    return tmp_path


@pytest.fixture
def client(monkeypatch, repo_root_dir):
    """App test client con daemons deshabilitados."""
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")
    monkeypatch.setenv("STACKY_OUTPUT_WATCHER_ENABLED", "false")
    # Atajo: stable_delay_b muy bajo para tests rápidos
    monkeypatch.setenv("STACKY_OUTPUT_WATCHER_STABLE_DELAY_B", "0.01")
    monkeypatch.setenv("STACKY_OUTPUT_WATCHER_STABLE_DELAY_A", "0.01")
    # Mockear publish_from_execution para no llamar a ADO real.
    # AgentHtmlPublish es modelo SQLAlchemy real (restaurado en c93ffbb) y
    # debe quedar disponible — solo intercept la función que pega a ADO.
    from services import ado_publisher as _ado_pub

    class _PR:
        def __init__(self):
            self.ok = True
            self.status = "ok"
            self.html_sha256 = "deadbeef"
            self.ado_id = None
            self.execution_id = None
            self.reason = None
            self.ado_response = {"stubbed": True}
            self.record_id = 1

    def _fake_publish(execution_id, triggered_by="test"):
        return _PR()

    monkeypatch.setattr(_ado_pub, "publish_from_execution", _fake_publish)

    from app import create_app
    from services.ticket_status import stop_stale_recovery
    from services.manifest_watcher import stop_manifest_watcher
    from services.output_watcher import stop_output_watcher

    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    stop_output_watcher()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()
    stop_manifest_watcher()
    stop_output_watcher()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _mk_ticket(ado_id: int, stacky_status: str = "running", work_item_type: str | None = None) -> int:
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=ado_id,
            project="RSPacifico",
            title=f"t-{ado_id}",
            ado_state="To Do",
            stacky_status=stacky_status,
            work_item_type=work_item_type,
        )
        session.add(t)
        session.flush()
        return t.id


def _mk_execution(ticket_id: int, *, status: str = "running", started_minutes_ago: float = 5.0,
                  agent_type: str = "functional") -> int:
    from db import session_scope
    from models import AgentExecution

    started = datetime.utcnow() - timedelta(minutes=started_minutes_ago)
    completed = datetime.utcnow() if status in {"completed", "error"} else None
    with session_scope() as session:
        e = AgentExecution(
            ticket_id=ticket_id,
            agent_type=agent_type,
            status=status,
            input_context_json="[]",
            started_by="test",
            started_at=started,
            completed_at=completed,
        )
        session.add(e)
        session.flush()
        return e.id


def _write_comment_html(repo_root: Path, ado_id: int, content: str = "<p>análisis</p>"):
    """Crea outputs/{ado_id}/comment.html con un mtime antiguo (pasó debounce)."""
    d = repo_root / "Agentes" / "outputs" / str(ado_id)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "comment.html"
    p.write_text(content, encoding="utf-8")
    # Forzar mtime al pasado para que el debounce no lo bloquee
    past = time.time() - 60
    os.utime(p, (past, past))
    return p


def _write_pending_task(repo_root: Path, epic_ado_id: int, rf_id: str, *, mtime_offset: float = -60.0):
    """Crea outputs/epic-{id}/{rf}/pending-task.json. Por defecto mtime es 60s atrás."""
    import json as _json
    d = repo_root / "Agentes" / "outputs" / f"epic-{epic_ado_id}" / rf_id
    d.mkdir(parents=True, exist_ok=True)
    p = d / "pending-task.json"
    p.write_text(_json.dumps({
        "rf_id": rf_id, "title": "test", "status": "pending_manual_creation",
        "generated_at": "2026-05-16T00:00:00Z",
    }), encoding="utf-8")
    past = time.time() + mtime_offset
    os.utime(p, (past, past))
    return p


def _write_done_marker(repo_root: Path, epic_ado_id: int, *, status: str = "completed", rf_id: str | None = None):
    """Crea el done-marker .stacky-done.json a nivel epic (o por RF si rf_id)."""
    import json as _json
    base = repo_root / "Agentes" / "outputs" / f"epic-{epic_ado_id}"
    if rf_id:
        base = base / rf_id
    base.mkdir(parents=True, exist_ok=True)
    p = base / ".stacky-done.json"
    p.write_text(_json.dumps({
        "status": status, "rf_id": rf_id or "ALL",
        "finished_at": "2026-05-27T01:00:00Z",
    }), encoding="utf-8")
    return p


def _write_pending_task_alt(repo_root: Path, epic_ado_id: int, rf_id: str, *, mtime_offset: float = -60.0):
    """Crea el pending-task.json en la base ALTERNATIVA `output/tickets/epic-{id}/{rf}/`.

    Es donde el agente funcional co-loca el pending junto al análisis/plan cuando
    NO usa la canónica `Agentes/outputs/epic-{id}/`.
    """
    import json as _json
    d = repo_root / "output" / "tickets" / f"epic-{epic_ado_id}" / rf_id
    d.mkdir(parents=True, exist_ok=True)
    p = d / "pending-task.json"
    p.write_text(_json.dumps({
        "rf_id": rf_id, "title": "test-alt", "status": "pending_manual_creation",
        "generated_at": "2026-06-01T00:00:00Z",
    }), encoding="utf-8")
    past = time.time() + mtime_offset
    os.utime(p, (past, past))
    return p


# ── Modo B ───────────────────────────────────────────────────────────────────


def test_mode_b_closes_running_execution_on_comment_html(client, repo_root_dir):
    from services.output_watcher import AdoOutputWatcher
    from db import session_scope
    from models import AgentExecution

    ticket_id = _mk_ticket(40101)
    exec_id = _mk_execution(ticket_id)
    _write_comment_html(repo_root_dir, 40101, "<p>resultado</p>")

    w = AdoOutputWatcher(stable_delay_b=0.0)
    result = w.scan_once()
    assert result["mode_b_closes"] == 1
    assert result["mode_b_skipped"] == 0

    with session_scope() as session:
        e = session.get(AgentExecution, exec_id)
        assert e.status == "completed"
        assert e.completed_at is not None


def test_mode_b_publishes_even_when_execution_already_terminal(client, repo_root_dir):
    """Si la execution ya está terminal y aparece comment.html, igual publica
    (cubre race Modo A → Modo B). El status no se re-abre."""
    from services.output_watcher import AdoOutputWatcher
    from db import session_scope
    from models import AgentExecution

    ticket_id = _mk_ticket(40102, stacky_status="completed")
    exec_id = _mk_execution(ticket_id, status="completed")  # ya cerrada
    _write_comment_html(repo_root_dir, 40102)

    w = AdoOutputWatcher(stable_delay_b=0.0)
    result = w.scan_once()
    # mode_b_closes ahora incluye publish-late (no solo transiciones)
    assert result["mode_b_closes"] == 1

    with session_scope() as session:
        e = session.get(AgentExecution, exec_id)
        assert e.status == "completed"  # NO se re-abre


def test_mode_b_respects_stable_delay(client, repo_root_dir):
    """Archivo recién escrito (mtime ~ahora) NO debe disparar hasta que estabilice."""
    from services.output_watcher import AdoOutputWatcher

    ticket_id = _mk_ticket(40103)
    _mk_execution(ticket_id)
    # Crear comment.html con mtime ACTUAL (no pasado)
    d = repo_root_dir / "Agentes" / "outputs" / "40103"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "comment.html"
    p.write_text("<p>fresh</p>", encoding="utf-8")
    # mtime = ahora → debe estar dentro del debounce de 1.0s

    w = AdoOutputWatcher(stable_delay_b=1.0)
    result1 = w.scan_once()
    assert result1["mode_b_closes"] == 0
    assert result1["mode_b_skipped"] == 0  # no procesa, ni siquiera lo marca skip

    # Esperar el debounce y reintentar
    time.sleep(1.1)
    result2 = w.scan_once()
    assert result2["mode_b_closes"] == 1


def test_mode_b_skips_when_mtime_older_than_execution_start(client, repo_root_dir):
    """comment.html viejo + execution nueva → no se considera output de esta corrida."""
    from services.output_watcher import AdoOutputWatcher

    ticket_id = _mk_ticket(40104)
    # Execution arrancó hace 1 min
    exec_id = _mk_execution(ticket_id, started_minutes_ago=1)
    # comment.html con mtime hace 10 min (más viejo que started_at)
    d = repo_root_dir / "Agentes" / "outputs" / "40104"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "comment.html"
    p.write_text("<p>old</p>", encoding="utf-8")
    old = time.time() - 600
    os.utime(p, (old, old))

    w = AdoOutputWatcher(stable_delay_b=0.0)
    result = w.scan_once()
    assert result["mode_b_closes"] == 0
    assert result["mode_b_skipped"] == 1


def test_mode_b_dedup_by_sha_does_not_double_close(client, repo_root_dir):
    """Segundo scan_once con mismo contenido no debe re-disparar."""
    from services.output_watcher import AdoOutputWatcher

    ticket_id = _mk_ticket(40105)
    _mk_execution(ticket_id)
    _write_comment_html(repo_root_dir, 40105, "<p>once</p>")

    w = AdoOutputWatcher(stable_delay_b=0.0)
    r1 = w.scan_once()
    assert r1["mode_b_closes"] == 1
    # Segundo scan — execution ya está completed
    r2 = w.scan_once()
    assert r2["mode_b_closes"] == 0
    assert r2["mode_b_skipped"] == 0  # cache mtime detecta sin re-stat


def test_mode_b_publishes_late_when_execution_already_terminal(client, repo_root_dir):
    """Race Modo A → Modo B: si la execution ya se cerró (p.ej. por Modo A),
    Modo B aún debe publicar el comment.html cuando aparezca."""
    from services.output_watcher import AdoOutputWatcher
    from db import session_scope
    from models import AgentExecution

    ticket_id = _mk_ticket(40107)
    exec_id = _mk_execution(ticket_id, status="completed")  # ya cerrada
    _write_comment_html(repo_root_dir, 40107, "<p>late publish</p>")

    w = AdoOutputWatcher(stable_delay_b=0.0)
    result = w.scan_once()
    # mode_b_closes cuenta el publish-only también (no es solo transiciones)
    assert result["mode_b_closes"] == 1

    # Verificar que se llamó publish (el fake_publish del fixture devuelve ok=True)
    # — no podemos checkear DB directo porque el stub no escribe agent_html_publish.
    # En su lugar, verificamos que la execution sigue completed (no se re-abrió).
    with session_scope() as session:
        e = session.get(AgentExecution, exec_id)
        assert e.status == "completed"


def test_mode_b_skips_when_no_execution_at_all(client, repo_root_dir):
    """comment.html en disco para un ticket sin ninguna execution → skip."""
    from services.output_watcher import AdoOutputWatcher

    _mk_ticket(40108)  # ticket pero sin execution alguna
    _write_comment_html(repo_root_dir, 40108)

    w = AdoOutputWatcher(stable_delay_b=0.0)
    r = w.scan_once()
    assert r["mode_b_closes"] == 0
    assert r["mode_b_skipped"] == 1


def test_mode_b_applies_target_state_from_meta_json(client, repo_root_dir, monkeypatch):
    """Si existe comment.meta.json con target_ado_state, el watcher lo aplica
    al cerrar (vía AdoClient.update_work_item_state)."""
    from services.output_watcher import AdoOutputWatcher
    import services.agent_completion_internal as aci
    import json as _json

    ticket_id = _mk_ticket(40109)
    _mk_execution(ticket_id)
    _write_comment_html(repo_root_dir, 40109, "<p>con meta</p>")

    # Escribir comment.meta.json con target_state
    meta = repo_root_dir / "Agentes" / "outputs" / "40109" / "comment.meta.json"
    meta.write_text(_json.dumps({"target_ado_state": "Reviewed by Dev"}), encoding="utf-8")

    # Stub AdoClient.update_work_item_state para capturar la llamada sin red
    calls: list[tuple] = []

    class _FakeAdoClient:
        def update_work_item_state(self, ado_id, state):
            calls.append((ado_id, state))

    import services.ado_client as _ado_client
    monkeypatch.setattr(_ado_client, "AdoClient", _FakeAdoClient)

    w = AdoOutputWatcher(stable_delay_b=0.0)
    result = w.scan_once()
    assert result["mode_b_closes"] == 1

    # AdoClient.update_work_item_state debe haber sido llamado con (40109, "Reviewed by Dev")
    assert calls == [(40109, "Reviewed by Dev")]


def test_mode_b_no_meta_json_skips_state_change(client, repo_root_dir, monkeypatch):
    """Sin comment.meta.json el watcher cierra/publica pero NO cambia estado."""
    from services.output_watcher import AdoOutputWatcher

    ticket_id = _mk_ticket(40110)
    _mk_execution(ticket_id)
    _write_comment_html(repo_root_dir, 40110)
    # NO meta.json

    calls: list[tuple] = []

    class _FakeAdoClient:
        def update_work_item_state(self, ado_id, state):
            calls.append((ado_id, state))

    import services.ado_client as _ado_client
    monkeypatch.setattr(_ado_client, "AdoClient", _FakeAdoClient)

    w = AdoOutputWatcher(stable_delay_b=0.0)
    result = w.scan_once()
    assert result["mode_b_closes"] == 1
    assert calls == []  # cero llamadas de state change


def test_mode_b_malformed_meta_json_tolerated(client, repo_root_dir, monkeypatch):
    """comment.meta.json malformado → state change skipeado sin romper el publish."""
    from services.output_watcher import AdoOutputWatcher

    ticket_id = _mk_ticket(40111)
    _mk_execution(ticket_id)
    _write_comment_html(repo_root_dir, 40111)

    # meta.json roto
    meta = repo_root_dir / "Agentes" / "outputs" / "40111" / "comment.meta.json"
    meta.write_text("{this is not json", encoding="utf-8")

    calls: list[tuple] = []

    class _FakeAdoClient:
        def update_work_item_state(self, ado_id, state):
            calls.append((ado_id, state))

    import services.ado_client as _ado_client
    monkeypatch.setattr(_ado_client, "AdoClient", _FakeAdoClient)

    w = AdoOutputWatcher(stable_delay_b=0.0)
    result = w.scan_once()
    # Publish OK aunque meta esté roto
    assert result["mode_b_closes"] == 1
    assert calls == []  # state change skipeado


def test_mode_b_ignores_dir_without_comment_html(client, repo_root_dir):
    from services.output_watcher import AdoOutputWatcher

    ticket_id = _mk_ticket(40106)
    _mk_execution(ticket_id)
    # crear el dir pero sin comment.html
    (repo_root_dir / "Agentes" / "outputs" / "40106").mkdir(parents=True)

    w = AdoOutputWatcher(stable_delay_b=0.0)
    r = w.scan_once()
    assert r["mode_b_closes"] == 0


# ── Modo A ───────────────────────────────────────────────────────────────────


def test_mode_a_closes_epic_execution_on_stable_pending_tasks(client, repo_root_dir):
    from services.output_watcher import AdoOutputWatcher
    from db import session_scope
    from models import AgentExecution

    ticket_id = _mk_ticket(40201, work_item_type="Epic")
    exec_id = _mk_execution(ticket_id)
    _write_pending_task(repo_root_dir, 40201, "RF-001")
    _write_pending_task(repo_root_dir, 40201, "RF-002")

    w = AdoOutputWatcher(stable_delay_a=0.0)
    result = w.scan_once()
    assert result["mode_a_closes"] == 1

    with session_scope() as session:
        e = session.get(AgentExecution, exec_id)
        assert e.status == "completed"


def test_mode_a_done_marker_fires_immediately_bypassing_debounce(client, repo_root_dir):
    """Con done-marker, el cierre dispara YA aunque el mtime esté dentro del
    debounce (stable_delay_a alto). Señal determinista P3."""
    from services.output_watcher import AdoOutputWatcher
    from db import session_scope
    from models import AgentExecution

    ticket_id = _mk_ticket(40220, work_item_type="Epic")
    exec_id = _mk_execution(ticket_id)
    # pending-task recién escrito (mtime ahora) → normalmente esperaría el debounce
    _write_pending_task(repo_root_dir, 40220, "RF-001", mtime_offset=0.0)
    _write_done_marker(repo_root_dir, 40220)

    # stable_delay_a alto: sin marker NO cerraría; con marker sí.
    w = AdoOutputWatcher(stable_delay_a=999.0)
    result = w.scan_once()
    assert result["mode_a_closes"] == 1

    with session_scope() as session:
        e = session.get(AgentExecution, exec_id)
        assert e.status == "completed"


def test_mode_a_non_terminal_marker_does_not_fire(client, repo_root_dir):
    """Un done-marker con status=running NO dispara; cae al fallback (debounce)."""
    from services.output_watcher import AdoOutputWatcher

    ticket_id = _mk_ticket(40221, work_item_type="Epic")
    _mk_execution(ticket_id)
    _write_pending_task(repo_root_dir, 40221, "RF-001", mtime_offset=0.0)
    _write_done_marker(repo_root_dir, 40221, status="running")

    w = AdoOutputWatcher(stable_delay_a=999.0)
    result = w.scan_once()
    assert result["mode_a_closes"] == 0  # marker no-terminal + dentro del debounce


def test_mode_a_respects_stable_delay(client, repo_root_dir):
    """pending-task.json recién escritos NO disparan hasta estabilizar."""
    from services.output_watcher import AdoOutputWatcher

    ticket_id = _mk_ticket(40202, work_item_type="Epic")
    _mk_execution(ticket_id)
    # mtime presente (no pasado) → dentro del debounce
    _write_pending_task(repo_root_dir, 40202, "RF-001", mtime_offset=0.0)

    w = AdoOutputWatcher(stable_delay_a=1.0)
    r1 = w.scan_once()
    assert r1["mode_a_closes"] == 0

    time.sleep(1.1)
    r2 = w.scan_once()
    assert r2["mode_a_closes"] == 1


def test_mode_a_does_not_create_child_tasks_when_flag_off(client, repo_root_dir, monkeypatch):
    """Con STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS=false el watcher cierra el
    Epic execution pero NO llama al endpoint create-child-task."""
    from services.output_watcher import AdoOutputWatcher
    from db import session_scope
    from models import Ticket

    monkeypatch.setenv("STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS", "false")

    ticket_id = _mk_ticket(40203, work_item_type="Epic")
    _mk_execution(ticket_id)
    _write_pending_task(repo_root_dir, 40203, "RF-001")

    # Cuentita inicial de tickets — con flag off, ningún ticket nuevo se crea
    with session_scope() as session:
        baseline = session.query(Ticket).count()

    w = AdoOutputWatcher(stable_delay_a=0.0)
    w.scan_once()

    with session_scope() as session:
        after = session.query(Ticket).count()
    assert after == baseline  # cero tickets nuevos


def test_mode_a_invokes_create_child_task_endpoint(client, repo_root_dir, monkeypatch):
    """Con auto-create ON (default), el watcher llama al endpoint create-child-task
    por cada pending-task.json no consumido."""
    from services.output_watcher import AdoOutputWatcher
    import services.output_watcher as ow_mod

    calls: list[dict] = []

    class _FakeResp:
        status_code = 200
        text = "{}"
        def json(self):
            return {"ok": True, "task_ado_id": 99999, "pending_task_consumed": True}

    def _fake_post(url, json=None, timeout=None, **kw):
        calls.append({"url": url, "body": json})
        return _FakeResp()

    # Monkey-patch requests dentro de _auto_create_pending_tasks
    import requests as _req
    monkeypatch.setattr(_req, "post", _fake_post)

    monkeypatch.setenv("STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS", "true")

    ticket_id = _mk_ticket(40207, work_item_type="Epic")
    _mk_execution(ticket_id)
    _write_pending_task(repo_root_dir, 40207, "RF-001")
    _write_pending_task(repo_root_dir, 40207, "RF-002")

    w = AdoOutputWatcher(stable_delay_a=0.0)
    w.scan_once()

    # Debe haber 2 llamadas, una por pending-task
    assert len(calls) == 2
    for call in calls:
        assert "/by-ado/40207/create-child-task" in call["url"]
        assert call["body"]["completion_source"] == "output_watcher_auto"


def test_mode_a_auto_creates_without_running_execution(client, repo_root_dir, monkeypatch):
    """Regresión (ask 2026-06-01): la auto-creación de Tasks NO debe depender de
    una AgentExecution 'running'. Aunque el agente haya corrido fuera del tracking
    de Stacky (execution completed/inexistente), el watcher igual llama a
    create-child-task. El cierre del run se omite (no hay run vivo) pero las Tasks
    se crean automáticamente — la vista Desatascador queda sólo como fallback."""
    from services.output_watcher import AdoOutputWatcher

    calls: list[dict] = []

    class _FakeResp:
        status_code = 200
        text = "{}"
        def json(self):
            return {"ok": True, "task_ado_id": 88888, "pending_task_consumed": True}

    def _fake_post(url, json=None, timeout=None, **kw):
        calls.append({"url": url, "body": json})
        return _FakeResp()

    import requests as _req
    monkeypatch.setattr(_req, "post", _fake_post)
    monkeypatch.setenv("STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS", "true")

    # Execution COMPLETED (no running) — antes esto bloqueaba el auto-create.
    ticket_id = _mk_ticket(40299, work_item_type="Epic", stacky_status="completed")
    _mk_execution(ticket_id, status="completed")
    _write_pending_task(repo_root_dir, 40299, "RF-001")

    w = AdoOutputWatcher(stable_delay_a=0.0)
    r = w.scan_once()

    # Auto-create SÍ se intentó pese a no haber execution running.
    assert len(calls) == 1
    assert "/by-ado/40299/create-child-task" in calls[0]["url"]
    # No hay run vivo que cerrar → no cuenta como close.
    assert r["mode_a_closes"] == 0


def test_mode_a_invalid_pending_task_is_terminal_skip(client, repo_root_dir, monkeypatch):
    """JSON inválido no debe quedar reintentando cada scan como error transitorio."""
    import requests as _req
    import services.output_watcher as ow_mod

    ow_mod._SEEN_TERMINAL_PENDING.clear()
    calls: list[dict] = []

    def _fake_post(url, json=None, timeout=None, **kw):
        calls.append({"url": url, "body": json})
        raise AssertionError("no debe llamar al endpoint con JSON inválido")

    monkeypatch.setattr(_req, "post", _fake_post)

    rf_dir = repo_root_dir / "Agentes" / "outputs" / "epic-40401" / "RF-BAD"
    rf_dir.mkdir(parents=True, exist_ok=True)
    pt = rf_dir / "pending-task.json"
    pt.write_text("", encoding="utf-8")

    first = ow_mod._auto_create_pending_tasks(epic_ado_id=40401, pending_files=[pt])
    second = ow_mod._auto_create_pending_tasks(epic_ado_id=40401, pending_files=[pt])

    assert first == {"created": 0, "skipped": 1, "errors": 0}
    assert second == {"created": 0, "skipped": 1, "errors": 0}
    assert calls == []


def test_mode_a_terminal_4xx_is_quarantined_not_retried(client, repo_root_dir, monkeypatch):
    """Un 4xx estructural del endpoint no debe contarse como error retryable."""
    import requests as _req
    import services.output_watcher as ow_mod

    ow_mod._SEEN_TERMINAL_PENDING.clear()
    calls: list[dict] = []

    class _FakeResp:
        status_code = 422
        text = '{"error":"ADO_PARENT_NOT_FOUND"}'

        def json(self):
            return {
                "ok": False,
                "error": "ADO_PARENT_NOT_FOUND",
                "message": "El work item padre no existe",
            }

    def _fake_post(url, json=None, timeout=None, **kw):
        calls.append({"url": url, "body": json})
        return _FakeResp()

    monkeypatch.setattr(_req, "post", _fake_post)
    pt = _write_pending_task(repo_root_dir, 40402, "RF-PARENT404")

    first = ow_mod._auto_create_pending_tasks(
        epic_ado_id=40402,
        pending_files=[pt],
        project_name="RSPACIFICO",
    )
    second = ow_mod._auto_create_pending_tasks(
        epic_ado_id=40402,
        pending_files=[pt],
        project_name="RSPACIFICO",
    )

    assert first == {"created": 0, "skipped": 1, "errors": 0}
    assert second == {"created": 0, "skipped": 1, "errors": 0}
    assert len(calls) == 1
    assert calls[0]["body"]["project"] == "RSPACIFICO"


def test_mode_a_transient_auto_create_error_is_not_cached(client, repo_root_dir, monkeypatch):
    """Si auto-create falla con 5xx, el mtime no se cachea y el watcher reintenta."""
    import requests as _req
    from services.output_watcher import AdoOutputWatcher

    calls: list[dict] = []

    class _FakeResp:
        status_code = 503
        text = "ADO temporalmente no disponible"

        def json(self):
            raise ValueError("not json")

    def _fake_post(url, json=None, timeout=None, **kw):
        calls.append({"url": url, "body": json})
        return _FakeResp()

    monkeypatch.setattr(_req, "post", _fake_post)
    monkeypatch.setenv("STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS", "true")

    ticket_id = _mk_ticket(40403, work_item_type="Epic")
    _mk_execution(ticket_id)
    _write_pending_task(repo_root_dir, 40403, "RF-RETRY")

    w = AdoOutputWatcher(stable_delay_a=0.0)
    w.scan_once()
    assert len(calls) == 1
    assert not w._seen_a

    w.scan_once()
    assert len(calls) == 2


def test_mode_a_auto_creates_from_alt_base_when_canonical_missing(client, repo_root_dir, monkeypatch):
    """Regresión (incidente 2026-06-01, proyecto RSSICREA): el agente escribió el
    pending-task.json SÓLO en `output/tickets/epic-{id}/` y NUNCA creó el dir
    canónico `Agentes/outputs`. scan_once hacía `return` temprano al no existir el
    canónico y jamás escaneaba la base alternativa → el auto-create quedaba muerto
    y la Task atascada. Tras el fix, scan_once igual escanea `output/tickets`
    aunque `Agentes/outputs` no exista."""
    import shutil
    from services.output_watcher import AdoOutputWatcher

    calls: list[dict] = []

    class _FakeResp:
        status_code = 200
        text = "{}"
        def json(self):
            return {"ok": True, "task_ado_id": 77777, "pending_task_consumed": True}

    def _fake_post(url, json=None, timeout=None, **kw):
        calls.append({"url": url, "body": json})
        return _FakeResp()

    import requests as _req
    monkeypatch.setattr(_req, "post", _fake_post)
    monkeypatch.setenv("STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS", "true")

    # El dir canónico NO debe existir: replica el caso RSSICREA real.
    shutil.rmtree(repo_root_dir / "Agentes", ignore_errors=True)
    assert not (repo_root_dir / "Agentes" / "outputs").exists()

    # Sin ticket ni execution en DB: el agente corrió fuera del tracking (Copilot
    # directo) y el auto-create igual debe dispararse desde el scan de disco
    # (ocurre antes del gate de execution en _process_mode_a). No tocar la DB acá
    # también evita contaminar la in-memory compartida de otros tests.
    _write_pending_task_alt(repo_root_dir, 40301, "RF-001")

    w = AdoOutputWatcher(stable_delay_a=0.0)
    w.scan_once()

    # El auto-create se invocó pese a que `Agentes/outputs` no existe.
    assert len(calls) == 1, f"esperaba 1 call al endpoint, hubo {len(calls)}"
    assert "/by-ado/40301/create-child-task" in calls[0]["url"]
    assert calls[0]["body"]["completion_source"] == "output_watcher_auto"


def test_mode_a_idempotent_does_not_double_close(client, repo_root_dir):
    from services.output_watcher import AdoOutputWatcher
    from db import session_scope
    from services.ticket_status import TicketStatusEvent

    ticket_id = _mk_ticket(40204, work_item_type="Epic")
    exec_id = _mk_execution(ticket_id)
    _write_pending_task(repo_root_dir, 40204, "RF-001")

    w = AdoOutputWatcher(stable_delay_a=0.0)
    w.scan_once()
    w.scan_once()  # segundo round, no debe re-fire

    with session_scope() as session:
        # Filtrar por execution_id para aislar del ruido de otros tests del archivo
        mode_a_events = (
            session.query(TicketStatusEvent)
            .filter(
                TicketStatusEvent.execution_id == exec_id,
                TicketStatusEvent.reason.like("%output_watcher mode_a%"),
            )
            .all()
        )
    assert len(mode_a_events) == 1


def test_mode_a_skips_when_no_pending_tasks(client, repo_root_dir):
    """Carpeta epic-{id}/ vacía → no acción."""
    from services.output_watcher import AdoOutputWatcher

    ticket_id = _mk_ticket(40205, work_item_type="Epic")
    _mk_execution(ticket_id)
    # Crear el dir pero sin pending-task.json adentro
    (repo_root_dir / "Agentes" / "outputs" / "epic-40205").mkdir(parents=True)

    w = AdoOutputWatcher(stable_delay_a=0.0)
    r = w.scan_once()
    assert r["mode_a_closes"] == 0


def test_mode_a_skips_when_no_running_execution(client, repo_root_dir):
    from services.output_watcher import AdoOutputWatcher

    ticket_id = _mk_ticket(40206, work_item_type="Epic", stacky_status="completed")
    _mk_execution(ticket_id, status="completed")
    _write_pending_task(repo_root_dir, 40206, "RF-001")

    w = AdoOutputWatcher(stable_delay_a=0.0)
    r = w.scan_once()
    assert r["mode_a_closes"] == 0
    assert r["mode_a_skipped"] == 1


# ── Robustez ─────────────────────────────────────────────────────────────────


def test_outputs_dir_re_resolves_lazily_between_scans(client, repo_root_dir, monkeypatch, tmp_path):
    """El watcher (sin override) resuelve outputs_dir en cada scan, así que si
    repo_root cambia tras el arranque (p.ej. al activarse el proyecto) lo refleja.

    Reproduce C1: watcher construido apuntando a un root sin Agentes/outputs
    (scan no-op), luego el root correcto aparece → el scan siguiente dispara.
    """
    from services.output_watcher import AdoOutputWatcher

    # Root inicial SIN Agentes/outputs → outputs_dir no existe → scan no-op.
    other_root = tmp_path / "sin_proyecto"
    other_root.mkdir()
    monkeypatch.setenv("STACKY_REPO_ROOT", str(other_root))

    w = AdoOutputWatcher(stable_delay_a=0.0)
    assert not w.outputs_dir.exists()
    r1 = w.scan_once()
    assert r1["mode_a_closes"] == 0

    # Preparar el root correcto (repo_root_dir ya tiene Agentes/outputs) con un
    # epic listo para cerrar, y "activar" ese root cambiando el env.
    ticket_id = _mk_ticket(40210, work_item_type="Epic")
    _mk_execution(ticket_id)
    _write_pending_task(repo_root_dir, 40210, "RF-001")
    monkeypatch.setenv("STACKY_REPO_ROOT", str(repo_root_dir))

    # El mismo watcher, sin reconstruir, ahora ve el dir correcto.
    assert w.outputs_dir.exists()
    r2 = w.scan_once()
    assert r2["mode_a_closes"] == 1


def test_scan_handles_malformed_dir_names(client, repo_root_dir):
    """Dirs con nombre no numérico o epic-abc → ignorados sin error."""
    from services.output_watcher import AdoOutputWatcher

    outputs = repo_root_dir / "Agentes" / "outputs"
    (outputs / "foo").mkdir()  # nombre no numérico
    (outputs / "epic-abc").mkdir()  # epic con sufijo no numérico
    (outputs / "epic-").mkdir()  # epic vacío

    w = AdoOutputWatcher(stable_delay_a=0.0, stable_delay_b=0.0)
    r = w.scan_once()  # no debe lanzar
    assert r["mode_b_closes"] == 0
    assert r["mode_a_closes"] == 0


# ── Endpoint scan-now ────────────────────────────────────────────────────────


def test_scan_now_endpoint_triggers_close(client, repo_root_dir):
    ticket_id = _mk_ticket(40301)
    _mk_execution(ticket_id)
    _write_comment_html(repo_root_dir, 40301)

    r = client.post("/api/diag/output-watcher/scan-now")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    # El watcher arrancó ad-hoc porque STACKY_OUTPUT_WATCHER_ENABLED=false
    assert body["ad_hoc_watcher"] is True
    assert body["round"]["mode_b_closes"] == 1


def test_stats_endpoint_returns_empty_when_disabled(client):
    r = client.get("/api/diag/output-watcher/stats")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["running"] is False
    assert body["stats"] is None
