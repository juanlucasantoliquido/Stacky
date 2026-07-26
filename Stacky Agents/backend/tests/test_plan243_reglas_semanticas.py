"""Plan 243 F3 — reglas semánticas por perfil (RS001..RS009).

Comando (§7.1 del plan):
    .venv\\Scripts\\python.exe -m pytest tests/test_plan243_reglas_semanticas.py -q

Convierte en gate el conocimiento que ADO-369 costó un incidente: el YAML era
sintácticamente perfecto y habría pasado el lint PL001..PL014 sin una sola marca.

C13 — el `mode` no es un adorno. RS004/RS006/RS008 son reglas sobre LO QUE STACKY
PUEDE GENERAR, no sobre lo que ya existe y anda en producción: sin la distinción,
RS008 y test_corpus_dorado_sin_errores no pueden ser verdaderos a la vez, porque
nightly-build-online.yml:110 tiene un `- script: |` crudo y real.
"""
from __future__ import annotations

import io
import os
import textwrap

import pytest

from services.cicd_semantic_rules import (
    MODE_AUDIT,
    MODE_NL_STRICT,
    RULES_VERSION,
    SemanticFinding,
    check_semantics,
)
from services.cicd_task_catalog import PROFILE_DOTNET_FRAMEWORK as P
from services.pipeline_lint import SEV_ERROR, SEV_WARNING

GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "cicd_nl", "golden")
GOLDEN_FILES = (
    "agendaweb-ci.yml", "bootstrap-server-environment.yml", "cd-deploy-test.yml",
    "ci-batch.yml", "ci-cd-online.yml", "ci-dacpac.yml", "nightly-build-online.yml",
    "pr-validation-online.yml", "security-scan-online.yml",
)


def _golden(name: str) -> str:
    with io.open(os.path.join(GOLDEN_DIR, name), "r", encoding="utf-8") as fh:
        return fh.read()


def _codes(findings, severity=None) -> set:
    return {f.code for f in findings if severity is None or f.severity == severity}


def _check(yaml_text, mode=MODE_AUDIT, repo_root=None):
    return check_semantics(textwrap.dedent(yaml_text), profile=P,
                           repo_root=repo_root, mode=mode)


# ── RS001 — tarea que requiere Windows sobre pool no-Windows ──────────────────

RS001_OK = """\
    pool:
      vmImage: 'windows-2022'
    variables:
      solution: 'a.sln'
    steps:
      - task: VSBuild@1
        inputs: {solution: '$(solution)', platform: 'Any CPU', configuration: 'Release'}
    """

RS001_MAL = """\
    pool:
      vmImage: 'ubuntu-latest'
    variables:
      solution: 'a.sln'
    steps:
      - task: VSBuild@1
        inputs: {solution: '$(solution)', platform: 'Any CPU', configuration: 'Release'}
    """


def test_rs001_positivo_pool_windows():
    assert "RS001" not in _codes(_check(RS001_OK))


def test_rs001_negativo_pool_linux():
    findings = _check(RS001_MAL)
    assert "RS001" in _codes(findings, SEV_ERROR)


def test_rs001_no_marca_pool_self_hosted_de_os_desconocido():
    """Un pool self-hosted por nombre no declara SO: marcarlo sería un falso positivo."""
    assert "RS001" not in _codes(_check("""\
        pool:
          name: 'TEST-Server'
        variables:
          solution: 'a.sln'
        steps:
          - task: VSBuild@1
            inputs: {solution: '$(solution)', platform: 'x', configuration: 'Release'}
        """))


# ── RS002 — tarea machine-group sobre pool hosted (ADO-369) ──────────────────

RS002_MAL = """\
    stages:
      - stage: Deploy
        pool:
          vmImage: 'windows-2022'
        jobs:
          - deployment: IIS
            environment: 'Test'
            strategy:
              runOnce:
                deploy:
                  steps:
                    - task: IISWebAppDeploymentOnMachineGroup@0
                      inputs: {WebSiteName: 'AgendaWeb'}
    """

