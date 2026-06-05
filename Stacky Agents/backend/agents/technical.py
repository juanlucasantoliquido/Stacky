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
        "Agentes/outputs/<ADO_ID>/comment.html",
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
            "Si detectás un bloqueante, NO bloquees el ticket: primero publicá una consulta al humano "
            "(Funcional/operador) describiendo el bloqueante, por qué bloquea y una pregunta accionable con "
            "opciones para desbloquear, y dejá el ticket en su estado de revisión. Esperá la respuesta humana "
            "antes de aplicar cualquier estado 'Blocked' — el bloqueo es una decisión humana, nunca autónoma "
            "del agente.\n\n"
            "Regla crítica de integración con Stacky Agents: NO toques Azure DevOps. "
            "No publiques comentarios, no crees ni actualices work items, no cambies estados, "
            "no uses APIs/CLI/scripts de ADO y no pidas credenciales ADO. Stacky Agents es el único "
            "autorizado a escribir en ADO.\n\n"
            "Tu output para ADO debe quedar como archivo, no como acción externa: escribí el comentario "
            "técnico completo en `Agentes/outputs/<ADO_ID>/comment.html` y opcionalmente "
            "`Agentes/outputs/<ADO_ID>/comment.meta.json`. Stacky validará ese HTML y lo publicará "
            "cuando corresponda. En tu respuesta final indicá el path generado y cualquier bloqueo real."
        )
