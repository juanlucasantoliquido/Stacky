"""services/pipeline_profiler.py — Plan 247. Perfilador determinista de pipelines ADO.

Qué es, qué hace y con qué está hecha cada pipeline: stack, anatomía de fases
(incluidas las AUSENTES), artefactos, entornos, agentes, disparadores y un propósito
en 1 línea. Cada campo lleva su evidencia y su confianza; lo que no se puede
determinar vale `desconocido`, NUNCA una suposición.

READ-ONLY y PURO: no toca disco, no toca red y NO usa modelo en el camino default.

C1/C14 (v2) — REUSO POR IMPORT. `cicd_semantic_rules.py` es superficie exclusiva del
plan 249: NO se edita. Los nombres privados se importan con alias público EN ESTE
módulo. Si el 249 los renombra, rompe `test_iter_step_contexts_es_el_mismo_objeto`
con un mensaje claro, nunca el arranque del backend.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace

import yaml

from services.cicd_semantic_rules import (
    MAX_YAML_BYTES,                        # 512 * 1024 — ya definido en :51, NO se redefine
    _iter_steps as iter_step_contexts,     # recorre las 3 raíces de ADO + jobs `- deployment:`
    _pool_is_hosted,
    _pool_os_is_windows,
    _StepCtx as StepContext,               # .step .location .pool .stage_doc .in_deployment
    _task_inputs,
)
from services.cicd_task_catalog import extract_task_dicts, is_deploy_step
from services.pipeline_renderers import scan_unsupported

CONTRACT_VERSION = "247.1"

CONF_HIGH = "alta"            # evidencia directa e inequívoca (ref de tarea, clave del YAML)
CONF_MEDIUM = "media"         # heurística sobre un dato EXPLÍCITO del YAML (texto de un input)
CONF_UNKNOWN = "desconocido"  # no determinable — NUNCA se adivina


@dataclass(frozen=True)
class Evidence:
    location: str   # "stages[1].deployments[0].steps[2]" | "pool" | "(documento)"
    detail: str     # "task VSBuild@1" | "vmImage: windows-2022" | "environment: 'Test'"


@dataclass(frozen=True)
class ProfileField:
    value: object            # tuple | bool | str  (nunca None)
    confidence: str          # CONF_*
    evidence: tuple = ()     # tuple[Evidence, ...]


@dataclass(frozen=True)
class EnvironmentRef:
    name: str                # literal tal cual aparece, sin resolver
    kind: str                # "dev"|"qa"|"test"|"prod"|"desconocido"
    resolved: bool           # False si `name` contiene "${{"
    possible_values: tuple = ()   # de `parameters[].values`, si se pudo resolver el nombre


@dataclass(frozen=True)
class AgentPool:
    kind: str            # "hosted" | "self_hosted" | "heredado_sin_declarar"
    name: str            # vmImage o pool name, literal
    os: object = None    # True (windows) | False (no windows) | None (desconocido)


@dataclass(frozen=True)
class PipelineProfile:
    contract_version: str
    source_path: str
    stack: ProfileField                # value: tuple[str, ...]
    phases: dict                       # str -> ProfileField (value: bool)
    artifacts_published: ProfileField  # value: tuple[str, ...]
    artifacts_consumed: ProfileField   # value: tuple[str, ...]
    environments: ProfileField         # value: tuple[EnvironmentRef, ...]
    agents: ProfileField               # value: tuple[AgentPool, ...]
    triggers: ProfileField             # value: tuple[str, ...]
    purpose: str = ""
    purpose_source: str = "plantilla"  # "plantilla" | "llm"
    not_understood: tuple = ()         # salida literal de scan_unsupported()
    parse_error: object = None         # str | None


STACK_TO_DETECTOR_ID: dict = {          # puente informativo hacia el Plan 97, sin acoplar
    "dotnet_framework": "dotnet",
    "dotnet_core":      "dotnet",
    "sql_dacpac":       "dotnet",
    "node":             "node",
    "python":           "python",
    "container":        None,           # detect_stack no tiene id para contenedores
}


def field_is_coherent(field: ProfileField) -> bool:
    """Invariante anti-alucinación (§3.2.1). Un campo con valor DEBE tener evidencia
    y no puede declararse desconocido. Un campo SIN valor es siempre coherente:
    puede o no traer evidencia de POR QUÉ no se pudo determinar."""
    tiene_valor = field.value if isinstance(field.value, bool) else bool(field.value)
    if tiene_valor:
        return bool(field.evidence) and field.confidence != CONF_UNKNOWN
    return True


def empty_profile(source_path: str = "", parse_error: str = None) -> PipelineProfile:
    """Perfil vacío coherente: todos los campos sin valor y con confianza desconocida."""
    vacio = ProfileField((), CONF_UNKNOWN, ())
    return PipelineProfile(
        contract_version=CONTRACT_VERSION,
        source_path=source_path,
        stack=vacio,
        phases={},
        artifacts_published=vacio,
        artifacts_consumed=vacio,
        environments=vacio,
        agents=vacio,
        triggers=vacio,
        purpose="",
        purpose_source=PURPOSE_SOURCE_TEMPLATE,
        not_understood=(),
        parse_error=parse_error,
    )


def _evidence_to_dict(ev: Evidence) -> dict:
    return {"location": ev.location, "detail": ev.detail}


def _value_to_json(value):
    if isinstance(value, tuple) or isinstance(value, list):
        return [_value_to_json(v) for v in value]
    if isinstance(value, EnvironmentRef):
        return {
            "name": value.name,
            "kind": value.kind,
            "resolved": value.resolved,
            "possible_values": list(value.possible_values),
        }
    if isinstance(value, AgentPool):
        return {"kind": value.kind, "name": value.name, "os": value.os}
    return value


def _field_to_dict(field: ProfileField) -> dict:
    return {
        "value": _value_to_json(field.value),
        "confidence": field.confidence,
        "evidence": [_evidence_to_dict(e) for e in field.evidence],
    }


def profile_to_dict(profile: PipelineProfile) -> dict:
    """JSON-safe, claves estables (las consume pipelineProfileModel.ts y el plan 248)."""
    return {
        "contract_version": profile.contract_version,
        "source_path": profile.source_path,
        "stack": _field_to_dict(profile.stack),
        "phases": {k: _field_to_dict(v) for k, v in (profile.phases or {}).items()},
        "artifacts_published": _field_to_dict(profile.artifacts_published),
        "artifacts_consumed": _field_to_dict(profile.artifacts_consumed),
        "environments": _field_to_dict(profile.environments),
        "agents": _field_to_dict(profile.agents),
        "triggers": _field_to_dict(profile.triggers),
        "purpose": profile.purpose,
        "purpose_source": profile.purpose_source,
        "not_understood": list(profile.not_understood or ()),
        "parse_error": profile.parse_error,
    }


# ═════════════════════════════════════════════════════════════════════════════
# F1 — Stack tecnológico, agentes/pools y disparadores
# ═════════════════════════════════════════════════════════════════════════════

STACK_IDS = ("dotnet_framework", "dotnet_core", "sql_dacpac", "node", "python", "container")
# ↑ el ORDEN es la precedencia de salida de la tupla `stack`. Determinista y documentado.

TRIGGER_KINDS = ("push", "pr", "scheduled", "manual")

SUPPORTED_PROVIDERS = ("ado",)   # el 249 agrega "gitlab" a ESTA tupla, no a un `if`

_DOTNET_CORE_BUILD_COMMANDS = ("build", "publish", "restore")


def _step_locations(doc: dict) -> dict:
    """id(paso) -> location, construido con el recorrido con contexto.

    Permite que una señal hallada con `extract_task_dicts` (que no lleva contexto)
    cite una `location` REAL del documento en vez de una inventada.
    """
    out: dict = {}
    try:
        for ctx in iter_step_contexts(doc):
            out[id(ctx.step)] = ctx.location
    except Exception:
        return {}
    return out


def _loc_of(step: dict, locations: dict) -> str:
    return locations.get(id(step), "(documento)")


def _has_container_key(node) -> bool:
    """C18: `container:` en CUALQUIER nivel del doc parseado."""
    if isinstance(node, dict):
        if "container" in node:
            return True
        return any(_has_container_key(v) for v in node.values())
    if isinstance(node, list):
        return any(_has_container_key(v) for v in node)
    return False


def detect_pipeline_stacks(doc: dict) -> ProfileField:
    """C16: NO `detect_stacks` — a una letra de `detect_stack` del Plan 97, que perfila REPOS."""
    tasks = extract_task_dicts(doc)
    locations = _step_locations(doc)
    hits: dict = {}

    def _add(stack_id: str, ev: Evidence):
        hits.setdefault(stack_id, []).append(ev)

    for task in tasks:
        ref = str(task.get("task") or "")
        inputs = _task_inputs(task)
        loc = _loc_of(task, locations)

        if ref == "VSBuild@1":
            _add("dotnet_framework", Evidence(loc, "task VSBuild@1"))
        elif ref == "NuGetCommand@2" and "restoreSolution" in inputs:
            _add("dotnet_framework", Evidence(loc, "task NuGetCommand@2 con restoreSolution"))

        if ref == "UseDotNet@2":
            _add("dotnet_core", Evidence(loc, "task UseDotNet@2"))
        elif ref == "DotNetCoreCLI@2":
            command = str(inputs.get("command") or "").strip().lower()
            if command in _DOTNET_CORE_BUILD_COMMANDS:
                _add("dotnet_core", Evidence(loc, "task DotNetCoreCLI@2 command: %s" % command))

        for key, value in inputs.items():
            if isinstance(value, str) and (".sqlproj" in value or ".dacpac" in value):
                _add("sql_dacpac", Evidence(loc, "input %s menciona %s" % (
                    key, ".sqlproj" if ".sqlproj" in value else ".dacpac")))
                break

        if ref in ("Npm@1", "NodeTool@0"):
            _add("node", Evidence(loc, "task %s" % ref))
        if ref == "UsePythonVersion@0":
            _add("python", Evidence(loc, "task UsePythonVersion@0"))
        if ref == "Docker@2":
            _add("container", Evidence(loc, "task Docker@2"))

    if "container" not in hits and _has_container_key(doc):
        _add("container", Evidence("(documento)", "el documento declara una clave container"))

    if not hits:
        return ProfileField((), CONF_UNKNOWN, ())
    ids = tuple(s for s in STACK_IDS if s in hits)
    evidencia = tuple(ev for s in ids for ev in hits[s])
    return ProfileField(ids, CONF_HIGH, evidencia)


def detect_agents(doc: dict) -> ProfileField:
    """Pools EFECTIVOS (job > stage > raíz). Deduplica por (kind, name), primera aparición."""
    vistos: list = []
    evidencia: list = []
    claves: set = set()
    for ctx in iter_step_contexts(doc):
        pool = ctx.pool if isinstance(ctx.pool, dict) else {}
        if _pool_is_hosted(pool):
            agent = AgentPool("hosted", str(pool.get("vmImage") or ""), _pool_os_is_windows(pool))
            detalle = "vmImage: %s" % agent.name
        elif pool.get("name"):
            # El SO de un pool self-hosted NO se declara: afirmarlo sería inventar.
            agent = AgentPool("self_hosted", str(pool.get("name")), None)
            detalle = "pool name: %s" % agent.name
        else:
            agent = AgentPool("heredado_sin_declarar", "", None)
            detalle = "el paso no declara pool en ningun nivel"
        clave = (agent.kind, agent.name)
        if clave in claves:
            continue
        claves.add(clave)
        vistos.append(agent)
        evidencia.append(Evidence(ctx.location, detalle))
    if not vistos:
        return ProfileField((), CONF_UNKNOWN, ())
    return ProfileField(tuple(vistos), CONF_HIGH, tuple(evidencia))


def detect_triggers(doc: dict) -> ProfileField:
    """En ADO, `trigger:` AUSENTE = CI implícito en todas las ramas; `trigger: none` = apagado."""
    kinds: list = []
    evidencia: list = []

    trg = doc.get("trigger")
    if isinstance(trg, dict) or trg is None:
        kinds.append("push")
        if "trigger" in doc:
            evidencia.append(Evidence("trigger", "bloque trigger declarado"))
        else:
            evidencia.append(Evidence("(documento)", "sin bloque trigger: CI implicito"))

    pr = doc.get("pr")
    if isinstance(pr, dict) or pr is None:
        kinds.append("pr")
        if "pr" in doc:
            evidencia.append(Evidence("pr", "bloque pr declarado"))
        else:
            evidencia.append(Evidence("(documento)", "sin bloque pr: validacion de PR implicita"))

    if doc.get("schedules"):
        kinds.append("scheduled")
        evidencia.append(Evidence("schedules", "el documento declara schedules"))

    if not kinds:
        kinds.append("manual")
        evidencia.append(Evidence("(documento)", "trigger y pr apagados, sin schedules"))

    return ProfileField(tuple(kinds), CONF_HIGH, tuple(evidencia))


# ═════════════════════════════════════════════════════════════════════════════
# F2 — Anatomía: qué fases tiene y cuáles NO, artefactos y entornos
# ═════════════════════════════════════════════════════════════════════════════

PHASE_IDS = ("build", "test", "package", "publish_artifact", "deploy")

# Construcciones que PODRÍAN esconder pasos en otro archivo. `matrix` y
# `compile_time_expression` NO esconden pasos (los pasos son visibles; sólo hay valores
# sin resolver) y por eso NO degradan la anatomía.
_HIDES_STEPS = ("template", "extends")

_ENV_MARKERS = (("prod", ("prod", "produccion", "producción")),
                ("qa",   ("qa", "uat")),
                ("test", ("test", "tst", "staging", "stg")),
                ("dev",  ("dev", "desarrollo")))

_PUBLISH_TASKS = ("PublishBuildArtifacts@1", "PublishPipelineArtifact@1")

_PARAM_EXPR_RE = re.compile(r"^\$\{\{\s*parameters\.([A-Za-z0-9_]+)\s*\}\}$")


def _signals_for(phase_id: str, doc: dict) -> list:
    tasks = extract_task_dicts(doc)
    locations = _step_locations(doc)
    hits: list = []
    for task in tasks:
        ref = str(task.get("task") or "")
        inputs = _task_inputs(task)
        loc = _loc_of(task, locations)

        if phase_id == "build":
            if ref in ("VSBuild@1", "MSBuild@1"):
                hits.append(Evidence(loc, "task %s" % ref))
            elif ref == "DotNetCoreCLI@2" and str(
                inputs.get("command") or ""
            ).strip().lower() in ("build", "publish"):
                hits.append(Evidence(loc, "task DotNetCoreCLI@2 command: %s" % inputs.get("command")))

        elif phase_id == "test":
            if ref == "DotNetCoreCLI@2" and str(
                inputs.get("command") or ""
            ).strip().lower() == "test":
                hits.append(Evidence(loc, "task DotNetCoreCLI@2 command: test"))
            elif ref in ("PublishTestResults@2", "VSTest@2"):
                hits.append(Evidence(loc, "task %s" % ref))

        elif phase_id == "package":
            for key, value in inputs.items():
                if not isinstance(value, str):
                    continue
                if "WebPublishMethod=Package" in value or "PackageLocation" in value:
                    hits.append(Evidence(loc, "input %s menciona empaquetado" % key))
                    break
                if ref == "CopyFiles@2" and "ArtifactStagingDirectory" in value:
                    hits.append(Evidence(loc, "task CopyFiles@2 hacia ArtifactStagingDirectory"))
                    break

        elif phase_id == "publish_artifact":
            if ref in _PUBLISH_TASKS:
                hits.append(Evidence(loc, "task %s" % ref))

        elif phase_id == "deploy":
            if is_deploy_step(ref, inputs):
                hits.append(Evidence(loc, "paso de despliegue: %s" % ref))

    return hits


def detect_phases(doc: dict, not_understood: tuple) -> dict:
    hay_ciego = any(c in (not_understood or ()) for c in _HIDES_STEPS)
    out: dict = {}
    for phase_id in PHASE_IDS:
        hits = _signals_for(phase_id, doc)
        if hits:
            out[phase_id] = ProfileField(
                True,
                CONF_MEDIUM if phase_id == "package" else CONF_HIGH,
                tuple(hits),
            )
        elif hay_ciego:
            # Los pasos podrían vivir en un template/extends que no leímos.
            out[phase_id] = ProfileField(False, CONF_UNKNOWN, (
                Evidence("(documento)",
                         "el pipeline usa %s: los pasos pueden estar en otro archivo"
                         % ", ".join(c for c in _HIDES_STEPS if c in not_understood)),))
        else:
            # Documento completo y sin señal ⇒ la AUSENCIA es un hecho verificado.
            out[phase_id] = ProfileField(False, CONF_HIGH, (
                Evidence("(documento)",
                         "ningun paso del pipeline corresponde a la fase '%s'" % phase_id),))
    return out


def detect_artifacts(doc: dict) -> tuple:
    """(published, consumed). LITERAL: prohibido resolver $(...) ni ${{ }} (plan 251)."""
    locations = _step_locations(doc)

    publicados: list = []
    ev_pub: list = []
    for task in extract_task_dicts(doc):
        ref = str(task.get("task") or "")
        if ref not in _PUBLISH_TASKS:
            continue
        inputs = _task_inputs(task)
        nombre = inputs.get("ArtifactName")
        if nombre is None:
            nombre = inputs.get("artifactName")
        if nombre is None:
            continue
        nombre = str(nombre)
        if nombre in publicados:
            continue
        publicados.append(nombre)
        ev_pub.append(Evidence(_loc_of(task, locations), "%s ArtifactName: %s" % (ref, nombre)))

    consumidos: list = []
    ev_con: list = []
    for ctx in iter_step_contexts(doc):
        step = ctx.step if isinstance(ctx.step, dict) else {}
        if "download" not in step or "artifact" not in step:
            continue
        nombre = str(step.get("artifact") or "")
        if not nombre or nombre in consumidos:
            continue
        consumidos.append(nombre)
        ev_con.append(Evidence(ctx.location, "download artifact: %s" % nombre))

    pub_field = (ProfileField(tuple(publicados), CONF_HIGH, tuple(ev_pub))
                 if publicados else ProfileField((), CONF_UNKNOWN, ()))
    con_field = (ProfileField(tuple(consumidos), CONF_HIGH, tuple(ev_con))
                 if consumidos else ProfileField((), CONF_UNKNOWN, ()))
    return pub_field, con_field


def _resolve_parameter_values(doc: dict, expr: str) -> tuple:
    """Sólo `${{ parameters.<nombre> }}` exacto. Cualquier otra forma -> ()."""
    match = _PARAM_EXPR_RE.match(str(expr or "").strip())
    if not match:
        return ()
    nombre = match.group(1)
    for item in (doc.get("parameters") or []):
        if isinstance(item, dict) and str(item.get("name") or "") == nombre:
            values = item.get("values")
            return tuple(str(v) for v in values) if isinstance(values, list) else ()
    return ()


def _iter_deployment_jobs(doc: dict):
    """(job_doc, location_del_environment) para cada job `- deployment:` del documento."""
    for j, jb_doc in enumerate(doc.get("jobs") or []):
        if isinstance(jb_doc, dict) and "deployment" in jb_doc:
            yield jb_doc, "jobs[%d].environment" % j
    for i, st_doc in enumerate(doc.get("stages") or []):
        if not isinstance(st_doc, dict):
            continue
        for j, jb_doc in enumerate(st_doc.get("jobs") or []):
            if isinstance(jb_doc, dict) and "deployment" in jb_doc:
                yield jb_doc, "stages[%d].jobs[%d].environment" % (i, j)


def detect_environments(doc: dict) -> ProfileField:
    """C4: DEDUPLICA por `EnvironmentRef.name`, conservando la primera aparición."""
    refs: list = []
    evidencia: list = []
    nombres: set = set()
    for jb_doc, loc in _iter_deployment_jobs(doc):
        entorno = jb_doc.get("environment")
        if isinstance(entorno, dict):
            entorno = entorno.get("name")
        name = str(entorno or "")
        if not name or name in nombres:
            continue
        nombres.add(name)
        resolved = "${{" not in name
        kind = "desconocido"
        possible: tuple = ()
        if resolved:
            low = name.lower()
            for k, markers in _ENV_MARKERS:
                if any(m in low for m in markers):
                    kind = k
                    break
        else:
            possible = _resolve_parameter_values(doc, name)
        refs.append(EnvironmentRef(name, kind, resolved, possible))
        detalle = "environment: '%s'" % name
        if possible:
            detalle += " (valores declarados: %s)" % ", ".join(possible)
        evidencia.append(Evidence(loc, detalle))
    if not refs:
        return ProfileField((), CONF_UNKNOWN, ())
    return ProfileField(tuple(refs), CONF_HIGH, tuple(evidencia))


# ═════════════════════════════════════════════════════════════════════════════
# F3 — Propósito en 1 línea: plantilla determinista + narración LLM opcional
# ═════════════════════════════════════════════════════════════════════════════

PURPOSE_MAX_CHARS = 200
PURPOSE_SOURCE_TEMPLATE = "plantilla"
PURPOSE_SOURCE_LLM = "llm"

_PHASE_VERBS = {
    "build": "Compila",
    "test": "testea",
    "package": "empaqueta",
    "publish_artifact": "publica artefactos",
    "deploy": "despliega",
}

_STACK_LABELS = {
    "dotnet_framework": ".NET Framework",
    "dotnet_core": ".NET Core",
    "sql_dacpac": "SQL/DACPAC",
    "node": "Node",
    "python": "Python",
    "container": "contenedores",
}

_TRIGGER_LABELS = {
    "push": "push",
    "pr": "pull request",
    "scheduled": "agendado",
    "manual": "manual",
}


def _join_es(items: list) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return "%s y %s" % (", ".join(items[:-1]), items[-1])


def build_purpose_template(profile: PipelineProfile) -> str:
    """Gramática fija, sin modelo. Determinista y acotada a PURPOSE_MAX_CHARS."""
    phases = profile.phases or {}
    verbos = [_PHASE_VERBS[p] for p in PHASE_IDS
              if p in phases and phases[p].value is True]
    frase = _join_es(verbos) if verbos else "No compila, no testea ni despliega"

    stack_ids = profile.stack.value if isinstance(profile.stack.value, tuple) else ()
    if stack_ids:
        frase += " para %s" % ", ".join(_STACK_LABELS.get(s, s) for s in stack_ids)

    publicados = profile.artifacts_published.value or ()
    if publicados:
        frase += "; publica %d artefacto(s)" % len(publicados)

    entornos = profile.environments.value or ()
    if entornos:
        nombres = [e.name if e.resolved else "<expresion sin resolver>" for e in entornos]
        frase += "; despliega a %s" % ", ".join(nombres)

    frase += "."

    triggers = profile.triggers.value or ()
    if triggers:
        frase += " Dispara: %s." % ", ".join(_TRIGGER_LABELS.get(t, t) for t in triggers)

    agentes = profile.agents.value or ()
    if agentes:
        etiquetas = []
        for a in agentes:
            if a.kind == "hosted":
                etiquetas.append("hosted %s" % a.name)
            elif a.kind == "self_hosted":
                etiquetas.append("self-hosted %s" % a.name)
            else:
                etiquetas.append("agente heredado")
        frase += " Agente: %s." % " + ".join(etiquetas)

    test_field = phases.get("test")
    if test_field is not None and test_field.value is False and test_field.confidence == CONF_HIGH:
        frase += " No corre tests."

    if profile.not_understood:
        frase += " No entendido: %s." % ", ".join(profile.not_understood)

    frase = " ".join(frase.split())
    if len(frase) > PURPOSE_MAX_CHARS:
        frase = frase[: PURPOSE_MAX_CHARS - 1] + "…"
    return frase


_NARRATION_SYSTEM = (
    "Reescribi en UNA sola linea en espanol, maximo 200 caracteres, el proposito de una "
    "pipeline de CI/CD. USA EXCLUSIVAMENTE los datos del JSON; esta PROHIBIDO agregar "
    "cualquier hecho que no este ahi. Responde JSON: {\"purpose\": \"...\"}"
)


@dataclass
class PurposeCallSpec:
    """Pedido de narracion. DESACOPLADO a proposito del cliente de modelo.

    Este modulo NO importa el cliente de modelo (K4, asercion (a)): el caller inyecta
    `llm_caller`. Los nombres de campo son los del contrato del cliente y hay un
    centinela que se pone rojo si el contrato deriva
    (`test_purpose_call_spec_no_derivo_del_contrato`).
    """
    project: str
    agent_kind: str
    prompt_type: str
    model: str
    system: str
    user: str
    max_output_tokens: int = 512
    temperature: float = 0.0
    fixture_id: object = None
    expect_json: bool = True


def narrate_purpose(profile: PipelineProfile, *, llm_caller=None,
                    model: str = "claude-haiku-4-5") -> tuple:
    """Devuelve (texto, fuente). NUNCA lanza. Sin llm_caller ⇒ plantilla."""
    base = build_purpose_template(profile)
    if llm_caller is None:
        return base, PURPOSE_SOURCE_TEMPLATE
    try:
        spec = PurposeCallSpec(
            project="pipeline_profiler",
            agent_kind="recommendation",
            prompt_type="plan247_purpose_v1",
            model=model,
            system=_NARRATION_SYSTEM,
            user=json.dumps(profile_to_dict(profile), ensure_ascii=False),  # el PERFIL, no el YAML
            expect_json=True,
            temperature=0.0,
            fixture_id="plan247_purpose",
        )
    except Exception:
        return base, PURPOSE_SOURCE_TEMPLATE
    try:
        result = llm_caller(spec)
    except Exception:
        return base, PURPOSE_SOURCE_TEMPLATE
    if not getattr(result, "success", False):
        return base, PURPOSE_SOURCE_TEMPLATE
    texto = ((getattr(result, "parsed_json", None) or {}).get("purpose") or "").strip()
    texto = " ".join(texto.split())                      # una sola línea, siempre
    if not texto or len(texto) > PURPOSE_MAX_CHARS:
        return base, PURPOSE_SOURCE_TEMPLATE
    return texto, PURPOSE_SOURCE_LLM


# ═════════════════════════════════════════════════════════════════════════════
# Entrada pública
# ═════════════════════════════════════════════════════════════════════════════

def profile_pipeline(yaml_text: str, *, provider: str = "ado",
                     source_path: str = "") -> PipelineProfile:
    """Perfil COMPLETO. Nunca lanza salvo por `provider` inválido (falla ruidosa)."""
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            "provider %r no soportado por el perfilador v1 (soportados: %s; GitLab = plan 249)"
            % (provider, ", ".join(SUPPORTED_PROVIDERS))
        )
    if len(yaml_text or "") > MAX_YAML_BYTES:
        return empty_profile(source_path, "el YAML supera 512 KB: fuera del rango soportado")
    try:
        doc = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        return empty_profile(
            source_path, "el YAML no se pudo parsear: %s" % str(exc).splitlines()[0])
    if not isinstance(doc, dict):
        return empty_profile(source_path, "el YAML no es un documento de pipeline (no es un mapa)")

    not_understood = scan_unsupported(yaml_text)
    publicados, consumidos = detect_artifacts(doc)
    profile = PipelineProfile(
        contract_version=CONTRACT_VERSION,
        source_path=source_path,
        stack=detect_pipeline_stacks(doc),
        phases=detect_phases(doc, not_understood),
        artifacts_published=publicados,
        artifacts_consumed=consumidos,
        environments=detect_environments(doc),
        agents=detect_agents(doc),
        triggers=detect_triggers(doc),
        not_understood=not_understood,
        parse_error=None,
    )
    # C5 (v2) — el propósito de PLANTILLA se rellena ACÁ, siempre, sin modelo.
    return replace(profile, purpose=build_purpose_template(profile))
