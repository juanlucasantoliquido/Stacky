"""tools/migrar_mantis_gitlab/secret_backend.py — Plan 217 F1c (C3).

Backend de secretos enchufable (portabilidad): `secrets_store.py` cifra con
DPAPI pero **aborta fuera de Windows** (`secrets_store._ensure_windows()`).
Como la herramienta se promete reutilizable en cualquier plataforma, este
módulo abstrae la resolución de un secreto detrás de 4 backends:

  - "dpapi"  -> envuelve `secrets_store.read_secret_from_file` (idéntico al
                comportamiento de hoy en Windows, backward-compat).
  - "env"    -> lee de una variable de entorno `MG_<FIELD_UPPER>`, sin
                persistir a disco (Linux/Mac/CI).
  - "prompt" -> contrato only: señala que hace falta pedirlo interactivo.
                La implementación real del prompt vive en el CLI (F9),
                fuera de este batch — acá NUNCA se implementa un
                "no-implementado" silencioso, se lanza una excepción propia
                explícita.
  - "auto"   -> "dpapi" en Windows; si no, intenta "env" y si falta, "prompt".
                Al elegir un backend no-dpapi, loguea un WARNING explícito.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from services import secrets_store

logger = logging.getLogger("migrar_mantis_gitlab.secret_backend")

_VALID_BACKENDS = ("dpapi", "env", "prompt", "auto")


class SecretPromptRequired(Exception):
    """El secreto no se pudo resolver sin interacción del operador.

    Señala que el CLI (F9, fuera de este batch) debe pedirlo interactivo;
    este módulo nunca implementa el prompt real ni devuelve un valor vacío
    en silencio."""


def resolve_secret(auth_file: str, field: str, backend: str) -> str:
    """Resuelve en texto plano el secreto `field` desde `auth_file`, según
    `backend` ("dpapi" | "env" | "prompt" | "auto").

    Lanza:
      - `ValueError` si `backend` no es uno de los 4 válidos.
      - `SecretPromptRequired` si el backend elegido no puede resolver el
        secreto sin pedirlo interactivamente al operador.
    """
    if backend not in _VALID_BACKENDS:
        raise ValueError(
            f"Backend de secretos desconocido: {backend!r}. Válidos: {list(_VALID_BACKENDS)}."
        )

    if backend == "dpapi":
        return _resolve_dpapi(auth_file, field)
    if backend == "env":
        return _resolve_env(field)
    if backend == "prompt":
        return _resolve_prompt(field)

    # backend == "auto"
    if sys.platform == "win32":
        return _resolve_dpapi(auth_file, field)

    logger.warning(
        "secret_backend='auto' en plataforma no-Windows (%s): el secreto '%s' "
        "NO quedará cifrado en reposo por DPAPI (fallback env/prompt).",
        sys.platform,
        field,
    )
    try:
        return _resolve_env(field)
    except SecretPromptRequired:
        return _resolve_prompt(field)


def _env_var_name(field: str) -> str:
    return f"MG_{field.upper()}"


def _resolve_env(field: str) -> str:
    var_name = _env_var_name(field)
    value = os.environ.get(var_name)
    if not value:
        raise SecretPromptRequired(
            f"La variable de entorno '{var_name}' no está seteada (backend 'env' "
            f"para el campo '{field}')."
        )
    return value


def _resolve_prompt(field: str) -> str:
    raise SecretPromptRequired(
        f"El backend 'prompt' para el campo '{field}' requiere pedirlo interactivo "
        "al operador; esa implementación vive en el CLI (F9), no en secret_backend.py."
    )


def _resolve_dpapi(auth_file: str, field: str) -> str:
    if not auth_file or not Path(auth_file).is_file():
        raise SecretPromptRequired(
            f"El archivo de credenciales '{auth_file}' no existe todavía; hace falta "
            f"pedir '{field}' interactivamente y persistirlo cifrado (DPAPI) la 1ra vez."
        )
    resolved = secrets_store.read_secret_from_file(
        auth_file,
        field,
        format_field="token_format",
        allow_preencoded=True,
        detect_preencoded=True,
    )
    if not resolved.value:
        raise SecretPromptRequired(
            f"El archivo '{auth_file}' no contiene un valor para '{field}'; hace falta "
            "pedirlo interactivamente y persistirlo cifrado (DPAPI)."
        )
    return resolved.value


__all__ = ["SecretPromptRequired", "resolve_secret"]
