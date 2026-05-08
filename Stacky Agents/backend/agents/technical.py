from .base import BaseAgent


class TechnicalAgent(BaseAgent):
    type = "technical"
    name = "Technical"
    icon = "🔧"
    description = "Análisis funcional → traducción técnica + plan + TUs"
    inputs_hint = [
        "Task ADO con análisis funcional aprobado",
        "documentación técnica del módulo",
        "código fuente relevante",
    ]
    outputs_hint = [
        "Comentario 🔬 con 5 secciones",
        "Plan de pruebas técnico",
        "Tests unitarios obligatorios",
        "Notas para el desarrollador",
    ]
    default_blocks = [
        "ticket-meta",
        "functional-analysis",
        "tech-docs",
        "code-tree",
    ]

    def system_prompt(self) -> str:
        return (
            "Sos el Analista Técnico. Recibís un Task con análisis funcional aprobado y "
            "explorás el código y la documentación técnica. Producís un análisis técnico de 5 secciones: "
            "(1) traducción funcional → técnica, (2) alcance de cambios a nivel de método, "
            "(3) plan de pruebas técnico con datos de BD reales, (4) tests unitarios obligatorios "
            "(TU-001…TU-N con clase, método, escenario, input, expected, assert), "
            "(5) notas para el desarrollador. "
            "Si detectás un bloqueante, lo declarás explícitamente y describís la acción requerida del Funcional."
        )
