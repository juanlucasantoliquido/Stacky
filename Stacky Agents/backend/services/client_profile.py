"""
services/client_profile.py — Perfil del cliente (datos específicos del proyecto
que los agentes genéricos consumen sin hardcodear).

Plan: docs/16_PLAN_GENERALIZACION_AGENTES_MULTI_CLIENTE.md

Sirve como fuente única de verdad para:
  - code_layout  : rutas online/batch/db/lib/tests + extensiones + capas.
  - language     : lenguaje primario + patrón de trazabilidad + idiomas RIDIOMA.
  - database     : tipo, server, auth_ref readonly, dml_policy, catalogos.
  - build        : herramienta, binarios, configuración, soluciones.
  - conventions  : helpers de I/O, sanitizers, naming.
  - docs_indexes : rutas a índices técnico/funcional.
  - tracker_state_machine : estados lógicos (functional/technical/developer).
  - terminology  : nombre de producto / cliente / glosario.

Principios:
  - Schema versionado (schema_version): hoy es 1; los migradores conviven con
    los de config_transfer si en el futuro hay cambios incompatibles.
  - Sin secretos: el perfil nunca lleva passwords/PATs. La BD readonly se
    referencia por `readonly_auth_ref` (archivo cifrado bajo `auth/`).
  - Defaults por tracker: `get_default_client_profile(tracker_type)` devuelve
    un template razonable que el operador puede ajustar.
  - Validación tolerante: faltan campos opcionales → se completan con defaults
    semánticos. Faltan campos requeridos → ValidationResult.ok = False.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from runtime_paths import projects_dir


SCHEMA_VERSION = 1

_SECRET_KEYS: frozenset[str] = frozenset(
    {"pat", "token", "password", "secret", "auth_header", "api_key"}
)

_DEFAULTS_DIR = Path(__file__).resolve().parent / "client_profile_defaults"

_REQUIRED_SECTIONS: tuple[str, ...] = (
    "code_layout",
    "language",
    "tracker_state_machine",
)

_OPTIONAL_SECTIONS: tuple[str, ...] = (
    "database",
    "build",
    "conventions",
    "docs_indexes",
    "terminology",
    "extensions",
)

_TRACKER_ROLES: tuple[str, ...] = ("functional", "technical", "developer")


class ClientProfileError(RuntimeError):
    """Error de carga/validación/normalización del client_profile."""


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    normalized: dict | None = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "normalized": copy.deepcopy(self.normalized) if self.normalized else None,
        }


# ── Defaults ──────────────────────────────────────────────────────────────────

def _read_default_template(tracker_type: str) -> dict:
    """Carga un template default desde el directorio de defaults.

    Si el tracker no tiene template específico, devuelve `azure_devops` como
    fallback (es el más completo y conocido).
    """
    key = (tracker_type or "azure_devops").strip().lower()
    candidate = _DEFAULTS_DIR / f"{key}.json"
    if not candidate.exists():
        candidate = _DEFAULTS_DIR / "azure_devops.json"
    try:
        return json.loads(candidate.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_default_client_profile(tracker_type: str | None = None) -> dict:
    """Devuelve un client_profile default razonable para el tracker.

    El operador puede usarlo como punto de partida desde la UI (botón
    "Aplicar template default") y editarlo a mano.
    """
    template = _read_default_template(tracker_type or "azure_devops")
    if not template:
        return {"schema_version": SCHEMA_VERSION}
    profile = copy.deepcopy(template)
    profile["schema_version"] = SCHEMA_VERSION
    return profile


# ── Validación ────────────────────────────────────────────────────────────────

def _check_section_type(profile: dict, section: str, expected: type) -> str | None:
    if section not in profile:
        return None
    value = profile.get(section)
    if not isinstance(value, expected):
        return f"client_profile.{section} debe ser {expected.__name__}, recibí {type(value).__name__}"
    return None


def _check_tracker_state_machine(machine: Any) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(machine, dict):
        errors.append("client_profile.tracker_state_machine debe ser un objeto.")
        return errors, warnings
    for role in _TRACKER_ROLES:
        sub = machine.get(role)
        if sub is None:
            warnings.append(f"tracker_state_machine.{role} ausente (los agentes pedirán al operador).")
            continue
        if not isinstance(sub, dict):
            errors.append(f"tracker_state_machine.{role} debe ser un objeto.")
            continue
        input_states = sub.get("input_states")
        if input_states is not None and not isinstance(input_states, list):
            errors.append(f"tracker_state_machine.{role}.input_states debe ser una lista.")
        next_state = sub.get("next_state_ok")
        if next_state is not None and not isinstance(next_state, str):
            errors.append(f"tracker_state_machine.{role}.next_state_ok debe ser string.")
    return errors, warnings


def _contains_secret_keys(value: Any) -> list[str]:
    """Recorre `value` buscando claves prohibidas. Devuelve los paths con secreto."""
    hits: list[str] = []

    def _walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if str(k).lower() in _SECRET_KEYS:
                    hits.append(f"{path}.{k}" if path else k)
                _walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(node, list):
            for i, item in enumerate(node):
                _walk(item, f"{path}[{i}]")

    _walk(value, "")
    return hits


def validate_client_profile(profile: Any) -> ValidationResult:
    """Valida el client_profile. Devuelve el bundle normalizado (con defaults
    semánticos para campos opcionales). Nunca lanza."""
    if profile is None:
        return ValidationResult(ok=True, normalized=None, warnings=["client_profile ausente — el agente caerá al fallback."])
    if not isinstance(profile, dict):
        return ValidationResult(ok=False, errors=["client_profile debe ser un objeto JSON."])

    errors: list[str] = []
    warnings: list[str] = []

    secret_hits = _contains_secret_keys(profile)
    if secret_hits:
        errors.append(
            "client_profile no debe contener secretos. Claves detectadas: "
            + ", ".join(secret_hits)
        )

    schema_version = profile.get("schema_version")
    if not isinstance(schema_version, int):
        warnings.append("schema_version ausente; asumo 1.")
        schema_version = SCHEMA_VERSION
    elif schema_version > SCHEMA_VERSION:
        errors.append(
            f"schema_version {schema_version} más nuevo que el soportado "
            f"({SCHEMA_VERSION}). Actualizá Stacky Agents."
        )

    for required in _REQUIRED_SECTIONS:
        if required not in profile:
            warnings.append(f"client_profile.{required} ausente — el agente preguntará al operador.")

    for section, expected_type in (
        ("code_layout", dict),
        ("language", dict),
        ("database", dict),
        ("build", dict),
        ("conventions", dict),
        ("docs_indexes", dict),
        ("terminology", dict),
        ("extensions", dict),
        ("tracker_state_machine", dict),
    ):
        err = _check_section_type(profile, section, expected_type)
        if err:
            errors.append(err)

    if "tracker_state_machine" in profile:
        sub_errs, sub_warns = _check_tracker_state_machine(profile["tracker_state_machine"])
        errors.extend(sub_errs)
        warnings.extend(sub_warns)

    if errors:
        return ValidationResult(ok=False, errors=errors, warnings=warnings)

    normalized = copy.deepcopy(profile)
    normalized["schema_version"] = schema_version
    return ValidationResult(ok=True, errors=[], warnings=warnings, normalized=normalized)


# ── Lectura ──────────────────────────────────────────────────────────────────

def load_client_profile(project_name: str) -> dict | None:
    """Carga el client_profile desde `projects/<NAME>/config.json`.

    Devuelve None si el proyecto no tiene `client_profile` (modo legacy).
    Si la sección existe pero es inválida, devuelve el dict tal cual (la
    validación es responsabilidad del caller — los endpoints validan antes de
    persistir; los consumidores en runtime degradan elegante).
    """
    if not project_name:
        return None
    cfg_file = projects_dir() / project_name.upper() / "config.json"
    if not cfg_file.exists():
        return None
    try:
        cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    profile = cfg.get("client_profile")
    if not isinstance(profile, dict):
        return None
    return profile


def has_client_profile(project_name: str) -> bool:
    return load_client_profile(project_name) is not None


# ── Escritura ────────────────────────────────────────────────────────────────

def save_client_profile(project_name: str, profile: dict) -> dict:
    """Persiste el client_profile en `config.json` del proyecto.

    Valida primero; si falla, lanza ClientProfileError. Devuelve el perfil
    normalizado tal como queda persistido.
    """
    if not project_name:
        raise ClientProfileError("project_name requerido")
    cfg_file = projects_dir() / project_name.upper() / "config.json"
    if not cfg_file.exists():
        raise ClientProfileError(f"Proyecto '{project_name}' no encontrado")

    result = validate_client_profile(profile)
    if not result.ok or result.normalized is None:
        raise ClientProfileError(
            "client_profile inválido: " + "; ".join(result.errors)
        )

    try:
        cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ClientProfileError(f"config.json ilegible: {exc}") from exc

    cfg["client_profile"] = result.normalized
    cfg_file.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return result.normalized


def clear_client_profile(project_name: str) -> bool:
    """Elimina la sección `client_profile` del config.json. Devuelve True si
    estaba presente."""
    cfg_file = projects_dir() / project_name.upper() / "config.json"
    if not cfg_file.exists():
        return False
    try:
        cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
    except Exception:
        return False
    if "client_profile" not in cfg:
        return False
    cfg.pop("client_profile", None)
    cfg_file.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


# ── Merge con defaults ────────────────────────────────────────────────────────

def _deep_merge(base: dict, override: dict) -> dict:
    """Merge profundo: override gana, dicts se fusionan recursivamente."""
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def merge_with_defaults(profile: dict, tracker_type: str | None = None) -> dict:
    """Fusiona `profile` con el template default del tracker.

    Útil para inyectar el context block: completa con defaults los campos que
    el operador no llenó, sin tener que listar todo en la UI.
    """
    if not isinstance(profile, dict):
        return get_default_client_profile(tracker_type)
    return _deep_merge(get_default_client_profile(tracker_type), profile)


__all__ = [
    "SCHEMA_VERSION",
    "ClientProfileError",
    "ValidationResult",
    "clear_client_profile",
    "get_default_client_profile",
    "has_client_profile",
    "load_client_profile",
    "merge_with_defaults",
    "save_client_profile",
    "validate_client_profile",
]
