"""services/cicd_security_rules.py — Plan 248 F1. Las 8 reglas SEC.

PURO: sin red, sin LLM, sin config, sin disco.
Toda extraccion de evidencia es sobre el arbol PARSEADO. El texto crudo del YAML se usa
EXCLUSIVAMENTE para resolver el numero de linea de una evidencia ya confirmada en el arbol
(un escaner por regex reportaria 9 falsos positivos sobre este corpus: §2.3 del plan).
"""
from __future__ import annotations

import re

import yaml

from services.cicd_audit_core import (
    MODE_AUDIT,
    MODE_NL_STRICT,
    SEV_ERROR,
    SEV_WARNING,
    audit_rule,
    finding,
    is_dynamic,
    iter_steps,
    line_of,
    line_of_pair,
    pool_is_self_hosted,
)
from services.cicd_semantic_rules import _MODES, _PROD_MARKERS, _task_inputs
from services.pipeline_lint import _looks_secret
from services.secret_masking import mask_token_values

SECURITY_RULES_VERSION = "248.1"

_SECURITY_TASKS = frozenset({
    "WhiteSource@21", "WhiteSourceBolt@20", "SonarQubeAnalyze@5", "SonarCloudAnalyze@1",
    "Trivy@1", "AquaSecurityTrivy@1", "CredScan@3", "AntiMalware@3",
})
# C12 — se comparan SIEMPRE contra texto.lower(). `test` va aparte, como PALABRA.
_SECURITY_MARKERS = ("vulnerab", "security", "scan", "audit", "sast", "dependency-check")
_SECURITY_WORD_MARKERS = ("test",)
# C5 — `echo` NO esta: ya es PL014. SEC002 cubre solo lo que PL014 no ve.
_LOG_SINKS = ("write-host", "write-output", "write-debug", "--verbose", "-verbose", "--debug")
_SECRET_INPUT_KEYS = ("arguments", "script", "custom", "msbuildArgs", "connectionString")

_ADO_REF_RE = re.compile(r"\$\(([A-Za-z_][A-Za-z0-9_.]*)\)")
_GITLAB_REF_RE = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")


def _exec_strings(step: dict) -> list:
    """(clave, valor) de los strings EJECUTABLES de un paso."""
    out = []
    for key in ("script", "bash", "pwsh", "powershell"):
        value = step.get(key)
        if isinstance(value, str):
            out.append((key, value))
    for key, value in _task_inputs(step).items():
        if isinstance(value, str) and key in _SECRET_INPUT_KEYS:
            out.append((key, value))
    return out


def _refs_in(texto: str, provider: str) -> list:
    rx = _ADO_REF_RE if provider == "ado" else _GITLAB_REF_RE
    return [m.group(1) for m in rx.finditer(texto or "")]


def _display_text(step: dict) -> str:
    partes = [str(step.get("displayName") or "")]
    inputs = _task_inputs(step)
    partes.append(str(inputs.get("command") or ""))
    partes.append(str(step.get("task") or ""))
    return " ".join(partes).lower()


def _matchea_seguridad(step: dict) -> bool:
    ref = str(step.get("task") or "")
    if ref in _SECURITY_TASKS:
        return True
    texto = _display_text(step)          # C12 — case-folded SIEMPRE
    if any(m in texto for m in _SECURITY_MARKERS):
        return True
    return any(re.search(r"\b%s\b" % re.escape(w), texto) for w in _SECURITY_WORD_MARKERS)


def _pr_esta_activo(doc) -> bool:
    """C13 — helper unico de 'pr activo', usado por SEC007 y OPT001."""
    pr = doc.get("pr")
    if pr is None or pr is False:
        return False
    if isinstance(pr, str):
        return pr.strip().lower() != "none"
    if isinstance(pr, dict):
        branches = pr.get("branches") if isinstance(pr.get("branches"), dict) else {}
        excl = branches.get("exclude")
        if isinstance(excl, list) and "*" in [str(x) for x in excl] and not branches.get("include"):
            return False
        return True
    return bool(pr)


