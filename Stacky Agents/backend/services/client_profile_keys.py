"""services/client_profile_keys.py — Plan 98.

Allowlist de keys parcheables del client_profile + validadores por-key EXTRAIDOS
(movidos, no reescritos) de api/client_profile.py::put_client_profile. PUROS, sin I/O.
Los mensajes de error son BYTE-IDENTICOS a los que el PUT devolvia inline.
"""
from __future__ import annotations

# Plan 88 F2 — grupos de publicación válidos (ortogonal a ALLOWED_PROCESS_KINDS).
# Duplicado intencional del mismo set en api/client_profile.py: ambos son
# constantes literales, no hay import circular entre services y api.
ALLOWED_PUBLISH_GROUPS = {"batch", "agenda"}

PATCHABLE_PROFILE_KEYS: frozenset = frozenset({
    "devops_pipeline_drafts",       # Plan 87 F2
    "devops_publication_presets",   # Plan 88 F2
    "devops_publication_settings",  # Plan 88 F2
    "devops_environment_settings",  # Plan 89 F3
})


def validate_profile_key(key: str, value) -> str | None:
    """Primer mensaje de error (str) o None si el valor es valido para esa key.
    value=None es valido para toda key (semantica 'ausente = no-op' del PUT)."""
    if value is None:
        return None
    if key == "devops_pipeline_drafts":
        return _validate_pipeline_drafts(value)
    if key == "devops_publication_presets":
        return _validate_publication_presets(value)
    if key == "devops_publication_settings":
        return _validate_publication_settings(value)
    if key == "devops_environment_settings":
        return _validate_environment_settings(value)
    return f"key '{key}' no es parcheable."


# Plan 87 F2 — validar devops_pipeline_drafts (traslado literal de
# api/client_profile.py:167-185).
def _validate_pipeline_drafts(drafts) -> str | None:
    if not isinstance(drafts, list):
        return "devops_pipeline_drafts debe ser una lista."
    if len(drafts) > 50:
        return "devops_pipeline_drafts: maximo 50 borradores."
    seen_names = set()
    for idx, d in enumerate(drafts):
        if not isinstance(d, dict) or not isinstance(d.get("name"), str) or not d.get("name").strip():
            return f"devops_pipeline_drafts[{idx}].name es obligatorio (string no vacio)."
        name = d["name"].strip()
        if len(name) > 120:
            return f"devops_pipeline_drafts[{idx}].name supera 120 caracteres."
        if name in seen_names:
            return f"devops_pipeline_drafts[{idx}].name duplicado: '{name}'."
        seen_names.add(name)
        if not isinstance(d.get("spec"), dict):
            return f"devops_pipeline_drafts[{idx}].spec debe ser un objeto."
    return None


# Plan 88 F2 — presets de publicación (traslado literal de
# api/client_profile.py:187-212).
def _validate_publication_presets(presets) -> str | None:
    if not isinstance(presets, list):
        return "devops_publication_presets debe ser una lista."
    if len(presets) > 50:
        return "devops_publication_presets: maximo 50 presets."
    seen_names = set()
    for idx, p in enumerate(presets):
        if not isinstance(p, dict) or not isinstance(p.get("name"), str) or not p.get("name").strip():
            return f"devops_publication_presets[{idx}].name es obligatorio."
        name = p["name"].strip()
        if len(name) > 120:
            return f"devops_publication_presets[{idx}].name supera 120 caracteres."
        if name in seen_names:
            return f"devops_publication_presets[{idx}].name duplicado: '{name}'."
        seen_names.add(name)
        if p.get("mode") not in ("selection", "todo"):
            return f"devops_publication_presets[{idx}].mode debe ser 'selection' o 'todo'."
        if p.get("mode") == "selection" and not isinstance(p.get("process_names"), list):
            return f"devops_publication_presets[{idx}].process_names debe ser una lista en mode=selection."
        groups = p.get("groups", [])
        if not isinstance(groups, list) or any(g not in ALLOWED_PUBLISH_GROUPS for g in groups):
            return f"devops_publication_presets[{idx}].groups: subset de {sorted(ALLOWED_PUBLISH_GROUPS)}."
        if p.get("target") not in (None, "ado", "gitlab"):
            return f"devops_publication_presets[{idx}].target debe ser 'ado' o 'gitlab'."
    return None


# Plan 88 F2 — settings de publicación (traslado literal de
# api/client_profile.py:213-224).
def _validate_publication_settings(pub_settings) -> str | None:
    if not isinstance(pub_settings, dict):
        return "devops_publication_settings debe ser un objeto."
    tpls = pub_settings.get("step_templates")
    if tpls is not None:
        if not isinstance(tpls, dict) or any(
            k not in ("entry", "processing", "output", "default") or not isinstance(v, str)
            for k, v in tpls.items()
        ):
            return "step_templates: keys en {entry,processing,output,default} y valores string."
    return None


# Plan 89 F3 — settings de ambiente (traslado literal de
# api/client_profile.py:226-247).
def _validate_environment_settings(env_settings) -> str | None:
    if not isinstance(env_settings, dict):
        return "devops_environment_settings debe ser un objeto."
    root = env_settings.get("environment_root")
    if root is not None:
        from services.environment_init import validate_root
        err = validate_root(root)
        if err:
            return f"environment_root: {err}"
    layout = env_settings.get("folder_layout")
    if layout is not None:
        from services.environment_init import is_safe_segment  # público (C12)
        if not isinstance(layout, dict) or any(k not in ("entry", "processing", "output", "default") for k in layout):
            return "folder_layout: keys en {entry,processing,output,default}."
        for k, segs in layout.items():
            if not isinstance(segs, list) or any(not isinstance(s, str) or not is_safe_segment(s) for s in segs):
                return f"folder_layout.{k}: lista de rutas relativas seguras (sin '..', sin caracteres invalidos de Windows, sin nombres reservados, no absolutas)."
    pps = env_settings.get("per_process_subfolder")
    if pps is not None and not isinstance(pps, bool):
        return "per_process_subfolder debe ser booleano."
    return None
