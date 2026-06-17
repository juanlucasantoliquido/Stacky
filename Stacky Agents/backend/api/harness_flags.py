"""H0.4 — Endpoint de flags del arnés.

GET  /api/harness-flags        → lista flags + valores actuales
PUT  /api/harness-flags        → actualiza, persiste al .env y hot-apply

Dueño único de los flags del arnés (cli_feature_flags.py sigue siendo el
evaluador; este endpoint es el escritor). NO agregar las keys de este panel a
_MANAGED_KEYS de global_config.py — dos endpoints no deben escribir la misma key.
"""
from __future__ import annotations

import logging
import os

from flask import Blueprint, jsonify, request

from runtime_paths import backend_root

logger = logging.getLogger(__name__)

bp = Blueprint("harness_flags", __name__)

# _ENV_PATH: permite monkeypatch en tests sin afectar global_config.
# Apunta al MISMO .env que carga config.py al arrancar (backend_root()/.env).
# En un deploy frozen eso es <dir_del_exe>/.env, NO _internal/.env. Antes esto
# usaba Path(__file__).parent.parent, que en el .exe resolvía a _internal/.env:
# el writer escribía ahí pero el loader nunca lo leía, así que los cambios de la
# UI no sobrevivían al reinicio del deploy.
_ENV_PATH = backend_root() / ".env"


def _write_env(updates: dict[str, str]) -> None:
    """Actualiza el .env sin tocar otras claves. Versión local para H0.4.

    Reutiliza la misma lógica que api.global_config._write_env pero opera sobre
    el _ENV_PATH de ESTE módulo (para que los tests puedan monkeypatchar solo este).
    """
    lines: list[str] = []
    if _ENV_PATH.exists():
        lines = _ENV_PATH.read_text(encoding="utf-8").splitlines()

    updated_keys: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key = stripped.partition("=")[0].strip()
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            updated_keys.add(key)
        else:
            new_lines.append(line)

    # Agregar keys nuevas que no estaban en el archivo
    for key, val in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={val}")

    _ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    # Actualizar os.environ en caliente
    for key, val in updates.items():
        if val:
            os.environ[key] = val
        elif key in os.environ:
            del os.environ[key]


@bp.get("/harness-flags")
def get_harness_flags():
    """Devuelve todos los flags del arnés con sus valores actuales."""
    from services.harness_flags import read_current
    from services.harness_profiles import detect_profile

    flags = read_current()
    return jsonify({
        "ok": True,
        "flags": flags,
        "active_profile": detect_profile(),  # V0.1 — "off"|"safe"|"full"|None(custom)
    })


@bp.post("/harness-flags/profile")
def post_harness_profile():
    """V0.1 — Aplica un perfil de arnés (off|safe|full) en caliente.

    Body: {"name": "full"}
    200 → {"ok": true, "applied": {flag: valor}, "active_profile": "full"}
    400 → perfil desconocido (con la lista de válidos)
    """
    from services.harness_profiles import apply_profile, detect_profile, PROFILES

    body = request.get_json(force=True, silent=True) or {}
    name = str(body.get("name") or "").strip().lower()

    try:
        applied = apply_profile(name)
    except ValueError as exc:
        return jsonify({
            "ok": False,
            "error": str(exc),
            "valid_profiles": sorted(PROFILES),
        }), 400

    logger.info("perfil de arnés aplicado: %s", name)
    return jsonify({
        "ok": True,
        "applied": applied,
        "active_profile": detect_profile(),
    })


@bp.put("/harness-flags")
def put_harness_flags():
    """Actualiza uno o más flags del arnés.

    Body: {"updates": {"KEY": value, ...}}

    Proceso:
    1. Validar + castear con apply_updates (ValueError → 400, sin escribir nada).
    2. Persistir al .env con _write_env (bools como "true"/"false", int como str).
    3. Hot-apply: setattr(config, key, typed_value) para env_only=False;
       os.environ para todos (para env_only flags que se leen de os.environ).
    4. Loguear y devolver {ok, applied}.
    """
    from services.harness_flags import apply_updates, _REGISTRY_INDEX
    from config import config

    body = request.get_json(force=True, silent=True) or {}
    raw_updates: dict = body.get("updates") or {}

    if not raw_updates:
        return jsonify({"ok": True, "applied": {}}), 200

    try:
        typed = apply_updates(raw_updates)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    # Serializar a strings para el .env
    env_strings: dict[str, str] = {}
    for key, val in typed.items():
        if isinstance(val, bool):
            env_strings[key] = "true" if val else "false"
        else:
            env_strings[key] = str(val)

    # Persistir al .env (reutiliza la lógica existente de global_config)
    _write_env(env_strings)

    # Hot-apply: actualizar os.environ y el atributo del config singleton
    for key, val in typed.items():
        spec = _REGISTRY_INDEX[key]
        # os.environ: ya actualizado por _write_env (para valores no vacíos)
        # Para env_only=False también actualizamos el atributo del singleton
        if not spec.env_only:
            try:
                setattr(config, key, val)
            except (AttributeError, TypeError) as exc:
                logger.warning("hot-apply fallback para %s: %s", key, exc)

    applied_keys = list(typed.keys())
    logger.info("harness-flags actualizado: %s", applied_keys)
    return jsonify({"ok": True, "applied": typed})
