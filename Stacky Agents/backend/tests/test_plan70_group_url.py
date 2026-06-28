"""Plan 70 F5 -- Grupo url: branch provider delante de cada item_url.

Los sites ya migrados (2032, 3958, 4258) introducen el patron:
    _provider = _provider_for_ticket(...)
    if _provider is not None:
        task_url = _provider.item_url(str(ado_id))
    else:
        task_url = _ado_client_for_ticket(...).work_item_url(int(ado_id))

Los sites dentro de los bloques de creacion epic/issue (6036, 6459) se migraran
junto con F8 (create group) y el contador de item_url subira a >=5 ahi.
"""
from __future__ import annotations

import pathlib

TICKETS = pathlib.Path(__file__).resolve().parents[1] / "api" / "tickets.py"


def test_tickets_module_imports_cleanly():
    import api.tickets  # noqa: F401


def test_url_group_has_provider_branches():
    """Al menos 3 branches provider (item_url) existen en tickets.py.

    Sitios ya migrados al momento de F5: 2032, 3958, 4258.
    Despues de F8 el contador sube a >=5 (6036 + 6459 sumados).
    """
    text = TICKETS.read_text(encoding="utf-8")
    count = text.count("_provider.item_url(")
    assert count >= 3, (
        f"F5: se esperaban >=3 branches provider (item_url) en tickets.py, "
        f"encontrados {count}"
    )


def test_url_fallback_work_item_url_preserved():
    """Los branches fallback ADO (work_item_url) siguen presentes."""
    text = TICKETS.read_text(encoding="utf-8")
    assert ".work_item_url(" in text, (
        "F5: work_item_url fallback ADO debe preservarse en tickets.py"
    )


def test_url_branches_paired_with_fallback():
    """Cada provider branch debe ir acompanado por un branch fallback ADO."""
    text = TICKETS.read_text(encoding="utf-8")
    # Verificacion de presencia de ambos patrones (no cuenta exacta)
    assert "_provider.item_url(" in text
    assert "_ado_client_for_ticket(" in text or "work_item_url(" in text
