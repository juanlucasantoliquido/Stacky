# 06 — Estrategia de migración desde Stacky Pipeline

> **TL;DR** — Stacky Agents y Stacky Pipeline coexisten. No hay big-bang. Vamos por convivencia controlada → migración por agentes → desactivación gradual del pipeline.

---

## Punto de partida

| Pieza | Vive en | Estado |
|---|---|---|
| Pipeline automático | `Tools/Stacky/pipeline_state.py`, `daemon.py`, `pipeline_runner.py` | producción |
| Bridge a copilot/LLM | `Tools/Stacky/copilot_bridge.py` | producción |
| Builders de prompts | `Tools/Stacky/prompt_builder.py` y `prompt_enhancer.py` | producción |
| Agentes existentes | `Tools/Stacky/dba_agent.py`, `meta_agent.py`, `tech_lead_reviewer.py`, etc. | producción |
| Provider de issues ADO | `Tools/Stacky/issue_provider/`, `ado_query_provider.py` | producción |
| Dashboard auditoría | `Tools/Stacky/dashboard.html` + `dashboard_server.py` | producción |
| Stacky Agents (nuevo) | `Tools/Stacky Agents/` | scaffold inicial |

---

## Principio rector

> **Stacky Agents reusa, no duplica.** Todo lo que el pipeline ya hace bien (invocar al LLM, leer ADO, parsear outputs) se delega.
> **Stacky Agents reemplaza, no convive,** sólo en la capa de orquestación: el pipeline automático y los estados rígidos.

---

## Qué se mantiene (y cómo lo usamos)

| Componente Stacky existente | Cómo lo usa Stacky Agents |
|---|---|
| `copilot_bridge.py` | importado tal cual desde `backend/copilot_bridge.py` con un wrapper fino |
| `prompt_builder.py` | el wrapper modulariza por agente — cada `agents/*.py` arma su prompt y delega al builder común para los detalles transversales (proyecto, identidad, formato) |
| `prompt_enhancer.py` | usado opcionalmente cuando un bloque de contexto pide "enriquecer con BD" |
| `issue_provider/` | el endpoint `/api/tickets` lo usa para leer ADO |
| `ado_query_provider.py`, `ado_attachment_manager.py` | usados por `/api/executions/:id/publish-to-ado` cuando el operador quiere mandar el output al ticket |
| `entry_point_resolver.py`, `dependency_graph.py`, `codebase_indexer.py` | invocados por sub-agentes del Technical agent para explorar código |
| `ridioma_lookup.py`, `ridioma_knowledge_registry.py` | consumido por el Developer agent |
| `subsystem_classifier.py`, `ticket_classifier.py` | usado por la lógica de auto-fill (sugerir docs / archivos relevantes) |

Todo esto se importa via Python normal — Stacky Agents es vecino de Stacky en el filesystem, no fork.

---

## Qué se descarta (y por qué)

| Componente | Razón de descarte |
|---|---|
| `pipeline_state.py` | la fuente de verdad pasa a ser `agent_executions` |
| `daemon.py`, `pipeline_runner.py`, `pipeline_watcher.py` | no hay loop automático |
| `pipeline_invoker.py`, `pipeline_lock.py` | el invoker es el HTTP handler; el lock es la PK de la fila |
| `auto_enter_*.py` | UX del pipeline — la nueva UX no usa hotkeys ni stdin del agente |
| `auto_escalator.py`, `intelligent_retry.py`, `speculative_executor.py` | optimizaciones del pipeline que no aplican a un modelo manual |
| `dashboard.html` + `dashboard_server.py` | reemplazado por la SPA React |
| `ticket_completion_flow.py` | el "flujo de completion" lo decide el operador con clicks |
| `pre_filter.py`, `pipeline_reconciler.py` | no hay queue ni reconciler |

**Importante:** descartar no significa borrar. Estos archivos quedan en `Tools/Stacky/` mientras el pipeline siga corriendo. Cuando el pipeline se desactive (Fase 4), se mueven a `Tools/Stacky/_deprecated/`.

---

## Qué se reescribe (porque cambia el contrato)

