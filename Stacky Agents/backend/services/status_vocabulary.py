"""Fuente ÚNICA de verdad del vocabulario de estados de Stacky (Plan 144 F0).

Antes existían dos definiciones divergentes:
  - agent_completion.TERMINAL_STATUSES  (con needs_review)
  - ticket_status.VALID_STATUSES        (sin needs_review)  → set_status rechazaba needs_review.

Este módulo las reconcilia. NO depende de db/models (import barato, sin ciclos)."""
from __future__ import annotations

# Estados terminales que la capa de completion puede producir para un run.
TERMINAL_STATUSES = frozenset({"completed", "error", "cancelled", "needs_review"})

# Estados NO terminales válidos a nivel ticket (stacky_status).
NON_TERMINAL_TICKET_STATUSES = frozenset({"idle", "running"})

# Vocabulario válido COMPLETO de stacky_status (lo que set_status acepta).
# Invariante garantizado por test de contrato: TERMINAL_STATUSES ⊆ VALID_TICKET_STATUSES.
VALID_TICKET_STATUSES = NON_TERMINAL_TICKET_STATUSES | TERMINAL_STATUSES
