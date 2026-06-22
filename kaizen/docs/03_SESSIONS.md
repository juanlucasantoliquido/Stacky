# 03 — Sesiones Separadas y Transición HITL → AOTL

## Qué es una sesión

Una **vuelta completa del ciclo**, aislada y reproducible, con su propia carpeta bajo
`sessions/<id>/`. El `<id>` es `<timestamp-UTC>__<slug-del-objetivo>` para que ordene
cronológicamente y sea legible.

### Contenido de una sesión

```
sessions/2026-06-21T1530Z__mejorar-mensajes-de-error/
├── session.json       # metadatos (contracts/session.input.schema.json)
├── proposal.json      # PROPONER  (contracts/proposal.schema.json)
├── change_set.json    # cambios declarativos a aplicar  (solo AOTL)
├── evaluation.json    # EVALUAR   (contracts/evaluation.schema.json)
├── decision.json      # DECIDIR   (contracts/decision.schema.json)
└── _apply/            # pre-imágenes y manifest de apply (reversible)
    └── applied.json
```

> En HITL manual, `proposal.json` lo escribe el humano; los demás artefactos también son JSON
> conforme a sus contratos — nunca archivos `.md`.
> `change_set.json` y `_apply/` solo aparecen en flujos AOTL (auto-apply).

### Aislamiento

- Una sesión no lee el estado mutable de otra. Solo el **índice** (`sessions/_index.json`) y
  los `decisions/` acumulados sirven como memoria entre sesiones (lectura, no escritura cruzada).
- Borrar una sesión no rompe a las demás. Lo promovido (artefactos/decisiones) ya fue copiado.

## El índice de sesiones

`sessions/_index.json` es **append-only**: una lista de entradas `{id, objetivo, mode, adapter,
created_utc, status}`. Permite listar, comparar y auditar sin abrir cada carpeta.

## Estados de una sesión

```
open ──► closed (verdict: accept | iterate | reject)
           │
           └─(iterate)─► abre una sesión hija (referencia al padre en parent_session)
```

El gate (`run_session.py`) transiciona `open → closed` al decidir. No hay estados intermedios
persisitidos; los artefactos `proposal.json`, `evaluation.json` y `decision.json` se escriben
progresivamente dentro del estado `open` y el gate cierra la sesión de una vez.

`iterate` no reabre la sesión: crea una **sesión hija** vía `spawn_child.py` que referencia
a la madre en `parent_session`. Así la historia es lineal y auditable (invariante I4).

## Transición HITL → AOTL

El ciclo y los contratos son idénticos; cambia **quién ejecuta** cada paso:

| Paso | HITL | AOTL |
|---|---|---|
| Crear sesión | humano corre `new_session.py` | `autoloop.py` la crea via `create_session()` |
| PROPONER | humano escribe `proposal.json` | `engine.py` (driver claude/mock) la genera |
| EVALUAR | humano escribe `evaluation.json` | `engine.py` la genera |
| APLICAR | humano aplica el cambio manualmente | `apply.py` aplica `change_set.json` (reversible) |
| DECIDIR | humano corre `run_session.py <id>` | `run_session.py` corre el gate automáticamente |
| Excepción | — | si el gate no alcanza confianza, escala a humano vía REVIEW_QUEUE.md |

### Cómo se activa AOTL

1. `config/kaizen.config.yaml: mode: aotl`.
2. `config/profiles/default.yaml` define los **gates**: umbral de score, criterios bloqueantes,
   límite de iteraciones, y la condición de **escalado a humano**.
3. Un adapter provee el "motor" (cómo se ejecutan improver/evaluator). El núcleo no cambia.

### Salvaguardas al ceder control (no negociables)

- **Reversibilidad obligatoria** (invariante I5): toda propuesta aceptada en AOTL debe declarar
  su rollback, o el gate la rechaza.
- **Escalado por excepción**: confianza baja, criterio bloqueante o acción irreversible → humano.
- **Tope de iteraciones**: evita bucles infinitos de auto-propuesta.
- **Append-only**: el agente nunca reescribe sesiones ni decisiones previas.

> Diseñá y validá la rúbrica y los gates **en HITL primero**. AOTL solo automatiza una rúbrica
> que ya demostró ser buena con humanos.
