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
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("stacky_agents.services.ado_edit_ledger")

_TABLE = "ado_edit_learned"

# C3 — dedup de warnings de SQLite POR FIRMA (no un booleano global de un solo
# disparo). Un booleano único silenciaría PARA SIEMPRE cualquier fallo nuevo o
# persistente posterior; el dedup por firma re-emite ante un error distinto y
# a lo sumo una vez por intervalo. Semántica idéntica a
# services/log_throttle.log_throttled (Plan 145): cuando 145 aterrice, migrar
# es reemplazar este helper por una llamada (ver cross-ref al final de F2).
_SQLITE_WARN_STATE: dict[str, float] = {}   # firma -> ts monotónico del último warning
_SQLITE_WARN_INTERVAL_S = 300.0             # re-emite una firma a lo sumo cada 5 min


def _connect() -> "sqlite3.Connection":
    """Abre la DB SQLite del ledger garantizando el directorio padre.

    Centraliza TODA apertura de conexión: crea el dir padre (mkdir -p) antes
    de conectar para evitar 'unable to open database file' cuando data_dir()
    aún no existe. (Causa raíz de la resolución de rutas: ver Plan 147.)
    """
    db_path = _get_db_path()
    try:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass  # si el mkdir falla, la connect de abajo reporta el error real
    return sqlite3.connect(db_path)


def _warn_sqlite_unavailable(where: str, exc: Exception) -> None:
    """Loguea con dedup POR FIRMA (tipo + mensaje de la excepción) y throttle.

    - Firma nueva (fallo distinto)  -> WARNING una vez.
    - Misma firma dentro del intervalo -> DEBUG (silenciado, no oculto).
    - Misma firma tras _SQLITE_WARN_INTERVAL_S -> vuelve a WARNING (heartbeat),
      para que un fallo PERSISTENTE no desaparezca de los logs para siempre.
    La firma NO incluye `where` a propósito: el mismo error desde 4 call-sites
    colapsa a 1 warning (cumple el KPI 42 -> <=1), pero un error de otra causa
    (p. ej. 'disk image is malformed') sí aflora.
    """
    sig = f"{type(exc).__name__}:{exc}"
    now = time.monotonic()
    last = _SQLITE_WARN_STATE.get(sig)
    if last is None or (now - last) >= _SQLITE_WARN_INTERVAL_S:
        _SQLITE_WARN_STATE[sig] = now
        logger.warning(
            "ado_edit_ledger: SQLite no disponible (%s): %s — degradando a "
            "JSONL. Repeticiones de esta firma se omiten por %ss.",
            where, exc, int(_SQLITE_WARN_INTERVAL_S),
        )
    else:
        logger.debug("ado_edit_ledger: SQLite falló (%s): %s", where, exc)


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
        con = _connect()
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
        _warn_sqlite_unavailable("create_table", exc)


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
        con = _connect()
        row = con.execute(
            f"SELECT 1 FROM {_TABLE} WHERE ado_id=? AND rev=?", (ado_id, rev)
        ).fetchone()
        con.close()
        return row is not None
    except Exception as exc:
        _warn_sqlite_unavailable("already_learned", exc)
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
        con = _connect()
        con.execute(
            f"INSERT OR IGNORE INTO {_TABLE} (ado_id, rev, run_id, learned_at) VALUES (?,?,?,?)",
            (ado_id, rev, run_id, ts),
        )
        con.commit()
        con.close()
        db_ok = True
    except Exception as exc:
        _warn_sqlite_unavailable("mark_learned", exc)

    # Siempre escribir JSONL (best-effort doble barrera)
    _append_jsonl(ado_id, rev, run_id)

    if not db_ok:
        logger.info("ado_edit_ledger: fallback JSONL para (%s, %s)", ado_id, rev)


def processed_revs_for(ado_id: int) -> set[int]:
    """Devuelve el set de revs ya aprendidas para el ado_id dado."""
    _create_table_if_needed()
    try:
        con = _connect()
        rows = con.execute(
            f"SELECT rev FROM {_TABLE} WHERE ado_id=?", (ado_id,)
        ).fetchall()
        con.close()
        return {int(r[0]) for r in rows}
    except Exception as exc:
        _warn_sqlite_unavailable("processed_revs_for", exc)
        # Fallback JSONL
        return {rev for (ai, rev) in _read_jsonl() if ai == ado_id}
