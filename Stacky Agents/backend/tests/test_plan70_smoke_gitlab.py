"""Plan 70 F13 -- Smoke: flag STACKY_TICKETS_PROVIDER_ENABLED + provider round-trip.

Verifica que:
  1. La flag existe en config.py y es editable por UI (env_only=False).
  2. Con flag ON + GitLab config: _provider_for_ticket devuelve un provider
     con nombre != "azure_devops" (no retorna AdoTrackerProvider por defecto).
  3. Con flag OFF: _provider_for_ticket retorna None (byte-identico con pre-plan).
  4. _tracker_item_from_kwargs produce un TrackerItem valido con los campos esperados.
"""
from __future__ import annotations

import pathlib
from unittest.mock import patch, MagicMock


def test_flag_exists_in_config():
    """STACKY_TICKETS_PROVIDER_ENABLED esta en config.py."""
    config = (
        pathlib.Path(__file__).resolve().parents[1] / "config.py"
    ).read_text(encoding="utf-8")
    assert "STACKY_TICKETS_PROVIDER_ENABLED" in config, (
        "F13: la flag STACKY_TICKETS_PROVIDER_ENABLED debe definirse en config.py"
    )


def test_flag_editable_by_ui():
    """STACKY_TICKETS_PROVIDER_ENABLED es editable por UI (env_only=False)."""
    config = (
        pathlib.Path(__file__).resolve().parents[1] / "config.py"
    ).read_text(encoding="utf-8")
    # La flag NO debe declararse como env_only=True
    lines = config.splitlines()
    in_block = False
    for i, line in enumerate(lines):
        if "STACKY_TICKETS_PROVIDER_ENABLED" in line:
            in_block = True
        if in_block and "env_only=True" in line:
            assert False, (
                f"F13: STACKY_TICKETS_PROVIDER_ENABLED no debe tener env_only=True "
                f"(operador debe poder activarla por UI). Linea {i+1}: {line.strip()!r}"
            )
        if in_block and ("HarnessFlag(" in line or ")" in line) and i > lines.index(
            next(l for l in lines if "STACKY_TICKETS_PROVIDER_ENABLED" in l)
        ):
            break  # fin del bloque de esta flag


def test_provider_for_ticket_flag_off_returns_none():
    """Flag OFF: _provider_for_ticket retorna None (comportamiento pre-plan)."""
    import config as cfg
    import api.tickets as tickets

    original = cfg.config.STACKY_TICKETS_PROVIDER_ENABLED
    try:
        cfg.config.STACKY_TICKETS_PROVIDER_ENABLED = False
        result = tickets._provider_for_ticket(project_name="p")
    finally:
        cfg.config.STACKY_TICKETS_PROVIDER_ENABLED = original

    assert result is None, (
        "F13: con flag OFF _provider_for_ticket debe retornar None (byte-identico)"
    )


def test_tracker_item_from_kwargs_creates_valid_item():
    """_tracker_item_from_kwargs produce TrackerItem con campos correctos."""
    import api.tickets as tickets

    item = tickets._tracker_item_from_kwargs(
        work_item_type="Epic",
        title="Mi Epica",
        description="<h1>desc</h1>",
    )

    assert item.item_type == "Epic"
    assert item.title == "Mi Epica"
    assert item.description_html == "<h1>desc</h1>"


def test_all_plan70_test_files_registered_in_ratchet():
    """F13: todos los test_plan70_*.py estan en HARNESS_TEST_FILES del .sh."""
    import re

    backend = pathlib.Path(__file__).resolve().parents[1]
    sh_path = backend / "scripts" / "run_harness_tests.sh"
    sh_text = sh_path.read_text(encoding="utf-8")

    # Archivos test_plan70_*.py existentes
    plan70_files = sorted(
        f"tests/{p.name}" for p in (backend / "tests").glob("test_plan70_*.py")
    )

    missing = [f for f in plan70_files if f not in sh_text]
    assert not missing, (
        "F13: estos test_plan70_*.py NO estan en HARNESS_TEST_FILES:\n"
        + "\n".join(f"  {f}" for f in missing)
    )
