"""services/pipeline_recommendations.py — Plan 248 F2. Las 4 reglas OPT.

PURO: sin red, sin LLM, sin config, sin disco. Sólo evalúa en MODE_AUDIT: una
recomendación de eficiencia sobre un YAML que Stacky acaba de generar es ruido.
"""
from __future__ import annotations

import yaml

from services.cicd_audit_core import (
    MODE_AUDIT,
    SEV_INFO,
    SEV_WARNING,
    audit_rule,
    finding,
    is_dynamic,
    iter_steps,
    job_key,
    line_of,
    line_of_pair,
    pool_is_self_hosted,
)
from services.cicd_semantic_rules import _MODES, _task_inputs

RECOMMENDATION_RULES_VERSION = "248.1"

_RESTORE_TASKS = {"NuGetCommand@2": "restore", "DotNetCoreCLI@2": "restore"}
_BUILD_TASKS = ("VSBuild@1", "MSBuild@1")


# ═════════════════════════════ OPT001 ═════════════════════════════

_REPRO_OPT001 = """\
pr:
  branches:
    include: [ main ]
steps:
- task: NuGetCommand@2
  inputs:
    command: 'restore'
"""


@audit_rule("OPT001", severity_audit=SEV_INFO, severity_nl=None,
            providers=("ado",), modes=(MODE_AUDIT,), repro=("ado", _REPRO_OPT001))
def _opt001_restore_sin_cache(doc, ctxs, lines) -> list:
    from services.cicd_security_rules import _pr_esta_activo  # noqa: PLC0415

    if not _pr_esta_activo(doc):
        return []
    restore_ctx = None
    for ctx in ctxs:
        ref = str(ctx.step.get("task") or "")
        esperado = _RESTORE_TASKS.get(ref)
        if not esperado:
            continue
        if str(_task_inputs(ctx.step).get("command") or "") == esperado:
            restore_ctx = restore_ctx or ctx
    if restore_ctx is None:
        return []
    for ctx in ctxs:
        if str(ctx.step.get("task") or "").startswith("Cache@"):
            return []
    return [finding(
        code="OPT001", severity=SEV_INFO,
        message="Este pipeline restaura dependencias desde cero en cada push a cada PR.",
        location=restore_ctx.location, line=line_of(lines, "'restore'"),
        evidence="restore sin Cache@2",
        remediation=("Un Cache@2 con clave sobre packages.config / *.csproj corta ese tiempo "
                     "casi entero cuando las dependencias no cambiaron."),
        providers=("ado",),
    )]


# ═════════════════════════════ OPT002 ═════════════════════════════

_REPRO_OPT002 = """\
steps:
- task: VSBuild@1
  inputs:
    solution: 'x.sln'
- task: DotNetCoreCLI@2
  inputs:
    command: 'test'
    arguments: '--configuration Release'
"""


@audit_rule("OPT002", severity_audit=SEV_INFO, severity_nl=None,
            providers=("ado",), modes=(MODE_AUDIT,), repro=("ado", _REPRO_OPT002))
def _opt002_recompilacion_en_tests(ctxs, lines) -> list:
    out = []
    por_job = {}
    for ctx in ctxs:
        por_job.setdefault(job_key(ctx.location), []).append(ctx)   # C2 — NUNCA rsplit crudo
    for _job, pasos in sorted(por_job.items()):
        hubo_build = False
        for ctx in pasos:
            ref = str(ctx.step.get("task") or "")
            inputs = _task_inputs(ctx.step)
            if ref in _BUILD_TASKS or (ref.startswith("DotNetCoreCLI@")
                                       and inputs.get("command") == "build"):
                hubo_build = True
                continue
            if not (ref.startswith("DotNetCoreCLI@") and inputs.get("command") == "test"):
                continue
            if hubo_build and "--no-build" not in str(inputs.get("arguments") or ""):
                out.append(finding(
                    code="OPT002", severity=SEV_INFO,
                    message="El job compila dos veces: el paso de tests recompila la solucion.",
                    location=ctx.location, line=line_of(lines, "'test'"),
                    evidence="command: test sin --no-build",
                    remediation=("dotnet test recompila por default. Si el proyecto de test es "
                                 "parte de la solucion que ya compilaste, agrega --no-build. Si "
                                 "no es parte de la solucion, ignora este aviso y suprimilo."),
                    providers=("ado",),
                ))
    return out


# ═════════════════════════════ OPT003 ═════════════════════════════

_REPRO_OPT003 = """\
pool:
  name: 'MI-SERVIDOR'
jobs:
- job: Deploy
  steps:
  - script: echo desplegando
"""


@audit_rule("OPT003", severity_audit=SEV_WARNING, severity_nl=None,
            providers=("ado",), modes=(MODE_AUDIT,), repro=("ado", _REPRO_OPT003))
