"""
test_agent_completion_gateway.py — Tests P1: AgentCompletionGateway en modo shadow.

Cubre §9.1 (unitarios) y §9.2 (integración) del plan SSD.

Invariantes verificadas:
  U01  test_gateway_off_returns_404_or_disabled
  U02  test_gateway_shadow_does_not_mutate_db
  U03  test_gateway_shadow_does_not_call_ado_publisher
  U04  test_gateway_resolves_by_execution_id
  U05  test_gateway_resolves_by_agent_type_when_unique
  U06  test_gateway_resolves_when_single_active_mismatched_type
  U07  test_gateway_rejects_when_zero_active_and_no_rescue_flag
  U08  test_gateway_invalid_html_returns_422_needs_review_plan
  U09  test_gateway_auth_required_returns_401
  U10  test_gateway_payload_invalid_returns_400
  U11  test_gateway_shadow_logs_discrepancy_when_legacy_diverges

Integración:
  I01  test_integration_shadow_no_writes_end_to_end
  I02  test_integration_shadow_parallel_with_legacy_logs_coincidence
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Bootstrap ─────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Forzar DB en memoria para todos los tests
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["LLM_BACKEND"] = "mock"
# Token de prueba para el gateway
os.environ["STACKY_AGENT_TOKEN"] = "test-secret-token-p1"


# ── Fixtures compartidas ───────────────────────────────────────────────────────


_TEST_ADO_ID = 99149   # ID ficticio que no existe en el ADO real del proyecto
_TEST_ADO_ID_2 = 99200  # segundo ID ficticio para tests multi-ticket


@pytest.fixture
def html_dir(tmp_path: Path, monkeypatch):
    """Crea <tmp>/Agentes/outputs/99149/comment.html válido y apunta STACKY_REPO_ROOT.

    Usa ado_id=99149 (ficticio) para no colisionar con tickets reales
    que el startup-sync de create_app() inserta.
    """
    outputs = tmp_path / "Agentes" / "outputs" / str(_TEST_ADO_ID)
    outputs.mkdir(parents=True)
    html_file = outputs / "comment.html"
    html_file.write_text(
        "<h2>Análisis Funcional</h2><p>Contenido válido del agente para ADO-99149.</p>"
        "<p>Detalle del análisis funcional completo.</p>" * 5,
        encoding="utf-8",
    )
    # También preparar directorio para el segundo ado_id usado en tests multi-ticket
    outputs2 = tmp_path / "Agentes" / "outputs" / str(_TEST_ADO_ID_2)
    outputs2.mkdir(parents=True)
    monkeypatch.setenv("STACKY_REPO_ROOT", str(tmp_path))
    return tmp_path


def _flush_syslogger(timeout: float = 5.0) -> None:
    """Drena todos los eventos pendientes del stacky_logger antes de tocar la DB."""
    try:
        from services.stacky_logger import logger as _sl
        _sl.flush_now(timeout=timeout)
        _sl.flush_now(timeout=timeout)  # doble flush: el segundo drena lo que llegó mientras el primero procesaba
    except Exception:
        pass


@pytest.fixture
def client(html_dir):
    """Flask test client con STACKY_COMPLETION_GATEWAY=shadow y DB limpia.

    El endpoint lee STACKY_COMPLETION_GATEWAY dinámicamente en cada request,
    por lo que los tests que necesiten probar otro modo solo deben setear
    os.environ ANTES de la llamada (ver test_gateway_off_returns_404_or_disabled).

    Teardown: flush logger + drop DB para evitar "database is locked" entre tests.
    """
    os.environ["STACKY_COMPLETION_GATEWAY"] = "shadow"

    # Flush cualquier log pendiente del test anterior antes de reiniciar la DB
    _flush_syslogger()

    from db import engine, Base
    Base.metadata.drop_all(engine)

    from app import create_app
    app = create_app()
    app.config.update(TESTING=True)
    from services.ticket_status import stop_stale_recovery
    stop_stale_recovery()

    with app.test_client() as c:
        yield c

    # Teardown: detener recovery + flush logger para que el próximo test encuentre la DB libre
    stop_stale_recovery()
    _flush_syslogger()
    os.environ["STACKY_COMPLETION_GATEWAY"] = "shadow"


_VALID_TOKEN = "test-secret-token-p1"
_VALID_HEADERS = {
    "X-Stacky-Agent-Token": _VALID_TOKEN,
    "X-User-Email": "agent@test.local",
    "Content-Type": "application/json",
}
_SHADOW_HEADERS = _VALID_HEADERS


def _mk_ticket_and_exec(
    ado_id: int = _TEST_ADO_ID,
    agent_type: str = "functional",
    exec_status: str = "running",
) -> tuple[int, int]:
    """Crea Ticket + AgentExecution con ado_id ficticio. Retorna (ticket_id, execution_id)."""
    from db import session_scope
    from models import Ticket, AgentExecution

    with session_scope() as session:
        t = Ticket(
            ado_id=ado_id,
            project="RSPacifico",
            title=f"Ticket TEST-{ado_id}",
            ado_state="Active",
            stacky_status="running",
        )
        session.add(t)
        session.flush()
        e = AgentExecution(
            ticket_id=t.id,
            agent_type=agent_type,
            status=exec_status,
            input_context_json="[]",
            started_by="test_agent",
            started_at=datetime.utcnow(),
        )
        session.add(e)
        session.flush()
        return t.id, e.id


def _default_payload(
    execution_id: int | None = None,
    agent_type: str = "functional",
    status: str = "completed",
    allow_synthetic_rescue: bool = False,
    include_legacy: dict | None = None,
    ado_id: int = _TEST_ADO_ID,
) -> dict:
    d: dict = {
        "agent_type": agent_type,
        "status": status,
        "html_output_path": f"Agentes/outputs/{ado_id}/comment.html",
        "metadata": {
            "agent_version": "AgentTest@2026-05-14",
            "duration_ms": 5000,
        },
        "reason": "test run",
        "allow_synthetic_rescue": allow_synthetic_rescue,
    }
    if execution_id is not None:
        d["execution_id"] = execution_id
    if include_legacy is not None:
        d["_legacy_observed"] = include_legacy
    return d


def _gateway_url(ado_id: int = _TEST_ADO_ID) -> str:
    return f"/api/tickets/by-ado/{ado_id}/agent-completion"


# ═══════════════════════════════════════════════════════════════════════════════
# U01 — Gateway off devuelve 404
# ═══════════════════════════════════════════════════════════════════════════════


def test_gateway_off_returns_404_or_disabled(client):
    """Con STACKY_COMPLETION_GATEWAY=off el endpoint debe devolver 404.

    El endpoint lee el flag dinámicamente; cambiamos el env antes de la llamada.
    """
    original = os.environ.get("STACKY_COMPLETION_GATEWAY", "shadow")
    try:
        os.environ["STACKY_COMPLETION_GATEWAY"] = "off"
        r = client.post(
            _gateway_url(),
            json=_default_payload(),
            headers=_SHADOW_HEADERS,
        )
    finally:
        os.environ["STACKY_COMPLETION_GATEWAY"] = original

    assert r.status_code == 404, f"Esperado 404, got {r.status_code}: {r.data}"
    data = r.get_json()
    assert data["ok"] is False
    assert data["error"]["code"] == "gateway_disabled"


# ═══════════════════════════════════════════════════════════════════════════════
# U02 — Shadow no muta la DB
# ═══════════════════════════════════════════════════════════════════════════════


def test_gateway_shadow_does_not_mutate_db(client):
    """El gateway en shadow NO debe cambiar status de AgentExecution ni Ticket."""
    ticket_id, exec_id = _mk_ticket_and_exec(ado_id=_TEST_ADO_ID, exec_status="running")

    # Capturar estado antes
    from db import session_scope
    from models import AgentExecution, Ticket
    with session_scope() as s:
        exec_before = s.get(AgentExecution, exec_id)
        ticket_before = s.query(Ticket).filter(Ticket.ado_id == _TEST_ADO_ID).first()
        status_before = exec_before.status
        completed_at_before = exec_before.completed_at
        stacky_status_before = ticket_before.stacky_status

    r = client.post(
        _gateway_url(),
        json=_default_payload(execution_id=exec_id),
        headers=_SHADOW_HEADERS,
    )
    assert r.status_code == 200, r.data
    data = r.get_json()
    assert data["mode"] == "shadow"
    assert data["would_succeed"] is True

    # Verificar que DB no fue mutada
    with session_scope() as s:
        exec_after = s.get(AgentExecution, exec_id)
        ticket_after = s.query(Ticket).filter(Ticket.ado_id == _TEST_ADO_ID).first()

        assert exec_after.status == status_before, (
            f"AgentExecution.status cambió de '{status_before}' "
            f"a '{exec_after.status}' — el shadow NO debe mutar DB"
        )
        assert exec_after.completed_at == completed_at_before, (
            "AgentExecution.completed_at fue modificado en modo shadow"
        )
        assert ticket_after.stacky_status == stacky_status_before, (
            "Ticket.stacky_status fue modificado en modo shadow"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# U03 — Shadow no llama a ado_publisher
# ═══════════════════════════════════════════════════════════════════════════════


def test_gateway_shadow_does_not_call_ado_publisher(client):
    """En shadow, ado_publisher.publish_from_execution NO debe ser invocado."""
    _mk_ticket_and_exec(ado_id=_TEST_ADO_ID, exec_status="running")

    with patch(
        "services.ado_publisher.publish_from_execution"
    ) as mock_publish:
        r = client.post(
            _gateway_url(),
            json=_default_payload(),
            headers=_SHADOW_HEADERS,
        )
        assert r.status_code == 200
        mock_publish.assert_not_called(), (
            "ado_publisher.publish_from_execution fue llamado en modo shadow"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# U04 — Resolución por execution_id explícito
# ═══════════════════════════════════════════════════════════════════════════════


def test_gateway_resolves_by_execution_id(client):
    """Con execution_id explícito, el gateway debe usar esa execution."""
    ticket_id, exec_id = _mk_ticket_and_exec(ado_id=_TEST_ADO_ID, exec_status="running")

    r = client.post(
        _gateway_url(),
        json=_default_payload(execution_id=exec_id),
        headers=_SHADOW_HEADERS,
    )
    assert r.status_code == 200, r.data
    data = r.get_json()
    assert data["mode"] == "shadow"
    assert data["execution_id"] == exec_id
    assert data["would_succeed"] is True
    assert data["errors"] == []


def test_gateway_resolves_by_execution_id_wrong_ticket_returns_409(client):
    """execution_id de otro ticket → 409 execution_state_invalid."""
    # Ticket 149 exec
    _mk_ticket_and_exec(ado_id=_TEST_ADO_ID, exec_status="running")
    # Ticket 200 exec
    _mk_ticket_and_exec(ado_id=_TEST_ADO_ID_2, exec_status="running")

    # Buscar exec del ticket 200
    from db import session_scope
    from models import AgentExecution, Ticket
    with session_scope() as s:
        t200 = s.query(Ticket).filter(Ticket.ado_id == _TEST_ADO_ID_2).first()
        exec200 = s.query(AgentExecution).filter(
            AgentExecution.ticket_id == t200.id
        ).first()
        exec200_id = exec200.id

    # Llamar al gateway del ticket 149 con exec del ticket 200
    r = client.post(
        _gateway_url(),
        json=_default_payload(execution_id=exec200_id),
        headers=_SHADOW_HEADERS,
    )
    assert r.status_code == 200, r.data
    data = r.get_json()
    assert data["mode"] == "shadow"
    assert data["would_succeed"] is False
    assert any(e["error"]["code"] == "execution_state_invalid" for e in data["errors"])


def test_gateway_resolves_by_execution_id_terminal_returns_409(client):
    """execution_id ya terminal → 409 execution_state_invalid."""
    ticket_id, exec_id = _mk_ticket_and_exec(ado_id=_TEST_ADO_ID, exec_status="completed")

    r = client.post(
        _gateway_url(),
        json=_default_payload(execution_id=exec_id),
        headers=_SHADOW_HEADERS,
    )
    assert r.status_code == 200, r.data
    data = r.get_json()
    assert data["would_succeed"] is False
    assert any(e["error"]["code"] == "execution_state_invalid" for e in data["errors"])


# ═══════════════════════════════════════════════════════════════════════════════
# U05 — Resolución por agent_type cuando hay una única activa coincidente
# ═══════════════════════════════════════════════════════════════════════════════


def test_gateway_resolves_by_agent_type_when_unique(client):
    """Sin execution_id, debe resolver por agent_type matching."""
    ticket_id, exec_id = _mk_ticket_and_exec(
        ado_id=_TEST_ADO_ID, agent_type="functional", exec_status="running"
    )

    r = client.post(
        _gateway_url(),
        json=_default_payload(agent_type="functional"),
        headers=_SHADOW_HEADERS,
    )
    assert r.status_code == 200, r.data
    data = r.get_json()
    assert data["mode"] == "shadow"
    assert data["execution_id"] == exec_id
    assert data["agent_type_mismatch"] is False
    assert data["would_succeed"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# U06 — Una sola activa con agent_type diferente → mismatch=true
# ═══════════════════════════════════════════════════════════════════════════════


def test_gateway_resolves_when_single_active_mismatched_type(client):
    """Si hay 1 activa con agent_type distinto, se usa con mismatch=True."""
    ticket_id, exec_id = _mk_ticket_and_exec(
        ado_id=_TEST_ADO_ID, agent_type="developer", exec_status="running"
    )

    # payload dice 'functional' pero la única activa es 'developer'
    r = client.post(
        _gateway_url(),
        json=_default_payload(agent_type="functional"),
        headers=_SHADOW_HEADERS,
    )
    assert r.status_code == 200, r.data
    data = r.get_json()
    assert data["execution_id"] == exec_id
    assert data["agent_type_mismatch"] is True
    assert data["would_succeed"] is True, (
        "Con 1 activa y mismatch, el gateway debería resolver y producir would_succeed=True"
    )

    # Esperar a que el stacky_logger termine de persistir antes de leer system_logs
    _flush_syslogger()

    # Debe quedar registrado en SystemLog
    from db import session_scope
    from models import SystemLog
    with session_scope() as s:
        logs = s.query(SystemLog).filter(
            SystemLog.source == "completion_gateway",
            SystemLog.action == "shadow.invocation",
        ).all()
        assert len(logs) >= 1
        last = logs[-1]
        ctx = json.loads(last.context_json)
        assert ctx.get("agent_type_mismatch") is True


# ═══════════════════════════════════════════════════════════════════════════════
# U07 — Cero activas sin flag de rescate → 409 no_active_execution
# ═══════════════════════════════════════════════════════════════════════════════


def test_gateway_rejects_when_zero_active_and_no_rescue_flag(client):
    """Sin ejecuciones activas y sin allow_synthetic_rescue → error."""
    _mk_ticket_and_exec(ado_id=_TEST_ADO_ID, exec_status="completed")  # ya terminal

    r = client.post(
        _gateway_url(),
        json=_default_payload(allow_synthetic_rescue=False),
        headers=_SHADOW_HEADERS,
    )
    assert r.status_code == 200, r.data
    data = r.get_json()
    assert data["mode"] == "shadow"
    assert data["would_succeed"] is False
    error_codes = [e["error"]["code"] for e in data["errors"]]
    assert "no_active_execution" in error_codes


def test_gateway_allows_synthetic_rescue_when_flag_set(client):
    """Con allow_synthetic_rescue=True, el plan debe incluir la execution sintética."""
    _mk_ticket_and_exec(ado_id=_TEST_ADO_ID, exec_status="completed")  # ya terminal

    r = client.post(
        _gateway_url(),
        json=_default_payload(allow_synthetic_rescue=True),
        headers=_SHADOW_HEADERS,
    )
    assert r.status_code == 200, r.data
    data = r.get_json()
    assert data["mode"] == "shadow"
    # No debería haber error de no_active_execution
    error_codes = [e["error"]["code"] for e in data["errors"]]
    assert "no_active_execution" not in error_codes
    # El plan debe mencionar execution sintética
    plan_descs = [s["description"] for s in data["plan"]]
    assert any("sintética" in d or "rescue" in d for d in plan_descs), (
        f"El plan no menciona execution sintética: {plan_descs}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# U08 — HTML inválido → would_succeed=False, plan refleja el bloqueo
# ═══════════════════════════════════════════════════════════════════════════════


def test_gateway_invalid_html_returns_422_needs_review_plan(client):
    """HTML inválido (archivo inexistente) → would_succeed=False con html_invalid."""
    _mk_ticket_and_exec(ado_id=_TEST_ADO_ID, exec_status="running")

    payload = _default_payload()
    payload["html_output_path"] = f"Agentes/outputs/{_TEST_ADO_ID}/NO_EXISTE.html"

    r = client.post(
        _gateway_url(),
        json=payload,
        headers=_SHADOW_HEADERS,
    )
    assert r.status_code == 200, r.data
    data = r.get_json()
    assert data["mode"] == "shadow"
    assert data["would_succeed"] is False
    error_codes = [e["error"]["code"] for e in data["errors"]]
    assert "html_invalid" in error_codes
    # El plan debe tener validate_html con skipped=True
    validate_step = next(
        (s for s in data["plan"] if s["step"] == "validate_html"), None
    )
    assert validate_step is not None
    assert validate_step.get("skipped") is True


# ═══════════════════════════════════════════════════════════════════════════════
# U09 — Sin token → 401 auth_required
# ═══════════════════════════════════════════════════════════════════════════════


def test_gateway_auth_required_returns_401(client):
    """Sin X-Stacky-Agent-Token → 401."""
    _mk_ticket_and_exec(ado_id=_TEST_ADO_ID, exec_status="running")

    r = client.post(
        _gateway_url(),
        json=_default_payload(),
        headers={"Content-Type": "application/json"},  # sin token
    )
    assert r.status_code == 401, r.data
    data = r.get_json()
    assert data["ok"] is False
    assert data["error"]["code"] == "auth_required"


def test_gateway_wrong_token_returns_401(client):
    """Token incorrecto → 401."""
    _mk_ticket_and_exec(ado_id=_TEST_ADO_ID, exec_status="running")

    r = client.post(
        _gateway_url(),
        json=_default_payload(),
        headers={
            "X-Stacky-Agent-Token": "token-equivocado",
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 401, r.data
    data = r.get_json()
    assert data["error"]["code"] == "auth_required"


# ═══════════════════════════════════════════════════════════════════════════════
# U10 — Payload inválido → 400 payload_invalid
# ═══════════════════════════════════════════════════════════════════════════════


def test_gateway_payload_invalid_returns_400_missing_agent_type(client):
    """Sin agent_type → 400 payload_invalid."""
    _mk_ticket_and_exec(ado_id=_TEST_ADO_ID, exec_status="running")

    payload = {"status": "completed"}  # sin agent_type

    r = client.post(
        _gateway_url(),
        json=payload,
        headers=_SHADOW_HEADERS,
    )
    assert r.status_code == 400, r.data
    data = r.get_json()
    assert data["error"]["code"] == "payload_invalid"


def test_gateway_payload_invalid_returns_400_bad_status(client):
    """status no terminal válido → 400 payload_invalid."""
    _mk_ticket_and_exec(ado_id=_TEST_ADO_ID, exec_status="running")

    payload = {
        "agent_type": "functional",
        "status": "running",  # no es estado terminal aceptable
    }

    r = client.post(
        _gateway_url(),
        json=payload,
        headers=_SHADOW_HEADERS,
    )
    assert r.status_code == 400, r.data
    data = r.get_json()
    assert data["error"]["code"] == "payload_invalid"


def test_gateway_payload_invalid_returns_400_empty_body(client):
    """Body vacío → 400 payload_invalid."""
    r = client.post(
        _gateway_url(),
        data="",
        headers=_SHADOW_HEADERS,
    )
    assert r.status_code == 400, r.data


# ═══════════════════════════════════════════════════════════════════════════════
# U11 — Shadow detecta discrepancia con legacy y la registra en SystemLog
# ═══════════════════════════════════════════════════════════════════════════════


def test_gateway_shadow_logs_discrepancy_when_legacy_diverges(client):
    """Si legacy reporta un status distinto al que el gateway daría, debe loguear discrepancia."""
    _mk_ticket_and_exec(ado_id=_TEST_ADO_ID, exec_status="running")

    # Legacy dice que ya marcó el ticket como 'error', pero el payload dice 'completed'
    legacy_observed = {
        "ok": True,
        "current_status": "error",   # diverge del payload.status='completed'
    }

    r = client.post(
        _gateway_url(),
        json=_default_payload(include_legacy=legacy_observed),
        headers=_SHADOW_HEADERS,
    )
    assert r.status_code == 200, r.data
    data = r.get_json()
    assert data["mode"] == "shadow"
    assert len(data["discrepancies"]) > 0, (
        "Se esperaba al menos una discrepancia entre gateway y legacy"
    )
    disc_fields = [d["field"] for d in data["discrepancies"]]
    assert "stacky_status" in disc_fields

    # Esperar flush del logger antes de leer system_logs
    _flush_syslogger()

    # Verificar SystemLog con action=shadow.discrepancy_detected
    from db import session_scope
    from models import SystemLog
    with session_scope() as s:
        disc_log = s.query(SystemLog).filter(
            SystemLog.source == "completion_gateway",
            SystemLog.action == "shadow.discrepancy_detected",
        ).first()
        assert disc_log is not None, "No se generó SystemLog de discrepancia"
        ctx = json.loads(disc_log.context_json)
        assert "divergence_fields" in ctx
        assert any(d["field"] == "stacky_status" for d in ctx["divergence_fields"])


# ═══════════════════════════════════════════════════════════════════════════════
# I01 — Integración: shadow end-to-end sin ninguna escritura en tablas de negocio
# ═══════════════════════════════════════════════════════════════════════════════


def test_integration_shadow_no_writes_end_to_end(client):
    """
    Flujo completo en shadow con un agente fake:
      - Crear ticket + execution activa
      - Llamar al gateway shadow
      - Verificar:
        * AgentExecution.status NO cambió
        * AgentHtmlPublish NO fue insertado
        * Ticket.stacky_status NO cambió
        * SystemLog(source='completion_gateway') SÍ fue generado con el plan
    """
    ticket_id, exec_id = _mk_ticket_and_exec(
        ado_id=_TEST_ADO_ID, agent_type="functional", exec_status="running"
    )

    from db import session_scope
    from models import AgentExecution, Ticket
    from services.ado_publisher import AgentHtmlPublish

    # Estado pre-llamada
    with session_scope() as s:
        exec_pre = s.get(AgentExecution, exec_id)
        ticket_pre = s.query(Ticket).filter(Ticket.ado_id == _TEST_ADO_ID).first()
        publish_count_pre = s.query(AgentHtmlPublish).filter(
            AgentHtmlPublish.execution_id == exec_id
        ).count()

    r = client.post(
        _gateway_url(),
        json=_default_payload(execution_id=exec_id, agent_type="functional"),
        headers=_SHADOW_HEADERS,
    )
    assert r.status_code == 200, r.data
    data = r.get_json()
    assert data["mode"] == "shadow"
    assert data["ok"] is True
    assert data["would_succeed"] is True
    assert data["execution_id"] == exec_id

    # Plan debe tener todos los pasos definidos
    step_names = {s["step"] for s in data["plan"]}
    expected_steps = {
        "resolve_execution",
        "validate_html",
        "close_execution",
        "ado_publish",
        "ticket_status_transition",
        "audit_seal",
    }
    assert expected_steps == step_names, (
        f"Pasos faltantes en el plan: {expected_steps - step_names}"
    )

    # Verificar que los pasos no están marcados como skipped (happy path)
    for step in data["plan"]:
        assert not step.get("skipped"), (
            f"Paso '{step['step']}' está marcado como skipped en happy path"
        )

    # Estado post-llamada — NADA debe haber cambiado en tablas de negocio
    with session_scope() as s:
        exec_post = s.get(AgentExecution, exec_id)
        ticket_post = s.query(Ticket).filter(Ticket.ado_id == _TEST_ADO_ID).first()
        publish_count_post = s.query(AgentHtmlPublish).filter(
            AgentHtmlPublish.execution_id == exec_id
        ).count()

        assert exec_post.status == exec_pre.status, (
            f"AgentExecution.status cambió: {exec_pre.status} → {exec_post.status}"
        )
        assert exec_post.completed_at == exec_pre.completed_at, (
            "AgentExecution.completed_at fue modificado"
        )
        assert ticket_post.stacky_status == ticket_pre.stacky_status, (
            f"Ticket.stacky_status cambió: {ticket_pre.stacky_status} → {ticket_post.stacky_status}"
        )
        assert publish_count_post == publish_count_pre, (
            f"AgentHtmlPublish count cambió: {publish_count_pre} → {publish_count_post}"
        )

    # Esperar flush del logger antes de leer system_logs
    _flush_syslogger()

    # SystemLog debe existir con el plan
    from models import SystemLog
    with session_scope() as s:
        logs = s.query(SystemLog).filter(
            SystemLog.source == "completion_gateway",
            SystemLog.action == "shadow.invocation",
        ).all()
        assert len(logs) >= 1, "No se generó SystemLog de shadow invocation"
        last_log = logs[-1]
        ctx = json.loads(last_log.context_json)
        assert ctx.get("mode") == "shadow"
        assert ctx.get("would_succeed") is True
        assert "plan_steps" in ctx
        assert set(ctx["plan_steps"]) == expected_steps


# ═══════════════════════════════════════════════════════════════════════════════
# I02 — Integración: shadow paralelo al legacy detecta coincidencia
# ═══════════════════════════════════════════════════════════════════════════════


def test_integration_shadow_parallel_with_legacy_logs_coincidence(client):
    """
    Simula doble llamada: primero al legacy (PATCH stacky-status),
    luego al gateway con _legacy_observed incluyendo el resultado del legacy.
    Cuando hay coincidencia (mismo status), discrepancies debe estar vacío.
    """
    ticket_id, exec_id = _mk_ticket_and_exec(
        ado_id=_TEST_ADO_ID, agent_type="functional", exec_status="running"
    )

    # El legacy responde que marcó completed (mismo que el payload del gateway)
    legacy_observed = {
        "ok": True,
        "current_status": "completed",  # coincide con payload.status
    }

    r = client.post(
        _gateway_url(),
        json=_default_payload(
            execution_id=exec_id,
            status="completed",
            include_legacy=legacy_observed,
        ),
        headers=_SHADOW_HEADERS,
    )
    assert r.status_code == 200, r.data
    data = r.get_json()
    assert data["mode"] == "shadow"
    assert data["would_succeed"] is True
    # Sin divergencia cuando legacy y gateway coinciden
    assert data["discrepancies"] == [], (
        f"No debe haber discrepancias cuando legacy y gateway coinciden: {data['discrepancies']}"
    )

    # Esperar flush del logger antes de leer system_logs
    _flush_syslogger()

    # No debe existir log de discrepancia
    from db import session_scope
    from models import SystemLog
    with session_scope() as s:
        disc_log = s.query(SystemLog).filter(
            SystemLog.source == "completion_gateway",
            SystemLog.action == "shadow.discrepancy_detected",
        ).first()
        assert disc_log is None, "No debe haber log de discrepancia cuando hay coincidencia"


# ═══════════════════════════════════════════════════════════════════════════════
# Tests adicionales de cobertura
# ═══════════════════════════════════════════════════════════════════════════════


def test_gateway_ticket_not_found_returns_404(client):
    """Ticket ADO inexistente → 404 ticket_not_found.

    El gateway retorna 404 con GatewayResult format (errors lista).
    """
    r = client.post(
        "/api/tickets/by-ado/99999/agent-completion",  # ID que no existe
        json=_default_payload(),
        headers=_SHADOW_HEADERS,
    )
    assert r.status_code == 404, r.data
    data = r.get_json()
    # En modo shadow 404, la respuesta tiene GatewayResult.to_dict() format
    # con errors como lista de {"error": {"code": ..., "message": ...}}
    assert data["ok"] is False
    error_codes = [e["error"]["code"] for e in data.get("errors", [])]
    assert "ticket_not_found" in error_codes


def test_gateway_shadow_logs_metric_on_invocation(client):
    """Cada invocación shadow debe generar un SystemLog de métrica."""
    _mk_ticket_and_exec(ado_id=_TEST_ADO_ID, exec_status="running")

    r = client.post(
        _gateway_url(),
        json=_default_payload(),
        headers=_SHADOW_HEADERS,
    )
    assert r.status_code == 200

    # Esperar flush del logger antes de leer system_logs
    _flush_syslogger()

    from db import session_scope
    from models import SystemLog
    with session_scope() as s:
        metric_log = s.query(SystemLog).filter(
            SystemLog.source == "completion_gateway",
            SystemLog.action == "metric.completion_gateway",
        ).first()
        assert metric_log is not None, "No se generó SystemLog de métrica"
        ctx = json.loads(metric_log.context_json)
        assert ctx.get("metric") == "stacky_agent_completion_total"
        assert ctx.get("mode") == "shadow"


def test_gateway_shadow_returns_correlation_id(client):
    """La respuesta shadow debe incluir correlation_id."""
    _mk_ticket_and_exec(ado_id=_TEST_ADO_ID, exec_status="running")

    r = client.post(
        _gateway_url(),
        json=_default_payload(),
        headers=_SHADOW_HEADERS,
    )
    data = r.get_json()
    assert "correlation_id" in data
    assert len(data["correlation_id"]) == 36, "correlation_id debe ser UUID"


def test_gateway_shadow_returns_duration_ms(client):
    """La respuesta shadow debe incluir duration_ms."""
    _mk_ticket_and_exec(ado_id=_TEST_ADO_ID, exec_status="running")

    r = client.post(
        _gateway_url(),
        json=_default_payload(),
        headers=_SHADOW_HEADERS,
    )
    data = r.get_json()
    assert "duration_ms" in data
    assert isinstance(data["duration_ms"], int)
    assert data["duration_ms"] >= 0


def test_gateway_multiple_active_executions_returns_no_active(client):
    """Múltiples activas sin execution_id explícito → error de ambigüedad."""
    from db import session_scope
    from models import Ticket, AgentExecution

    # Crear ticket con 2 executions activas
    with session_scope() as s:
        t = Ticket(
            ado_id=_TEST_ADO_ID,
            project="RSPacifico",
            title="Ticket con 2 activas",
            ado_state="Active",
            stacky_status="running",
        )
        s.add(t)
        s.flush()
        for agent_type in ["functional", "developer"]:
            e = AgentExecution(
                ticket_id=t.id,
                agent_type=agent_type,
                status="running",
                input_context_json="[]",
                started_by="test",
                started_at=datetime.utcnow(),
            )
            s.add(e)

    r = client.post(
        _gateway_url(),
        json=_default_payload(agent_type="technical"),  # no coincide con ninguna
        headers=_SHADOW_HEADERS,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["would_succeed"] is False
    error_codes = [e["error"]["code"] for e in data["errors"]]
    assert "no_active_execution" in error_codes
