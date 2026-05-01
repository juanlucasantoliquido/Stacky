from .base import BaseAgent


class QAAgent(BaseAgent):
    type = "qa"
    name = "QA"
    icon = "✅"
    description = "Implementación → veredicto de aprobación / regresión"
    inputs_hint = [
        "Task con análisis funcional + técnico",
        "última exec aprobada del Developer",
        "commits del branch",
        "plan de pruebas",
    ]
    outputs_hint = [
        "TESTER_COMPLETADO.md",
        "Verdict: PASS / FAIL",
        "Casos verificados",
        "Riesgos detectados",
    ]
    default_blocks = [
        "ticket-meta",
        "functional-test-plan",
        "technical-test-plan",
        "developer-evidence",
        "branch-commits",
    ]

    def system_prompt(self) -> str:
        return (
            "Sos el QA. Recibís un Task con análisis funcional y técnico, y el comentario 🚀 del Developer. "
            "Validás que cada caso del plan de pruebas haya sido verificado, evaluás riesgos de regresión "
            "y emitís un veredicto claro (PASS / FAIL) con justificación. "
            "Sos crítico pero constructivo: si encontrás un fallo, indicás el caso, el comportamiento esperado y el observado."
        )
