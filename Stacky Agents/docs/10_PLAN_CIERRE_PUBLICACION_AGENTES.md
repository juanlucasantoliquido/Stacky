# Plan SSD Robusto — Cierre, Publicación y Transición de Estados en Stacky Agents

**Versión:** 1.0
**Fecha:** 2026-05-14
**Owner:** Stacky Core
**Estado:** Propuesto

---

## 1. Resumen Ejecutivo

La cadena de cierre de ejecuciones de agentes está partida: un agente puede informar `completed`, pero Stacky no cierra la `AgentExecution`, no dispara los hooks de publicación, no consolida el estado real con ADO, y la UI puede quedar bloqueada por ejecuciones `running` huérfanas. Hoy `PATCH /api/tickets/by-ado/{ado_id}/stacky-status` (`backend/api/tickets.py:392`) llama a `ticket_status.set_status(...)` y deja la publicación a un post-hook implícito, sin validar HTML, sin resolver ejecución activa, sin idempotencia explícita y sin auditoría unificada.

**Tesis:** Stacky debe ser la **única autoridad de cierre, publicación y transición**. Los agentes solo producen evidencia (HTML + metadata) y notifican finalización contra un **gateway backend** que hace, en una sola transacción auditable: resolver ejecución activa → validar HTML → cerrar ejecución → publicar en ADO → transicionar estado, todo idempotente.

---

## 2. Diagnóstico Detallado

### 2.1 Síntomas observados

| # | Síntoma | Evidencia |
|---|---|---|
| S1 | Tickets con `stacky_status='completed'` y `AgentExecution.status='running'` simultáneamente. | ADO-149 / ejecución 44. |
| S2 | HTML válido en `Agentes/outputs/{ado_id}/comment.html` sin registro en `AgentHtmlPublish`. | ADO-149. |
| S3 | Botón “Finalizar/Recuperar” oculto cuando `stacky_status=completed` aunque haya `running` huérfano. | UI grafo / detalle. |
| S4 | Agentes con identidad inconsistente: `AnalistaFuncionlPacifico.agent.md` vs `AnalistaFuncionalPacifico.agent.md`. | `backend/projects/PACIFICO/config.json` y archivos del repo. |
| S5 | Prompts contienen instrucciones de publicar y transicionar ADO directamente, violando la regla de autoridad única. | Agentes funcional/técnico (legado). |

### 2.2 Causa raíz

1. **Endpoint de finalización no canónico.** `set_stacky_status_by_ado` (`api/tickets.py:392`) acepta cualquier `status` arbitrario sin distinguir “señal de cierre de agente” de “override manual”, no resuelve `execution_id`, no valida HTML, no llama `on_execution_end`.
2. **Publicación implícita y frágil.** El hook que invoca `ado_publisher.publish_from_execution` corre solo si el estado terminal queda exactamente como espera; cualquier reentrada o ambigüedad rompe la cadena.
3. **Idempotencia inexistente.** No hay constraint que prevenga doble publicación (`AgentHtmlPublish` se chequea solo si llega al publisher).
4. **No hay contrato del agente.** Los prompts cambian sin tests; cualquier agente puede mentirle al backend (decir `completed` sin haber generado HTML).
5. **UI confía en `stacky_status` y oculta acciones de recuperación**, dejando al operador sin salida.

---

## 3. Principios de Diseño

1. **Stacky es la única autoridad** para publicar en ADO y cambiar `stacky_status`. Los agentes no escriben en ADO.
2. **Una sola entrada de finalización**: el gateway. Cualquier otra ruta queda como override manual con auditoría diferenciada.
3. **Idempotencia por construcción**: misma señal repetida = mismo resultado, sin duplicados.
4. **Trazabilidad end-to-end**: cada evento de cierre genera un registro consultable (ticket → ejecución → HTML → publicación → transición).
5. **Recuperación sin tocar DB**: cualquier inconsistencia debe poder resolverse desde UI/CLI oficial.
6. **Reversibilidad**: rollout detrás de feature flag, capacidad de re-procesar histórico.

---

## 4. Arquitectura Objetivo

