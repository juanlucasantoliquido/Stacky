# Prompt Template — EVALUAR

> Variables entre `{{...}}` las llena el adapter o el operador. Salida: `contracts/evaluation.schema.json`.

Objetivo de la sesión:
{{objective}}

Propuesta a evaluar (JSON conforme a proposal.schema.json):
{{proposal}}

Aplicá la rúbrica de `docs/04_HUMAN_REVIEW.md`:
- Puntuá C1..C5 (0-3) con un hallazgo por criterio.
- Dispará bloqueantes B1..B4 si corresponde.
- Veredicto preliminar + confianza honesta.

Produciendo la evaluación como JSON conforme a `contracts/evaluation.schema.json`.