def _opt003_selfhosted_sin_timeout(doc, ctxs, lines, notes) -> list:
    raiz_timeout = doc.get("timeoutInMinutes") is not None
    out, vistos = [], set()
    for ctx in ctxs:
        pool = ctx.pool if isinstance(ctx.pool, dict) else {}
        nombre = pool.get("name")
        if isinstance(nombre, str) and is_dynamic(nombre):
            nota = "OPT003 no pudo evaluar %s: pool con nombre dinamico" % job_key(ctx.location)
            if nota not in notes:
                notes.append(nota)
            continue
        if not pool_is_self_hosted(pool):
            continue
        clave = job_key(ctx.location)
        if clave in vistos:
            continue
        vistos.add(clave)
        jb_doc, st_doc = _job_and_stage(doc, clave)
        if raiz_timeout or (jb_doc or {}).get("timeoutInMinutes") is not None \
                or (st_doc or {}).get("timeoutInMinutes") is not None:
            continue
        etiqueta = (jb_doc or {}).get("deployment") or (jb_doc or {}).get("job") or ""
        linea = (line_of_pair(lines, "deployment:", str(etiqueta))
                 or line_of_pair(lines, "job:", str(etiqueta))
                 or line_of_pair(lines, "name:", str(nombre)))
        out.append(finding(
            code="OPT003", severity=SEV_WARNING,
            message="Un job self-hosted no declara limite de tiempo.",
            location=ctx.location, line=linea,
            evidence="pool self-hosted %s sin timeoutInMinutes" % nombre,
            remediation=("En agentes self-hosted el timeout por default de ADO es sin limite "
                         "(verifica el default de tu organizacion): un job colgado inmoviliza el "
                         "agente del servidor para siempre. Declara timeoutInMinutes acorde a lo "
                         "que tarda el deploy."),
            providers=("ado",),
        ))
    return out


def _job_and_stage(doc: dict, clave: str) -> tuple:
    """Resuelve (job_doc, stage_doc) desde un job_key del walk."""
    if clave == "(root)":
        return None, None
    partes = clave.split(".")
    st_doc = None
    jb_doc = None
    contenedor = doc
    for parte in partes:
        if parte.startswith("stages["):
            idx = int(parte[len("stages["):-1])
            stages = doc.get("stages") or []
            if idx >= len(stages):
                return None, None
            st_doc = stages[idx]
            contenedor = st_doc
        elif parte.startswith("jobs[") or parte.startswith("deployments["):
            idx = int(parte[parte.index("[") + 1:-1])
            jobs = (contenedor or {}).get("jobs") or []
            reales = [j for j in jobs if isinstance(j, dict)]
            if parte.startswith("deployments["):
                reales = [j for j in reales if "deployment" in j]
            else:
                reales = [j for j in reales if "deployment" not in j]
            if idx < len(reales):
                jb_doc = reales[idx]
    return jb_doc, st_doc


# ═════════════════════════════ OPT004 ═════════════════════════════

_REPRO_OPT004 = """\
steps:
- checkout: self
"""


@audit_rule("OPT004", severity_audit=SEV_INFO, severity_nl=None,
            providers=("ado", "gitlab"), modes=(MODE_AUDIT,), repro=("ado", _REPRO_OPT004))
def _opt004_checkout_historial_completo(ctxs, lines, provider) -> list:
    out = []
    ordinal = 0
    for ctx in ctxs:
        step = ctx.step
        if "checkout" not in step:
            continue
        ordinal += 1
        if step.get("fetchDepth") is not None:
            continue
        out.append(finding(
            code="OPT004", severity=SEV_INFO,
            message="El checkout trae todo el historial del repositorio.",
            location=ctx.location,
            line=line_of(lines, "checkout:", occurrence=ordinal),
            evidence="checkout explicito sin fetchDepth",
            remediation=("Si el job solo necesita los archivos actuales, fetchDepth: 1 baja el "
                         "tiempo de checkout y el disco del agente."),
            providers=("ado", "gitlab"),
        ))
    return out


# ═════════════════════════════ Orquestador OPT ═════════════════════════════

def check_recommendations(yaml_text, *, provider, mode=MODE_AUDIT) -> tuple:
    """→ (findings, undetermined_notes). Sólo evalúa en MODE_AUDIT."""
    if mode not in _MODES:
        raise ValueError("mode %r invalido (validos: %s)" % (mode, ", ".join(_MODES)))
    if mode != MODE_AUDIT:
        return (), ()
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
    if provider == "ado":
        out += _opt001_restore_sin_cache(doc, ctxs, lines)
        out += _opt002_recompilacion_en_tests(ctxs, lines)
        out += _opt003_selfhosted_sin_timeout(doc, ctxs, lines, notes)
    out += _opt004_checkout_historial_completo(ctxs, lines, provider)
    return tuple(out), tuple(notes)
