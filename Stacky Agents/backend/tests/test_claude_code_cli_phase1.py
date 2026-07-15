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


def test_event_detail_lines_renders_thinking_text_and_tool_use_in_order():
    from services import claude_code_cli_runner as r

    event = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "primero miro el ticket"},
                {"type": "text", "text": "Voy a listar los archivos."},
                {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
            ],
        },
    }
    lines = r._event_detail_lines(event)
    assert [level for _, level in lines] == ["debug", "info", "info"]
    assert lines[0][0].startswith("thinking: primero miro el ticket")
    assert lines[1][0] == "assistant: Voy a listar los archivos."
    assert lines[2][0].startswith("tool_use/Bash: ")
    assert '"command": "ls"' in lines[2][0]


def test_event_detail_lines_renders_tool_result_from_user_event():
    from services import claude_code_cli_runner as r

    ok_event = {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tu_1",
                    "content": [{"type": "text", "text": "archivo1.py\narchivo2.py"}],
                }
            ],
        },
    }
    lines = r._event_detail_lines(ok_event)
    assert lines == [("tool_result(ok): archivo1.py archivo2.py", "info")]

    err_event = {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {"type": "tool_result", "is_error": True, "content": "boom"}
            ],
        },
    }
    lines = r._event_detail_lines(err_event)
    assert lines == [("tool_result(error): boom", "warn")]


def test_event_detail_lines_passthrough_for_other_events():
    from services import claude_code_cli_runner as r

    assert r._event_detail_lines(None) is None
    assert r._event_detail_lines({"type": "result", "result": "ok"}) is None
    assert r._event_detail_lines({"type": "system", "subtype": "init"}) is None
    # assistant sin lista de content → sin render especial
    assert r._event_detail_lines({"type": "assistant", "message": {}}) is None
    # message no-dict no debe crashear el reader thread
    assert r._event_detail_lines({"type": "user", "message": "raro"}) is None


def test_event_detail_lines_labels_user_text_as_user():
    from services import claude_code_cli_runner as r

    # Texto en eventos user (p. ej. replay de --resume) NO debe decir assistant.
    event = {
        "type": "user",
        "message": {"role": "user", "content": [{"type": "text", "text": "dale, seguí"}]},
    }
    assert r._event_detail_lines(event) == [("user: dale, seguí", "info")]

    # content como string plano también se renderiza.
    flat = {"type": "user", "message": {"role": "user", "content": "hola"}}
    assert r._event_detail_lines(flat) == [("user: hola", "info")]


def test_prompt_echo_message_shows_input_and_truncates():
    from services import claude_code_cli_runner as r

    short = r._prompt_echo_message("hola agente")
    assert short == "input inicial → claude:\nhola agente"

    masked = r._prompt_echo_message("hola [PII_1]", pii_masked=True)
    assert masked == "input inicial → claude (PII enmascarada):\nhola [PII_1]"

    long_prompt = "x" * (r._PROMPT_ECHO_MAX_CHARS + 500)
    echoed = r._prompt_echo_message(long_prompt)
    assert echoed.startswith("input inicial → claude:\n")
    assert "truncado" in echoed
    assert str(len(long_prompt)) in echoed
    # No incluye el prompt completo
    assert len(echoed) < len(long_prompt)


def test_tool_result_excerpt_marks_non_text_blocks():
    from services import claude_code_cli_runner as r

    content = [
        {"type": "image", "source": {"type": "base64", "data": "…"}},
        {"type": "text", "text": "listo"},
    ]
    assert r._tool_result_excerpt(content) == "[bloque image] listo"


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


# ---------------------------------------------------------------------------
# Defaults duros: modelo sonnet-5 (primario) + effort medium en TODA invocación CLI
# ---------------------------------------------------------------------------

def test_build_command_defaults_sonnet5_and_medium_effort():
    from config import config
    from services import claude_code_cli_runner as r

    assert config.CLAUDE_CODE_CLI_MODEL == "claude-sonnet-5"
    assert config.CLAUDE_CODE_CLI_EFFORT == "medium"
    cmd = r._build_command(model_override=None)
    assert cmd[cmd.index("--model") + 1] == "claude-sonnet-5"
    assert cmd[cmd.index("--effort") + 1] == "medium"


def test_fallback_model_default_is_sonnet46():
    """El fallback default es sonnet-4-6 (el antiguo primario) — nunca vacío ni opus/fable."""
    from config import config

    assert config.CLAUDE_CODE_CLI_MODEL_FALLBACK == "claude-sonnet-4-6"


def test_build_command_model_override_wins_over_default():
    from services import claude_code_cli_runner as r

    cmd = r._build_command(model_override="claude-haiku-4-5")
    assert cmd[cmd.index("--model") + 1] == "claude-haiku-4-5"


def test_build_command_effort_configurable_and_validated(monkeypatch):
    from config import config
    from services import claude_code_cli_runner as r

    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_EFFORT", "high")
    cmd = r._build_command(model_override=None)
    assert cmd[cmd.index("--effort") + 1] == "high"

    # Valor inválido → no se pasa el flag (el CLI usa su default), no rompe el spawn.
    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_EFFORT", "ultra")
    cmd = r._build_command(model_override=None)
    assert "--effort" not in cmd

    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_EFFORT", "")
    cmd = r._build_command(model_override=None)
    assert "--effort" not in cmd


# ---------------------------------------------------------------------------
# Fallback sonnet-5 → sonnet-4-6 en el spawn (_spawn_claude_with_fallback).
# ---------------------------------------------------------------------------

