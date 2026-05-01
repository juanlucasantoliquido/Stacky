from .base import BaseAgent


class BusinessAgent(BaseAgent):
    type = "business"
    name = "Business"
    icon = "🧠"
    description = "Texto libre / conversación cliente → Epics estructurados"
    inputs_hint = ["brief o transcripción de entrevista", "notas del cliente"]
    outputs_hint = [
        "HTML con bloques RF-XXX",
        "Actores identificados",
        "Reglas de negocio",
        "Datos involucrados",
        "Prioridades",
    ]
    default_blocks = ["raw-conversation", "user-notes"]

    def system_prompt(self) -> str:
        return (
            "Sos el Agente de Negocio. Recibís texto libre del cliente y devolvés un Epic "
            "estructurado en HTML, separando los requerimientos en bloques `RF-XXX` con `<hr><h2>`. "
            "Para cada RF identificás: actores, reglas de negocio, datos involucrados y prioridad. "
            "Sos preciso, no inventás. Si falta información, marcás `[PENDIENTE: ...]`."
        )
