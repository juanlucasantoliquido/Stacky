"""Tests Fase 1 del plan robustecimiento arnés sobre claude_code_cli_runner.

F1.1 — paridad de calidad (contract validator + confidence + gate needs_review)
F1.2 — telemetría nativa del stream-json + repro.ps1
F1.4 — settings.json efímero con hooks + --settings en _build_command
§5.3 — --dangerously-skip-permissions default ON
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
# F1.2 — parsing y telemetría
# ---------------------------------------------------------------------------

def test_parse_line_returns_event_dict():
    from services import claude_code_cli_runner as r

    line = json.dumps({"type": "result", "result": "ok!", "is_error": False})
    message, level, text, event = r._parse_claude_code_line(line, "info")
    assert text == "ok!"
    assert isinstance(event, dict) and event["type"] == "result"

    # Línea no-JSON: event None, comportamiento previo intacto.
    message, level, text, event = r._parse_claude_code_line("plain text", "info")
    assert event is None and message == "plain text"


def test_capture_result_telemetry_extracts_native_fields():
    from services import claude_code_cli_runner as r

    telemetry: dict = {}
    # session_id llega primero en system/init
    r._capture_result_telemetry(
        telemetry, {"type": "system", "subtype": "init", "session_id": "sess-123"}
    )
    r._capture_result_telemetry(
        telemetry,
        {
            "type": "result",
            "session_id": "sess-123",
            "is_error": False,
            "num_turns": 7,
            "total_cost_usd": 0.42,
            "usage": {
                "input_tokens": 1000,
                "output_tokens": 200,
                "cache_read_input_tokens": 800,
            },
        },
    )
    assert telemetry["session_id"] == "sess-123"
    assert telemetry["num_turns"] == 7
    assert telemetry["total_cost_usd"] == 0.42
    assert telemetry["is_error"] is False
    assert telemetry["usage"]["input_tokens"] == 1000
    assert telemetry["usage"]["cache_read_input_tokens"] == 800


def test_capture_ignores_non_result_usage():
    from services import claude_code_cli_runner as r

    telemetry: dict = {}
    r._capture_result_telemetry(
        telemetry, {"type": "assistant", "usage": {"input_tokens": 5}}
    )
    assert "usage" not in telemetry


def test_write_repro_script(tmp_path):
    from services import claude_code_cli_runner as r

    repro = r._write_repro_script(
        tmp_path,
        cmd=["C:\\bin\\claude.cmd", "-p", "--output-format", "stream-json"],
        cwd=Path("C:/workspace"),
        execution_id=42,
        initial_message="hola agente",
    )
    assert repro.exists()
    content = repro.read_text(encoding="utf-8")
    assert "claude.cmd" in content
    assert "first_message.jsonl" in content
    assert 'STACKY_EXECUTION_ID = "42"' in content
    # El primer mensaje queda materializado como stream-json válido.
    first = json.loads((tmp_path / "first_message.jsonl").read_text(encoding="utf-8"))
    assert first["message"]["content"][0]["text"] == "hola agente"


# ---------------------------------------------------------------------------
# F1.1 — paridad de calidad + gate needs_review
# ---------------------------------------------------------------------------

_BAD_QA_OUTPUT = "muy corto"  # sin verdict, sin PASS/FAIL → errores duros
_GOOD_QA_OUTPUT = (
    "## Verdict\n\nPASS — la funcionalidad cumple los criterios.\n\n" + "detalle " * 100
)


def test_quality_eval_runs_contract_and_confidence(monkeypatch):
    from config import config
    from services import claude_code_cli_runner as r

    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED", False)
    cv, conf, status = r._evaluate_output_quality("qa", _BAD_QA_OUTPUT)
    # Validación corre y persiste aunque el gate esté apagado…
    assert cv.failures and not cv.passed
    assert conf.overall >= 0
    # …pero el status no se degrada con el gate OFF (default).
    assert status == "completed"


def test_quality_gate_demotes_to_needs_review(monkeypatch):
    from config import config
    from services import claude_code_cli_runner as r

    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED", True)
    cv, conf, status = r._evaluate_output_quality("qa", _BAD_QA_OUTPUT)
    assert status == "needs_review"

    cv, conf, status = r._evaluate_output_quality("qa", _GOOD_QA_OUTPUT)
    assert not cv.failures
    assert status == "completed"


def test_unknown_agent_type_never_demotes(monkeypatch):
    from config import config
    from services import claude_code_cli_runner as r

    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED", True)
    cv, conf, status = r._evaluate_output_quality("sin_contrato", "salida libre")
    assert status == "completed" and cv.passed


# ---------------------------------------------------------------------------
# F1.4 — --settings en el comando + §5.3 skip permissions default ON
# ---------------------------------------------------------------------------

def test_build_command_includes_settings_when_provided(tmp_path):
    from services import claude_code_cli_runner as r

    settings = tmp_path / "stacky_hooks_settings.json"
    settings.write_text("{}", encoding="utf-8")
    cmd = r._build_command(model_override=None, settings_file=settings)
    assert "--settings" in cmd
    assert str(settings) in cmd


def test_build_command_omits_settings_when_none():
    from services import claude_code_cli_runner as r

    cmd = r._build_command(model_override=None)
    assert "--settings" not in cmd


def test_skip_permissions_default_true_decision_5_3(monkeypatch):
    # Decisión vinculante §5.3: default true → --dangerously-skip-permissions
    # siempre presente salvo override explícito del operador.
    from config import config
    from services import claude_code_cli_runner as r

    assert config.CLAUDE_CODE_CLI_SKIP_PERMISSIONS is True
    cmd = r._build_command(model_override=None)
    assert "--dangerously-skip-permissions" in cmd
    assert "--permission-mode" not in cmd
