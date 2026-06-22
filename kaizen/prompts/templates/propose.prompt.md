# Prompt Template — PROPONER

> Variables entre `{{...}}` las llena el adapter o el operador. Salida: `contracts/proposal.schema.json`.

Objetivo de la sesión:
{{objective}}

Contexto observado:
{{context}}

Restricciones:
- Una sola mejora, acotada (declarar scope.in / scope.out).
- Reversibilidad obligatoria (describir rollback).
- Métrica de éxito objetiva.

Produciendo la propuesta como JSON conforme a `contracts/proposal.schema.json`.
