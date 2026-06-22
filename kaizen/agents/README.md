# Agentes

Un **agente** acá es la definición de un rol del ciclo: su responsabilidad, su prompt de sistema
(en `prompts/system/`) y el contrato de su salida (en `contracts/`). **No** incluye el motor que
lo ejecuta: ese se conecta por adapter (ver `adapters/adapter.contract.md`), lo que mantiene el
núcleo portable y sin dependencias.

| Agente | Rol | Prompt | Salida (contrato) |
|---|---|---|---|
| `improver.agent.md` | Propone una mejora acotada | `prompts/system/improver.system.md` | `proposal.schema.json` |
| `evaluator.agent.md` | Evalúa la propuesta con la rúbrica | `prompts/system/evaluator.system.md` | `evaluation.schema.json` |

En **HITL** estos roles los ejecuta un humano (o un humano asistido). En **AOTL** los ejecuta un
motor real conectado por adapter. La definición del rol no cambia entre modos.
