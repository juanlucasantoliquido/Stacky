# 12 — Subsistema DevOps (pipelines, servidores, migración, publicación)

← [INDEX](INDEX.md) · hermanos: [04-api](04-api.md) · [06-servicios-daemons](06-servicios-daemons.md) · [09-integraciones](09-integraciones.md)

Suite construida por los planes 72-116 (GitLab CI, panel DevOps, servidores, doctores, consola remota).
Toda la superficie cuelga de blueprints `devops*`/`ci`/`pipeline-generator`/`migrator` bajo `/api`. Las tabs del
SPA (`devops`, `migrador`) aparecen solo si el flag de backend está ON. [V: frontend/src/App.tsx:94-102]

## Blueprints y prefijos [V: api/__init__.py:42-111]
| Blueprint | Prefijo `/api…` | Plan | Rol |
|-----------|-----------------|------|-----|
| `ci` | `/ci` | 72 | Trigger/monitor CI (HITL) |
| `pipeline_generator` | `/pipeline-generator` | 73 | Genera `PipelineSpec`→YAML declarativo |
| `migrator` | `/migrator` | 74 | Migrador ADO→GitLab idempotente |
| `devops` | `/devops` | 87 | Panel: creador gráfico de pipelines + health/flags |
| `devops_agent` | `/devops/agent` | 90 | Agente DevOps interactivo multi-turno |
| `devops_servers` | `/devops/servers` | 91 | Registro de servidores/alias/credenciales |
| `devops_variables` | `/devops/variables` | 94 | Caja fuerte de variables secretas de pipeline |
| `devops_production` | `/devops/production` | 95 | Llevar a producción: MR/PR paridad ADO |
| `devops_section_doctor` | `/devops/sections` | 104 | Doctores IA por sección |
| `devops_remote_console` | `/devops/console` | 105 | Consola remota de prompts por servidor |
| `devops_connections` | `/devops/connections` | 116 | Doctor de conexiones + remediación guiada |

`GET /api/devops/health` devuelve el estado de ~18 sub-flags (`publications_enabled`, `servers_enabled`,
`agent_enabled`, `production_enabled`, `doctor_enabled`, `remote_console_enabled`, `connection_doctor_enabled`…). [V: api/devops.py:39-63]

## Servicios de soporte [V: ls backend/services | grep gitlab/pipeline/migrator/remote_exec]
- **GitLab**: `gitlab_client`, `gitlab_provider`, `gitlab_ci_provider`, `gitlab_ci_logs`, `gitlab_variables`, `gitlab_preflight`, `gitlab_deep_links`. [V: services/gitlab_*.py]
- **Pipelines**: `pipeline_spec`, `pipeline_renderers`, `pipeline_orchestrator`, `pipeline_preflight`, `pipeline_status`, `pipeline_stack_detector`; ADO: `ado_pipeline_definitions`, `ado_pipeline_inference`. [V: services/pipeline_*.py, ado_pipeline_*.py]
- **Migración**: `migrator_core`, `migrator_epics`, `migrator_attachments`, `migrator_executor`, `migrator_map`, `migrator_verify`. [V: services/migrator_*.py]
- **Ejecución remota**: `remote_exec` es el ÚNICO módulo que ejecuta comandos remotos; la credencial viaja SOLO por env del proceso hijo `powershell.exe` y toda corrida se audita (éxito o error) antes de devolver. [V: services/remote_exec.py:1-4]

## Flags (default ON) [V: config.py:960-1067]
`STACKY_DEVOPS_PANEL_ENABLED`, `_PUBLICATIONS_ENABLED`, `_ENVIRONMENTS_ENABLED`, `_AGENT_ENABLED`,
`_SERVERS_ENABLED`, `_PREFLIGHT_ENABLED`, `_PRODUCTION_ENABLED`, `_DOCTOR_ENABLED`, `_VARIABLES_ENABLED`,
`_STACK_DETECT_ENABLED`, `_BOOTSTRAP_ENABLED`, `_SECTION_DOCTOR_ENABLED`, `_REMOTE_CONSOLE_ENABLED`,
`_REMOTE_TARGET_ENABLED`, `_CONNECTION_DOCTOR_ENABLED`, `_ENV_TREE_PREVIEW_ENABLED`, `_ENV_SANDBOX_ENABLED` — todos default `"true"`. [V: config.py:960-1067]
> Familia promovida a default ON por directiva (patrón triple). [INF: MEMORY flags-devops-93-108-default-on]

## Límites / seguridad
- Secretos de pipeline y credenciales de servidor: `<REDACTADO>`; nunca se copian a doc ni salen en respuestas. [V: remote_exec.py:3 riel §3.1]
- El detalle endpoint-por-endpoint de cada blueprint DevOps no se enumera acá. [NV]
- Prior art de scripts de deploy/compare vive fuera del repo (`RSPACIFICO/pipelines`). [INF: MEMORY rspacifico-dbcompare-scripts-prior-art]

## No cubierto en esta rama
El "Centro de Despliegues multi-destino + rollback 1-click" (plan 120) NO tiene blueprint ni servicio en
`plans-138-141-serie-ux-ui`: fue implementado en otra rama sin mergear. [V: grep sin resultados deploy/rollback en services; INF: MEMORY plan-120-status] → documentar cuando se integre.