RS002_OK = """\
    stages:
      - stage: Deploy
        pool:
          name: 'TEST-Server'
        jobs:
          - deployment: Web
            environment: 'Test'
            strategy:
              runOnce:
                deploy:
                  steps:
                    - task: PowerShell@2
                      inputs: {filePath: 'pipelines/scripts/Deploy-Local.ps1'}
    """


def test_rs002_positivo_deploy_self_hosted():
    assert "RS002" not in _codes(_check(RS002_OK))


def test_rs002_negativo_machine_group_en_pool_hosted():
    assert "RS002" in _codes(_check(RS002_MAL), SEV_ERROR)


# ── RS003 — stage de deploy sin pool self-hosted / sin deployment ────────────

RS003_MAL = """\
    stages:
      - stage: Deploy
        pool:
          vmImage: 'windows-2022'
        jobs:
          - job: DeployJob
            steps:
              - task: PowerShell@2
                inputs: {filePath: 'pipelines/scripts/Deploy-Local.ps1'}
    """


def test_rs003_positivo_stage_de_deploy_bien_formado():
    assert "RS003" not in _codes(_check(RS002_OK))


def test_rs003_negativo_deploy_sin_pool_ni_deployment():
    assert "RS003" in _codes(_check(RS003_MAL), SEV_ERROR)


# ── RS004 — PowerShell@2 inline (sólo nl_strict) ─────────────────────────────

RS004_INLINE = """\
    pool:
      name: 'TEST-Server'
    steps:
      - task: PowerShell@2
        inputs:
          targetType: 'inline'
          script: |
            Write-Host "hola"
    """

RS004_FILEPATH = """\
    pool:
      name: 'TEST-Server'
    steps:
      - task: PowerShell@2
        inputs: {filePath: 'pipelines/scripts/Check-Algo.ps1'}
    """


def test_rs004_positivo_filepath(tmp_path):
    (tmp_path / "pipelines" / "scripts").mkdir(parents=True)
    (tmp_path / "pipelines" / "scripts" / "Check-Algo.ps1").write_text("# ok", encoding="utf-8")
    findings = _check(RS004_FILEPATH, mode=MODE_NL_STRICT, repo_root=str(tmp_path))
    assert "RS004" not in _codes(findings)


def test_rs004_negativo_inline_en_nl_strict():
    assert "RS004" in _codes(_check(RS004_INLINE, mode=MODE_NL_STRICT), SEV_ERROR)
    # …y en audit no dice nada: el corpus real usa inline y funciona.
    assert "RS004" not in _codes(_check(RS004_INLINE, mode=MODE_AUDIT))


# ── RS005 — referencia $(x) no declarada ─────────────────────────────────────

RS005_OK = """\
    pool:
      vmImage: 'windows-2022'
    variables:
      solution: 'a.sln'
    steps:
      - task: NuGetCommand@2
        inputs: {command: 'restore', restoreSolution: '$(solution)', feedsToUse: 'select'}
      - task: PublishBuildArtifacts@1
        inputs:
          PathtoPublish: '$(Build.ArtifactStagingDirectory)'
          ArtifactName: 'drop'
          publishLocation: 'Container'
    """

RS005_MAL = """\
    pool:
      vmImage: 'windows-2022'
    variables:
      solution: 'a.sln'
    steps:
      - task: NuGetCommand@2
        inputs: {command: 'restore', restoreSolution: '$(solucionQueNadieDeclaro)', feedsToUse: 'select'}
    """


def test_rs005_positivo_variables_declaradas_y_builtins():
    assert "RS005" not in _codes(_check(RS005_OK))


def test_rs005_negativo_referencia_huerfana():
    findings = _check(RS005_MAL)
    assert "RS005" in _codes(findings, SEV_ERROR)
    assert any("solucionQueNadieDeclaro" in f.message for f in findings)


# ── RS006 — rutas inexistentes (sólo nl_strict y con repo_root) ──────────────

