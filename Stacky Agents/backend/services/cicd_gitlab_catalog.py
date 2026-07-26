"""services/cicd_gitlab_catalog.py — Plan 249 F1. Los constructos de GitLab CI, como DATO.

Espejo exacto de la forma de `cicd_task_catalog.py`: dataclasses frozen + dicts por scope +
una API que NUNCA lanza. PURO: sin red, sin disco, sin LLM, sin config.

Toda extraccion es sobre el documento ya parseado por `yaml.safe_load`. NUNCA por regex sobre
el texto: un `# needs: [fantasma]` comentado no existe para este modulo (regla dura del 243 C20).
"""
from __future__ import annotations

from dataclasses import dataclass

GITLAB_CATALOG_VERSION = "249.1"

SCOPE_ROOT = "root"
SCOPE_JOB = "job"
SCOPE_BOTH = "both"


@dataclass(frozen=True)
class KeywordSpec:
    name: str                 # "needs"
    scope: str                # SCOPE_ROOT | SCOPE_JOB | SCOPE_BOTH
    value_kind: str           # "str"|"list"|"map"|"bool"|"int"|"str_or_list"|"any"
    allowed_values: tuple = ()    # enum cerrado (ej. when)
    deprecated_by: str = ""       # "rules"  -> only/except
    requires_gate: str = ""       # "when"   -> environment
    evidence: str = ""            # por que esta en el catalogo


WHEN_VALUES = ("on_success", "on_failure", "always", "manual", "delayed", "never")
IMPLICIT_STAGES = (".pre", ".post")   # existen SIN declararse en `stages:` (clave para GL001)
DEPRECATED_KEYWORDS = ("only", "except")
GATED_KEYWORDS = {"environment": "when"}
# Mismo criterio que _PROD_MARKERS (cicd_semantic_rules.py:55).
PROD_ENV_MARKERS = ("prod", "produccion", "producción")


def _root(name, kind, evidence):
    return KeywordSpec(name=name, scope=SCOPE_ROOT, value_kind=kind, evidence=evidence)


def _job(name, kind, evidence, **kw):
    return KeywordSpec(name=name, scope=SCOPE_JOB, value_kind=kind, evidence=evidence, **kw)


# ── Raiz — las 11 de pipeline_lint._GITLAB_RESERVED (el conjunto ya verificado) ──
ROOT_KEYWORDS: dict = {
    "stages": _root("stages", "list", "orden de ejecucion; fundamento de GL001 y GL002"),
    "variables": _root("variables", "map", "valores del pipeline; ya cubierto por PL010..PL014"),
    "include": _root("include", "str_or_list", "trae jobs de otro archivo; desactiva GL006"),
    "workflow": _root("workflow", "map", "reglas a nivel pipeline"),
    "default": _root("default", "map", "valores por defecto de job; satisface GL009"),
    "image": _root("image", "str_or_list", "imagen por defecto de todos los jobs"),
    "services": _root("services", "list", "contenedores auxiliares"),
    "before_script": _root("before_script", "list", "prefijo de todos los scripts"),
    "after_script": _root("after_script", "list", "sufijo de todos los scripts"),
    "cache": _root("cache", "map", "cache por defecto"),
    "pages": _root("pages", "map", "job especial de GitLab Pages"),
}

# ── Job ────────────────────────────────────────────────────────────────────────
JOB_KEYWORDS: dict = {
    "stage": _job("stage", "str", "debe pertenecer a stages union IMPLICIT_STAGES -> GL001"),
    "script": _job("script", "str_or_list", "cuerpo ejecutable del job"),
    "before_script": _job("before_script", "list", "prefijo del script del job"),
    "after_script": _job("after_script", "list", "sufijo del script del job"),
    "image": _job("image", "str_or_list", "imagen del contenedor del job -> GL009"),
    "services": _job("services", "list", "contenedores auxiliares del job"),
    "tags": _job("tags", "list", "exige un runner con esos tags -> GL007"),
    "needs": _job("needs", "str_or_list", "DAG entre jobs; orden topologico -> GL002"),
    "extends": _job("extends", "str_or_list", "debe resolver a un job oculto -> GL006"),
    "rules": _job("rules", "list", "excluyente con only/except -> GL003"),
    "only": _job("only", "any", "sintaxis legada -> GL003/GL004", deprecated_by="rules"),
    "except": _job("except", "any", "sintaxis legada -> GL003/GL004", deprecated_by="rules"),
    "when": _job("when", "str", "compuerta de environment -> GL005", allowed_values=WHEN_VALUES),
    "environment": _job("environment", "any", "ambiente de deploy -> GL005", requires_gate="when"),
    "artifacts": _job("artifacts", "map", "paths publicados -> GL008"),
    "cache": _job("cache", "map", "cache del job"),
    "variables": _job("variables", "map", "valores del job"),
    "allow_failure": _job("allow_failure", "bool",
                          "el eje 'enmascara fallos' es del plan 248; aca es solo dato"),
    "retry": _job("retry", "any", "reintentos del job"),
    "timeout": _job("timeout", "str", "limite de tiempo del job"),
    "parallel": _job("parallel", "any", "incluye parallel:matrix; no se round-trippea"),
    "dependencies": _job("dependencies", "list", "artefactos; distinto de needs"),
    "resource_group": _job("resource_group", "str", "serializa jobs por recurso"),
    "interruptible": _job("interruptible", "bool", "cancelable por un pipeline nuevo"),
    "trigger": _job("trigger", "any", "pipeline hijo; no se round-trippea"),
}

KEYWORD_CATALOG: dict = {SCOPE_ROOT: ROOT_KEYWORDS, SCOPE_JOB: JOB_KEYWORDS}


def get_keyword(name: str, scope: str):
    """KeywordSpec o None. NUNCA lanza."""
    tabla = KEYWORD_CATALOG.get(scope)
    if not tabla:
        return None
    return tabla.get(str(name))


def is_known_keyword(name: str, scope: str) -> bool:
    return get_keyword(name, scope) is not None


def is_deprecated(name: str) -> bool:
    return str(name) in DEPRECATED_KEYWORDS


def job_dicts(doc) -> dict:
    """{nombre: dict} de los jobs REALES. PURA. NUNCA lanza.

    Excluye claves de raiz y jobs ocultos (`.x`), exactamente como
    pipeline_lint._gitlab_jobs. El criterio vive UNA sola vez.
    """
    if not isinstance(doc, dict):
        return {}
    out = {}
    for key, value in doc.items():
        nombre = str(key)
        if isinstance(value, dict) and not nombre.startswith(".") and nombre not in ROOT_KEYWORDS:
            out[nombre] = value
    return out


def hidden_job_names(doc) -> tuple:
    """Templates `.x` en orden alfabetico — el universo valido de `extends` (GL006)."""
    if not isinstance(doc, dict):
        return ()
    return tuple(sorted(str(k) for k, v in doc.items()
                        if str(k).startswith(".") and isinstance(v, dict)))


def stage_index_map(doc) -> dict:
    """{nombre_de_stage: indice}. `.pre` -> -1, `.post` -> len(stages)."""
    stages = doc.get("stages") if isinstance(doc, dict) else None
    nombres = [str(s) for s in stages] if isinstance(stages, list) else []
    out = {".pre": -1}
    for idx, nombre in enumerate(nombres):
        out.setdefault(nombre, idx)
    out[".post"] = len(nombres)
    return out
