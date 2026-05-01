"""Tests de agent_config."""
import os
import sys
import json

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from agent_config import (
    AgentConfig,
    load_agent_config,
    save_agent_config,
    build_prompt_injection,
    to_dict,
    from_dict,
    KNOWN_AGENTS,
)


class TestPersistencia:
    def test_default_si_no_existe(self, tmp_path):
        cfg = load_agent_config(str(tmp_path), "tester")
        assert cfg.strictness == "normal"
        assert cfg.enabled is True

    def test_roundtrip(self, tmp_path):
        c = AgentConfig(strictness="permissive",
                        extra_instructions="No me importan los typos")
        save_agent_config(str(tmp_path), "tester", c)
        loaded = load_agent_config(str(tmp_path), "tester")
        assert loaded.strictness == "permissive"
        assert "typos" in loaded.extra_instructions

    def test_agente_desconocido_rechaza(self, tmp_path):
        with pytest.raises(ValueError):
            load_agent_config(str(tmp_path), "not_an_agent")

    def test_strictness_invalido_rechaza(self, tmp_path):
        c = AgentConfig(strictness="insano")
        with pytest.raises(ValueError):
            save_agent_config(str(tmp_path), "tester", c)

    def test_campos_extra_en_archivo_se_ignoran(self, tmp_path):
        os.makedirs(os.path.join(tmp_path, "agents"), exist_ok=True)
        path = os.path.join(tmp_path, "agents", "tester.config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "strictness": "strict",
                "hacker_field_that_does_not_exist": "rm -rf /",
            }, f)
        cfg = load_agent_config(str(tmp_path), "tester")
        assert cfg.strictness == "strict"
        # El campo raro no se cuela
        assert not hasattr(cfg, "hacker_field_that_does_not_exist")


class TestPromptInjection:
    def test_default_no_inyecta(self):
        inj = build_prompt_injection("tester", AgentConfig())
        assert inj == ""

    def test_permissive_inyecta_reglas_permisivas(self):
        c = AgentConfig(strictness="permissive")
        inj = build_prompt_injection("tester", c)
        assert "PERMISSIVE" in inj
        assert "RECHAZADO" in inj
        assert "bloqueantes reales" in inj.lower() or "bloqueante" in inj.lower()

    def test_strict_inyecta_reglas_estrictas(self):
        c = AgentConfig(strictness="strict")
        inj = build_prompt_injection("tester", c)
        assert "STRICT" in inj
        assert "RECHAZADO" in inj

    def test_extra_instructions_aparecen(self):
        c = AgentConfig(extra_instructions="Ignorá warnings de CSS")
        inj = build_prompt_injection("tester", c)
        assert "Ignorá warnings de CSS" in inj

    def test_forbidden_tests_aparecen(self):
        c = AgentConfig(forbidden_tests=["load_test", "stress_test"])
        inj = build_prompt_injection("tester", c)
        assert "load_test" in inj
        assert "NO corras" in inj

    def test_blocker_criteria_custom_aparece(self):
        c = AgentConfig(blocker_criteria=["compile_error"])  # solo uno
        inj = build_prompt_injection("tester", c)
        assert "compile_error" in inj
        assert "BLOQUEANTE" in inj or "blocker" in inj.lower() or "RECHAZADO" in inj

    def test_pm_skip_queries(self):
        c = AgentConfig(skip_queries=True)
        inj = build_prompt_injection("pm", c)
        assert "QUERIES_ANALISIS" in inj
        assert "NO generes" in inj or "no generes" in inj.lower()

    def test_dev_require_tests(self):
        c = AgentConfig(require_tests=True)
        inj = build_prompt_injection("dev", c)
        assert "tests unitarios" in inj.lower() or "test" in inj.lower()

    def test_disabled_agent_avisa(self):
        c = AgentConfig(enabled=False)
        inj = build_prompt_injection("pm", c)
        assert "DESHABILITADO" in inj


class TestDictIO:
    def test_from_dict_coacciona_tipos(self):
        c = from_dict({"enabled": 1, "strictness": "strict",
                       "forbidden_tests": "not-a-list"})
        assert c.enabled is True
        assert c.strictness == "strict"
        assert c.forbidden_tests == []   # coaccionado a lista vacía

    def test_from_dict_ignora_campos_desconocidos(self):
        c = from_dict({"strictness": "permissive",
                       "random_field": "boom"})
        assert c.strictness == "permissive"
        assert not hasattr(c, "random_field")

    def test_to_dict_tiene_todos_los_campos(self):
        c = AgentConfig()
        d = to_dict(c)
        assert "strictness" in d
        assert "extra_instructions" in d
        assert "allowed_tests" in d
