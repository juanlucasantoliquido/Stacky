"""Plan 154 F2 — Factory canónica de payloads pending-task para tests.

Única fuente de verdad de un payload VÁLIDO según el contrato de intake:
los 9 campos de _PENDING_TASK_REQUIRED_FIELDS (api/tickets.py). Cualquier
test que necesite un pending-task.json válido usa esta factory; los tests
que prueban payloads INVÁLIDOS los construyen a mano a propósito.
"""
from __future__ import annotations


def make_intake_payload(
    *,
    rf_id: str,
    epic_ado_id: int,
    title: str = "test",
    status: str = "pending_manual_creation",
    generated_at: str = "2026-05-16T00:00:00Z",
    **overrides,
) -> dict:
    """Payload pending-task válido con los 9 campos canónicos.

    epic_ado_id debe ser el ADO id REAL del epic del test (la regla
    anti-ordinal del intake lo valida contra _intake_valid_ado_ids).
    overrides pisa cualquier campo (incluso para romperlo a propósito).
    """
    payload = {
        "rf_id": rf_id,
        "title": title,
        "status": status,
        "generated_at": generated_at,
        "generated_by": "pytest-intake-fixture",
        "epic_id": int(epic_ado_id),
        "description_html": "<p>generado por tests (plan 154)</p>",
        "plan_de_pruebas_path": "outputs/plan_de_pruebas.md",
        "parent_link_type": "System.LinkTypes.Hierarchy-Reverse",
    }
    payload.update(overrides)
    return payload
