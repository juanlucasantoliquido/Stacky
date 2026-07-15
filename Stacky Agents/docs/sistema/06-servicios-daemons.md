# 06 — Servicios y Daemons

← [INDEX](INDEX.md) · hermanos: [02-arquitectura](02-arquitectura.md) · [08-configuracion-flags](08-configuracion-flags.md)

`backend/services/` tiene 137 módulos. [V: ls services | wc -l = 137] Acá se documentan los que `app.py`
arranca/importa en boot (los que tienen impacto operativo directo). El resto queda [NV] hasta auditarlo.

## Daemons que arranca `create_app()`
| Servicio | Función de arranque | Disparador / flags | Conf. |
|----------|---------------------|--------------------|-------|
| Orphan reaper | `orphan_reaper.start_background_reaper()` | `STACKY_ORPHAN_REAPER_ENABLED` (def true), `STACKY_ORPHAN_REAPER_INTERVAL_SEC` (def 0=solo boot) | [V: app.py:251-256; config.py:562-570; orphan_reaper.py docstring] |
| Stale recovery guardian | `ticket_status.schedule_stale_recovery(interval)` | `STACKY_REAPER_ENABLED` (def true), `STACKY_REAPER_INTERVAL_SECONDS` (def 120) | [V: app.py:299-304] |
| Manifest watcher | `manifest_watcher.start_manifest_watcher(poll)` | `STACKY_MANIFEST_WATCHER_ENABLED` (def true), `..._INTERVAL_SECONDS` (def 2.0) | [V: app.py:312-317; manifest_watcher.py docstring] |
| Output watcher | `output_watcher.start_output_watcher(poll)` | `STACKY_OUTPUT_WATCHER_ENABLED` (def true), `..._INTERVAL_SECONDS` (def 3.0) | [V: app.py:326-331; output_watcher.py docstring] |
| Evals scheduler | `eval_history.schedule_evals(h)` | `STACKY_EVALS_INTERVAL_HOURS` (def 0=off) | [V: app.py:342-347] |
| Digest daemon | thread `stacky-digest-daemon` → `webhooks.fire("digest.ready", ...)` | `STACKY_DIGEST_INTERVAL_HOURS` (def 0=off) | [V: app.py:366-382] |
| Memory review daemon | thread `stacky-memory-review-daemon` → `memory_store.mark_stale_for_review()` | `STACKY_MEMORY_REVIEW_SWEEP_HOURS` (def 0=off) | [V: app.py:386-406] |

## Watchers de cierre de runs (qué resuelven)
- **output_watcher** — el flujo `/api/agents/open-chat` arranca un agente en VS Code Copilot Chat; la
  `AgentExecution` queda `running` y debería cerrarse cuando el agente PATCHea `stacky-status`. Si no lo hace,
  el watcher detecta artifacts en `Agentes/outputs/` y cierra el run (y, según flag, crea Tasks). [V: output_watcher.py docstring 1-6; config.py:170-177 auto-create]
- **manifest_watcher** — polea `backend/data/codex_runs/<id>/MANIFEST.json`; si está terminal pero la
  ejecución sigue `running`/`queued`, dispara el cierre. [V: manifest_watcher.py docstring 1-5]
- **orphan_reaper** — reconcilia executions `running` sin heartbeat reciente (boot + periódico). [V: orphan_reaper.py docstring 1-5]
- **stale recovery** — `recover_stale_running_tickets` corrige tickets stale + executions con timeout. [V: app.py:280-304]

## Servicios de sincronización con trackers
| Servicio | Interfaz | Conf. |
|----------|----------|-------|
| `ado_sync.sync_tickets()` | sync de work items ADO ↔ DB; `purge_non_project_tickets` limpia tickets ajenos | [V: ado_sync.py docstring; app.py:121-133] |
| `jira_sync.sync_tickets()` | mismo contrato para Jira | [V: jira_sync.py docstring; app.py:72-86] |
| `mantis_sync.sync_tickets()` | mismo contrato para Mantis BT | [V: mantis_sync.py docstring; app.py:89-103] |
El selector está en `_startup_sync()`: lee `issue_tracker.type` del proyecto activo. [V: app.py:55-139]

## Servicios usados por el runner (importados en agent_runner.py)
`audit_chain, confidence, desktop_notifier, egress_policies, embeddings, llm_router, output_cache, pii_masker, webhooks`;
`project_context.{resolve_project_context, ensure_project_vscode, build_ado_client}`; `run_slots` (cap de concurrencia V0.3); `run_preflight` (gate G0.1). [V: agent_runner.py:22-23,105,286-287]

## Otros servicios mencionados en el boot
- `stacky_agents.materialize_agents()` — resolver canónico de `.agent.md`. [V: app.py:204; stacky_agents.py docstring]
- `db_backup.ensure_weekly_backup()` — backup semanal de la DB. [V: app.py:220-228]
- `demo_seed.seed_demo_project()` — seed idempotente de demo. [V: app.py:231-236]
- `flow_config_store.seed_defaults_if_empty()` — reglas iniciales de flow. [V: app.py:241-246]
- `pipeline_orchestrator.register_ticket_status_hook()` — avance de pipeline al finalizar ejecuciones (U2.1). [V: app.py:356-362]
- `harness_profiles.apply_profile(profile)` — aplica perfil del arnés en boot (off/safe/full). [V: app.py:258-271]

## Subsistemas con doc propia (familias de servicios)
Estas familias de `backend/services/` tienen documento dedicado (no se repiten acá):
- **DevOps** (`gitlab_*`, `pipeline_*`, `migrator_*`, `remote_exec`, `ado_pipeline_*`) → [12-devops](12-devops.md). [V: ls services]
- **Docs/RAG/grafo** (`doc_indexer`, `doc_graph`, `docs_rag`, `rag_retriever`, `lexical_core`) → [13-docs-rag-grafo](13-docs-rag-grafo.md). [V: ls services]
- **DB Compare** (`dbcompare_*`) → [14-db-compare](14-db-compare.md). [V: ls services]

## No cubierto (alcance)
Los servicios restantes (memoria colaborativa, PM suite, evals, contract validation, exec
verification, glossary, etc.) no se documentan módulo-a-módulo acá. Muchos se gobiernan por flags `STACKY_*`
listados en [08-configuracion-flags](08-configuracion-flags.md). Detalle por servicio: [NV].
