"""Plan 70 F7 -- Grupo attachments: provider branches para fetch/upload/link.

Sites migrados:
  - 889/895: fetch_attachments (get_attachments endpoint)
  - 4430/4432: upload_attachment (create_child_task)
  - 4447/4449: link_attachment (create_child_task)

Patron aplicado:
    _provider = _provider_for_ticket(...)
    if _provider is not None:
        _provider.<metodo>(...)
    else:
        <ado/client>.<metodo_ADO>(...)
"""
from __future__ import annotations

import pathlib

TICKETS = pathlib.Path(__file__).resolve().parents[1] / "api" / "tickets.py"


def test_tickets_module_imports_cleanly():
    import api.tickets  # noqa: F401


def test_fetch_attachments_has_provider_branch():
    """Branch provider para fetch_attachments presente en tickets.py."""
    text = TICKETS.read_text(encoding="utf-8")
    # El branch usa provider (variable puede ser _provider o provider)
    assert "provider.fetch_attachments(" in text, (
        "F7: branch provider para fetch_attachments no encontrado"
    )


def test_fetch_attachments_fallback_preserved():
    """Fallback ADO client.fetch_attachments sigue presente."""
    text = TICKETS.read_text(encoding="utf-8")
    assert "client.fetch_attachments(" in text


def test_upload_attachment_has_provider_branch():
    """Branch provider para upload_attachment presente en tickets.py."""
    text = TICKETS.read_text(encoding="utf-8")
    assert "_provider.upload_attachment(" in text, (
        "F7: branch provider para upload_attachment no encontrado"
    )


def test_upload_attachment_fallback_preserved():
    """Fallback ADO ado.upload_attachment sigue presente."""
    text = TICKETS.read_text(encoding="utf-8")
    assert "ado.upload_attachment(" in text


def test_link_attachment_has_provider_branch():
    """Branch provider para link_attachment presente en tickets.py."""
    text = TICKETS.read_text(encoding="utf-8")
    assert "_provider.link_attachment(" in text, (
        "F7: branch provider para link_attachment no encontrado"
    )


def test_link_attachment_fallback_preserved():
    """Fallback ADO link_attachment_to_work_item sigue presente."""
    text = TICKETS.read_text(encoding="utf-8")
    assert "ado.link_attachment_to_work_item(" in text
