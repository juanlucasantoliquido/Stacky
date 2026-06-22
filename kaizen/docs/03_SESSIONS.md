# 03 — Sesiones Separadas y Transición HITL → AOTL

## Qué es una sesión

Una **vuelta completa del ciclo**, aislada y reproducible, con su propia carpeta bajo
`sessions/<id>/`. El `<id>` es `<timestamp-UTC>__<slug-del-objetivo>` para que ordene
cronológicamente y sea legible.

### Contenido de una sesión

```
sessions/2026-06-21T1530Z__mejorar-mensajes-de-error/
├── session.json     # metadatos (contracts/session.input.schema.json)
├── session.md       # bitácora humana
├── proposal.md      # PROPONER
├── evaluation.md    # EVALUAR
├── decision.md      # DECIDIR
└── artifacts/       # (opcional) artefactos locales de esta sesión
```

### Aislamiento

- Una sesión no lee el estado mutable de otra. Solo el **índice** (`sessions/_index.json`) y
  los `decisions/` acumulados sirven como memoria entre sesiones (lectura, no escritura cruzada).
- Borrar una sesión no rompe a las demás. Lo promovido (artefactos/decisiones) ya fue copiado.

## El índice de sesiones

`sessions/_index.json` es **append-only**: una lista de entradas `{id, objetivo, mode, adapter,
created_utc, status}`. Permite listar, comparar y auditar sin abrir cada carpeta.

## Estados de una sesión

```
open ──► proposed ──► evaluated ──► decided ──► closed
                                       │
                                       └─(iterate)─► abre una sesión hija (referencia al padre)
```

`iterate` no reabre la sesión: crea una **sesión hija** que referencia a la madre en su
`session.json` (`parent_session`). Así la historia es lineal y auditable (invariante I4).

## Transición HITL → AOTL

El ciclo y los contratos son idénticos; cambia **quién ejecuta** cada paso:

| Paso | HITL | AOTL |
|---|---|---|
| Crear sesión | humano corre `new_session.py` | scheduler/agente la crea |
| PROPONER | humano escribe `proposal.md` | `agents/improver` la genera |
| EVALUAR | humano escribe `evaluation.md` | `agents/evaluator` la genera |
| DECIDIR | humano escribe `decision.md` | gate de `config/profiles/default.yaml` decide |
| Excepción | — | si el gate no alcanza confianza, escala a humano |

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
