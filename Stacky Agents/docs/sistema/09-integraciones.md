# 09 — Integraciones

← [INDEX](INDEX.md) · hermanos: [06-servicios-daemons](06-servicios-daemons.md) · [02-arquitectura](02-arquitectura.md)

## Issue trackers (entrada y salida)
El proyecto activo define `issue_tracker.type` en `projects/<name>/config.json`. `_startup_sync()` rutea al sync correcto. [V: app.py:62-139]

| Tracker | type | Sync | Cliente | Conf. |
|---------|------|------|---------|-------|
| Azure DevOps (default) | `azure_devops` | `ado_sync.sync_tickets()` + `purge_non_project_tickets` | `services/ado_client`, `project_context.build_ado_client` | [V: app.py:105-139; ado_sync.py docstring] |
| Jira | `jira` | `jira_sync.sync_tickets(tracker_config)` | `services/jira_client` (JiraApiError/JiraConfigError) | [V: app.py:71-86; jira_sync.py docstring] |
| Mantis BT | `mantis` | `mantis_sync.sync_tickets(tracker_config)` | `services/mantis_client` (MantisApiError/MantisConfigError) | [V: app.py:88-103; mantis_sync.py docstring] |

Cada sync devuelve `{project, fetched, created, updated, removed}`. Errores de config se loguean como warning
(sync saltado), errores de API como warning (sync falló), y se sincroniza también on-demand vía `POST /api/tickets/sync`. [V: app.py:75-139; api/tickets.py:503]

### Escritura al tracker (ADO)
- Tasks/comentarios se publican vía outbox idempotente (`AdoWriteOperation`, `AgentHtmlPublish`). [V: db.py:57-58]
- El output_watcher puede auto-crear Tasks si `STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS=true` y hay PAT. [V: app.py:170-177; output_watcher.py docstring]
- Épica desde brief: `POST /api/tickets/epics/from-brief` publica en ADO; el finalizador del runner CLI puede
  auto-publicar (`STACKY_EPIC_AUTOPUBLISH_BACKEND`, default true). [V: tickets.py:5699; config.py:702-704]
- Requiere `ADO_PAT` (`<REDACTADO>`). El preflight grita si falta y auto-create está ON. [V: app.py:170-177; config.py:437]

## Webhooks salientes (`services/webhooks.py`)
- FA-52 — emite eventos a otros sistemas (CI/Slack/dashboards) sin polling al aprobarse una ejecución. [V: webhooks.py docstring]
- Tabla `Webhook` (con columna `format`, default `raw`). [V: db.py:44, db.py:114]
- API de gestión: blueprint `webhooks` bajo `/api/webhooks`. [V: api/__init__.py; webhooks.py:6]
- Evento `digest.ready` lo dispara el digest daemon. [V: app.py:374-378]
- Flag `STACKY_WEBHOOKS_V2_ENABLED`. [V: config.py:303-305]

## Notificaciones desktop (`services/desktop_notifier.py`)
- C10 — capa fina sobre `plyer`/`win10toast` (opcional); notifica al operador cuando un ticket asignado cambia
  a estado relevante (p.ej. "Ready for QA"). [V: desktop_notifier.py docstring 1-5]
- Importado por el runner. [V: agent_runner.py:22]
- Flag `STACKY_DESKTOP_NOTIFY_ENABLED` (default false). [V: config.py:306-308]

## Outputs en filesystem
- Los agentes escriben artifacts en `<repo_root>/Agentes/outputs/` (resuelto por `repo_root()` + `outputs_dir()`). [V: app.py:150-156; runtime_paths.py:99-136]
- En deploy congelado, `repo_root()` usa el `workspace_root` del proyecto activo; sin proyecto activo devuelve un sentinel inexistente (los watchers no escanean). [V: runtime_paths.py:119-135]
- Runtimes CLI dejan `backend/data/codex_runs/<execution_id>/MANIFEST.json` para el manifest_watcher. [V: manifest_watcher.py docstring]
- Nota operativa: la DB viva está en `DeployStackyAgents\data`; los outputs del agente caen en la máquina del operador. [INF: MEMORY stacky-runtime-data-locations]

## Auth / egress
- No hay login/roles real; identidad = header `X-User-Email` sin validar (mono-operador). [V: app.py:422; INF: MEMORY stacky-no-auth-substrate]
- Gateway de agentes usa token simétrico `X-Stacky-Agent-Token` (`STACKY_AGENT_TOKEN`, `<REDACTADO>`) cuando `STACKY_COMPLETION_GATEWAY != off`. [V: config.py:441-452]
- `egress_policies` (FA-41) + `pii_masker` se aplican en el runner. [V: agent_runner.py:22; db.py:53]
