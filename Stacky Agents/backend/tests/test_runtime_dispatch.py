"""
Tests de runtime dispatch (AL-01 / Fase 0 — Preflight runtime).

Cubren el endpoint POST /api/agents/run para los casos:
  - runtime=codex_cli con vscode_agent_filename válido → delega a start_codex_cli_run
  - runtime=codex_cli sin vscode_agent_filename → HTTP 400 missing_vscode_agent_filename
  - runtime=claude_code_cli → HTTP 501 not_implemented
  - runtime=foo (desconocido) → HTTP 400 unknown_runtime
  - runtime=github_copilot → path existente intacto (smoke)
  - runtime ausente → path existente intacto (smoke, retrocompat)

Layer: api_contract
Priority: P0

NOTA DE EJECUCIÓN:
Correr este módulo en aislamiento (recomendado):
    pytest tests/test_runtime_dispatch.py -v

Correr junto con test_smoke.py puede causar segfault en Windows debido a threads
daemon del runner github_copilot que acceden a SQLite in-memory después que pytest
cierra el proceso. Esto es un problema pre-existente del test suite, no de este PR.
"""
from __future__ import annotations

import itertools
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

# Contador global para ado_id únicos por test (evita UNIQUE constraint failures
# cuando la DB in-memory sobrevive entre fixtures del mismo proceso pytest).
_ADO_ID_COUNTER = itertools.count(80010)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """Flask test client único por módulo — reutiliza la misma DB in-memory."""
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