# ═════════════════════════════ SEC001 ═════════════════════════════

_REPRO_SEC001 = """\
steps:
- task: PowerShell@2
  inputs:
    arguments: '-Token ghp_0123456789abcdefghijklmnopqrstuvwx'
"""


@audit_rule("SEC001", severity_audit=SEV_ERROR, severity_nl=SEV_ERROR,
            providers=("ado", "gitlab"), modes=(MODE_AUDIT, MODE_NL_STRICT),
            repro=("ado", _REPRO_SEC001))
def _sec001_secreto_literal(ctxs, doc, lines, provider) -> list:
    """Secreto literal FUERA del bloque `variables:` (la zona que PL012 no recorre)."""
    out = []
    vistos = set()

    def _revisar(valor, location, detalle_key):
        if not isinstance(valor, str) or len(valor) < 8:
            return
        if mask_token_values(valor) == valor:
            return
        clave = (location, detalle_key)
        if clave in vistos:
            return
        vistos.add(clave)
        out.append(finding(
            code="SEC001", severity=SEV_ERROR,
            message=("Hay un valor con pinta de token escrito literal en el YAML, fuera del "
                     "bloque de variables."),
            location=location, line=line_of(lines, detalle_key),
            evidence="%s con un valor que parece un token" % detalle_key,
            remediation=("Movelo a la caja fuerte de variables (Plan 94) y referencialo como "
                         "$(NOMBRE). Un literal en el YAML queda en el historial de git para "
                         "siempre, incluso si lo borras despues."),
            providers=("ado", "gitlab"),
        ))

    for ctx in ctxs:
        for key, value in _task_inputs(ctx.step).items():
            _revisar(value, ctx.location, str(key))
        env = ctx.step.get("env")
        if isinstance(env, dict):
            for key, value in env.items():
                _revisar(value, ctx.location, str(key))

    for item in (doc.get("parameters") or []):
        if isinstance(item, dict):
            _revisar(item.get("default"), "parameters", str(item.get("name") or "parameters"))
    return out


# ═════════════════════════════ SEC002 ═════════════════════════════

_REPRO_SEC002 = """\
steps:
- task: PowerShell@2
  inputs:
    script: 'Write-Host "token=$(API_TOKEN)"'
"""


@audit_rule("SEC002", severity_audit=SEV_ERROR, severity_nl=SEV_ERROR,
            providers=("ado", "gitlab"), modes=(MODE_AUDIT, MODE_NL_STRICT),
            repro=("ado", _REPRO_SEC002))
def _sec002_secreto_al_log(ctxs, lines, provider) -> list:
    """Secreto impreso por un sink que PL014 NO ve (este corpus es 100% PowerShell)."""
    out = []
    for ctx in ctxs:
        for _key, texto in _exec_strings(ctx.step):
            bajo = texto.lower()
            if not any(sink in bajo for sink in _LOG_SINKS):
                continue
            secretas = [r for r in _refs_in(texto, provider) if _looks_secret(r)]
            if not secretas:
                continue
            out.append(finding(
                code="SEC002", severity=SEV_ERROR,
                message=("Un paso imprime en el log una variable cuyo nombre indica que es un "
                         "secreto."),
                location=ctx.location, line=line_of(lines, secretas[0]),
                evidence=secretas[0],
                remediation=("El log de una corrida es visible para cualquiera con permiso de "
                             "lectura del proyecto. Marca la variable como secreta o no la "
                             "imprimas."),
                providers=("ado", "gitlab"),
            ))
            break
    return out


# ═════════════════════════════ SEC003 ═════════════════════════════

_REPRO_SEC003 = """\
pool:
  vmImage: 'ubuntu-latest'
steps:
- script: echo hola
"""


