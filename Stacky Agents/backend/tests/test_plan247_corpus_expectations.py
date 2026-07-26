"""Plan 247 F5 CAPSTONE — el perfil de los 9 golden REALES contra la tabla escrita a mano.

11 campos x 9 pipelines = 99 aserciones exactas (C7).
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import pytest
import yaml

from services import pipeline_profiler as pp
from services.pipeline_profiler import CONF_HIGH, field_is_coherent

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "cicd_nl" / "golden"

# Plan 247 F5 — expectativas escritas a mano contra los 9 pipelines REALES.
# Formato: nombre -> (stack, build, test, publish_artifact, deploy, publicados, consumidos,
#                     entornos_literales, agentes, triggers, not_understood)
EXPECTATIVAS = {
 "agendaweb-ci.yml": (
   ("dotnet_framework",), True, True, True, False,
   ("$(ARTIFACT_NAME)",), (), (), (("hosted", "windows-2022"),), ("manual",), ()),

 "bootstrap-server-environment.yml": (
   (), False, False, True, False,
   ("BootstrapLogs-${{ parameters.targetEnvironment }}-$(Build.BuildNumber)",), (),
   ("${{ parameters.targetEnvironment }}",),
   (("self_hosted", "${{ parameters.agentPool }}"),), ("manual",), ("compile_time_expression",)),

 "cd-deploy-test.yml": (
   ("dotnet_framework",), True, False, True, True,
   ("AgendaWeb", "Batch", "DeployLogs-AgendaWeb-$(Build.BuildNumber)",
    "DeployLogs-Batch-$(Build.BuildNumber)"),
   ("AgendaWeb", "Batch"), ("Test",),
   (("hosted", "windows-2022"), ("self_hosted", "TEST-Server")), ("push",), ()),

 "ci-batch.yml": (
   ("dotnet_framework",), True, False, False, False,
   (), (), (), (("hosted", "windows-2022"),), ("push", "pr"), ("matrix",)),

 "ci-cd-online.yml": (
   ("dotnet_framework",), True, True, True, False,
   ("AgendaWeb-drop",), (), (), (("hosted", "windows-2022"),), ("push",), ()),

 "ci-dacpac.yml": (
   ("dotnet_core", "sql_dacpac"), True, False, True, False,
   ("dacpac-$(Build.BuildNumber)",), (), (), (("hosted", "ubuntu-latest"),), ("push", "pr"), ()),

 "nightly-build-online.yml": (
   ("dotnet_framework",), True, True, True, False,
   ("AgendaWeb-nightly-$(Build.BuildNumber)",), (), (), (("hosted", "windows-2022"),),
   ("scheduled",), ()),

 "pr-validation-online.yml": (
   ("dotnet_framework",), True, True, False, False,
   (), (), (), (("hosted", "windows-2022"),), ("push", "pr"), ()),

 "security-scan-online.yml": (
   (), False, False, True, False,
   ("vulnerability-report-$(Build.BuildNumber)",), (), (), (("hosted", "windows-2022"),),
   ("push", "pr", "scheduled"), ()),
}


def _perfilar(nombre: str):
    path = GOLDEN / nombre
    return pp.profile_pipeline(path.read_text(encoding="utf-8"), source_path=nombre)


def test_los_nueve_golden_estan():
    assert len(list(GOLDEN.glob("*.yml"))) == 9


def test_expectativas_cubren_los_nueve():
    assert set(EXPECTATIVAS) == {p.name for p in GOLDEN.glob("*.yml")}


@pytest.mark.parametrize("nombre", sorted(EXPECTATIVAS))
def test_perfil_por_pipeline(nombre):
    (stack, build, test, publish, deploy, publicados, consumidos,
     entornos, agentes, triggers, not_understood) = EXPECTATIVAS[nombre]
    perfil = _perfilar(nombre)
    assert perfil.stack.value == stack, "stack"
    assert perfil.phases["build"].value is build, "build"
    assert perfil.phases["test"].value is test, "test"
    assert perfil.phases["publish_artifact"].value is publish, "publish_artifact"
    assert perfil.phases["deploy"].value is deploy, "deploy"
    assert perfil.artifacts_published.value == publicados, "publicados"
    assert perfil.artifacts_consumed.value == consumidos, "consumidos"
    assert tuple(e.name for e in perfil.environments.value) == entornos, "entornos"
    assert tuple((a.kind, a.name) for a in perfil.agents.value) == agentes, "agentes"
    assert perfil.triggers.value == triggers, "triggers"
    assert perfil.not_understood == not_understood, "not_understood"


def test_ningun_perfil_lanza():
    for nombre in EXPECTATIVAS:
        perfil = _perfilar(nombre)
        assert perfil.parse_error is None


def test_sin_valor_sin_confianza():
    """K3 — invariante anti-alucinación sobre TODOS los campos de los 9."""
    for nombre in EXPECTATIVAS:
        perfil = _perfilar(nombre)
        campos = [perfil.stack, perfil.artifacts_published, perfil.artifacts_consumed,
                  perfil.environments, perfil.agents, perfil.triggers]
        campos += list(perfil.phases.values())
        for campo in campos:
            assert field_is_coherent(campo), (nombre, campo)


def test_proposito_es_determinista_y_acotado():
    for nombre in EXPECTATIVAS:
        a = _perfilar(nombre)
        b = _perfilar(nombre)
        assert a.purpose.strip(), nombre
        assert "\n" not in a.purpose, nombre
        assert len(a.purpose) <= pp.PURPOSE_MAX_CHARS, nombre
        assert a.purpose_source == "plantilla", nombre
        assert a.purpose == b.purpose, nombre


def test_ausencia_de_tests_declarada():
    """K2 — la ausencia es un HECHO verificado, no un silencio."""
    for nombre in ("cd-deploy-test.yml", "ci-batch.yml", "ci-dacpac.yml",
                   "bootstrap-server-environment.yml", "security-scan-online.yml"):
        campo = _perfilar(nombre).phases["test"]
        assert campo.value is False, nombre
        assert campo.confidence == CONF_HIGH, nombre


def test_perfila_lo_que_no_entiende():
    """K5 — perfil completo AUNQUE haya construcciones no modeladas."""
    for nombre in ("ci-batch.yml", "bootstrap-server-environment.yml"):
        perfil = _perfilar(nombre)
        assert perfil.not_understood
        assert perfil.agents.value
        assert perfil.phases and len(perfil.phases) == len(pp.PHASE_IDS)
        assert perfil.triggers.value


def test_los_nueve_en_menos_de_un_segundo():
    """K6 — perfilar el corpus entero es barato."""
    textos = {n: (GOLDEN / n).read_text(encoding="utf-8") for n in EXPECTATIVAS}
    inicio = time.monotonic()
    for nombre, texto in textos.items():
        pp.profile_pipeline(texto, source_path=nombre)
    assert (time.monotonic() - inicio) < 1.0


def _todas_las_evidencias(perfil):
    campos = [perfil.stack, perfil.artifacts_published, perfil.artifacts_consumed,
              perfil.environments, perfil.agents, perfil.triggers]
    campos += list(perfil.phases.values())
    for campo in campos:
        for ev in campo.evidence:
            yield ev


def test_task_comentada_no_entra_al_perfil():
    """R3 / ADO-369 — un `- task:` comentado NO existe para el perfilador."""
    casos = {
        "agendaweb-ci.yml": "IISWebAppDeploymentOnMachineGroup@0",
        "ci-dacpac.yml": "SqlAzureDacpacDeployment@1",
    }
    for nombre, ref in casos.items():
        crudo = (GOLDEN / nombre).read_text(encoding="utf-8")
        assert ref in crudo, "%s: el fixture ya no tiene la task comentada" % nombre
        perfil = _perfilar(nombre)
        for ev in _todas_las_evidencias(perfil):
            assert ref not in ev.detail, (nombre, ev)
        assert perfil.phases["deploy"].value is False, nombre


_ENV_LOC_RE = re.compile(r"^(?:stages\[(\d+)\]\.)?jobs\[(\d+)\]\.environment$")
_TOP_LEVEL_LOCS = ("pool", "trigger", "pr", "schedules")


def test_toda_evidencia_apunta_a_un_lugar_real():
    """[ADICIÓN ARQUITECTO 1] — de 'hay evidencia' a 'la evidencia es verificable'."""
    for nombre in EXPECTATIVAS:
        doc = yaml.safe_load((GOLDEN / nombre).read_text(encoding="utf-8"))
        pasos = {ctx.location for ctx in pp.iter_step_contexts(doc)}
        perfil = _perfilar(nombre)
        for ev in _todas_las_evidencias(perfil):
            loc = ev.location
            if loc == "(documento)":
                continue
            if loc in pasos:
                continue
            if loc in _TOP_LEVEL_LOCS and loc in doc:
                continue
            match = _ENV_LOC_RE.match(loc)
            assert match, "%s: location inventada %r" % (nombre, loc)
            stage_idx, job_idx = match.group(1), int(match.group(2))
            if stage_idx is None:
                jobs = doc.get("jobs") or []
            else:
                stages = doc.get("stages") or []
                assert int(stage_idx) < len(stages), (nombre, loc)
                jobs = stages[int(stage_idx)].get("jobs") or []
            assert job_idx < len(jobs), (nombre, loc)
            assert "environment" in jobs[job_idx], (nombre, loc)
