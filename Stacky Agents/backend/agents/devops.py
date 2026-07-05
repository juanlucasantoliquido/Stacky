from .base import BaseAgent


class DevOpsAgent(BaseAgent):
    type = "devops"
    name = "DevOps"
    icon = "🛠️"
    description = "Agente DevOps conversacional: diagnostico, configuraciones y despliegues con confirmacion"
    inputs_hint = [
        "mensaje del operador (chat DevOps)",
        "workspace del proyecto",
    ]
    outputs_hint = [
        "respuesta conversacional",
        "plan de accion propuesto (pendiente de CONFIRMO)",
        "resumen de acciones ejecutadas",
    ]
    default_blocks: list[str] = []

    def system_prompt(self) -> str:
        return (
            "Sos el agente DevOps de Stacky. Trabajas en modo CONVERSACIONAL "
            "multi-turno: respondes, proponés y esperás la respuesta del operador. "
            "Regla de oro (R-HITL): NUNCA ejecutes una accion que modifique estado "
            "(deploy, cambio de configuracion, borrado, reinicio de servicios, "
            "escritura fuera del workspace) sin antes mostrar el plan exacto de "
            "comandos y recibir la palabra CONFIRMO del operador. Diagnosticar, "
            "leer y comparar es libre. Nunca imprimas secretos ni credenciales."
        )
