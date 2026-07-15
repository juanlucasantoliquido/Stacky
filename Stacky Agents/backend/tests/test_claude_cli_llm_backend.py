"""Plan 37 — backend LLM interno `claude_cli`.

Verifica que `LLM_BACKEND=claude_cli` enruta las llamadas LLM internas de Stacky
por el CLI `claude` (cuenta Claude del operador, OAuth de disco) y NO por GitHub
Copilot. Subprocess mockeado: no llama al `claude` real.
"""
import json
import os
import subprocess

os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

from config import config
import copilot_bridge


def _collector():
    logs: list[tuple[str, str]] = []
    return logs, (lambda level, msg: logs.append((level, msg)))


def _completed(stdout: str = "", stderr: str = "", rc: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["claude"], returncode=rc, stdout=stdout, stderr=stderr)


def test_claude_cli_backend_uses_cli_not_copilot(monkeypatch):
    monkeypatch.setattr(config, "LLM_BACKEND", "claude_cli")
    monkeypatch.setattr(copilot_bridge, "_resolve_claude_bin", lambda: "claude")

    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["input"] = kwargs.get("input")
        return _completed(stdout=json.dumps({
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "RESPUESTA-CLAUDE",
            "usage": {"input_tokens": 12, "output_tokens": 7},
        }))

    monkeypatch.setattr(copilot_bridge.subprocess, "run", fake_run)
    # Si tocara Copilot, esto reventaría el test:
    def _no_copilot():
        raise AssertionError("claude_cli NO debe pedir token de Copilot")
    monkeypatch.setattr(copilot_bridge, "_get_copilot_token", _no_copilot)

    _logs, on_log = _collector()
    resp = copilot_bridge.invoke(agent_type="technical", system="SYS", user="USR", on_log=on_log)

    assert resp.text == "RESPUESTA-CLAUDE"
    assert resp.metadata["backend"] == "claude_cli"
    assert resp.metadata["model"] == config.CLAUDE_CODE_CLI_MODEL
    assert resp.metadata["tokens_in"] == 12
    assert resp.metadata["tokens_out"] == 7
    # system + user van combinados por stdin
    assert "SYS" in captured["input"] and "USR" in captured["input"]
    # el comando es el CLI claude en modo print + json
    assert captured["cmd"][0] == "claude"
    assert "-p" in captured["cmd"]
    assert "--output-format" in captured["cmd"] and "json" in captured["cmd"]
    assert "--model" in captured["cmd"]


def test_claude_cli_backend_exit_nonzero_raises_with_stderr(monkeypatch):
    monkeypatch.setattr(config, "LLM_BACKEND", "claude_cli")
    monkeypatch.setattr(copilot_bridge, "_resolve_claude_bin", lambda: "claude")
    monkeypatch.setattr(
        copilot_bridge.subprocess, "run",
        lambda cmd, **kw: _completed(stderr="boom auth error", rc=1),
    )
    _logs, on_log = _collector()
    with pytest.raises(RuntimeError) as ei:
        copilot_bridge.invoke(agent_type="qa", system="", user="hola", on_log=on_log)
    assert "boom auth error" in str(ei.value)


def test_claude_cli_backend_timeout_raises(monkeypatch):
    monkeypatch.setattr(config, "LLM_BACKEND", "claude_cli")
    monkeypatch.setattr(copilot_bridge, "_resolve_claude_bin", lambda: "claude")

    def _timeout(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kw.get("timeout", 0))

    monkeypatch.setattr(copilot_bridge.subprocess, "run", _timeout)
    _logs, on_log = _collector()
    with pytest.raises(RuntimeError) as ei:
        copilot_bridge.invoke(agent_type="technical", system="", user="hola", on_log=on_log)
    assert "timeout" in str(ei.value).lower()


def test_claude_cli_backend_falls_back_to_sonnet46_on_model_rejection(monkeypatch):
    """Primario (config.CLAUDE_CODE_CLI_MODEL, sonnet-5) rechazado -> reintenta
    UNA vez con config.CLAUDE_CODE_CLI_MODEL_FALLBACK (sonnet-4-6) y loguea ambos."""
    monkeypatch.setattr(config, "LLM_BACKEND", "claude_cli")
    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_MODEL", "claude-sonnet-5")
    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_MODEL_FALLBACK", "claude-sonnet-4-6")
    monkeypatch.setattr(copilot_bridge, "_resolve_claude_bin", lambda: "claude")

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        model_arg = cmd[cmd.index("--model") + 1]
        if model_arg == "claude-sonnet-5":
            return _completed(stderr="unknown model 'claude-sonnet-5'", rc=1)
        return _completed(stdout=json.dumps({
            "type": "result", "subtype": "success", "is_error": False,
            "result": "RESPUESTA-FALLBACK",
            "usage": {"input_tokens": 5, "output_tokens": 2},
        }))

    monkeypatch.setattr(copilot_bridge.subprocess, "run", fake_run)
    _logs, on_log = _collector()
    resp = copilot_bridge.invoke(agent_type="technical", system="SYS", user="USR", on_log=on_log)

    assert resp.text == "RESPUESTA-FALLBACK"
    assert resp.metadata["model"] == "claude-sonnet-4-6"
    assert len(calls) == 2
    assert calls[0][calls[0].index("--model") + 1] == "claude-sonnet-5"
    assert calls[1][calls[1].index("--model") + 1] == "claude-sonnet-4-6"
    warn_logs = [msg for level, msg in _logs if level == "warn"]
    assert any("reintentando con fallback" in msg for msg in warn_logs)


def test_claude_cli_backend_explicit_model_never_falls_back(monkeypatch):
    """Un `model=` explícito del caller (no el default de config) NUNCA degrada
    en silencio a otro modelo — si falla, se propaga el error tal cual."""
    monkeypatch.setattr(config, "LLM_BACKEND", "claude_cli")
    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_MODEL_FALLBACK", "claude-sonnet-4-6")
    monkeypatch.setattr(copilot_bridge, "_resolve_claude_bin", lambda: "claude")

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _completed(stderr="boom", rc=1)

    monkeypatch.setattr(copilot_bridge.subprocess, "run", fake_run)
    _logs, on_log = _collector()
    with pytest.raises(RuntimeError):
        copilot_bridge._invoke_claude_cli(
            agent_type="technical", system="SYS", user="USR", on_log=on_log,
            execution_id=None, model="claude-haiku-4-5",
        )
    # Un solo intento: el override explícito no dispara el fallback de config.
    assert len(calls) == 1


def test_parse_claude_cli_json_variants():
    text, tin, tout, finish = copilot_bridge._parse_claude_cli_json(
        json.dumps({"result": "ok", "usage": {"input_tokens": 3, "output_tokens": 4}, "subtype": "success"})
    )
    assert (text, tin, tout, finish) == ("ok", 3, 4, "success")
    # lista de eventos (stream-json accidental) → toma el de type=result
    listed = json.dumps([
        {"type": "system"},
        {"type": "result", "result": "final", "usage": {"input_tokens": 1, "output_tokens": 2}},
    ])
    assert copilot_bridge._parse_claude_cli_json(listed)[0] == "final"
    # vacío / no-json → tupla segura
    assert copilot_bridge._parse_claude_cli_json("")[0] == ""
    assert copilot_bridge._parse_claude_cli_json("not json at all")[0] == ""