@audit_rule("SEC003", severity_audit=SEV_WARNING, severity_nl=SEV_ERROR,
            providers=("ado",), modes=(MODE_AUDIT, MODE_NL_STRICT),
            repro=("ado", _REPRO_SEC003))
def _sec003_imagen_sin_pin(ctxs, lines) -> list:
    out, vistos = [], set()
    for ctx in ctxs:
        pool = ctx.pool if isinstance(ctx.pool, dict) else {}
        image = pool.get("vmImage")
        if not isinstance(image, str) or not image.endswith("-latest"):
            continue
        if image in vistos:
            continue
        vistos.add(image)
        out.append(finding(
            code="SEC003", severity=SEV_WARNING,
            message="El agente corre sobre una imagen sin version fijada.",
            location=ctx.location, line=line_of_pair(lines, "vmImage", image),
            evidence=image,
            remediation=("'-latest' rota sin avisar y puede romper la build sin que cambies una "
                         "linea. Fija la version (ubuntu-24.04), como ya hacen los otros "
                         "pipelines de este repo con windows-2022."),
            providers=("ado",),
        ))
    return out


# ═════════════════════════════ SEC004 ═════════════════════════════

_REPRO_SEC004 = """\
steps:
- checkout: self
  persistCredentials: true
"""


@audit_rule("SEC004", severity_audit=SEV_ERROR, severity_nl=SEV_ERROR,
            providers=("ado", "gitlab"), modes=(MODE_AUDIT, MODE_NL_STRICT),
            repro=("ado", _REPRO_SEC004))
def _sec004_persist_credentials(ctxs, lines, provider) -> list:
    out = []
    for ctx in ctxs:
        step = ctx.step
        if "checkout" not in step:
            continue
        if step.get("persistCredentials") is not True:
            continue
        out.append(finding(
            code="SEC004", severity=SEV_ERROR,
            message="El checkout deja el token de la corrida escrito en el workspace.",
            location=ctx.location, line=line_of(lines, "persistCredentials"),
            evidence="persistCredentials: true",
            remediation=("Queda al alcance de cualquier paso posterior del job. Quitalo; si un "
                         "paso puntual necesita el token, pasaselo explicito y acotado a ese paso."),
            providers=("ado", "gitlab"),
        ))
    return out


# ═════════════════════════════ SEC005 ═════════════════════════════

_REPRO_SEC005 = """\
steps:
- task: VSBuild@1
  inputs:
    msbuildArgs: '/p:DeployOnBuild=true /p:AutoParameterizationWebConfigConnectionStrings=false'
- task: PublishBuildArtifacts@1
  inputs:
    ArtifactName: 'drop'
"""


@audit_rule("SEC005", severity_audit=SEV_WARNING, severity_nl=SEV_WARNING,
            providers=("ado",), modes=(MODE_AUDIT, MODE_NL_STRICT),
            repro=("ado", _REPRO_SEC005))
def _sec005_artefacto_webconfig(doc, ctxs, lines) -> list:
    """Una vez por pipeline, anclada en el PRIMER Publish del walk.

    C11 — `location` y `line` DEBEN apuntar al MISMO paso: se lleva el ordinal del walk
    y se lo pasa a `occurrence`, nunca la primera ocurrencia textual a secas.
    """
    publish_ctx, publish_ordinal, ordinal = None, 0, 0
    for ctx in ctxs:
        if str(ctx.step.get("task") or "").startswith("PublishBuildArtifacts@"):
            ordinal += 1
            if publish_ctx is None:
                publish_ctx = ctx
                publish_ordinal = ordinal
    if publish_ctx is None:
        return []
    for ctx in ctxs:
        if not str(ctx.step.get("task") or "").startswith("VSBuild@"):
            continue
        args = str(_task_inputs(ctx.step).get("msbuildArgs") or "")
        if "DeployOnBuild=true" in args and \
           "AutoParameterizationWebConfigConnectionStrings=false" in args:
            return [finding(
                code="SEC005", severity=SEV_WARNING,
                message=("El artefacto publicado incluye el Web.config con las cadenas de "
                         "conexion sin parametrizar."),
                location=publish_ctx.location,
                line=line_of(lines, "PublishBuildArtifacts@", occurrence=publish_ordinal),
                evidence="AutoParameterizationWebConfigConnectionStrings=false",
                remediation=("Las cadenas van al paquete tal cual estan en el repo y el "
                             "artefacto lo descarga cualquiera con permiso de lectura del "
                             "proyecto. Revisa si ese Web.config tiene credenciales reales; si "
                             "las tiene, parametriza (quita el =false) o exclui Web.config del "
                             "paquete."),
                providers=("ado",),
            )]
    return []


