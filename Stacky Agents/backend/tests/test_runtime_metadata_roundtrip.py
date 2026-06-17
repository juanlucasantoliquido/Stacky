"""Plan 36 — F4: persistencia de runtime en metadata de la ejecución (los 3 runtimes).

Tests:
1. github_copilot → metadata_dict["runtime"] == "github_copilot"
2. codex_cli → metadata_dict["runtime"] == "codex_cli"
3. claude_code_cli → metadata_dict["runtime"] == "claude_code_cli"
4. claude_code_cli → en ningún punto la metadata dice "github_copilot"

Los tests 2 y 3 ya pasan (runners CLI ya persisten RUNTIME). Los tests 1 y 4 verifican
que el path github_copilot también persiste runtime (corrección F4).
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, call, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Constantes conocidas
RUNTIME_COPILOT = "github_copilot"
RUNTIME_CODEX = "codex_cli"
RUNTIME_CLAUDE = "claude_code_cli"


# ---------------------------------------------------------------------------
# Helper: capturar qué metadata_dict se asignó al exec_row
# ---------------------------------------------------------------------------

def _capture_metadata_from_codex_runner(monkeypatch) -> dict:
    """Llama start_codex_cli_run con mocks y retorna la metadata del exec_row."""
    captured_md: dict = {}

    class FakeRow:
        id = 77
        metadata_dict: dict = {}
        input_context = None
        chain_from = None

        def __setattr__(self, name, value):
            object.__setattr__(self, name, value)
            if name == "metadata_dict":
                captured_md.update(value or {})

    fake_row = FakeRow()

    @contextmanager
    def _fake_scope():
        sess = MagicMock()
        sess.get.return_value = MagicMock(
            title="Test ticket",
            stacky_project_name=None,
            project=None,
        )
        sess.add = MagicMock()
        sess.flush = MagicMock()
        # Al hacer add(exec_row), queremos que sea nuestro fake_row
        sess.add.side_effect = lambda row: None
        yield sess

    import services.codex_cli_runner as cr
    monkeypatch.setattr(cr, "session_scope", _fake_scope)
    monkeypatch.setattr(cr, "log_streamer", MagicMock())
    monkeypatch.setattr(cr, "context_enrichment", MagicMock())
    monkeypatch.setattr(cr, "resolve_project_context", lambda *a, **kw: None)

    # Capturar la metadata_dict inicial del exec_row antes de add
    original_ae = cr.AgentExecution

    class InstrumentedAE(original_ae):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)

        @property
        def metadata_dict(self):
            return self.__dict__.get("_metadata_dict", {})

        @metadata_dict.setter
        def metadata_dict(self, v):
            self.__dict__["_metadata_dict"] = v or {}
            captured_md.clear()
            captured_md.update(self.__dict__["_metadata_dict"])

    monkeypatch.setattr(cr, "AgentExecution", InstrumentedAE)

    # Parchear también threading para no lanzar background
    monkeypatch.setattr("threading.Thread", MagicMock())

    try:
        cr.start_codex_cli_run(
            ticket_id=1,
            agent_type="dev",
            context_blocks=[],
            user="test",
            vscode_agent_filename="Dev.agent.md",
            ticket_message="Test",
            workspace_root=None,
            model_override=None,
        )
    except Exception:
        pass  # Puede fallar después de crear el exec_row — no nos importa

    return captured_md


def _capture_metadata_from_claude_runner(monkeypatch) -> dict:
    """Llama start_claude_code_cli_run con mocks y retorna la metadata del exec_row."""
    captured_md: dict = {}

    import services.claude_code_cli_runner as cr

    original_ae = cr.AgentExecution

    class InstrumentedAE(original_ae):
        @property
        def metadata_dict(self):
            return self.__dict__.get("_metadata_dict", {})

        @metadata_dict.setter
        def metadata_dict(self, v):
            self.__dict__["_metadata_dict"] = v or {}
            captured_md.clear()
            captured_md.update(self.__dict__["_metadata_dict"])

    monkeypatch.setattr(cr, "AgentExecution", InstrumentedAE)

    @contextmanager
    def _fake_scope():
        sess = MagicMock()
        sess.get.return_value = MagicMock(
            title="Test ticket",
            stacky_project_name=None,
            project=None,
        )
        yield sess

    monkeypatch.setattr(cr, "session_scope", _fake_scope)
    monkeypatch.setattr(cr, "log_streamer", MagicMock())
    monkeypatch.setattr(cr, "context_enrichment", MagicMock())
    monkeypatch.setattr(cr, "resolve_project_context", lambda *a, **kw: None)
    monkeypatch.setattr("threading.Thread", MagicMock())

    try:
        cr.start_claude_code_cli_run(
            ticket_id=1,
            agent_type="dev",
            context_blocks=[],
            user="test",
            vscode_agent_filename="Dev.agent.md",
            ticket_message="Test",
            workspace_root=None,
            model_override=None,
        )
    except Exception:
        pass

    return captured_md


def _capture_metadata_from_copilot_runner(monkeypatch) -> dict:
    """Llama agent_runner.run_agent con runtime=github_copilot y captura metadata."""
    captured_md: dict = {}

    import agent_runner as ar
    import agents as agents_mod

    # agents.get("dev") retorna None si los agentes no están registrados → UnknownAgentError
    monkeypatch.setattr(agents_mod, "get", lambda agent_type: MagicMock())

    @contextmanager
    def _fake_scope():
        """Sesión fake que captura el exec_row cuando se hace .add()."""
        sess = MagicMock()
        sess.get.return_value = MagicMock(title="Test", stacky_project_name=None, project=None)

        def _capture_add(row):
            # Capturamos metadata leyendo tanto la property como el JSON subyacente
            try:
                import json as _json
                # Intentar por metadata_json (campo subyacente, siempre disponible)
                raw = getattr(row, "metadata_json", None)
                if raw:
                    parsed = _json.loads(raw) if isinstance(raw, str) else raw
                    captured_md.clear()
                    captured_md.update(parsed or {})
                else:
                    # Fallback: property
                    md = row.metadata_dict
                    captured_md.clear()
                    captured_md.update(md or {})
            except Exception:
                pass

        sess.add.side_effect = _capture_add
        yield sess

    monkeypatch.setattr(ar, "session_scope", _fake_scope)
    monkeypatch.setattr(ar, "log_streamer", MagicMock())
    monkeypatch.setattr(ar, "stacky_logger", MagicMock())
    monkeypatch.setattr(ar, "copilot_bridge", MagicMock())

    # Evitar preflight gate (ambos: flag y el módulo para que el try no llame session_scope)
    import config as cfg_mod
    monkeypatch.setattr(cfg_mod.config, "STACKY_RUN_PREFLIGHT_GATE_ENABLED", False, raising=False)
    import services.run_preflight as rpf
    _pass_result = MagicMock()
    _pass_result.ok = True
    monkeypatch.setattr(rpf, "check", lambda *a, **kw: _pass_result)

    # Evitar auto-asignación
    import services.ticket_assigner as ta
    monkeypatch.setattr(ta, "auto_assign_on_run", lambda *a, **kw: None)

    # parchear threading para que el background thread no corra
    monkeypatch.setattr("threading.Thread", MagicMock())

    try:
        ar.run_agent(
            agent_type="dev",
            ticket_id=1,
            context_blocks=[],
            user="test",
            runtime=RUNTIME_COPILOT,
        )
    except Exception:
        pass

    return captured_md


# ---------------------------------------------------------------------------
# Test 1: github_copilot → metadata_dict["runtime"] == "github_copilot"
# ---------------------------------------------------------------------------

def test_copilot_run_records_runtime_metadata(monkeypatch):
    md = _capture_metadata_from_copilot_runner(monkeypatch)
    assert md.get("runtime") == RUNTIME_COPILOT, (
        f"github_copilot runner no persiste runtime en metadata. Metadata: {md}"
    )


# ---------------------------------------------------------------------------
# Test 2: codex_cli → metadata_dict["runtime"] == "codex_cli"
# ---------------------------------------------------------------------------

def test_codex_run_records_runtime_metadata(monkeypatch):
    md = _capture_metadata_from_codex_runner(monkeypatch)
    assert md.get("runtime") == RUNTIME_CODEX, (
        f"codex_cli runner no persiste runtime en metadata. Metadata: {md}"
    )


# ---------------------------------------------------------------------------
# Test 3: claude_code_cli → metadata_dict["runtime"] == "claude_code_cli"
# ---------------------------------------------------------------------------

def test_claude_run_records_runtime_metadata(monkeypatch):
    md = _capture_metadata_from_claude_runner(monkeypatch)
    assert md.get("runtime") == RUNTIME_CLAUDE, (
        f"claude_code_cli runner no persiste runtime en metadata. Metadata: {md}"
    )


# ---------------------------------------------------------------------------
# Test 4: claude_code_cli → metadata nunca dice "github_copilot"
# ---------------------------------------------------------------------------

def test_runtime_never_rewritten(monkeypatch):
    md = _capture_metadata_from_claude_runner(monkeypatch)
    assert md.get("runtime") != RUNTIME_COPILOT, (
        f"claude_code_cli runner registró runtime como 'github_copilot'. Metadata: {md}"
    )
    assert md.get("runtime") == RUNTIME_CLAUDE, (
        f"Se esperaba runtime=claude_code_cli pero fue: {md.get('runtime')}"
    )
