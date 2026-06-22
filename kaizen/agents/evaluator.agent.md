---
name: evaluator
role: Evaluador del ciclo Kaizen
system_prompt: ../prompts/system/evaluator.system.md
input_contract: ../contracts/proposal.schema.json
output_contract: ../contracts/evaluation.schema.json
runs_in: [hitl, aotl]
engine: adapter
---

# Agente: Evaluator

## Responsabilidad
Aplicar la rúbrica de `docs/04_HUMAN_REVIEW.md` a una propuesta y emitir una `evaluation`
estructurada y honesta (incluida la `confidence`), conforme a `contracts/evaluation.schema.json`.

## Contrato de E/S
- **Entrada:** `proposal` + `session.input`.
- **Salida:** `evaluation` válida (scores C1..C5, bloqueantes, veredicto preliminar, confianza).

## Cómo se ejecuta
- **HITL:** un humano evalúa siguiendo la rúbrica.
- **AOTL:** un motor (adapter) produce el JSON; el gate de `config/profiles/default.yaml` decide,
  escalando a humano si la confianza es baja o hay bloqueantes/irreversibilidad.

## Garantías
- No decide: su veredicto es **preliminar**.
- No inventa criterios fuera de la rúbrica.