# ═════════════════════════════ SEC006 ═════════════════════════════

_REPRO_SEC006 = """\
steps:
- task: DotNetCoreCLI@2
  displayName: 'Escaneo de vulnerabilidades'
  continueOnError: true
  inputs:
    command: 'custom'
"""


@audit_rule("SEC006", severity_audit=SEV_WARNING, severity_nl=SEV_ERROR,
            providers=("ado", "gitlab"), modes=(MODE_AUDIT, MODE_NL_STRICT),
            repro=("ado", _REPRO_SEC006))
def _sec006_fallo_enmascarado(ctxs, lines, provider) -> list:
    out = []
    for ctx in ctxs:
        step = ctx.step
        enmascara = step.get("continueOnError") is True or step.get("allow_failure") is True
        if not enmascara:
            continue
        if not _matchea_seguridad(step):
            continue
        clave = "continueOnError" if step.get("continueOnError") is True else "allow_failure"
        out.append(finding(
            code="SEC006", severity=SEV_WARNING,
            message="Un paso de seguridad o de test no puede fallar la build.",
            location=ctx.location, line=line_of(lines, clave),
            evidence="%s: true" % clave,
            remediation=("Un paso de seguridad o de test que no puede fallar la build es un "
                         "falso verde: reporta el problema en un log que nadie lee y la corrida "
                         "sale en verde igual. Quita el continueOnError, o move el gate adentro "
                         "del script y suprimi este hallazgo dejando el motivo por escrito."),
            providers=("ado", "gitlab"),
        ))
    return out


# ═════════════════════════════ SEC007 ═════════════════════════════

_REPRO_SEC007 = """\
pr:
  branches:
    include: [ main ]
pool:
  name: 'MI-SERVIDOR'
steps:
- script: echo hola
"""


@audit_rule("SEC007", severity_audit=SEV_ERROR, severity_nl=SEV_ERROR,
            providers=("ado",), modes=(MODE_AUDIT, MODE_NL_STRICT),
            repro=("ado", _REPRO_SEC007))
def _sec007_selfhosted_expuesto_a_pr(doc, ctxs, lines) -> list:
    if not _pr_esta_activo(doc):
        return []
    out, vistos = [], set()
    for ctx in ctxs:
        if not pool_is_self_hosted(ctx.pool):   # dinamico => abstencion (§4.4)
            continue
        nombre = str(ctx.pool.get("name"))
        if nombre in vistos:
            continue
        vistos.add(nombre)
        out.append(finding(
            code="SEC007", severity=SEV_ERROR,
            message="Un pool self-hosted queda expuesto a codigo de pull request.",
            location=ctx.location, line=line_of_pair(lines, "name:", nombre),
            evidence="pool self-hosted %s con pr activo" % nombre,
            remediation=("Cualquiera que abra un PR ejecuta codigo en tu servidor. La disciplina "
                         "que ya sigue este repo es separarlo: validacion de PR en pool hosted y "
                         "deploy en self-hosted con pr: none. Mantenela."),
            providers=("ado",),
        ))
    return out


# ═════════════════════════════ SEC008 ═════════════════════════════