| Componente original | Nuevo en Stacky Agents | Cambio |
|---|---|---|
| `prompt_builder.build(ticket, agent_kind)` | `agents/*.py` con `BaseAgent.build_prompt(blocks)` | el input pasa de "ticket entero" a "lista de bloques explícita y editable" |
| `pipeline_events.py` | `log_streamer.py` + SSE | de bus interno a stream HTTP consumible por la UI |
| `metrics_collector.py` | `models.py` `metadata_json` + endpoint `/api/admin/metrics` | métricas en BD relacional, no en archivos |
| Reglas de transición de estado ADO (varias) | endpoint `/api/executions/:id/publish-to-ado` invocado a mano | el humano decide cuándo |

---

## Plan por fases

### Fase 0 — Scaffold (esta entrega)

- [x] Repositorio `Tools/Stacky Agents/` creado con docs y scaffold runnable.
- [x] Backend levanta con SQLite + endpoints stub.
- [x] Frontend React levanta y se conecta al backend.
- [x] `copilot_bridge.py` en modo **mock** (devuelve outputs canned para validar la UI).

**Salida:** demo navegable end-to-end con datos falsos. Permite validar la UX antes de invertir en integración.

### Fase 1 — Integración real con `copilot_bridge`

- Reemplazar el mock por import real de `Tools/Stacky/copilot_bridge.py`.
- Adaptar el wrapper para soportar `on_log` callback (logs → SSE).
- Smoke test: 1 ticket real, los 5 agentes corriendo manualmente, outputs persistidos.
- Métrica clave: latencia y costo coincidente con pipeline equivalente.

**Salida:** Stacky Agents corre sobre infra real para early adopters internos.

### Fase 2 — Convivencia controlada

- Pipeline automático sigue corriendo en producción para tickets en flujo normal.
- Stacky Agents disponible para casos donde el operador quiere control: re-correr análisis, comparar versiones, explorar.
- Política: tickets marcados con label `stacky-agents` saltean el pipeline automático y son terreno exclusivo del workbench.
- Auditoría dual: las execs de Stacky Agents también escriben un row resumen en la tabla legacy del pipeline (sólo lectura) para no romper dashboards existentes.

**Salida:** comparación lado a lado de KPIs (tiempo, calidad, satisfacción del operador) entre los dos modos durante 30 días.

### Fase 3 — Migración por agente

Por orden de menor a mayor riesgo:

1. **QA agent** — el más seguro: si Stacky Agents falla, el QA humano lo detecta. Migrar 100%.
2. **Technical agent** — el de mayor valor para uso manual (operador suele querer iterar). Migrar 100%.
3. **Functional agent** — migrar gradualmente con A/B (50/50) durante 2 semanas.
4. **Developer agent** — el más sensible: cambia código. Migrar último, con doble validación humana inicialmente.
5. **Business agent** — nuevo (no existe en pipeline). Empieza directamente en Stacky Agents.

**Criterio de migración por agente:** ≥ 80% de aprobación sin re-run en su modo Agents durante 2 semanas consecutivas.

### Fase 4 — Desactivación del pipeline automático

- `daemon.py` deja de ejecutarse en producción (servicio detenido).
- `pipeline_runner.py` queda invocable a mano para casos legacy (un mes adicional).
- Después: mover `Tools/Stacky/` archivos descartados a `_deprecated/`, dejar sólo los reusables.

**Salida:** el pipeline ya no decide; sólo Stacky Agents.

### Fase 5 — Limpieza y consolidación

- Mover `copilot_bridge.py`, `prompt_enhancer.py`, etc. a `Tools/Stacky Agents/backend/_legacy/` o a un paquete `stacky_engine/` compartido.
- Renombrar `Tools/Stacky/` a `Tools/Stacky_legacy/` o eliminar tras período de gracia.
- `Stacky Agents` pasa a ser simplemente "Stacky".

---

## Equivalencia conceptual entre los dos sistemas

