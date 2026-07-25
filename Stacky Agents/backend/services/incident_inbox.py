"""Plan 238 F1 -- Nucleo PURO de la bandeja de incidencias.

Sin web, sin ORM, sin I/O: solo funciones deterministas sobre dicts.
Fuente UNICA de verdad de "que es una incidencia" y "que estado esta abierto".
"""
from __future__ import annotations

# Espejo EXACTO de INCIDENT_TYPES en frontend/src/utils/workItemTypeColor.ts:34.
DEFAULT_INCIDENT_TYPES: tuple[str, ...] = ("issue", "bug")

# Espejo EXACTO de CLOSED_STATES en frontend/src/pages/TicketBoard.tsx:82 y de
# _CLOSED_STATES en backend/services/ticket_assigner.py:41.
# Cubre tambien GitLab: sus estados son "opened"/"closed" y "closed" cae aca
# por comparacion case-insensitive contra "Closed".
DEFAULT_CLOSED_STATES: tuple[str, ...] = (
    "Done", "Closed", "Resolved", "Removed", "Completed",
)

# Tope duro de filas devueltas por la bandeja (P7).
MAX_ITEMS: int = 1000


def normalize(value: str | None) -> str:
    """'  Done ' -> 'done'. None/no-str -> ''."""
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _clean_string_list(raw) -> tuple[str, ...] | None:
    """Lista de strings no vacia -> tupla de strings ya stripeados. Si no lo es
    (None, no-list, vacia, con elementos no-str o todos vacios) devuelve None
    para que el caller caiga al siguiente nivel de precedencia. NUNCA lanza."""
    if not isinstance(raw, list):
        return None
    out = [v.strip() for v in raw if isinstance(v, str) and v.strip()]
    return tuple(out) if out else None


def resolve_incident_types(profile: dict | None) -> tuple[tuple[str, ...], str]:
    """(tipos_normalizados, fuente). Ver Plan 238 seccion 4.1.1."""
    if isinstance(profile, dict):
        section = profile.get("incident_inbox")
        if isinstance(section, dict):
            explicit = _clean_string_list(section.get("incident_types"))
            if explicit is not None:
                return tuple(normalize(v) for v in explicit), "profile_incident_inbox"
    return DEFAULT_INCIDENT_TYPES, "default"


def resolve_closed_states(profile: dict | None) -> tuple[tuple[str, ...], str]:
    """(estados_cerrados_tal_cual, fuente). Ver Plan 238 seccion 4.1.2.

    CONTRATO CON EL PLAN 216: la key `state_flow.closed_states` es ADITIVA y
    OPCIONAL. Si el plan 216 aterriza sin ella, esta funcion cae al default y el
    comportamiento es identico al del tablero de hoy.
    """
    if isinstance(profile, dict):
        section = profile.get("incident_inbox")
        if isinstance(section, dict):
            explicit = _clean_string_list(section.get("closed_states"))
            if explicit is not None:
                return explicit, "profile_incident_inbox"
        state_flow = profile.get("state_flow")
        if isinstance(state_flow, dict):
            from_216 = _clean_string_list(state_flow.get("closed_states"))
            if from_216 is not None:
                return from_216, "profile_state_flow"
    return DEFAULT_CLOSED_STATES, "default"


def is_incident_type(work_item_type: str | None, types: tuple[str, ...]) -> bool:
    """True si el tipo del work item esta en el conjunto de tipos-incidencia."""
    norm = normalize(work_item_type)
    if not norm:
        return False
    return norm in {normalize(t) for t in types}


def is_open_state(state: str | None, closed_states: tuple[str, ...]) -> bool:
    """True si el estado NO esta en el conjunto de estados cerrados.

    Estado vacio/None => ABIERTA (un item sin estado sincronizado es trabajo
    pendiente, no trabajo terminado: nunca se oculta silenciosamente).
    """
    norm = normalize(state)
    if not norm:
        return True
    return norm not in {normalize(s) for s in closed_states}


def normalize_scope(raw: str | None) -> str:
    """'all'/'todas' -> 'all'; cualquier otra cosa (incluido None) -> 'open'."""
    norm = normalize(raw)
    return "all" if norm in {"all", "todas"} else "open"


def build_counts(total: int, closed: int) -> dict[str, int]:
    """Counts a partir de dos agregados SQL. Nunca negativo. Ver Plan 238 4.2."""
    total = max(0, int(total))
    closed = max(0, min(int(closed), total))
    return {"open": total - closed, "closed": closed, "total": total}
