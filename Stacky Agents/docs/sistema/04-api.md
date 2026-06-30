# 04 — API

← [INDEX](INDEX.md) · hermanos: [02-arquitectura](02-arquitectura.md) · [05-agentes-runtimes](05-agentes-runtimes.md)

Toda la API cuelga de `api_bp` con `url_prefix="/api"`. Los blueprints se registran en `backend/api/__init__.py`. [V: api/__init__.py:43-83]
Health check: `GET /api/health` → `{"ok": true}`. [V: api/__init__.py:85-87]

## Blueprints registrados (prefijo efectivo = `/api` + url_prefix del bp)
| Blueprint | url_prefix | Archivo | Conf. |
|-----------|-----------|---------|-------|
| tickets | `/tickets` | api/tickets.py | [V: tickets.py:35] |
| executions | `/executions` | api/executions.py | [V: executions.py:22] |
| agents | `/agents` | api/agents.py | [V: agents.py:25] |
| chat | `/chat` | api/chat.py | [V: chat.py:37] |
| evals | `/evals` | api/evals.py | [V: evals.py:16] |
| packs | `/packs` | api/packs.py | [V: packs.py:11] |
| similarity | `/similarity` | api/similarity.py | [V: similarity.py:8] |
| anti_patterns | `/anti-patterns` | api/anti_patterns.py | [V: anti_patterns.py:7] |
| webhooks | `/webhooks` | api/webhooks.py | [V: webhooks.py:6] |
| decisions | `/decisions` | api/decisions.py | [V: decisions.py:7] |
| git | `/git` | api/git.py | [V: git.py:6] |
| glossary | `/glossary` | api/glossary.py | [V: glossary.py:7] |
| logs | `/logs` | api/logs.py | [V: logs.py:26] |
| memory | `/memory` | api/memory.py | [V: memory.py:16] |
| pm | `/pm` | api/pm.py | [V: pm.py:52] |
| preferences | `/preferences` | api/preferences.py | [V: preferences.py:12] |
| qa_browser | `/qa-browser` | api/qa_browser.py | [V: qa_browser.py:33] |
| qa_uat | `/qa-uat` | api/qa_uat.py | [V: qa_uat.py:50] |
| pipelines | `/pipelines` | api/pipelines.py | [V: pipelines.py:8] |
| metrics | `/metrics` | api/metrics.py | [V: metrics.py:29] |
| reports | `/reports` | api/reports.py | [V: reports.py:9] |
| diag | `/diag` | api/diag.py | [V: diag.py:36] |
| docs | `/docs` | api/docs.py | [V: docs.py:28] |
| docs_rag | `/docs-rag` | api/docs_rag.py | [V: docs_rag.py:30] |
| flow_config | `/flow-config` | api/flow_config.py | [V: flow_config.py:35] |
| ui_sections | `/ui-sections` | api/ui_sections.py | [V: ui_sections.py:26] |
| agent_roles | `/agent-roles` | api/agent_roles.py | [V: agent_roles.py:25] |
| ado_manager, adoption, config_transfer, client_profile, db_query, extras, global_config, harness_flags, phase4, phase5, phase6, projects | `""` (rutas absolutas bajo `/api`) | varios | [V: grep Blueprint: ado_manager.py:37, adoption.py:25, projects.py:64, global_config.py:30, harness_flags.py:21, phase4-6, extras.py:14, config_transfer.py:49, client_profile.py:53, db_query.py:34] |

> Nota: `phase4/5/6`, `projects`, `global_config`, `extras`, `client_profile`, `config_transfer`, `db_query`,
> `ado_manager`, `adoption`, `harness_flags` usan `url_prefix=""`; sus rutas concretas no se enumeran acá. [NV]

