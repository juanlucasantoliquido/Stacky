"""
ticket_assigner.py — Recomendador de asignacion de tickets a personas.

Algoritmo deterministico (sin LLM). Cuatro componentes:
  - load_score       (40%): inverso de la carga activa ponderada por prioridad
  - type_affinity    (25%): match entre tipo del ticket y historial de la persona
  - area_affinity    (20%): match entre area_path del ticket y areas historicas
  - throughput_score (15%): tasa de cierre en los ultimos 90 dias

Contrato: advisory_only siempre True. publish_requires_human_approval siempre True.
El operador elige y confirma antes de PATCH a ADO.

P6-Recom: version 2026-05-19
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from db import session_scope
from models import Ticket, User

logger = logging.getLogger("stacky_agents.ticket_assigner")

# Pesos del algoritmo (deben sumar 1.0)
_WEIGHT_LOAD = 0.40
_WEIGHT_TYPE = 0.25
_WEIGHT_AREA = 0.20
_WEIGHT_THROUGHPUT = 0.15

# Pesos de prioridad para calcular la carga ponderada
_PRIORITY_WEIGHTS: dict[int | None, int] = {1: 4, 2: 3, 3: 2, 4: 1}
_DEFAULT_PRIORITY_WEIGHT = 2

# Estados considerados "activos" (carga actual de la persona)
_ACTIVE_STATES = {"Active", "In Progress", "En Progreso", "Committed", "New"}

# Estados considerados "cerrados" (para calcular throughput)
_CLOSED_STATES = {"Done", "Closed", "Resolved", "Removed", "Completed"}

# Ventana de historial para throughput (dias)
_THROUGHPUT_WINDOW_DAYS = 90


def _load_users_from_db(session) -> list[User]:
    """Carga todos los usuarios que tienen ado_unique_name configurado."""
    return (
        session.query(User)
        .filter(User.ado_unique_name.isnot(None))
        .all()
    )


def _load_tickets_for_user(session, ado_unique_name: str) -> list[Ticket]:
    """Carga todos los tickets asignados a la persona en la BD local."""
    return (
        session.query(Ticket)
        .filter(Ticket.assigned_to_ado == ado_unique_name)
        .all()
    )


def _parse_json_field(raw: str | None) -> list:
    if not raw:
        return []
    try:
        result = json.loads(raw)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _compute_load_score(
    active_tickets: list[Ticket],
    max_active_tickets: int,
) -> tuple[float, float, bool]:
    """Calcula el load_score y el porcentaje de carga actual.

    Returns:
        (load_score, load_pct, overloaded)
    """
    max_peso = _PRIORITY_WEIGHTS.get(1, 4)  # peso maximo (prioridad 1)
    max_carga_ponderada = max_active_tickets * max_peso

    carga_ponderada = sum(
        _PRIORITY_WEIGHTS.get(t.priority, _DEFAULT_PRIORITY_WEIGHT)
        for t in active_tickets
    )

    if max_carga_ponderada <= 0:
        return 0.0, 100.0, True

    load_pct = min(100.0, round(carga_ponderada / max_carga_ponderada * 100, 1))
    overloaded = carga_ponderada >= max_carga_ponderada
    load_score = max(0.0, 1.0 - carga_ponderada / max_carga_ponderada)
    return round(load_score, 4), load_pct, overloaded


def _compute_type_affinity(
    all_tickets: list[Ticket],
    target_type: str | None,
) -> tuple[float, list[str], bool]:
    """Calcula la afinidad de tipo de ticket.

    Returns:
        (type_affinity_score, top_types, matched)
    """
    if not target_type or not all_tickets:
        return 0.0, [], False

    type_count: dict[str, int] = {}
    for t in all_tickets:
        wt = t.work_item_type or "Unknown"
        type_count[wt] = type_count.get(wt, 0) + 1

    total = len(all_tickets)
    target_count = type_count.get(target_type, 0)
    affinity_raw = target_count / total if total > 0 else 0.0

    # Boost si es especialista: cap a 1.0
    score = min(affinity_raw * 2, 1.0)

    top_types = sorted(type_count, key=lambda k: type_count[k], reverse=True)[:3]
    matched = target_type in type_count

    return round(score, 4), top_types, matched


def _compute_area_affinity(
    area_paths_json: str | None,
    target_area: str | None,
) -> tuple[float, list[str]]:
    """Calcula la afinidad de area (comparacion de prefijos de ruta ADO).

    Returns:
        (area_affinity_score, matched_areas)
    """
    if not target_area:
        return 0.5, []  # sin info de area, score neutro

    user_areas = _parse_json_field(area_paths_json)
    if not user_areas:
        return 0.0, []

    matched = []
    for ua in user_areas:
        # Match exacto o prefijo (sub-area)
        if target_area == ua or target_area.startswith(ua) or ua.startswith(target_area):
            matched.append(ua)

    if matched:
        score = 1.0
    else:
        score = 0.0

    return round(score, 4), matched


def _compute_throughput_score(
    all_tickets: list[Ticket],
) -> float:
    """Calcula la tasa de cierre en los ultimos _THROUGHPUT_WINDOW_DAYS dias.

    Returns:
        throughput_score en [0, 1]
    """
    cutoff = datetime.utcnow() - timedelta(days=_THROUGHPUT_WINDOW_DAYS)
    recent = [t for t in all_tickets if t.last_synced_at and t.last_synced_at >= cutoff]

    if not recent:
        return 0.5  # sin historial reciente, score neutro

    closed_count = sum(1 for t in recent if (t.ado_state or "") in _CLOSED_STATES)
    score = closed_count / len(recent)
    return round(score, 4)


def _build_reason(
    load_pct: float,
    type_matched: bool,
    target_type: str | None,
    area_matched: list[str],
    overloaded: bool,
    recommendation_flags: list[str],
) -> str:
    """Construye una razon legible para la recomendacion."""
    parts = []
    if overloaded:
        parts.append(f"Carga alta ({load_pct:.0f}%) — puede estar sobrecargado")
    else:
        parts.append(f"Carga {load_pct:.0f}%")

    if type_matched and target_type:
        parts.append(f"tiene experiencia en {target_type}")
    elif target_type:
        parts.append(f"sin historial en {target_type}")

    if area_matched:
        parts.append(f"area coincide ({area_matched[0]})")
    else:
        parts.append("sin coincidencia de area")

    return ", ".join(parts)


def compute_recommendations(
    ticket: Ticket,
    filters: dict | None = None,
) -> dict:
    """Calcula recomendaciones de asignacion para un ticket.

    filters (opcionales):
      max_load_pct: int (default 80) — excluye candidatos con carga mayor
      only_skill: str | None — filtra por skill en skills_json
      only_area_path: str | None — filtra por area exacta
      exclude_ado_unique_names: list[str] — excluye estos usuarios

    Returns: dict con el contrato P6-Recom.
    """
    filters = filters or {}
    max_load_pct = int(filters.get("max_load_pct") or 80)
    only_skill = filters.get("only_skill")
    only_area_path = filters.get("only_area_path") or ticket.area_path if hasattr(ticket, "area_path") else filters.get("only_area_path")
    exclude_names: list[str] = list(filters.get("exclude_ado_unique_names") or [])

    scored_at = datetime.utcnow().isoformat()
    candidates: list[dict] = []
    excluded: list[dict] = []

    with session_scope() as session:
        users = _load_users_from_db(session)

        if not users:
            return {
                "ok": True,
                "ticket_ado_id": ticket.ado_id,
                "scored_at": scored_at,
                "candidates": [],
                "excluded": [],
                "advisory_only": True,
                "publish_requires_human_approval": True,
                "warning": "no_users_configured",
            }

        target_type = ticket.work_item_type
        # area_path no esta en el modelo Ticket actual, se pasa si esta disponible
        target_area: str | None = None

        for user in users:
            if not user.ado_unique_name:
                continue

            if user.ado_unique_name in exclude_names:
                excluded.append({
                    "ado_unique_name": user.ado_unique_name,
                    "reason": "excluded_by_filter",
                    "load_pct": 0.0,
                })
                continue

            # Filtro por skill
            if only_skill:
                user_skills = _parse_json_field(user.skills_json)
                if only_skill.lower() not in [s.lower() for s in user_skills]:
                    excluded.append({
                        "ado_unique_name": user.ado_unique_name,
                        "reason": f"skill_filter:{only_skill}",
                        "load_pct": 0.0,
                    })
                    continue

            # Cargar tickets del usuario
            user_tickets = _load_tickets_for_user(session, user.ado_unique_name)
            active_tickets = [t for t in user_tickets if (t.ado_state or "") in _ACTIVE_STATES]

            # Calcular sub-scores
            load_score, load_pct, overloaded = _compute_load_score(
                active_tickets, user.max_active_tickets or 5
            )
            type_score, top_types, type_matched = _compute_type_affinity(user_tickets, target_type)
            area_score, matched_areas = _compute_area_affinity(user.area_paths_json, target_area)
            throughput = _compute_throughput_score(user_tickets)

            # Filtro por carga maxima
            if load_pct > max_load_pct:
                excluded.append({
                    "ado_unique_name": user.ado_unique_name,
                    "reason": "overloaded",
                    "load_pct": load_pct,
                })
                continue

            # Score compuesto
            score = (
                _WEIGHT_LOAD * load_score
                + _WEIGHT_TYPE * type_score
                + _WEIGHT_AREA * area_score
                + _WEIGHT_THROUGHPUT * throughput
            )
            score = round(score, 4)

            recommendation_flags: list[str] = []
            if overloaded:
                recommendation_flags.append("overloaded")
            if not type_matched and target_type:
                recommendation_flags.append("no_type_specialization")
            if not matched_areas and target_area:
                recommendation_flags.append("area_mismatch")

            reason = _build_reason(load_pct, type_matched, target_type, matched_areas, overloaded, recommendation_flags)

            candidates.append({
                "ado_unique_name": user.ado_unique_name,
                "display_name": user.ado_display_name or user.name or user.ado_unique_name,
                "score": score,
                "rank": 0,  # se asigna despues de ordenar
                "overloaded": overloaded,
                "load_pct": load_pct,
                "active_tickets": len(active_tickets),
                "active_tickets_detail": [
                    {"ado_id": t.ado_id, "priority": t.priority, "state": t.ado_state}
                    for t in active_tickets[:5]
                ],
                "type_affinity": {
                    "score": type_score,
                    "top_types": top_types,
                    "match": type_matched,
                },
                "area_affinity": {
                    "score": area_score,
                    "matched_areas": matched_areas,
                },
                "throughput_score": throughput,
                "reason": reason,
                "recommendation_flags": recommendation_flags,
            })

    # Ordenar por score descendente y asignar rank
    candidates.sort(key=lambda c: c["score"], reverse=True)
    for i, c in enumerate(candidates):
        c["rank"] = i + 1

    return {
        "ok": True,
        "ticket_ado_id": ticket.ado_id,
        "scored_at": scored_at,
        "candidates": candidates,
        "excluded": excluded,
        "advisory_only": True,
        "publish_requires_human_approval": True,
    }


def sync_users_from_ado_history() -> dict:
    """Puebla la tabla users con los asignados distintos encontrados en tickets.

    No sobreescribe campos ya configurados manualmente (skills, area_paths, max_active_tickets).
    Returns: { "created": N, "updated": M, "total": K }
    """
    created = 0
    updated = 0
    with session_scope() as session:
        # Obtener todos los assigned_to_ado distintos y no nulos
        from sqlalchemy import distinct
        rows = (
            session.query(distinct(Ticket.assigned_to_ado))
            .filter(Ticket.assigned_to_ado.isnot(None))
            .all()
        )
        unique_names = [r[0] for r in rows if r[0]]

        for uname in unique_names:
            existing = (
                session.query(User)
                .filter(User.ado_unique_name == uname)
                .first()
            )
            if existing is None:
                # Crear nuevo usuario con el ado_unique_name como email y nombre
                user = User(
                    email=uname,
                    name=uname.split("@")[0] if "@" in uname else uname,
                    ado_unique_name=uname,
                    ado_display_name=None,
                    max_active_tickets=5,
                )
                session.add(user)
                created += 1
            else:
                # Solo actualizar si ado_unique_name no estaba seteado
                if not existing.ado_unique_name:
                    existing.ado_unique_name = uname
                    updated += 1

    return {"created": created, "updated": updated, "total": created + updated}


def get_user_stats(ado_unique_name: str | None = None) -> list[dict]:
    """Devuelve estadisticas de tickets por usuario.

    Para cada usuario con ado_unique_name, devuelve:
    - Tickets actuales por estado (de la tabla tickets)
    - Tickets historicos por estado (de ticket_state_history)

    Si ado_unique_name se especifica, filtra solo ese usuario.
    """
    from models import TicketStateHistory
    from sqlalchemy import func

    result: list[dict] = []

    with session_scope() as session:
        users_q = session.query(User).filter(User.ado_unique_name.isnot(None))
        if ado_unique_name:
            users_q = users_q.filter(User.ado_unique_name == ado_unique_name)
        users = users_q.all()

        for user in users:
            uname = user.ado_unique_name

            # Conteo actual: agrupar por ado_state en tickets actuales
            current_rows = (
                session.query(Ticket.ado_state, func.count(Ticket.id))
                .filter(Ticket.assigned_to_ado == uname)
                .group_by(Ticket.ado_state)
                .all()
            )
            current_by_state = {
                (state or "Unknown"): count
                for state, count in current_rows
            }

            # Conteo historico: agrupar por new_state en ticket_state_history
            historical_rows = (
                session.query(TicketStateHistory.new_state, func.count(TicketStateHistory.id))
                .filter(TicketStateHistory.assigned_to_ado == uname)
                .group_by(TicketStateHistory.new_state)
                .all()
            )
            historical_by_state = {
                (state or "Unknown"): count
                for state, count in historical_rows
            }

            total_current = sum(current_by_state.values())
            total_historical = sum(historical_by_state.values())

            result.append({
                "ado_unique_name": uname,
                "display_name": user.ado_display_name or user.name or uname,
                "current_tickets": {
                    "total": total_current,
                    "by_state": current_by_state,
                },
                "historical_tickets": {
                    "total": total_historical,
                    "by_state": historical_by_state,
                },
                "max_active_tickets": user.max_active_tickets,
                "skills": _parse_json_field(user.skills_json),
                "area_paths": _parse_json_field(user.area_paths_json),
            })

    return result


__all__ = [
    "compute_recommendations",
    "sync_users_from_ado_history",
    "get_user_stats",
]