```
┌──────────┐    POST/PATCH /agent-completion     ┌─────────────────────────┐
│ Agente   │ ─────────────────────────────────▶ │ AgentCompletionGateway   │
│ (CLI/MD) │   { ado_id, agent_type, html_path, │  (backend/api/tickets    │
│          │     execution_id?, status, ... }    │   o api/agents)          │
└──────────┘                                     └────────────┬─────────────┘
                                                              │
   ┌──────────────────────────────────────────────────────────┼──────────────┐
   │                          Transacción única               │              │
   │  1. resolve_execution()      ── prioridad documentada    │              │
   │  2. SELECT ... FOR UPDATE    ── lock por ejecución       │              │
   │  3. validate_html()          ── contract_validator       │              │
   │  4. persist html_output_path en AgentExecution           │              │
   │  5. close_execution()        ── status terminal + ts     │              │
   │  6. ado_publisher.publish_from_execution()               │              │
   │     └─ INSERT AgentHtmlPublish (UNIQUE)                  │              │
   │  7. ticket_status.on_execution_end(...)                  │              │
   │     └─ workflow.apply_transition(project, from, to)      │              │
   │  8. emit audit event + structured log                    │              │
   └──────────────────────────────────────────────────────────┴──────────────┘
```

---

## 5. Cambios Backend

### 5.1 Nuevo Gateway de Finalización

**Endpoint canónico:** `POST /api/tickets/by-ado/{ado_id}/agent-completion`
(El endpoint legacy `PATCH /stacky-status` se mantiene como override manual auditado.)

**Auth:** header `X-Stacky-Agent-Token` (token simétrico por proyecto, configurable) + `X-User-Email` opcional para trazabilidad.

**Payload:**

```json
{
  "execution_id": 44,
  "agent_type": "functional",
  "status": "completed",
  "html_output_path": "Agentes/outputs/149/comment.html",
  "metadata": {
    "html_sha256": "…",
    "agent_version": "AnalistaFuncionalPacifico@2026-05-14",
    "duration_ms": 184232
  },
  "reason": "fin de análisis funcional"
}
```

**Resolución de ejecución** (prioridad estricta, primer match gana):

1. `execution_id` explícito → debe pertenecer al ticket; estado en `{running, queued}`. En caso contrario → `409 execution_state_invalid`.
2. Última `AgentExecution` con `status in (running, queued)` del ticket cuyo `agent_type` matchee el payload.
3. Si no hay match por `agent_type` pero existe **una y solo una** ejecución activa → usar esa, registrar `metadata.agent_type_mismatch = true`.
4. Cero ejecuciones activas + HTML válido presente → crear `AgentExecution` sintética `kind=rescue` (solo flag `allow_synthetic_rescue=true`), de lo contrario → `409 no_active_execution`.

**Estados terminales aceptados:** `completed`, `error`, `cancelled`, `needs_review` (este último para HTML inválido pero recuperable).

**Idempotencia:**

- `AgentHtmlPublish` debe tener `UNIQUE(execution_id, html_sha256)`. La fila se crea en la misma transacción que el cierre.
- Si llega un callback repetido con misma `(execution_id, html_sha256)` y ejecución ya terminal → responder `200 idempotent_replay` con el registro existente, sin republicar.
- Si llega callback con misma execution pero HTML distinto → `409 html_already_published` salvo `force=true` con auditoría.

**Concurrencia:**

- `SELECT ... FOR UPDATE` sobre la fila `AgentExecution`.
- Fallback aplicativo: `pipeline_lock.py` con key `ticket:{ticket_id}:completion`.

**Códigos de error (machine-readable):**

| HTTP | `error.code` | Causa |
|---|---|---|
| 400 | `payload_invalid` | Faltan campos / tipos malos. |
| 401 | `auth_required` | Falta/expira `X-Stacky-Agent-Token`. |
| 404 | `ticket_not_found` | ADO id no existe en DB local. |
| 409 | `no_active_execution` | Sin ejecución resoluble. |
| 409 | `execution_state_invalid` | Execution ya terminal y payload no es replay. |
| 409 | `html_already_published` | Otro HTML publicado para esa ejecución. |
| 422 | `html_invalid` | `contract_validator` rechaza. Cierra ejecución como `needs_review` salvo `dry_run`. |
| 500 | `internal_error` | Trazar correlation_id. |

