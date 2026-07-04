"""publication_spec.py — Plan 88. PURO: sin I/O, sin config, sin flags.

Convierte un preset de publicación + process_catalog en un dict PipelineSpec
(el mismo shape que consume dict_to_spec, services/pipeline_spec.py:69).
NO genera texto de pipeline: eso es exclusivo de pipeline_renderers (plan 73).
Prohibido importar pipeline_renderers acá (criterio binario F6).
"""
from __future__ import annotations

import re

_KIND_ORDER = ("entry", "processing", "output")   # flujo canónico de carga
_FALLBACK_STAGE = "otros"                          # kind ausente/desconocido
_DEFAULT_TEMPLATE = 'echo "[stacky] publicar {process_name}"'
_ALLOWED_GROUPS = ("batch", "agenda")


def _slug(name: str) -> str:
    """Mismo criterio que api/pipeline_generator.py:27-31 _slug (copiado, NO
    importado, para mantener services sin dependencia de api)."""
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", (name or "").strip().lower()).strip("-")
    return s or "pipeline"


def resolve_processes(preset: dict, catalog: list) -> tuple[list, list]:
    """(procesos_resueltos_en_orden_de_catalogo, unknown_processes).

    mode='todo' -> todo el catálogo; mode='selection' -> por name (case-sensitive).
    Luego filtro groups (si no vacío, exige publish_group in groups; ausente/[] = sin filtro).
    Entradas del catálogo que no sean dict, o sin 'name' string no vacío, se ignoran
    silenciosamente (C5).
    """
    valid_entries = [
        e for e in (catalog or [])
        if isinstance(e, dict) and isinstance(e.get("name"), str) and e.get("name").strip()
    ]

    mode = preset.get("mode")
    unknown: list = []
    if mode == "selection":
        process_names = preset.get("process_names") or []
        by_name = {e["name"]: e for e in valid_entries}
        candidates = []
        for pname in process_names:
            entry = by_name.get(pname)
            if entry is not None:
                if entry not in candidates:
                    candidates.append(entry)
            else:
                unknown.append(pname)
        # Preservar orden de CATÁLOGO, no del preset.
        candidates_set = {id(c) for c in candidates}
        candidates = [e for e in valid_entries if id(e) in candidates_set]
    else:
        # mode == 'todo' (o cualquier otro valor no reconocido cae a comportamiento 'todo'
        # a nivel de resolución; la validación de mode es responsabilidad de F2).
        candidates = list(valid_entries)

    groups = preset.get("groups") or []
    if groups:
        candidates = [e for e in candidates if e.get("publish_group") in groups]

    return candidates, unknown


def _script_for(entry: dict, settings: dict | None) -> str:
    """step_templates[kind] > step_templates['default'] > _DEFAULT_TEMPLATE.
    Sustituye SOLO '{process_name}' con str.replace (NUNCA str.format)."""
    templates = {}
    if isinstance(settings, dict):
        tpls = settings.get("step_templates")
        if isinstance(tpls, dict):
            templates = tpls
    kind = entry.get("kind")
    template = templates.get(kind) or templates.get("default") or _DEFAULT_TEMPLATE
    return template.replace("{process_name}", entry.get("name", ""))


def build_publication_spec(preset: dict, catalog: list, settings: dict | None = None) -> dict:
    """Retorna {'spec': <dict PipelineSpec>, 'resolved': [names], 'unknown_processes': [names]}.

    spec['name'] = 'publicacion-' + slug(preset['name']).
    Stages: por kind en _KIND_ORDER + _FALLBACK_STAGE al final; SOLO stages no vacíos.
    Cada stage: {'name': kind, 'jobs': [...]}; un job por proceso:
      {'name': 'publicar-' + slug(name), 'steps': [{'name': 'publicar', 'script': _script_for(...)}]}.
    SOLO estas keys — cero campos nuevos en el spec (C13: test_f1_spec_shape_frozen
    del 87 v2 queda intacto).
    Sin procesos resueltos -> spec con stages=[] (inválido a propósito: _validate_spec
    lo rechaza aguas abajo; este módulo NO valida, igual que dict_to_spec)."""
    resolved, unknown = resolve_processes(preset, catalog)

    by_kind: dict = {}
    for entry in resolved:
        kind = entry.get("kind")
        stage_key = kind if kind in _KIND_ORDER else _FALLBACK_STAGE
        by_kind.setdefault(stage_key, []).append(entry)

    stages = []
    for kind in (*_KIND_ORDER, _FALLBACK_STAGE):
        entries = by_kind.get(kind)
        if not entries:
            continue
        jobs = [
            {
                "name": f"publicar-{_slug(entry['name'])}",
                "steps": [
                    {"name": "publicar", "script": _script_for(entry, settings)}
                ],
            }
            for entry in entries
        ]
        stages.append({"name": kind, "jobs": jobs})

    spec = {
        "name": f"publicacion-{_slug(preset.get('name', ''))}",
        "stages": stages,
    }

    return {
        "spec": spec,
        "resolved": [e["name"] for e in resolved],
        "unknown_processes": unknown,
    }
