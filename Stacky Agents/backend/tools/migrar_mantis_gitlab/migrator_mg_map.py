"""tools/migrar_mantis_gitlab/migrator_mg_map.py — Plan 217 F4.

Tabla de mapeo `mantis_gitlab_map` en un SQLite **local y portable propio
del tool** — a diferencia de `services/migrator_map.py` (que usa la
conexión `db` compartida de la app Flask de Stacky, tabla
`migrator_ado_gitlab_map`), acá el propio módulo abre/crea su archivo
SQLite en la ruta que indique el caller (§11 del plan: "SQLite local
propio, portable — NO el `db` compartido de Stacky"). NO importa
`services/migrator_map.py` ni depende de la app Flask — reusa solo el
PATRÓN (schema + snapshot con hash).

`hydrate_map_from_destination` (rehidratación leyendo el marker desde
GitLab) NO vive en este módulo — el plan (§16 fila F5) la asigna al
executor, con implementación propia (NO reusa
`services/migrator_executor.py:154`, acoplada a `db`/`stacky_project`).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

_DDL_MAP = """
CREATE TABLE IF NOT EXISTS mantis_gitlab_map (
    project_path       TEXT NOT NULL,
    mantis_project_id  TEXT NOT NULL,
    mantis_issue_id    TEXT NOT NULL,
    gitlab_iid         TEXT,
    status             TEXT NOT NULL DEFAULT 'pending',
    last_attempt_at     TEXT,
    PRIMARY KEY (project_path, mantis_project_id, mantis_issue_id)
);
"""

_DDL_SNAPSHOT = """
CREATE TABLE IF NOT EXISTS mantis_gitlab_plan_snapshot (
    plan_id     TEXT PRIMARY KEY,
    plan_hash   TEXT NOT NULL,
    plan_json   TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def ensure_map_schema(conn: sqlite3.Connection) -> None:
    """Crea las tablas propias del tool si no existen. Idempotente."""
    conn.execute(_DDL_MAP)
    conn.execute(_DDL_SNAPSHOT)
    conn.commit()


def open_map_db(db_path: str) -> sqlite3.Connection:
    """Abre (creando el archivo/directorio padre si no existe) el SQLite
    propio y portable del tool, y garantiza el schema antes de devolver la
    conexión."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    ensure_map_schema(conn)
    return conn


# ── mantis_gitlab_map ──────────────────────────────────────────────────────


def upsert_mapping(
    conn: sqlite3.Connection,
    *,
    project_path: str,
    mantis_project_id: str,
    mantis_issue_id: str,
    gitlab_iid: Optional[str],
    status: str,
) -> None:
    """Inserta o actualiza el mapeo (project_path, mantis_project_id,
    mantis_issue_id) -> gitlab_iid/status. `status` refleja pending|done|
    partial|failed (§11 del plan)."""
    conn.execute(
        """
        INSERT INTO mantis_gitlab_map
            (project_path, mantis_project_id, mantis_issue_id, gitlab_iid, status, last_attempt_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(project_path, mantis_project_id, mantis_issue_id) DO UPDATE SET
            gitlab_iid      = excluded.gitlab_iid,
            status          = excluded.status,
            last_attempt_at = excluded.last_attempt_at
        """,
        (project_path, str(mantis_project_id), str(mantis_issue_id), gitlab_iid, status),
    )
    conn.commit()


def get_gitlab_iid(
    conn: sqlite3.Connection,
    *,
    project_path: str,
    mantis_project_id: str,
    mantis_issue_id: str,
) -> Optional[str]:
    """Devuelve el `gitlab_iid` mapeado o `None` si el issue todavía no
    fue migrado."""
    row = conn.execute(
        """
        SELECT gitlab_iid FROM mantis_gitlab_map
        WHERE project_path=? AND mantis_project_id=? AND mantis_issue_id=?
        """,
        (project_path, str(mantis_project_id), str(mantis_issue_id)),
    ).fetchone()
    return row["gitlab_iid"] if row else None


def get_full_mapping(conn: sqlite3.Connection, project_path: str) -> list[dict]:
    """Devuelve todas las filas del mapeo para el proyecto, ordenadas por
    `mantis_issue_id`. Este es el shape que `migrator_mg_core.plan_migration`
    espera reindexar a `{mantis_issue_id: status}` para su parámetro
    `existing_map`."""
    rows = conn.execute(
        """
        SELECT project_path, mantis_project_id, mantis_issue_id, gitlab_iid,
               status, last_attempt_at
        FROM mantis_gitlab_map
        WHERE project_path=?
        ORDER BY mantis_issue_id ASC
        """,
        (project_path,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── mantis_gitlab_plan_snapshot ────────────────────────────────────────────


def save_plan_snapshot(conn: sqlite3.Connection, plan_id: str, plan_hash: str, plan_data: Any) -> None:
    """Persiste el snapshot del plan (mismo patrón que
    `services/migrator_map.save_plan_snapshot`, Plan 74 F6) para detectar
    drift entre `plan` y `execute`."""
    conn.execute(
        """
        INSERT INTO mantis_gitlab_plan_snapshot (plan_id, plan_hash, plan_json)
        VALUES (?, ?, ?)
        ON CONFLICT(plan_id) DO UPDATE SET
            plan_hash = excluded.plan_hash,
            plan_json = excluded.plan_json
        """,
        (plan_id, plan_hash, json.dumps(plan_data, sort_keys=True)),
    )
    conn.commit()


def get_plan_snapshot(conn: sqlite3.Connection, plan_id: str) -> Optional[dict]:
    """Devuelve `{"plan_id", "plan_hash", "plan_json", "created_at",
    "plan_data"}` (con `plan_data` ya deserializado) o `None` si no existe."""
    row = conn.execute(
        "SELECT plan_id, plan_hash, plan_json, created_at FROM mantis_gitlab_plan_snapshot WHERE plan_id=?",
        (plan_id,),
    ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["plan_data"] = json.loads(result["plan_json"])
    return result


__all__ = [
    "ensure_map_schema",
    "get_full_mapping",
    "get_gitlab_iid",
    "get_plan_snapshot",
    "open_map_db",
    "save_plan_snapshot",
    "upsert_mapping",
]