## tickets (`/api/tickets`) — endpoints clave [V: tickets.py grep @bp]
| Método · ruta | Función |
|---------------|---------|
| GET `/hierarchy` | árbol de tickets |
| GET `` | lista de tickets |
| POST `/sync`, GET `/sync/status` | sync de tickets desde el tracker |
| POST `/sync-v2`, GET `/sync/status-v2` | sync v2 |
| GET `/<id>` | detalle de ticket |
| GET `/<id>/pipeline-status`, `/pipeline`, `/ado-pipeline-status` | pipeline del ticket |
| POST `/ado-pipeline-batch`, DELETE `/<id>/ado-pipeline-cache` | batch / cache de pipeline ADO |
| GET `/<id>/fingerprint`, `/glossary`, `/comments`, `/attachments` | metadatos del ticket |
| GET/PATCH `/<id>/stacky-status`, PATCH `/by-ado/<ado_id>/stacky-status` | estado interno Stacky |
| POST `/by-ado/<ado_id>/agent-completion` | cierre por gateway de agente |
| POST `/recover-stale-status` | recuperar estados colgados |
| POST `/<id>/finish-work` | cierre del trabajo del ticket |
| GET `/by-ado/<ado_id>/pending-tasks`, `/artifact-status` | artifacts pendientes |
| GET `/unblocker-board` | tablero del desatascador |
| POST `/by-ado/<ado_id>/rescue-artifact`, `/create-child-task` | rescatar artifact / crear Task hija |
| POST `/<id>/assignment-recommendations`, `/assign` | asignación |
| GET `/user-stats`, `/ado-user`; POST `/users/sync-from-ado` | usuarios |
| GET `/<id>/diagnostics`, DELETE `/<id>/diagnostics/cache` | diagnóstico |
| GET `/config/frontend` | config para el frontend |
| POST `/<ado_id>/prewarm` | pre-warm de caché ADO (I0.3) |
| **POST `/epics/from-brief`** | publicar épica derivada de brief en ADO (gated `STACKY_EPIC_FROM_BRIEF_ENABLED`) [V: tickets.py:5699; config.py:695-697] |

## executions (`/api/executions`) [V: executions.py grep @bp]
GET `` (lista) · GET `/<id>` · GET `/<id>/logs` · POST `/<id>/input` · GET `/<id>/logs/stream` (SSE) · POST `/<id>/approve` · POST `/<id>/discard` · GET `/history` (gated `STACKY_EXECUTION_HISTORY_ENABLED`) · POST `/<id>/publish-to-ado` · GET `/<id>/diff/<other_id>` · POST `/<id>/cancel` · DELETE `/<id>` · DELETE `/bulk-by-ticket` · POST `/<id>/answer` · GET/DELETE `/<id>/output-files`. [V: executions.py:26-550; config.py:426-428]

## agents (`/api/agents`) [V: agents.py grep @bp]
GET `` (lista de agentes) · POST `/validate-artifact` · GET `/vscode`, `/stacky/manifest` · POST `/stacky/materialize`, `/stacky/import` · GET `/vscode/<file>/history`, `/<file>/versions`, `/<file>/versions/diff`, `/advise` · **POST `/run`** (despacho de agente al runtime) · **POST `/run-brief`** (Business Agent con brief, sin ticket real) · GET `/autoprofile/<project>` (gated) · POST `/route` · GET `/models` · GET `/<agent_type>/schema`, `/system-prompt` · GET `/next-suggestion` · POST `/cancel/<id>` · POST `/estimate` · POST `/open-chat` (lanza agente en VS Code Copilot Chat). [V: agents.py:28-830]

### Contrato `POST /api/agents/run-brief` [V: agents.py:564-669]
Body: `{brief (req), runtime, project, vscode_agent_filename, model, effort}`.
- `model`: si viene, pasa por `clamp_model(model, allow_opus=True)` → brief→épica admite Opus 4.8. [V: agents.py:586-592]
- `effort`: oficial `{low,medium,high,xhigh,max}`, default `high`; luego `_clamp_effort_for_model`. [V: agents.py:594-598]
- Crea/reusa "Brief Pool Ticket" (`ado_id=-1` por proyecto) y delega a `run_agent(agent_type="business", ...)`. [V: agents.py:604-650]
- Salidas: `202 {execution_id, status:"running"}`; `400` si falta brief / agente desconocido; `502 {ok:false,error:"agent_launch_failed"}` ante fallo de lanzamiento (nunca 500 genérico). [V: agents.py:578-669]

## Middleware transversal
Cada request recibe `request_id` y se loguea en `system_logs` (excepto `/api/health` y body de `/api/logs/frontend`). Excepciones no manejadas → 500 con `request_id`, logueadas. [V: app.py:408-467]