**Archivos afectados (estimado):**

- `backend/api/tickets.py` → nuevo handler `agent_completion(ado_id)`.
- `backend/services/ticket_status.py` → exponer `on_execution_end()` puro, sin efectos de publicación.
- `backend/services/agent_completion.py` (nuevo) → orquesta resolución + cierre + publish + transición.
- `backend/services/ado_publisher.py` → reforzar `publish_from_execution` para que asuma idempotencia y devuelva `AgentHtmlPublish`.
- `backend/models.py` → migración: `UNIQUE(execution_id, html_sha256)` en `AgentHtmlPublish`; campo `AgentExecution.completion_source` (`agent_gateway` / `manual` / `recovery` / `rescue`).

### 5.2 Centralización de publicación y transición ADO

- Único punto de publicación: `ado_publisher.publish_from_execution(execution_id, *, force=False) -> AgentHtmlPublish`.
- Único punto de transición ADO: `services/ado_workflow.py` (nuevo) leyendo `projects/{PROJECT}/workflow.json`:
  ```json
  {
    "transitions": {
      "functional": { "from": "*", "to": "Resolved",
                      "comment_template": "Análisis funcional completado por Stacky" },
      "developer":  { "from": "*", "to": "Resolved" }
    },
    "fallback_state": "Active"
  }
  ```
- Los prompts de agentes ya **no** invocan `ado_client.update_workitem_state` ni `add_comment` directamente. Esas herramientas se remueven del `tool_allowlist` de los agentes salvo el reportero/QA específico.

### 5.3 Timeout reaper / startup recovery

- Job al iniciar `app.py` + endpoint manual ya existente `POST /tickets/recover-stale-status` (`api/tickets.py:466`).
- Extender para que use el mismo `agent_completion` con `completion_source=recovery` y `status=error` cuando supere `EXECUTION_TIMEOUT_MINUTES`.

### 5.4 Feature flag de rollout

- `STACKY_COMPLETION_GATEWAY=on|shadow|off`.
  - `shadow`: el gateway corre paralelo al legacy y solo registra discrepancias (sin escribir ADO).
  - `on`: gateway es la ruta canónica.
  - `off`: comportamiento legacy.
- 1–2 sprints en `shadow` con métricas antes de cortar.

---

## 6. Cambios en Agentes y Configuración

### 6.1 Renombre y unificación

- Mover `AnalistaFuncionlPacifico.agent.md` → `AnalistaFuncionalPacifico.agent.md` (único nombre).
- Buscar referencias en `backend/projects/PACIFICO/config.json`, preferences, recipes, y CI.
- Agregar identidad explícita en el frontmatter del `.agent.md`:
  ```yaml
  stacky_agent_type: functional
  stacky_completion_contract: v1
  ```

### 6.2 Contrato de finalización del agente

El prompt funcional debe, al terminar:

1. Escribir `Agentes/outputs/{ado_id}/comment.html` (HTML válido según contract_validator).
2. Escribir `Agentes/outputs/{ado_id}/metadata.json` (sha256, agent_version, duration, references).
3. Llamar al gateway con payload v1.
4. **No** invocar herramientas ADO directas.

Esto se vigila con un test de contrato sobre el prompt (`tests/test_agent_contracts.py`).

---

## 7. Cambios en UI

### 7.1 Vista detalle

- Mostrar siempre acción **“Cerrar ejecución y publicar”** cuando:
  `ticket.stacky_status == 'completed' AND any(executions where status in {running, queued})`.
- Reemplazar tooltip “EN EJECUCIÓN” por badge `INCONSISTENTE` cuando aplique.
- El botón llama al gateway con `force=false` primero; si responde `409 html_already_published`, ofrecer confirmación para `force=true`.

### 7.2 Vista grafo