RS006_YAML = """\
    pool:
      vmImage: 'windows-2022'
    steps:
      - task: VSBuild@1
        inputs:
          solution: 'trunk/OnLine/Soluciones/AgendaWeb.sln'
          platform: 'Any CPU'
          configuration: 'Release'
    """


def test_rs006_positivo_ruta_existente(tmp_path):
    destino = tmp_path / "trunk" / "OnLine" / "Soluciones"
    destino.mkdir(parents=True)
    (destino / "AgendaWeb.sln").write_text("", encoding="utf-8")
    findings = _check(RS006_YAML, mode=MODE_NL_STRICT, repo_root=str(tmp_path))
    assert "RS006" not in _codes(findings)


def test_rs006_negativo_ruta_inexistente(tmp_path):
    findings = _check(RS006_YAML, mode=MODE_NL_STRICT, repo_root=str(tmp_path))
    assert "RS006" in _codes(findings, SEV_ERROR)


def test_rs006_no_corre_sin_repo_root():
    """[C13] Sin repo_root la regla NO se evalúa: no se inventa un veredicto."""
    for mode in (MODE_AUDIT, MODE_NL_STRICT):
        assert "RS006" not in _codes(_check(RS006_YAML, mode=mode, repo_root=None))


# ── RS007 — dos pipelines de deploy sobre los mismos paths ───────────────────

_DEPLOY_TPL = """\
trigger:
  branches:
    include: [main]
  paths:
    include: ['trunk/OnLine/**']
stages:
  - stage: Deploy
    pool:
      name: 'TEST-Server'
    jobs:
      - deployment: D%s
        environment: 'Test'
        strategy:
          runOnce:
            deploy:
              steps:
                - task: PowerShell@2
                  inputs: {filePath: 'pipelines/scripts/Deploy-Local.ps1'}
"""


def test_rs007_positivo_un_solo_pipeline_de_deploy(tmp_path):
    pipes = tmp_path / "pipelines"
    pipes.mkdir()
    (pipes / "cd-uno.yml").write_text(_DEPLOY_TPL % "1", encoding="utf-8")
    findings = check_semantics(_DEPLOY_TPL % "1", profile=P, repo_root=str(tmp_path))
    assert "RS007" not in _codes(findings)


def test_rs007_negativo_dos_deploys_sobre_los_mismos_paths(tmp_path):
    pipes = tmp_path / "pipelines"
    pipes.mkdir()
    (pipes / "cd-uno.yml").write_text(_DEPLOY_TPL % "1", encoding="utf-8")
    (pipes / "cd-dos.yml").write_text(_DEPLOY_TPL % "2", encoding="utf-8")
    findings = check_semantics(_DEPLOY_TPL % "1", profile=P, repo_root=str(tmp_path))
    assert "RS007" in _codes(findings, SEV_WARNING)
    # Es warning, NUNCA error: dos deploys sobre los mismos paths puede ser deliberado.
    assert "RS007" not in _codes(findings, SEV_ERROR)


# ── RS008 — script crudo y tareas fuera del catálogo (sólo nl_strict) ────────

RS008_SCRIPT_CRUDO = """\
    pool:
      vmImage: 'windows-2022'
    steps:
      - script: echo hola
        displayName: 'saludar'
    """

RS008_TAREA_FUERA = """\
    pool:
      vmImage: 'windows-2022'
    steps:
      - task: MSBuild@1
        inputs: {solution: 'a.sln'}
    """

RS008_OK = """\
    pool:
      vmImage: 'windows-2022'
    steps:
      - task: NuGetToolInstaller@1
        inputs: {versionSpec: '6.x'}
    """


def test_rs008_positivo_solo_tareas_del_catalogo():
    assert "RS008" not in _codes(_check(RS008_OK, mode=MODE_NL_STRICT))


def test_rs008_negativo_script_crudo_y_tarea_fuera_del_catalogo():
    assert "RS008" in _codes(_check(RS008_SCRIPT_CRUDO, mode=MODE_NL_STRICT), SEV_ERROR)
    assert "RS008" in _codes(_check(RS008_TAREA_FUERA, mode=MODE_NL_STRICT), SEV_ERROR)
    assert "RS008" in _codes(_check("""\
        pool:
          vmImage: 'ubuntu-latest'
        steps:
          - bash: echo hola
        """, mode=MODE_NL_STRICT), SEV_ERROR)


