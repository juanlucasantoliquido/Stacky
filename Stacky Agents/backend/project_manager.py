"""
project_manager.py — Gestión multi-proyecto para Stacky Agents.

Cada proyecto vive en:
  backend/projects/{NOMBRE}/
    config.json   ← configuración del cliente/proyecto (issue_tracker, workspace_root, etc.)

El formato de config.json es compatible con el de Stacky, sección issue_tracker:
  {
    "name": "RSPACIFICO",
    "display_name": "RS Pacífico",
    "workspace_root": "C:/Repos/RSPacifico",
    "issue_tracker": {
      "type": "azure_devops",       ← o "jira"
      "organization": "UbimiaPacifico",
      "project": "Strategist_Pacifico",
      "auth_file": "auth/ado_auth.json"
    }
  }
"""

from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path

from runtime_paths import data_dir, projects_dir
from services.secrets_store import set_encrypted_secret, write_json_file

BASE_DIR     = Path(__file__).resolve().parent
PROJECTS_DIR = projects_dir()
ACTIVE_FILE  = data_dir() / "active_project.json"


# ── Lectura ───────────────────────────────────────────────────────────────────

def get_all_projects() -> list[dict]:
    """Retorna todos los proyectos inicializados en projects/."""
    if not PROJECTS_DIR.exists():
        return []
    result = []
    for d in sorted(PROJECTS_DIR.iterdir()):
        cfg_file = d / "config.json"
        if d.is_dir() and cfg_file.exists():
            try:
                cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
                result.append(cfg)
            except Exception:
                pass
    return result