- Mismo botón disponible en el nodo del agente.
- Refresh automático tras 200 del gateway (invalidar cache de `useTicketGraph`).

### 7.3 Mensajes de error

- Mapear `error.code` a copy entendible. Nunca mostrar stacktrace al usuario.

---

## 8. Plan de Rescate ADO-149 / EP-013

Implementar como **script reproducible** en `backend/scripts/rescue_execution.py`, no como SQL manual:

```bash
python -m scripts.rescue_execution \
  --ado-id 149 \
  --execution-id 44 \
  --html-path "Agentes/outputs/149/comment.html" \
  --reason "Rescate EP-013 ejecución huérfana" \
  --dry-run
```

Pasos internos (idéntico al gateway, `completion_source=rescue`):

1. Validar HTML.
2. `SELECT FOR UPDATE` sobre ejecución 44.
3. Asociar `html_output_path`.
4. Cerrar ejecución como `completed`.
5. `publish_from_execution(44)`.
6. `on_execution_end()` → transición ADO según workflow.
7. Insertar audit `AgentHtmlPublish + AuditEvent(kind=rescue)`.

Modo `--dry-run` imprime el plan sin escribir. Requiere `--apply` para ejecutar contra ADO real. Confirmación explícita del operador queda registrada con `X-User-Email`.

---

## 9. Plan de Test

### 9.1 Unitarios

- `test_agent_completion_resolves_by_execution_id`
- `test_agent_completion_resolves_by_agent_type_when_unique`
- `test_agent_completion_resolves_when_single_active_mismatched_type`
- `test_agent_completion_rejects_when_zero_active_and_no_rescue_flag`
- `test_agent_completion_idempotent_replay_returns_existing_publish`
- `test_agent_completion_concurrent_callbacks_only_one_publishes` (con locking)
- `test_agent_completion_invalid_html_marks_needs_review`
- `test_agent_completion_auth_required`

### 9.2 Integración

- Ejecutar agente fake que solo escribe HTML + llama gateway → estado final esperado.
- Repetir la misma llamada 3× → un solo comentario en ADO mock.
- ADO mock falla en `update_workitem_state` → ejecución queda `completed`, publicación intentada de nuevo en reaper.

### 9.3 Contract tests

- Parsear `.agent.md` y verificar que el prompt cumple el contrato (no llama herramientas ADO prohibidas, sí llama al gateway).
- Validar `workflow.json` por proyecto contra schema.

### 9.4 Regresión histórica

- Fixture ADO-149: el script de rescate corre en CI sobre snapshot y debe pasar.

### 9.5 UI

- Test E2E: ticket con execution huérfana → botón visible → click → DOM refleja estado limpio.

---

## 10. Observabilidad

- Logs estructurados (JSON) en cada paso del gateway con `correlation_id`, `ticket_id`, `execution_id`, `agent_type`, `step`, `result`.
- Métricas (Prometheus o equivalente):
  - `stacky_agent_completion_total{result, agent_type}`
  - `stacky_agent_completion_duration_seconds`
  - `stacky_publish_idempotent_replay_total`
  - `stacky_execution_orphans_detected_total`
- Auditoría persistente: tabla `AuditEvent` (ya existe en `audit_chain.py`) con `kind in {agent_completion, manual_override, rescue, recovery}`.

---

## 11. Migración / Backfill

1. Migración DB (Alembic):
   - `AgentHtmlPublish` → `UNIQUE(execution_id, html_sha256)`.
   - `AgentExecution.completion_source VARCHAR(20) DEFAULT 'legacy'`.
2. Script `backfill_completion_source.py` para marcar ejecuciones históricas.
3. Job único `recover-stale-status` con flag `--include-historical` para barrer todo `running` previo al deploy.

---

## 12. Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| El gateway publica dos veces por race condition con el reaper. | Media | Alto | UNIQUE constraint + lock + `idempotent_replay`. |
| Algún agente legado sigue invocando `update_workitem_state`. | Alta | Medio | Remover herramienta del allowlist + auditar logs. |
| Workflow ADO de un proyecto no encaja en `workflow.json` declarativo. | Media | Medio | Permitir `transitions.functional.script` (callable Python) como escape hatch. |
| Rollout rompe tickets en vuelo. | Baja | Alto | Feature flag `shadow` + comparación de outcomes durante 1 sprint. |
| HTML válido hoy queda inválido bajo el validador endurecido. | Media | Bajo | Estado `needs_review` + endpoint para re-validar. |

