"""Plan 278 F4/F4-bis — run_brief acepta Epic/Issue en los 3 runtimes.

Antes (Plan 52 F0) el autopublish vivia SOLO en el finalizador de
claude_code_cli_runner, asi que run_brief rechazaba con 400
`autopublish_requires_claude_cli` cualquier combo Epic/Issue + runtime distinto
de claude_code_cli. Ese rechazo era correcto: con Copilot o Codex la run gastaba
tokens y NO creaba la epica.

Plan 278 mudo el publicador al post-hook runtime-agnostico
(services/epic_autopublish.py sobre ticket_status.on_execution_end), que los 3
runtimes disparan. Por eso el rechazo por RUNTIME desaparece.

Lo que NO desaparece es el rechazo por FLAG APAGADA (F4-bis): con
STACKY_EPIC_AUTOPUBLISH_BACKEND=false, un run_brief de Epic/Issue terminaria
`completed` sin work item y sin error. Ese falso verde se sigue rechazando,
ahora con `autopublish_disabled`.
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _make_app():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@contextmanager
def _patch_deps(execution_id=99):
    fake_ticket = MagicMock()
    fake_ticket.id = 1

    @contextmanager
    def _fake_scope():
        sess = MagicMock()
        sess.query.return_value.filter_by.return_value.first.return_value = fake_ticket
        yield sess

    import agent_runner as ar
    mock_run_agent = MagicMock(return_value=execution_id)
    with patch("db.session_scope", _fake_scope), \
         patch.object(ar, "run_agent", mock_run_agent):
        yield mock_run_agent


def _post(client, body):
    return client.post(
        "/api/agents/run-brief",
        json={"brief": "texto", **body},
        headers={"X-User-Email": "test@test.com"},
    )


def test_run_brief_epic_codex_no_es_rechazado():
    app = _make_app()
    with app.test_client() as client:
        with _patch_deps() as mock_run_agent:
            resp = _post(client, {"runtime": "codex_cli", "work_item_type": "Epic"})
        assert resp.get_json().get("error") != "autopublish_requires_claude_cli"
        # "no da 400" solo NO prueba que arranco: sin esto el test pasaria con
        # un run_brief que devuelve 500 y el KPI K1 seria falso.
        mock_run_agent.assert_called_once()


def test_run_brief_issue_copilot_no_es_rechazado():
    from config import config
    app = _make_app()
    with patch.object(config, "STACKY_ISSUE_FROM_BRIEF_ENABLED", True):
        with app.test_client() as client:
            with _patch_deps() as mock_run_agent:
                resp = _post(client, {"runtime": "github_copilot", "work_item_type": "Issue"})
            assert resp.get_json().get("error") != "autopublish_requires_claude_cli"
            mock_run_agent.assert_called_once()


def test_run_brief_epic_claude_cli_not_rejected_by_parity_guard():
    app = _make_app()
    with app.test_client() as client:
        with _patch_deps() as mock_run_agent:
            resp = _post(client, {
                "runtime": "claude_code_cli",
                "work_item_type": "Epic",
                "vscode_agent_filename": "BusinessAgent.agent.md",
            })
        # NO debe rechazarse por el guard de paridad. Puede ser 202 (lanzado) o
        # fallar por otra validación, pero el error NUNCA es el de paridad.
        assert resp.get_json().get("error") != "autopublish_requires_claude_cli"


def test_run_brief_epic_default_runtime_copilot_no_es_rechazado():
    # work_item_type por default normaliza a "Epic"; runtime por default es
    # github_copilot. Ese es EXACTAMENTE el combo que el operador toca sin
    # configurar nada, y antes de este plan chocaba contra el 400 de fabrica.
    app = _make_app()
    with app.test_client() as client:
        with _patch_deps() as mock_run_agent:
            resp = _post(client, {})  # sin runtime, sin work_item_type
        assert resp.get_json().get("error") != "autopublish_requires_claude_cli"
        mock_run_agent.assert_called_once()


# ── F4-bis — el 400 no se borra: se reemplaza ────────────────────────────────

def test_run_brief_epic_copilot_rechazado_con_flag_off():
    from config import config
    app = _make_app()
    with patch.object(config, "STACKY_EPIC_AUTOPUBLISH_BACKEND", False):
        with app.test_client() as client:
            with _patch_deps() as mock_run_agent:
                resp = _post(client, {"runtime": "github_copilot", "work_item_type": "Epic"})
            assert resp.status_code == 400
            assert resp.get_json().get("error") == "autopublish_disabled"
            mock_run_agent.assert_not_called()


def test_run_brief_epic_copilot_aceptado_con_flag_on():
    app = _make_app()
    with app.test_client() as client:
        with _patch_deps() as mock_run_agent:
            resp = _post(client, {"runtime": "github_copilot", "work_item_type": "Epic"})
        assert resp.get_json().get("error") != "autopublish_disabled"
        mock_run_agent.assert_called_once()