_REPRO_SEC008 = """\
stages:
- stage: Deploy
  jobs:
  - deployment: DeployProd
    environment: 'Produccion'
    strategy:
      runOnce:
        deploy:
          steps:
          - script: echo desplegando
"""


@audit_rule("SEC008", severity_audit=SEV_WARNING, severity_nl=None,
            providers=("ado",), modes=(MODE_AUDIT,),
            repro=("ado", _REPRO_SEC008))
def _sec008_prod_sin_gate(doc, lines, notes) -> list:
    out = []

    def _jobs():
        for j, jb in enumerate(doc.get("jobs") or []):
            if isinstance(jb, dict) and "deployment" in jb:
                yield jb, "jobs[%d]" % j
        for i, st in enumerate(doc.get("stages") or []):
            if not isinstance(st, dict):
                continue
            for j, jb in enumerate(st.get("jobs") or []):
                if isinstance(jb, dict) and "deployment" in jb:
                    yield jb, "stages[%d].jobs[%d]" % (i, j)

    for jb, location in _jobs():
        env = jb.get("environment")
        if isinstance(env, dict):
            env = env.get("name")
        if not isinstance(env, str) or not env.strip():
            continue
        if is_dynamic(env):
            notes.append("SEC008 no pudo evaluar %s.environment: valor dinamico" % location)
            continue
        bajo = env.lower()
        if not any(m in bajo for m in _PROD_MARKERS):
            continue
        out.append(finding(
            code="SEC008", severity=SEV_WARNING,
            message="Hay un deploy a un ambiente de produccion sin gate verificable desde el YAML.",
            location=location, line=line_of(lines, env),
            evidence="environment: '%s'" % env,
            remediation=("El check de aprobacion de un Environment vive en la configuracion de "
                         "ADO, no en el YAML: desde aca no se puede verificar. Confirma a mano "
                         "que el Environment tiene aprobacion manual antes de que este stage "
                         "llegue a correr."),
            providers=("ado",),
        ))
    return out


# ═════════════════════════════ Orquestador SEC ═════════════════════════════

def check_security(yaml_text, *, provider, profile=None, mode=MODE_AUDIT) -> tuple:
    """→ (findings, undetermined_notes). Determinista, sin LLM, sin red."""
    if mode not in _MODES:
        raise ValueError("mode %r invalido (validos: %s)" % (mode, ", ".join(_MODES)))
    try:
        doc = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        return (), ()
    if not isinstance(doc, dict):
        return (), ()
    lines = (yaml_text or "").splitlines()
    ctxs = iter_steps(doc)
    notes: list = []

    out: list = []
    out += _sec001_secreto_literal(ctxs, doc, lines, provider)
    out += _sec002_secreto_al_log(ctxs, lines, provider)
    if provider == "ado":
        out += _sec003_imagen_sin_pin(ctxs, lines)
    out += _sec004_persist_credentials(ctxs, lines, provider)
    if provider == "ado":
        out += _sec005_artefacto_webconfig(doc, ctxs, lines)
    out += _sec006_fallo_enmascarado(ctxs, lines, provider)
    if provider == "ado":
        out += _sec007_selfhosted_expuesto_a_pr(doc, ctxs, lines)
        if mode == MODE_AUDIT:   # en NL_STRICT lo cubre RS009: no se duplica
            out += _sec008_prod_sin_gate(doc, lines, notes)

    from services.cicd_audit_core import AUDIT_RULES  # noqa: PLC0415
    if mode == MODE_NL_STRICT:
        ajustados = []
        for f in out:
            spec = AUDIT_RULES.get(f.code)
            if spec and spec.severity_nl and spec.severity_nl != f.severity:
                ajustados.append(finding(
                    code=f.code, severity=spec.severity_nl, message=f.message,
                    location=f.location, line=f.line, evidence=f.evidence,
                    remediation=f.remediation, providers=f.providers))
            else:
                ajustados.append(f)
        out = ajustados
    return tuple(out), tuple(notes)
