"""Tests para auto-publish server-side en PATCH /api/tickets/by-ado/{ado_id}/stacky-status.

Contrato arquitectónico (2026-05-15):
  El agente NO envía ningún flag de publicación. Stacky decide automáticamente
  si publicar en ADO cuando detecta status=completed + html_output_path + AgentExecution.
  El control de opt-out es server-side via STACKY_LEGACY_AUTO_PUBLISH (default "on").

Cubre:
  1. Default (STACKY_LEGACY_AUTO_PUBLISH=on) + status=completed + exec + html_output_path
     → publisher invocado automáticamente, response publish.ok=true.
  2. STACKY_LEGACY_AUTO_PUBLISH=on + publish falla
     → response 200 (status local guardado), publish.ok=false, event=publish.failed.
  3. STACKY_LEGACY_AUTO_PUBLISH=on + publisher lanza excepcion
     → response 200, publish.ok=false con type y reason.
  4. STACKY_LEGACY_AUTO_PUBLISH=off
     → publish.skipped=true, reason=legacy_auto_publish_disabled.
  5. status != completed (e.g. "error")
     → publish.skipped=true, reason=status_not_completed.
  6. html_output_path ausente en el body
     → publish.skipped=true, reason=html_output_path_missing.
  7. No hay AgentExecution en BD
     → publish.skipped=true, reason=no_execution_found.
  8. Ticket no existe en BD → 200 skipped (backwards-compat).
  9. Body sin 'status' → 400.
  10. Campo "auto_publish" enviado por el agente es ignorado (backwards-compat):
      el comportamiento de publish lo determina el servidor, no el campo del body.
  11. Callers que no esperaban "publish" en el response no rompen
      (publish siempre presente como dict, nunca null).

Nota sobre services.ado_publisher:
  El modulo solo existe como .pyc (sin fuente .py). No es importable directamente
  en el entorno de test. El patron de mock es inyectar un modulo stub en
  sys.modules['services.ado_publisher'] antes de que el import local dentro
  de set_stacky_status_by_ado lo resuelva.
"""
from __future__ import annotations

import os
import sys
import types
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


# ── Fake PublishResult ────────────────────────────────────────────────────────


@dataclass
class FakePublishResult:
    ok: bool
    status: str
    reason: str | None = None
    ado_id: int | None = None
    execution_id: int | None = None
    html_sha256: str | None = None
    ado_response: dict | None = None
    record_id: int | None = None


# ── Helper: inyectar stub de ado_publisher en sys.modules ─────────────────────


def _inject_publisher_stub(publish_fn) -> None:
    """Inyecta un modulo fake en sys.modules para que el import local del endpoint lo use."""
    stub = types.ModuleType("services.ado_publisher")
    stub.publish_from_execution = publish_fn
    sys.modules["services.ado_publisher"] = stub
    if "services" in sys.modules:
        sys.modules["services"].ado_publisher = stub  # type: ignore[attr-defined]


def _remove_publisher_stub() -> None:
    sys.modules.pop("services.ado_publisher", None)
    if "services" in sys.modules and hasattr(sys.modules["services"], "ado_publisher"):
        try:
            delattr(sys.modules["services"], "ado_publisher")
        except AttributeError:
            pass


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clean_publisher_stub():
    """Limpia el stub de ado_publisher antes y despues de cada test."""
    _remove_publisher_stub()
    yield
    _remove_publisher_stub()


@pytest.fixture(autouse=True)
def reset_auto_publish_env(monkeypatch):
    """Asegura que cada test parte con STACKY_LEGACY_AUTO_PUBLISH=on (default)."""
    monkeypatch.setenv("STACKY_LEGACY_AUTO_PUBLISH", "on")


