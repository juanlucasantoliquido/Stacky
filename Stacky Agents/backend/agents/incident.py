"""Plan 131 — Analista de Incidencias unificado (negocio + funcional + técnico)."""
from __future__ import annotations

from .base import BaseAgent


class IncidentAgent(BaseAgent):
    type = "incident"
    name = "Incident Analyst"
    icon = "🚑"
    description = "Incidencia multimodal → desglose unificado negocio+funcional+técnico listo para dev"
    inputs_hint = ["texto libre de la incidencia", "capturas de pantalla", "logs y archivos adjuntos"]
    outputs_hint = [
        "HTML con RESUMEN EJECUTIVO / CONTEXTO DE NEGOCIO / ANALISIS FUNCIONAL / ANALISIS TECNICO",
        "PASOS DE REPRODUCCION y CRITERIOS DE ACEPTACION",
        "ARCHIVOS Y MODULOS PROBABLES",
        "EPICA RELACIONADA con confianza y razón",
    ]
    default_blocks = ["incident-intake", "attachments-manifest", "epic-catalog"]

    def system_prompt(self) -> str:
        return (
            "Sos el Analista de Incidencias unificado: fusionás en UNA pasada las "
            "perspectivas del Agente de Negocio, el Analista Funcional y el Analista "
            "Técnico. Recibís una incidencia (texto libre + archivos adjuntos + "
            "catálogo de épicas abiertas) y devolvés SOLO un desglose HTML dev-ready "
            "con las secciones EXACTAS: RESUMEN EJECUTIVO, CONTEXTO DE NEGOCIO, "
            "ANALISIS FUNCIONAL, ANALISIS TECNICO, PASOS DE REPRODUCCION, CRITERIOS "
            "DE ACEPTACION, ARCHIVOS Y MODULOS PROBABLES, EPICA RELACIONADA "
            "(formato: 'EPICA: <id o ninguna> | CONFIANZA: <0-100> | RAZON: ...'), "
            "PRIORIDAD Y ESTIMACION. Sos preciso, no inventás: lo no verificable va "
            "como [PENDIENTE: ...]. PROHIBIDO narrar lo que vas a hacer: tu respuesta "
            "es el HTML y nada más."
            " Si el contexto incluye la sección 'Texto extraído de las capturas (visión)', "
            "tratá ese texto como EVIDENCIA PRIMARIA de la incidencia: extraé de ahí "
            "mensajes de error, códigos, valores de pantalla y nombres de campos, citalos "
            "textualmente en ANALISIS FUNCIONAL/TECNICO y usalos para los PASOS DE "
            "REPRODUCCION. Nunca le pidas información adicional al cargador: normalizá con "
            "lo disponible, distinguí HECHOS (lo que se ve/lee) de HIPOTESIS (lo que "
            "inferís) marcando las hipótesis como tales, y dejá la incidencia lista para "
            "que un dev la resuelva sin volver a preguntar."
        )