# ── RS009 — environment de Producción ────────────────────────────────────────

def test_rs009_positivo_environment_de_prueba():
    assert "RS009" not in _codes(_check(RS002_OK))


def test_rs009_negativo_environment_de_produccion():
    for env in ("Production", "Producción", "PROD", "prod-web"):
        yaml_text = RS002_OK.replace("environment: 'Test'", "environment: '%s'" % env)
        assert "RS009" in _codes(_check(yaml_text), SEV_ERROR), env


# ── CAPSTONE 1 — el corpus real no puede dar rojo ────────────────────────────

def test_corpus_dorado_sin_errores():
    """Si una regla marca un pipeline que HOY funciona, la regla está mal (R2)."""
    rojos = {}
    for name in GOLDEN_FILES:
        findings = check_semantics(_golden(name), profile=P, mode=MODE_AUDIT)
        errores = [f for f in findings if f.severity == SEV_ERROR]
        if errores:
            rojos[name] = [(f.code, f.location, f.message) for f in errores]
    assert rojos == {}, "reglas que marcan pipelines reales en verde: %s" % rojos


# ── CAPSTONE 2 — el KPI del plan: ADO-369 se detectaría hoy ──────────────────

def test_ado369_seria_detectado():
    """Reconstrucción del stage eliminado en ci-cd-online.yml:9-29.

    Era sintácticamente perfecto y habría pasado el lint actual sin una sola marca:
    heredaba el pool hosted 'windows-2022' y usaba la variante machine-group, que
    publica contra el IIS LOCAL del agente -> ERROR_SITE_DOES_NOT_EXIST.
    """
    for mode in (MODE_AUDIT, MODE_NL_STRICT):
        findings = _check(RS002_MAL, mode=mode)
        rs002 = [f for f in findings if f.code == "RS002"]
        assert rs002, "ADO-369 NO detectado en mode=%s" % mode
        assert rs002[0].severity == SEV_ERROR
        assert "ADO-369" in rs002[0].evidence


# ── CAPSTONE 3 — [C13] la contradicción resuelta, no escondida ───────────────

def test_script_crudo_solo_falla_en_nl_strict():
    """nightly-build-online.yml:110 tiene un `- script: |` crudo y REAL.

    Este test es el que impide que alguien 'arregle' la contradicción borrando un
    assert: exige las dos verdades a la vez.
    """
    texto = _golden("nightly-build-online.yml")
    estricto = check_semantics(texto, profile=P, mode=MODE_NL_STRICT)
    assert "RS008" in _codes(estricto, SEV_ERROR)

    auditoria = check_semantics(texto, profile=P, mode=MODE_AUDIT)
    assert _codes(auditoria, SEV_ERROR) == set()


# ── Contrato del módulo ──────────────────────────────────────────────────────

def test_mode_invalido_lanza():
    with pytest.raises(ValueError):
        check_semantics("steps: []", profile=P, mode="loquesea")


def test_finding_es_dato_serializable_y_en_espanol():
    findings = _check(RS002_MAL)
    assert findings and all(isinstance(f, SemanticFinding) for f in findings)
    for f in findings:
        assert f.code.startswith("RS") and f.severity in (SEV_ERROR, SEV_WARNING)
        assert f.message and f.location and f.evidence
    assert RULES_VERSION == "243.1"


def test_yaml_gigante_no_cuelga_el_request():
    gigante = "variables:\n" + "".join(
        "  v%d: '%s'\n" % (i, "x" * 512) for i in range(1200))
    findings = check_semantics(gigante, profile=P)
    assert [f.code for f in findings] == ["RS000"]
    assert findings[0].severity == SEV_WARNING


def test_yaml_invalido_no_lanza():
    findings = check_semantics("esto: [no cierra\n", profile=P)
    assert [f.code for f in findings] == ["RS000"]
