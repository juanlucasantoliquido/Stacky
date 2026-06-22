# Skills

Una **skill** acá es un procedimiento determinístico invocable: una secuencia de pasos clara,
sin ambigüedad, que opera sobre los contratos y plantillas del núcleo. Son portables: no
dependen del proyecto padre.

| Skill | Qué hace |
|---|---|
| `run-session/SKILL.md` | Corre una vuelta completa del ciclo (observar→…→registrar). |

Las skills son agnósticas de motor: describen el procedimiento. En HITL las sigue un humano; en
AOTL las puede orquestar un runner conectado por adapter.
