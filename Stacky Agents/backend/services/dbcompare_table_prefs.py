"""Plan 176 F6 — Tablas de parámetro y claves naturales, elegidas una sola vez.

Dos molestias reales del comparador de datos:

1. En cada corrida hay que volver a tildar las mismas tablas de parámetro. El
   operador ya sabe cuáles son; que el producto se lo pregunte cada vez es
   trabajo inventado.
2. Una tabla sin PK hoy es "no comparable" y punto. Pero muchas de esas tienen
   una clave natural que el operador conoce perfectamente (el caso `RCONTROLES`
   del prior art). Declararla una vez las vuelve comparables.

Las preferencias son GLOBALES, no por ambiente: es el mismo producto en todos
los ambientes del cliente, y el prior art hacía exactamente eso con su
`FallbackKeyColumns`.

Acá NO se guarda SQL, solo nombres de columna — el quoting sigue siendo trabajo
de `quote_ident` al emitir.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from runtime_paths import data_dir

__all__ = [
    "PREFS_VERSION",
    "load_prefs",
    "set_pref",
    "natural_key_for",
    "param_tables",
    "is_param_table",
]

PREFS_VERSION = 1

# Un nombre de columna, no una expresión: lo que entra acá termina en un SELECT.
_COL_RE = re.compile(r"^[A-Za-z0-9_$#]{1,128}$")

_SIN_CAMBIO = object()


def _prefs_path() -> Path:
    return Path(data_dir()) / "db_compare" / "table_prefs.json"


def _clave(schema: str, table: str) -> str:
    return f"{schema or ''}.{table or ''}"


def _vacio() -> dict:
    return {"version": PREFS_VERSION, "tables": {}}


def load_prefs() -> dict:
    """Nunca lanza: sin archivo o corrupto ⇒ preferencias vacías."""
    try:
        path = _prefs_path()
        if not path.is_file():
            return _vacio()
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or not isinstance(doc.get("tables"), dict):
            return _vacio()
        doc.setdefault("version", PREFS_VERSION)
        return doc
    except Exception:  # noqa: BLE001
        return _vacio()


def _validar_clave_natural(cols) -> list:
    if not isinstance(cols, list) or not cols:
        raise ValueError("natural_key debe ser una lista no vacía de columnas")
    limpias = []
    for c in cols:
        nombre = str(c or "").strip()
        if not _COL_RE.match(nombre):
            raise ValueError(f"nombre de columna inválido: {c!r}")
        limpias.append(nombre)
    if len(set(limpias)) != len(limpias):
        raise ValueError("la clave natural tiene columnas repetidas")
    return limpias


def set_pref(schema: str, table: str, natural_key=_SIN_CAMBIO,
             param_table=_SIN_CAMBIO) -> dict:
    """Actualización PARCIAL: lo que no se pasa, no se toca.

    `natural_key=None` explícito borra la clave; omitirlo la deja como estaba.
    Sin esa distinción no habría forma de tocar solo el flag de parámetro.
    """
    doc = load_prefs()
    clave = _clave(schema, table)
    entrada = dict(doc["tables"].get(clave) or {})

    if natural_key is not _SIN_CAMBIO:
        entrada["natural_key"] = (None if natural_key is None
                                  else _validar_clave_natural(natural_key))
    if param_table is not _SIN_CAMBIO:
        entrada["param_table"] = bool(param_table)

    entrada["updated_at"] = datetime.now(timezone.utc).isoformat()
    doc["tables"][clave] = entrada

    path = _prefs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return doc


def natural_key_for(schema: str, table: str) -> list | None:
    entrada = load_prefs()["tables"].get(_clave(schema, table)) or {}
    cols = entrada.get("natural_key")
    return list(cols) if cols else None


def is_param_table(schema: str, table: str) -> bool:
    entrada = load_prefs()["tables"].get(_clave(schema, table)) or {}
    return bool(entrada.get("param_table"))


def param_tables() -> list:
    doc = load_prefs()
    return sorted(k for k, v in doc["tables"].items() if (v or {}).get("param_table"))
