"""Unit tests for step_descriptor.py.

Validates:
  - Deterministic baseline descriptions match action/target metadata.
  - [STEP NN] log lines override planned steps when both exist.
  - LLM polish path (mocked) replaces descriptions and tags source='llm'.
  - LLM failure falls back to deterministic without raising.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")

import step_descriptor


def _make_run(sid: str, screenshots: list, stdout_lines: list = None) -> dict:
    """Helper to build a minimal runner_output run dict."""
    stdout_text = ""
    if stdout_lines:
        stdout_text = "\n".join(stdout_lines) + "\n"
    return {
        "scenario_id": sid,
        "status": "pass",
        "duration_ms": 1000,
        "artifacts": {"screenshots": screenshots},
        "raw_stdout": stdout_text,
    }


def _make_scenario(sid: str, pasos: list, oraculos: list = None) -> dict:
    return {
        "scenario_id": sid,
        "titulo": f"Title {sid}",
        "pantalla": "FrmAgenda.aspx",
        "pasos": pasos,
        "oraculos": oraculos or [],
    }


def test_setup_screenshot_gets_setup_description():
    runs = [_make_run("P01", [r"C:\evidence\P01\step_00_setup.png"])]
    scenarios = [_make_scenario("P01", pasos=[
        {"accion": "navigate", "target": "FrmAgenda.aspx", "valor": None}
    ])]

    out = step_descriptor.build_step_descriptions(runs, scenarios, use_llm=False)
    descs = out["P01"]
    assert len(descs) == 1
    assert descs[0]["step_index"] == "setup"
    assert "FrmAgenda" in descs[0]["description"]
    assert descs[0]["description_source"] == "deterministic"


def test_final_screenshot_uses_oracles():
    runs = [_make_run("P04", [r"C:\evidence\P04\step_final_state.png"])]
    scenarios = [_make_scenario("P04",
        pasos=[{"accion": "click", "target": "btn_buscar", "valor": None}],
        oraculos=[{"tipo": "visible", "target": "msg_lista_vacia", "valor": None}],
    )]
    out = step_descriptor.build_step_descriptions(runs, scenarios, use_llm=False)
    final = out["P04"][0]
    assert final["step_index"] == "final"
    assert "lista_vacia" in final["description"]


def test_step_after_uses_planned_paso_when_no_stdout():
    runs = [_make_run("P05", [r"C:\evidence\P05\step_02_after.png"])]
    scenarios = [_make_scenario("P05", pasos=[
        {"accion": "navigate", "target": "FrmAgenda.aspx", "valor": None},
        {"accion": "select", "target": "select_empresa", "valor": "0001"},
        {"accion": "click", "target": "btn_buscar", "valor": None},
    ])]
    out = step_descriptor.build_step_descriptions(runs, scenarios, use_llm=False)
    step2 = out["P05"][0]
    assert step2["step_index"] == 2
    assert step2["action"] == "select"
    assert step2["target"] == "select_empresa"
    assert step2["value"] == "0001"
    # Description mentions the value
    assert "0001" in step2["description"]


def test_observed_steps_override_planned_paso():
    """When [STEP NN] stdout differs from scenarios.json, prefer the observed log."""
    runs = [_make_run("P05",
        [r"C:\evidence\P05\step_01_after.png"],
        stdout_lines=["[STEP 01] expand collapsible"],
    )]
    # Planned says navigate, but the runtime log says expand
    scenarios = [_make_scenario("P05", pasos=[
        {"accion": "navigate", "target": "FrmAgenda.aspx", "valor": None},
    ])]
    out = step_descriptor.build_step_descriptions(runs, scenarios, use_llm=False)
    step = out["P05"][0]
    assert step["action"] == "expand"
    assert step["target"] == "collapsible"
    # The deterministic phrase for "expand collapsible" should NOT mention FrmAgenda
    assert "FrmAgenda" not in step["description"]


def test_action_phrasings_are_spanish():
    """Spot-check that common actions get readable Spanish phrases."""
    cases = [
        ("click", "btn_buscar", None, "click"),
        ("fill", "input_fecha_desde", "01/2026", "01/2026"),
        ("select", "select_empresa", "0001", "0001"),
    ]
    for action, target, value, must_include in cases:
        text = step_descriptor._action_to_phrase(action, target, value)
        assert must_include in text, f"action={action}: missing '{must_include}' in {text!r}"


def test_llm_polish_replaces_descriptions(monkeypatch):
    """If llm_client returns valid JSON, descriptions and source are updated."""
    runs = [_make_run("P01",
        [r"C:\evidence\P01\step_00_setup.png", r"C:\evidence\P01\step_01_after.png"],
    )]
    scenarios = [_make_scenario("P01", pasos=[
        {"accion": "navigate", "target": "FrmAgenda.aspx", "valor": None},
    ])]

    def fake_call_llm(**kwargs):
        return {
            "text": (
                '{"steps":[{"n":0,"description":"Polished setup desc"},'
                '{"n":1,"description":"Polished step 1 desc"}]}'
            ),
            "model": "gpt-5-mini",
            "duration_ms": 50,
        }

    # Inject a fake llm_client module
    import types
    fake_mod = types.SimpleNamespace(
        call_llm=fake_call_llm,
        LLMError=RuntimeError,
    )
    monkeypatch.setitem(sys.modules, "llm_client", fake_mod)

    out = step_descriptor.build_step_descriptions(runs, scenarios, use_llm=True)
    descs = out["P01"]
    assert descs[0]["description"] == "Polished setup desc"
    assert descs[0]["description_source"] == "llm"
    assert descs[1]["description"] == "Polished step 1 desc"


def test_llm_polish_failure_falls_back_to_deterministic(monkeypatch):
    runs = [_make_run("P01", [r"C:\evidence\P01\step_00_setup.png"])]
    scenarios = [_make_scenario("P01", pasos=[
        {"accion": "navigate", "target": "FrmAgenda.aspx", "valor": None},
    ])]

    class FakeError(Exception):
        pass

    def fake_call_llm(**kwargs):
        raise FakeError("network down")

    import types
    fake_mod = types.SimpleNamespace(
        call_llm=fake_call_llm,
        LLMError=FakeError,
    )
    monkeypatch.setitem(sys.modules, "llm_client", fake_mod)

    out = step_descriptor.build_step_descriptions(runs, scenarios, use_llm=True)
    descs = out["P01"]
    assert descs[0]["description_source"] == "deterministic"
    assert "FrmAgenda" in descs[0]["description"]


def test_llm_polish_invalid_json_falls_back(monkeypatch):
    runs = [_make_run("P01", [r"C:\evidence\P01\step_00_setup.png"])]
    scenarios = [_make_scenario("P01", pasos=[
        {"accion": "navigate", "target": "FrmAgenda.aspx", "valor": None},
    ])]

    def fake_call_llm(**kwargs):
        return {"text": "not json at all", "model": "x", "duration_ms": 1}

    import types
    fake_mod = types.SimpleNamespace(call_llm=fake_call_llm, LLMError=RuntimeError)
    monkeypatch.setitem(sys.modules, "llm_client", fake_mod)

    out = step_descriptor.build_step_descriptions(runs, scenarios, use_llm=True)
    assert out["P01"][0]["description_source"] == "deterministic"


def test_extract_observed_steps_from_plain_text():
    raw = (
        "[STEP 01] navigate FrmAgenda.aspx\n"
        "[STEP 02] click btn_buscar\n"
    )
    parsed = step_descriptor._extract_observed_steps(raw)
    assert len(parsed) == 2
    assert parsed[0] == {"step_index": 1, "action": "navigate", "target": "FrmAgenda.aspx"}
    assert parsed[1] == {"step_index": 2, "action": "click", "target": "btn_buscar"}


def test_extract_observed_steps_from_playwright_json():
    """raw_stdout may be a JSON report; STEP markers live inside results[].stdout[]."""
    import json
    raw = json.dumps({
        "suites": [{
            "suites": [{
                "specs": [{
                    "tests": [{
                        "results": [{
                            "stdout": [
                                {"text": "[STEP 01] expand collapsible\n"},
                                {"text": "[STEP 02] fill input_desde\n"},
                            ]
                        }]
                    }]
                }]
            }]
        }]
    })
    parsed = step_descriptor._extract_observed_steps(raw)
    assert len(parsed) == 2
    assert parsed[0]["step_index"] == 1
    assert parsed[1]["action"] == "fill"