@pytest.fixture
def tmp_repo(monkeypatch, tmp_path):
    monkeypatch.setenv("STACKY_REPO_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def client(tmp_repo):
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    from services.ticket_status import stop_stale_recovery
    stop_stale_recovery()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()


def _mk_ticket_and_exec(ado_id: int, agent_type: str = "functional") -> tuple[int, int]:
    """Crea Ticket + AgentExecution en BD. Devuelve (ticket_id, exec_id)."""
    from db import session_scope
    from models import Ticket, AgentExecution

    with session_scope() as session:
        t = Ticket(
            ado_id=ado_id,
            project="RSPacifico",
            title=f"t-{ado_id}",
            ado_state="In Progress",
            stacky_status="running",
        )
        session.add(t)
        session.flush()
        e = AgentExecution(
            ticket_id=t.id,
            agent_type=agent_type,
            status="running",
            input_context_json="[]",
            started_by="test",
            started_at=datetime.utcnow(),
        )
        session.add(e)
        session.flush()
        return t.id, e.id


def _mk_ticket_only(ado_id: int) -> int:
    """Crea solo Ticket sin ejecucion. Devuelve ticket_id."""
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=ado_id,
            project="RSPacifico",
            title=f"t-{ado_id}",
            ado_state="In Progress",
            stacky_status="running",
        )
        session.add(t)
        session.flush()
        return t.id


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_server_side_publish_on_completed_with_html_path(client, tmp_repo):
    """Default (STACKY_LEGACY_AUTO_PUBLISH=on): agente manda solo status+html_output_path
    → publisher invocado automaticamente, response publish.ok=true."""
    ado_id = 9001
    _mk_ticket_and_exec(ado_id)

    calls: list[tuple[int, str]] = []

    def fake_publish(execution_id: int, triggered_by: str = "legacy_auto_publish", **kw):
        calls.append((execution_id, triggered_by))
        return FakePublishResult(
            ok=True,
            status="ok",
            ado_id=ado_id,
            execution_id=execution_id,
            html_sha256="abc123",
            ado_response={"id": 42},
            record_id=1,
        )

    _inject_publisher_stub(fake_publish)

    # El agente NO manda auto_publish — solo status + html_output_path
    resp = client.patch(
        f"/api/tickets/by-ado/{ado_id}/stacky-status",
        json={
            "status": "completed",
            "reason": "AnalistaFuncional completo ADO-9001",
            "agent_type": "functional",
            "html_output_path": f"Agentes/outputs/{ado_id}/comment.html",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["publish"]["ok"] is True
    assert body["publish"]["status"] == "ok"
    assert body["publish"]["event"] == "publish.succeeded"
    assert len(calls) == 1
    assert calls[0][1] == "legacy_auto_publish"


def test_publish_fails_does_not_break_patch_response(client, tmp_repo):
    """Publish falla → response 200, status local guardado, publish.ok=false."""
    ado_id = 9002
    _mk_ticket_and_exec(ado_id)

    def fake_publish(execution_id: int, **kw):
        return FakePublishResult(ok=False, status="failed", reason="ADO timeout")

    _inject_publisher_stub(fake_publish)

    resp = client.patch(
        f"/api/tickets/by-ado/{ado_id}/stacky-status",
        json={
            "status": "completed",
            "reason": "test fail path",
            "agent_type": "functional",
            "html_output_path": f"Agentes/outputs/{ado_id}/comment.html",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True  # status local preservado
    assert body["current_status"] == "completed"
    assert body["publish"]["ok"] is False
    assert body["publish"]["event"] == "publish.failed"
    assert "ADO timeout" in body["publish"]["reason"]


def test_publish_raises_exception_does_not_break_patch_response(client, tmp_repo):
    """Publisher lanza excepcion → response 200, publish.ok=false con type y reason."""
    ado_id = 9003
    _mk_ticket_and_exec(ado_id)

    def fake_publish(execution_id: int, **kw):
        raise RuntimeError("connection refused")

    _inject_publisher_stub(fake_publish)

    resp = client.patch(
        f"/api/tickets/by-ado/{ado_id}/stacky-status",
        json={
            "status": "completed",
            "html_output_path": f"Agentes/outputs/{ado_id}/comment.html",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["publish"]["ok"] is False
    assert body["publish"]["event"] == "publish.failed"
    assert "connection refused" in body["publish"]["reason"]
    assert body["publish"]["type"] == "RuntimeError"


def test_legacy_auto_publish_off_skips_publish(client, tmp_repo, monkeypatch):
    """STACKY_LEGACY_AUTO_PUBLISH=off → publish.skipped, reason=legacy_auto_publish_disabled."""
    monkeypatch.setenv("STACKY_LEGACY_AUTO_PUBLISH", "off")
    ado_id = 9004
    _mk_ticket_and_exec(ado_id)

    publish_calls: list = []

    def fake_publish(execution_id: int, **kw):
        publish_calls.append(execution_id)
        return FakePublishResult(ok=True, status="ok")

    _inject_publisher_stub(fake_publish)

    resp = client.patch(
        f"/api/tickets/by-ado/{ado_id}/stacky-status",
        json={
            "status": "completed",
            "html_output_path": f"Agentes/outputs/{ado_id}/comment.html",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["publish"]["skipped"] is True
    assert body["publish"]["reason"] == "legacy_auto_publish_disabled"
    assert len(publish_calls) == 0  # publisher NO invocado


def test_status_not_completed_skips_publish(client, tmp_repo):
    """status=error → publish.skipped=true, reason=status_not_completed."""
    ado_id = 9005
    _mk_ticket_and_exec(ado_id)

    publish_calls: list = []

    def fake_publish(execution_id: int, **kw):
        publish_calls.append(execution_id)
        return FakePublishResult(ok=True, status="ok")

    _inject_publisher_stub(fake_publish)

    resp = client.patch(
        f"/api/tickets/by-ado/{ado_id}/stacky-status",
        json={
            "status": "error",
            "html_output_path": f"Agentes/outputs/{ado_id}/comment.html",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["publish"]["skipped"] is True
    assert body["publish"]["reason"] == "status_not_completed"
    assert len(publish_calls) == 0  # publisher NO invocado


def test_html_output_path_missing_skips_publish(client, tmp_repo):
    """html_output_path ausente en el body → publish.skipped, reason=html_output_path_missing."""
    ado_id = 9006
    _mk_ticket_and_exec(ado_id)

    publish_calls: list = []

    def fake_publish(execution_id: int, **kw):
        publish_calls.append(execution_id)
        return FakePublishResult(ok=True, status="ok")

    _inject_publisher_stub(fake_publish)

    # El agente manda status=completed pero NO html_output_path
    resp = client.patch(
        f"/api/tickets/by-ado/{ado_id}/stacky-status",
        json={"status": "completed", "reason": "sin html_output_path"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["publish"]["skipped"] is True
    assert body["publish"]["reason"] == "html_output_path_missing"
    assert len(publish_calls) == 0


def test_no_execution_in_db_skips_publish(client, tmp_repo):
    """No hay AgentExecution en BD → publish.skipped, reason=no_execution_found."""
    ado_id = 9007
    _mk_ticket_only(ado_id)  # sin AgentExecution

    publish_calls: list = []

    def fake_publish(execution_id: int, **kw):
        publish_calls.append(execution_id)
        return FakePublishResult(ok=True, status="ok")

    _inject_publisher_stub(fake_publish)

    resp = client.patch(
        f"/api/tickets/by-ado/{ado_id}/stacky-status",
        json={
            "status": "completed",
            "html_output_path": f"Agentes/outputs/{ado_id}/comment.html",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["publish"]["skipped"] is True
    assert body["publish"]["reason"] == "no_execution_found"
    assert len(publish_calls) == 0


def test_ticket_not_in_db_returns_200_skipped(client, tmp_repo):
    """Ticket no en BD → 200 skipped (backwards-compat legacy)."""
    resp = client.patch(
        "/api/tickets/by-ado/99999/stacky-status",
        json={
            "status": "completed",
            "html_output_path": "Agentes/outputs/99999/comment.html",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["skipped"] is True


def test_missing_status_returns_400(client, tmp_repo):
    """Body sin 'status' → 400."""
    ado_id = 9008
    _mk_ticket_only(ado_id)
    resp = client.patch(
        f"/api/tickets/by-ado/{ado_id}/stacky-status",
        json={"html_output_path": f"Agentes/outputs/{ado_id}/comment.html"},
    )
    assert resp.status_code == 400
    assert "status" in resp.get_json()["error"]


def test_agent_auto_publish_field_is_ignored_server_decides(client, tmp_repo):
    """Campo 'auto_publish' del body es ignorado — la decision la toma el servidor.

    Backwards-compat: si un caller legacy manda auto_publish=false, el servidor
    sigue publicando si se cumplen las precondiciones (STACKY_LEGACY_AUTO_PUBLISH=on
    y html_output_path presente).
    """
    ado_id = 9009
    _mk_ticket_and_exec(ado_id)

    calls: list = []

    def fake_publish(execution_id: int, **kw):
        calls.append(execution_id)
        return FakePublishResult(ok=True, status="ok", execution_id=execution_id)

    _inject_publisher_stub(fake_publish)

    # Caller legacy manda auto_publish=false — el servidor lo ignora y publica igual
    resp = client.patch(
        f"/api/tickets/by-ado/{ado_id}/stacky-status",
        json={
            "status": "completed",
            "html_output_path": f"Agentes/outputs/{ado_id}/comment.html",
            "auto_publish": False,  # campo ignorado por el servidor
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    # El servidor publicó porque las precondiciones se cumplen — auto_publish=false ignorado
    assert body["publish"].get("ok") is True
    assert len(calls) == 1


def test_publish_field_always_present_in_response(client, tmp_repo):
    """El campo 'publish' siempre está presente en el response como dict (nunca null).

    Garantiza que callers que iteran sobre publish.* no rompen por KeyError.
    """
    ado_id = 9010
    _mk_ticket_and_exec(ado_id)

    # No inyectar publisher stub — el skip ocurre antes por status=cancelled
    resp = client.patch(
        f"/api/tickets/by-ado/{ado_id}/stacky-status",
        json={"status": "cancelled"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "publish" in body
    assert isinstance(body["publish"], dict)
    assert "skipped" in body["publish"] or "ok" in body["publish"]
