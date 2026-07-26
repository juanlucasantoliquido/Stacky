"""Plan 248 F0 — contrato de hallazgo y espina compartida. 8 tests + el gate anti-red."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

from services import cicd_audit_core as core
from services import cicd_semantic_rules

BACKEND = Path(__file__).resolve().parent.parent
GOLDEN = BACKEND / "tests" / "fixtures" / "cicd_nl" / "golden"

_MODULOS_DEL_PLAN = (
    "services/cicd_audit_core.py",
    "services/cicd_security_rules.py",
    "services/pipeline_recommendations.py",
    "services/pipeline_audit_suppressions.py",
    "api/pipeline_audit.py",
)


def test_finding_exige_location_y_remediation():
    with pytest.raises(AssertionError):
        core.finding(code="SEC001", severity=core.SEV_ERROR, message="m",
                     location="steps[0]", line=1, evidence="e", remediation="")
    with pytest.raises(AssertionError):
        core.finding(code="SEC001", severity=core.SEV_ERROR, message="m",
                     location="", line=1, evidence="e", remediation="r")


def test_line_of_devuelve_none_si_no_esta():
    assert core.line_of(["a", "b"], "zzz") is None
    assert core.line_of([], "a") is None
    assert core.line_of(["a"], "") is None


def test_line_of_respeta_occurrence():
    lines = ["x", "hit", "y", "hit", "z"]
    assert core.line_of(lines, "hit") == 2
    assert core.line_of(lines, "hit", occurrence=2) == 4
    assert core.line_of(lines, "hit", occurrence=9) is None
    # line_of_pair ancla la evidencia cuando el corpus la menciona en un comentario
    assert core.line_of_pair(["# ubuntu-latest es barato", "  vmImage: 'ubuntu-latest'"],
                             "vmImage", "ubuntu-latest") == 2


def test_is_dynamic_reconoce_ambas_sintaxis():
    assert core.is_dynamic("${{ parameters.x }}") is True
    assert core.is_dynamic("$(Build.BuildNumber)") is True
    assert core.is_dynamic("literal") is False
    assert core.is_dynamic(None) is False
    assert core.is_dynamic(123) is False


def test_pool_self_hosted_se_abstiene_con_nombre_dinamico():
    assert core.pool_is_self_hosted({"name": "TEST-Server"}) is True
    assert core.pool_is_self_hosted({"name": "${{ parameters.agentPool }}"}) is False
    assert core.pool_is_self_hosted({"vmImage": "windows-2022"}) is False
    assert core.pool_is_self_hosted({}) is False


def test_walk_importado_es_el_del_243():
    assert core.iter_steps is cicd_semantic_rules._iter_steps
    assert core.StepCtx is cicd_semantic_rules._StepCtx
    # Si alguien reintroduce el diff de la v1, este assert se pone rojo.
    assert not hasattr(cicd_semantic_rules, "iter_steps")


def test_walk_sobre_cd_deploy_test():
    doc = yaml.safe_load((GOLDEN / "cd-deploy-test.yml").read_text(encoding="utf-8"))
    ctxs = core.iter_steps(doc)
    deploys = [c for c in ctxs if c.location.startswith("stages[1].deployments[0].steps[")]
    assert deploys
    assert deploys[0].pool == {"name": "TEST-Server"}


def test_job_key_agrupa_los_pasos_de_raiz():
    assert core.job_key("stages[1].jobs[0].steps[2]") == "stages[1].jobs[0]"
    assert core.job_key("stages[1].deployments[0].steps[2]") == "stages[1].deployments[0]"
    assert core.job_key("steps[0]") == core.job_key("steps[9]") == "(root)"


def test_job_key_sobre_pr_validation_agrupa_todo_junto():
    """El test que habria atrapado el bug de OPT002 ANTES de escribir OPT002."""
    doc = yaml.safe_load((GOLDEN / "pr-validation-online.yml").read_text(encoding="utf-8"))
    claves = {core.job_key(c.location) for c in core.iter_steps(doc)}
    assert claves == {"(root)"}


def test_modulos_sin_red_ni_llm():
    """C10 — gate por AST, NUNCA por grep sobre el texto (un centinela textual se
    autocolisiona con la prosa que lo describe)."""
    prohibidos = {"requests", "httpx", "urllib", "socket", "pm_llm_client", "copilot_bridge"}
    for rel in _MODULOS_DEL_PLAN:
        tree = ast.parse((BACKEND / rel).read_text(encoding="utf-8"))
        importados = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    importados.update(alias.name.split("."))
            elif isinstance(node, ast.ImportFrom):
                importados.update((node.module or "").split("."))
                for alias in node.names:
                    importados.add(alias.name)
        assert not (importados & prohibidos), (rel, importados & prohibidos)
