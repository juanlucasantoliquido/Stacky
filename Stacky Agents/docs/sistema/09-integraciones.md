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

## GitLab — TLS de la sonda, errores tipados y match de webhooks (Plan 295)

### El TLS de la sonda de configuración
- `run_gitlab_checks` monta el adaptador OpenSSL del plan 276 (`gitlab_client._AdaptadorOpenSSL`) con el
  `ca_bundle` del proyecto, sobre una `requests.Session` propia y **sólo para el prefijo de ese host**.
  [V: services/gitlab_setup_check.py:_sesion_para]
- **Por qué `verify=<bundle>` NO alcanza:** `app.py:26` llama `truststore.inject_into_ssl()`, que reemplaza
  `ssl.SSLContext` para **todo el proceso** — necesario por la inspección TLS de la red, y letal para un GitLab
  interno (verifica por Windows CryptoAPI e ignora `VERIFY_X509_PARTIAL_CHAIN`). Por eso el `requests.get()`
  pelado que tenía esta sonda **nacía roto**. [V: services/tls_openssl_context.py:3-13]
- El bundle se resuelve con `tls_pinning.resolver_ca_bundle` (parámetro > `STACKY_GITLAB_CA_BUNDLE` >
  `REQUESTS_CA_BUNDLE`), igual que el cliente: saltearlo haría que la sonda hable **otro TLS** que el sync.
- Chequeo nuevo `chk-tls`, **antes** de `chk-instancia` (el handshake ocurre antes de que exista un status HTTP).
  Distingue **certificado** de **red**: antes un cert que no cerraba salía como `chk-instancia = fail`
  "No se pudo llegar a esa dirección" — culpaba a la red con el sync funcionando.
- `run_gitlab_checks` devuelve **SIEMPRE 6 resultados** (eran 5) en **todos** sus caminos de salida: la UI pinta
  la lista que recibe. Flag reusada: `STACKY_GITLAB_TLS_ADAPTER_ENABLED` (OFF ⇒ sesión pelada, conducta previa).

### Los errores de la API de GitLab
- `TrackerApiError` **NO es hermana** de `AdoApiError`: deriva de `TrackerError(RuntimeError)`
  [V: services/tracker_provider.py:46,52-57]. Por eso la lista de `except` de `/sync` y `/sync-v2` **se veía
  completa sin estarlo** y un PAT vencido salía como `500 {"error":"unexpected"}`.
- Ahora hay `_gitlab_sync_error_response`, simétrico a `_ado_sync_error_response`: **502** + `kind` + copy
  accionable que nombra GitLab. Los **siete** `kind` reales tienen copy propio —
  `auth`, `not_found`, `rate_limited`, `server`, `tls`, `network` y **`unknown`** (el default de
  `TrackerApiError.__init__` y lo que `_kind_for_status` devuelve para 400/409/422).
- **`.status`, NO `.status_code`**: ese segundo nombre es de `AdoApiError`; confundirlos hace que el handler
  lea `None` siempre.
- Breaker propio `"gitlab_sync"`, cuya key de proyecto es **`stacky_project_name`**, nunca `ado_breaker_project`:
  en GitLab el token, la URL y el `ca_bundle` son **por proyecto**. Sólo abren los `kind` **terminales de
  configuración** (`auth`, `not_found`); `rate_limited`/`server`/`network`/`tls` son transitorios y abrir por
  ellos apagaría GitLab hasta 6 h por un blip de red. [V: services/integration_breaker.py:classify_gitlab_error]
- El breaker se consulta **después** de resolver el tracker: antes vivía arriba de `resolve_project_context` y un
  proyecto GitLab podía recibir `{"error":"ado_degraded"}` por el breaker de Azure DevOps de **otro** proyecto —
  el mismo defecto que el 281 F4 arregló en el arranque (`app.py:204-209`) y dejó vivo en `sync-v2`.
- Flag: `STACKY_GITLAB_SYNC_ERRORS_ROUTED_ENABLED` (ON). OFF ⇒ el `except` re-lanza y vuelve el 500 de antes.

### El match de los webhooks entrantes
- **`ado_id` NO es único**: es `nullable=False` pero no `unique=True`; el único índice único es la **terna**
  `(stacky_project_name, tracker_type, external_id)`. [V: models.py:42, models.py:77-83]
- En GitLab `ado_id` lleva el **IID**, que se repite entre proyectos [V: services/gitlab_sync.py:12-16]. Los dos
  receptores de `api/phase6.py` macheaban por `ado_id` pelado: con dos proyectos GitLab que tuvieran un issue
  #42, el webhook tomaba el del proyecto **equivocado** y corría el DebugAgent sobre él.
- Ahora los dos filtran por proyecto vía `_ticket_del_webhook`, con la misma tolerancia del `or_` de
  `api/tickets.py` para las filas históricas con `stacky_project_name` NULL (siguen macheando por `project`).
- El placeholder auto-creado escribe los **tres** campos del índice único (`stacky_project_name`,
  `tracker_type`, `external_id`) y el `project` del contexto — antes ponía `"RSPacifico"` hardcodeado y sin
  `tracker_type`, o sea un ticket ADO sintético dentro de un proyecto GitLab.
  Flag: `STACKY_WEBHOOK_TICKET_AUTOCREATE_ENABLED` (ON; OFF ⇒ 404 accionable en vez de crear).
- **Deuda declarada:** `api/phase6.py:192` corre el DebugAgent siempre con `runtime="github_copilot"` y
  `project_name=None`. Es preexistente; el plan 295 la declara y no la cambia.

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
