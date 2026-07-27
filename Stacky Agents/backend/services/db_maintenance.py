"""Plan 253 F5/F6 — mantenimiento de la base de runtime.

F5: purga EN LOTES de `system_logs` vencidos, registrada como tarea del
    `_maintenance_loop` compartido (thread "stacky-maintenance").
F6: diagnostico + compactacion asistida (VACUUM), la UNICA pieza destructiva
    del plan: exige confirmacion explicita del operador y respalda antes.
"""
from __future__ import annotations

import logging
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("stacky.db_maintenance")

# El VACUUM necesita ~2x el tamano de la base en disco, mas el respaldo previo.
_DISK_HEADROOM_FACTOR = 2.2
_COMPACT_ACTION = "db_compact"


# ── F5 — purga en lotes ──────────────────────────────────────────────────────


def purge_syslog_batched(*, days: int | None = None, batch_size: int = 5000,
                         max_batches: int = 200) -> int:
    """Plan 253 F5 — borra system_logs vencidos EN LOTES. Devuelve filas borradas.

    OJO (medido en este SQLite 3.49.1): `DELETE ... LIMIT` NO existe
    (`near "limit": syntax error`, sin ENABLE_UPDATE_DELETE_LIMIT). El lote se
    acota con una subconsulta por clave primaria.

    El indice ix_syslog_timestamp YA EXISTE (models.py:457): NO crear otro.
    """
    from sqlalchemy import text

    from config import config
    from db import run_with_retry, session_scope

    days = config.STACKY_SYSLOG_RETENTION_DAYS if days is None else days
    cutoff = datetime.utcnow() - timedelta(days=int(days))
    total = 0
    for _ in range(max_batches):
        def _unit():
            with session_scope() as session:
                return session.execute(text(
                    "DELETE FROM system_logs WHERE id IN ("
                    "  SELECT id FROM system_logs WHERE timestamp < :cutoff LIMIT :n)"
                ), {"cutoff": cutoff, "n": batch_size}).rowcount

        deleted = run_with_retry(_unit, label="syslog.purge") or 0
        total += deleted
        if deleted < batch_size:
            break
    return total


def register_syslog_purge_task() -> None:
    """Plan 253 F5 — cuelga la purga del loop de mantenimiento compartido.

    `interval_s` y `enabled` son callables A PROPOSITO: leer `config.X` en
    tiempo de registro congelaria el valor y la flag de la UI no aplicaria
    hasta reiniciar.
    """
    from config import config
    from services.maintenance import MaintenanceTask, register_maintenance_task

    register_maintenance_task(MaintenanceTask(
        name="syslog_purge",
        interval_s=lambda: int(config.STACKY_SYSLOG_PURGE_INTERVAL_S),
        enabled=lambda: bool(config.STACKY_SYSLOG_AUTO_PURGE_ENABLED),
        run=purge_syslog_batched,
    ))


# ── F6 — diagnostico y compactacion asistida (HITL) ──────────────────────────


def _sqlite_path() -> Path | None:
    """Detector UNICO de 'es SQLite con archivo' (reusa services/db_backup.py)."""
    from services.db_backup import sqlite_db_path

    try:
        return sqlite_db_path()
    except Exception:  # noqa: BLE001 — el diagnostico jamas rompe el health
        return None


def _wal_path(path: Path) -> Path:
    return path.with_name(path.name + "-wal")


