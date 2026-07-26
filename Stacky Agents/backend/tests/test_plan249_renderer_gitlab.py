"""Plan 249 F3 — el renderer GitLab deja de emitir pipelines vacías. K1, K2, K3."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

from services.pipeline_renderers import (
    TASK_TRANSLATION_MAP,
    UNTRANSLATABLE_TASK_MARKER,
    _task_step_to_script_lines,
    parse_ado_yaml,
    to_ado_yaml,
    to_gitlab_yaml,
)
from services.pipeline_spec import DeploymentJob, Job, Step, TaskStep

BACKEND = Path(__file__).resolve().parent.parent
GOLDEN = BACKEND / "tests" / "fixtures" / "cicd_nl" / "golden"
DERIVED = BACKEND / "tests" / "fixtures" / "cicd_gitlab" / "derived"

if str(BACKEND / "scripts") not in sys.path:
    sys.path.insert(0, str(BACKEND / "scripts"))
import regen_gitlab_derived_corpus as regen  # noqa: E402


def _specs():
    for path in sorted(GOLDEN.glob("*.yml")):
        yield path.name, parse_ado_yaml(path.read_text(encoding="utf-8"))


def _task_steps(spec) -> list:
    out = list(spec.root_task_steps)
    for jb in spec.root_jobs:
        out += list(jb.task_steps)
    for st in spec.stages:
        for jb in st.jobs:
            out += list(jb.task_steps)
        for dp in st.deployments:
            out += list(dp.steps)
    return out


def _script_lines(doc: dict) -> list:
    out = []
    for value in doc.values():
        if isinstance(value, dict):
            out.extend(str(x) for x in (value.get("script") or []))
    return out


def test_k1_los_9_derivados_emiten_comandos():
    """K1: 9/9 — ningun pipeline emitido queda sin un solo comando."""
    for nombre, spec in _specs():
        doc = yaml.safe_load(to_gitlab_yaml(spec))
        reales = [ln for ln in _script_lines(doc)
                  if ln.strip() and ln.strip() != "echo 'no-op'"]
        assert reales, nombre


def test_k2_los_51_task_steps_sobreviven():
    """K2: 51/51. Las dos sumas se CALCULAN; el 51 queda como assert de sanidad."""
    total_task_steps = 0
    total_lineas = 0
    for _nombre, spec in _specs():
        pasos = _task_steps(spec)
        total_task_steps += len(pasos)
        total_lineas += sum(len(_task_step_to_script_lines(t)) for t in pasos)
    assert total_lineas == total_task_steps
    assert total_task_steps == 51, total_task_steps


def test_deployment_con_step_crudo_no_revienta():
    """C6 — F3 no depende del accidente de _parse_deployment."""
    dp = DeploymentJob(name="D", environment="Test", steps=(Step(name="s", script="echo hola"),))
    from services.pipeline_renderers import _deployment_doc_gitlab

    assert _deployment_doc_gitlab(dp, "deploy")["script"] == ["echo hola"]


def test_k3_los_3_deployments_emiten_environment():
    """K3: 3/3."""
    vistos = 0
    for _nombre, spec in _specs():
        doc = yaml.safe_load(to_gitlab_yaml(spec))
        for st in spec.stages:
            for dp in st.deployments:
                jd = doc[dp.name]
                assert jd["environment"] == dp.environment
                assert jd["when"] == "manual"
                vistos += 1
    assert vistos == 3


def test_raices_no_se_pierden():
    for nombre in ("agendaweb-ci.yml", "nightly-build-online.yml", "ci-batch.yml"):
        spec = parse_ado_yaml((GOLDEN / nombre).read_text(encoding="utf-8"))
        doc = yaml.safe_load(to_gitlab_yaml(spec))
        jobs = [k for k, v in doc.items() if isinstance(v, dict)]
        assert jobs, nombre


def test_depends_on_se_emite_como_needs():
    from services.pipeline_spec import PipelineSpec, Stage

    spec = PipelineSpec(name="x", stages=(Stage(name="s", jobs=(
        Job(name="B", steps=(Step(name="p", script="make"),), depends_on=("A",)),)),))
    assert yaml.safe_load(to_gitlab_yaml(spec))["B"]["needs"] == ["A"]


def test_pool_name_se_emite_como_tag():
    from services.pipeline_spec import PipelineSpec, Stage

    spec = PipelineSpec(name="x", stages=(Stage(name="s", jobs=(
        Job(name="B", steps=(Step(name="p", script="make"),), pool_name="RSPacifico"),)),))
    assert yaml.safe_load(to_gitlab_yaml(spec))["B"]["tags"] == ["RSPacifico"]


def test_tarea_sin_equivalente_se_marca_no_se_inventa():
    lineas = _task_step_to_script_lines(TaskStep(name="b", task="VSBuild@1", inputs={"solution": "x.sln"}))
    assert len(lineas) == 1
    assert lineas[0].startswith(UNTRANSLATABLE_TASK_MARKER)
    assert "msbuild" not in lineas[0].lower()


def test_translation_map_es_cerrado():
    assert set(TASK_TRANSLATION_MAP) == {"DotNetCoreCLI@2", "PowerShell@2", "CopyFiles@2"}


def test_powershell_inline_no_se_traduce():
    inline = _task_step_to_script_lines(
        TaskStep(name="p", task="PowerShell@2", inputs={"script": "Write-Host hola"}))
    assert inline[0].startswith(UNTRANSLATABLE_TASK_MARKER)
    con_archivo = _task_step_to_script_lines(
        TaskStep(name="p", task="PowerShell@2", inputs={"filePath": "x.ps1"}))
    assert con_archivo == ["pwsh -File x.ps1"]


def test_ado_intacto():
    """P6/P10 — el camino ADO no cambió."""
    for nombre, spec in _specs():
        assert to_ado_yaml(spec), nombre
        assert "TODO(stacky-249)" not in to_ado_yaml(spec), nombre


def test_foto_del_defecto_actualizada():
    """El corpus derivado en disco corresponde al renderer POST-F3."""
    for origen in sorted(GOLDEN.glob("*.yml")):
        destino = DERIVED / regen.derived_name(origen.name)
        esperado = (regen.PROVENANCE_HEADER_FMT % origen.name) + regen.render_derived(
            origen.read_text(encoding="utf-8"))
        assert destino.read_text(encoding="utf-8") == esperado, origen.name
    con_marca = [p.name for p in DERIVED.glob("*.yml")
                 if UNTRANSLATABLE_TASK_MARKER in p.read_text(encoding="utf-8")]
    assert len(con_marca) >= 7, con_marca
