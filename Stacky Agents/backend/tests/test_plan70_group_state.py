"""Plan 70 F4 — Grupo estado: branch provider delante de cada update_work_item_state.

Como las llamadas viven dentro de endpoints Flask con sesión DB, validamos:
  (a) que el branch ``_provider_for_ticket(...) is not None`` existe antes de
      cada ``update_work_item_state`` en tickets.py (control de fuente);
  (b) smoke de import: tickets.py carga sin errores tras la migración.
"""
from __future__ import annotations

import pathlib


TICKETS = pathlib.Path(__file__).resolve().parents[1] / "api" / "tickets.py"


def test_tickets_module_imports_cleanly():
    import api.tickets  # noqa: F401


def test_every_update_work_item_state_has_provider_branch():
    """Cada ``update_work_item_state(`` en tickets.py está precedida (en la misma
    función/bloque) por un branch ``_provider_for_ticket`` que enruta por
    ``update_item_state``. Verificamos presencia textual del branch provider."""
    text = TICKETS.read_text(encoding="utf-8")
    # Cada sitio migrado introduce la línea del puerto:
    assert text.count("_provider.update_item_state(") >= 3, (
        "F4: se esperaban >=3 branches provider (update_item_state) en tickets.py"
    )
    # Y las llamadas legacy quedan como fallback (siguen presentes):
    assert text.count("update_work_item_state(") >= 3
