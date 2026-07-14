"""services/dbcompare_sqlnames.py — Plan 125 F1.

Fuente unica de verdad para quoting de identificadores y naming de backups
en los scripts de paridad del Comparador de BD (serie 122-126). Puro:
string -> string, sin tocar BD.
"""
from __future__ import annotations

import hashlib
import re

IDENT_MAX = {"sqlserver": 128, "oracle": 128, "sqlite": 128}
# Nota Oracle: 128 vale para 12.2+; si el operador corre 11g/12.1 (limite 30)
# el nombre truncado igual funciona porque backup_table_name acepta max_len
# por parametro. La UI no expone esto en v1; el generador usa IDENT_MAX[engine].

_SLUG_RE = re.compile(r"[^A-Za-z0-9_-]")


def quote_ident(name: str, dialect: str) -> str:
    if dialect == "sqlserver":
        return "[" + name.replace("]", "]]") + "]"
    if dialect == "oracle":
        return '"' + name.upper().replace('"', '""') + '"'
    if dialect == "sqlite":
        return '"' + name.replace('"', '""') + '"'
    raise ValueError(f"dialecto desconocido: {dialect!r}")


def qualified(schema: str, name: str, dialect: str) -> str:
    return quote_ident(schema, dialect) + "." + quote_ident(name, dialect)


def backup_table_name(table: str, ts: str, max_len: int) -> str:
    """Convencion del operador (Backup-TestTables.ps1, doc 122 §2-bis):
    sufijo "_BAK_" + timestamp. Si no entra en max_len, cae a un sufijo fijo
    de 14 chars con hash determinista. Determinista: mismo (table, ts,
    max_len) -> mismo nombre.
    """
    candidato = f"{table}_BAK_{ts}"
    if len(candidato) <= max_len:
        return candidato
    hash6 = hashlib.sha256(table.encode()).hexdigest()[:6].upper()
    head = table[: max_len - 14]
    return f"{head}_BAK{hash6}{ts[4:8]}"


def _slug(texto: str) -> str:
    return _SLUG_RE.sub("_", texto)[:60]


def script_filename(seq: int, kind: str, schema: str, name: str) -> str:
    return f"{seq:03d}_{kind}_{_slug(schema)}_{_slug(name)}.sql"
