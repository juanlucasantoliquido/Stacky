"""Plan 169 F2 — generador de variantes (local / runtime one-shot).

REGLA DURA (G14/§2.3): invoke_local_llm, run_agent, _wait_and_read_output y
_ensure_optimizer_ticket SIEMPRE mockeados — cero red, cero subprocess, cero DB.
"""
import types

import pytest

import runtime_paths
from config import config as _cfg
from services import variant_generator as vg


@pytest.fixture(autouse=True)
def _tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    monkeypatch.setattr(runtime_paths, "stacky_agents_dir", lambda: agents_dir)
    # C8/G14 — _ensure_optimizer_ticket abre DB real: mockeado en TODOS los casos.
    monkeypatch.setattr(vg, "_ensure_optimizer_ticket", lambda: 4242)
    return tmp_path


_VARIANT_OK = (
    "<<<VARIANTE>>>\nnuevo prompt mejorado\n<<<FIN_VARIANTE>>>\n"
    "<<<LECCION>>>\ncambie X para atacar la critica\n<<<FIN_LECCION>>>"
)


def _bridge_resp(text):
    return types.SimpleNamespace(text=text)


def test_extract_block():
    assert vg.extract_block(_VARIANT_OK, "<<<VARIANTE>>>", "<<<FIN_VARIANTE>>>") == "nuevo prompt mejorado"
    assert vg.extract_block("no hay marcadores", "<<<VARIANTE>>>", "<<<FIN_VARIANTE>>>") is None
    assert vg.extract_block("<<<VARIANTE>>>\nsin cierre", "<<<VARIANTE>>>", "<<<FIN_VARIANTE>>>") is None
    assert vg.extract_block("", "<<<VARIANTE>>>", "<<<FIN_VARIANTE>>>") is None


def test_resolve_generator_mode_auto(monkeypatch):
    monkeypatch.setattr(_cfg, "STACKY_EVOLUTION_OPTIMIZER_GENERATOR", "auto")
    monkeypatch.setattr(_cfg, "LOCAL_LLM_ENDPOINT", "http://x/v1")
    assert vg.resolve_generator_mode() == ("local", True)
    monkeypatch.setattr(_cfg, "LOCAL_LLM_ENDPOINT", "")
    assert vg.resolve_generator_mode() == ("runtime", True)


def test_resolve_generator_mode_local_sin_endpoint(monkeypatch):
    monkeypatch.setattr(_cfg, "STACKY_EVOLUTION_OPTIMIZER_GENERATOR", "local")
    monkeypatch.setattr(_cfg, "LOCAL_LLM_ENDPOINT", "")
    assert vg.resolve_generator_mode() == ("local", False)


def test_generate_local_ok(monkeypatch):
    import copilot_bridge
    monkeypatch.setattr(copilot_bridge, "invoke_local_llm", lambda **kw: _bridge_resp(_VARIANT_OK))
    monkeypatch.setattr(_cfg, "LOCAL_LLM_MODEL", "qwen3:32b")
    res = vg.generate(user_prompt="mejora esto", mode="local", runtime=None)
    assert res["text"] == "nuevo prompt mejorado"
    assert res["lesson"] == "cambie X para atacar la critica"
    assert res["error"] is None
    assert res["model"] == "qwen3:32b"
    assert res["tokens_est_in"] > 0 and res["tokens_est_out"] > 0


def test_generate_local_runtime_error_degrada(monkeypatch):
    import copilot_bridge

    def _boom(**kw):
        raise RuntimeError("LOCAL_LLM_ENDPOINT no está configurado")

    monkeypatch.setattr(copilot_bridge, "invoke_local_llm", _boom)
    res = vg.generate(user_prompt="x", mode="local", runtime=None)
    assert res["error"] is not None
    assert res["text"] is None


def test_generate_sin_marcador(monkeypatch):
    import copilot_bridge
    monkeypatch.setattr(copilot_bridge, "invoke_local_llm",
                        lambda **kw: _bridge_resp("solo prosa sin ningun marcador"))
    res = vg.generate(user_prompt="x", mode="local", runtime=None)
    assert res["error"] == "sin_marcador_variante"


def test_generate_runtime_llama_run_agent(monkeypatch):
    import agent_runner
    captured = {}

    def _fake_run_agent(**kw):
        captured.update(kw)
        return 777

    monkeypatch.setattr(agent_runner, "run_agent", _fake_run_agent)
    monkeypatch.setattr(vg, "_wait_and_read_output", lambda eid, **kw: _VARIANT_OK)
    res = vg.generate(user_prompt="mejora", mode="runtime", runtime="claude_code_cli")
    assert captured["agent_type"] == "evolution_mutator"
    assert captured["runtime"] == "claude_code_cli"
    assert captured["vscode_agent_filename"] == "EvolutionMutator.agent.md"
    assert captured["system_prompt_override"] == vg._MUTATOR_SYSTEM
    assert res["text"] == "nuevo prompt mejorado"
    assert res["model"] == "runtime:claude_code_cli"


def test_generate_runtime_launch_failed(monkeypatch):
    import agent_runner

    def _boom(**kw):
        raise RuntimeError("no arranca")

    monkeypatch.setattr(agent_runner, "run_agent", _boom)
    res = vg.generate(user_prompt="x", mode="runtime", runtime="codex_cli")
    assert res["error"].startswith("runtime_launch_failed")
    assert res["text"] is None


def test_flag_suggestion_parse(monkeypatch):
    import copilot_bridge
    raw_ok = (
        _VARIANT_OK + "\n<<<SUGERENCIA_FLAG>>>\n"
        '{"flag": "LOCAL_LLM_MODEL", "value": "qwen3:14b", "razon": "mas barato"}\n'
        "<<<FIN_SUGERENCIA_FLAG>>>"
    )
    monkeypatch.setattr(copilot_bridge, "invoke_local_llm", lambda **kw: _bridge_resp(raw_ok))
    res = vg.generate(user_prompt="x", mode="local", runtime=None)
    assert res["flag_suggestion"] == {"flag": "LOCAL_LLM_MODEL", "value": "qwen3:14b", "razon": "mas barato"}

    raw_bad = _VARIANT_OK + "\n<<<SUGERENCIA_FLAG>>>\n{roto json\n<<<FIN_SUGERENCIA_FLAG>>>"
    monkeypatch.setattr(copilot_bridge, "invoke_local_llm", lambda **kw: _bridge_resp(raw_bad))
    res2 = vg.generate(user_prompt="x", mode="local", runtime=None)
    assert res2["flag_suggestion"] is None


def test_one_shot_incluye_menos_nueve():
    from services.claude_code_cli_runner import _ONE_SHOT_ADO_IDS
    assert -9 in _ONE_SHOT_ADO_IDS
    assert vg._OPTIMIZER_ADO_ID == -9
