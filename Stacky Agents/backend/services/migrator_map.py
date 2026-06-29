"""Plan 74 F1 — Persistencia del mapeo ado_id ↔ gitlab_iid.

Funciones PURAS de CRUD sobre las tablas SQLite:
  - migrator_ado_gitlab_map  (F1)
  - migrator_plan_snapshot   (F6)

NO importa AdoClient ni GitLabTrackerProvider.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Optional


# ── Schema ───────────────────────────────────────────────────────────────────

_DDL_MAP = """
CREATE TABLE IF NOT EXISTS migrator_ado_gitlab_map (
    stacky_project TEXT NOT NULL,
    ado_id          TEXT NOT NULL,
    ado_type        TEXT NOT NULL,
    gitlab_iid      TEXT NOT NULL,
    gitlab_web_url  TEXT NOT NULL,
    marker          TEXT NOT NULL,
    migrated_at     TEXT NOT NULL DEFAULT (datetime('now')),
    migration_run   TEXT NOT NULL,
    PRIMARY KEY (stacky_project, ado_id)
);
"""

_DDL_SNAPSHOT = """
CREATE TABLE IF NOT EXISTS migrator_plan_snapshot (
    plan_id        TEXT PRIMARY KEY,
    stacky_project TEXT NOT NULL,
    counts_json    TEXT NOT NULL,
    plan_hash      TEXT NOT NULL,
    created_at     TEXT NOT NULL
);
"""


def ensure_map_schema(db: sqlite3.Connection) -> None:
    """Crea las tablas si no existen. Idempotente."""
    db.execute(_DDL_MAP)
    db.execute(_DDL_SNAPSHOT)
    db.commit()


# ── migrator_ado_gitlab_map ──────────────────────────────────────────────────

def upsert_mapping(
    db: sqlite3.Connection,
    *,
    stacky_project: str,
    ado_id: str,
    ado_type: str,
    gitlab_iid: str,
    gitlab_web_url: str,
    marker: str,
    migration_run: str,
) -> None:
    """Inserta o actualiza el mapeo (stacky_project, ado_id) → gitlab_iid."""
    db.execute(
        """
        INSERT INTO migrator_ado_gitlab_map
            (stacky_project, ado_id, ado_type, gitlab_iid, gitlab_web_url, marker, migration_run)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(stacky_project, ado_id) DO UPDATE SET
            gitlab_iid     = excluded.gitlab_iid,
            gitlab_web_url = excluded.gitlab_web_url,
            marker         = excluded.marker,
            migration_run  = excluded.migration_run,
            migrated_at    = datetime('now')
        """,
        (stacky_project, ado_id, ado_type, gitlab_iid, gitlab_web_url, marker, migration_run),
    )
    db.commit()


def get_gitlab_iid(
    db: sqlite3.Connection, stacky_project: str, ado_id: str
) -> Optional[str]:
    """Devuelve el gitlab_iid para (project, ado_id) o None si no existe."""
    row = db.execute(
        "SELECT gitlab_iid FROM migrator_ado_gitlab_map WHERE stacky_project=? AND ado_id=?",
        (stacky_project, ado_id),
    ).fetchone()
    return row["gitlab_iid"] if row else None


def get_full_mapping(db: sqlite3.Connection, stacky_project: str) -> list[dict]:
    """Devuelve todas las filas del mapeo para el proyecto, ordenadas por ado_id."""
    rows = db.execute(
        """
        SELECT stacky_project, ado_id, ado_type, gitlab_iid, gitlab_web_url,
               marker, migrated_at, migration_run
        FROM migrator_ado_gitlab_map
        WHERE stacky_project=?
        ORDER BY ado_id ASC
        """,
        (stacky_project,),
    ).fetchall()
    return [dict(r) for r in rows]


def bulk_upsert(
    db: sqlite3.Connection, stacky_project: str, rows: list[dict]
) -> None:
    """Inserta/actualiza N filas en una sola transacción."""
    with db:
        for r in rows:
            db.execute(
                """
                INSERT INTO migrator_ado_gitlab_map
                    (stacky_project, ado_id, ado_type, gitlab_iid, gitlab_web_url, marker, migration_run)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(stacky_project, ado_id) DO UPDATE SET
                    gitlab_iid     = excluded.gitlab_iid,
                    gitlab_web_url = excluded.gitlab_web_url,
                    marker         = excluded.marker,
                    migration_run  = excluded.migration_run,
                    migrated_at    = datetime('now')
                """,
                (
                    stacky_project,
                    r["ado_id"],
                    r.get("ado_type", ""),
                    r["gitlab_iid"],
                    r.get("gitlab_web_url", ""),
                    r.get("marker", ""),
                    r.get("migration_run", ""),
                ),
            )


# ── migrator_plan_snapshot (F6) ───────────────────────────────────────────────

def save_plan_snapshot(
    db: sqlite3.Connection,
    *,
    plan_id: str,
    stacky_project: str,
    counts_json: str,
    plan_hash: str,
    created_at: str,
) -> None:
    """Persiste el snapshot del dry-run para detectar drift en /execute."""
    db.execute(
        """
        INSERT INTO migrator_plan_snapshot (plan_id, stacky_project, counts_json, plan_hash, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(plan_id) DO UPDATE SET
            counts_json = excluded.counts_json,
            plan_hash   = excluded.plan_hash
        """,
        (plan_id, stacky_project, counts_json, plan_hash, created_at),
    )
    db.commit()


def get_plan_snapshot(db: sqlite3.Connection, plan_id: str) -> Optional[dict]:
    """Devuelve el snapshot por plan_id o None."""
    row = db.execute(
        "SELECT * FROM migrator_plan_snapshot WHERE plan_id=?", (plan_id,)
    ).fetchone()
    return dict(row) if row else None
