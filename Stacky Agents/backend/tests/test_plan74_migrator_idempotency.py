"""Plan 74 F10 — Test de idempotencia end-to-end (2 corridas = sin duplicados).

4 casos: setup + corrida1 + corrida2 (applied=0) + corrida3 (1 nuevo).
"""
import sqlite3
from unittest.mock import MagicMock

import pytest

from services.migrator_map import ensure_map_schema
from services.migrator_core import plan_migration
from services.migrator_executor import execute_migration, hydrate_map_from_destination
from services.migrator_verify import verify_migration


def _make_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    ensure_map_schema(db)
    return db


def _item(ado_id, item_type="Issue"):
    return {"id": ado_id, "title": f"Item {ado_id}", "description": "desc",
            "item_type": item_type}


def _make_origin(items):
    origin = MagicMock(name="origin")
    origin.fetch_open_items.return_value = items
    origin.fetch_all_comments.return_value = []
    origin.fetch_attachments.return_value = []
    return origin


def _make_dest(iid_start=100):
    """Mock de destino que registra los items creados."""
    dest = MagicMock(name="dest")
    _counter = [iid_start]
    _created = {}  # ado_id embedded in description → iid

    def create_item(item):
        # Extraer marker del description para hydrate
        desc = item.description_html or ""
        import re
        m = re.search(r"stacky-migrated:ado:(\w+)", desc)
        ado_id = m.group(1) if m else str(_counter[0])
        iid = str(_counter[0])
        _counter[0] += 1
        _created[ado_id] = {"id": iid, "iid": iid, "web_url": f"u/{iid}",
                             "description": desc, "item_type": item.item_type}
        return {"id": iid, "iid": iid, "web_url": f"u/{iid}"}

    dest.create_item.side_effect = create_item
    dest.comment_exists.return_value = False
    # fetch_open_items devuelve los items ya creados (para hydrate)
    dest.fetch_open_items.side_effect = lambda q: list(_created.values())
    return dest


# ── Caso 1: Setup ────────────────────────────────────────────────────────────

def test_setup_origen_con_3_epicas_5_issues():
    """El origen de prueba tiene 3 épicas + 5 issues."""
    items = [_item(str(i), "Epic") for i in range(3)] + \
            [_item(str(i + 3), "Issue") for i in range(5)]
    assert len(items) == 8
    assert sum(1 for it in items if it["item_type"] == "Epic") == 3
    assert sum(1 for it in items if it["item_type"] == "Issue") == 5


# ── Caso 2: Corrida 1 → applied == 8, passed=True ────────────────────────────

def test_corrida_1_aplica_todos():
    db = _make_db()
    base_items = [_item(str(i), "Epic") for i in range(3)] + \
                 [_item(str(i + 3), "Issue") for i in range(5)]
    origin = _make_origin(base_items)
    dest = _make_dest()

    existing_map = hydrate_map_from_destination(dest, db, stacky_project="P")
    plan = plan_migration(origin, dest, stacky_project="P", existing_map=existing_map)
    result = execute_migration(plan, dest, db, stacky_project="P",
                               migration_run="r1", existing_map=existing_map)

    assert result.applied == 8
    assert result.skipped == 0

    verify_result = verify_migration(plan, dest, stacky_project="P", db=db)
    assert verify_result.passed is True


# ── Caso 3: Corrida 2 → applied=0, skipped=8, passed=True ───────────────────

def test_corrida_2_idempotente():
    """2da corrida sobre el mismo origen → applied=0, skipped=8."""
    db = _make_db()
    base_items = [_item(str(i), "Epic") for i in range(3)] + \
                 [_item(str(i + 3), "Issue") for i in range(5)]
    origin = _make_origin(base_items)
    dest = _make_dest()

    # Corrida 1
    existing_map = hydrate_map_from_destination(dest, db, stacky_project="P")
    plan = plan_migration(origin, dest, stacky_project="P", existing_map=existing_map)
    execute_migration(plan, dest, db, stacky_project="P", migration_run="r1",
                      existing_map=existing_map)

    # Corrida 2 — mismo origen, destino ya tiene los items
    existing_map2 = hydrate_map_from_destination(dest, db, stacky_project="P")
    plan2 = plan_migration(origin, dest, stacky_project="P", existing_map=existing_map2)
    result2 = execute_migration(plan2, dest, db, stacky_project="P",
                                migration_run="r2", existing_map=existing_map2)

    # Gate de significancia: applied debe ser 0 en la 2da corrida
    assert result2.applied == 0, (
        f"Idempotencia rota: corrida 2 aplicó {result2.applied} ops (esperado 0)"
    )
    assert result2.skipped == 8


# ── Caso 4: Corrida 3 con 1 issue nuevo → applied=1, skipped=8 ───────────────

def test_corrida_3_con_item_nuevo():
    """3ra corrida con 1 issue nuevo → applied=1, skipped=8."""
    db = _make_db()
    base_items = [_item(str(i), "Epic") for i in range(3)] + \
                 [_item(str(i + 3), "Issue") for i in range(5)]
    origin = _make_origin(base_items)
    dest = _make_dest()

    # Corridas 1 y 2
    for run_id in ["r1", "r2"]:
        em = hydrate_map_from_destination(dest, db, stacky_project="P")
        plan = plan_migration(origin, dest, stacky_project="P", existing_map=em)
        execute_migration(plan, dest, db, stacky_project="P", migration_run=run_id, existing_map=em)

    # Corrida 3 con origen que ahora tiene 1 issue nuevo (ado_id "99")
    new_items = base_items + [_item("99", "Issue")]
    origin3 = _make_origin(new_items)

    em3 = hydrate_map_from_destination(dest, db, stacky_project="P")
    plan3 = plan_migration(origin3, dest, stacky_project="P", existing_map=em3)
    result3 = execute_migration(plan3, dest, db, stacky_project="P",
                                migration_run="r3", existing_map=em3)

    assert result3.applied == 1
    assert result3.skipped == 8
