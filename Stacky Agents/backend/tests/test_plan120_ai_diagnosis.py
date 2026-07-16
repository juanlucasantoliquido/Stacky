"""Plan 120 F6 — deploy_diagnosis.py: diagnóstico IA local (costo cero, opt-in),
cliente LLM SIEMPRE mockeado (cero red real)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from services import deploy_diagnosis as diag
from services import deploy_store as store


@pytest.fixture()
def st(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_apps_path", lambda: tmp_path / "deploy_apps.json")
    monkeypatch.setattr(store, "_ledger_path", lambda: tmp_path / "deploy_ledger.jsonl")
    store._RUN_LOCKS.clear()
    return store


def _entry(run_id="dr-1", **overrides):
    base = {
        "run_id": run_id, "app_id": "miapp", "target": "__local__", "action": "deploy",
        "version_id": "v1", "status": "failed",
        "steps": [
            {"name": "ensure_dirs", "ok": True, "detail": ""},
            {"name": "transfer", "ok": False, "detail": "winrm_error: " + ("x" * 5000)},
        ],
        "error": "transfer: winrm_error",
    }
    base.update(overrides)
    return base


def test_prompt_incluye_hitl_y_paso_fallido():
    prompt = diag.build_diagnosis_prompt(_entry())
    assert "REGLA ABSOLUTA (HITL)" in prompt
    assert "NUNCA ejecutes comandos" in prompt
    assert "paso 'transfer'" in prompt


def test_prompt_trunca_outputs_largos():
    prompt = diag.build_diagnosis_prompt(_entry())
    assert "[recortado]" in prompt
    assert len(prompt) < 10000


def test_flag_off_404(st, monkeypatch):
    import config as _config
    monkeypatch.setattr(_config.config, "STACKY_DEPLOYMENTS_AI_DIAGNOSIS_ENABLED", False, raising=False)
    result = diag.diagnose_run("dr-1")
    assert result == {"ok": False, "error": "ai_diagnosis_disabled"}


def test_modelo_caido_error_legible_sin_llamada(st, monkeypatch):
    import config as _config
    monkeypatch.setattr(_config.config, "STACKY_DEPLOYMENTS_AI_DIAGNOSIS_ENABLED", True, raising=False)
    store.append_ledger(_entry())
    monkeypatch.setattr("services.local_insights._local_llm_reachable", lambda timeout=3.0: False)
    with mock.patch("copilot_bridge.invoke_local_llm") as m_invoke:
        result = diag.diagnose_run("dr-1")
    assert result["ok"] is False
    assert result["error"] == "local_llm_unreachable"
    m_invoke.assert_not_called()


def test_persiste_insight_en_entry(st, monkeypatch):
    import config as _config
    monkeypatch.setattr(_config.config, "STACKY_DEPLOYMENTS_AI_DIAGNOSIS_ENABLED", True, raising=False)
    store.append_ledger(_entry())
    monkeypatch.setattr("services.local_insights._local_llm_reachable", lambda timeout=3.0: True)
    fake_resp = SimpleNamespace(
        text='{"tldr": "fallo transferencia", "probable_cause": "WinRM caido", "remediation": "habilitar WinRM"}',
        metadata={"model": "qwen-local"},
    )
    with mock.patch("copilot_bridge.invoke_local_llm", return_value=fake_resp):
        result = diag.diagnose_run("dr-1")
    assert result["ok"] is True
    assert result["insight"]["tldr"] == "fallo transferencia"

    persisted = next(r for r in store.read_ledger(limit=10) if r["run_id"] == "dr-1")
    assert persisted["insight"]["tldr"] == "fallo transferencia"


def test_respuesta_corrupta_degrada_sin_crash(st, monkeypatch):
    import config as _config
    monkeypatch.setattr(_config.config, "STACKY_DEPLOYMENTS_AI_DIAGNOSIS_ENABLED", True, raising=False)
    store.append_ledger(_entry())
    monkeypatch.setattr("services.local_insights._local_llm_reachable", lambda timeout=3.0: True)
    fake_resp = SimpleNamespace(text="no es json valido {{{", metadata={})
    with mock.patch("copilot_bridge.invoke_local_llm", return_value=fake_resp):
        result = diag.diagnose_run("dr-1")
    assert result["ok"] is False
    assert result["error"] == "parse_failed"
