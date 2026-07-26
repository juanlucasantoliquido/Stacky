"""Plan 247 F2 — anatomía de fases (incluidas las AUSENTES), artefactos y entornos.

20 funciones de test.
"""
from __future__ import annotations

from services import pipeline_profiler as pp
from services.pipeline_profiler import CONF_HIGH, CONF_MEDIUM, CONF_UNKNOWN


def _doc(*steps) -> dict:
    return {"steps": [dict(s) for s in steps]}


def _phases(doc, not_understood=()):
    return pp.detect_phases(doc, not_understood)


# ── build ─────────────────────────────────────────────────────────────────────

def test_build_por_vsbuild():
    campo = _phases(_doc({"task": "VSBuild@1"}))["build"]
    assert campo.value is True
    assert campo.confidence == CONF_HIGH
    assert campo.evidence


def test_build_por_dotnet_build():
    campo = _phases(_doc({"task": "DotNetCoreCLI@2", "inputs": {"command": "build"}}))["build"]
    assert campo.value is True
    assert campo.confidence == CONF_HIGH


# ── test ──────────────────────────────────────────────────────────────────────

def test_test_por_dotnet_test():
    campo = _phases(_doc({"task": "DotNetCoreCLI@2", "inputs": {"command": "test"}}))["test"]
    assert campo.value is True


def test_test_por_publish_test_results():
    assert _phases(_doc({"task": "PublishTestResults@2"}))["test"].value is True
    assert _phases(_doc({"task": "VSTest@2"}))["test"].value is True


def test_ausencia_de_test_es_hecho_no_silencio():
    campo = _phases(_doc({"task": "VSBuild@1"}))["test"]
    assert campo.value is False
    assert campo.confidence == CONF_HIGH
    assert campo.evidence and campo.evidence[0].detail


# ── degradación ───────────────────────────────────────────────────────────────

def test_template_degrada_toda_ausencia():
    fases = _phases({"steps": [{"template": "x.yml"}]}, not_understood=("template",))
    for phase_id in pp.PHASE_IDS:
        assert fases[phase_id].value is False
        assert fases[phase_id].confidence == CONF_UNKNOWN


def test_matrix_no_degrada_la_anatomia():
    fases = _phases(_doc({"task": "VSBuild@1"}), not_understood=("matrix",))
    assert fases["build"].value is True and fases["build"].confidence == CONF_HIGH
    assert fases["test"].value is False and fases["test"].confidence == CONF_HIGH


def test_compile_time_expression_no_degrada():
    fases = _phases(_doc({"task": "VSBuild@1", "inputs": {"solution": "${{ parameters.sln }}"}}),
                    not_understood=("compile_time_expression",))
    assert fases["build"].value is True
    assert fases["test"].confidence == CONF_HIGH


# ── package / deploy ──────────────────────────────────────────────────────────

def test_package_tiene_confianza_media():
    campo = _phases(_doc({"task": "VSBuild@1",
                          "inputs": {"msbuildArgs": "/p:WebPublishMethod=Package"}}))["package"]
    assert campo.value is True
    assert campo.confidence == CONF_MEDIUM


def test_copyfiles_sin_staging_no_es_package():
    campo = _phases(_doc({"task": "CopyFiles@2",
                          "inputs": {"Contents": "**/*.dll", "TargetFolder": "C:/tmp"}}))["package"]
    assert campo.value is False


def test_deploy_reusa_is_deploy_step():
    campo = _phases(_doc({"task": "PowerShell@2",
                          "inputs": {"filePath": "scripts/Deploy-Local.ps1"}}))["deploy"]
    assert campo.value is True


def test_initialize_no_es_deploy():
    campo = _phases(_doc({"task": "PowerShell@2",
                          "inputs": {"filePath": "scripts/Initialize-ServerEnvironment.ps1"}}))["deploy"]
    assert campo.value is False


# ── artefactos ────────────────────────────────────────────────────────────────

def test_artefactos_publicados_literales():
    pub, _con = pp.detect_artifacts(
        _doc({"task": "PublishBuildArtifacts@1", "inputs": {"ArtifactName": "$(X)"}}))
    assert pub.value == ("$(X)",)


def test_artefactos_consumidos():
    doc = {"stages": [{"stage": "D", "jobs": [{
        "deployment": "d",
        "strategy": {"runOnce": {"deploy": {"steps": [
            {"download": "current", "artifact": "A"},
        ]}}},
    }]}]}
    _pub, con = pp.detect_artifacts(doc)
    assert con.value == ("A",)


# ── entornos ──────────────────────────────────────────────────────────────────

def _deployment_doc(environment, parameters=None, veces=1):
    jobs = []
    for i in range(veces):
        jobs.append({
            "deployment": "D%d" % i,
            "environment": environment,
            "strategy": {"runOnce": {"deploy": {"steps": [{"script": "echo"}]}}},
        })
    doc = {"stages": [{"stage": "S", "jobs": jobs}]}
    if parameters:
        doc["parameters"] = parameters
    return doc


def test_entorno_literal_clasifica():
    campo = pp.detect_environments(_deployment_doc("Test"))
    assert campo.value[0].kind == "test"
    assert campo.value[0].resolved is True


def test_entorno_produccion_clasifica_prod():
    assert pp.detect_environments(_deployment_doc("Production")).value[0].kind == "prod"


def test_entorno_parametrizado_no_se_adivina():
    doc = _deployment_doc(
        "${{ parameters.targetEnvironment }}",
        parameters=[{"name": "targetEnvironment", "values": ["Test", "Production"]}],
    )
    ref = pp.detect_environments(doc).value[0]
    assert ref.resolved is False
    assert ref.kind == "desconocido"
    assert ref.possible_values == ("Test", "Production")


def test_entorno_expresion_rara_no_resuelve():
    doc = _deployment_doc("${{ variables.foo }}",
                          parameters=[{"name": "foo", "values": ["a"]}])
    assert pp.detect_environments(doc).value[0].possible_values == ()


def test_sin_deployment_no_hay_entornos():
    campo = pp.detect_environments(_doc({"task": "VSBuild@1"}))
    assert campo.value == ()
    assert campo.confidence == CONF_UNKNOWN


def test_dos_deployments_al_mismo_entorno_dedup():
    campo = pp.detect_environments(_deployment_doc("Test", veces=2))
    assert len(campo.value) == 1
    assert campo.value[0].name == "Test"