def test_looks_like_model_error_detects_known_patterns():
    from services import claude_code_cli_runner as r

    assert r._looks_like_model_error("Error: unknown model 'claude-sonnet-5'")
    assert r._looks_like_model_error("model claude-x-9 does not exist")
    assert r._looks_like_model_error("INVALID MODEL specified")
    assert not r._looks_like_model_error("some unrelated stack trace")
    assert not r._looks_like_model_error("")
    assert not r._looks_like_model_error(None)


class _FakeAliveProc:
    """Simula un `claude` que arrancó bien: poll() nunca deja de ser None."""

    def poll(self):
        return None


class _FakeDeadProc:
    """Simula un `claude` que murió casi al toque con un exit code dado."""

    def __init__(self, returncode: int, stderr_text: str):
        self.returncode = returncode
        self._stderr_text = stderr_text
        self.communicate_called = False

    def poll(self):
        return self.returncode

    def communicate(self, timeout=None):
        self.communicate_called = True
        return "", self._stderr_text


def test_spawn_with_fallback_primary_succeeds_single_attempt(monkeypatch):
    """El primario (sonnet-5) arranca bien → nunca se llega a tocar el fallback."""
    from services import claude_code_cli_runner as r

    calls: list[list[str]] = []

    def fake_popen(cmd, **kwargs):
        calls.append(cmd)
        return _FakeAliveProc()

    monkeypatch.setattr(r.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(r, "_MODEL_FAILURE_GRACE_SEC", 0.05)

    logs: list[tuple[str, str]] = []
    proc, cmd, model = r._spawn_claude_with_fallback(
        primary_model="claude-sonnet-5",
        fallback_model="claude-sonnet-4-6",
        build_cmd=lambda m: ["claude", "--model", m],
        cwd=".",
        creationflags=0,
        env={},
        log=lambda level, msg: logs.append((level, msg)),
    )
    assert model == "claude-sonnet-5"
    assert len(calls) == 1
    assert cmd == ["claude", "--model", "claude-sonnet-5"]


def test_spawn_with_fallback_primary_fails_fast_retries_fallback(monkeypatch):
    """Sonnet-5 rechazado casi al toque → reintenta UNA vez con sonnet-4-6 y loguea ambos."""
    from services import claude_code_cli_runner as r

    responses = [
        _FakeDeadProc(1, "Error: unknown model 'claude-sonnet-5'"),
        _FakeAliveProc(),
    ]
    calls: list[list[str]] = []

    def fake_popen(cmd, **kwargs):
        calls.append(cmd)
        return responses.pop(0)

    monkeypatch.setattr(r.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(r, "_MODEL_FAILURE_GRACE_SEC", 0.05)

    logs: list[tuple[str, str]] = []
    proc, cmd, model = r._spawn_claude_with_fallback(
        primary_model="claude-sonnet-5",
        fallback_model="claude-sonnet-4-6",
        build_cmd=lambda m: ["claude", "--model", m],
        cwd=".",
        creationflags=0,
        env={},
        log=lambda level, msg: logs.append((level, msg)),
    )
    assert model == "claude-sonnet-4-6"
    assert calls == [
        ["claude", "--model", "claude-sonnet-5"],
        ["claude", "--model", "claude-sonnet-4-6"],
    ]
    assert any("intento 1/2" in msg and "claude-sonnet-5" in msg for _, msg in logs)
    assert any("intento 2/2" in msg and "claude-sonnet-4-6" in msg for _, msg in logs)
    assert any("reintentando con fallback" in msg for _, msg in logs)


def test_spawn_with_fallback_both_fail_returns_last_proc_untouched(monkeypatch):
    """Si hasta el fallback falla, el proc del último intento se devuelve intacto
    (sin communicate()) para que el manejo de error preexistente lo procese solo."""
    from services import claude_code_cli_runner as r

    responses = [_FakeDeadProc(1, "boom"), _FakeDeadProc(1, "boom again")]
    calls: list[list[str]] = []

    def fake_popen(cmd, **kwargs):
        calls.append(cmd)
        return responses.pop(0)

    monkeypatch.setattr(r.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(r, "_MODEL_FAILURE_GRACE_SEC", 0.05)

    proc, cmd, model = r._spawn_claude_with_fallback(
        primary_model="claude-sonnet-5",
        fallback_model="claude-sonnet-4-6",
        build_cmd=lambda m: ["claude", "--model", m],
        cwd=".",
        creationflags=0,
        env={},
        log=lambda level, msg: None,
    )
    assert model == "claude-sonnet-4-6"
    assert len(calls) == 2
    assert proc.communicate_called is False


def test_spawn_with_fallback_no_fallback_configured_single_attempt(monkeypatch):
    """fallback_model=None (o igual al primario) → un solo intento, sin ventana de gracia."""
    from services import claude_code_cli_runner as r

    calls: list[list[str]] = []

    def fake_popen(cmd, **kwargs):
        calls.append(cmd)
        return _FakeDeadProc(1, "boom")

    monkeypatch.setattr(r.subprocess, "Popen", fake_popen)

    proc, cmd, model = r._spawn_claude_with_fallback(
        primary_model="claude-sonnet-5",
        fallback_model=None,
        build_cmd=lambda m: ["claude", "--model", m],
        cwd=".",
        creationflags=0,
        env={},
        log=lambda level, msg: None,
    )
    assert model == "claude-sonnet-5"
    assert len(calls) == 1
