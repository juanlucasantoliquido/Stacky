# 00 — Base Conceptual

## El problema

Mejorar un sistema de forma sostenida exige un ciclo **repetible, auditable y reversible**:
algo observa el estado, propone un cambio, alguien lo evalúa, se decide, y queda registro de
por qué. Sin ese ciclo, las "mejoras" son ad-hoc, no trazables y difíciles de revertir.

Kaizen es la base de ese ciclo, diseñada para empezar con un humano al mando y poder
**ceder control gradualmente** a un agente, sin reescribir nada: solo cambia *quién* ejecuta
cada paso, no *cuáles* son los pasos ni *qué* contratos los unen.

## El ciclo (invariante)

```
        ┌─────────────────────────────────────────────────────────┐
        │                      SESIÓN (aislada)                    │
        │                                                          │
   OBSERVAR  ──►  PROPONER  ──►  EVALUAR  ──►  DECIDIR  ──►  REGISTRAR
   (contexto)     (mejora)      (rúbrica)     (veredicto)   (artefactos
        ▲                                                    + decisión)
        │                                                          │
        └──────────────────  feedback a la próxima sesión  ────────┘
```

Cada paso produce un artefacto con **contrato** definido (ver `contracts/`):

1. **Observar** → `session.input` (objetivo + contexto + adapter).
2. **Proponer** → `proposal` (qué cambiar y por qué).
3. **Evaluar** → `evaluation` (rúbrica, hallazgos, score).
4. **Decidir** → `decision` (aceptar / rechazar / iterar + justificación).
5. **Registrar** → `session.output` (todo lo anterior + referencias a artefactos).

## Invariantes (no se rompen al pasar de HITL a AOTL)

- **I1. Una sesión = una vuelta del ciclo**, aislada y reproducible.
- **I2. Todo paso tiene contrato.** Los productos son datos validables, no prosa suelta.
- **I3. La decisión es explícita y justificada.** Nunca implícita.
- **I4. El registro es append-only.** No se reescribe la historia; se itera con nuevas sesiones.
- **I5. Reversibilidad.** Ninguna mejora se aplica sin un camino de retorno declarado.

## Los dos modos

| | Human-in-the-Loop (HITL) | Agent-on-the-Loop (AOTL) |
|---|---|---|
| Propone | Humano (o agente asistiendo) | Agente |
| Evalúa | Humano | Agente (rúbrica + gates) |
| Decide | Humano | Gate automático; humano por excepción |
| Cierra el ciclo | Humano | Política configurada |
| Mismos contratos | ✅ | ✅ |

El tránsito HITL → AOTL es un **cambio de configuración**, no de arquitectura. Ver
[`03_SESSIONS.md`](03_SESSIONS.md) y [`04_HUMAN_REVIEW.md`](04_HUMAN_REVIEW.md).

## Por qué "automejora por sesiones separadas"

Sesiones separadas dan: aislamiento de fallos, reproducibilidad, comparabilidad entre intentos,
y una unidad natural de revisión humana. Cada sesión es desechable salvo por lo que decide
promover (artefactos + decisión), lo que mantiene el sistema honesto y auditable.
