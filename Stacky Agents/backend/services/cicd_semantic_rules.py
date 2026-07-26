"""services/cicd_semantic_rules.py — Plan 243 F3.

Reglas SEMÁNTICAS por perfil (RS001..RS009). Convierten en gate el conocimiento que
el incidente ADO-369 costó caro: aquel YAML era sintácticamente perfecto y habría
pasado el lint PL001..PL014 sin una sola marca. Las reglas PL son genéricas de
estructura; ninguna conoce la compatibilidad tarea <-> pool <-> entorno, que es
justo lo que falló.

MODOS (C13) — la distinción no es un adorno, es lo que evita que la fase se
contradiga a sí misma:

  MODE_AUDIT     auditar un YAML que YA EXISTE y funciona.
  MODE_NL_STRICT validar un YAML que STACKY acaba de generar.

RS004, RS006 y RS008 sólo se evalúan en `nl_strict`: son reglas sobre *lo que Stacky
puede generar*, no sobre *lo que ya existe y anda en producción*. Sin esto, RS008 y
el capstone `test_corpus_dorado_sin_errores` no podrían ser verdaderos a la vez,
porque nightly-build-online.yml:110 tiene un `- script: |` crudo y real.
RS001, RS002, RS003, RS005, RS007 y RS009 se evalúan SIEMPRE: son verdades del dominio.

Módulo PURO salvo por la verificación opcional de rutas contra `repo_root` (RS006) y
la lectura de pipelines vecinos (RS007), ambas explícitas y opcionales. Sin LLM, sin
red: paridad automática en los 3 runtimes.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

import yaml

from services.cicd_task_catalog import (
    extract_task_dicts,
    is_allowed,
    is_deploy_step,
    is_machine_group_task,
)
from services.pipeline_lint import SEV_ERROR, SEV_WARNING, _ADO_WL_PREFIXES

RULES_VERSION = "243.1"

MODE_AUDIT = "audit"
MODE_NL_STRICT = "nl_strict"
_MODES = (MODE_AUDIT, MODE_NL_STRICT)

# Reglas que sólo aplican a lo que Stacky GENERA, nunca a lo que ya existe (C13).
_NL_STRICT_ONLY = ("RS004", "RS006", "RS008")

# Por encima de esto no se procesa: se devuelve un aviso en vez de colgar el request.
MAX_YAML_BYTES = 512 * 1024

_ADO_REF_RE = re.compile(r"\$\(([A-Za-z_][A-Za-z0-9_.]*)\)")
_PATH_INPUTS = ("solution", "restoreSolution", "projects", "testProject", "filePath")
_PROD_MARKERS = ("prod", "producción", "produccion")

# vmImage de agentes hosted cuyo SO conocemos con certeza.
_WINDOWS_IMAGE_MARKER = "windows"
_KNOWN_NON_WINDOWS_MARKERS = ("ubuntu", "linux", "macos", "macmini")


@dataclass(frozen=True)
class SemanticFinding:
    code: str          # "RS002"
    severity: str      # SEV_ERROR / SEV_WARNING de pipeline_lint
    message: str       # español, accionable
    location: str      # "stages[1].jobs[0]"
    evidence: str      # por qué existe la regla


# ── Recorrido estructural ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class _StepCtx:
    """Un paso con su contexto resuelto: dónde vive y sobre qué pool corre."""
    step: dict
    location: str
    stage_index: int
    stage_doc: dict
    pool: dict            # pool efectivo (job > stage > raíz)
    stage_pool: dict
    in_deployment: bool


def _pool_of(node) -> dict:
    pool = node.get("pool") if isinstance(node, dict) else None
    return pool if isinstance(pool, dict) else {}


def _steps_of(node) -> list:
    steps = node.get("steps") if isinstance(node, dict) else None
    return [s for s in (steps or []) if isinstance(s, dict)]


def _deployment_steps(jb_doc: dict) -> list:
    strategy = jb_doc.get("strategy")
    if not isinstance(strategy, dict):
        return []
    for value in strategy.values():
        if isinstance(value, dict) and isinstance(value.get("deploy"), dict):
            return [s for s in (value["deploy"].get("steps") or []) if isinstance(s, dict)]
    return []


def _iter_steps(doc: dict) -> list:
    """Todos los pasos del documento con su contexto. Cubre las tres raíces de ADO
    (`steps:`, `jobs:`, `stages:`) y los jobs `- deployment:`."""
    root_pool = _pool_of(doc)
    out: list = []

    def _from_jobs(job_docs, stage_index, stage_doc, stage_pool, prefix):
        for j, jb_doc in enumerate(job_docs or []):
            if not isinstance(jb_doc, dict):
                continue
            job_pool = _pool_of(jb_doc) or stage_pool or root_pool
            if "deployment" in jb_doc:
                for k, step in enumerate(_deployment_steps(jb_doc)):
                    out.append(_StepCtx(step, "%sdeployments[%d].steps[%d]" % (prefix, j, k),
                                        stage_index, stage_doc, job_pool, stage_pool, True))
            else:
                for k, step in enumerate(_steps_of(jb_doc)):
                    out.append(_StepCtx(step, "%sjobs[%d].steps[%d]" % (prefix, j, k),
                                        stage_index, stage_doc, job_pool, stage_pool, False))

    for k, step in enumerate(_steps_of(doc)):
        out.append(_StepCtx(step, "steps[%d]" % k, -1, {}, root_pool, {}, False))

    _from_jobs(doc.get("jobs"), -1, {}, {}, "")

    for i, st_doc in enumerate(doc.get("stages") or []):
        if not isinstance(st_doc, dict):
            continue
        stage_pool = _pool_of(st_doc)
        _from_jobs(st_doc.get("jobs"), i, st_doc, stage_pool, "stages[%d]." % i)

    return out


# ── Helpers de dominio ─────────────────────────────────────────────────────────

def _pool_is_hosted(pool: dict) -> bool:
    return bool(pool.get("vmImage"))


def _pool_os_is_windows(pool: dict):
    """True / False / None (desconocido). Un pool self-hosted no declara su SO:
    afirmar algo sobre él sería inventar."""
    image = str(pool.get("vmImage") or "").lower()
    if not image:
        return None
    if _WINDOWS_IMAGE_MARKER in image:
        return True
    if any(m in image for m in _KNOWN_NON_WINDOWS_MARKERS):
        return False
    return None


def _task_inputs(step: dict) -> dict:
    inputs = step.get("inputs")
    return dict(inputs) if isinstance(inputs, dict) else {}


def _declared_variables(doc) -> set:
    """Nombres disponibles como `$(x)`: `variables:` (en cualquier nivel y en sus dos
    formas), claves del `matrix:` y nombres de `parameters:`.

    El matrix y los parameters cuentan aunque estén en UNSUPPORTED_CONSTRUCTS: no se
    modelan para EMITIR, pero ignorarlos acá haría que RS005 marcara en rojo pipelines
    reales que funcionan (ci-batch.yml define $(SLN) por matrix).
    """
    nombres: set = set()

    def _add_variables(block):
        if isinstance(block, dict):
            for clave, valor in block.items():
                if isinstance(valor, dict):
                    # Bloque de inserción condicional: la clave es la condición
                    # (`${{ if ... }}:`) y los nombres reales están adentro.
                    # Evidencia: bootstrap-server-environment.yml:100-110.
                    _add_variables(valor)
                else:
                    nombres.add(str(clave))
        elif isinstance(block, list):
            for item in block:
                if isinstance(item, dict):
                    for key in ("name", "template", "group"):
                        if isinstance(item.get(key), str):
                            nombres.add(item[key])

    def _walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "variables":
                    _add_variables(value)
                elif key == "matrix" and isinstance(value, dict):
                    for caso in value.values():
                        if isinstance(caso, dict):
                            nombres.update(str(k) for k in caso)
                elif key == "parameters":
                    _add_variables(value)
                _walk(value)
        elif isinstance(node, list):
            for value in node:
                _walk(value)

    _walk(doc)
    return nombres


def _is_builtin_ref(ref: str) -> bool:
    return any(ref.startswith(p) for p in _ADO_WL_PREFIXES)


def _collect_strings(node) -> list:
    out: list = []
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str):
                out.append(key)
            out.extend(_collect_strings(value))
    elif isinstance(node, list):
        for value in node:
            out.extend(_collect_strings(value))
    return out


def _trigger_paths(doc) -> tuple:
    trigger = doc.get("trigger")
    if not isinstance(trigger, dict):
        return ()
    paths = trigger.get("paths")
    if not isinstance(paths, dict):
        return ()
    return tuple(paths.get("include") or ())


def _has_deploy_step(doc) -> bool:
    return any(is_deploy_step(t.get("task", ""), _task_inputs(t))
               for t in extract_task_dicts(doc))


# ── Reglas ─────────────────────────────────────────────────────────────────────

def _rs001(ctxs, profile) -> list:
    from services.cicd_task_catalog import get_task
    out = []
    for ctx in ctxs:
        ref = ctx.step.get("task")
        if not isinstance(ref, str):
            continue
        spec = get_task(profile, ref)
        if spec is None or not spec.requires_windows:
            continue
        if _pool_os_is_windows(ctx.pool) is False:
            out.append(SemanticFinding(
                code="RS001", severity=SEV_ERROR,
                message=("la tarea %s requiere un agente Windows y este job corre sobre "
                         "'%s'. .NET Framework 4.8.1 necesita Visual Studio Build Tools."
                         % (ref, ctx.pool.get("vmImage"))),
                location=ctx.location,
                evidence="pipelines/ci-cd-online.yml:55-56 (pool: vmImage: 'windows-2022')",
            ))
    return out


def _rs002(ctxs) -> list:
    out = []
    for ctx in ctxs:
        ref = ctx.step.get("task")
        if not isinstance(ref, str) or not is_machine_group_task(ref):
            continue
        if _pool_is_hosted(ctx.pool):
            out.append(SemanticFinding(
                code="RS002", severity=SEV_ERROR,
                message=("%s es la variante machine-group: no tiene input de servidor y "
                         "publica contra el IIS LOCAL del agente. Sobre el pool hosted "
                         "'%s' apunta a la VM efímera de Microsoft, no a tu servidor. "
                         "Usá un pool self-hosted del entorno."
                         % (ref, ctx.pool.get("vmImage"))),
                location=ctx.location,
                evidence=("ADO-369 — pipelines/ci-cd-online.yml:9-29: msdeploy buscaba el "
                          "sitio 'AgendaWeb' en la VM efímera -> ERROR_SITE_DOES_NOT_EXIST"),
            ))
    return out


def _rs003(doc, ctxs) -> list:
    out = []
    por_stage: dict = {}
    for ctx in ctxs:
        ref = ctx.step.get("task")
        if not isinstance(ref, str) or not is_deploy_step(ref, _task_inputs(ctx.step)):
            continue
        por_stage.setdefault(ctx.stage_index, []).append(ctx)

    for stage_index, deploys in sorted(por_stage.items()):
        ctx = deploys[0]
        falta = []
        if not (ctx.stage_pool or {}).get("name"):
            falta.append("`pool: name:` a nivel de stage (agente self-hosted del entorno)")
        if not all(d.in_deployment for d in deploys):
            falta.append("un job `- deployment:` con `environment:`")
        if falta:
            out.append(SemanticFinding(
                code="RS003", severity=SEV_ERROR,
                message=("este stage despliega a un servidor pero le falta %s. El patrón "
                         "correcto de este ecosistema es pool a nivel de stage + "
                         "Deploy-Local.ps1 en un job de deployment." % " y ".join(falta)),
                location=("stages[%d]" % stage_index) if stage_index >= 0 else ctx.location,
                evidence=("pipelines/cd-deploy-test.yml:119-127; recomendación explícita en "
                          "pipelines/ci-cd-online.yml:27-29"),
            ))
    return out


def _rs004(ctxs, repo_root) -> list:
    out = []
    for ctx in ctxs:
        if ctx.step.get("task") != "PowerShell@2":
            continue
        inputs = _task_inputs(ctx.step)
        if inputs.get("script") or str(inputs.get("targetType", "")).lower() == "inline":
            out.append(SemanticFinding(
                code="RS004", severity=SEV_ERROR,
                message=("PowerShell@2 con script inline no se admite en un pipeline "
                         "generado: usá `inputs.filePath` apuntando a un script ya "
                         "versionado en el repo. El YAML generado corre en agentes con "
                         "acceso a servidores y datos reales."),
                location=ctx.location,
                evidence="pipelines/cd-deploy-test.yml:134-141 (filePath a Deploy-Local.ps1)",
            ))
            continue
        file_path = str(inputs.get("filePath") or "")
        if not file_path:
            out.append(SemanticFinding(
                code="RS004", severity=SEV_ERROR,
                message="PowerShell@2 sin `inputs.filePath`: no hay script versionado que correr.",
                location=ctx.location,
                evidence="pipelines/cd-deploy-test.yml:134-141",
            ))
        elif repo_root and "$(" not in file_path:
            if not os.path.exists(os.path.join(repo_root, file_path.replace("\\", "/"))):
                out.append(SemanticFinding(
                    code="RS004", severity=SEV_ERROR,
                    message="el script '%s' no existe en el repositorio." % file_path,
                    location=ctx.location,
                    evidence="pipelines/cd-deploy-test.yml:134-141",
                ))
    return out


def _rs005(doc) -> list:
    declaradas = _declared_variables(doc)
    huerfanas: dict = {}
    for texto in _collect_strings(doc):
        for ref in _ADO_REF_RE.findall(texto):
            if ref in declaradas or _is_builtin_ref(ref):
                continue
            huerfanas.setdefault(ref, texto)
    return [
        SemanticFinding(
            code="RS005", severity=SEV_ERROR,
            message=("la referencia $(%s) no está declarada en `variables:` de este YAML "
                     "ni es una variable built-in de ADO. Este ecosistema no usa variable "
                     "groups: declarala inline." % ref),
            location="variables",
            evidence="ausencia total de variable groups en el corpus (`group:` = 0 usos)",
        )
        for ref in sorted(huerfanas)
    ]


def _rs006(ctxs, repo_root) -> list:
    if not repo_root:
        return []
    out = []
    vistos: set = set()
    for ctx in ctxs:
        if not isinstance(ctx.step.get("task"), str):
            continue
        for nombre, valor in _task_inputs(ctx.step).items():
            if nombre not in _PATH_INPUTS or not isinstance(valor, str) or not valor:
                continue
            if "$(" in valor or "${{" in valor or "*" in valor:
                continue  # ruta parametrizada o glob: no se puede resolver sin inventar
            if valor in vistos:
                continue
            vistos.add(valor)
            if not os.path.exists(os.path.join(repo_root, valor.replace("\\", "/"))):
                out.append(SemanticFinding(
                    code="RS006", severity=SEV_ERROR,
                    message=("la ruta '%s' (input `%s`) no existe en el repositorio: el "
                             "pipeline fallaría en la primera corrida." % (valor, nombre)),
                    location=ctx.location,
                    evidence="pipelines/ci-cd-online.yml:48-49",
                ))
    return out


def _rs007(doc, repo_root) -> list:
    if not repo_root or not _has_deploy_step(doc):
        return []
    mis_paths = set(_trigger_paths(doc))
    if not mis_paths:
        return []

    carpeta = os.path.join(repo_root, "pipelines")
    if not os.path.isdir(carpeta):
        return []

    colisiones = []
    for nombre in sorted(os.listdir(carpeta)):
        if not nombre.endswith((".yml", ".yaml")):
            continue
        try:
            with open(os.path.join(carpeta, nombre), "r", encoding="utf-8") as fh:
                otro = yaml.safe_load(fh.read())
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(otro, dict) or not _has_deploy_step(otro):
            continue
        compartidos = mis_paths & set(_trigger_paths(otro))
        if compartidos and otro != doc:
            colisiones.append((nombre, sorted(compartidos)))

    return [
        SemanticFinding(
            code="RS007", severity=SEV_WARNING,
            message=("'%s' también despliega y dispara sobre %s: dos corridas simultáneas "
                     "podrían escribir sobre el mismo destino del mismo servidor."
                     % (nombre, ", ".join(paths))),
            location="trigger.paths",
            evidence=("pipelines/ci-cd-online.yml:22-25 — dos robocopy simultáneos sobre "
                      "C:\\AIS\\AgendaWeb\\Web del mismo servidor"),
        )
        for nombre, paths in colisiones
    ]


def _rs008(ctxs, profile) -> list:
    out = []
    for ctx in ctxs:
        step = ctx.step
        for clave in ("script", "bash", "powershell", "pwsh"):
            if clave in step and "task" not in step:
                out.append(SemanticFinding(
                    code="RS008", severity=SEV_ERROR,
                    message=("paso `- %s:` crudo: un pipeline generado sólo puede usar "
                             "tareas del catálogo del perfil '%s'. Compilar .NET Framework "
                             "requiere `- task: VSBuild@1`, no un script."
                             % (clave, profile)),
                    location=ctx.location,
                    evidence=("contraejemplo real que SÍ funciona y por eso sólo se prohíbe "
                              "en la ruta NL: pipelines/nightly-build-online.yml:110"),
                ))
                break
        ref = step.get("task")
        if isinstance(ref, str) and not is_allowed(profile, ref):
            out.append(SemanticFinding(
                code="RS008", severity=SEV_ERROR,
                message=("la tarea %s no está en el catálogo del perfil '%s': o no existe, "
                         "o todavía no tiene evidencia de uso real en este ecosistema."
                         % (ref, profile)),
                location=ctx.location,
                evidence="allowlist cerrada de services/cicd_task_catalog.py (C5)",
            ))
    return out


def _rs009(doc) -> list:
    out = []
    for i, st_doc in enumerate(doc.get("stages") or []):
        if not isinstance(st_doc, dict):
            continue
        for j, jb_doc in enumerate(st_doc.get("jobs") or []):
            if not isinstance(jb_doc, dict):
                continue
            env = jb_doc.get("environment")
            if not isinstance(env, str):
                continue
            if any(m in env.lower() for m in _PROD_MARKERS):
                out.append(SemanticFinding(
                    code="RS009", severity=SEV_ERROR,
                    message=("environment '%s': este generador no despliega a Producción. "
                             "Generá el pipeline contra un entorno de prueba y promové a "
                             "producción por el flujo humano que ya tenés." % env),
                    location="stages[%d].jobs[%d].environment" % (i, j),
                    evidence="alcance declarado del plan 243 (§3, Fuera de alcance)",
                ))
    return out


# ── API pública ────────────────────────────────────────────────────────────────

def check_semantics(yaml_text: str, *, profile: str, repo_root: str = None,
                    mode: str = MODE_AUDIT) -> list:
    """Reglas semánticas RS001..RS009 sobre un pipeline ADO. Determinista, sin LLM.

    `mode` inválido lanza ValueError: falla ruidosa, nunca silenciosa (C13).
    """
    if mode not in _MODES:
        raise ValueError("mode inválido: %r (esperado %s)" % (mode, " o ".join(_MODES)))

    if len(yaml_text or "") > MAX_YAML_BYTES:
        return [SemanticFinding(
            code="RS000", severity=SEV_WARNING,
            message=("el YAML supera %d KB: fuera del rango soportado, no se analizó."
                     % (MAX_YAML_BYTES // 1024)),
            location="(documento)", evidence="límite de procesamiento del plan 243 F3",
        )]

    try:
        doc = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        return [SemanticFinding(
            code="RS000", severity=SEV_WARNING,
            message="el YAML no se pudo parsear: %s" % str(exc).splitlines()[0],
            location="(documento)", evidence="yaml.safe_load",
        )]

    if not isinstance(doc, dict):
        return []

    ctxs = _iter_steps(doc)

    findings: list = []
    findings.extend(_rs001(ctxs, profile))
    findings.extend(_rs002(ctxs))
    findings.extend(_rs003(doc, ctxs))
    findings.extend(_rs005(doc))
    findings.extend(_rs007(doc, repo_root))
    findings.extend(_rs009(doc))

    if mode == MODE_NL_STRICT:
        findings.extend(_rs004(ctxs, repo_root))
        findings.extend(_rs006(ctxs, repo_root))
        findings.extend(_rs008(ctxs, profile))

    assert all(f.code not in _NL_STRICT_ONLY for f in findings) or mode == MODE_NL_STRICT
    return findings
