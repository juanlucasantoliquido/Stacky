"""pipeline_environments.py — Plan 251. Matriz de entornos y valores requeridos.

Nucleo PURO (F1/F2): sin I/O, sin red, sin LLM. La extraccion camina el documento
PARSEADO con yaml.safe_load y NUNCA hace grep sobre el texto crudo (C20 del Plan 243:
agendaweb-ci.yml y ci-dacpac.yml tienen referencias a tareas DENTRO de comentarios).
El VALOR de un secreto no entra ni sale de este modulo.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, asdict
from typing import Iterator, Optional

import yaml

from services.ci_variables import looks_secret
from services.secret_masking import MASK_PLACEHOLDER, mask_token_values

ENV_MATRIX_VERSION = "251.1"

VALUE_KINDS = ("variable", "secret", "service_connection", "server", "deploy_path", "parameter")
CELL_STATES = ("definido", "default", "falta", "manual")
SOURCES = ("predefinida", "yaml_variables", "yaml_parameter_default",
           "caja_fuerte", "registro_servidores", "scope_proveedor", "ninguna")
CONFIDENCE = ("alta", "baja")

PROVIDER_ADO = "azure_devops"
PROVIDER_GITLAB = "gitlab"
PROVIDERS = (PROVIDER_ADO, PROVIDER_GITLAB)

# Variables predefinidas de ADO: JAMAS se piden.
_ADO_PREDEFINED_PREFIXES = ("Build.", "System.", "Agent.", "Pipeline.", "Release.",
                            "Environment.", "Deployment.", "Task.", "Common.")
_ADO_PREDEFINED_EXACT = ("Rev",)

# Claves cuyo VALOR es un bloque de shell: ahi `$(algo)` puede ser sustitucion de
# comando de bash o una variable de PowerShell, NO una variable de pipeline.
_SHELL_KEYS = ("script", "bash", "pwsh", "powershell")

_PATH_INPUT_KEYS = ("filePath", "PathtoPublish", "targetPath", "workingDirectory",
                    "destinationFolder", "SourceFolder", "TargetFolder", "packageForLinux")

_ADO_SERVICE_CONNECTION_KEYS = ("azureSubscription", "ConnectedServiceName",
                                "ConnectedServiceNameARM", "connectedServiceName",
                                "azureResourceManagerConnection", "kubernetesServiceConnection",
                                "dockerRegistryServiceConnection", "publishFeedCredentials")

_ENV_RANK = {"dev": 0, "desarrollo": 0, "development": 0,
             "test": 1, "qa": 1, "testing": 1, "staging": 2, "uat": 2,
             "prod": 3, "produccion": 3, "producción": 3, "production": 3}

ENV_UNICO = "(único)"

_ADO_VAR_RE = re.compile(r"\$\((?P<n>[A-Za-z_][A-Za-z0-9_.]*)\)")
_ADO_TPL_RE = re.compile(r"\$\{\{\s*parameters\.(?P<n>[A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_GL_VAR_RE = re.compile(r"\$\{?(?P<n>[A-Za-z_][A-Za-z0-9_]*)\}?")

# (a) el string ENTERO es una ruta absoluta
_ABS_PATH_FULL_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|/)[^\s\"']*$")
# (b) la ruta esta EMBEBIDA en un texto mayor (cd-deploy-test.yml:136 y :175 tienen la
#     ruta DESPUES de 'Deploy AgendaWeb -> '): confidence SIEMPRE baja -> estado 'manual'.
#     La rama unix exige DOS segmentos: sin eso, un `msbuildArgs: >-` multilinea mete
#     `/p:WebPublishMethod=Package`, `/p:PackageAsSingleFile=true`, ... como "rutas de
#     despliegue" en 4 de los 9 goldens (medido). Eso es exactamente el ruido que mata
#     el KPI-2: 5 filas basura por archivo y el operador deja de mirar la matriz.
_ABS_PATH_EMBEDDED_RE = re.compile(
    r"[A-Za-z]:[\\/][^\s\"'\)\],]{2,}"                   # C:\AIS\AgendaWeb\Web
    r"|(?<=\s)/[^\s\"'\)\],]*/[^\s\"'\)\],]+"            # /opt/app/bin (>= 2 segmentos)
)

_NOTA_ADO_SIN_SCOPING = (
    "en Azure DevOps las variables viven en la definition, no por entorno: "
    "el mismo valor aplica a todos los entornos de esta pipeline"
)
_NOTA_MISMO_VALOR = " (mismo valor para todos los entornos)"
_NOTA_SERVICE_CONNECTION = (
    "Stacky no puede crear ni verificar service connections: creala en la web de "
    "Azure DevOps."
)
_NOTA_RUTA_MANUAL = (
    "ruta absoluta hardcodeada en el YAML — confirmá el valor de cada entorno."
)
_NOTA_CONFIANZA_BAJA = (
    "detectado con confianza baja (aparece dentro de un bloque de shell o de un texto): "
    "confirmalo vos, Stacky no lo da por faltante."
)


# ── Contratos ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Evidence:
    path: str          # "stages[1].jobs[0].steps[2].inputs.filePath"
    excerpt: str       # el string donde aparece, YA pasado por mask_token_values


@dataclass(frozen=True)
class Requirement:
    name: str
    kind: str
    provider: str
    is_secret: bool
    declared_default: Optional[str]
    per_environment: bool
    confidence: str
    evidence: tuple
    note: str = ""     # honestidad: por que este requirement es una SUPOSICION.
                       # El §4.2 del plan lo omitia, pero su propio test
                       # test_f1_bootstrap_servidor_desde_parametro lo exige.


@dataclass(frozen=True)
class Cell:
    requirement: str
    environment: str
    state: str
    source: str
    note: Optional[str]


@dataclass(frozen=True)
class EnvMatrix:
    environments: tuple
    requirements: tuple
    cells: tuple
    pending_count: int
    pending_fingerprint: str
    degraded: tuple


# ── Masking del `declared_default` ───────────────────────────────────────────

# Red A del §3.3 es `mask_token_values`, que sólo conoce 7 PREFIJOS
# (secret_masking.py:11). Un password arbitrario bajo un nombre inocente
# (`SONAR_HOST: 'p4ssw0rd-Un1c0-Rs!'`) NO lo ve ninguna de las dos redes del plan.
# Esta es una tercera red por FORMA GENERICA, acotada para no tapar valores legitimos
# del corpus (`Release`, `Any CPU`, `windows-2022`, `AgendaWeb-drop`, rutas, `$(...)`).
_CRED_MIN_LEN = 16
_CRED_SYMBOLS = set("!@#$%^&*+=~?")


def looks_like_credential_value(value: str) -> bool:
    """Heuristica de FORMA para un valor opaco tipo credencial. Conservadora a
    proposito: preferimos mostrar un valor inocuo antes que tapar medio corpus.

    Excluye: strings cortos, con espacios, expresiones de pipeline, rutas y
    valores sin mezcla de clases de caracteres.
    """
    s = (value or "").strip()
    if len(s) < _CRED_MIN_LEN:
        return False
    if any(c.isspace() for c in s):
        return False
    if "$(" in s or "${{" in s or "${" in s:
        return False
    if _ABS_PATH_FULL_RE.match(s) or s.startswith(("./", "../", "**", "~")):
        return False
    if "/" in s or "\\" in s:          # rutas y globs
        return False
    tiene_min = any(c.islower() for c in s)
    tiene_may = any(c.isupper() for c in s)
    tiene_num = any(c.isdigit() for c in s)
    tiene_sim = any(c in _CRED_SYMBOLS for c in s)
    clases = sum((tiene_min, tiene_may, tiene_num, tiene_sim))
    return clases >= 3


def _mask_default(name: str, value) -> Optional[str]:
    """Redes A (forma conocida), A' (forma generica) y B (nombre), en ese orden.
    B es la mas fuerte y pisa a las otras."""
    if value is None:
        return None
    texto = mask_token_values(str(value))            # red A
    if looks_like_credential_value(texto):           # red A' (extension de este plan)
        texto = MASK_PLACEHOLDER
    if looks_secret(name):                           # red B
        texto = MASK_PLACEHOLDER
    return texto


# ── Recorrido del documento ─────────────────────────────────────────────────

def _iter_nodes(doc, path: str = "", key: str = "") -> Iterator[tuple]:
    """(path, key, value) de cada nodo del documento parseado. Espejo de `_walk`
    (pipeline_renderers.py:39) pero llevando la RUTA, que es la evidencia."""
    yield (path, key, doc)
    if isinstance(doc, dict):
        for k, v in doc.items():
            sub = f"{path}.{k}" if path else str(k)
            yield from _iter_nodes(v, sub, str(k))
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            yield from _iter_nodes(v, f"{path}[{i}]", key)


def _resolve_parameter_expr(text: str, parameters: dict) -> tuple:
    """'${{ parameters.agentPool }}' -> ('agentPool', <default del parametro>)."""
    m = _ADO_TPL_RE.search(str(text or ""))
    if not m:
        return None, None
    nombre = m.group("n")
    spec = parameters.get(nombre) or {}
    default = spec.get("default")
    return nombre, (None if default is None else str(default))


def _declared_variables(doc) -> dict:
    """Todas las variables declaradas: `variables:` de raiz, stage y job.

    Soporta las DOS formas de ADO (mapa y lista de {name,value}). Las claves de
    compile-time `${{ if ... }}:` se ignoran como nombre pero SI se registran las
    variables que declaran adentro (bootstrap:101-112)."""
    out: dict = {}

    def _absorber(bloque) -> None:
        if isinstance(bloque, dict):
            for k, v in bloque.items():
                if str(k).startswith("${{"):
                    _absorber(v)
                    continue
                out.setdefault(str(k), v)
        elif isinstance(bloque, list):
            for item in bloque:
                if not isinstance(item, dict):
                    continue
                if str(item.get("name") or "").startswith("${{"):
                    continue
                if item.get("name") is not None:
                    out.setdefault(str(item["name"]), item.get("value"))
                elif item.get("group") is None:
                    for k, v in item.items():
                        if not str(k).startswith("${{"):
                            out.setdefault(str(k), v)

    for _path, key, value in _iter_nodes(doc):
        if key == "variables":
            _absorber(value)
    return out


def _declared_parameters(doc) -> dict:
    """{name: {"type":, "default":, "values": []}} del bloque `parameters:` de raiz."""
    out: dict = {}
    if not isinstance(doc, dict):
        return out
    bloque = doc.get("parameters")
    if isinstance(bloque, list):
        for item in bloque:
            if isinstance(item, dict) and item.get("name"):
                out[str(item["name"])] = {
                    "type": item.get("type"),
                    "default": item.get("default"),
                    "values": list(item.get("values") or ()),
                    "displayName": item.get("displayName"),
                }
    elif isinstance(bloque, dict):
        for k, v in bloque.items():
            out[str(k)] = {"type": None, "default": v, "values": [], "displayName": None}
    return out


def is_ado_predefined(name: str) -> bool:
    n = str(name or "")
    return n.startswith(_ADO_PREDEFINED_PREFIXES) or n in _ADO_PREDEFINED_EXACT


# ── F1 — extraccion ─────────────────────────────────────────────────────────

class _Acumulador:
    """Deduplica por (name, kind) ACUMULANDO evidencias, en orden de aparicion."""

    def __init__(self) -> None:
        self._orden: list = []
        self._datos: dict = {}

    def add(self, name: str, kind: str, *, path: str, excerpt: str,
            confidence: str = "alta", per_environment: bool = False,
            declared_default=None, note: str = "") -> None:
        nombre = str(name or "").strip()
        if not nombre:
            return
        clave = (nombre, kind)
        ev = Evidence(path=path, excerpt=mask_token_values(str(excerpt))[:400])
        if clave not in self._datos:
            self._orden.append(clave)
            self._datos[clave] = {
                "confidence": confidence, "per_environment": per_environment,
                "declared_default": declared_default, "evidence": [ev], "note": note,
            }
            return
        d = self._datos[clave]
        if ev not in d["evidence"]:
            d["evidence"].append(ev)
        # la confianza ALTA gana: si el mismo nombre aparece una vez fuera de un shell,
        # es una variable de pipeline de verdad.
        if confidence == "alta":
            d["confidence"] = "alta"
        d["per_environment"] = d["per_environment"] or per_environment
        if d["declared_default"] is None and declared_default is not None:
            d["declared_default"] = declared_default
        if note and not d["note"]:
            d["note"] = note

    def build(self, provider: str) -> tuple:
        salida = []
        for nombre, kind in self._orden:
            d = self._datos[(nombre, kind)]
            salida.append(Requirement(
                name=nombre, kind=kind, provider=provider,
                is_secret=(kind == "secret"),
                declared_default=_mask_default(nombre, d["declared_default"]),
                per_environment=bool(d["per_environment"]),
                confidence=d["confidence"],
                evidence=tuple(d["evidence"]),
                note=d["note"],
            ))
        return tuple(salida)


def extract_requirements(yaml_text: str, provider: str) -> tuple:
    """tuple[Requirement, ...]. Determinista: mismo input -> mismo output y mismo ORDEN.
    YAML invalido -> (). NUNCA levanta."""
    if provider not in PROVIDERS:
        return ()
    try:
        doc = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        return ()
    if not isinstance(doc, dict):
        return ()

    declared = _declared_variables(doc)
    params = _declared_parameters(doc)
    acc = _Acumulador()

    # (3) un Requirement `parameter` por cada entrada del bloque parameters:
    for nombre, spec in params.items():
        valores = spec.get("values") or []
        per_env = (str(nombre).lower() in _ENV_RANK) or (len(valores) >= 2) or any(
            str(v).lower() in _ENV_RANK for v in valores)
        extracto = str(spec.get("displayName") or spec.get("default") or nombre)
        acc.add(nombre, "parameter", path="parameters.%s" % nombre, excerpt=extracto,
                confidence="alta", per_environment=per_env,
                declared_default=(None if spec.get("default") is None
                                  else str(spec.get("default"))))

    var_re = _ADO_VAR_RE if provider == PROVIDER_ADO else _GL_VAR_RE

    for path, key, value in _iter_nodes(doc):
        # `tags:` de GitLab -> runner (server)
        if provider == PROVIDER_GITLAB and key == "tags" and isinstance(value, list):
            for i, t in enumerate(value):
                if isinstance(t, str) and t.strip():
                    acc.add(t, "server", path="%s[%d]" % (path, i), excerpt=t,
                            confidence="alta", per_environment=True)
            continue
        if not isinstance(value, str):
            continue
        s = value

        # service connections de ADO
        if provider == PROVIDER_ADO and key in _ADO_SERVICE_CONNECTION_KEYS:
            acc.add(s, "service_connection", path=path, excerpt=s, confidence="alta",
                    per_environment=True)
            continue

        # pool -> servidor
        if key == "name" and (path.endswith(".pool.name") or path == "pool.name"):
            nombre_param, default_param = _resolve_parameter_expr(s, params)
            if nombre_param is not None:
                if default_param:
                    acc.add(default_param, "server", path=path, excerpt=s,
                            confidence="alta", per_environment=True,
                            note=("pool tomado del default del parámetro `%s`; si al "
                                  "encolar elegís otro, este chequeo no aplica"
                                  % nombre_param))
                    acc.add(default_param, "server",
                            path="parameters.%s" % nombre_param, excerpt=default_param,
                            confidence="alta", per_environment=True)
            else:
                acc.add(s, "server", path=path, excerpt=s, confidence="alta",
                        per_environment=True)
            continue

        # rutas: (a) el string ENTERO; (b) SOLO si (a) no matcheo, embebidas
        if _ABS_PATH_FULL_RE.match(s) and "$(" not in s and "${{" not in s:
            acc.add(s, "deploy_path", path=path, excerpt=s, per_environment=True,
                    confidence=("alta" if key in _PATH_INPUT_KEYS else "baja"))
        else:
            for hit in _ABS_PATH_EMBEDDED_RE.findall(s):
                acc.add(hit, "deploy_path", path=path, excerpt=s, per_environment=True,
                        confidence="baja")

        # variables / secretos
        for m in var_re.finditer(s):
            nombre = m.group("n")
            if provider == PROVIDER_ADO and is_ado_predefined(nombre):
                continue
            if provider == PROVIDER_GITLAB and nombre.startswith("CI_"):
                continue
            en_shell = key in _SHELL_KEYS
            conocido = (nombre in declared) or (nombre in params)
            confianza = "baja" if (en_shell and not conocido) else "alta"
            kind = "secret" if looks_secret(nombre) else "variable"
            acc.add(nombre, kind, path=path, excerpt=s, confidence=confianza,
                    declared_default=(declared.get(nombre) if nombre in declared else None))

    return acc.build(provider)


# ── F2 — entornos derivados y matriz ────────────────────────────────────────

def _env_sort_key(nombre: str) -> tuple:
    return (_ENV_RANK.get(nombre.strip().lower(), 99), nombre.strip().lower())


def derive_environments(yaml_text: str, provider: str,
                        provider_scopes: tuple = ()) -> tuple:
    """tuple[str, ...] DERIVADOS. NUNCA una lista hardcodeada.
    Union vacía -> ("(único)",). Nunca fabrica Dev/QA/Prod."""
    try:
        doc = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        doc = None
    vistos: dict = {}

    def _agregar(nombre) -> None:
        s = str(nombre or "").strip()
        if not s or s.startswith("${{") or s.startswith("$("):
            return
        vistos.setdefault(s.lower(), s)

    if isinstance(doc, dict):
        params = _declared_parameters(doc)
        for _path, key, value in _iter_nodes(doc):
            if key != "environment":
                continue
            crudo = value
            if isinstance(crudo, dict):
                crudo = crudo.get("name")
            if not isinstance(crudo, str):
                continue
            nombre_param, default_param = _resolve_parameter_expr(crudo, params)
            if nombre_param is not None:
                valores = (params.get(nombre_param) or {}).get("values") or []
                if valores:
                    for v in valores:
                        _agregar(v)
                elif default_param:
                    _agregar(default_param)
                continue
            _agregar(crudo)

    for scope in provider_scopes or ():
        if str(scope) != "*":
            _agregar(scope)

    if not vistos:
        return (ENV_UNICO,)
    return tuple(sorted(vistos.values(), key=_env_sort_key))


def pending_fingerprint(cells: tuple) -> str:
    """sha256 (16 hex) de las celdas que representan trabajo pendiente. PURA."""
    canon = sorted("%s|%s|%s" % (c.state, c.requirement, c.environment)
                   for c in cells if c.state in ("falta", "manual"))
    return hashlib.sha256("\n".join(canon).encode("utf-8")).hexdigest()[:16]


def _nota_por_kind(req: Requirement) -> tuple:
    """(state_default, note_default) para un par sin entrada en `resolutions`."""
    if req.kind == "service_connection":
        return "manual", _NOTA_SERVICE_CONNECTION
    if req.kind == "deploy_path" and req.confidence == "baja":
        return "manual", _NOTA_RUTA_MANUAL
    if req.confidence == "baja":
        return "manual", _NOTA_CONFIANZA_BAJA
    return "falta", None


def build_matrix(requirements: tuple, environments: tuple, resolutions: dict,
                 provider: str, degraded: tuple = ()) -> EnvMatrix:
    """PURA. `resolutions` = {(name, env): (state, source, note)}; es INTERNO y nunca
    se serializa: la frontera JSON es EnvMatrix (C3)."""
    requirements = tuple(requirements or ())
    environments = tuple(environments or (ENV_UNICO,))
    resolutions = dict(resolutions or {})
    celdas: list = []
    ado_multi = (provider == PROVIDER_ADO and len(environments) > 1)

    for req in requirements:
        nota_req = req.note
        for env in environments:
            entrada = resolutions.get((req.name, env))
            if entrada is not None:
                state, source, note = entrada
            else:
                state, note = _nota_por_kind(req)
                source = "ninguna"
            partes = [p for p in (note, nota_req) if p]
            if ado_multi and state == "definido" and source == "caja_fuerte":
                partes.append(_NOTA_ADO_SIN_SCOPING)
            if not req.per_environment:
                partes.append(_NOTA_MISMO_VALOR.strip())
            celdas.append(Cell(requirement=req.name, environment=env, state=state,
                               source=source, note=("; ".join(partes) or None)))

    celdas_t = tuple(celdas)
    return EnvMatrix(
        environments=environments,
        requirements=requirements,
        cells=celdas_t,
        pending_count=sum(1 for c in celdas_t if c.state == "falta"),
        pending_fingerprint=pending_fingerprint(celdas_t),
        degraded=tuple(degraded or ()),
    )


def to_json_payload(m: EnvMatrix, provider: str) -> dict:
    """UNICA frontera de serializacion. PURA. `json.dumps()` sobre el retorno NUNCA
    levanta: todo es dict/lista/str/int nativo, sin claves tupla ni byte NUL."""
    return {
        "environments": list(m.environments),
        "requirements": [
            {
                "name": r.name, "kind": r.kind, "provider": r.provider,
                "is_secret": r.is_secret, "declared_default": r.declared_default,
                "per_environment": r.per_environment, "confidence": r.confidence,
                "note": r.note or None,
                "evidence": [asdict(e) for e in r.evidence],
            } for r in m.requirements
        ],
        "cells": [asdict(c) for c in m.cells],
        "pending_count": m.pending_count,
        "pending_fingerprint": m.pending_fingerprint,
        "degraded": list(m.degraded),
        "provider": provider,
        "version": ENV_MATRIX_VERSION,
    }
