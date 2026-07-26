"""Plan 243 F2 — renderer ADO con task:/deployment: + gates de round-trip.

Comando (§7.1 del plan):
    .venv\\Scripts\\python.exe -m pytest tests/test_plan243_renderer_ado.py -q

C14 — el "round-trip 9/9" del v2 era alcance ilimitado disfrazado de criterio binario
(exigía un AST completo de ADO YAML: matrix, 17 expresiones ${{ }}, templates...).
Se reemplaza por DOS gates acotados y honestos:

  GATE A — EMISIÓN EXACTA 3/3 sobre los goldens que el generador DEBE poder producir.
           No se relaja: si no cierra, se implementa la construcción.
  GATE B — PARSE TOLERANTE 9/9: parse_ado_yaml no lanza sobre ninguno de los 9 y la
           espina de `task:` que recupera coincide con la del yaml.safe_load crudo.
"""
from __future__ import annotations

import io
import os

import pytest
import yaml

from services.cicd_task_catalog import extract_task_refs
from services.pipeline_renderers import (
    UNSUPPORTED_CONSTRUCTS,
    parse_ado_yaml,
    scan_unsupported,
    to_ado_yaml,
)
from services.pipeline_spec import (
    DeploymentJob,
    Job,
    PipelineSpec,
    Stage,
    Step,
    TaskStep,
)

GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "cicd_nl", "golden")

# Los 3 que el generador NL debe poder producir (build+test+publish, build plano, deploy).
GATE_A_FILES = ("ci-cd-online.yml", "agendaweb-ci.yml", "cd-deploy-test.yml")

GATE_B_FILES = (
    "agendaweb-ci.yml",
    "bootstrap-server-environment.yml",
    "cd-deploy-test.yml",
    "ci-batch.yml",
    "ci-cd-online.yml",
    "ci-dacpac.yml",
    "nightly-build-online.yml",
    "pr-validation-online.yml",
    "security-scan-online.yml",
)


def _golden(name: str) -> str:
    with io.open(os.path.join(GOLDEN_DIR, name), "r", encoding="utf-8") as fh:
        return fh.read()


def _spine_of_spec(spec: PipelineSpec) -> tuple:
    """Espina de tareas recuperada por el PARSER, en orden estructural."""
    out = []
    out.extend(t.task for t in spec.root_task_steps)
    for job in spec.root_jobs:
        out.extend(t.task for t in job.task_steps)
    for stage in spec.stages:
        for job in stage.jobs:
            out.extend(t.task for t in job.task_steps)
        for dep in stage.deployments:
            out.extend(t.task for t in dep.steps)
    return tuple(out)


# ── GATE A — emisión exacta 3/3 ───────────────────────────────────────────────

@pytest.mark.parametrize("name", GATE_A_FILES)
def test_gate_a_emision_exacta(name):
    original = _golden(name)
    spec = parse_ado_yaml(original)
    reemitido = to_ado_yaml(spec)

    esperado = yaml.safe_load(original)
    obtenido = yaml.safe_load(reemitido)

    assert obtenido == esperado, (
        "GATE A roto en %s.\n--- esperado ---\n%s\n--- obtenido ---\n%s"
        % (name,
           yaml.safe_dump(esperado, sort_keys=True, allow_unicode=True),
           yaml.safe_dump(obtenido, sort_keys=True, allow_unicode=True))
    )


# ── GATE B — parse tolerante 9/9 ──────────────────────────────────────────────

@pytest.mark.parametrize("name", GATE_B_FILES)
def test_gate_b_parse_tolerante(name):
    texto = _golden(name)
    spec = parse_ado_yaml(texto)          # no lanza
    assert isinstance(spec, PipelineSpec)
    # La espina recuperada por el parser == la del yaml.safe_load crudo, en orden.
    assert _spine_of_spec(spec) == extract_task_refs(texto), name


# ── Construcciones NO modeladas, declaradas ───────────────────────────────────

def test_unsupported_declarado():
    assert "matrix" in scan_unsupported(_golden("ci-batch.yml"))
    assert "compile_time_expression" in scan_unsupported(
        _golden("bootstrap-server-environment.yml"))
    # Un pipeline plenamente modelado no declara nada.
    assert scan_unsupported(_golden("ci-cd-online.yml")) == ()


def test_allowlist_no_crece_en_silencio():
    assert UNSUPPORTED_CONSTRUCTS == (
        "matrix", "compile_time_expression", "template", "extends", "resources",
    )
    assert len(UNSUPPORTED_CONSTRUCTS) == 5


