"""Plan 74 F3 — Política de épicas (Free vs Premium) para el migrador.

resolve_epic_strategy decide cómo migrar épicas reusando la detección
existente en GitLabTrackerProvider._epics_native (gitlab_provider.py:39).

NO toca gitlab_provider; solo lee el atributo del provider.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EpicStrategy = Literal["premium_native", "free_degrade"]


@dataclass(frozen=True)
class EpicDecision:
    strategy: EpicStrategy
    item_type_for_create: str           # "epic" (premium) o "issue" (free)
    extra_labels: tuple[str, ...]       # ("type::epic",) en free_degrade
    reason: str


def resolve_epic_strategy(dest_provider, policy: str) -> EpicDecision:
    """Decide la estrategia de migración de épicas.

    policy ∈ {'auto', 'premium_native', 'free_degrade'}.
    - auto: lee dest_provider._epics_native (si existe) → premium_native o free_degrade.
    - premium_native: fuerza 'epic' (si luego falla 403, _link_parent lo atrapa internamente).
    - free_degrade: siempre 'issue' + label type::epic.

    Nunca escribe; solo lee el flag del provider.
    """
    if policy == "premium_native":
        return EpicDecision(
            strategy="premium_native",
            item_type_for_create="epic",
            extra_labels=(),
            reason="policy=premium_native forzado",
        )

    if policy == "free_degrade":
        return _free_degrade_decision("policy=free_degrade forzado")

    # policy == "auto" (u otro valor): detectar desde el provider
    epics_native = getattr(dest_provider, "_epics_native", None)
    if epics_native:
        return EpicDecision(
            strategy="premium_native",
            item_type_for_create="epic",
            extra_labels=(),
            reason="auto: dest_provider._epics_native=True (licencia Premium detectada)",
        )

    return _free_degrade_decision("auto: dest_provider._epics_native=False o ausente (default seguro)")


def _free_degrade_decision(reason: str) -> EpicDecision:
    return EpicDecision(
        strategy="free_degrade",
        item_type_for_create="issue",
        extra_labels=("type::epic",),
        reason=reason,
    )
