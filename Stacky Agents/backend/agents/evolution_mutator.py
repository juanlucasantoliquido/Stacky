"""Plan 169 F2 — Agente Mutador del optimizador evolutivo.

Genera UNA variante COMPLETA y mejorada de un artefacto de texto (el prompt de un
agente) leyendo las críticas del juez del 168 (mutación reflexiva estilo GEPA). Es
one-shot: corre en background bajo cualquiera de los 3 runtimes vía run_agent y cierra
la sesión CLI de Claude por el sentinel `-9` (variant_generator._OPTIMIZER_ADO_ID).
Espejo estructural de agents/incident_dev.py."""
from .base import BaseAgent


class EvolutionMutatorAgent(BaseAgent):
    type = "evolution_mutator"
    name = "Evolution Mutator"
    icon = "🧬"
    description = "Genera variantes mejoradas de un artefacto de texto para el optimizador evolutivo"
    inputs_hint = ["artefacto base", "criticas de la ultima evaluacion", "lecciones previas"]
    outputs_hint = ["una variante completa entre marcadores <<<VARIANTE>>>...<<<FIN_VARIANTE>>>"]
    default_blocks: list[str] = []

    def system_prompt(self) -> str:
        from services.variant_generator import _MUTATOR_SYSTEM
        return _MUTATOR_SYSTEM
