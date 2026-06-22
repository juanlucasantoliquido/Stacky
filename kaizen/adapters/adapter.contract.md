# Contrato de Adapter

Qué debe proveer cualquier adapter para que el núcleo genérico lo use sin acoplarse. Un adapter
es **declarativo** (`adapter.yaml`) y opcionalmente apunta a comandos/hooks externos; el núcleo
solo necesita los campos de abajo.

## Campos requeridos de `adapter.yaml`

| Campo | Tipo | Para qué |
|---|---|---|
| `name` | string | Identifica el adapter (== nombre de carpeta). |
| `description` | string | Qué proyecto/contexto acopla. |
| `observe` | objeto | Cómo se obtiene el `context` de `session.input` (manual o comando). |
| `engine` | objeto | Cómo se ejecutan los agentes improver/evaluator (manual en HITL; runner en AOTL). |
| `apply` | objeto | Cómo se aplica una propuesta aceptada (manual / comando), SIEMPRE con rollback. |
| `measure` | objeto | Cómo se evalúa la `success_metric` (manual / comando). |

> Cualquier capacidad ausente se declara `mode: manual` (lo hace un humano). El adapter `generic`
> tiene todo en `manual`: por eso no toca nada externo.

## Contrato semántico (invariantes que el adapter NO puede violar)

- **No filtrar al núcleo.** El adapter llena `context`/`payload`; no modifica los esquemas de
  `contracts/`.
- **Reversibilidad.** `apply` siempre acompaña un `rollback`. Sin rollback, no se aplica.
- **No destructivo por defecto.** Ningún comando destructivo corre sin aprobación (HITL) o gate
  que lo permita explícitamente (AOTL).
- **Rutas portables.** Nada de rutas absolutas versionadas; usar relativas o variables de entorno.
- **Aislamiento.** No importar otros adapters; secretos fuera de control de versiones.

## Forma esperada de los hooks (cuando `mode: command`)

Un hook recibe JSON por stdin (el artefacto relevante) y devuelve JSON por stdout (conforme al
contrato correspondiente). Esto mantiene el motor desacoplado del núcleo y del lenguaje.
