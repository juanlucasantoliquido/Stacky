"""Plan 70 F12 -- Centinela: _ado_client_for_ticket solo en definition + else/fallback.

OBJETIVO: asegurar que no se introduzcan call sites "directos" (fuera de un
branch fallback) de _ado_client_for_ticket en api/tickets.py. Cada site nuevo
debe ser un fallback explícito cuando el provider no está disponible.

ALLOWLIST de files api/ que pueden importar AdoClient (pre-existentes a Plan 70):
  - tickets.py   → usa _ado_client_for_ticket como fallback gateado
  - pm.py        → Project Manager: usa _new_client ADO-only (scope diferente)

ALLOWLIST de sites ADO-only en tickets.py APROBADOS (no migrados):
  - def _ado_client_for_ticket  → DEFINITION (fallback function)
  - idempotency_ado             → idempotencia ADO-especifica
  - eq_ado                      → equivalencia ADO-especifica
  - _rev_client                 → learning System.Rev, ADO-only
  - ado = _ado_client_for_ticket → init fallback ADO create_child_task
  - _sync_via_provider_or_ado   → funcion-gating de sync con fallback ADO
  - or _ado_client_for_ticket   → operador "or" como fallback explícito

CONTROL 1: api/*.py no importa AdoClient fuera de la allowlist de archivos
CONTROL 2: api/*.py no tiene '-> AdoClient' fuera de tickets.py + definition
CONTROL 3: _ado_client_for_ticket( en tickets.py solo en def/else/fallback
"""
from __future__ import annotations

import pathlib
import re

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_TICKETS = _BACKEND / "api" / "tickets.py"
_API_DIR = _BACKEND / "api"

# Archivos api/ que TIENEN PERMISO de importar AdoClient (pre-existentes a Plan 70)
_ADOCLIENT_IMPORT_ALLOWLIST = {
    "tickets.py",  # usa _ado_client_for_ticket como fallback gateado
    "pm.py",       # project manager, scope diferente — ADO-only aprobado
}

# Archivos api/ que TIENEN PERMISO de usar '-> AdoClient'
_ADOCLIENT_RETURN_ALLOWLIST = {
    "pm.py",  # _new_client() → AdoClient aprobado pre-Plan70
}


# ---------------------------------------------------------------------------
# CONTROL 1: solo archivos allowlisteados pueden importar AdoClient en api/
# ---------------------------------------------------------------------------

def test_no_new_adoclient_import_in_api():
    """CONTROL 1: solo tickets.py y pm.py pueden importar AdoClient en api/."""
    violations = []
    for fpath in _API_DIR.glob("*.py"):
        if fpath.name in _ADOCLIENT_IMPORT_ALLOWLIST:
            continue
        text = fpath.read_text(encoding="utf-8")
        matches = re.findall(
            r"(?:import AdoClient|from\s+\S+\s+import\s+[^\n]*AdoClient)", text
        )
        if matches:
            violations.append((fpath.name, matches))
    assert not violations, (
        "F12-C1: archivo(s) api/ NUEVOS importan AdoClient — "
        "usar _provider_for_ticket en su lugar:\n"
        + "\n".join(f"  {name}: {m}" for name, m in violations)
    )


# ---------------------------------------------------------------------------
# CONTROL 2: '-> AdoClient' en api/ solo en files allowlisteados
# ---------------------------------------------------------------------------

def test_no_new_adoclient_return_type_in_api():
    """CONTROL 2: '-> AdoClient' solo en pm.py y tickets.py definition."""
    violations = []
    for fpath in _API_DIR.glob("*.py"):
        text = fpath.read_text(encoding="utf-8")
        lines = text.splitlines()
        for i, line in enumerate(lines, start=1):
            if "-> AdoClient" not in line:
                continue
            # tickets.py: solo permite la definition de _ado_client_for_ticket
            if fpath.name == "tickets.py":
                if "_ado_client_for_ticket" in line:
                    continue
                violations.append((fpath.name, i, line.strip()))
                continue
            # Otros archivos en allowlist
            if fpath.name in _ADOCLIENT_RETURN_ALLOWLIST:
                continue
            violations.append((fpath.name, i, line.strip()))
    assert not violations, (
        "F12-C2: '-> AdoClient' en api/ FUERA de allowlist:\n"
        + "\n".join(f"  {name}:{i}: {txt}" for name, i, txt in violations)
        + "\n\nUsar TrackerProvider o agregar al allowlist si es ADO-only por diseno."
    )


# ---------------------------------------------------------------------------
# CONTROL 3: _ado_client_for_ticket( en tickets.py solo en def/else/fallback
# ---------------------------------------------------------------------------

def test_ado_client_for_ticket_only_in_allowed_positions():
    """CONTROL 3: _ado_client_for_ticket( en tickets.py en posiciones permitidas.

    Cada aparicion DEBE estar en una de estas categorias:
      A) Es la linea de definicion: 'def _ado_client_for_ticket('
      B) El contexto de 20 lineas hacia arriba contiene 'else:' o signals de
         gating/fallback (provider check, allowlist ADO-only).
    """
    text = _TICKETS.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Signals que indican que el call site es parte de un fallback o gating
    fallback_signals = [
        "else:",
        "else :",
        "provider is None",
        "_provider_for_ticket",
        "provider is not None",
        "or _ado_client_for_ticket",   # operador "or" como fallback
        "_sync_via_provider_or_ado",   # funcion-gating aprobada
        "idempotency_ado",
        "eq_ado",
        "_rev_client",
        "ado = _ado_client_for_ticket",
    ]

    violations = []
    for i, line in enumerate(lines, start=1):
        if "_ado_client_for_ticket(" not in line:
            continue

        # A) Linea de definicion
        if "def _ado_client_for_ticket(" in line:
            continue

        # B) Contexto de 20 lineas (captura la funcion padre en la mayoria de casos)
        start = max(0, i - 21)
        context_window = "\n".join(lines[start: i + 1])

        if any(sig in context_window for sig in fallback_signals):
            continue

        violations.append((i, line.strip()))

    assert not violations, (
        "F12-C3: _ado_client_for_ticket( encontrado FUERA de definicion/else/fallback:\n"
        + "\n".join(f"  tickets.py:{lineno}: {txt}" for lineno, txt in violations)
        + "\n\nCada nuevo call site debe estar en un branch 'else:' "
        "despues de un check _provider_for_ticket."
    )


def test_ado_client_for_ticket_definition_still_exists():
    """Sanity: la funcion _ado_client_for_ticket sigue definida (no fue eliminada)."""
    text = _TICKETS.read_text(encoding="utf-8")
    assert "def _ado_client_for_ticket(" in text, (
        "F12: _ado_client_for_ticket fue eliminada — es necesaria como fallback ADO"
    )
