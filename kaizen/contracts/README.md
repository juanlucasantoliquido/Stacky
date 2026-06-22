# Contratos de Entrada/Salida

Los contratos son **JSON Schema (draft 2020-12)** y definen la forma de los artefactos que
fluyen entre los pasos del ciclo. Son la **API estable** del sistema: lo que hace que el núcleo,
los agentes y los adapters se entiendan sin acoplarse.

## Mapa de contratos

| Esquema | Producido por | Consumido por |
|---|---|---|
| `session.input.schema.json` | crear sesión | todos los pasos |
| `proposal.schema.json` | PROPONER (humano o improver) | EVALUAR |
| `evaluation.schema.json` | EVALUAR (humano o evaluator) | DECIDIR / gate |
| `decision.schema.json` | DECIDIR (humano o gate) | REGISTRAR |
| `artifact.schema.json` | cualquier paso que genere un artefacto | índice / migración |
| `session.output.schema.json` | REGISTRAR | auditoría / próxima sesión |

## Reglas

- **Aditivo y versionado.** Cambios compatibles = campos opcionales nuevos. Cambios incompatibles
  = bump de `$id` (`.../v2/...`) y nota en el changelog de abajo. Nunca rompas un consumidor en silencio.
- **Sin dependencias del proyecto padre.** Los esquemas son genéricos; cualquier especificidad
  va en el `payload`/`context` que llena el adapter, no en el esquema.
- **Markdown + JSON espejados.** En las sesiones, el `.md` es para humanos y el `.json` valida
  contra el esquema. En HITL el `.md` manda; en AOTL el `.json` manda. Deben coincidir.

## Validación

Cualquier validador draft 2020-12 sirve (p.ej. `jsonschema` en Python, `ajv` en JS). El núcleo no
impone uno para no agregar dependencias. La fase M2 de la migración agrega `kaizen validate`.

## Changelog de contratos

- **v1 (0.1.0)** — versión inicial: session.input/output, proposal, evaluation, decision, artifact.
