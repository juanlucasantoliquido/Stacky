---
name: Plan SSD — Estado de fases P0-P5
description: Estado del plan de cierre/publicación de agentes Stacky (plan §10_PLAN_CIERRE_PUBLICACION_AGENTES.md)
type: project
---

P0 (Rescate ADO-149): COMPLETADO. Script `backend/scripts/rescue_execution.py` con --dry-run/--apply. Execution 44 rescatada. Branch `fix/stacky-rescue-p0-execution-149` commit `9fe22b8`. NO mergeado a main — incluido en P2.

P1 (Gateway shadow): COMPLETADO. Branch `feat/stacky-gateway-p1-shadow` commit `9539843` en submodulo `Tools/Stacky`. NO mergeado a main — el merge order se decide en P5.

P2 (Idempotencia DB): COMPLETADO. Branch `feat/stacky-idempotency-p2` commit `751c951`. Implementado desde main (independiente de P0/P1).

**Why:** La cadena de cierre de ejecuciones estaba rota: agentes informaban `completed` pero Stacky no cerraba AgentExecution, no publicaba HTML, no sellaba audit. ADO-149/execution-44 es el caso concreto.

P3 (Workflow declarativo + Contrato agente v1): COMPLETADO. Branch `feat/stacky-workflow-p3`. Submodule commit `1d80180` (backend), root commit `bbb7945`. 23 tests verdes. NO mergeado a main.

**How to apply:** Los próximos PRs son P4 (UI recovery), P5 (cutover a on). Merge order: P2 → P3 → P1 → P4 → P5 (P1 gateway puede ir antes o después de P3 — independiente).

Entregables P1 en el branch (NO en main):
- `backend/config.py`: flags STACKY_COMPLETION_GATEWAY y STACKY_AGENT_TOKEN
- `backend/services/agent_completion.py`: gateway service completo
- `backend/api/tickets.py`: handler `agent_completion()` añadido (no modifica legacy)
- `backend/tests/test_agent_completion_gateway.py`: 24 tests, todos green
- `docs/GATEWAY_AGENT_COMPLETION_P1.md`: documentación del gateway

Entregables P2 en branch `feat/stacky-idempotency-p2`:
- `backend/db.py`: migración SQLite-safe UNIQUE + completion_source + dedup pre-constraint
- `backend/models.py`: AgentExecution.completion_source (legacy|agent_gateway|manual|recovery|rescue)
- `backend/services/ado_publisher.py`: idempotent_replay, IntegrityError capturado, _increment_idempotent_replay_counter
- `backend/services/ticket_status.py`: _set_status_inner escribe completion_source según trigger
- `backend/api/tickets.py`: PATCH stacky-status acepta execution_id + metadata.trigger
- `backend/scripts/rescue_execution.py`: persiste completion_source='rescue' en DB
- `backend/scripts/backfill_completion_source.py`: clasifica ejecuciones históricas
- `backend/tests/test_idempotency_p2.py`: 13 tests (M01-M04, P01-P03, B01-B03, R01, G01, L01) — todos verdes
- `docs/IDEMPOTENCY_P2.md`: documentación completa

Backfill dry-run resultado en dev (2026-05-14):
  execution 44 (ADO-149) clasificada como 'rescue' (encontró SystemLog source=rescue_execution).

Constraint DB: `uq_agent_html_publish_execution_sha` en `agent_html_publish(execution_id, html_sha256)`.

