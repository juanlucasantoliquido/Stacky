"""Plan 196 — agente ejecutor del pipeline de planes (una skill por corrida)."""
from __future__ import annotations

from .base import BaseAgent


class PlansPipelineAgent(BaseAgent):
    type = "plans_pipeline"
    name = "Plans Pipeline Runner"
    icon = "🗂️"
    description = "Ejecuta una etapa del pipeline de planes (proponer/criticar/implementar/supervisar) vía las skills del repo"
    inputs_hint = ["línea de skill del pipeline con su argumento"]
    outputs_hint = ["doc de plan creado/criticado, implementación o auditoría según la skill"]
    default_blocks: list[str] = []

    def system_prompt(self) -> str:
        return (
            "Sos el ejecutor del pipeline de planes de Stacky. El mensaje inicial "
            "es UNA linea con una skill (/proponer-plan-stacky, "
            "/criticar-y-mejorar-plan, /implementar-plan-stacky o "
            "/supervisar-implementaciones-planes) y su argumento: ejecutala "
            "exactamente, sin ampliar el alcance. PROHIBIDO git push (y push "
            "--force), git stash, git reset, git rebase, git commit --amend, "
            "cambiar de rama y --no-verify: hay sesiones paralelas en este repo "
            "y el push es siempre manual del operador."
        )
