"""
services/config_transfer.py — Exportación / importación portable de la
configuración de un proyecto de Stacky Agents.

Objetivo (plan 2026-05-27):
  - Evitar reconfiguración manual tras upgrades / nuevos despliegues.
  - Portar la configuración entre versiones de forma segura.

Principios:
  - Backward compatible: el bundle lleva `schemaVersion` y hay un registro de
    migradores para subir versiones viejas a la actual sin romper nada.
  - Idempotencia: importar el mismo archivo dos veces no produce cambios la
    segunda vez (apply_import devuelve un diff vacío).
  - Trazabilidad: cada export/import deja una entrada de auditoría en
    `data/config_transfer_events.jsonl`.
  - Seguridad por defecto: los secretos (PAT / tokens / passwords) NUNCA salen
    en claro. El bundle solo lleva `secretsRef` (qué credenciales existían y qué
    campos tenían), de modo que el import pueda avisar cuáles hay que re-cargar.

Formato del bundle (schema v1):
  {
    "meta": {
      "schemaVersion": 1,
      "appVersion": "...",
      "projectId": "RSPACIFICO",
      "exportedAt": "2026-05-27T12:00:00Z",
      "checksum": "sha256:....",
      "sections": ["settings", "integrations", ...]
    },
    "settings":      { "display_name", "workspace_root", "docs_paths" },
    "integrations":  { "issue_tracker": { ... sin secretos ... } },
    "workflows":     { "agent_workflow_configs": { ... } },
    "agentProfiles": { "pinned_agents": [ ... ] },
    "uiPreferences": { ... data/preferences.json (global) ... },
    "secretsRef":    [ { "tracker_type", "auth_file", "present", "fields" } ]
  }

Formato multi-proyecto (schema v1):
  {
    "meta": {
      "schemaVersion": 1,
      "scope": "allProjects",
      "activeProject": "RSPACIFICO",
      "projectCount": 2,
      ...
    },
    "projects": [
      { bundle de proyecto v1 sin uiPreferences },
      ...
    ],
    "uiPreferences": { ... }
  }
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from runtime_paths import data_dir, projects_dir
from services.secret_masking import mask_token_values, strip_secret_keys

# ── Constantes de schema ──────────────────────────────────────────────────────

CURRENT_SCHEMA_VERSION = 1

# Orden canónico de secciones exportables.
ALL_SECTIONS: tuple[str, ...] = (
    "settings",
    "integrations",
    "workflows",
    "agentProfiles",
    "clientProfile",
    "uiPreferences",
    "secretsRef",
)

# Secciones que sólo informan (no se aplican al importar).
READONLY_SECTIONS: frozenset[str] = frozenset({"secretsRef"})

# Claves que jamás deben viajar en claro dentro de `integrations`.
_SECRET_KEYS: frozenset[str] = frozenset(
    {"pat", "token", "password", "secret", "auth_header", "api_key"}
)

_EVENTS_FILENAME = "config_transfer_events.jsonl"


# ── Plan 190 — Secciones DevOps (aditivas, opcionales; schemaVersion sigue en 1) ─

# Las secciones devops son GLOBALES (stores en data_dir) → viven en el TOP LEVEL
# del bundle all-projects (como uiPreferences), NUNCA dentro de un proyecto.
DEVOPS_SECTIONS: tuple[str, ...] = ("devopsServers", "devopsApps")


def _devops_transfer_enabled() -> bool:
    from config import config as _cfg  # import intra-función (evita ciclos en startup)
    return bool(getattr(_cfg, "STACKY_CONFIG_TRANSFER_DEVOPS_ENABLED", False))


def available_sections(scope: str = "all") -> tuple[str, ...]:
    """Catálogo efectivo de secciones exportables.

    Las secciones devops solo existen en scope "all" (bundle all-projects,
    top-level como uiPreferences) y solo con la flag ON. scope "project"
    (rutas per-proyecto) devuelve SIEMPRE ALL_SECTIONS sin devops.
    """
    if scope == "all" and _devops_transfer_enabled():
        return ALL_SECTIONS + DEVOPS_SECTIONS
    return ALL_SECTIONS


def _devops_sections_in_bundle(bundle: dict) -> list[str]:
    return [s for s in DEVOPS_SECTIONS if isinstance(bundle, dict) and s in bundle]


# ── Versión de la app ─────────────────────────────────────────────────────────

def _app_version() -> str:
    """Mejor esfuerzo para resolver la versión de la app (para auditoría)."""
    env = os.getenv("STACKY_APP_VERSION", "").strip()
    if env:
        return env
    # frontend/package.json (../frontend/package.json desde backend/)
    try:
        pkg = Path(__file__).resolve().parents[2] / "frontend" / "package.json"
        if pkg.exists():
            data = json.loads(pkg.read_text(encoding="utf-8"))
            ver = str(data.get("version") or "").strip()
            if ver:
                return f"stacky-agents@{ver}"
    except Exception:
        pass
    return "stacky-agents@unknown"


# ── Errores ─────────────────────────────────────────────────────────────────--

class ConfigTransferError(RuntimeError):
    """Error de exportación/importación de configuración."""


# ── Checksum ────────────────────────────────────────────────────────────────--

def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def compute_checksum(bundle: dict) -> str:
    """sha256 sobre el bundle SIN `meta.checksum` (canónico, keys ordenadas)."""
    clone = copy.deepcopy(bundle)
    meta = clone.get("meta")
    if isinstance(meta, dict):
        meta.pop("checksum", None)
    digest = hashlib.sha256(_canonical_json(clone).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


# ── Helpers de proyecto ───────────────────────────────────────────────────────

def _project_dir(name: str) -> Path:
    return projects_dir() / name.upper()


def _load_project_config(name: str) -> dict:
    from project_manager import get_project_config

    cfg = get_project_config(name)
    if cfg is None:
        raise ConfigTransferError(f"Proyecto '{name}' no encontrado")
    return cfg


def _load_project_config_optional(name: str) -> dict | None:
    from project_manager import get_project_config

    return get_project_config(name)


def _strip_secrets(value: Any) -> Any:
    """Devuelve una copia de `value` con cualquier clave-secreto removida."""
    if isinstance(value, dict):
        return {
            k: _strip_secrets(v)
            for k, v in value.items()
            if k.lower() not in _SECRET_KEYS
        }
    if isinstance(value, list):
        return [_strip_secrets(v) for v in value]
    return value


def _detect_secret_keys(value: Any) -> list[str]:
    """Recorre `value` buscando claves prohibidas. Devuelve los paths con secreto."""
    hits: list[str] = []

    def _walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if str(k).lower() in _SECRET_KEYS:
                    hits.append(f"{path}.{k}" if path else str(k))
                _walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(node, list):
            for i, item in enumerate(node):
                _walk(item, f"{path}[{i}]")

    _walk(value, "")
    return hits


def _scan_secrets_ref(name: str, tracker_type: str) -> list[dict]:
    """Inventario de credenciales presentes (sin valores)."""
    auth_dir = _project_dir(name) / "auth"
    refs: list[dict] = []
    if not auth_dir.exists():
        return refs
    for auth_file in sorted(auth_dir.glob("*.json")):
        fields_present: list[str] = []
        try:
            data = json.loads(auth_file.read_text(encoding="utf-8"))
            for fld in ("pat", "token", "password"):
                if data.get(fld):
                    fields_present.append(fld)
        except Exception:
            fields_present = []
        refs.append({
            "tracker_type": tracker_type,
            "auth_file": f"auth/{auth_file.name}",
            "present": bool(fields_present),
            "fields": fields_present,
        })
    return refs


def _write_project_config(name: str, cfg: dict) -> None:
    cfg_file = _project_dir(name) / "config.json"
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    cfg_file.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def _project_name_from_bundle(bundle: dict, fallback: str | None = None) -> str:
    meta = bundle.get("meta") if isinstance(bundle.get("meta"), dict) else {}
    name = str(meta.get("projectId") or fallback or "").strip()
    if not name:
        raise ConfigTransferError("El bundle no indica meta.projectId para el proyecto")
    return name.upper()


def _load_ui_preferences() -> dict:
    prefs_file = data_dir() / "preferences.json"
    try:
        if prefs_file.exists():
            data = json.loads(prefs_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


# ── Export ─────────────────────────────────────────────────────────────────--

def build_export(name: str, sections: list[str] | None = None) -> dict:
    """Construye el bundle exportable de un proyecto.

    sections: subconjunto de ALL_SECTIONS a incluir. None = todas.
    """
    cfg = _load_project_config(name)
    project_name = cfg.get("name", name.upper())
    tracker = cfg.get("issue_tracker") or {}
    tracker_type = tracker.get("type", "azure_devops")

    requested = list(sections) if sections else list(ALL_SECTIONS)
    unknown = [s for s in requested if s not in ALL_SECTIONS]
    if unknown:
        raise ConfigTransferError(f"Secciones desconocidas: {unknown}")

    bundle: dict[str, Any] = {}

    if "settings" in requested:
        bundle["settings"] = {
            "display_name": cfg.get("display_name", project_name),
            "workspace_root": cfg.get("workspace_root", ""),
            "docs_paths": cfg.get("docs_paths") or {"technical": "", "functional": ""},
        }
    if "integrations" in requested:
        bundle["integrations"] = {"issue_tracker": _strip_secrets(tracker)}
    if "workflows" in requested:
        bundle["workflows"] = {
            "agent_workflow_configs": cfg.get("agent_workflow_configs") or {}
        }
    if "agentProfiles" in requested:
        bundle["agentProfiles"] = {"pinned_agents": cfg.get("pinned_agents") or []}
    if "clientProfile" in requested:
        cp = cfg.get("client_profile")
        if isinstance(cp, dict):
            # Defensa en profundidad: rechazar exportar si el client_profile
            # local contiene claves prohibidas (el operador las metió a mano).
            hits = _detect_secret_keys(cp)
            if hits:
                raise ConfigTransferError(
                    "client_profile contiene claves prohibidas (no se permite exportar): "
                    + ", ".join(hits)
                )
            bundle["clientProfile"] = {"profile": _strip_secrets(cp)}
        else:
            bundle["clientProfile"] = {"profile": None}
    if "uiPreferences" in requested:
        bundle["uiPreferences"] = _load_ui_preferences()
    if "secretsRef" in requested:
        bundle["secretsRef"] = _scan_secrets_ref(project_name, tracker_type)

    bundle["meta"] = {
        "schemaVersion": CURRENT_SCHEMA_VERSION,
        "appVersion": _app_version(),
        "projectId": project_name,
        "exportedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "sections": [s for s in ALL_SECTIONS if s in bundle],
    }
    bundle["meta"]["checksum"] = compute_checksum(bundle)
    return bundle


def _export_devops_servers() -> dict:
    """Campos públicos del registro 91 + has_password (booleano local). CERO keyring
    reads para VALORES; has_password ya lo expone list_servers. `notes` sale con
    masking de prefijos de token (módulo común secret_masking). credentials_manifest =
    aliases que TENÍAN password al exportar (lista de aliases, JAMÁS el secreto)."""
    from services import server_registry

    servers = server_registry.list_servers()  # ya viene SIN password y CON has_password
    for s in servers:
        s["notes"] = mask_token_values(s.get("notes") or "")
    manifest = [s["alias"] for s in servers if s.get("has_password")]
    return {"servers": servers, "credentials_manifest": manifest}


def _export_devops_apps() -> dict:
    """Apps del Centro 120 con scrub de claves secretas en targets (módulo común)."""
    from services import deploy_store

    apps = deploy_store.list_apps()
    return {"apps": strip_secret_keys(apps)}


def build_all_projects_export(sections: list[str] | None = None) -> dict:
    """Construye un bundle portable con todos los proyectos configurados.

    El archivo resultante permite levantar Stacky Agents desde cero: crea los
    proyectos que falten y aplica settings, integraciones, workflows, agentes
    fijados y perfiles de cliente. Los secretos siguen viajando sólo como
    referencias. Plan 190: si la flag está ON, incluye también las secciones
    devops (servidores sin contraseñas + apps de despliegue) como top-level.
    """
    from project_manager import get_active_project, get_all_projects

    catalog = available_sections("all")
    requested = list(sections) if sections else list(catalog)
    unknown = [s for s in requested if s not in catalog]
    if unknown:
        raise ConfigTransferError(f"Secciones desconocidas: {unknown}")

    # Secciones de proyecto (per-proyecto). uiPreferences y las devops son top-level.
    project_sections = [s for s in requested if s in ALL_SECTIONS and s != "uiPreferences"]
    bundle: dict[str, Any] = {}

    if project_sections:
        projects: list[dict] = []
        for cfg in get_all_projects():
            name = str(cfg.get("name") or "").strip()
            if not name:
                continue
            projects.append(build_export(name, sections=project_sections))
        bundle["projects"] = projects

    if "uiPreferences" in requested:
        bundle["uiPreferences"] = _load_ui_preferences()
    # Plan 190 — secciones devops (solo con flag ON; available_sections ya la respeta).
    if "devopsServers" in requested and _devops_transfer_enabled():
        bundle["devopsServers"] = _export_devops_servers()
    if "devopsApps" in requested and _devops_transfer_enabled():
        bundle["devopsApps"] = _export_devops_apps()

    top_sections = [
        s for s in ("projects", "uiPreferences", "devopsServers", "devopsApps")
        if s in bundle
    ]

    bundle["meta"] = {
        "schemaVersion": CURRENT_SCHEMA_VERSION,
        "appVersion": _app_version(),
        "scope": "allProjects",
        "activeProject": get_active_project(),
        "projectCount": len(bundle.get("projects") or []),
        "exportedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "sections": top_sections,
    }
    bundle["meta"]["checksum"] = compute_checksum(bundle)
    return bundle


# ── Migradores de schema ──────────────────────────────────────────────────────

# Registro versión_origen -> función que sube el bundle a versión_origen + 1.
# Hoy v1 es la única versión; el andamiaje queda listo para v2+.
_MIGRATORS: dict[int, Callable[[dict], dict]] = {}


def _migrate_bundle(bundle: dict, from_version: int) -> tuple[dict, list[str]]:
    """Aplica migradores secuenciales hasta CURRENT_SCHEMA_VERSION."""
    notes: list[str] = []
    current = copy.deepcopy(bundle)
    ver = from_version
    while ver < CURRENT_SCHEMA_VERSION:
        migrator = _MIGRATORS.get(ver)
        if migrator is None:
            raise ConfigTransferError(
                f"No hay migrador de schema v{ver} → v{ver + 1}"
            )
        current = migrator(current)
        notes.append(f"migrado schema v{ver} → v{ver + 1}")
        ver += 1
    if current.get("meta", {}).get("schemaVersion") != CURRENT_SCHEMA_VERSION:
        current.setdefault("meta", {})["schemaVersion"] = CURRENT_SCHEMA_VERSION
    return current, notes


# ── Validación ─────────────────────────────────────────────────────────────--

@dataclass
class ValidationResult:
    ok: bool
    schema_version: int | None = None
    app_version: str | None = None
    project_id: str | None = None
    checksum_ok: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    migration_notes: list[str] = field(default_factory=list)
    normalized_bundle: dict | None = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "app_version": self.app_version,
            "project_id": self.project_id,
            "checksum_ok": self.checksum_ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "migration_notes": self.migration_notes,
        }


def validate_import(bundle: Any) -> ValidationResult:
    """Valida estructura, versión y checksum. Devuelve el bundle normalizado
    (migrado a la versión actual) si es compatible."""
    if not isinstance(bundle, dict):
        return ValidationResult(ok=False, errors=["El archivo no es un objeto JSON válido."])

    meta = bundle.get("meta")
    if not isinstance(meta, dict):
        return ValidationResult(ok=False, errors=["Falta la sección 'meta'."])

    schema_version = meta.get("schemaVersion")
    app_version = meta.get("appVersion")
    project_id = meta.get("projectId")
    result = ValidationResult(
        ok=True,
        schema_version=schema_version if isinstance(schema_version, int) else None,
        app_version=str(app_version) if app_version else None,
        project_id=str(project_id) if project_id else None,
    )

    if not isinstance(schema_version, int):
        result.ok = False
        result.errors.append("meta.schemaVersion ausente o no numérico.")
        return result

    if schema_version > CURRENT_SCHEMA_VERSION:
        result.ok = False
        result.errors.append(
            f"Schema v{schema_version} es más nuevo que el soportado "
            f"(v{CURRENT_SCHEMA_VERSION}). Actualizá Stacky Agents para importar."
        )
        return result

    # Integridad: el checksum es opcional pero si está debe coincidir.
    expected = meta.get("checksum")
    if expected:
        actual = compute_checksum(bundle)
        result.checksum_ok = (actual == expected)
        if not result.checksum_ok:
            result.ok = False
            result.errors.append(
                "Checksum inválido: el archivo está corrupto o fue modificado."
            )
            return result
    else:
        result.warnings.append("El bundle no trae checksum; no se verificó integridad.")

    is_all_projects = meta.get("scope") == "allProjects" or "projects" in bundle
    if is_all_projects and not isinstance(bundle.get("projects"), list):
        result.ok = False
        result.errors.append("El bundle multi-proyecto debe traer 'projects' como lista.")
        return result

    # Que al menos haya una sección aplicable.
    applicable = [s for s in ALL_SECTIONS if s in bundle and s not in READONLY_SECTIONS]
    if not applicable and not is_all_projects:
        result.warnings.append("El bundle no contiene secciones aplicables.")

    try:
        normalized, notes = _migrate_bundle(bundle, schema_version)
    except ConfigTransferError as exc:
        result.ok = False
        result.errors.append(str(exc))
        return result

    result.migration_notes = notes
    result.normalized_bundle = normalized
    return result


# ── Diff / apply ───────────────────────────────────────────────────────────--

def _diff_settings(current: dict, incoming: dict, *, overwrite: bool) -> list[dict]:
    changes: list[dict] = []
    for key in ("display_name", "workspace_root", "docs_paths"):
        if key not in incoming:
            continue
        new_val = incoming.get(key)
        old_val = current.get(key)
        # En merge no pisamos un valor existente con uno vacío.
        if not overwrite and new_val in (None, "", {}):
            continue
        if new_val == old_val:
            continue
        changes.append({
            "section": "settings", "field": key,
            "action": "update" if old_val not in (None, "", {}) else "add",
            "old": old_val, "new": new_val,
        })
    return changes


def _diff_dict_section(
    section: str, sub_key: str, current_map: dict, incoming_map: dict, *, overwrite: bool
) -> list[dict]:
    changes: list[dict] = []
    keys = set(current_map) | set(incoming_map)
    for k in sorted(keys):
        in_new = k in incoming_map
        in_old = k in current_map
        if not in_new:
            if overwrite and in_old:
                changes.append({"section": section, "field": f"{sub_key}.{k}",
                                 "action": "remove", "old": current_map[k], "new": None})
            continue
        new_val = incoming_map[k]
        old_val = current_map.get(k)
        if in_old and old_val == new_val:
            continue
        changes.append({"section": section, "field": f"{sub_key}.{k}",
                        "action": "update" if in_old else "add",
                        "old": old_val, "new": new_val})
    return changes


def _diff_pinned(current: list, incoming: list, *, overwrite: bool) -> list[dict]:
    if overwrite:
        new_list = list(dict.fromkeys(incoming))
    else:
        new_list = list(dict.fromkeys(list(current) + list(incoming)))
    if new_list == list(current):
        return []
    return [{"section": "agentProfiles", "field": "pinned_agents",
             "action": "update", "old": list(current), "new": new_list}]


def compute_diff(name: str, bundle: dict, *, overwrite: bool) -> dict:
    """Calcula los cambios que provocaría aplicar `bundle` al proyecto `name`."""
    existing_cfg = _load_project_config_optional(name)
    cfg = existing_cfg or {"name": name.upper()}
    changes: list[dict] = []

    if existing_cfg is None:
        changes.append({
            "section": "projects",
            "field": name.upper(),
            "action": "add",
            "old": None,
            "new": "config.json",
        })

    if "settings" in bundle:
        changes += _diff_settings(cfg, bundle["settings"], overwrite=overwrite)

    if "integrations" in bundle:
        inc_tracker = (bundle["integrations"] or {}).get("issue_tracker") or {}
        cur_tracker = _strip_secrets(cfg.get("issue_tracker") or {})
        changes += _diff_dict_section(
            "integrations", "issue_tracker", cur_tracker, inc_tracker, overwrite=overwrite
        )

    if "workflows" in bundle:
        inc_wf = (bundle["workflows"] or {}).get("agent_workflow_configs") or {}
        cur_wf = cfg.get("agent_workflow_configs") or {}
        changes += _diff_dict_section(
            "workflows", "agent_workflow_configs", cur_wf, inc_wf, overwrite=overwrite
        )

    if "agentProfiles" in bundle:
        inc_pinned = (bundle["agentProfiles"] or {}).get("pinned_agents") or []
        changes += _diff_pinned(cfg.get("pinned_agents") or [], inc_pinned, overwrite=overwrite)

    if "clientProfile" in bundle:
        inc_profile = (bundle["clientProfile"] or {}).get("profile")
        cur_profile = cfg.get("client_profile")
        if inc_profile is None:
            if overwrite and cur_profile is not None:
                changes.append({"section": "clientProfile", "field": "profile",
                                "action": "remove", "old": cur_profile, "new": None})
        else:
            # El diff debe comparar contra lo que apply_import realmente escribirá.
            # En merge eso es un shallow-merge ({**cur, **inc}); comparar el perfil
            # entrante crudo contra el actual reportaba cambios fantasma (e
            # idempotent=False) en cada re-aplicación cuando el destino tenía claves
            # top-level que el entrante no trae — el caso común ahora que todo
            # proyecto arranca con el template default sembrado.
            if not overwrite and isinstance(cur_profile, dict) and isinstance(inc_profile, dict):
                effective = {**cur_profile, **inc_profile}
            else:
                effective = inc_profile
            if effective != cur_profile:
                changes.append({"section": "clientProfile", "field": "profile",
                                "action": "update" if cur_profile is not None else "add",
                                "old": cur_profile, "new": effective})

    if "uiPreferences" in bundle:
        cur_prefs = _load_ui_preferences()
        inc_prefs = bundle["uiPreferences"] or {}
        changes += _diff_dict_section(
            "uiPreferences", "prefs", cur_prefs, inc_prefs, overwrite=overwrite
        )

    # secretsRef → informa qué credenciales faltan en el destino.
    secrets_required: list[dict] = []
    for ref in bundle.get("secretsRef") or []:
        auth_rel = ref.get("auth_file", "")
        target = _project_dir(name) / auth_rel
        if ref.get("present") and not target.exists():
            secrets_required.append({
                "tracker_type": ref.get("tracker_type"),
                "auth_file": auth_rel,
                "fields": ref.get("fields") or [],
            })

    return {"changes": changes, "secrets_required": secrets_required}


def _apply_settings(cfg: dict, incoming: dict, *, overwrite: bool) -> dict:
    out = dict(cfg)
    for key in ("display_name", "workspace_root", "docs_paths"):
        if key not in incoming:
            continue
        new_val = incoming.get(key)
        if not overwrite and new_val in (None, "", {}):
            continue
        out[key] = new_val
    return out


def apply_import(name: str, bundle: dict, *, mode: str) -> dict:
    """Aplica el bundle al proyecto `name`.

    mode: 'dry-run' | 'merge' | 'overwrite'
      - dry-run:   no persiste; sólo devuelve el diff.
      - merge:     fusiona claves; no pisa con vacío.
      - overwrite: reemplaza por sección.
    Idempotente: re-aplicar el mismo bundle deja un diff vacío.
    """
    if mode not in {"dry-run", "merge", "overwrite"}:
        raise ConfigTransferError(f"mode inválido: {mode}")

    overwrite = (mode == "overwrite")
    diff = compute_diff(name, bundle, overwrite=overwrite)

    # Plan 190 (C2) — las secciones devops son GLOBALES: la ruta per-proyecto NUNCA
    # las aplica; si el bundle las trae, se informan como saltadas.
    devops_skipped = _devops_sections_in_bundle(bundle)

    if mode == "dry-run":
        out = {
            "ok": True,
            "mode": mode,
            "applied": False,
            "changes": diff["changes"],
            "secrets_required": diff["secrets_required"],
        }
        if devops_skipped:
            out["skipped_sections"] = devops_skipped
        return out

    if not diff["changes"]:
        out = {
            "ok": True,
            "mode": mode,
            "applied": True,
            "changes": [],
            "secrets_required": diff["secrets_required"],
            "idempotent": True,
        }
        if devops_skipped:
            out["skipped_sections"] = devops_skipped
        return out

    # Importante: persistimos escribiendo config.json directamente, SIN pasar por
    # los validadores de existencia de project_manager.initialize_project
    # (validate_workspace_root / validate_docs_paths). Al importar en una máquina
    # nueva esas rutas pueden no existir todavía, y exigir su existencia
    # rompería justamente el caso de uso que el plan busca: portabilidad
    # post-deploy. El operador puede corregir rutas luego desde el modal de
    # proyecto, que sí valida.
    cfg = _load_project_config_optional(name) or {"name": name.upper()}
    new_cfg = dict(cfg)
    new_cfg["name"] = str(new_cfg.get("name") or name).upper()

    # settings
    if "settings" in bundle:
        new_cfg = _apply_settings(new_cfg, bundle["settings"], overwrite=overwrite)

    # integrations (issue_tracker) — preservar auth_file/secretos locales.
    if "integrations" in bundle:
        tracker = dict(new_cfg.get("issue_tracker") or {})
        inc_tracker = (bundle["integrations"] or {}).get("issue_tracker") or {}
        if overwrite:
            preserved = {k: tracker[k] for k in ("auth_file",) if k in tracker}
            tracker = {**inc_tracker, **preserved}
        else:
            tracker = {**tracker, **{k: v for k, v in inc_tracker.items() if v not in (None, "")}}
        new_cfg["issue_tracker"] = tracker

    # workflows
    if "workflows" in bundle:
        inc_wf = (bundle["workflows"] or {}).get("agent_workflow_configs") or {}
        if overwrite:
            new_cfg["agent_workflow_configs"] = inc_wf
        else:
            merged_wf = dict(new_cfg.get("agent_workflow_configs") or {})
            merged_wf.update(inc_wf)
            new_cfg["agent_workflow_configs"] = merged_wf

    # agentProfiles
    if "agentProfiles" in bundle:
        inc_pinned = (bundle["agentProfiles"] or {}).get("pinned_agents") or []
        cur_pinned = new_cfg.get("pinned_agents") or []
        if overwrite:
            new_cfg["pinned_agents"] = list(dict.fromkeys(inc_pinned))
        else:
            new_cfg["pinned_agents"] = list(dict.fromkeys(list(cur_pinned) + list(inc_pinned)))

    # clientProfile
    if "clientProfile" in bundle:
        inc_profile = (bundle["clientProfile"] or {}).get("profile")
        if inc_profile is None:
            if overwrite:
                new_cfg.pop("client_profile", None)
            # En merge dejamos intacto.
        else:
            # Defensa: rechazar perfiles entrantes con claves prohibidas.
            leftover = _detect_secret_keys(inc_profile)
            if leftover:
                raise ConfigTransferError(
                    "clientProfile entrante contiene claves prohibidas: " + ", ".join(leftover)
                )
            if overwrite:
                new_cfg["client_profile"] = inc_profile
            else:
                cur = new_cfg.get("client_profile")
                if isinstance(cur, dict) and isinstance(inc_profile, dict):
                    merged = dict(cur)
                    merged.update(inc_profile)
                    new_cfg["client_profile"] = merged
                else:
                    new_cfg["client_profile"] = inc_profile

    _write_project_config(name, new_cfg)

    # uiPreferences (global)
    if "uiPreferences" in bundle:
        _apply_ui_preferences(bundle["uiPreferences"] or {}, overwrite=overwrite)

    out = {
        "ok": True,
        "mode": mode,
        "applied": True,
        "changes": diff["changes"],
        "secrets_required": diff["secrets_required"],
        "idempotent": False,
    }
    if devops_skipped:
        out["skipped_sections"] = devops_skipped
    return out


def is_all_projects_bundle(bundle: dict) -> bool:
    meta = bundle.get("meta") if isinstance(bundle.get("meta"), dict) else {}
    return meta.get("scope") == "allProjects" or isinstance(bundle.get("projects"), list)


# ── Plan 190 — Import de secciones DevOps (globales, top-level) ────────────────

def _import_devops_servers(section: dict, *, mode: str) -> dict:
    """Aplica la sección devopsServers. merge/overwrite upsertean SIN tocar el
    keyring (upsert_server no lo toca); overwrite además borra los aliases locales
    AUSENTES del bundle (C1: JAMÁS un alias presente — eso destruiría su password).
    Los campos derivados (has_password/last_connected_at) NO se aplican."""
    from services import server_registry

    incoming = [s for s in (section.get("servers") or []) if isinstance(s, dict)]
    manifest = section.get("credentials_manifest") or []
    incoming_set = {s.get("alias") for s in incoming if s.get("alias")}
    local_aliases = {s.get("alias") for s in server_registry.list_servers()}
    counts = {
        "add": len([a for a in incoming_set if a not in local_aliases]),
        "update": len([a for a in incoming_set if a in local_aliases]),
        "remove_overwrite": len([a for a in local_aliases if a and a not in incoming_set]),
    }
    pending: list[str] = []
    never_set: list[str] = []
    if mode != "dry-run":
        for s in incoming:
            alias = s.get("alias")
            if not alias:
                continue
            server_registry.upsert_server(
                alias=alias,
                host=s.get("host") or "",
                domain=s.get("domain") or "",
                username=s.get("username") or "",
                notes=s.get("notes") or "",
            )
        if mode == "overwrite":
            for alias in list(local_aliases):
                if alias and alias not in incoming_set:
                    server_registry.delete_server(alias)  # semántica 91 (borra credencial)
        # credentials_pending/never_set: EN IMPORT TIME contra el keyring local real.
        for alias in sorted(a for a in incoming_set if a):
            if not server_registry.has_password(alias):
                (pending if alias in manifest else never_set).append(alias)
    return {"counts": counts, "credentials_pending": pending, "credentials_never_set": never_set}


def _import_devops_apps(section: dict, *, mode: str) -> dict:
    """Aplica la sección devopsApps. merge upsertea; overwrite además borra las apps
    locales ausentes del bundle."""
    from services import deploy_store

    incoming = [a for a in (section.get("apps") or []) if isinstance(a, dict)]
    incoming_ids = {a.get("id") for a in incoming if a.get("id")}
    local_ids = {a.get("id") for a in deploy_store.list_apps()}
    counts = {
        "add": len([i for i in incoming_ids if i not in local_ids]),
        "update": len([i for i in incoming_ids if i in local_ids]),
        "remove_overwrite": len([i for i in local_ids if i and i not in incoming_ids]),
    }
    if mode != "dry-run":
        for a in incoming:
            if not a.get("id"):
                continue
            deploy_store.upsert_app(a)
        if mode == "overwrite":
            for app_id in list(local_ids):
                if app_id and app_id not in incoming_ids:
                    deploy_store.delete_app(app_id)
    return {"counts": counts}


def _apply_devops_sections(bundle: dict, *, mode: str) -> dict:
    """Aplica ambas secciones devops presentes en el bundle. Devuelve conteos +
    checklist de re-credencialización (aliases sin password local)."""
    servers_rep = {"counts": {"add": 0, "update": 0, "remove_overwrite": 0},
                   "credentials_pending": [], "credentials_never_set": []}
    apps_rep = {"counts": {"add": 0, "update": 0, "remove_overwrite": 0}}
    if isinstance(bundle.get("devopsServers"), dict):
        servers_rep = _import_devops_servers(bundle["devopsServers"], mode=mode)
    if isinstance(bundle.get("devopsApps"), dict):
        apps_rep = _import_devops_apps(bundle["devopsApps"], mode=mode)
    return {
        "counts": {"servers": servers_rep["counts"], "apps": apps_rep["counts"]},
        "credentials_pending": servers_rep["credentials_pending"],
        "credentials_never_set": servers_rep["credentials_never_set"],
    }


def apply_all_projects_import(bundle: dict, *, mode: str) -> dict:
    """Aplica un bundle multi-proyecto.

    En dry-run no escribe nada. En merge/overwrite crea automáticamente los
    proyectos faltantes escribiendo config.json directo, igual que apply_import,
    para soportar instalaciones limpias donde workspace_root/docs todavía no
    existen en esa máquina.
    """
    if mode not in {"dry-run", "merge", "overwrite"}:
        raise ConfigTransferError(f"mode inválido: {mode}")
    if not is_all_projects_bundle(bundle):
        raise ConfigTransferError("El bundle no es multi-proyecto")

    overwrite = mode == "overwrite"
    project_results: list[dict] = []
    all_changes: list[dict] = []
    all_secrets: list[dict] = []

    for project_bundle in bundle.get("projects") or []:
        if not isinstance(project_bundle, dict):
            raise ConfigTransferError("projects contiene un elemento inválido")
        project_name = _project_name_from_bundle(project_bundle)
        if mode == "dry-run":
            result = compute_diff(project_name, project_bundle, overwrite=overwrite)
            changes = result["changes"]
            secrets_required = result["secrets_required"]
            applied = False
            idempotent = False
        else:
            result = apply_import(project_name, project_bundle, mode=mode)
            changes = result.get("changes") or []
            secrets_required = result.get("secrets_required") or []
            applied = bool(result.get("applied"))
            idempotent = bool(result.get("idempotent"))
        all_changes.extend(changes)
        all_secrets.extend(secrets_required)
        project_results.append({
            "project": project_name,
            "applied": applied,
            "idempotent": idempotent,
            "changes": changes,
            "secrets_required": secrets_required,
        })

    if "uiPreferences" in bundle:
        ui_changes = _diff_dict_section(
            "uiPreferences",
            "prefs",
            _load_ui_preferences(),
            bundle.get("uiPreferences") or {},
            overwrite=overwrite,
        )
        all_changes.extend(ui_changes)

    if mode != "dry-run" and "uiPreferences" in bundle:
        _apply_ui_preferences(bundle.get("uiPreferences") or {}, overwrite=overwrite)

    if mode != "dry-run":
        active = (bundle.get("meta") or {}).get("activeProject")
        if active and _load_project_config_optional(str(active)):
            from project_manager import set_active_project

            set_active_project(str(active).upper())

    # Plan 190 — secciones DevOps (top-level, globales). Flag OFF → se saltean.
    devops_present = _devops_sections_in_bundle(bundle)
    skipped_sections: list[str] = []
    devops_report: dict | None = None
    devops_structural_change = False
    if devops_present:
        if not _devops_transfer_enabled():
            skipped_sections = list(devops_present)
        else:
            devops_report = _apply_devops_sections(bundle, mode=mode)
            sc = devops_report["counts"]["servers"]
            ac = devops_report["counts"]["apps"]
            devops_structural_change = bool(
                sc["add"] or ac["add"]
                or (mode == "overwrite" and (sc["remove_overwrite"] or ac["remove_overwrite"]))
            )

    idempotent = mode != "dry-run" and not all_changes and not devops_structural_change
    result = {
        "ok": True,
        "mode": mode,
        "applied": mode != "dry-run",
        "changes": all_changes,
        "secrets_required": all_secrets,
        "projects": project_results,
        "idempotent": idempotent,
    }
    if skipped_sections:
        result["skipped_sections"] = skipped_sections
        record_event(
            action="import-all", project="*", result="skipped-devops",
            mode=mode, sections=skipped_sections,
        )
    if devops_report is not None:
        if mode == "dry-run":
            result["devops"] = devops_report["counts"]
        else:
            result["devops"] = {
                "credentials_pending": devops_report["credentials_pending"],
                "credentials_never_set": devops_report["credentials_never_set"],
            }
            record_event(
                action="import-all", project="*", result="applied-devops", mode=mode,
                detail={
                    "servers": devops_report["counts"]["servers"],
                    "apps": devops_report["counts"]["apps"],
                    "credentials_pending": devops_report["credentials_pending"],
                    "credentials_never_set": devops_report["credentials_never_set"],
                },
            )
    return result


def _apply_ui_preferences(incoming: dict, *, overwrite: bool) -> None:
    prefs_file = data_dir() / "preferences.json"
    current = _load_ui_preferences()
    if overwrite:
        merged = dict(incoming)
    else:
        merged = {**current, **incoming}
    prefs_file.parent.mkdir(parents=True, exist_ok=True)
    prefs_file.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Auditoría ─────────────────────────────────────────────────────────────--

def _events_path() -> Path:
    return data_dir() / _EVENTS_FILENAME


def record_event(
    *,
    action: str,
    project: str,
    result: str,
    actor: str = "operator",
    schema_version: int | None = None,
    app_version: str | None = None,
    mode: str | None = None,
    checksum: str | None = None,
    sections: list[str] | None = None,
    detail: dict | None = None,
) -> dict:
    """Anexa un evento de transferencia a data/config_transfer_events.jsonl."""
    event = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "action": action,
        "project": project,
        "result": result,
        "actor": actor,
        "schema_version": schema_version,
        "app_version": app_version,
        "mode": mode,
        "checksum": checksum,
        "sections": sections or [],
        "detail": detail or {},
    }
    path = _events_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def list_events(project: str | None = None, limit: int = 100) -> list[dict]:
    """Lee los eventos de auditoría (más recientes primero)."""
    path = _events_path()
    if not path.exists():
        return []
    events: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if project and ev.get("project", "").upper() != project.upper():
            continue
        events.append(ev)
    events.reverse()
    return events[:limit]


__all__ = [
    "ALL_SECTIONS",
    "DEVOPS_SECTIONS",
    "available_sections",
    "CURRENT_SCHEMA_VERSION",
    "ConfigTransferError",
    "ValidationResult",
    "apply_import",
    "apply_all_projects_import",
    "build_export",
    "build_all_projects_export",
    "compute_checksum",
    "compute_diff",
    "is_all_projects_bundle",
    "list_events",
    "record_event",
    "validate_import",
]