@pytest.fixture
def ticket_id():
    """Crea un ticket real en la DB in-memory y devuelve su id."""
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        t = Ticket(
            ado_id=next(_ADO_ID_COUNTER),
            project="RSPacifico",
            title="AL-01 test ticket",
            ado_state="Active",
        )
        session.add(t)
        session.flush()
        return t.id


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _base_payload(ticket_id: int, **extra) -> dict:
    return {
        "agent_type": "functional",
        "ticket_id": ticket_id,
        "context_blocks": [
            {"id": "b1", "kind": "editable", "title": "Notas", "content": "test"}
        ],
        **extra,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Test AL-01-1: runtime=codex_cli con vscode_agent_filename → llama a start_codex_cli_run
# ──────────────────────────────────────────────────────────────────────────────

def test_codex_cli_valid_dispatches_to_runner(client, ticket_id):
    """
    runtime=codex_cli + vscode_agent_filename presente → el endpoint
    llama agent_runner.run_agent con runtime=codex_cli y este delega a
    services.codex_cli_runner.start_codex_cli_run.
    No se cae a github_copilot.
    """
    fake_exec_id = 42

    # Monkeypatch start_codex_cli_run para no lanzar subprocess real.
    with patch(
        "services.codex_cli_runner.start_codex_cli_run",
        return_value=fake_exec_id,
    ) as mock_start:
        r = client.post(
            "/api/agents/run",
            json=_base_payload(
                ticket_id,
                runtime="codex_cli",
                vscode_agent_filename="DevPacifico.agent.md",
            ),
        )

    assert r.status_code == 202, f"Esperado 202, got {r.status_code}: {r.data}"
    data = r.get_json()
    assert data["runtime"] == "codex_cli"
    assert data["execution_id"] == fake_exec_id

    # Confirmar que start_codex_cli_run fue llamado exactamente una vez
    # con los parámetros correctos.
    mock_start.assert_called_once()
    call_kwargs = mock_start.call_args.kwargs
    assert call_kwargs["vscode_agent_filename"] == "DevPacifico.agent.md"
    assert call_kwargs["ticket_id"] == ticket_id
    assert call_kwargs["agent_type"] == "functional"


# ──────────────────────────────────────────────────────────────────────────────
# Test AL-01-2: runtime=codex_cli sin vscode_agent_filename → HTTP 400
# ──────────────────────────────────────────────────────────────────────────────

def test_codex_cli_missing_filename_returns_400(client, ticket_id):
    """
    runtime=codex_cli sin vscode_agent_filename → HTTP 400
    con error=missing_vscode_agent_filename.
    No hay fallback silencioso a github_copilot.
    """
    r = client.post(
        "/api/agents/run",
        json=_base_payload(ticket_id, runtime="codex_cli"),
    )

    assert r.status_code == 400, f"Esperado 400, got {r.status_code}: {r.data}"
    data = r.get_json()
    assert data["ok"] is False
    assert data["error"] == "missing_vscode_agent_filename"
    assert "vscode_agent_filename" in data["message"].lower()


def test_codex_cli_empty_filename_returns_400(client, ticket_id):
    """vscode_agent_filename presente pero vacío/null también debe dar 400."""
    for bad_val in ("", None):
        r = client.post(
            "/api/agents/run",
            json=_base_payload(
                ticket_id,
                runtime="codex_cli",
                vscode_agent_filename=bad_val,
            ),
        )
        assert r.status_code == 400, (
            f"vscode_agent_filename={bad_val!r}: esperado 400, got {r.status_code}"
        )
        data = r.get_json()
        assert data["error"] == "missing_vscode_agent_filename", (
            f"Error code incorrecto para vscode_agent_filename={bad_val!r}: {data}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Test AL-01-3: runtime=claude_code_cli → HTTP 501
# ──────────────────────────────────────────────────────────────────────────────

def test_claude_code_cli_returns_501(client, ticket_id):
    """
    runtime=claude_code_cli → HTTP 501 not_implemented.
    No se ejecuta nada, no hay fallback.
    """
    r = client.post(
        "/api/agents/run",
        json=_base_payload(
            ticket_id,
            runtime="claude_code_cli",
            vscode_agent_filename="DevPacifico.agent.md",
        ),
    )

    assert r.status_code == 501, f"Esperado 501, got {r.status_code}: {r.data}"
    data = r.get_json()
    assert data["ok"] is False
    assert data["error"] == "not_implemented"


# ──────────────────────────────────────────────────────────────────────────────
# Test AL-01-4: runtime desconocido → HTTP 400
# ──────────────────────────────────────────────────────────────────────────────

def test_unknown_runtime_returns_400(client, ticket_id):
    """
    runtime con valor no conocido → HTTP 400 unknown_runtime.
    Nunca fue aceptado silenciosamente.
    """
    r = client.post(
        "/api/agents/run",
        json=_base_payload(ticket_id, runtime="foo_runtime"),
    )

    assert r.status_code == 400, f"Esperado 400, got {r.status_code}: {r.data}"
    data = r.get_json()
    assert data["ok"] is False
    assert data["error"] == "unknown_runtime"


def test_unknown_runtime_bar_returns_400(client, ticket_id):
    """Segundo valor desconocido para confirmar que la regla es genérica."""
    r = client.post(
        "/api/agents/run",
        json=_base_payload(ticket_id, runtime="openai_api"),
    )
    assert r.status_code == 400
    assert r.get_json()["error"] == "unknown_runtime"


# ──────────────────────────────────────────────────────────────────────────────
# Test AL-01-5: runtime=github_copilot → path existente intacto (smoke)
# ──────────────────────────────────────────────────────────────────────────────

def test_github_copilot_runtime_works(client, ticket_id):
    """
    runtime=github_copilot → acepta sin tocar el path existente.
    Smoke test: solo verifica 202 y que el execution_id sea un int.
    """
    r = client.post(
        "/api/agents/run",
        json=_base_payload(ticket_id, runtime="github_copilot"),
    )

    assert r.status_code == 202, f"Esperado 202, got {r.status_code}: {r.data}"
    data = r.get_json()
    assert data["runtime"] == "github_copilot"
    assert isinstance(data["execution_id"], int)


def test_runtime_absent_defaults_to_github_copilot(client, ticket_id):
    """
    runtime ausente (campo no enviado) → retrocompat: trata como github_copilot.
    """
    payload = _base_payload(ticket_id)
    # No incluir "runtime" en el payload
    assert "runtime" not in payload

    r = client.post("/api/agents/run", json=payload)

    assert r.status_code == 202, f"Esperado 202, got {r.status_code}: {r.data}"
    data = r.get_json()
    assert data["runtime"] == "github_copilot"


# ──────────────────────────────────────────────────────────────────────────────
# Test AL-01-6: codex_cli dispatch — FileNotFoundError del CLI marca error sin fallback
# ──────────────────────────────────────────────────────────────────────────────

def test_codex_cli_file_not_found_marks_error_no_fallback(client, ticket_id):
    """
    Si start_codex_cli_run lanza FileNotFoundError (CLI no instalado), la
    ejecución debe quedar con status=error. NO debe caer silenciosamente a
    github_copilot. El endpoint devuelve 202 (la ejecución se creó antes del error).

    Nota de implementación: el path de error en codex_cli es síncrono dentro de
    run_agent (no lanza thread adicional), por lo que el status queda en error
    antes de que el endpoint retorne.
    """
    import time

    with patch(
        "services.codex_cli_runner.start_codex_cli_run",
        side_effect=FileNotFoundError("codex not found in PATH"),
    ):
        r = client.post(
            "/api/agents/run",
            json=_base_payload(
                ticket_id,
                runtime="codex_cli",
                vscode_agent_filename="DevPacifico.agent.md",
            ),
        )

    # El endpoint devuelve 202 porque la fila de ejecución se creó antes del error.
    assert r.status_code == 202, f"Esperado 202, got {r.status_code}: {r.data}"
    data = r.get_json()
    execution_id = data["execution_id"]
    assert isinstance(execution_id, int)

    # Leer el status directamente — el path de error es síncrono en codex_cli.
    from db import session_scope
    from models import AgentExecution

    # Espera breve para que la marca síncrona se persista (máx 1s).
    deadline = time.time() + 1.5
    final_status = None
    while time.time() < deadline:
        with session_scope() as session:
            row = session.get(AgentExecution, execution_id)
            final_status = row.status if row else None
        if final_status in ("error", "completed", "cancelled"):
            break
        time.sleep(0.05)

    assert final_status == "error", (
        f"Esperado status=error (sin fallback a github_copilot), got '{final_status}'"
    )
