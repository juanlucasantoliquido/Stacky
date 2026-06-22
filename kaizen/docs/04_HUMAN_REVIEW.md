# 04 — Base de Evaluación Humana

> La rúbrica que un humano usa en HITL — y que un agente reusa en AOTL. Misma rúbrica, distinto ejecutor.

## Rúbrica de evaluación

Cada propuesta se puntúa en 5 criterios, 0–3 cada uno (0 = ausente, 3 = excelente):

| # | Criterio | Pregunta guía |
|---|---|---|
| C1 | **Valor** | ¿Resuelve un problema real y vale el esfuerzo? |
| C2 | **Corrección** | ¿La propuesta es técnicamente sólida y no introduce regresiones? |
| C3 | **Alcance** | ¿Está acotada? ¿Hace una cosa bien en vez de muchas a medias? |
| C4 | **Reversibilidad** | ¿Hay un rollback claro? ¿Se puede deshacer sin daño? |
| C5 | **Mensurabilidad** | ¿Hay una forma objetiva de saber si mejoró? |

`score = suma(C1..C5)` (0–15).

## Criterios bloqueantes (vetan, sin importar el score)

- **B1.** No declara rollback y la propuesta no es trivialmente reversible.
- **B2.** Acción destructiva o irreversible sin aprobación humana explícita.
- **B3.** Sale del alcance declarado (scope creep).
- **B4.** No se puede verificar si funcionó (sin métrica ni criterio de éxito).

Si se dispara cualquier bloqueante → veredicto `reject` o `iterate`, independientemente del score.

## Veredictos

| Veredicto | Cuándo |
|---|---|
| `accept` | Sin bloqueantes y `score ≥ umbral` (default 11/15). |
| `iterate` | Buena dirección pero con bloqueante corregible o score 7–10. |
| `reject` | Bloqueante no corregible, o `score ≤ 6`. |

El umbral vive en `config/profiles/default.yaml: review.accept_threshold`.

## Cómo se completa (HITL)

En `evaluation.md` de la sesión:

1. Listá hallazgos concretos (qué está bien / qué falta), citando evidencia cuando exista.
2. Puntuá C1..C5 con una línea de justificación cada uno.
3. Marcá bloqueantes disparados (si los hay).
4. Veredicto preliminar (la decisión final va en `decision.md`).

## Cómo lo reusa AOTL

El `agents/evaluator` produce el **mismo** `evaluation.json` (mismo contrato), con los mismos
criterios y bloqueantes. El gate de `config/profiles/default.yaml`:

- aplica `accept_threshold`,
- respeta los bloqueantes (cualquier bloqueante ⇒ no auto-accept),
- y **escala a humano** si la confianza del evaluador es menor a `review.min_confidence`.

> Principio: AOTL no inventa criterios nuevos. Solo automatiza una rúbrica ya validada en HITL.
