# 03 — Modelo de datos

← [INDEX](INDEX.md) · hermanos: [02-arquitectura](02-arquitectura.md) · [04-api](04-api.md)

Todas las clases viven en `backend/models.py` y heredan de `db.Base` (SQLAlchemy DeclarativeBase). La DB es
SQLite por defecto (`data/stacky_agents.db`), con migración aditiva segura. [V: db.py:8-19, config.py:58-60]

> Nota: `models.py` define **9** clases ORM. Pero `db.init_db()` importa además ~30 modelos definidos
> dentro de `backend/services/*` (output_cache, anti_patterns, webhooks, decisions, glossary, memoria
> colaborativa, PM suite, etc.). Acá se documentan las 9 centrales de `models.py`; el resto se enumera al final. [V: db.py:40-80]

## Tablas centrales (`models.py`)

### `tickets` — `Ticket` [V: models.py:38-98]
Espejo local del work item del tracker. Campos: `id` (PK), `ado_id` (NOT NULL), `external_id`, `project` (NOT NULL, guarda tracker_project), `stacky_project_name`, `tracker_type` (default `azure_devops`), `title` (NOT NULL), `description`, `ado_state`, `ado_url`, `priority`, `work_item_type` (Epic/Task/Bug…), `parent_ado_id`, `last_synced_at`, `created_at`, `stacky_status` (idle|running|completed|error|cancelled, default `idle`), `assigned_to_ado`.
Relación: `executions` → `AgentExecution` (1:N).
Índices: `ix_tickets_project_state`, `ix_tickets_stacky_project`, único `ux_tickets_stacky_tracker_external (stacky_project_name, tracker_type, external_id)`.

### `users` — `User` [V: models.py:101-129]
`id` (PK), `email` (único, NOT NULL), `name`, `created_at`, `ado_unique_name` (único), `ado_display_name`, `skills_json` (JSON list), `area_paths_json` (JSON list), `max_active_tickets` (default 5).

### `ticket_state_history` — `TicketStateHistory` [V: models.py:132-169]
Transiciones de `ado_state`. `id`, `ticket_id` (FK→tickets, ondelete CASCADE), `ado_id`, `stacky_project_name`, `old_state`, `new_state` (NOT NULL), `assigned_to_ado`, `recorded_at`. Índices por ticket, proyecto+fecha, asignado, fecha.

### `pack_runs` — `PackRun` [V: models.py:172-204]
Ejecución de un "pack" (workflow multi-step). `id`, `pack_definition_id` (NOT NULL), `ticket_id` (FK), `status` (NOT NULL), `current_step` (default 1), `options_json`, `started_by` (NOT NULL), `started_at`, `completed_at`. Property `options` (de/serializa JSON).

### `agent_executions` — `AgentExecution` [V: models.py:207-302]
Núcleo: una corrida de un agente. `id`, `ticket_id` (FK NOT NULL), `agent_type` (NOT NULL), `status` (NOT NULL), `verdict`, `input_context_json` (NOT NULL), `chain_from_json`, `output`, `output_format` (default markdown), `metadata_json`, `contract_result_json`, `error_message`, `started_by` (NOT NULL), `started_at`, `completed_at`, `pack_run_id` (FK), `pack_step`, `html_output_path`, `completion_source` (agent_gateway|manual|output_watcher|rescue…). Relación inversa `ticket`. Properties JSON: `input_context`, `chain_from`, `metadata_dict`, `contract_result`. `duration_ms()` calcula la duración. Índices: por ticket+fecha, ticket+agente+status, pack_run, status+fecha.

### `pipeline_runs` — `PipelineRun` [V: models.py:305-341]
Pipeline multi-etapa por ticket. `id`, `ticket_id` (FK), `project`, `stages_json` (NOT NULL, default `[]`), `current_stage` (default 0), `status` (default running), `last_execution_id`, `created_at`, `updated_at`. Índice `ix_pipeline_ticket_status`.

### `execution_logs` — `ExecutionLog` [V: models.py:344-368]
Logs por ejecución. `id`, `execution_id` (FK→agent_executions, CASCADE), `timestamp`, `level` (NOT NULL), `message` (NOT NULL), `group_name`, `indent` (default 0). Índice `ix_logs_exec_ts`.

### `system_logs` — `SystemLog` [V: models.py:371-456]
Log estructurado system-wide (HTTP, agentes, servicios, errores, frontend). `id`, `timestamp` (NOT NULL), `level` (NOT NULL), `source` (NOT NULL), `action` (NOT NULL), `execution_id`, `ticket_id`, `user`, `request_id` (UUID), `method`, `endpoint`, `status_code`, `duration_ms`, `input_json`/`output_json`/`error_json`/`context_json`/`tags_json`. Sin FK (las correlaciones pueden no existir). 6 índices. Payloads truncados (input/output ≤16KB, error ≤64KB). [V: models.py:401-403 comentarios]

### `agent_prompt_versions` — `AgentPromptVersion` [V: models.py:459-489]
Historial auditable de prompts `.agent.md` (que están gitignored). `id`, `filename`, `sha256`, `body` (NOT NULL), `imported_at`, `source` (import_endpoint|fs_scan). Único `(filename, sha256)`.

### `eval_runs` — `EvalRun` [V: models.py:492-525]
Historial de corridas de evals golden. `id`, `ran_at`, `agent_type`, `passed`, `failed`, `scores_json`, `prompt_sha`.

## Migración SQLite (`db._migrate_add_columns`) [V: db.py:85-133]
- `init_db()` hace `Base.metadata.create_all(engine)` y luego ALTER TABLE add-only para columnas que pueden faltar en DBs viejas (lista explícita en `db.py:89-119`).
- Backfill de columnas multi-proyecto en `tickets`, rebuild de la tabla `tickets` si falta el índice único nuevo, backfill de `ticket_state_history`, y creación idempotente de índices de `agent_html_publish`. [V: db.py:130-277]
- `:memory:` se remapea a shared-cache para que threads en background vean los datos. [V: db.py:21-24]

## Modelos definidos en services/ (creados por `init_db`)
`OutputCache`, `AntiPattern`, `Webhook`, `Decision`, `TranslationCache`, `GlossaryEntry`/`GlossaryCandidate`, `DriftAlert`, `AuditEntry`, `ProjectConstraint`, `UserStyleProfile`, `SpecExecution`, `EgressPolicy`, `Macro`, `ExecutionEmbedding`, `PipelineInferenceCache`, `AgentHtmlPublish`, `AdoWriteOperation`, `TicketStatusEvent`, PM suite (`PmSprintSnapshot`, `PmRiskItem`, `PmWorkItemComment`, `PmAiUsage`, `PmAiRecommendation`), `DocChunk`, memoria colaborativa (`StackyMemoryObservation`, `StackyMemoryRelation`, `StackyMemoryFinding`, `StackyMemoryValidationRun`, `StackyMemorySyncChunk`, `StackyMemorySyncOutbox`). [V: db.py:42-80]
Sus campos exactos no se documentan acá (viven en sus módulos) — marcados [NV] hasta auditarlos. [NV]
