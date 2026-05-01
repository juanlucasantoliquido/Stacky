"""
CustomAgent — agente genérico para system prompts arbitrarios (ej: agentes
.agent.md de VS Code / GitHub Copilot). Siempre se ejecuta con
system_prompt_override; sin override no aporta valor.
"""
from .base import BaseAgent


CUSTOM_FALLBACK_PROMPT = (
    "Sos un agente IA personalizado del workbench Stacky. "
    "El operador no proveyó system prompt; respondé con un análisis útil del contexto."
)


class CustomAgent(BaseAgent):
    type = "custom"
    name = "Custom Agent"
    description = "Agente con system prompt arbitrario (VS Code / Copilot custom)."
    icon = "✦"
    inputs_hint = ["context blocks libres"]
    outputs_hint = ["respuesta del agente"]
    default_blocks = []

    def system_prompt(self) -> str:
        return CUSTOM_FALLBACK_PROMPT