Entregables P3 en branch `feat/stacky-workflow-p3`:
- `backend/services/ado_workflow.py`: motor transición declarativo (cache thread-safe, escape hatch script:fn, applied/idempotent_noop/fallback/skipped)
- `backend/projects/PACIFICO/workflow.json`: functional→Doing, technical→To Do, developer→Resolved, qa→Reviewed by QA, ui_qa→Done by AI
- `backend/projects/_schemas/workflow.schema.json`: JSON Schema draft-07 para validación CI
- `backend/services/agent_contract.py`: validador contrato v1 (stacky_agent_type, completion_contract:v1, no ADO mutation en cuerpo, instrucciones HTML+notificación)
- `backend/services/ticket_status.py`: on_execution_end refactorizado — retorna dict con target_ado_state, decision, source
- `backend/tests/test_ado_workflow.py`: 15 tests W01-W15
- `backend/tests/test_agent_contracts.py`: 8 tests C01-C08
- `backend/projects/PACIFICO/config.json`: corrige typo AnalistaFuncionlPacifico → AnalistaFuncionalPacifico
- `docs/AGENT_CONTRACT_V1.md` + `docs/WORKFLOW_DECLARATIVO_P3.md`

Agentes root repo actualizados con frontmatter P3:
- TechnicalAnalyst.agent.md: stacky_agent_type: technical
- AnalistaFuncionalPacifico.agent.md: stacky_agent_type: functional
- DevPacifico.agent.md: stacky_agent_type: developer
- QAUat1.agent.md (renombrado de PROMPT.agent.md): stacky_agent_type: qa

Nota P3: developer→Resolved necesita revisión del equipo (no tenía transition_state en config.json original).
Nota P3: AnalistaFuncional tiene excepción documentada — ADO creation tools en frontmatter son legítimos; contrato solo valida mutación de estado en cuerpo del prompt.

P4 (UI recuperación): COMPLETADO. Branch `feat/stacky-ui-recovery-p4` commit `2eb731c`. Desde `feat/stacky-gateway-p1-shadow` (P1). 11 archivos, 1213 inserciones.

Entregables P4:
- `frontend/src/utils/agentCompletionErrors.ts`: mapeo canónico 8 error.code → copy UI
- `frontend/src/utils/inconsistencyDetector.ts`: detección pura INCONSISTENTE (stacky_status=completed + running/queued execution)
- `frontend/src/components/RecoverExecutionButton.tsx`: botón con flujo 200/409-html_already_published/force=true/error
- `frontend/src/components/RecoverExecutionButton.module.css`: estilos amber
- `frontend/src/api/client.ts`: rawPost() para manejo de 4xx sin throw
- `frontend/src/api/endpoints.ts`: namespace AgentCompletion.complete()
- `frontend/src/pages/TicketBoard.tsx`: badge INCONSISTENTE + RecoverExecutionButton en TicketCard (vista detalle)
- `frontend/src/components/TicketGraphView.jsx`: badge INCONSISTENTE + RecoverExecutionButton compact en nodo grafo
- `frontend/src/utils/__tests__/`: 3 archivos test vitest (listos, vitest pendiente instalación)

FIX PENDIENTE (no aplicado en P4):
  workflow.json PACIFICO: `transitions.developer.to` debe cambiar de "Resolved" a "Done by AI".
  El branch `feat/stacky-workflow-p3` no estaba disponible en el worktree de P4.
  Acción: aplicar el cambio directamente en el branch `feat/stacky-workflow-p3` antes del merge:
    Archivo: `backend/projects/PACIFICO/workflow.json`
    Campo: `transitions.developer.to`
    Valor actual: "Resolved"
    Valor correcto: "Done by AI"
    Commit sugerido: `fix(workflow): developer agent transitions to 'Done by AI' instead of 'Resolved'`

BLOQUEOS PENDIENTES PARA P5:
  B1: vitest no instalado → tests no corren. Instalar: `npm install --save-dev vitest`.
  B2: VITE_STACKY_AGENT_TOKEN no configurado en .env del frontend → botón recibirá 401 del gateway.
  B3: CORS del backend en P1 no verifica si acepta X-Stacky-Agent-Token desde browser (origen http://localhost:5173).
  B4: Merge order: P2 → P3 (con fix developer→Done by AI) → P1 → P4 → P5.

**How to apply:** P5 puede arrancar desde P4. Solo cutover del feature flag STACKY_COMPLETION_GATEWAY a 'on'.
Merge order final: P2 → P3 → P1 → P4 → P5.
