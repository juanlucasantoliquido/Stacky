"""Plan 133 F2 — Predicados de negocio por agent_type antes de lanzar el run.

Complementa (NO reemplaza) el gate de infraestructura G0.1
(services/run_preflight.py). Fail-closed ante hechos deterministas del
snapshot local (tipo/estado), fail-open ante errores de red (comentarios).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger("stacky.services.business_preflight")

BLOCKER_MARKER = "🚫 BLOQUEANTE TÉCNICO"  # espejo de FunctionalAnalyst.agent.md:119 y :294


@dataclass
class BusinessPreflightResult:
    ok: bool
    mode: str | None = None            # "A" | "B" | None
    reason: str = ""                   # legible, en español, accionable
    check: str | None = None           # id máquina del predicado fallido
    epic_ado_id: int | None = None     # Modo A: ado_id de la épica
    validated_state: str | None = None  # estado del ticket validado
    blocker: dict | None = None        # Modo B: {author, date, excerpt}
    warnings: list[str] = field(default_factory=list)


def _most_recent_comment(comments: list[dict]) -> dict | None:
    """El comentario con la fecha (string ISO) más reciente. None si la lista está vacía."""
    if not comments:
        return None
    return max(comments, key=lambda c: (c.get("date") or ""))


def _evaluate_functional(
    *,
    ado_id: int,
    work_item_type: str,
    ado_state: str,
    stacky_project_name: str | None,
    tracker_project: str | None,
) -> BusinessPreflightResult:
    from config import config

    # Cargar client-profile con el MISMO loader que usa _inject_client_profile_block
    # (context_enrichment.py:110): load_client_profile → get_project_tracker_type →
    # merge_with_defaults. Mismo fallback que build_client_profile_block/enrich_blocks:
    # stacky_project_name si está resuelto, si no el tracker_project del ticket.
    # Defensivo ante cualquier error (profile inaccesible).
    input_states: list = []
    blocked_states: list | None = None
    project_name = stacky_project_name or tracker_project
    try:
        from services.client_profile import (
            get_project_tracker_type,
            load_client_profile,
            merge_with_defaults,
        )

        persisted = load_client_profile(project_name) if project_name else None
        tracker_type = get_project_tracker_type(project_name) if project_name else None
        profile = merge_with_defaults(
            persisted if isinstance(persisted, dict) else {}, tracker_type
        )
        fsm = (profile.get("tracker_state_machine") or {}).get("functional") or {}
        raw_input_states = fsm.get("input_states")
        input_states = raw_input_states if isinstance(raw_input_states, list) else []
        raw_blocked_states = fsm.get("blocked_states")
        blocked_states = raw_blocked_states if isinstance(raw_blocked_states, list) else None
    except Exception as exc:  # noqa: BLE001 — profile inaccesible no bloquea
        logger.warning("business_preflight — no se pudo cargar client-profile: %s", exc)

    # Modo A — Epic en un estado de entrada válido (o sin estados declarados).
    if work_item_type == "Epic" and (not input_states or ado_state in input_states):
        return BusinessPreflightResult(
            ok=True, mode="A", epic_ado_id=ado_id, validated_state=ado_state,
        )

    # Modo B — comentario bloqueante en el ÚLTIMO comentario (por fecha).
    try:
        from services import ado_read_cache
        from services.project_context import build_ado_client

        client = build_ado_client(
            project_name=stacky_project_name, tracker_project=tracker_project
        )
        ttl = int(getattr(config, "STACKY_ADO_READ_CACHE_TTL_SEC", 0) or 0)
        comments = ado_read_cache.get_or_fetch(
            ("run_comments", ado_id),
            lambda: client.fetch_comments(ado_id, top=30),
            ttl_sec=ttl,
        )
    except Exception as exc:  # noqa: BLE001 — fail-open ante red (§3.3)
        return BusinessPreflightResult(
            ok=True,
            mode=None,
            warnings=[f"comentarios inaccesibles: {exc} — el agente hará el cross-check"],
        )

    from services.ado_context import _html_to_text

    most_recent = _most_recent_comment(comments or [])
    marker_present = most_recent is not None and BLOCKER_MARKER in _html_to_text(
        most_recent.get("text") or ""
    )
    if marker_present:
        state_ok = True
        if blocked_states:
            state_ok = ado_state in blocked_states
        if state_ok:
            text = _html_to_text(most_recent.get("text") or "")
            return BusinessPreflightResult(
                ok=True,
                mode="B",
                blocker={
                    "author": most_recent.get("author"),
                    "date": most_recent.get("date"),
                    "excerpt": text[:500],
                },
            )

    reason = (
        f"FunctionalAnalyst requiere: (Modo A) una Épica en estado {input_states}, o "
        f"(Modo B) un work item cuyo ÚLTIMO comentario contenga '{BLOCKER_MARKER}'. "
        f"El ticket ADO-{ado_id} es {work_item_type} en estado '{ado_state}' y su "
        "último comentario no tiene el marcador. Cambiá el estado/tipo del ticket o "
        "agregá el comentario bloqueante en ADO y relanzá."
    )
    return BusinessPreflightResult(ok=False, check="functional_prereqs_unmet", reason=reason)


# Registro extensible por agent_type (v1: solo functional). Agregar más
# predicados acá NO requiere tocar evaluate().
_PREDICATES: dict[str, Callable[..., BusinessPreflightResult]] = {
    "functional": _evaluate_functional,
}


def evaluate(*, ticket_id: int, agent_type: str) -> BusinessPreflightResult:
    """Evalúa predicados de negocio para agent_type. NUNCA levanta excepción.

    Sin predicados registrados para ese agent_type, flag OFF, ticket
    inexistente, o ado_id None/negativo (sentinels -1..-8) → ok=True (identidad).
    """
    from config import config

    if not getattr(config, "STACKY_BUSINESS_PREFLIGHT_ENABLED", False):
        return BusinessPreflightResult(ok=True, reason="preflight_off")

    if agent_type not in _PREDICATES:
        return BusinessPreflightResult(ok=True, reason="not_applicable")

    try:
        from db import session_scope
        from models import Ticket

        with session_scope() as session:
            ticket = session.query(Ticket).filter_by(id=ticket_id).first()
            if ticket is None:
                return BusinessPreflightResult(ok=True, reason="not_applicable")
            ado_id = ticket.ado_id
            if not ado_id or ado_id <= 0:
                return BusinessPreflightResult(ok=True, reason="not_applicable")
            work_item_type = ticket.work_item_type or ""
            ado_state = ticket.ado_state or ""
            stacky_project_name = ticket.stacky_project_name
            tracker_project = ticket.project

        return _PREDICATES[agent_type](
            ado_id=ado_id,
            work_item_type=work_item_type,
            ado_state=ado_state,
            stacky_project_name=stacky_project_name,
            tracker_project=tracker_project,
        )
    except Exception as exc:  # noqa: BLE001 — el preflight nunca bloquea por su propio error
        logger.warning("business_preflight.evaluate falló (fail-open): %s", exc)
        return BusinessPreflightResult(ok=True, mode=None, warnings=[f"preflight error: {exc}"])
