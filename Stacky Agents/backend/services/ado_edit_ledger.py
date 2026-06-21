"""Plan 60 F3 — Ledger de idempotencia para ediciones aprendidas de ADO.

Garantiza que cada revisión (ado_id, rev) se convierte en lección exactamente una vez.
Almacena en SQLite (tabla ado_edit_learned) con fallback JSONL append-only
por si la DB no es escribible (builds frozen, despliegues con permisos restringidos).

Sin PII: solo persiste (ado_id, rev, run_id, ts). Nunca autor ni contenido.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("stacky_agents.services.ado_edit_ledger")

_TABLE = "ado_edit_learned"


def _get_db_path() -> str:
    """Ruta de la DB SQLite viva. Inyectable en tests."""
    from runtime_paths import data_dir
    return str(data_dir() / "stacky_agents.db")


def _get_jsonl_path() -> Path:
    """Ruta del JSONL de fallback. Inyectable en tests."""
    from runtime_paths import data_dir
    return data_dir() / "ado_edit_learned.jsonl"


def _create_table_if_needed() -> None:
    """Crea la tabla si no existe. Se llama en cada punto de entrada (idempotente)."""
    try:
        con = sqlite3.connect(_get_db_path())
        con.execute(
            f"CREATE TABLE IF NOT EXISTS {_TABLE} ("
            "ado_id INTEGER NOT NULL, "
            "rev INTEGER NOT NULL, "
            "run_id TEXT, "
            "learned_at TEXT, "
            "PRIMARY KEY (ado_id, rev)"
            ")"
        )
        con.commit()
        con.close()
    except Exception as exc:
        logger.warning("ado_edit_ledger: no se pudo crear tabla SQLite: %s", exc)


def _read_jsonl() -> set[tuple[int, int]]:
    """Lee el JSONL de fallback y devuelve los pares (ado_id, rev) ya marcados."""
    path = _get_jsonl_path()
    result: set[tuple[int, int]] = set()
    try:
        if not path.exists():
            return result
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    result.add((int(entry["ado_id"]), int(entry["rev"])))
                except Exception:
                    pass
    except Exception as exc:
        logger.warning("ado_edit_ledger: no se pudo leer JSONL: %s", exc)
    return result


def _append_jsonl(ado_id: int, rev: int, run_id: str | None) -> None:
    """Append al JSONL de fallback. Solo ado_id/rev/ts — sin PII ni contenido."""
    path = _get_jsonl_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ado_id": ado_id,
            "rev": rev,
            "run_id": run_id,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        logger.warning("ado_edit_ledger: no se pudo escribir JSONL: %s", exc)


def already_learned(ado_id: int, rev: int) -> bool:
    """True si este (ado_id, rev) ya fue convertido en lección.

    Si SQLite no funciona: cae al JSONL (idempotencia preservada).
    Si el JSONL tampoco funciona: devuelve True defensivo (no duplicar).
    """
    _create_table_if_needed()
    try:
        con = sqlite3.connect(_get_db_path())
        row = con.execute(
            f"SELECT 1 FROM {_TABLE} WHERE ado_id=? AND rev=?", (ado_id, rev)
        ).fetchone()
        con.close()
        return row is not None
    except Exception as exc:
        logger.warning("ado_edit_ledger: SQLite falló en already_learned: %s", exc)
        # Fallback: JSONL
        try:
            return (ado_id, rev) in _read_jsonl()
        except Exception:
            return True  # conservador: no duplicar si todo falla


def mark_learned(ado_id: int, rev: int, run_id: str | None) -> None:
    """Marca (ado_id, rev) como aprendido. INSERT OR IGNORE → idempotente."""
    _create_table_if_needed()
    ts = datetime.now(timezone.utc).isoformat()
    db_ok = False
    try:
        con = sqlite3.connect(_get_db_path())
        con.execute(
            f"INSERT OR IGNORE INTO {_TABLE} (ado_id, rev, run_id, learned_at) VALUES (?,?,?,?)",
            (ado_id, rev, run_id, ts),
        )
        con.commit()
        con.close()
        db_ok = True
    except Exception as exc:
        logger.warning("ado_edit_ledger: SQLite falló en mark_learned: %s", exc)

    # Siempre escribir JSONL (best-effort doble barrera)
    _append_jsonl(ado_id, rev, run_id)

    if not db_ok:
        logger.info("ado_edit_ledger: fallback JSONL para (%s, %s)", ado_id, rev)


def processed_revs_for(ado_id: int) -> set[int]:
    """Devuelve el set de revs ya aprendidas para el ado_id dado."""
    _create_table_if_needed()
    try:
        con = sqlite3.connect(_get_db_path())
        rows = con.execute(
            f"SELECT rev FROM {_TABLE} WHERE ado_id=?", (ado_id,)
        ).fetchall()
        con.close()
        return {int(r[0]) for r in rows}
    except Exception as exc:
        logger.warning("ado_edit_ledger: SQLite falló en processed_revs_for: %s", exc)
        # Fallback JSONL
        return {rev for (ai, rev) in _read_jsonl() if ai == ado_id}
