from .base import BaseAgent


class DeveloperAgent(BaseAgent):
    type = "developer"
    name = "Developer"
    icon = "💻"
    description = "Análisis técnico → implementación de código + evidencia"
    inputs_hint = [
        "Task con análisis técnico aprobado",
        "código fuente",
        "scripts de BD existentes",
    ]
    outputs_hint = [
        "Cambios en repo (diffs propuestos)",
        "Comentario 🚀 con evidencia",
        "Resultados de tests unitarios",
        "Verificaciones de BD",
    ]
    default_blocks = [
        "ticket-meta",
        "technical-analysis",
        "code-tree",
        "ridioma-master",
    ]

    def system_prompt(self) -> str:
        return (
            "Sos el Developer. Recibís un Task con análisis técnico aprobado e implementás los cambios "
            "exactamente dentro del alcance definido. Cada cambio lleva `// ADO-{id} | {YYYY-MM-DD} | descripción`. "
            "Las entradas RIDIOMA / RTABL / RPARAM se agregan al final del archivo maestro existente "
            "(nunca creás archivos .sql nuevos). Ejecutás los TUs definidos hasta 100%. "
            "Cerrás con un comentario 🚀 con: archivos modificados, trazabilidad, resultados de TUs, "
            "verificaciones de BD, compilación y notas para QA."
        )
