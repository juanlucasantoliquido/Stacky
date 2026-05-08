"""
FA-29 — Debug agent.

Recibe contexto de un fallo (test log + diff de PR + commit info) y produce:
- Causa probable
- Ubicación exacta (archivo:línea)
- Fix tentativo
- Lista de comandos para reproducir local

Disparado por:
- /api/ci/failure-webhook (FA-29)
- /api/pr/review-webhook  (FA-28, cuando reviewer @-menciona stacky-bot)
"""
from __future__ import annotations

from .base import BaseAgent


class DebugAgent(BaseAgent):
    type = "debug"
    name = "Debug"
    icon = "🐞"
    description = "Analiza fallos de CI / tests y propone causa + fix tentativo"
    inputs_hint = ["build log", "diff del commit", "tests fallidos"]
    outputs_hint = ["causa probable", "fix tentativo", "comandos de repro"]
    default_blocks = ["build-log", "commit-diff", "failed-tests"]

    def system_prompt(self) -> str:
        return (
            "Sos el Debug Agent. Recibís logs de CI, diffs de commits y tests fallidos. "
            "Producí un análisis estructurado con:\n\n"
            "1. **Causa probable** — hipótesis principal con evidencia del log.\n"
            "2. **Ubicación exacta** — archivo:línea donde está el problema.\n"
            "3. **Fix tentativo** — diff sugerido (o pseudocódigo si no hay seguridad).\n"
            "4. **Repro local** — comandos exactos para reproducir el fallo.\n"
            "5. **Riesgo de regresión** — qué más podría romper este fix.\n\n"
            "Sé específico — citá líneas concretas del log. Si no podés determinar la causa "
            "con la información dada, decilo explícitamente y enumerá qué información falta."
        )


class PRReviewAgent(BaseAgent):
    """FA-28 — variante orientada a code review on-demand."""

    type = "pr_review"
    name = "PR Review"
    icon = "🔍"
    description = "Revisa un PR diff y comenta findings"
    inputs_hint = ["diff del PR", "descripción del PR", "convenciones del proyecto"]
    outputs_hint = ["lista de findings con severidad y archivo:línea"]
    default_blocks = ["pr-diff", "pr-description"]

    def system_prompt(self) -> str:
        return (
            "Sos el PR Reviewer. Recibís un diff y describís findings con esta estructura:\n\n"
            "Para cada finding:\n"
            "- **Severidad**: blocker | major | minor | nit\n"
            "- **Ubicación**: archivo:línea\n"
            "- **Tipo**: bug | security | performance | style | maintainability\n"
            "- **Detalle**: explicación concreta\n"
            "- **Sugerencia**: cómo arreglarlo (si aplica)\n\n"
            "Sé constructivo. Si el PR está bien, decilo claramente — no fuerces findings. "
            "Limitá a los 5 findings más relevantes. Ignorá nits triviales si hay issues mayores."
        )
