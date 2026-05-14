"""
test_rescue_execution.py — Regresión P0: scripts/rescue_execution.py

Cubre el plan §9.4 del PLAN_CIERRE_PUBLICACION_AGENTES.md:
  - Fixture ADO-149: execution 44 en 'running', HTML válido en disco, ticket 149.
  - Test dry-run: verifica plan generado sin escribir en DB ni ADO.
  - Test apply con mock ADO: verifica que:
    · execution cierra (status='completed')
    · AgentHtmlPublish se inserta UNA VEZ (idempotente al reintentar)
    · SystemLog con kind='rescue' queda registrado
    · on_execution_end actualiza stacky_status del ticket

Nota: los tests de apply usan un AdoClient mock (client_factory) para no
tocar ADO real. El rescate real de ADO-149 requiere --apply con ADO real,
que el operador autoriza explícitamente tras revisar el dry-run.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── Bootstrap ─────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["LLM_BACKEND"] = "mock"
# Apuntar repo root a un directorio temporal controlado por los tests
# (se sobreescribe por fixture)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_db():
    """Inicializa la DB in-memory para cada test."""
    from db import init_db, engine, Base
    Base.metadata.drop_all(engine)
    init_db()
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def html_dir(tmp_path: Path, monkeypatch):
    """
    Crea un directorio temporal que simula <repo_root>/Agentes/outputs/149/
    con un comment.html válido y apunta STACKY_REPO_ROOT a tmp_path.
    """
    outputs = tmp_path / "Agentes" / "outputs" / "149"
    outputs.mkdir(parents=True)
    html_file = outputs / "comment.html"
    html_file.write_text(
        "<h2>ANÁLISIS TÉCNICO — ADO-149</h2>"
        "<p>plan de pruebas técnico</p>"
        "<p>ADO-149 — alcance de cambios</p>"
        "<p>traducción funcional</p>"
        "<p>tests unitarios</p>"
        "<p>notas para el desarrollador</p>"
        " " * 400,  # padding para superar min_word_count del contrato técnico
        encoding="utf-8",
    )
    monkeypatch.setenv("STACKY_REPO_ROOT", str(tmp_path))
    return html_file


@pytest.fixture
def ticket_149(html_dir):
    """Inserta Ticket con ado_id=149 en DB."""
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=149,
            project="PACIFICO",
            title="RF-014 Ordenamiento Teléfonos por Efectividad",
            ado_state="Active",
            stacky_status="running",
        )
        session.add(t)
        session.flush()
        ticket_id = t.id

    return ticket_id


@pytest.fixture
def execution_44(ticket_149):
    """
    Inserta AgentExecution simulando la exec 44 en estado 'running'
    (el escenario real de ADO-149).
    """
    from db import session_scope
    from models import AgentExecution

    with session_scope() as session:
        exec_row = AgentExecution(
            id=44,
            ticket_id=ticket_149,
            agent_type="technical",
            status="running",
            input_context_json="[]",
            started_by="agent@stacky",
            started_at=datetime(2026, 5, 14, 8, 0, 0),
        )
        session.add(exec_row)

    return 44


# ── Tests: dry-run ────────────────────────────────────────────────────────────


class TestDryRun:
    def test_dry_run_generates_full_plan(self, execution_44, html_dir):
        """dry-run sobre execution 44 / ADO-149 produce plan de 7 pasos coherente."""
        from scripts.rescue_execution import run_dry_run

        result = run_dry_run(
            ado_id=149,
            execution_id=44,
            html_path=str(html_dir),
            reason="Test dry-run EP-013",
            user_email="test@stacky",
            correlation_id="test-corr-001",
        )

        assert result["ok"] is True, f"dry-run falló: {result}"
        assert result["mode"] == "dry_run"
        assert result["ado_id"] == 149
        assert result["execution_id"] == 44
        assert result["ticket_id"] is not None
        assert result["agent_type"] == "technical"
        assert result["html_sha256"]  # sha256 no vacío

        # Plan tiene exactamente 7 pasos
        plan = result["plan"]
        assert len(plan) == 7, f"Se esperaban 7 pasos, se obtuvo {len(plan)}"

        steps_by_name = {s["name"]: s for s in plan}
        assert "validate_html" in steps_by_name
        assert "load_and_lock_execution" in steps_by_name
        assert "persist_html_output_path" in steps_by_name
        assert "close_execution" in steps_by_name
        assert "publish_from_execution" in steps_by_name
        assert "on_execution_end" in steps_by_name
        assert "audit_event" in steps_by_name

        # Paso 1 (validate_html) debe reportar HTML ok
        assert steps_by_name["validate_html"]["result"]["ok"] is True

        # Paso 2 (load) confirma estado running
        load_res = steps_by_name["load_and_lock_execution"]["result"]
        assert load_res["ok"] is True
        assert load_res["current_status"] == "running"

        # Paso 5 (publish) incluye sha256
        pub_step = steps_by_name["publish_from_execution"]
        assert pub_step["html_sha256"] == result["html_sha256"]

    def test_dry_run_blocked_html_not_found(self, ticket_149, tmp_path, monkeypatch):
        """dry-run se bloquea en step 1 si el HTML no existe.

        Nota: no usa execution_44 (que depende de html_dir y crearía el HTML).
        Crea su propia execution en una carpeta tmp sin HTML.
        """
        # tmp_path limpio sin HTML — solo crear el directorio vacío
        empty_repo = tmp_path / "empty_repo"
        empty_repo.mkdir()
        (empty_repo / "Agentes" / "outputs" / "149").mkdir(parents=True)
        monkeypatch.setenv("STACKY_REPO_ROOT", str(empty_repo))

        # Insertar execution propia (no usa el fixture execution_44)
        from db import session_scope
        from models import AgentExecution

        with session_scope() as session:
            exec_row = AgentExecution(
                id=77,
                ticket_id=ticket_149,
                agent_type="technical",
                status="running",
                input_context_json="[]",
                started_by="agent@stacky",
                started_at=datetime(2026, 5, 14, 8, 0, 0),
            )
            session.add(exec_row)

        from scripts.rescue_execution import run_dry_run

        result = run_dry_run(
            ado_id=149,
            execution_id=77,
            html_path="",
            reason="Test sin HTML",
            user_email="test@stacky",
            correlation_id="test-corr-002",
        )

        assert result["ok"] is False
        assert result["blocked_at_step"] == 1
        assert result["error"]["code"] == "NOT_FOUND"

    def test_dry_run_blocked_execution_not_running(self, ticket_149, html_dir):
        """dry-run se bloquea en step 2 si la ejecución ya está completed."""
        from db import session_scope
        from models import AgentExecution

        with session_scope() as session:
            exec_row = AgentExecution(
                id=99,
                ticket_id=ticket_149,
                agent_type="technical",
                status="completed",  # ya cerrada
                input_context_json="[]",
                started_by="agent@stacky",
                started_at=datetime(2026, 5, 14, 9, 0, 0),
                completed_at=datetime(2026, 5, 14, 10, 0, 0),
            )
            session.add(exec_row)

        from scripts.rescue_execution import run_dry_run

        result = run_dry_run(
            ado_id=149,
            execution_id=99,
            html_path=str(html_dir),
            reason="Test exec ya cerrada",
            user_email="test@stacky",
            correlation_id="test-corr-003",
        )

        assert result["ok"] is False
        assert result["blocked_at_step"] == 2
        assert result["error"]["code"] == "EXECUTION_STATE_INVALID"

    def test_dry_run_blocked_ado_mismatch(self, ticket_149, html_dir):
        """dry-run se bloquea si la ejecución pertenece a otro ADO ticket."""
        from db import session_scope
        from models import AgentExecution, Ticket

        # Crear otro ticket
        with session_scope() as session:
            other = Ticket(
                ado_id=999,
                project="PACIFICO",
                title="Otro ticket",
                stacky_status="running",
            )
            session.add(other)
            session.flush()
            other_id = other.id

        with session_scope() as session:
            exec_row = AgentExecution(
                id=88,
                ticket_id=other_id,
                agent_type="technical",
                status="running",
                input_context_json="[]",
                started_by="agent@stacky",
                started_at=datetime(2026, 5, 14, 9, 0, 0),
            )
            session.add(exec_row)

        from scripts.rescue_execution import run_dry_run

        result = run_dry_run(
            ado_id=149,  # exec 88 pertenece a ADO-999, no 149
            execution_id=88,
            html_path=str(html_dir),
            reason="Test mismatch",
            user_email="test@stacky",
            correlation_id="test-corr-004",
        )

        assert result["ok"] is False
        assert result["error"]["code"] == "EXECUTION_ADO_MISMATCH"


# ── Tests: apply con ADO mock ─────────────────────────────────────────────────


class TestApply:
    def _make_ado_mock(self):
        """Crea un mock de AdoClient que simula post_comment exitoso."""
        mock_client = MagicMock()
        mock_client.post_comment.return_value = {
            "id": 12345,
            "text": "mock comment posted",
        }
        return lambda: mock_client

    def test_apply_closes_execution_and_publishes(self, execution_44, html_dir, monkeypatch):
        """
        apply sobre execution 44 / ADO-149:
        - Execution queda status='completed'
        - AgentHtmlPublish se inserta (status='ok')
        - SystemLog con action='rescue.completed' queda registrado
        - stacky_status del ticket queda 'completed'
        """
        # Inyectar ADO mock para evitar llamada real
        mock_factory = self._make_ado_mock()
        monkeypatch.setattr(
            "services.ado_publisher._default_client",
            mock_factory,
        )

        from scripts.rescue_execution import run_apply

        result = run_apply(
            ado_id=149,
            execution_id=44,
            html_path=str(html_dir),
            reason="Rescate test EP-013",
            user_email="test@stacky",
            correlation_id="test-apply-001",
            confirmed_via_stdin=True,
        )

        assert result["ok"] is True, f"apply falló: {json.dumps(result, indent=2)}"
        assert result["mode"] == "apply"
        assert result["execution_id"] == 44
        assert result["execution_status_now"] == "completed"
        assert result["completion_source"] == "rescue"

        # Verificar en DB que la ejecución quedó cerrada
        from db import session_scope
        from models import AgentExecution, Ticket

        with session_scope() as session:
            exec_row = session.get(AgentExecution, 44)
            assert exec_row is not None
            assert exec_row.status == "completed"
            assert exec_row.completed_at is not None
            assert exec_row.html_output_path == str(html_dir)

            # Ticket debe haber transicionado a 'completed'
            ticket = session.get(Ticket, exec_row.ticket_id)
            assert ticket.stacky_status == "completed"

        # Verificar AgentHtmlPublish insertado
        from services.ado_publisher import AgentHtmlPublish

        with session_scope() as session:
            pub_row = (
                session.query(AgentHtmlPublish)
                .filter(AgentHtmlPublish.execution_id == 44)
                .first()
            )
            assert pub_row is not None, "AgentHtmlPublish no se insertó"
            assert pub_row.status == "ok"
            assert pub_row.triggered_by == "rescue"

        # Verificar SystemLog con rescue
        from models import SystemLog

        with session_scope() as session:
            rescue_log = (
                session.query(SystemLog)
                .filter(
                    SystemLog.source == "rescue_execution",
                    SystemLog.action == "rescue.completed",
                )
                .first()
            )
            assert rescue_log is not None, "SystemLog de rescate no se insertó"
            assert rescue_log.execution_id == 44
            assert rescue_log.user == "test@stacky"
            ctx = json.loads(rescue_log.context_json)
            assert ctx["kind"] == "rescue"

    def test_apply_idempotent_no_double_publish(self, execution_44, html_dir, monkeypatch):
        """
        Reintentar apply con la misma (execution_id, html_sha256) no duplica
        AgentHtmlPublish ni republica en ADO.
        """
        mock_factory = self._make_ado_mock()
        monkeypatch.setattr(
            "services.ado_publisher._default_client",
            mock_factory,
        )

        from scripts.rescue_execution import run_apply

        # Primera ejecución (cierra exec, publica)
        result1 = run_apply(
            ado_id=149,
            execution_id=44,
            html_path=str(html_dir),
            reason="Primera vez",
            user_email="test@stacky",
            correlation_id="test-idempotent-001",
            confirmed_via_stdin=True,
        )
        assert result1["ok"] is True

        # Re-abrir la ejecución para simular segundo intento
        from db import session_scope
        from models import AgentExecution

        with session_scope() as session:
            exec_row = session.get(AgentExecution, 44)
            exec_row.status = "running"  # forzar para simular reintento
            exec_row.completed_at = None

        # Segunda ejecución
        result2 = run_apply(
            ado_id=149,
            execution_id=44,
            html_path=str(html_dir),
            reason="Segunda vez (reintento)",
            user_email="test@stacky",
            correlation_id="test-idempotent-002",
            confirmed_via_stdin=True,
        )
        assert result2["ok"] is True

        # Verificar que post_comment no se llamó dos veces (dedupe)
        from services.ado_publisher import AgentHtmlPublish

        with session_scope() as session:
            pub_rows = (
                session.query(AgentHtmlPublish)
                .filter(
                    AgentHtmlPublish.execution_id == 44,
                    AgentHtmlPublish.status == "ok",
                )
                .all()
            )
            # Debe haber exactamente 1 registro ok (el segundo fue skipped)
            assert len(pub_rows) == 1, (
                f"Se esperaba 1 AgentHtmlPublish ok, se encontraron {len(pub_rows)}"
            )

        # post_comment solo se llamó una vez
        called = mock_factory().post_comment.call_count
        assert called == 1, f"post_comment se llamó {called} veces (se esperaba 1)"

    def test_apply_fails_if_execution_already_completed(
        self, ticket_149, html_dir, monkeypatch
    ):
        """
        apply falla con EXECUTION_STATE_INVALID si la ejecución ya está 'completed'
        (sin haberla reabierto artificialmente).
        """
        from db import session_scope
        from models import AgentExecution

        with session_scope() as session:
            exec_row = AgentExecution(
                id=55,
                ticket_id=ticket_149,
                agent_type="technical",
                status="completed",
                input_context_json="[]",
                started_by="agent@stacky",
                started_at=datetime(2026, 5, 14, 8, 0, 0),
                completed_at=datetime(2026, 5, 14, 9, 0, 0),
            )
            session.add(exec_row)

        from scripts.rescue_execution import run_apply

        result = run_apply(
            ado_id=149,
            execution_id=55,
            html_path=str(html_dir),
            reason="Test exec ya cerrada",
            user_email="test@stacky",
            correlation_id="test-state-check-001",
            confirmed_via_stdin=True,
        )

        assert result["ok"] is False
        assert result["error"]["code"] == "EXECUTION_STATE_INVALID"

    def test_apply_registers_audit_event_with_user_email(
        self, execution_44, html_dir, monkeypatch
    ):
        """El SystemLog de rescate incluye user_email del operador."""
        monkeypatch.setattr(
            "services.ado_publisher._default_client",
            self._make_ado_mock(),
        )

        from scripts.rescue_execution import run_apply

        result = run_apply(
            ado_id=149,
            execution_id=44,
            html_path=str(html_dir),
            reason="Rescate EP-013",
            user_email="juanluca@ubimia.com",
            correlation_id="test-audit-001",
            confirmed_via_stdin=False,  # --yes path
        )

        assert result["ok"] is True
        assert result["user_email"] == "juanluca@ubimia.com"

        from db import session_scope
        from models import SystemLog

        with session_scope() as session:
            log = (
                session.query(SystemLog)
                .filter(SystemLog.action == "rescue.completed")
                .first()
            )
            assert log is not None
            assert log.user == "juanluca@ubimia.com"
            ctx = json.loads(log.context_json)
            assert ctx["confirmed_via_stdin"] is False  # registra que fue via --yes


# ── Tests: main CLI ───────────────────────────────────────────────────────────


class TestCLI:
    def test_main_dry_run_exit_code_0(self, execution_44, html_dir, capsys):
        """main() con --dry-run retorna exit code 0 y JSON válido."""
        from scripts.rescue_execution import main

        exit_code = main([
            "--ado-id", "149",
            "--execution-id", "44",
            "--html-path", str(html_dir),
            "--reason", "CLI test dry-run",
            "--dry-run",
        ])

        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["ok"] is True
        assert data["mode"] == "dry_run"

    def test_main_dry_blocked_exit_code_1(self, ticket_149, tmp_path, monkeypatch, capsys):
        """main() con --dry-run y HTML faltante retorna exit code 1."""
        # Usar subdirectorio limpio propio para no colisionar con fixtures previas
        empty_repo = tmp_path / "empty_repo"
        empty_repo.mkdir()
        (empty_repo / "Agentes" / "outputs" / "149").mkdir(parents=True)
        monkeypatch.setenv("STACKY_REPO_ROOT", str(empty_repo))

        from db import session_scope
        from models import AgentExecution

        with session_scope() as session:
            exec_row = AgentExecution(
                id=66,
                ticket_id=ticket_149,
                agent_type="technical",
                status="running",
                input_context_json="[]",
                started_by="agent@stacky",
                started_at=datetime(2026, 5, 14, 8, 0, 0),
            )
            session.add(exec_row)

        from scripts.rescue_execution import main

        exit_code = main([
            "--ado-id", "149",
            "--execution-id", "66",
            "--reason", "Test CLI sin HTML",
            "--dry-run",
        ])

        assert exit_code == 1
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["ok"] is False
        assert data["error"]["code"] == "NOT_FOUND"
