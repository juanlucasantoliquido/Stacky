"""Plan 106 F1 — Cliente HTTP al modelo local (OpenAI-compatible) en copilot_bridge.py.

invoke_local_llm() va SIEMPRE al endpoint local, sin mirar config.LLM_BACKEND (C1).
Mock de requests.post en el módulo copilot_bridge (gotcha plan 28: parchear en el
módulo que lo importa).
"""
import os
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def json(self):
        return self._json_data


def _ok_payload(content="Análisis completo del código."):
    return {"choices": [{"message": {"content": content}}]}


@pytest.fixture(autouse=True)
def _local_llm_config(monkeypatch):
    import config as cfg
    monkeypatch.setattr(cfg.config, "LOCAL_LLM_ENDPOINT", "http://localhost:11434/v1/chat/completions")
    monkeypatch.setattr(cfg.config, "LOCAL_LLM_MODEL", "qwen3:32b")
    monkeypatch.setattr(cfg.config, "LOCAL_LLM_TIMEOUT_SEC", 120)
    yield


def test_f1_invoke_local_llm_success(monkeypatch):
    import copilot_bridge

    mock_post = mock.Mock(return_value=_FakeResponse(200, _ok_payload("hola desde qwen")))
    monkeypatch.setattr(copilot_bridge.requests, "post", mock_post)

    result = copilot_bridge.invoke_local_llm(
        agent_type="local_llm_analyzer", system="sys", user="user",
        on_log=lambda level, msg: None,
    )
    assert result.text == "hola desde qwen"
    assert result.metadata["backend"] == "local_llm"


def test_f1_invoke_local_llm_ignores_global_backend(monkeypatch):
    import config as cfg
    import copilot_bridge

    monkeypatch.setattr(cfg.config, "LLM_BACKEND", "copilot")
    mock_post = mock.Mock(return_value=_FakeResponse(200, _ok_payload()))
    monkeypatch.setattr(copilot_bridge.requests, "post", mock_post)

    copilot_bridge.invoke_local_llm(
        agent_type="x", system="s", user="u", on_log=lambda level, msg: None,
    )
    called_url = mock_post.call_args[0][0]
    assert called_url == cfg.config.LOCAL_LLM_ENDPOINT


def test_f1_invoke_local_llm_timeout(monkeypatch):
    import copilot_bridge
    import requests as _requests

    monkeypatch.setattr(
        copilot_bridge.requests, "post",
        mock.Mock(side_effect=_requests.Timeout()),
    )
    with pytest.raises(RuntimeError, match="LOCAL_LLM_TIMEOUT_SEC"):
        copilot_bridge.invoke_local_llm(
            agent_type="x", system="s", user="u", on_log=lambda level, msg: None,
        )


def test_f1_invoke_local_llm_connection_error(monkeypatch):
    import copilot_bridge
    import requests as _requests

    monkeypatch.setattr(
        copilot_bridge.requests, "post",
        mock.Mock(side_effect=_requests.ConnectionError("refused")),
    )
    with pytest.raises(RuntimeError):
        copilot_bridge.invoke_local_llm(
            agent_type="x", system="s", user="u", on_log=lambda level, msg: None,
        )


def test_f1_invoke_local_llm_non_200(monkeypatch):
    import copilot_bridge

    monkeypatch.setattr(
        copilot_bridge.requests, "post",
        mock.Mock(return_value=_FakeResponse(500, {}, text="server error")),
    )
    with pytest.raises(RuntimeError, match="500"):
        copilot_bridge.invoke_local_llm(
            agent_type="x", system="s", user="u", on_log=lambda level, msg: None,
        )


def test_f1_invoke_local_llm_missing_choices(monkeypatch):
    import copilot_bridge

    monkeypatch.setattr(
        copilot_bridge.requests, "post",
        mock.Mock(return_value=_FakeResponse(200, {"choices": []})),
    )
    with pytest.raises(RuntimeError):
        copilot_bridge.invoke_local_llm(
            agent_type="x", system="s", user="u", on_log=lambda level, msg: None,
        )


def test_f1_invoke_local_llm_empty_content(monkeypatch):
    import copilot_bridge

    monkeypatch.setattr(
        copilot_bridge.requests, "post",
        mock.Mock(return_value=_FakeResponse(200, _ok_payload(""))),
    )
    with pytest.raises(RuntimeError):
        copilot_bridge.invoke_local_llm(
            agent_type="x", system="s", user="u", on_log=lambda level, msg: None,
        )


def test_f1_invoke_local_llm_endpoint_required(monkeypatch):
    import config as cfg
    import copilot_bridge

    monkeypatch.setattr(cfg.config, "LOCAL_LLM_ENDPOINT", "")
    with pytest.raises(RuntimeError, match="LOCAL_LLM_ENDPOINT"):
        copilot_bridge.invoke_local_llm(
            agent_type="x", system="s", user="u", on_log=lambda level, msg: None,
        )


def test_f1_invoke_local_llm_uses_configured_timeout(monkeypatch):
    import config as cfg
    import copilot_bridge

    monkeypatch.setattr(cfg.config, "LOCAL_LLM_TIMEOUT_SEC", 300)
    mock_post = mock.Mock(return_value=_FakeResponse(200, _ok_payload()))
    monkeypatch.setattr(copilot_bridge.requests, "post", mock_post)

    copilot_bridge.invoke_local_llm(
        agent_type="x", system="s", user="u", on_log=lambda level, msg: None,
    )
    assert mock_post.call_args.kwargs["timeout"] == 300


def test_f1_invoke_dispatch_local_llm_backend(monkeypatch):
    import config as cfg
    import copilot_bridge

    monkeypatch.setattr(cfg.config, "LLM_BACKEND", "local_llm")
    mock_post = mock.Mock(return_value=_FakeResponse(200, _ok_payload("via invoke()")))
    monkeypatch.setattr(copilot_bridge.requests, "post", mock_post)

    result = copilot_bridge.invoke(
        agent_type="developer", system="s", user="u", on_log=lambda level, msg: None,
    )
    assert result.text == "via invoke()"
    assert result.metadata["backend"] == "local_llm"


def test_f1_list_models_local_backend(monkeypatch):
    import config as cfg
    import copilot_bridge

    monkeypatch.setattr(cfg.config, "LLM_BACKEND", "local_llm")
    models = copilot_bridge.list_copilot_models()
    assert len(models) == 1
    assert models[0]["id"] == cfg.config.LOCAL_LLM_MODEL


def test_f1_on_log_receives_level_and_msg(monkeypatch):
    import copilot_bridge

    mock_post = mock.Mock(return_value=_FakeResponse(200, _ok_payload()))
    monkeypatch.setattr(copilot_bridge.requests, "post", mock_post)

    captured = []
    copilot_bridge.invoke_local_llm(
        agent_type="x", system="s", user="u",
        on_log=lambda level, msg: captured.append((level, msg)),
    )
    assert len(captured) >= 1
    for level, msg in captured:
        assert isinstance(level, str)
        assert isinstance(msg, str)
