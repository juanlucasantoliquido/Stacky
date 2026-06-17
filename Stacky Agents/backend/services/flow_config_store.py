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


def _read_raw(project_name: str | None = None) -> dict:
    """Lee el archivo JSON. Ante cualquier error devuelve estructura vacía y loguea."""
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


def _write(data: dict, project_name: str | None = None) -> None:
    config_file = _config_file_for(project_name)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _now_iso()
    config_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


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