---

## 13. Acceptance Criteria

El trabajo se considera terminado cuando:

- [ ] Ningún agente puede dejar una `AgentExecution` en `running` tras informar finalización exitosa.
- [ ] La publicación ADO ocurre automáticamente desde Stacky al cerrar una ejecución válida.
- [ ] Las transiciones de estado ADO son declarativas y auditables (`workflow.json` + `AuditEvent`).
- [ ] La UI permite recuperar inconsistencias sin tocar base de datos manualmente, tanto en detalle como en grafo.
- [ ] ADO-149 se cierra/publica mediante `scripts/rescue_execution.py --apply` (no SQL manual).
- [ ] Reintentos del mismo callback no duplican comentarios ni publicaciones (verificado por test de integración).
- [ ] Los prompts de agentes no contienen llamadas directas a herramientas de mutación ADO.
- [ ] Métricas y logs del gateway disponibles en dashboard de Stacky.
- [ ] Feature flag puede revertir el flujo a legacy sin downtime.

---

## 14. Fuera de Alcance

- Reescritura del modelo de ejecución (sigue siendo `AgentExecution` actual).
- Cambios en el motor de prompts más allá del contrato de finalización.
- Migración de Jira/Mantis: este plan cubre solo ADO; los otros conectores adoptarán el mismo patrón en un plan derivado.
- UI de administración del `workflow.json` (se edita por PR en este ciclo).

---

## 15. Fases y Secuencia

| Fase | Entregable | Bloquea a | Duración estimada |
|---|---|---|---|
| **P0 — Rescate** | `scripts/rescue_execution.py` + cierre ADO-149. | — | 0.5 día |
| **P1 — Gateway shadow** | Endpoint `agent-completion` corriendo en `shadow`, métricas, logs. | P2 | 2 días |
| **P2 — Idempotencia DB** | Migración `UNIQUE`, `completion_source`, refactor `publish_from_execution`. | P3 | 1 día |
| **P3 — Workflow declarativo** | `workflow.json` + `services/ado_workflow.py` + remoción de tools ADO de prompts. | P4 | 1.5 días |
| **P4 — UI recuperación** | Botón visible/grafo + manejo de `409` + refresh. | P5 | 1 día |
| **P5 — Cutover** | Flag `on`, kill switch a legacy, contracts tests verdes. | — | 0.5 día |

Total estimado: ~6 días-ingeniero + 1 sprint de observación en shadow.

---

## 16. Assumptions

- Stacky permanece como la autoridad única para publicar y cambiar estado ADO.
- Los agentes solo producen evidencia y notifican finalización; nunca escriben ADO.
- Robustez/seguridad/idempotencia priman sobre velocidad de implementación.
- No habrá escrituras directas sobre ADO/DB productiva durante desarrollo sin confirmación explícita por operador.
- La infraestructura actual de `pipeline_lock.py` y `audit_chain.py` es reutilizable.

---

## 17. Apéndice A — Diff resumido del endpoint actual vs propuesto

**Hoy** (`api/tickets.py:392-463`):

- Acepta cualquier `status`.
- No valida HTML.
- Persiste `html_output_path` en la última execution **sin verificar estado**.
- Llama `ts.set_status(...)` directo.
- Responde 200 incluso si el ticket no existe.

**Propuesto** (nuevo `agent-completion`):

- Acepta solo estados terminales válidos del contrato v1.
- Autenticación obligatoria.
- Resuelve ejecución por prioridad documentada.
- Lock + validación + cierre + publish + transición en transacción única.
- Idempotente por `(execution_id, html_sha256)`.
- Devuelve códigos `error.code` machine-readable.
- El legacy `PATCH /stacky-status` queda como **override manual auditado** (`completion_source=manual`), no como vía de cierre de agentes.
