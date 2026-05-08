"""
FA-47 — Agent debate / critic loop.

El CriticAgent recibe el output de cualquier agente y genera una lista
de desafíos: "¿Consideraste X?", "¿Es seguro hacer Y?", "Este punto
contradice la decisión Z".

No re-escribe el output — sólo desafía. El operador decide si responde
o si el output original ya es suficiente.

Endpoint: POST /api/agents/:exec_id/critique
"""
from __future__ import annotations

from .base import BaseAgent


class CriticAgent(BaseAgent):
    type = "__critic__"
    name = "Critic"
    icon = "🧐"
    description = "Revisa un output y genera desafíos sin reescribirlo"
    inputs_hint = ["output de otro agente"]
    outputs_hint = ["lista de desafíos y preguntas accionables"]
    default_blocks = []

    def system_prompt(self) -> str:
        return (
            "Sos el Critic Agent. Recibís el output de otro agente y tu trabajo es "
            "DESAFIARLO — no re-escribirlo. Generá una lista concisa de:\n"
            "1. Asunciones no declaradas que podrían ser incorrectas.\n"
            "2. Edge cases que el análisis no cubre.\n"
            "3. Contradicciones internas o con restricciones conocidas del proyecto.\n"
            "4. Preguntas que el analista funcional o el desarrollador deberían responder "
            "antes de proceder.\n\n"
            "Sé directo y accionable. Máximo 8 puntos. No repitas lo que dice el output."
        )
