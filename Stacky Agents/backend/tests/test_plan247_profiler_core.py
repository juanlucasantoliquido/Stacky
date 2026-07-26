"""Plan 247 F0+F1 — contrato del perfil, reuso del recorredor, stack/agentes/triggers.

27 funciones: 12 de F0 + 15 de F1.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from services import cicd_semantic_rules
from services import pipeline_profiler as pp
from services.pipeline_profiler import (
    CONF_HIGH,
    CONF_UNKNOWN,
    Evidence,
    ProfileField,
    empty_profile,
    field_is_coherent,
    profile_to_dict,
)

BACKEND = Path(__file__).resolve().parent.parent


def _task_doc(*tasks) -> dict:
    return {"steps": [dict(t) for t in tasks]}


# ══════════════════════════ F0 — contrato ══════════════════════════

def test_contract_version_declarada():
    assert pp.CONTRACT_VERSION == "247.1"


def test_field_con_valor_exige_evidencia():
    assert field_is_coherent(ProfileField(("dotnet_framework",), CONF_HIGH, ())) is False


def test_field_con_valor_no_puede_ser_desconocido():
    assert field_is_coherent(ProfileField(True, CONF_UNKNOWN, (Evidence("x", "y"),))) is False


def test_field_vacio_desconocido_es_coherente():
    assert field_is_coherent(ProfileField((), CONF_UNKNOWN, ())) is True
    assert field_is_coherent(ProfileField(False, CONF_UNKNOWN, ())) is True


def test_empty_profile_es_serializable():
    json.dumps(profile_to_dict(empty_profile("x.yml", "boom")))


def test_profile_to_dict_claves_estables():
    dto = profile_to_dict(empty_profile("x.yml"))
    assert set(dto) == {
        "contract_version", "source_path", "stack", "phases", "artifacts_published",
        "artifacts_consumed", "environments", "agents", "triggers", "purpose",
        "purpose_source", "not_understood", "parse_error",
    }
    assert len(dto) == 13


def test_iter_step_contexts_es_el_mismo_objeto():
    assert pp.iter_step_contexts is cicd_semantic_rules._iter_steps
    assert pp.StepContext is cicd_semantic_rules._StepCtx


def test_no_se_edito_cicd_semantic_rules():
    fuente = (BACKEND / "services" / "cicd_semantic_rules.py").read_text(encoding="utf-8")
    assert "iter_step_contexts" not in fuente


def test_max_yaml_bytes_es_el_del_motor():
    assert pp.MAX_YAML_BYTES is cicd_semantic_rules.MAX_YAML_BYTES


def test_iter_step_contexts_cubre_las_tres_raices():
    raiz = {"steps": [{"task": "VSBuild@1"}]}
    jobs = {"jobs": [{"job": "A", "steps": [{"task": "VSBuild@1"}]}]}
    stages = {"stages": [{"stage": "S", "jobs": [{"job": "A", "steps": [{"task": "VSBuild@1"}]}]}]}
    assert [c.location for c in pp.iter_step_contexts(raiz)] == ["steps[0]"]
    assert [c.location for c in pp.iter_step_contexts(jobs)] == ["jobs[0].steps[0]"]
    assert [c.location for c in pp.iter_step_contexts(stages)] == ["stages[0].jobs[0].steps[0]"]


def test_stack_to_detector_id_no_inventa():
    assert set(pp.STACK_TO_DETECTOR_ID.values()) <= {"dotnet", "node", "python", None}


def test_empty_profile_es_coherente():
    perfil = empty_profile("x.yml", "roto")
    for campo in (perfil.stack, perfil.artifacts_published, perfil.artifacts_consumed,
                  perfil.environments, perfil.agents, perfil.triggers):
        assert field_is_coherent(campo)
    assert perfil.parse_error == "roto"


# ══════════════════════════ F1 — stack ══════════════════════════

def test_vsbuild_implica_dotnet_framework():
    campo = pp.detect_pipeline_stacks(_task_doc({"task": "VSBuild@1"}))
    assert campo.value == ("dotnet_framework",)
    assert campo.confidence == CONF_HIGH
    assert campo.evidence


def test_dotnet_test_no_implica_dotnet_core():
    campo = pp.detect_pipeline_stacks(
        _task_doc({"task": "DotNetCoreCLI@2", "inputs": {"command": "test"}}))
    assert campo.value == ()
    assert campo.confidence == CONF_UNKNOWN


def test_sqlproj_implica_sql_dacpac():
    campo = pp.detect_pipeline_stacks(
        _task_doc({"task": "DotNetCoreCLI@2",
                   "inputs": {"command": "build", "projects": "x/y.sqlproj"}}))
    assert "sql_dacpac" in campo.value


def test_stack_multiple_respeta_precedencia():
    campo = pp.detect_pipeline_stacks(_task_doc(
        {"task": "CopyFiles@2", "inputs": {"Contents": "**/*.dacpac"}},
        {"task": "UseDotNet@2"},
    ))
    assert campo.value == ("dotnet_core", "sql_dacpac")


def test_stack_sin_senal_es_desconocido():
    campo = pp.detect_pipeline_stacks(
        _task_doc({"task": "PowerShell@2", "inputs": {"filePath": "x.ps1"}}))
    assert campo.value == ()
    assert campo.confidence == CONF_UNKNOWN


def test_node_python_container_sinteticos():
    assert pp.detect_pipeline_stacks(_task_doc({"task": "Npm@1"})).value == ("node",)
    assert pp.detect_pipeline_stacks(_task_doc({"task": "NodeTool@0"})).value == ("node",)
    assert pp.detect_pipeline_stacks(_task_doc({"task": "UsePythonVersion@0"})).value == ("python",)
    assert pp.detect_pipeline_stacks(_task_doc({"task": "Docker@2"})).value == ("container",)
    # C18: `container:` en cualquier nivel del doc, no sólo en la raíz.
    anidado = {"jobs": [{"job": "A", "container": "img:1", "steps": []}]}
    assert pp.detect_pipeline_stacks(anidado).value == ("container",)


# ══════════════════════════ F1 — agentes ══════════════════════════

def test_pool_hosted_vs_self_hosted():
    doc = {"stages": [
        {"stage": "B", "pool": {"vmImage": "windows-2022"},
         "jobs": [{"job": "b", "steps": [{"task": "VSBuild@1"}]}]},
        {"stage": "D", "pool": {"name": "TEST-Server"},
         "jobs": [{"job": "d", "steps": [{"script": "echo"}]}]},
    ]}
    campo = pp.detect_agents(doc)
    assert [(a.kind, a.name) for a in campo.value] == [
        ("hosted", "windows-2022"), ("self_hosted", "TEST-Server")]


def test_pool_self_hosted_os_es_none():
    doc = {"pool": {"name": "TEST-Server"}, "steps": [{"script": "echo"}]}
    assert pp.detect_agents(doc).value[0].os is None


def test_pool_heredado_de_la_raiz():
    doc = {"pool": {"vmImage": "ubuntu-latest"},
           "jobs": [{"job": "a", "steps": [{"script": "echo"}]}]}
    campo = pp.detect_agents(doc)
    assert len(campo.value) == 1
    assert campo.value[0].kind == "hosted"
    assert campo.value[0].name == "ubuntu-latest"


# ══════════════════════════ F1 — triggers ══════════════════════════

def test_trigger_none_es_manual():
    assert pp.detect_triggers({"trigger": "none", "pr": "none"}).value == ("manual",)


def test_trigger_ausente_es_push():
    assert pp.detect_triggers({}).value == ("push", "pr")


def test_schedules_es_scheduled():
    campo = pp.detect_triggers({"trigger": "none", "pr": "none",
                                "schedules": [{"cron": "0 5 * * 1-5"}]})
    assert "scheduled" in campo.value
    assert "manual" not in campo.value


# ══════════════════════════ F1 — profile_pipeline ══════════════════════════

def test_provider_invalido_lanza():
    with pytest.raises(ValueError):
        pp.profile_pipeline("a: 1", provider="gitlab")


def test_yaml_roto_devuelve_parse_error():
    perfil = pp.profile_pipeline("a: [\n")
    assert perfil.parse_error
    assert perfil.stack.value == ()


def test_yaml_gigante_no_se_procesa():
    perfil = pp.profile_pipeline("a: 1\n" * 200000)
    assert perfil.parse_error and "512 KB" in perfil.parse_error
