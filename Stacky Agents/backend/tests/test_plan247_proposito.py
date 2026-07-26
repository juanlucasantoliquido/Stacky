"""Plan 247 F3 — propósito: plantilla determinista + narración LLM opcional. 15 casos."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from services import pipeline_profiler as pp
from services.pipeline_profiler import (
    CONF_HIGH,
    CONF_UNKNOWN,
    AgentPool,
    Evidence,
    PipelineProfile,
    ProfileField,
    build_purpose_template,
    narrate_purpose,
)

BACKEND = Path(__file__).resolve().parent.parent
GOLDEN = BACKEND / "tests" / "fixtures" / "cicd_nl" / "golden"


def _perfil(**over) -> PipelineProfile:
    fases = {p: ProfileField(False, CONF_HIGH, (Evidence("(documento)", "sin senal"),))
             for p in pp.PHASE_IDS}
    base = dict(
        contract_version=pp.CONTRACT_VERSION,
        source_path="x.yml",
        stack=ProfileField(("dotnet_framework",), CONF_HIGH, (Evidence("steps[0]", "task VSBuild@1"),)),
        phases=fases,
        artifacts_published=ProfileField((), CONF_UNKNOWN, ()),
        artifacts_consumed=ProfileField((), CONF_UNKNOWN, ()),
        environments=ProfileField((), CONF_UNKNOWN, ()),
        agents=ProfileField((AgentPool("hosted", "windows-2022", True),), CONF_HIGH,
                            (Evidence("steps[0]", "vmImage: windows-2022"),)),
        triggers=ProfileField(("push",), CONF_HIGH, (Evidence("trigger", "bloque trigger"),)),
    )
    base.update(over)
    return PipelineProfile(**base)


class _Resultado:
    def __init__(self, success, parsed_json=None):
        self.success = success
        self.parsed_json = parsed_json


# ── plantilla ─────────────────────────────────────────────────────────────────

def test_plantilla_es_determinista():
    p = _perfil()
    assert build_purpose_template(p) == build_purpose_template(p)


def test_plantilla_menciona_ausencia_de_tests():
    assert "No corre tests." in build_purpose_template(_perfil())


def test_plantilla_no_miente_si_test_es_desconocido():
    fases = dict(_perfil().phases)
    fases["test"] = ProfileField(False, CONF_UNKNOWN, (Evidence("(documento)", "template"),))
    assert "No corre tests." not in build_purpose_template(_perfil(phases=fases))


def test_plantilla_sin_fases_lo_dice():
    assert "No compila" in build_purpose_template(_perfil())


def test_plantilla_omite_stack_vacio():
    texto = build_purpose_template(_perfil(stack=ProfileField((), CONF_UNKNOWN, ())))
    assert "para " not in texto


def test_plantilla_respeta_el_techo():
    artefactos = tuple("artefacto-larguisimo-%03d" % i for i in range(80))
    inflado = _perfil(
        artifacts_published=ProfileField(artefactos, CONF_HIGH,
                                         (Evidence("steps[0]", "pub"),)),
        agents=ProfileField(
            tuple(AgentPool("self_hosted", "servidor-numero-%03d" % i, None) for i in range(50)),
            CONF_HIGH, (Evidence("steps[0]", "pool"),)),
    )
    assert len(build_purpose_template(inflado)) <= pp.PURPOSE_MAX_CHARS


# ── narración ─────────────────────────────────────────────────────────────────

def test_narrate_sin_llm_usa_plantilla():
    p = _perfil()
    assert narrate_purpose(p) == (build_purpose_template(p), "plantilla")


def test_narrate_con_llm_ok():
    texto, fuente = narrate_purpose(_perfil(),
                                    llm_caller=lambda spec: _Resultado(True, {"purpose": "X"}))
    assert (texto, fuente) == ("X", "llm")


def test_narrate_con_llm_fallido_cae_a_plantilla():
    p = _perfil()
    texto, fuente = narrate_purpose(p, llm_caller=lambda spec: _Resultado(False))
    assert fuente == "plantilla" and texto == build_purpose_template(p)


def test_narrate_con_llm_que_explota_cae_a_plantilla():
    def _explota(spec):
        raise RuntimeError("boom")

    p = _perfil()
    texto, fuente = narrate_purpose(p, llm_caller=_explota)
    assert fuente == "plantilla" and texto == build_purpose_template(p)


def test_narrate_descarta_texto_largo():
    largo = "x" * 500
    _texto, fuente = narrate_purpose(
        _perfil(), llm_caller=lambda spec: _Resultado(True, {"purpose": largo}))
    assert fuente == "plantilla"


def test_narrate_colapsa_multilinea():
    texto, fuente = narrate_purpose(
        _perfil(), llm_caller=lambda spec: _Resultado(True, {"purpose": "a\nb"}))
    assert (texto, fuente) == ("a b", "llm")


def test_narrate_recibe_el_perfil_no_el_yaml():
    capturado = {}

    def _captura(spec):
        capturado["spec"] = spec
        return _Resultado(True, {"purpose": "X"})

    narrate_purpose(_perfil(), llm_caller=_captura)
    payload = json.loads(capturado["spec"].user)
    assert "contract_version" in payload


def test_purpose_call_spec_no_derivo_del_contrato():
    """Centinela: el spec local del perfilador sigue siendo aceptable por el cliente real.

    El plan escribia `LLMCallSpec(system=..., user=..., expect_json=..., temperature=...,
    fixture_id=...)`, pero ese dataclass exige ADEMAS project/agent_kind/prompt_type/model
    sin default: la llamada del plan levantaba TypeError y el try/except la tapaba en
    silencio (siempre plantilla). El perfilador usa un spec propio para NO importar el
    cliente (K4-a); este test es el que se pone rojo si el contrato del cliente deriva.
    """
    import dataclasses

    from services.pm.pm_llm_client import LLMCallSpec

    reales = {f.name for f in dataclasses.fields(LLMCallSpec)}
    obligatorios = {f.name for f in dataclasses.fields(LLMCallSpec)
                    if f.default is dataclasses.MISSING
                    and f.default_factory is dataclasses.MISSING}
    propios = {f.name for f in dataclasses.fields(pp.PurposeCallSpec)}
    assert propios <= reales, propios - reales
    assert obligatorios <= propios, obligatorios - propios


def test_profile_pipeline_rellena_purpose():
    texto = (GOLDEN / "agendaweb-ci.yml").read_text(encoding="utf-8")
    perfil = pp.profile_pipeline(texto, source_path="agendaweb-ci.yml")
    assert perfil.purpose.strip()
    assert "\n" not in perfil.purpose
    assert perfil.purpose_source == "plantilla"


def test_perfil_no_llama_al_llm(monkeypatch):
    """K4 — 3 aserciones que SI pueden fallar si alguien mete un modelo en el camino default."""
    # (a) el modulo no nombra el cliente de modelo ni en un comentario de import.
    fuente = (BACKEND / "services" / "pipeline_profiler.py").read_text(encoding="utf-8")
    assert "pm_llm_client" not in fuente

    # (b) perfilar los 9 golden no deja el modulo del cliente cargado.
    sys.modules.pop("services.pm.pm_llm_client", None)
    for path in sorted(GOLDEN.glob("*.yml")):
        pp.profile_pipeline(path.read_text(encoding="utf-8"), source_path=path.name)
    assert "services.pm.pm_llm_client" not in sys.modules

    # (c) el endpoint SIN narrate responde 200 con plantilla, con call_llm explotando.
    def _explota(spec):
        raise RuntimeError("el camino default NO puede llamar al modelo")

    monkeypatch.setattr("services.pm.pm_llm_client.call_llm", _explota)
    from app import create_app
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_PROFILER_ENABLED", True, raising=False)
    application = create_app()
    application.config["TESTING"] = True
    texto = (GOLDEN / "ci-batch.yml").read_text(encoding="utf-8")
    resp = application.test_client().post("/api/pipeline-profiler/profile",
                                          json={"yaml_text": texto})
    assert resp.status_code == 200
    assert resp.get_json()["purpose_source"] == "plantilla"
