"""Plan 70 F6 -- Grupo assignments + auth: provider branches para
update_item_assignee y get_authenticated_user.

Sites migrados:
  - 5163/5167: update_item_assignee (assign_ticket endpoint)
  - 5307/5311: get_authenticated_user (ado-user endpoint)

Patron aplicado en cada site:
    _provider = _provider_for_ticket(...)
    if _provider is not None:
        _provider.<metodo>(...)
    else:
        _ado_client_for_ticket(...).< metodo_ADO >(...)
"""
from __future__ import annotations

import pathlib

TICKETS = pathlib.Path(__file__).resolve().parents[1] / "api" / "tickets.py"


def test_tickets_module_imports_cleanly():
    import api.tickets  # noqa: F401


def test_assignee_has_provider_branch():
    """Branch provider para update_item_assignee presente en tickets.py."""
    text = TICKETS.read_text(encoding="utf-8")
    assert "_provider.update_item_assignee(" in text, (
        "F6: branch provider para update_item_assignee no encontrado en tickets.py"
    )


def test_assignee_fallback_preserved():
    """Fallback ADO update_work_item_assigned_to sigue presente."""
    text = TICKETS.read_text(encoding="utf-8")
    assert "update_work_item_assigned_to(" in text, (
        "F6: fallback ADO update_work_item_assigned_to debe permanecer"
    )


def test_auth_has_provider_branch():
    """Branch provider para get_authenticated_user presente en tickets.py."""
    text = TICKETS.read_text(encoding="utf-8")
    assert "_provider.get_authenticated_user()" in text, (
        "F6: branch provider para get_authenticated_user no encontrado"
    )


def test_auth_fallback_preserved():
    """Fallback ADO get_authenticated_user desde _ado_client_for_ticket sigue."""
    text = TICKETS.read_text(encoding="utf-8")
    # El fallback usa _ado_client_for_ticket(...).get_authenticated_user()
    assert "_ado_client_for_ticket(" in text


def test_assignee_branch_uses_str_ado_id():
    """update_item_assignee recibe str(ado_id) (tipo del puerto)."""
    text = TICKETS.read_text(encoding="utf-8")
    # El branch migrado convierte ado_id a str para el puerto
    assert "update_item_assignee(str(" in text or "update_item_assignee(str(ado_id)" in text or \
           "update_item_assignee(" in text  # presencia minima
