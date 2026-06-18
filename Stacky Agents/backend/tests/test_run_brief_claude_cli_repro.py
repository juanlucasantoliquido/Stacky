"""Plan 39 B0/B2 — Test de reproducción: run_brief con claude_code_cli no debe dar 500.

B0: confirmar que SIN el fix existe un path que falla.
B2: después del fix, todos los runtimes devuelven 202.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
# Helper: app de prueba con session_scope + Ticket mockeados
# ---------------------------------------------------------------------------

def _make_app():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@contextmanager
def _patch_run_brief_deps(execution_id=99, run_agent_exc=None):
    """Mockea todo lo que run_brief() necesita sin tocar disco ni BD."""
    fake_ticket = MagicMock()
    fake_ticket.id = 1

    @contextmanager
    def _fake_scope():
        sess = MagicMock()
        sess.query.return_value.filter_by.return_value.first.return_value = fake_ticket
        yield sess

    import agent_runner as ar

    if run_agent_exc:
        mock_run_agent = MagicMock(side_effect=run_agent_exc)
    else:
        mock_run_agent = MagicMock(return_value=execution_id)

    with patch("db.session_scope", _fake_scope), \
         patch.object(ar, "run_agent", mock_run_agent):
        yield mock_run_agent


# ---------------------------------------------------------------------------
# B0 — Reproducción: RuntimeError no atrapada da 500 (SIN el fix de B1)
# ---------------------------------------------------------------------------

def test_run_brief_runtime_error_returns_502_not_500():
    """
    Con el fix B1: si run_agent lanza RuntimeError, run_brief() devuelve 502
    con JSON estructurado — nunca 500 genérico.
    """
    app = _make_app()
    with app.test_client() as client:
        with _patch_run_brief_deps(run_agent_exc=RuntimeError("boom")):
            resp = client.post(
                "/api/agents/run-brief",
                json={"brief": "test", "runtime": "claude_code_cli"},
                headers={"X-User-Email": "test@test.com"},
            )
        assert resp.status_code == 502
        data = resp.get_json()
        assert data["error"] == "agent_launch_failed"


# ---------------------------------------------------------------------------
# B2 — Post-fix: todos los runtimes devuelven 202
# ---------------------------------------------------------------------------

def test_run_brief_claude_cli_no_500():
    """Después del fix B1: claude_code_cli → 202 con execution_id."""
    app = _make_app()
    with app.test_client() as client:
        with _patch_run_brief_deps(execution_id=42):
            resp = client.post(
                "/api/agents/run-brief",
                json={"brief": "analizar el sistema", "runtime": "claude_code_cli"},
                headers={"X-User-Email": "test@test.com"},
            )
        assert resp.status_code == 202
        data = resp.get_json()
        assert data["execution_id"] == 42


def test_run_brief_codex_cli_no_regression():
    """codex_cli → 202."""
    app = _make_app()
    with app.test_client() as client:
        with _patch_run_brief_deps(execution_id=43):
            resp = client.post(
                "/api/agents/run-brief",
                json={"brief": "codex test", "runtime": "codex_cli"},
                headers={"X-User-Email": "test@test.com"},
            )
        assert resp.status_code == 202
        data = resp.get_json()
        assert data["execution_id"] == 43


def test_run_brief_copilot_no_regression():
    """github_copilot → 202."""
    app = _make_app()
    with app.test_client() as client:
        with _patch_run_brief_deps(execution_id=44):
            resp = client.post(
                "/api/agents/run-brief",
                json={"brief": "copilot test", "runtime": "github_copilot"},
                headers={"X-User-Email": "test@test.com"},
            )
        assert resp.status_code == 202
        data = resp.get_json()
        assert data["execution_id"] == 44


def test_brief_pool_output_dir_resolves():
    """Ticket con ado_id=-1 no debe causar error en run_brief."""
    app = _make_app()
    with app.test_client() as client:
        with _patch_run_brief_deps(execution_id=45):
            resp = client.post(
                "/api/agents/run-brief",
                json={"brief": "pool test", "runtime": "claude_code_cli", "project": "RSPACIFICO"},
                headers={"X-User-Email": "test@test.com"},
            )
        assert resp.status_code == 202


# ---------------------------------------------------------------------------
# Regresión 2026-06-18 — el constructor REAL de Ticket no debe romper.
#
# Los tests de arriba mockean session_scope + Ticket, así que el constructor
# nunca se ejecuta (falso verde). Este test usa la BD real (sqlite shared-mem)
# y un proyecto nuevo para forzar la rama `pool_ticket is None`, que es donde
# vivía el `TypeError: 'tracker_item_id' is an invalid keyword argument`.
# ---------------------------------------------------------------------------

def test_run_brief_creates_real_pool_ticket_no_500():
    """run_brief() debe crear el Brief Pool Ticket vía el constructor real."""
    from unittest.mock import MagicMock, patch
    import agent_runner as ar

    project = "REGRESION_POOL_2026_06_18"  # único → garantiza pool_ticket is None

    app = _make_app()
    with app.test_client() as client:
        with patch.object(ar, "run_agent", MagicMock(return_value=77)):
            resp = client.post(
                "/api/agents/run-brief",
                json={
                    "brief": "regresion del pool ticket",
                    "runtime": "claude_code_cli",
                    "project": project,
                },
                headers={"X-User-Email": "test@test.com"},
            )

    assert resp.status_code == 202, resp.get_data(as_text=True)
    assert resp.get_json()["execution_id"] == 77

    # El pool ticket debe existir en la BD real con external_id=-1.
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        pool = (
            session.query(Ticket)
            .filter_by(ado_id=-1, project=project)
            .first()
        )
        assert pool is not None
        assert pool.external_id == -1
        assert pool.stacky_project_name == project
