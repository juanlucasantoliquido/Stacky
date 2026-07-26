"""
FlowConfig Store — Feature #4
=================================
Encapsula la lectura y escritura de ``data/flow_config.json``.

Contratos de datos
------------------
Archivo en disco::

    {
      "version": "1.0",
      "updated_at": "<iso>",
      "rules": [
        {
          "id": "<uuid4>",
          "ado_state": "New",
          "agent_type": "business",
          "created_at": "<iso>",
          "updated_at": "<iso>"
        }
      ]
    }

Regla: la clave de mapping es ``agent_type`` (DO-4.1).

Errores elevados
----------------
- ``DuplicateStateError`` → 409 en el blueprint.
- ``RuleNotFoundError``   → 404 en el blueprint.
- ``ValidationError``     → 400 en el blueprint.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_manager import PROJECTS_DIR, get_active_project, get_project_config

_log = logging.getLogger("stacky_agents.flow_config_store")

# Path relativo al directorio de trabajo (backend/), igual que preferences.py
_DEFAULT_CONFIG_FILE = Path("data/flow_config.json")
_CONFIG_FILE = _DEFAULT_CONFIG_FILE

# Tipos de agente válidos — sincronizados con DEFAULT_NEXT en next_agent.py
VALID_AGENT_TYPES: frozenset[str] = frozenset(
    {"business", "functional", "technical", "developer", "qa"}
)

# Reglas semilla cuando `data/flow_config.json` no existe (DO-4.4).
# El archivo runtime queda fuera de git (data/ está en .gitignore); las defaults
# viajan en el código como cualquier otra configuración inicial del backend.
_DEFAULT_RULES_SEED: tuple[tuple[str, str], ...] = (
    ("New", "business"),
    ("Active", "developer"),
    ("Code Review", "qa"),
    ("Resolved", "qa"),
)


# ── Excepciones de dominio ─────────────────────────────────────────────────


class DuplicateStateError(Exception):
    def __init__(self, ado_state: str) -> None:
        self.ado_state = ado_state
        super().__init__(f"Ya existe una regla para el estado '{ado_state}'.")


class RuleNotFoundError(Exception):
    def __init__(self, rule_id: str) -> None:
        self.rule_id = rule_id
        super().__init__(f"Regla '{rule_id}' no encontrada.")


class ValidationError(Exception):
    pass


# ── Helpers internos ───────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_project_name(project_name: str | None) -> str | None:
    raw = (project_name or "").strip()
    return raw.upper() if raw else None


def _config_file_for(project_name: str | None = None) -> Path:
    if _CONFIG_FILE != _DEFAULT_CONFIG_FILE:
        return _CONFIG_FILE

    normalized = _normalize_project_name(project_name)
    if normalized and get_project_config(normalized):
        return PROJECTS_DIR / normalized / "flow_config.json"

    active = _normalize_project_name(get_active_project())
    if active and get_project_config(active):
        return PROJECTS_DIR / active / "flow_config.json"

    return _CONFIG_FILE


def _legacy_fallback_file_for(config_file: Path) -> Path | None:
    """Retorna el archivo global legacy si aplica como fallback de lectura."""
    if config_file == _DEFAULT_CONFIG_FILE:
        return None
    if not _DEFAULT_CONFIG_FILE.exists():
        return None
    return _DEFAULT_CONFIG_FILE


def _empty_config() -> dict:
    return {"version": "1.0", "updated_at": _now_iso(), "rules": []}


def _read_json_file(config_file: Path) -> dict:
    text = config_file.read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict) or "rules" not in data:
        raise ValueError("formato inesperado — falta campo 'rules'")
    return data


# ── Plan 216 — fuente única en client_profile.state_flow ─────────────────────

# Snapshot del default al importar. Cualquier test que parchee `_CONFIG_FILE` o
# `_DEFAULT_CONFIG_FILE` queda FUERA del camino centralizado: el override de tests
# tiene prioridad absoluta y así ninguna suite puede escribir en el perfil real.
_PRISTINE_CONFIG_FILE = _DEFAULT_CONFIG_FILE


def _paths_are_pristine() -> bool:
    return (_CONFIG_FILE == _DEFAULT_CONFIG_FILE == _PRISTINE_CONFIG_FILE)


def state_flow_centralized_enabled() -> bool:
    # INSTANCIA config.config: el módulo devolvería el default y mataría el OFF.
    try:
        from config import config as _cfg

        return bool(getattr(_cfg, "STACKY_STATE_CONFIG_CENTRALIZED_ENABLED", False))
    except Exception:  # noqa: BLE001
        return False


def _resolve_project(project_name: str | None) -> str | None:
    """Proyecto efectivo, o None ⇒ path legacy global (aunque la flag esté ON)."""
    normalized = _normalize_project_name(project_name)
    if normalized and get_project_config(normalized):
        return normalized
    active = _normalize_project_name(get_active_project())
    if active and get_project_config(active):
        return active
    return None


def _read_state_flow_from_profile(project_name: str) -> dict | None:
    try:
        from services.client_profile import load_client_profile

        profile = load_client_profile(project_name) or {}
        sf = profile.get("state_flow")
        if isinstance(sf, dict) and isinstance(sf.get("rules"), list):
            return sf
    except Exception:  # noqa: BLE001
        _log.debug("no se pudo leer state_flow del perfil", exc_info=True)
    return None


def _write_state_flow_to_profile(project_name: str, data: dict) -> None:
    from services.client_profile import set_client_profile_state_flow

    data["updated_at"] = _now_iso()
    set_client_profile_state_flow(project_name, data)


def _sanitize_rules(data: dict) -> dict:
    """Deja SOLO reglas válidas. Un legacy editado a mano no puede romper la
    migración ni la validación del perfil. Nunca lanza."""
    rules = (data or {}).get("rules")
    limpias: list = []
    vistos: set = set()
    for rule in rules if isinstance(rules, list) else []:
        if not isinstance(rule, dict):
            _log.warning("flow_config: regla descartada (no es un objeto)")
            continue
        ado_state = rule.get("ado_state")
        if not isinstance(ado_state, str) or not ado_state.strip():
            _log.warning("flow_config: regla descartada (ado_state vacío)")
            continue
        if rule.get("agent_type") not in VALID_AGENT_TYPES:
            _log.warning("flow_config: regla descartada (agent_type %r inválido)",
                         rule.get("agent_type"))
            continue
        clave = ado_state.strip().lower()
        if clave in vistos:
            _log.warning("flow_config: regla duplicada descartada (%s)", ado_state)
            continue
        vistos.add(clave)
        limpias.append(rule)
    return {"version": (data or {}).get("version") or "1.0",
            "updated_at": (data or {}).get("updated_at") or _now_iso(),
            "rules": limpias}


def _read_legacy_raw(project_name: str | None) -> dict:
    """Lectura legacy pura (archivo), sin pasar por el perfil."""
    config_file = _config_file_for(project_name)
    return _read_raw_from_file(config_file)


def _has_legacy_file(project_name: str | None) -> bool:
    config_file = _config_file_for(project_name)
    return config_file.exists() or _legacy_fallback_file_for(config_file) is not None


def _should_use_profile(project_name: str) -> bool:
    """El perfil es la fuente solo si YA tiene `state_flow`, o si el proyecto YA
    tiene un perfil al que migrar.

    Nunca se crea un perfil de la nada: si el proyecto no tiene ninguno, la UI diría
    "perfil configurado" sin que el operador haya configurado nada. Esos proyectos
    siguen por el camino legacy y migran solo, sin perder nada, en cuanto el operador
    cree su perfil.
    """
    if _read_state_flow_from_profile(project_name) is not None:
        return True
    try:
        from services.client_profile import has_client_profile

        return bool(has_client_profile(project_name))
    except Exception:  # noqa: BLE001
        return False


def migrate_legacy_flow_config(project_name: str) -> dict:
    """Copia el JSON legacy al perfil la primera vez. Idempotente y NO destructiva:
    el archivo legacy no se borra ni se renombra, y si el perfil no se puede
    escribir se devuelve el legacy saneado (se reintenta en el próximo acceso)."""
    existente = _read_state_flow_from_profile(project_name)
    if existente is not None:
        return existente

    saneado = _sanitize_rules(_read_legacy_raw(project_name))
    try:
        _write_state_flow_to_profile(project_name, saneado)
        _log.info("flow_config migrado a client_profile.state_flow (%d reglas)",
                  len(saneado["rules"]))
    except Exception as exc:  # noqa: BLE001 — la LECTURA nunca puede romper
        _log.warning("no se pudo migrar flow_config al perfil (%s); se usa el legacy",
                     type(exc).__name__)
    return saneado


def _read_raw_from_file(config_file: Path) -> dict:
    """Cuerpo legacy de lectura por archivo (con fallback global)."""
    try:
        return _read_json_file(config_file)
    except FileNotFoundError:
        legacy_file = _legacy_fallback_file_for(config_file)
        if legacy_file is not None:
            try:
                data = _read_json_file(legacy_file)
                _log.info(
                    "flow_config.json no encontrado en %s — usando fallback legacy %s",
                    config_file, legacy_file,
                )
                return data
            except FileNotFoundError:
                pass
            except (json.JSONDecodeError, ValueError) as exc:
                _log.warning(
                    "flow_config legacy inválido en %s (%s) — iniciando con reglas vacías",
                    legacy_file, exc,
                )
                return _empty_config()
        _log.warning("flow_config.json no encontrado en %s — iniciando con reglas vacías",
                     config_file)
        return _empty_config()
    except (json.JSONDecodeError, ValueError) as exc:
        _log.warning("flow_config.json inválido en %s (%s) — iniciando con reglas vacías",
                     config_file, exc)
        return _empty_config()


def _read_raw(project_name: str | None = None) -> dict:
    """Lee el archivo JSON. Ante cualquier error devuelve estructura vacía y loguea."""
    # Plan 216 — con la flag ON y proyecto resuelto, la fuente es el perfil.
    # El override de tests (_CONFIG_FILE) conserva prioridad ABSOLUTA.
    if _paths_are_pristine() and state_flow_centralized_enabled():
        proyecto = _resolve_project(project_name)
        if proyecto and _should_use_profile(proyecto):
            return migrate_legacy_flow_config(proyecto)

    config_file = _config_file_for(project_name)
    try:
        return _read_json_file(config_file)
    except FileNotFoundError:
        legacy_file = _legacy_fallback_file_for(config_file)
        if legacy_file is not None:
            try:
                data = _read_json_file(legacy_file)
                _log.info(
                    "flow_config.json no encontrado en %s — usando fallback legacy %s",
                    config_file,
                    legacy_file,
                )
                return data
            except FileNotFoundError:
                pass
            except (json.JSONDecodeError, ValueError) as exc:
                _log.warning(
                    "flow_config legacy inválido en %s (%s) — iniciando con reglas vacías",
                    legacy_file,
                    exc,
                )
                return _empty_config()
        _log.warning("flow_config.json no encontrado en %s — iniciando con reglas vacías", config_file)
        return _empty_config()
    except (json.JSONDecodeError, ValueError) as exc:
        _log.warning("flow_config.json inválido en %s (%s) — iniciando con reglas vacías", config_file, exc)
        return _empty_config()


def _write_legacy_file(data: dict, project_name: str | None = None) -> None:
    config_file = _config_file_for(project_name)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _now_iso()
    config_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _write(data: dict, project_name: str | None = None) -> None:
    # Plan 216 — con la flag ON el perfil manda; además se espeja el archivo
    # legacy best-effort para que apagar la flag no pierda las ediciones.
    if _paths_are_pristine() and state_flow_centralized_enabled():
        proyecto = _resolve_project(project_name)
        if proyecto and _should_use_profile(proyecto):
            _write_state_flow_to_profile(proyecto, data)
            try:
                _write_legacy_file(dict(data), project_name)
            except Exception:  # noqa: BLE001 — el espejo jamás rompe el guardado
                _log.debug("mirror legacy falló (best-effort)", exc_info=True)
            return
    _write_legacy_file(data, project_name)


def _validate_fields(ado_state: Any, agent_type: Any, on_failure_state: Any | None = None) -> None:
    """Lanza ValidationError si algún campo es inválido."""
    if not ado_state or not isinstance(ado_state, str) or not ado_state.strip():
        raise ValidationError("ado_state es requerido y debe ser un string no vacío.")
    if not agent_type or not isinstance(agent_type, str) or not agent_type.strip():
        raise ValidationError("agent_type es requerido y debe ser un string no vacío.")
    if agent_type not in VALID_AGENT_TYPES:
        raise ValidationError(
            f"agent_type '{agent_type}' no válido. "
            f"Valores permitidos: {sorted(VALID_AGENT_TYPES)}."
        )
    if on_failure_state is not None and not isinstance(on_failure_state, str):
        raise ValidationError("on_failure_state debe ser string o null.")


# ── API pública ────────────────────────────────────────────────────────────


def list_rules(project_name: str | None = None) -> list[dict]:
    """Devuelve todas las reglas como lista de dicts."""
    return _read_raw(project_name).get("rules", [])


def get_rule(rule_id: str, project_name: str | None = None) -> dict | None:
    """Devuelve una regla por ID o None si no existe."""
    for rule in list_rules(project_name):
        if rule.get("id") == rule_id:
            return rule
    return None


def create_rule(
    ado_state: str,
    agent_type: str,
    project_name: str | None = None,
    on_failure_state: str | None = None,
) -> dict:
    """
    Crea una nueva regla.

    Raises:
        ValidationError: campos inválidos.
        DuplicateStateError: ya existe una regla para ese ado_state.
    """
    _validate_fields(ado_state, agent_type, on_failure_state)
    ado_state = ado_state.strip()
    agent_type = agent_type.strip()
    failure_state = (on_failure_state or "").strip() or None

    data = _read_raw(project_name)
    rules: list[dict] = data.get("rules", [])

    # Comprobar duplicado
    for r in rules:
        if r.get("ado_state") == ado_state:
            raise DuplicateStateError(ado_state)

    now = _now_iso()
    rule: dict = {
        "id": str(uuid.uuid4()),
        "ado_state": ado_state,
        "agent_type": agent_type,
        "on_failure_state": failure_state,
        "created_at": now,
        "updated_at": now,
    }
    rules.append(rule)
    data["rules"] = rules
    _write(data, project_name)
    return rule


def update_rule(
    rule_id: str,
    ado_state: str,
    agent_type: str,
    on_failure_state: str | None = None,
    project_name: str | None = None,
) -> dict:
    """
    Actualiza una regla existente.

    Raises:
        ValidationError: campos inválidos.
        RuleNotFoundError: regla no encontrada.
        DuplicateStateError: otro registro ya usa ese ado_state.
    """
    _validate_fields(ado_state, agent_type, on_failure_state)
    ado_state = ado_state.strip()
    agent_type = agent_type.strip()
    failure_state = (on_failure_state or "").strip() or None

    data = _read_raw(project_name)
    rules: list[dict] = data.get("rules", [])

    # Verificar que no haya otro con el mismo ado_state
    for r in rules:
        if r.get("ado_state") == ado_state and r.get("id") != rule_id:
            raise DuplicateStateError(ado_state)

    updated = None
    for r in rules:
        if r.get("id") == rule_id:
            r["ado_state"] = ado_state
            r["agent_type"] = agent_type
            r["on_failure_state"] = failure_state
            r["updated_at"] = _now_iso()
            updated = r
            break

    if updated is None:
        raise RuleNotFoundError(rule_id)

    data["rules"] = rules
    _write(data, project_name)
    return updated


def delete_rule(rule_id: str, project_name: str | None = None) -> None:
    """
    Elimina una regla.

    Raises:
        RuleNotFoundError: regla no encontrada.
    """
    data = _read_raw(project_name)
    rules: list[dict] = data.get("rules", [])

    original_len = len(rules)
    rules = [r for r in rules if r.get("id") != rule_id]

    if len(rules) == original_len:
        raise RuleNotFoundError(rule_id)

    data["rules"] = rules
    _write(data, project_name)


def seed_defaults_if_empty(project_name: str | None = None) -> int:
    """
    Si ``data/flow_config.json`` no existe, lo crea con las reglas semilla
    de ``_DEFAULT_RULES_SEED``. Si ya existe (con o sin reglas), no toca nada.

    Returns el número de reglas creadas (0 si ya había archivo).
    """
    # Plan 216 — con la flag ON, la migración lazy ya cubre el seed.
    if _paths_are_pristine() and state_flow_centralized_enabled():
        proyecto = _resolve_project(project_name)
        if proyecto and _should_use_profile(proyecto):
            ya_estaba = _read_state_flow_from_profile(proyecto) is not None
            migrado = migrate_legacy_flow_config(proyecto)
            return 0 if ya_estaba else len(migrado.get("rules") or [])

    config_file = _config_file_for(project_name)
    if config_file.exists():
        return 0
    legacy_file = _legacy_fallback_file_for(config_file)
    if legacy_file is not None:
        _log.info(
            "flow_config seed omitido para %s — existe fallback legacy en %s",
            config_file,
            legacy_file,
        )
        return 0
    now = _now_iso()
    rules = [
        {
            "id": str(uuid.uuid4()),
            "ado_state": ado_state,
            "agent_type": agent_type,
            "created_at": now,
            "updated_at": now,
        }
        for ado_state, agent_type in _DEFAULT_RULES_SEED
    ]
    _write({"version": "1.0", "rules": rules}, project_name)
    _log.info("flow_config seed: %d reglas iniciales escritas", len(rules))
    return len(rules)


def resolve(ado_state: str, project_name: str | None = None) -> dict:
    """
    Dado un estado ADO, retorna el agente mapeado.

    Returns::

        {
            "found": True,
            "ado_state": "Active",
            "agent_type": "developer"
        }

        o bien ``{"found": False, "ado_state": "In Review", "agent_type": None}``
    """
    for rule in list_rules(project_name):
        if rule.get("ado_state") == ado_state:
            return {
                "found": True,
                "ado_state": ado_state,
                "agent_type": rule.get("agent_type"),
                "on_failure_state": rule.get("on_failure_state"),
            }
    return {
        "found": False,
        "ado_state": ado_state,
        "agent_type": None,
        "on_failure_state": None,
    }
