"""services/cicd_task_catalog.py — Plan 243 F0.

Catálogo CERRADO de tareas ADO por perfil. Codifica como DATO el conocimiento real
del dominio, extraído del corpus dorado (9 pipelines que hoy corren en producción,
vendorizados en tests/fixtures/cicd_nl/golden/).

Módulo PURO: sin I/O, sin red, sin LLM. Los 3 runtimes (Codex CLI, Claude Code CLI,
GitHub Copilot Pro) lo ejecutan idéntico porque no hay nada específico de runtime.

REGLA DURA (plan 243, C20) — la extracción es SIEMPRE por yaml.safe_load, NUNCA por
grep/regex: un regex sobre los 9 golden devuelve 12 refs porque dos viven DENTRO de
comentarios (agendaweb-ci.yml:142 -> IISWebAppDeploymentOnMachineGroup@0 y
ci-dacpac.yml:102 -> SqlAzureDacpacDeployment@1). La primera es la causa raíz de
ADO-369: catalogarla como "tarea legítima" habilitaría al compilador a emitir
exactamente lo que RS002 existe para prohibir.

El catálogo NO se importa desde pipeline_spec.py (C15): el modelo del Plan 73 es
genérico y sirve también a GitLab. La pertenencia al catálogo se valida en F3 (RS008),
donde `profile` es un parámetro explícito.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import yaml

CATALOG_VERSION = "243.1"

PROFILE_DOTNET_FRAMEWORK = "dotnet_framework"


# ── Contrato ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TaskInput:
    name: str
    required: bool = False
    allowed_values: tuple = ()


@dataclass(frozen=True)
class TaskSpec:
    ref: str                        # "VSBuild@1"
    inputs: tuple = ()              # tuple[TaskInput, ...]
    requires_windows: bool = False
    is_deploy: bool = False
    evidence: str = ""              # "pipelines/ci-cd-online.yml:85"

    def input_names(self) -> tuple:
        return tuple(i.name for i in self.inputs)


# ── Tareas que despliegan (fundamento de RS002/RS003) ─────────────────────────
#
# NINGUNA de las 10 tareas vivas del corpus es una tarea de deploy: el corpus
# despliega con PowerShell@2 + Deploy-Local.ps1 sobre un pool self-hosted
# (cd-deploy-test.yml:134-141). Las refs de abajo son las tareas de deploy que el
# propio corpus documenta EN COMENTARIOS como el camino equivocado o pendiente
# (agendaweb-ci.yml:142, ci-dacpac.yml:102). Están acá, y NO en TASK_CATALOG,
# justamente para poder prohibirlas sin habilitarlas.
DEPLOY_TASK_REFS = frozenset({
    "IISWebAppDeploymentOnMachineGroup@0",
    "SqlAzureDacpacDeployment@1",
    "AzureRmWebAppDeployment@4",
})

# Convención verificada en el corpus: los scripts de despliegue se llaman Deploy-*.ps1
# (cd-deploy-test.yml:137 y :176 -> pipelines/scripts/Deploy-Local.ps1). Un
# Initialize-*.ps1 (bootstrap) o un Check-*.ps1 (security-scan) NO son deploy.
DEPLOY_SCRIPT_PREFIX = "Deploy-"

# Marcador de la variante machine-group (ADO-369): publica contra el IIS LOCAL del
# agente que la corre, así que sobre un pool hosted apunta a una VM efímera.
MACHINE_GROUP_MARKER = "OnMachineGroup"


# ── Perfil dotnet_framework ────────────────────────────────────────────────────
#
# Cada `required=True` está respaldado por el 100% de los usos del corpus (calculado
# por intersección de las claves de `inputs` sobre todas las apariciones vivas).
# Cada `allowed_values` es un enum cerrado y documentado de ADO cuyo valor del corpus
# pertenece al conjunto. Lo que el corpus no evidencia, no se inventa: queda sin
# restringir en vez de adivinado.

_DOTNET_FRAMEWORK_TASKS = (
    TaskSpec(
        ref="NuGetToolInstaller@1",
        inputs=(TaskInput("versionSpec", required=True),),
        evidence="pipelines/ci-cd-online.yml:70",
    ),
    TaskSpec(
        ref="NuGetCommand@2",
        inputs=(
            TaskInput("command", required=True,
                      allowed_values=("restore", "pack", "push", "custom")),
            TaskInput("restoreSolution", required=True),
            TaskInput("feedsToUse", required=True,
                      allowed_values=("select", "config")),
            TaskInput("vstsFeed"),
        ),
        requires_windows=True,
        evidence="pipelines/ci-cd-online.yml:75",
    ),
    TaskSpec(
        ref="VSBuild@1",
        inputs=(
            TaskInput("solution", required=True),
            TaskInput("platform", required=True),
            TaskInput("configuration", required=True),
            TaskInput("msbuildArgs"),
        ),
        requires_windows=True,
        evidence="pipelines/ci-cd-online.yml:85",
    ),
    TaskSpec(
        ref="DotNetCoreCLI@2",
        inputs=(
            TaskInput("command", required=True,
                      allowed_values=("build", "push", "pack", "test", "publish",
                                      "restore", "run", "custom")),
            TaskInput("projects"),
            TaskInput("arguments"),
            TaskInput("custom"),
            TaskInput("publishTestResults"),
        ),
        evidence="pipelines/ci-cd-online.yml:100",
    ),
    TaskSpec(
        ref="PublishTestResults@2",
        inputs=(
            TaskInput("testResultsFormat", required=True,
                      allowed_values=("JUnit", "NUnit", "VSTest", "XUnit", "CTest")),
            TaskInput("testResultsFiles", required=True),
            TaskInput("failTaskOnFailedTests", required=True),
            TaskInput("testRunTitle"),
        ),
        evidence="pipelines/ci-cd-online.yml:112",
    ),
    TaskSpec(
        ref="PublishBuildArtifacts@1",
        inputs=(
            TaskInput("PathtoPublish", required=True),
            TaskInput("ArtifactName", required=True),
            TaskInput("publishLocation", required=True,
                      allowed_values=("Container", "FilePath")),
        ),
        evidence="pipelines/ci-cd-online.yml:121",
    ),
    TaskSpec(
        ref="PublishCodeCoverageResults@2",
        inputs=(TaskInput("summaryFileLocation", required=True),),
        evidence="pipelines/agendaweb-ci.yml:101",
    ),
    TaskSpec(
        ref="CopyFiles@2",
        inputs=(
            TaskInput("SourceFolder", required=True),
            TaskInput("Contents", required=True),
            TaskInput("TargetFolder", required=True),
            TaskInput("flattenFolders", required=True),
        ),
        evidence="pipelines/ci-dacpac.yml:66",
    ),
    TaskSpec(
        ref="UseDotNet@2",
        inputs=(
            TaskInput("packageType", required=True, allowed_values=("sdk", "runtime")),
            TaskInput("version", required=True),
        ),
        evidence="pipelines/ci-dacpac.yml:42",
    ),
    TaskSpec(
        # Sin inputs requeridos a propósito: el corpus la usa de las dos formas
        # (targetType inline y filePath). RS004 restringe la forma inline SOLO en
        # la ruta NL (mode="nl_strict"), no acá.
        ref="PowerShell@2",
        inputs=(
            TaskInput("targetType", allowed_values=("inline", "filePath")),
            TaskInput("filePath"),
            TaskInput("script"),
            TaskInput("arguments"),
            TaskInput("workingDirectory"),
            TaskInput("failOnStderr"),
            TaskInput("pwsh"),
        ),
        requires_windows=True,
        evidence="pipelines/cd-deploy-test.yml:134",
    ),
)

TASK_CATALOG: dict = {
    PROFILE_DOTNET_FRAMEWORK: {t.ref: t for t in _DOTNET_FRAMEWORK_TASKS},
}


# ── API pública ────────────────────────────────────────────────────────────────

def get_task(profile: str, ref: str) -> Optional[TaskSpec]:
    """TaskSpec del perfil, o None. NUNCA lanza (perfil o ref desconocidos -> None)."""
    return (TASK_CATALOG.get(profile) or {}).get(ref)


def is_allowed(profile: str, ref: str) -> bool:
    """True sólo si `ref` está en el catálogo cerrado del perfil."""
    return get_task(profile, ref) is not None


def validate_inputs(profile: str, ref: str, inputs: dict) -> list:
    """Valida los `inputs` de una tarea contra el catálogo. [] = OK. NUNCA lanza.

    Detecta las tres alucinaciones típicas (C5): tarea inexistente, input inventado
    (p.ej. `msbuildArguments` en vez del real `msbuildArgs`) y valor fuera del enum.
    """
    spec = get_task(profile, ref)
    if spec is None:
        return ["tarea '%s' fuera del catálogo del perfil '%s'" % (ref, profile)]

    errores: list = []
    dados = dict(inputs or {})
    conocidos = {i.name: i for i in spec.inputs}

    for name in sorted(dados):
        if name not in conocidos:
            errores.append(
                "input '%s' no existe en %s (válidos: %s)"
                % (name, ref, ", ".join(spec.input_names()))
            )
            continue
        allowed = conocidos[name].allowed_values
        if allowed and str(dados[name]) not in allowed:
            errores.append(
                "input '%s' de %s con valor %r fuera de %s"
                % (name, ref, dados[name], list(allowed))
            )

    for inp in spec.inputs:
        if inp.required and inp.name not in dados:
            errores.append("falta el input requerido '%s' en %s" % (inp.name, ref))

    return errores


def is_deploy_step(ref: str, inputs: Optional[dict] = None) -> bool:
    """¿Este paso despliega a un servidor? Fundamento de RS002/RS003.

    Dos caminos, ambos evidenciados en el corpus:
      1. una tarea de deploy conocida (DEPLOY_TASK_REFS);
      2. PowerShell@2 corriendo un script Deploy-*.ps1 (cd-deploy-test.yml:137),
         que es como este ecosistema despliega de verdad.
    """
    if ref in DEPLOY_TASK_REFS:
        return True
    if ref == "PowerShell@2":
        file_path = str((inputs or {}).get("filePath") or "")
        base = file_path.replace("\\", "/").rsplit("/", 1)[-1]
        return base.startswith(DEPLOY_SCRIPT_PREFIX)
    return False


def is_machine_group_task(ref: str) -> bool:
    """Variante machine-group: publica contra el IIS LOCAL del agente (ADO-369)."""
    return MACHINE_GROUP_MARKER in str(ref)


# ── Extractor canónico (reusado por F2, F3 y F3.5) ────────────────────────────

def extract_task_dicts(node) -> list:
    """Todos los dicts `task:` VIVOS de un documento ya parseado. PURA.

    Recorre recursivamente listas/dicts. Al operar sobre la salida de yaml.safe_load,
    los `- task:` comentados no existen: quedan excluidos por construcción, no por un
    filtro posterior que alguien pueda borrar (C20).
    """
    acc: list = []
    if isinstance(node, dict):
        if isinstance(node.get("task"), str):
            acc.append(node)
        for value in node.values():
            acc.extend(extract_task_dicts(value))
    elif isinstance(node, list):
        for value in node:
            acc.extend(extract_task_dicts(value))
    return acc


def extract_task_refs(yaml_text: str) -> tuple:
    """Espina de tareas de un YAML, en orden de aparición. PURA (parsea, no lee disco)."""
    doc = yaml.safe_load(yaml_text)
    return tuple(t["task"] for t in extract_task_dicts(doc))