def get_project_config(name: str) -> dict | None:
    cfg_file = PROJECTS_DIR / name / "config.json"
    if not cfg_file.exists():
        return None
    try:
        return json.loads(cfg_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_active_project() -> str | None:
    """
    Retorna el nombre del proyecto activo.
    Si hay un solo proyecto configurado lo retorna directamente.
    Retorna None si no hay ningún proyecto.
    """
    if ACTIVE_FILE.exists():
        try:
            data = json.loads(ACTIVE_FILE.read_text(encoding="utf-8"))
            name = data.get("active", "")
            if name and (PROJECTS_DIR / name / "config.json").exists():
                return name
        except Exception:
            pass
    projects = get_all_projects()
    if projects:
        return projects[0]["name"]
    return None


def set_active_project(name: str) -> None:
    ACTIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_FILE.write_text(json.dumps({"active": name}, indent=2), encoding="utf-8")


def get_active_tracker_config() -> dict | None:
    """
    Retorna el bloque issue_tracker del proyecto activo, o None si no hay proyecto.
    """
    name = get_active_project()
    if not name:
        return None
    cfg = get_project_config(name)
    if not cfg:
        return None
    return cfg.get("issue_tracker") or None


# ── Inicialización ────────────────────────────────────────────────────────────

def initialize_project(
    name: str,
    display_name: str = "",
    workspace_root: str = "",
    issue_tracker: dict | None = None,
    docs_paths: dict | None = None,
    agents_dir: str | None = None,
) -> dict:
    """
    Crea la estructura de carpetas y el config.json para un nuevo proyecto.

    issue_tracker: bloque completo de configuración. El campo "type" puede ser
                   "azure_devops" o "jira". Ver initialize_ado_project /
                   initialize_jira_project para helpers de alto nivel.
    """
    name = name.upper()
    ws   = validate_workspace_root(workspace_root) if workspace_root else ""
    base = PROJECTS_DIR / name
    base.mkdir(parents=True, exist_ok=True)

    if issue_tracker is None:
        issue_tracker = {"type": "azure_devops"}

    # Preserve extra fields that already exist in config.json (e.g. pinned_agents)
    cfg_file = base / "config.json"
    existing: dict = {}
    if cfg_file.exists():
        try:
            existing = json.loads(cfg_file.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    if docs_paths is None:
        existing_docs = existing.get("docs_paths") if isinstance(existing.get("docs_paths"), dict) else {}
        docs = {
            "technical": str(existing_docs.get("technical") or ""),
            "functional": str(existing_docs.get("functional") or ""),
        }
    else:
        docs = validate_docs_paths(docs_paths)

    if agents_dir is None:
        agents = str(existing.get("agents_dir") or "")
    else:
        agents = validate_agents_dir(agents_dir)

    config = {
        **{k: v for k, v in existing.items() if k not in ("name", "display_name", "workspace_root", "issue_tracker", "docs_paths", "agents_dir")},
        "name":           name,
        "display_name":   display_name or name,
        "workspace_root": ws,
        "docs_paths":     docs,
        "agents_dir":     agents,
        "issue_tracker":  issue_tracker,
    }

    # Seed del client_profile en la creación: todo proyecto arranca con el
    # template default de su tracker, de modo que ningún agente quede sin perfil.
    # Idempotente: si ya existía (preservado del spread de `existing`) no se toca,
    # así una actualización/PATCH nunca pisa lo que configuró el operador.
    if "client_profile" not in config:
        from services.client_profile import get_default_client_profile

        tracker_type = (issue_tracker.get("type") or "azure_devops").strip().lower()
        config["client_profile"] = get_default_client_profile(tracker_type)

    cfg_file.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

    # Copiar docs/ al workspace si no existe
    if ws:
        ws_path = Path(ws)
        ws_docs = ws_path / "docs"
        src_docs = BASE_DIR.parent / "docs"
        if ws_path.exists() and not ws_docs.exists() and src_docs.exists():
            shutil.copytree(str(src_docs), str(ws_docs))

    return config


def validate_workspace_root(workspace_root: str) -> str:
    """Normaliza y valida que `workspace_root` exista y sea un directorio."""
    raw = (workspace_root or "").strip()
    if not raw:
        raise ValueError("workspace_root requerido")

    candidate = Path(raw).expanduser()
    if not candidate.exists():
        raise ValueError(f"workspace_root no existe: {raw}")
    if not candidate.is_dir():
        raise ValueError(f"workspace_root no es una carpeta: {raw}")

    try:
        candidate = candidate.resolve(strict=True)
    except Exception:
        candidate = candidate.absolute()
    return str(candidate).replace("\\", "/")


def validate_docs_paths(docs_paths: dict | None) -> dict:
    """
    Normaliza y valida las rutas opcionales de documentación del proyecto.

    Si technical/functional están vacías, se guardan como cadena vacía para
    mantener una forma estable de config.json y permitir fallback al autodiscovery.
    """
    raw = docs_paths or {}
    if not isinstance(raw, dict):
        raise ValueError("docs_paths debe ser un objeto")

    normalized: dict[str, str] = {}
    for key, label in (("technical", "docs_paths.technical"), ("functional", "docs_paths.functional")):
        value = str(raw.get(key) or "").strip()
        if not value:
            normalized[key] = ""
            continue

        candidate = Path(value).expanduser()
        if not candidate.exists():
            raise ValueError(f"{label} no existe: {value}")
        if not candidate.is_dir():
            raise ValueError(f"{label} no es una carpeta: {value}")
        try:
            next(candidate.iterdir(), None)
        except PermissionError:
            raise ValueError(f"{label} no es legible: {value}")
        except OSError as exc:
            raise ValueError(f"{label} no se puede leer: {value} ({exc})")

        try:
            candidate = candidate.resolve(strict=True)
        except Exception:
            candidate = candidate.absolute()
        normalized[key] = str(candidate).replace("\\", "/")

    return normalized


def validate_agents_dir(agents_dir: str | None) -> str:
    """Normaliza la carpeta opcional de agentes del proyecto.

    Vacío significa: usar la fuente canónica de Stacky Agents.
    """
    raw = (agents_dir or "").strip()
    if not raw:
        return ""

    candidate = Path(raw).expanduser()
    if not candidate.exists():
        raise ValueError(f"agents_dir no existe: {raw}")
    if not candidate.is_dir():
        raise ValueError(f"agents_dir no es una carpeta: {raw}")
    try:
        next(candidate.iterdir(), None)
    except PermissionError:
        raise ValueError(f"agents_dir no es legible: {raw}")
    except OSError as exc:
        raise ValueError(f"agents_dir no se puede leer: {raw} ({exc})")

    try:
        candidate = candidate.resolve(strict=True)
    except Exception:
        candidate = candidate.absolute()
    return str(candidate).replace("\\", "/")


def initialize_ado_project(
    name: str,
    organization: str,
    ado_project: str,
    workspace_root: str,
    display_name: str = "",
    area_path: str = "",
    wiql: str = "",
    state_mapping: dict | None = None,
    auth_file: str = "auth/ado_auth.json",
    docs_paths: dict | None = None,
    agents_dir: str | None = None,
) -> dict:
    """
    Helper de alto nivel para dar de alta un proyecto Azure DevOps.

    Ejemplo:
        initialize_ado_project(
            name="RSPACIFICO",
            organization="UbimiaPacifico",
            ado_project="Strategist_Pacifico",
            workspace_root="C:/Repos/RSPacifico",  # raíz del repo (contiene trunk/)
        )
    """
    tracker: dict = {
        "type":         "azure_devops",
        "organization": organization,
        "project":      ado_project,
        "auth_file":    auth_file,
    }
    if area_path:
        tracker["area_path"] = area_path
    if wiql:
        tracker["wiql"] = wiql
    if state_mapping:
        tracker["state_mapping"] = state_mapping

    return initialize_project(
        name=name,
        display_name=display_name or name,
        workspace_root=workspace_root,
        issue_tracker=tracker,
        docs_paths=docs_paths,
        agents_dir=agents_dir,
    )


def initialize_jira_project(
    name: str,
    url: str,
    project_key: str,
    workspace_root: str,
    display_name: str = "",
    api_version: str = "3",
    jql: str = "",
    verify_ssl: bool = True,
    auth_file: str = "auth/jira_auth.json",
    docs_paths: dict | None = None,
    agents_dir: str | None = None,
) -> dict:
    """
    Helper de alto nivel para dar de alta un proyecto Jira.

    Ejemplo (Cloud):
        initialize_jira_project(
            name="B2IMPACT",
            url="https://empresa.atlassian.net",
            project_key="B2IM",
            workspace_root="C:/Repos/B2Impact",  # raíz del repo (contiene trunk/)
        )

    Ejemplo (Server/DC):
        initialize_jira_project(
            name="MIPROYECTO",
            url="https://jira.intranet.com",
            project_key="PROJ",
            workspace_root="C:/Repos/MiRepo",  # raíz del repo (contiene trunk/)
            api_version="2",
        )
    """
    tracker: dict = {
        "type":         "jira",
        "url":          url.rstrip("/"),
        "project_key":  project_key,
        "api_version":  api_version,
        "auth_file":    auth_file,
        "verify_ssl":   verify_ssl,
    }
    if jql:
        tracker["jql"] = jql

    return initialize_project(
        name=name,
        display_name=display_name or name,
        workspace_root=workspace_root,
        issue_tracker=tracker,
        docs_paths=docs_paths,
        agents_dir=agents_dir,
    )


def get_project_pinned_agents(name: str) -> list[str]:
    """Retorna la lista de agentes fijados del proyecto."""
    cfg = get_project_config(name)
    if not cfg:
        return []
    return cfg.get("pinned_agents") or []


def set_project_pinned_agents(name: str, agents: list[str]) -> None:
    """Guarda la lista de agentes fijados en el config.json del proyecto."""
    proj_dir = PROJECTS_DIR / name.upper()
    cfg_file = proj_dir / "config.json"
    if not cfg_file.exists():
        raise FileNotFoundError(f"Proyecto '{name}' no encontrado")
    cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
    cfg["pinned_agents"] = agents
    cfg_file.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Workflow de agentes ───────────────────────────────────────────────────────

def get_agent_workflow_config(project_name: str, agent_filename: str) -> dict:
    """Retorna la config de workflow de un agente en el proyecto.

    Estructura:
      {
        "allowed_states": ["New", "Active"],
        "transition_state": "Resolved",
        "requires_prior_output": false
      }
    """
    cfg = get_project_config(project_name)
    if not cfg:
        return {}
    return (cfg.get("agent_workflow_configs") or {}).get(agent_filename) or {}


def set_agent_workflow_config(
    project_name: str, agent_filename: str, workflow: dict
) -> None:
    """Guarda la config de workflow de un agente en config.json del proyecto."""
    proj_dir = PROJECTS_DIR / project_name.upper()
    cfg_file = proj_dir / "config.json"
    if not cfg_file.exists():
        raise FileNotFoundError(f"Proyecto '{project_name}' no encontrado")
    cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
    if "agent_workflow_configs" not in cfg:
        cfg["agent_workflow_configs"] = {}
    cfg["agent_workflow_configs"][agent_filename] = workflow
    cfg_file.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def find_project_for_tracker(tracker_project: str) -> tuple[str | None, dict]:
    """Encuentra el proyecto Stacky cuyo tracker_project coincide con el dado.

    tracker_project es el valor guardado en Ticket.project (ej. "Strategist_Pacifico",
    "B2I", "mantis-3").

    Retorna (project_name, project_config) o (None, {}).
    """
    for cfg in get_all_projects():
        tracker = cfg.get("issue_tracker") or {}
        t_type = tracker.get("type", "azure_devops")
        if t_type == "jira":
            key = tracker.get("project_key") or tracker.get("project", "")
            if key == tracker_project:
                return cfg["name"], cfg
        elif t_type == "mantis":
            pid = tracker.get("project_id", "")
            if f"mantis-{pid}" == tracker_project:
                return cfg["name"], cfg
        else:  # ADO
            if tracker.get("project") == tracker_project:
                return cfg["name"], cfg
    return None, {}


# ── Credenciales ─────────────────────────────────────────────────────────────

# Firma DPAPI en base64: bytes 01 00 00 00 D0 8C 9D DF (CryptProtectData blob).
_DPAPI_B64_PREFIX = "AQAAANCMnd8"


def _normalize_ado_pat(pat: str) -> str:
    """Normaliza lo que el usuario pega a una credencial Basic canónica `base64(":"+PAT)`.

    Robusto frente a los errores de pegado que rompían el auth:
      - "Basic <token>" → se descarta el prefijo.
      - Blob DPAPI ya cifrado (pegado desre otro ado_auth.json) → se rechaza con
        mensaje claro, en vez de cifrarlo de nuevo (doble cifrado → 401).
      - Credencial Basic ya pre-encoded (base64 de "algo:token" imprimible) → se
        usa tal cual.
      - PAT crudo (incluidos los PATs largos ~84 chars que el heurístico de longitud
        confundía con pre-encoded) → se envuelve como base64(":"+PAT).

    El resultado se guarda con pat_format=dpapi_preencoded, así el lector lo envía
    tal cual sin tener que adivinar el formato.
    """
    p = (pat or "").strip()
    if not p:
        return p
    if p.lower().startswith("basic "):
        p = p[6:].strip()
    if p.startswith(_DPAPI_B64_PREFIX):
        raise ValueError(
            "El valor pegado es un PAT ya cifrado (blob DPAPI), no un PAT crudo. "
            "Pegá el Personal Access Token tal como lo entrega Azure DevOps."
        )
    # ¿Ya es una credencial Basic? base64 que decodifica a texto imprimible con ':'.
    try:
        decoded = base64.b64decode(p, validate=True)
        if b":" in decoded and all(32 <= b < 127 for b in decoded):
            return p
    except Exception:
        pass
    return base64.b64encode(f":{p}".encode("utf-8")).decode("ascii")


def write_ado_auth(name: str, pat: str) -> Path:
    """
    Escribe backend/projects/{NAME}/auth/ado_auth.json con el PAT proporcionado.

    El PAT se normaliza a una credencial Basic canónica (ver `_normalize_ado_pat`)
    y se guarda cifrado con DPAPI (ligado al usuario local de Windows) con formato
    `dpapi_preencoded`. Retorna la ruta del archivo escrito.
    """
    auth_dir = PROJECTS_DIR / name.upper() / "auth"
    auth_dir.mkdir(parents=True, exist_ok=True)
    auth_file = auth_dir / "ado_auth.json"
    normalized = _normalize_ado_pat(pat)
    payload: dict = {}
    set_encrypted_secret(payload, "pat", normalized, format_field="pat_format", preencoded=True)
    write_json_file(auth_file, payload)
    return auth_file


def write_jira_auth(name: str, url: str, user: str, token: str) -> Path:
    """
    Escribe backend/projects/{NAME}/auth/jira_auth.json con las credenciales.
    Retorna la ruta del archivo escrito.
    """
    auth_dir = PROJECTS_DIR / name.upper() / "auth"
    auth_dir.mkdir(parents=True, exist_ok=True)
    auth_file = auth_dir / "jira_auth.json"
    payload = {"url": url.rstrip("/"), "user": user}
    set_encrypted_secret(payload, "token", token, format_field="token_format")
    write_json_file(auth_file, payload)
    return auth_file


def delete_project(name: str) -> bool:
    """Elimina el directorio del proyecto. Retorna True si existía."""
    import shutil
    project_dir = PROJECTS_DIR / name.upper()
    if project_dir.exists():
        shutil.rmtree(project_dir)
        # Limpiar active si era el proyecto eliminado
        if ACTIVE_FILE.exists():
            try:
                data = json.loads(ACTIVE_FILE.read_text(encoding="utf-8"))
                if data.get("active", "").upper() == name.upper():
                    ACTIVE_FILE.unlink(missing_ok=True)
            except Exception:
                pass
        return True
    return False


# ── Mantis ────────────────────────────────────────────────────────────────────

def initialize_mantis_project(
    name: str,
    url: str,
    project_id: str,
    workspace_root: str,
    display_name: str = "",
    project_name: str = "",
    protocol: str = "rest",
    verify_ssl: bool = True,
    auth_file: str = "auth/mantis_auth.json",
    docs_paths: dict | None = None,
    agents_dir: str | None = None,
) -> dict:
    """
    Helper de alto nivel para dar de alta un proyecto Mantis BT.

    protocol: 'rest' (Token API) o 'soap' (usuario/contraseña via MantisConnect)
    """
    tracker: dict = {
        "type":       "mantis",
        "url":        url.rstrip("/"),
        "project_id": str(project_id).strip(),
        "protocol":   protocol.lower(),
        "auth_file":  auth_file,
        "verify_ssl": verify_ssl,
    }
    if project_name:
        tracker["project_name"] = project_name

    return initialize_project(
        name=name,
        display_name=display_name or name,
        workspace_root=workspace_root,
        issue_tracker=tracker,
        docs_paths=docs_paths,
        agents_dir=agents_dir,
    )


def write_mantis_auth(
    name: str,
    url: str,
    protocol: str = "rest",
    token: str = "",
    username: str = "",
    password: str = "",
    project_id: str = "",
) -> Path:
    """
    Escribe backend/projects/{NAME}/auth/mantis_auth.json.
    Para REST guarda token; para SOAP guarda username + password.
    Retorna la ruta del archivo escrito.
    """
    auth_dir = PROJECTS_DIR / name.upper() / "auth"
    auth_dir.mkdir(parents=True, exist_ok=True)
    auth_file = auth_dir / "mantis_auth.json"
    payload: dict = {"url": url.rstrip("/"), "protocol": protocol.lower()}
    if protocol.lower() == "soap":
        payload["username"] = username
        set_encrypted_secret(payload, "password", password, format_field="password_format")
    else:
        set_encrypted_secret(payload, "token", token, format_field="token_format")
    if project_id:
        payload["project_id"] = str(project_id)
    write_json_file(auth_file, payload)
    return auth_file


__all__ = [
    "PROJECTS_DIR",
    "get_all_projects",
    "get_project_config",
    "get_active_project",
    "set_active_project",
    "get_active_tracker_config",
    "initialize_project",
    "initialize_ado_project",
    "initialize_jira_project",
    "initialize_mantis_project",
    "validate_workspace_root",
    "validate_docs_paths",
    "validate_agents_dir",
    "write_ado_auth",
    "write_jira_auth",
    "write_mantis_auth",
    "delete_project",
    "get_project_pinned_agents",
    "set_project_pinned_agents",
]