| Pipeline (estado/concepto) | Agents (equivalente) |
|---|---|
| Ticket en `Technical review` con `daemon.py` corriendo | Ticket cargado en TicketSelector + Technical agent seleccionado |
| Daemon decide invocar `tech_analyst` | Operador hace click en Run |
| Output queda en archivo `output/tickets/...` | Output queda en `agent_executions.output` |
| Cambio de estado a `To Do` automático | Operador click "Approve" + (opcional) "Send to ADO" |
| `pipeline_state.json` tiene `last_step: "tech_done"` | `agent_executions.verdict = approved` para la última exec del agente Technical |
| Re-run requiere revertir estado en ADO | Click "Edit & Re-run" |
| Bloqueante = comentario + estado `Blocked` | Output puede contener bloqueante; el operador decide qué hacer (publish-to-ado, mandar al funcional, etc.) |

---

## Riesgos de migración y mitigación

| Riesgo | Mitigación |
|---|---|
| Equipos acostumbrados al pipeline automático sienten que Agents "los obliga a trabajar más" | Onboarding con énfasis en **Agent Packs** — recuperan el feeling de "una sola acción → todo corre" pero con checkpoints |
| Stacky Agents tiene un bug y un agente queda en `running` para siempre | Reconciliador al startup marca execs `running` con > 1h como `error (process killed)` + alerta |
| Outputs de Agents difieren de los del pipeline (mismo input, distinto output) | Durante Fase 2 se loguean ambos lado a lado para detectar drift |
| Bridge de copilot rompe contrato | Tests de integración en CI con prompts canónicos por agente |
| Pérdida de auditoría de cambios de estado ADO | Eventos de `publish-to-ado` se loguean con timestamp y user; replicable a auditoría externa |
| Operador reusa output viejo sin darse cuenta | UI muestra antigüedad en cada bloque auto-fill ("desde exec #20 hace 3 días") |

---

## Lo que **no** migra (y por qué)

| Funcionalidad pipeline | Por qué se queda fuera |
|---|---|
| Ejecución cron / programada | Stacky Agents es manual. Si en el futuro alguien quiere correr packs cada noche, eso vivirá en otro servicio que llame a la API |
| Auto-escalation a humano cuando un agente falla | La UX de Agents YA tiene al humano en el loop — la "escalation" es la pantalla de error con Retry |
| Hot-reload de código del agente | Agents corre en producción con deploys normales. No hay hotreload en prod |
| Métricas en archivos JSON | reemplazadas por queries SQL |

---

## Compatibilidad con el dashboard actual de Stacky

El dashboard HTML existente (`Tools/Stacky/dashboard.html`) seguirá funcionando durante Fase 2 con sus datos del pipeline. **No** lo intentamos modificar para mostrar execs de Agents — el frontend de Agents es la nueva UX.

Cuando el dashboard se descontinue (Fase 4), su URL redirecciona a `localhost:5173` (o el dominio interno).

---

## Checklist de readiness por agente para migración

Antes de marcar un agente como "migrado a Agents":

- [ ] System prompt portado a `agents/<type>.py` con tests unitarios.
- [ ] `default_blocks` configurado en el agente.
- [ ] Auto-fill suggestion funciona (operador ve los bloques al seleccionarlo).
- [ ] Output del agente parsea correctamente en el frontend (markdown / json).
- [ ] `publish-to-ado` para este agente tiene la lógica correcta (target, formato).
- [ ] 10 ejecuciones reales con outputs aprobados consecutivamente.
- [ ] Documentado en runbook: qué hacer si falla.

---

## Comunicación al equipo

Cada fase incluye un memo corto al equipo:

- **Fase 1:** "Stacky Agents está disponible para tus tickets. Probalo, dame feedback."
- **Fase 2:** "Si tu ticket tiene la label `stacky-agents`, no esperes al pipeline — usá el workbench."
- **Fase 3 (por agente):** "Desde el lunes, el agente <X> corre 100% en Agents. El comportamiento es idéntico, sólo cambia la UI."
- **Fase 4:** "El pipeline automático se desactiva el próximo lunes. Si necesitás disparar agentes, es desde Agents."

Soporte en cada fase: canal `#stacky-agents` (a crear), office hours 1×semana las primeras 4 semanas.
