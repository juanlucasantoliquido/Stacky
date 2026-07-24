"""tools/migrar_mantis_gitlab/config_loader.py — Plan 217 F1b.

Carga `migration_config.json` de disco y lo valida vía `config_schema.py`.
No resuelve secretos acá (eso es `secret_backend.py`, invocado por el CLI
o por `destination_writer.py` en fases posteriores) — este módulo solo
parsea/valida la estructura del archivo.
"""
from __future__ import annotations

import json
from pathlib import Path

from tools.migrar_mantis_gitlab.config_schema import (
    ConfigValidationError,
    MigrationConfig,
    validate_config,
)


class ConfigLoadError(Exception):
    """Error al leer o parsear (JSON inválido) el archivo de config de disco.

    Distinto de `ConfigValidationError` (estructura JSON válida pero
    contenido inválido) para que el CLI pueda distinguir "no encontré/no
    pude leer el archivo" de "el contenido no cumple el esquema"."""


def load_config(path: str) -> MigrationConfig:
    """Lee `path`, lo parsea como JSON y lo valida. Propaga errores claros
    (nunca una excepción genérica silenciosa):
      - `ConfigLoadError` si el archivo no existe, no se puede leer, o el
        JSON tiene un error de sintaxis.
      - `ConfigValidationError` si el JSON es válido pero el contenido no
        cumple el esquema (ver `config_schema.validate_config`).
    """
    p = Path(path)
    if not p.is_file():
        raise ConfigLoadError(f"No se encontró el archivo de config: {path}")

    try:
        raw_text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigLoadError(f"No se pudo leer el archivo de config '{path}': {exc}") from exc

    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigLoadError(
            f"El archivo de config '{path}' no es JSON válido: {exc}"
        ) from exc

    return validate_config(raw)


__all__ = ["ConfigLoadError", "load_config"]