# ── Formas de emisión ─────────────────────────────────────────────────────────

def test_task_step_emite_task_displayname_inputs_en_ese_orden():
    spec = PipelineSpec(
        name="p",
        stages=(Stage(name="Build", jobs=(Job(
            name="j", steps=(),
            task_steps=(TaskStep(name="MSBuild", task="VSBuild@1",
                                 inputs={"solution": "x.sln"}),),
        ),)),),
    )
    doc = yaml.safe_load(to_ado_yaml(spec))
    step_doc = doc["stages"][0]["jobs"][0]["steps"][0]
    claves = list(step_doc.keys())
    assert claves.index("task") < claves.index("displayName") < claves.index("inputs")
    assert step_doc["task"] == "VSBuild@1"
    assert step_doc["displayName"] == "MSBuild"
    assert step_doc["inputs"] == {"solution": "x.sln"}
    # sort_keys=False sigue vigente: el YAML no sale alfabetizado.
    assert to_ado_yaml(spec).index("task:") < to_ado_yaml(spec).index("displayName:")


def test_deployment_emite_runonce_con_checkout_y_download_al_frente():
    dep = DeploymentJob(
        name="DeployWeb", environment="Test",
        display_name="Backup + Deploy local",
        download_artifacts=("AgendaWeb",),
        steps=(TaskStep(name="Deploy", task="PowerShell@2",
                        inputs={"filePath": "scripts/Deploy-Local.ps1"}),),
    )
    spec = PipelineSpec(
        name="p",
        stages=(Stage(name="Deploy", jobs=(), deployments=(dep,),
                      pool_name="TEST-Server", depends_on=("Build",)),),
    )
    doc = yaml.safe_load(to_ado_yaml(spec))
    stage = doc["stages"][0]
    assert stage["pool"] == {"name": "TEST-Server"}
    assert stage["dependsOn"] == "Build"          # 1 dependencia => escalar, como el corpus
    job = stage["jobs"][0]
    assert job["deployment"] == "DeployWeb"
    assert job["environment"] == "Test"
    steps = job["strategy"]["runOnce"]["deploy"]["steps"]
    assert steps[0] == {"checkout": "self"}
    assert steps[1] == {"download": "current", "artifact": "AgendaWeb"}
    assert steps[2]["task"] == "PowerShell@2"


def test_depends_on_multiple_emite_lista():
    spec = PipelineSpec(
        name="p",
        stages=(Stage(name="C", jobs=(Job(name="j", steps=(),
                                          task_steps=(TaskStep(name="b", task="VSBuild@1"),)),),
                      depends_on=("A", "B")),),
    )
    doc = yaml.safe_load(to_ado_yaml(spec))
    assert doc["stages"][0]["dependsOn"] == ["A", "B"]


# ── No regresión del Plan 73 ──────────────────────────────────────────────────

def test_spec_del_plan73_produce_exactamente_el_mismo_yaml():
    spec = PipelineSpec(
        name="pipeline-viejo",
        stages=(Stage(name="build", jobs=(Job(
            name="build-job",
            steps=(Step(name="compilar", script="echo hola",
                        working_directory="src", condition="always()",
                        env={"K": "V"}),),
            pool_vm_image="ubuntu-latest",
            variables={"X": "1"},
            artifacts=("dist/",),
            runner_tags=("linux",),
        ),), condition="succeeded()"),),
        variables={"G": "0"},
        trigger_branches=("main",),
    )
    esperado = (
        "name: pipeline-viejo\n"
        "trigger:\n"
        "  branches:\n"
        "    include:\n"
        "    - main\n"
        "variables:\n"
        "  G: '0'\n"
        "stages:\n"
        "- stage: build\n"
        "  condition: succeeded()\n"
        "  jobs:\n"
        "  - job: build-job\n"
        "    pool:\n"
        "      vmImage: ubuntu-latest\n"
        "    variables:\n"
        "      X: '1'\n"
        "    steps:\n"
        "    - script: echo hola\n"
        "      displayName: compilar\n"
        "      workingDirectory: src\n"
        "      condition: always()\n"
        "      env:\n"
        "        K: V\n"
        "    artifacts:\n"
        "      publish:\n"
        "      - dist/\n"
        "    demands:\n"
        "    - linux\n"
    )
    assert to_ado_yaml(spec) == esperado


def test_raw_yaml_escape_hatch_intacto():
    spec = PipelineSpec(name="p", stages=(), raw_yaml="crudo: si\n", raw_yaml_target="ado")
    assert to_ado_yaml(spec) == "crudo: si\n"
