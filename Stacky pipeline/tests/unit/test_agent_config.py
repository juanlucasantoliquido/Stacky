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


# ── P1.4 — qa y tester comparten prompt base, se diferencian por config ──

class TestQaTesterUnification:
    def test_qa_es_known_agent(self):
        assert "qa" in KNOWN_AGENTS
        assert "tester" in KNOWN_AGENTS

    def test_qa_strictness_inyecta_bloque_tester(self):
        # Cuando agent='qa' y strictness != normal, debe inyectar el bloque
        # de QA (no el genérico). qa y tester comparten lógica.
        c = AgentConfig(strictness="permissive")
        out_qa = build_prompt_injection("qa", c)
        out_tester = build_prompt_injection("tester", c)
        # Ambos deben hablar de "RECHAZADO" / "APROBADO" (bloque de QA)
        assert "APROBADO" in out_qa
        assert "APROBADO" in out_tester
        # Texto idéntico salvo posibles secciones específicas
        assert "Solo RECHAZADO si encontrás bloqueantes reales" in out_qa
        assert "Solo RECHAZADO si encontrás bloqueantes reales" in out_tester

    def test_evidence_strict_true_inyecta_pass_fail(self):
        c = AgentConfig(evidence_strict=True)
        out = build_prompt_injection("tester", c)
        assert "[PASS]" in out
        assert "[FAIL]" in out
        assert "[N/A" in out
        assert "STRICT" in out

    def test_evidence_strict_false_inyecta_permissive(self):
        # Default es False, así que no inyecta nada — pero si se setea explícito
        # a False y otro campo cambió, igual no aparece (es default)
        # Probamos que si el valor != default sí aparece
        c = AgentConfig(evidence_strict=False, strictness="permissive")
        out = build_prompt_injection("qa", c)
        # evidence_strict=False es el default → no inyecta el bloque PERMISSIVE de evidence
        assert "Formato de evidencia" not in out

    def test_evidence_strict_aplica_a_qa_y_tester(self):
        c_strict = AgentConfig(evidence_strict=True)
        out_qa = build_prompt_injection("qa", c_strict)
        out_tester = build_prompt_injection("tester", c_strict)
        assert "[PASS]" in out_qa
        assert "[PASS]" in out_tester

    def test_evidence_strict_no_aplica_a_otros_agentes(self):
        # Si el agente no es qa/tester, evidence_strict no se inyecta
        c = AgentConfig(evidence_strict=True)
        out_dev = build_prompt_injection("dev", c)
        out_pm = build_prompt_injection("pm", c)
        assert "[PASS]" not in out_dev
        assert "[PASS]" not in out_pm

    def test_load_qa_config(self, tmp_path):
        # Persistencia roundtrip para qa
        c = AgentConfig(strictness="permissive", evidence_strict=False)
        save_agent_config(str(tmp_path), "qa", c)
        loaded = load_agent_config(str(tmp_path), "qa")
        assert loaded.strictness == "permissive"
        assert loaded.evidence_strict is False

    def test_from_dict_coacciona_evidence_strict(self):
        c = from_dict({"evidence_strict": 1})
        assert c.evidence_strict is True
        c = from_dict({"evidence_strict": 0})
        assert c.evidence_strict is False


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
