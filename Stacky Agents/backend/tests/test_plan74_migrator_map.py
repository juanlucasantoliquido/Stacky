"""Plan 74 F1 — Tests de migrator_map.py (tabla migrator_ado_gitlab_map + migrator_plan_snapshot).

7 casos F1 + helpers de snapshot (F6).
"""
import sqlite3
import pytest


def _make_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    return db


# Importar después de crear el módulo
from services.migrator_map import (
    ensure_map_schema,
    upsert_mapping,
    get_gitlab_iid,
    get_full_mapping,
    bulk_upsert,
    save_plan_snapshot,
    get_plan_snapshot,
)


# ── F1 — migrator_ado_gitlab_map ──────────────────────────────────────────────

def test_ensure_map_schema_idempotente():
    """ensure_map_schema es idempotente (llamar 2x no falla)."""
    db = _make_db()
    ensure_map_schema(db)
    ensure_map_schema(db)  # no debe lanzar


def test_upsert_y_get_gitlab_iid():
    """upsert_mapping + get_gitlab_iid devuelve el iid correcto."""
    db = _make_db()
    ensure_map_schema(db)
    upsert_mapping(
        db,
        stacky_project="proj-A",
        ado_id="100",
        ado_type="Epic",
        gitlab_iid="5",
        gitlab_web_url="https://gitlab.example.com/issues/5",
        marker="<!-- stacky-migrated:ado:100 -->",
        migration_run="run-001",
    )
    assert get_gitlab_iid(db, "proj-A", "100") == "5"


def test_upsert_actualiza_sin_duplicar():
    """upsert_mapping sobre (project, ado_id) existente actualiza iid (no duplica)."""
    db = _make_db()
    ensure_map_schema(db)
    upsert_mapping(db, stacky_project="P", ado_id="10", ado_type="Issue",
                   gitlab_iid="1", gitlab_web_url="u1", marker="m", migration_run="r1")
    upsert_mapping(db, stacky_project="P", ado_id="10", ado_type="Issue",
                   gitlab_iid="99", gitlab_web_url="u99", marker="m", migration_run="r2")
    assert get_gitlab_iid(db, "P", "10") == "99"
    rows = get_full_mapping(db, "P")
    assert len(rows) == 1  # no duplicó


def test_get_gitlab_iid_inexistente_devuelve_none():
    """get_gitlab_iid para ado_id inexistente → None."""
    db = _make_db()
    ensure_map_schema(db)
    assert get_gitlab_iid(db, "P", "999") is None


def test_bulk_upsert_inserta_n_filas():
    """bulk_upsert inserta N filas en una transacción y son legibles por get_full_mapping."""
    db = _make_db()
    ensure_map_schema(db)
    rows_in = [
        {"ado_id": str(i), "ado_type": "Issue", "gitlab_iid": str(i + 100),
         "gitlab_web_url": f"u{i}", "marker": f"m{i}", "migration_run": "r"}
        for i in range(5)
    ]
    bulk_upsert(db, "proj-B", rows_in)
    out = get_full_mapping(db, "proj-B")
    assert len(out) == 5


def test_get_full_mapping_ordena_por_ado_id():
    """get_full_mapping ordena por ado_id ascendente (determinista)."""
    db = _make_db()
    ensure_map_schema(db)
    for ado_id in ["30", "10", "20"]:
        upsert_mapping(db, stacky_project="P", ado_id=ado_id, ado_type="Issue",
                       gitlab_iid=ado_id, gitlab_web_url="u", marker="m", migration_run="r")
    out = get_full_mapping(db, "P")
    ado_ids = [r["ado_id"] for r in out]
    assert ado_ids == sorted(ado_ids)


def test_aislamiento_por_proyecto():
    """Mapping de proyecto A no filtra a proyecto B."""
    db = _make_db()
    ensure_map_schema(db)
    upsert_mapping(db, stacky_project="A", ado_id="1", ado_type="Epic",
                   gitlab_iid="10", gitlab_web_url="u", marker="m", migration_run="r")
    upsert_mapping(db, stacky_project="B", ado_id="1", ado_type="Epic",
                   gitlab_iid="20", gitlab_web_url="u", marker="m", migration_run="r")
    assert get_gitlab_iid(db, "A", "1") == "10"
    assert get_gitlab_iid(db, "B", "1") == "20"
    assert len(get_full_mapping(db, "A")) == 1
    assert len(get_full_mapping(db, "B")) == 1


# ── F6 — migrator_plan_snapshot ───────────────────────────────────────────────

def test_save_y_get_plan_snapshot():
    """save_plan_snapshot + get_plan_snapshot recupera el snapshot correctamente."""
    db = _make_db()
    ensure_map_schema(db)
    save_plan_snapshot(db, plan_id="p1", stacky_project="proj",
                       counts_json='{"Epic": 2}', plan_hash="abc123",
                       created_at="2026-06-29T00:00:00Z")
    snap = get_plan_snapshot(db, "p1")
    assert snap is not None
    assert snap["plan_hash"] == "abc123"
    assert snap["stacky_project"] == "proj"


def test_get_plan_snapshot_inexistente_devuelve_none():
    """get_plan_snapshot para plan_id inexistente → None."""
    db = _make_db()
    ensure_map_schema(db)
    assert get_plan_snapshot(db, "no-existe") is None
