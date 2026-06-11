"""H5 — Runaway Guard in-run.

Detecta si un run agéntico supera los límites configurados de turnos o costo.
Dispara UNA SOLA VEZ por instancia (la segunda llamada con el mismo estado
devuelve None para evitar spam de señales al proceso).

Contrato:
  - RunLimits(max_turns=0, max_cost_usd=0.0) = sin límite (ambos desactivados).
  - observe() devuelve None si todo OK; devuelve razón legible la primera vez
    que se excede un límite. Las llamadas posteriores con el mismo estado → None.
  - Sin estado externo, sin I/O, sin dependencias de DB.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RunLimits:
    max_turns: int = 0          # 0 = sin límite
    max_cost_usd: float = 0.0   # 0.0 = sin límite


@dataclass
class RunawayGuard:
    limits: RunLimits
    _fired: bool = field(default=False, init=False, repr=False)

    def observe(
        self,
        *,
        num_turns: int | None = None,
        cost_usd: float | None = None,
    ) -> str | None:
        """None si OK o ya se disparó antes; razón legible si se excede (primera vez).

        El guard dispara UNA sola vez: la primera llamada que supera un límite
        retorna la razón; todas las siguientes retornan None aunque el estado
        siga excedido. El caller es responsable de actuar al recibir la razón.
        """
        if self._fired:
            return None

        if (
            self.limits.max_turns > 0
            and num_turns is not None
            and num_turns >= self.limits.max_turns
        ):
            self._fired = True
            return (
                f"runaway: límite de turnos alcanzado "
                f"({num_turns} >= {self.limits.max_turns})"
            )

        if (
            self.limits.max_cost_usd > 0.0
            and cost_usd is not None
            and cost_usd >= self.limits.max_cost_usd
        ):
            self._fired = True
            return (
                f"runaway: límite de costo alcanzado "
                f"(${cost_usd:.4f} >= ${self.limits.max_cost_usd:.4f})"
            )

        return None
