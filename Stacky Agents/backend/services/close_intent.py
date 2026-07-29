"""Plan 270 F0 — Traducción pura de la intención de cierre por tracker.

Sin I/O, sin ORM, sin red: sólo funciones deterministas sobre strings y dicts.
"""
from __future__ import annotations

from dataclasses import dataclass

# Estados de cierre del vocabulario ADO que la bandeja ofrece hoy.
# Espejo EXACTO de FINISH_STATE_SUGGESTIONS en
# frontend/src/incidents/incidentInboxActionsModel.ts:18
ADO_CLOSE_STATES: tuple[str, ...] = ("Done", "Closed", "Resolved")

# Claves lógicas que services/gitlab_provider.py:94-102 (_state_map_for_gitlab)
# realmente entiende. Cualquier otra cosa cae en el else que emite "reopen".
GITLAB_LOGICAL_STATES: tuple[str, ...] = (
    "functional", "accepted", "rejected", "in_progress",
)
# C8 — Claves lógicas cuyo mapping tiene closed=True. Son DOS, no una:
# gitlab_provider.py:99 ("accepted") y :100 ("rejected").
GITLAB_CLOSING_LOGICAL_STATES: tuple[str, ...] = ("accepted", "rejected")
# Destino CANÓNICO al que se traduce un cierre pedido en vocabulario ADO.
# Se elige "accepted" (no "rejected") porque el operador apretó "Cerrar", que
# significa "esto quedó resuelto", no "esto se descarta".
GITLAB_CLOSE_STATE: str = "accepted"

_ADO_TRACKER_TYPES: frozenset[str] = frozenset({"", "azure_devops"})


@dataclass(frozen=True)
class CloseTarget:
    """Instrucción resuelta para UN tracker concreto."""
    tracker_type: str      # "azure_devops" | "gitlab"
    native_state: str      # lo que se le pasa a update_item_state()
    closes: bool           # True si la intención es dejar el ítem CERRADO
    source: str            # "passthrough" | "mapped" | "already_logical"


def _norm(value: str | None) -> str:
    """Misma normalización que services/incident_inbox.py:23 `normalize`."""
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def is_close_state(state: str | None, closed_states: tuple[str, ...]) -> bool:
    """¿`state` pertenece al conjunto de estados cerrados? Case/space-insensitive.

    Reusa la MISMA normalización que services/incident_inbox.py:23 `normalize`
    para que el tablero y esta capa nunca discrepen.
    """
    norm = _norm(state)
    if not norm:
        return False
    return norm in {_norm(s) for s in closed_states or ()}


def resolve_close_target(
    tracker_type: str | None,
    requested_state: str,
    closed_states: tuple[str, ...],
) -> CloseTarget:
    """Traduce el estado pedido por el operador al nativo del tracker.

    Reglas (en orden):
      1. tracker_type ausente/"azure_devops" -> passthrough EXACTO del string
         pedido (backward-compat byte-idéntico). closes = is_close_state(...).
      2. tracker_type == "gitlab":
         a. si requested_state ya es una clave de GITLAB_LOGICAL_STATES ->
            source="already_logical", native = esa clave, y
            closes = (native in GITLAB_CLOSING_LOGICAL_STATES).   # C8
         b. si is_close_state(requested_state, closed_states) ->
            source="mapped", native = GITLAB_CLOSE_STATE, closes=True.
         c. si no -> ValueError("unmappable_state:<requested>"). NUNCA se
            devuelve un target que termine reabriendo.
      3. cualquier otro tracker_type -> ValueError("unsupported_tracker:<t>").

    IMPORTANTE (C1) — `closed_states` es una tupla PLANA de strings. El
    llamador que la obtiene de services.incident_inbox.resolve_closed_states()
    DEBE desempaquetar la 2-tupla: esa función devuelve (estados, fuente).
    """
    ttype = _norm(tracker_type)

    if ttype in _ADO_TRACKER_TYPES:
        # Regla 1 — passthrough EXACTO: el string va sin transformar.
        raw = requested_state if isinstance(requested_state, str) else ""
        return CloseTarget(
            tracker_type="azure_devops",
            native_state=raw,
            closes=is_close_state(raw, closed_states),
            source="passthrough",
        )

    if ttype == "gitlab":
        pedido = _norm(requested_state)
        # Regla 2.a — ya viene en el vocabulario lógico de GitLab.
        if pedido in {_norm(s) for s in GITLAB_LOGICAL_STATES}:
            return CloseTarget(
                tracker_type="gitlab",
                native_state=pedido,
                closes=pedido in {_norm(s) for s in GITLAB_CLOSING_LOGICAL_STATES},
                source="already_logical",
            )
        # Regla 2.b — es un estado de cierre del vocabulario ADO.
        if is_close_state(requested_state, closed_states):
            return CloseTarget(
                tracker_type="gitlab",
                native_state=GITLAB_CLOSE_STATE,
                closes=True,
                source="mapped",
            )
        # Regla 2.c — NUNCA adivinar: un estado no mapeable no puede terminar
        # emitiendo state_event="reopen" (que es el bug C2 del plan).
        raw = requested_state if isinstance(requested_state, str) else ""
        raise ValueError(f"unmappable_state:{raw}")

    # Regla 3 — tracker sin traductor.
    raise ValueError(f"unsupported_tracker:{tracker_type}")
