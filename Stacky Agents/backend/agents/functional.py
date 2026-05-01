from .base import BaseAgent


class FunctionalAgent(BaseAgent):
    type = "functional"
    name = "Functional"
    icon = "📋"
    description = "Epic → análisis funcional + plan de pruebas + clasificación"
    inputs_hint = ["Epic ADO", "documentación funcional del módulo"]
    outputs_hint = [
        "analisis-funcional.md",
        "plan-de-pruebas.md",
        "clasificación: CUBRE / GAP / NUEVA FUNC.",
    ]
    default_blocks = ["ticket-meta", "epic-description", "func-docs"]

    def system_prompt(self) -> str:
        return (
            "Sos el Analista Funcional. Recibís un Epic con bloques RF-XXX y la documentación "
            "funcional del producto. Para cada RF: clasificás cobertura "
            "(CUBRE Sin modificación / CUBRE Con configuración / GAP Menor / Nueva Funcionalidad), "
            "redactás el análisis funcional y un plan de pruebas. "
            "Sos riguroso con la trazabilidad y citás explícitamente los documentos consultados."
        )
