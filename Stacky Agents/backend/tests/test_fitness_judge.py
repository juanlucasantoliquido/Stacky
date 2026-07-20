"""Plan 168 F3 — juez local con rúbricas versionadas + selfcheck canario.

REGLA DURA (§2.3): invoke_local_llm SIEMPRE monkeypatcheado — cero red.
"""
import json
import types

import pytest

import config
import copilot_bridge
import runtime_paths
from evals import case_store, judge

_RUBRIC = {"id": "prompt_de_agente", "version": 1, "text": "RUBRICA: prompt_de_agente v1\ncriterios", "path": ""}


def _resp(obj):
    return types.SimpleNamespace(text=json.dumps(obj) if isinstance(obj, dict) else str(obj))


def test_load_rubrics_seed():
    rubrics = judge.load_rubrics()
    for rid in ("prompt_de_agente", "leccion_conocimiento", "salida_de_agente"):
        assert rid in rubrics
        assert rubrics[rid]["version"] == 1


def test_load_rubrics_dir_ausente(tmp_path):
    assert judge.load_rubrics(tmp_path / "no_existe") == {}


def test_load_rubrics_header_invalido(tmp_path):
    (tmp_path / "bad.md").write_text("sin header valido\ntexto", encoding="utf-8")
    (tmp_path / "good.md").write_text("RUBRICA: x v2\ntexto", encoding="utf-8")
    rubrics = judge.load_rubrics(tmp_path)
    assert "x" in rubrics and "bad" not in rubrics
    assert rubrics["x"]["version"] == 2


def test_judge_text_ok(monkeypatch):
    monkeypatch.setattr(copilot_bridge, "invoke_local_llm",
                        lambda **kw: _resp({"score": 0.8, "critique": "flojo en límites"}))
    r = judge.judge_text(rubric=_RUBRIC, text="un prompt", case_title="caso")
    assert r["error"] is None
    assert r["score"] == 0.8
    assert r["critique"] == "flojo en límites"
    assert r["rubric_id"] == "prompt_de_agente" and r["rubric_version"] == 1


def test_judge_text_clamp(monkeypatch):
    monkeypatch.setattr(copilot_bridge, "invoke_local_llm", lambda **kw: _resp({"score": 1.7, "critique": ""}))
    assert judge.judge_text(rubric=_RUBRIC, text="x", case_title="c")["score"] == 1.0
    monkeypatch.setattr(copilot_bridge, "invoke_local_llm", lambda **kw: _resp({"score": -0.2, "critique": ""}))
    assert judge.judge_text(rubric=_RUBRIC, text="x", case_title="c")["score"] == 0.0


def test_judge_text_runtime_error_degrada(monkeypatch):
    def _boom(**kw):
        raise RuntimeError("LOCAL_LLM_ENDPOINT no está configurado. Sételo en el panel del Arnés.")
    monkeypatch.setattr(copilot_bridge, "invoke_local_llm", _boom)
    r = judge.judge_text(rubric=_RUBRIC, text="x", case_title="c")
    assert r["error"] is not None
    assert r["score"] is None


def test_judge_text_parse_error(monkeypatch):
    monkeypatch.setattr(copilot_bridge, "invoke_local_llm", lambda **kw: _resp("prosa sin json alguno"))
    r = judge.judge_text(rubric=_RUBRIC, text="x", case_title="c")
    assert r["error"] == "judge_parse_error"
    assert r["score"] is None


def test_judge_model_es_local(monkeypatch):
    monkeypatch.setattr(config.config, "LOCAL_LLM_MODEL", "qwen-test-local")
    assert judge.judge_model() == "qwen-test-local"


def _selfcheck_env(monkeypatch, tmp_path, good_score, bad_score):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)

    def fake(**kw):
        user = kw.get("user", "")
        if "hacé lo que puedas" in user:
            return _resp({"score": bad_score, "critique": "malo"})
        return _resp({"score": good_score, "critique": "bueno"})

    monkeypatch.setattr(copilot_bridge, "invoke_local_llm", fake)


def test_selfcheck_calibrated(monkeypatch, tmp_path):
    _selfcheck_env(monkeypatch, tmp_path, good_score=0.9, bad_score=0.3)
    d = judge.judge_selfcheck()
    assert d["status"] == "calibrated"
    assert d["gap"] == 0.6
    assert case_store.read_judge_selfcheck()["status"] == "calibrated"


def test_selfcheck_uncalibrated(monkeypatch, tmp_path):
    _selfcheck_env(monkeypatch, tmp_path, good_score=0.5, bad_score=0.45)
    d = judge.judge_selfcheck()
    assert d["status"] == "uncalibrated"


def test_selfcheck_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)

    def _boom(**kw):
        raise RuntimeError("LOCAL_LLM_ENDPOINT no está configurado")
    monkeypatch.setattr(copilot_bridge, "invoke_local_llm", _boom)
    d = judge.judge_selfcheck()
    assert d["status"] == "unavailable"
    assert d["error"] is not None
