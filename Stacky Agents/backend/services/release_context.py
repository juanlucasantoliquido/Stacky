"""
FA-07 — Schedule & release context injection.

Inyecta en el contexto del agente: próxima fecha de release, días restantes,
nivel de freeze, y política de agente activa (ej: "sólo crítico").

Fuente: variables de entorno o tabla `release_config` (editable por proyecto).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class ReleaseInfo:
    next_release: str | None    # ISO date
    freeze_date: str | None     # ISO date
    days_to_release: int | None
    days_to_freeze: int | None
    policy: str                  # "normal" | "soft-freeze" | "hard-freeze"

    def to_dict(self) -> dict:
        return {
            "next_release": self.next_release,
            "freeze_date": self.freeze_date,
            "days_to_release": self.days_to_release,
            "days_to_freeze": self.days_to_freeze,
            "policy": self.policy,
        }

    def to_block_content(self) -> str:
        lines: list[str] = []
        if self.next_release:
            suffix = f"(en {self.days_to_release}d)" if self.days_to_release is not None else ""
            lines.append(f"- **Próxima release:** {self.next_release} {suffix}")
        if self.freeze_date:
            suffix = f"(en {self.days_to_freeze}d)" if self.days_to_freeze is not None else ""
            lines.append(f"- **Code freeze:** {self.freeze_date} {suffix}")
        policy_labels = {
            "normal": "Normal — no hay restricciones especiales",
            "soft-freeze": "Soft freeze — sólo features críticos, revisión extra requerida",
            "hard-freeze": "Hard freeze — sólo hotfixes bloqueantes, nada de nuevas features",
        }
        lines.append(f"- **Política activa:** {policy_labels.get(self.policy, self.policy)}")
        return "\n".join(lines)


def _days(date_str: str | None) -> int | None:
    if not date_str:
        return None
    try:
        target = date.fromisoformat(date_str)
        return (target - date.today()).days
    except ValueError:
        return None


def _policy(days_to_freeze: int | None) -> str:
    if days_to_freeze is None:
        return "normal"
    if days_to_freeze <= 0:
        return "hard-freeze"
    if days_to_freeze <= 2:
        return "soft-freeze"
    return "normal"


def get_release_info(project: str | None = None) -> ReleaseInfo:
    """Lee env vars por ahora; Fase 5+: tabla release_config por proyecto."""
    next_release = os.getenv("NEXT_RELEASE_DATE")
    freeze_date = os.getenv("RELEASE_FREEZE_DATE")
    days_release = _days(next_release)
    days_freeze = _days(freeze_date)
    policy = _policy(days_freeze)
    return ReleaseInfo(
        next_release=next_release,
        freeze_date=freeze_date,
        days_to_release=days_release,
        days_to_freeze=days_freeze,
        policy=policy,
    )


def build_context_block(project: str | None = None) -> dict | None:
    """Devuelve ContextBlock listo para inyectar. None si no hay config."""
    info = get_release_info(project)
    if not info.next_release and not info.freeze_date:
        return None
    return {
        "id": "release-context-auto",
        "kind": "auto",
        "title": f"Contexto de release ({info.policy})",
        "content": info.to_block_content(),
        "source": {"type": "release", "policy": info.policy},
    }