def db_stats() -> dict:
    """Diagnostico read-only de la base de runtime.

    {'available', 'path', 'size_bytes', 'wal_size_bytes', 'page_count',
     'page_size', 'journal_mode', 'rows_by_table', 'purgeable_rows',
     'purgeable_before', 'estimated_reclaim_bytes'}

    Si la base no es SQLite-con-archivo devuelve {'available': False, 'reason': ...}.
    """
    from config import config

    path = _sqlite_path()
    if path is None:
        return {"available": False, "reason": "non_sqlite_database"}
    if not path.exists():
        return {"available": False, "reason": "database_missing", "path": str(path)}

    days = int(config.STACKY_SYSLOG_RETENTION_DAYS)
    cutoff = datetime.utcnow() - timedelta(days=days)

    conn = sqlite3.connect(str(path))
    try:
        cur = conn.cursor()
        journal_mode = str((cur.execute("PRAGMA journal_mode").fetchone() or [""])[0]).lower()
        page_count = int((cur.execute("PRAGMA page_count").fetchone() or [0])[0])
        page_size = int((cur.execute("PRAGMA page_size").fetchone() or [0])[0])
        freelist = int((cur.execute("PRAGMA freelist_count").fetchone() or [0])[0])

        rows_by_table: dict[str, int] = {}
        tables = [
            r[0] for r in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        for table in tables:
            try:
                rows_by_table[table] = int(
                    cur.execute(f"SELECT count(*) FROM \"{table}\"").fetchone()[0]
                )
            except sqlite3.Error:
                continue

        try:
            purgeable = int(cur.execute(
                "SELECT count(*) FROM system_logs WHERE timestamp < ?",
                (cutoff.strftime("%Y-%m-%d %H:%M:%S.%f"),),
            ).fetchone()[0])
        except sqlite3.Error:
            purgeable = 0
        total_syslog = rows_by_table.get("system_logs", 0)
        cur.close()
    finally:
        conn.close()

    size_bytes = path.stat().st_size
    wal = _wal_path(path)
    wal_size = wal.stat().st_size if wal.exists() else 0

    # Estimacion honesta: espacio ya libre en el archivo + la parte proporcional
    # de system_logs que se borraria. No pretende ser exacta.
    reclaim = freelist * page_size
    if total_syslog > 0 and purgeable > 0:
        reclaim += int(size_bytes * (purgeable / max(total_syslog, 1)) * 0.99)

    return {
        "available": True,
        "path": str(path),
        "size_bytes": size_bytes,
        "wal_size_bytes": wal_size,
        "page_count": page_count,
        "page_size": page_size,
        "freelist_count": freelist,
        "journal_mode": journal_mode,
        "rows_by_table": rows_by_table,
        "purgeable_rows": purgeable,
        "purgeable_before": cutoff.isoformat(),
        "retention_days": days,
        "estimated_reclaim_bytes": max(reclaim, 0),
    }


def issue_compact_token(stats: dict | None = None) -> str:
    """Emite el identificador efimero que la UI debe devolver para compactar."""
    from services.confirm_token import issue_token

    stats = stats if stats is not None else db_stats()
    return issue_token(_COMPACT_ACTION, {
        "rows_to_delete": int(stats.get("purgeable_rows") or 0),
        "bytes_to_reclaim": int(stats.get("estimated_reclaim_bytes") or 0),
        "cutoff_iso": stats.get("purgeable_before"),
    })


class CompactError(Exception):
    """Falla controlada de la compactacion; lleva un `reason` para el llamador."""

    def __init__(self, reason: str, message: str = ""):
        super().__init__(message or reason)
        self.reason = reason


def compact_db(*, token: str, purge_retroactive: bool = True) -> dict:
    """Plan 253 F6 — VACUUM + (opcional) purga retroactiva. Pieza DESTRUCTIVA.

    Orden EXACTO, no negociable:
      1. validar el identificador de confirmacion (un solo uso, con TTL) y que
         el conteo que vio el operador siga vigente (+-5%);
      2. verificar espacio en disco >= 2,2x el tamano de la base;
      3. detener el vigilante de artefactos;
      4. copia de respaldo previa (reusa services/db_backup.py y SU convencion
         de nombre `stacky_agents-YYYYMMDD.db`, que el pruning entiende);
      5. purga retroactiva EN LOTES (reusa purge_syslog_batched);
      6. PRAGMA wal_checkpoint(TRUNCATE) — si no, el sidecar sobrevive y el
         espacio recuperado que se le reporta al operador es mentira;
      7. VACUUM en una conexion aparte con isolation_level=None;
      8. reanudar el vigilante (pasos 3 y 8 en try/finally);
      9. devolver el antes/despues.
    """
    from config import config
    from services.confirm_token import ConfirmTokenError, consume_token

    if not config.STACKY_DB_COMPACT_ENABLED:
        raise CompactError("compact_disabled", "la compactacion esta deshabilitada")

    before = db_stats()
    if not before.get("available"):
        raise CompactError(before.get("reason") or "unavailable",
                           "no hay una base de archivo que compactar")

    # 1) confirmacion explicita del operador, atada al conteo que vio.
    try:
        payload = consume_token(_COMPACT_ACTION, token)
    except ConfirmTokenError as exc:
        raise CompactError("confirmation_invalid", str(exc)) from exc

    prometidas = int(payload.get("rows_to_delete") or 0)
    actuales = int(before.get("purgeable_rows") or 0)
    tolerancia = max(int(prometidas * 0.05), 1)
    if abs(actuales - prometidas) > tolerancia:
        raise CompactError(
            "confirmation_stale",
            f"el conteo cambio desde el diagnostico ({prometidas} -> {actuales})",
        )

    path = Path(before["path"])

    # 2) espacio en disco antes de tocar nada.
    needed = int(before["size_bytes"] * _DISK_HEADROOM_FACTOR)
    free = shutil.disk_usage(str(path.parent)).free
    if free < needed:
        raise CompactError(
            "insufficient_disk_space",
            f"hacen falta ~{needed} bytes libres y hay {free}",
        )

    from services.output_watcher import get_output_watcher, start_output_watcher

    watcher = get_output_watcher()
    estaba_corriendo = bool(watcher and watcher._thread and watcher._thread.is_alive())
    poll_interval = watcher.poll_interval if watcher is not None else None

    purged = 0
    try:
        # 3) detener el vigilante para que no escriba durante el VACUUM.
        if estaba_corriendo and watcher is not None:
            watcher.stop()

        # 4) respaldo previo OBLIGATORIO; si falla, se aborta sin tocar la base.
        backup = _forzar_backup()
        if not backup.get("ok"):
            raise CompactError("backup_failed", f"la copia de respaldo fallo: {backup!r}")

        # 5) purga retroactiva en lotes.
        if purge_retroactive:
            purged = purge_syslog_batched()

        # 6 y 7) checkpoint + VACUUM en su propia conexion (fuera de transaccion).
        conn = sqlite3.connect(str(path), isolation_level=None)
        try:
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.Error:
                logger.warning("wal_checkpoint fallo antes del VACUUM", exc_info=True)
            conn.execute("VACUUM")
        finally:
            conn.close()
    finally:
        # 8) el vigilante vuelve SIEMPRE si estaba corriendo (nunca se lo arranca
        #    de cero si no lo estaba).
        if estaba_corriendo:
            try:
                start_output_watcher(poll_interval=poll_interval)
            except Exception:  # noqa: BLE001
                logger.exception("no se pudo reanudar el vigilante de artefactos")

    after = db_stats()
    return {
        "ok": True,
        "purged_rows": purged,
        "backup_path": backup.get("backup_path"),
        "before": {"size_bytes": before.get("size_bytes"),
                   "wal_size_bytes": before.get("wal_size_bytes"),
                   "purgeable_rows": before.get("purgeable_rows")},
        "after": {"size_bytes": after.get("size_bytes"),
                  "wal_size_bytes": after.get("wal_size_bytes"),
                  "purgeable_rows": after.get("purgeable_rows")},
        "reclaimed_bytes": max(int(before.get("size_bytes") or 0)
                               - int(after.get("size_bytes") or 0), 0),
    }


def _forzar_backup() -> dict:
    """Respaldo previo REUSANDO db_backup y su convencion de nombre.

    PROHIBIDO inventar `stacky_agents-<timestamp>.db`: ese nombre no matchea
    `_BACKUP_RE`, el pruning nunca lo borraria y cada compactacion dejaria una
    copia muerta para siempre.
    """
    from services import db_backup

    result = db_backup.ensure_weekly_backup()
    if result.get("ok") and not result.get("skipped"):
        return result
    if not result.get("ok"):
        return result

    # Ya habia respaldo de esta semana: se fuerza uno nuevo con el MISMO nombre
    # (mismo dia => mismo archivo), borrando el anterior para que se regenere.
    existing = result.get("backup_path")
    try:
        if existing:
            Path(existing).unlink(missing_ok=True)
    except OSError as exc:
        return {"ok": False, "skipped": True, "reason": f"backup_unlink_failed: {exc}",
                "backup_path": existing}
    return db_backup.ensure_weekly_backup()
