"""H6.3 — Tests del gate suave de evals al importar/guardar un agente.

Verifica:
1. POST /agents/stacky/import dispara evals en thread para el agent_type inferido
2. El guardado NO se bloquea aunque los evals fallen
3. La respuesta incluye `evals_warning` (puede ser null si no hay goldens)
4. Si los evals detectan regresión, `evals_warning` contiene texto descriptivo
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture
def app():
    """Flask test app con DB en memoria."""
    from db import init_db
    from app import create_app

    application = create_app()
    application.config["TESTING"] = True
    init_db()
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def _make_agent_md(tmp_path: Path, name: str, agent_type: str) -> Path:
    """Crea un .agent.md temporal válido."""
    content = f"# {name}\n\nagent_type: {agent_type}\n\nSystem prompt del agente de prueba.\n"
    p = tmp_path / f"{name}.agent.md"
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Tests del gate suave
# ---------------------------------------------------------------------------

def test_import_agent_includes_evals_warning_key(client, tmp_path):
    """POST /agents/stacky/import devuelve evals_warning en la respuesta."""
    agent_file = _make_agent_md(tmp_path, "QA", "qa")

    with patch("services.stacky_agents.import_agent_from_path") as mock_import, \
         patch("evals.eval_gate.run_evals_for_agent_type_async") as mock_eval:

        mock_entry = MagicMock()
        mock_entry.to_manifest_dict.return_value = {
            "filename": "QA.agent.md",
            "agent_type": "qa",
        }
        mock_import.return_value = mock_entry

        resp = client.post("/api/agents/stacky/import", json={
            "source_path": str(agent_file),
        })

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert "evals_warning" in data


def test_import_agent_evals_failure_does_not_block(client, tmp_path):
    """Si el thread de evals lanza excepción, el guardado sigue siendo OK."""
    agent_file = _make_agent_md(tmp_path, "DevTest", "developer")

    with patch("services.stacky_agents.import_agent_from_path") as mock_import, \
         patch("evals.eval_gate.run_evals_for_agent_type_async") as mock_eval:

        mock_entry = MagicMock()
        mock_entry.to_manifest_dict.return_value = {
            "filename": "DevTest.agent.md",
            "agent_type": "developer",
        }
        mock_import.return_value = mock_entry
        # Simular que el eval falla
        mock_eval.side_effect = RuntimeError("eval crashed")

        resp = client.post("/api/agents/stacky/import", json={
            "source_path": str(agent_file),
        })

    # El guardado NO debe bloquearse ni devolver error
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True


def test_eval_gate_run_evals_for_agent_type():
    """run_evals_for_agent_type retorna None si no hay goldens, o string con warning."""
    from evals.eval_gate import run_evals_for_agent_type

    # agent_type sin goldens → None (no hay casos que puedan fallar)
    result = run_evals_for_agent_type("agente_sin_goldens")
    assert result is None

    # agent_type con goldens conocidos → string con resumen
    result = run_evals_for_agent_type("qa")
    # Puede ser None (todo OK) o un string de warning (algún fallo)
    assert result is None or isinstance(result, str)


def test_eval_gate_run_evals_detects_failure():
    """run_evals_for_agent_type retorna warning string cuando algún golden falla."""
    from evals import eval_gate
    from evals.golden_runner import GoldenResult, GoldenCase

    bad_result = GoldenResult(
        case=GoldenCase(name="bad_case", agent_type="qa", output="x", expect={}),
        score=10,
        passed_contract=False,
        ok=False,
        reasons=["score 10 < min_score 90"],
    )

    with patch("evals.eval_gate.golden_runner.run_agent", return_value=[bad_result]):
        warning = eval_gate.run_evals_for_agent_type("qa")

    assert warning is not None
    assert isinstance(warning, str)
    assert "bad_case" in warning or "FAIL" in warning or "qa" in warning


def test_eval_gate_run_evals_no_warning_on_all_ok():
    """run_evals_for_agent_type retorna None cuando todos los goldens pasan."""
    from evals import eval_gate
    from evals.golden_runner import GoldenResult, GoldenCase

    good_result = GoldenResult(
        case=GoldenCase(name="good_case", agent_type="qa", output="x", expect={}),
        score=95,
        passed_contract=True,
        ok=True,
        reasons=[],
    )

    with patch("evals.eval_gate.golden_runner.run_agent", return_value=[good_result]):
        warning = eval_gate.run_evals_for_agent_type("qa")

    assert warning is None


def test_eval_gate_async_runs_in_thread():
    """run_evals_for_agent_type_async lanza un thread daemon."""
    from evals import eval_gate

    started = threading.Event()
    original = eval_gate.run_evals_for_agent_type

    def _slow(*args, **kwargs):
        started.set()
        return None

    with patch("evals.eval_gate.run_evals_for_agent_type", side_effect=_slow):
        eval_gate.run_evals_for_agent_type_async("qa")
        # El thread debe arrancar en < 1 segundo
        assert started.wait(timeout=2), "El thread de evals no arrancó"
