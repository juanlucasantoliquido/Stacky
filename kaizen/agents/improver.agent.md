---
name: improver
role: Proponedor de mejoras del ciclo Kaizen
system_prompt: ../prompts/system/improver.system.md
input_contract: ../contracts/session.input.schema.json
output_contract: ../contracts/proposal.schema.json
runs_in: [hitl, aotl]
engine: adapter   # el motor real lo provee el adapter activo; el núcleo no lo fija
---

# Agente: Improver

## Responsabilidad
Producir **una** propuesta de mejora acotada, valiosa y reversible para el objetivo de la sesión,
conforme a `contracts/proposal.schema.json`.

## Contrato de E/S
- **Entrada:** `session.input` (objetivo + contexto del adapter).
- **Salida:** `proposal` válida.

## Cómo se ejecuta
- **HITL:** un humano escribe la propuesta (a mano o asistido por el prompt de sistema).
- **AOTL:** un motor (provisto por el adapter) corre el prompt de sistema y emite el JSON.

## Garantías
- No ejecuta cambios: solo propone.
- Reversibilidad y métrica de éxito son obligatorias (las exige el contrato).
