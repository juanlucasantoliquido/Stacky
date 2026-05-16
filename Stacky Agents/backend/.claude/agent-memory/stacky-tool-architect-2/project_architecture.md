---
name: Stacky Agents — Contratos y rutas clave del codebase
description: Rutas, modelos, servicios y patrones arquitectónicos verificados en el codebase actual
type: project
---

**Why:** Necesario para implementar features sin reinventar contratos existentes.

**Modelos ORM verificados:**
- `AgentExecution` → `backend/models.py:121` (campos: status, html_output_path, completed_at, started_by, started_at, agent_type, ticket_id, completion_source[P2])
- `AgentHtmlPublish` → `backend/services/ado_publisher.py:45` (execution_id, ticket_id, ado_id, html_sha256, status, triggered_by) + UNIQUE(execution_id, html_sha256)[P2]
- `SystemLog` → `backend/models.py:245` (source, action, context_json, tags_json, ticket_id, execution_id, correlation via request_id)
- `Ticket` → `backend/models.py:37` (ado_id UNIQUE, stacky_status, project)

**Servicios clave:**
- `publish_from_execution(execution_id, *, triggered_by=..., force=False)` → `backend/services/ado_publisher.py:112` (P2: idempotente vía UNIQUE DB; segunda llamada con mismo sha → status='idempotent_replay', no 'skipped')
- `on_execution_end(ticket_id, execution_id, final_status, agent_type)` → `backend/services/ticket_status.py:318`
- `audit_chain.seal(execution_id)` → `backend/services/audit_chain.py:107`
- `agent_html_output.read_and_validate(ado_id, hint)` → `backend/services/agent_html_output.py:133`

**Patrones:**
- SystemLog se escribe via `stacky_logger` (async queue) O directamente con `session.add(SystemLog(...))`. En contextos con riesgo de deadlock SQLite (gateway), usar sesión separada (session=None en _emit_system_log).
- `_emit_system_log(session=None)` abre su propia session_scope.
- DB SQLite compartida en tests: usar `flush_now()` del logger antes de leer system_logs para evitar lock contention.
- Tests: ado_ids ficticios > 99000 para no colisionar con el startup ADO sync.

**Endpoint legacy a preservar:**
- `PATCH /api/tickets/by-ado/{ado_id}/stacky-status` → `backend/api/tickets.py:392` (no modificar — es el override manual auditado).

**Feature flags activos:**
- `STACKY_COMPLETION_GATEWAY` (off|shadow|on) — leído dinámicamente en cada request vía `os.getenv`.
- `STACKY_AGENT_TOKEN` — token simétrico para auth del gateway.
