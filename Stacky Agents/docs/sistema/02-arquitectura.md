# 02 — Arquitectura

← [INDEX](INDEX.md) · hermanos: [04-api](04-api.md) · [06-servicios-daemons](06-servicios-daemons.md) · [08-configuracion-flags](08-configuracion-flags.md)

## Forma general
Monolito Flask que (1) expone una API REST bajo `/api`, (2) sirve el SPA React compilado desde `frontend/dist`,
y (3) arranca varios daemons (threads) de mantenimiento/cierre de runs. [V: app.py:182-505]

## App factory `create_app()`
Punto de entrada: `backend/app.py`. `app = create_app()` a nivel módulo y `app.run(host=0.0.0.0, port=config.PORT, threaded=True)` en `__main__`. [V: app.py:508-512]

### Secuencia de boot (orden real en `create_app`)
| # | Paso | Evidencia |
|---|------|-----------|
| 1 | Resolver `frontend_dist_dir()`, crear `Flask`, CORS condicional (`dist is None` o `ENABLE_CORS`) | [V: app.py:183-186] |
| 2 | `register_blueprint(api_bp)` (toda la API bajo `/api`) | [V: app.py:187] |
| 3 | `logging.basicConfig` + file log handler | [V: app.py:189-191] |
| 4 | `init_db()` (crea tablas + migración aditiva SQLite) | [V: app.py:193; db.py:40] |
| 5 | `install_console_log_handler()` | [V: app.py:194] |
| 6 | Bootstrap `Stacky/agents`: `materialize_agents()` refresca `manifest.json` desde el canonical | [V: app.py:200-217] |
| 7 | `ensure_weekly_backup()` de la DB | [V: app.py:219-228] |
| 8 | `seed_demo_project()` si `STACKY_DEMO_SEED_ENABLED!=false` | [V: app.py:230-236] |
| 9 | `seed_defaults_if_empty()` de `flow_config.json` | [V: app.py:238-246] |
| 10 | `reconcile_orphans()` (executions huérfanas) | [V: app.py:247-249] |
| 11 | `start_background_reaper()` (orphan reaper R0.3) | [V: app.py:251-256] |
| 12 | Aplicar `STACKY_HARNESS_PROFILE` si seteado (off/safe/full) | [V: app.py:258-271] |
| 13 | Startup recovery de tickets stale (`recover_stale_running_tickets`) si habilitado | [V: app.py:273-293] |
| 14 | Stale recovery guardian (`schedule_stale_recovery`, daemon, default ON, 120s) | [V: app.py:295-306] |
| 15 | Manifest watcher (`start_manifest_watcher`, default ON, 2.0s) | [V: app.py:308-319] |
| 16 | Output watcher (`start_output_watcher`, default ON, 3.0s) | [V: app.py:321-333] |
| 17 | Evals scheduler si `STACKY_EVALS_INTERVAL_HOURS>0` (default 0=off) | [V: app.py:335-347] |
| 18 | `_log_completion_preflight()` (gritar si outputs_dir no existe o falta PAT) | [V: app.py:142-179,349-352] |
| 19 | `_startup_sync()` (sync de tickets del proyecto activo: jira/mantis/azure) | [V: app.py:55-139,354] |
| 20 | `pipeline_orchestrator.register_ticket_status_hook()` | [V: app.py:356-362] |
| 21 | Digest daemon si `STACKY_DIGEST_INTERVAL_HOURS>0` | [V: app.py:364-382] |
| 22 | Memory review sweep daemon si `STACKY_MEMORY_REVIEW_SWEEP_HOURS>0` | [V: app.py:384-406] |
| 23 | Middleware `before/after_request` (request_id, logging estructurado) + errorhandler global | [V: app.py:408-467] |
| 24 | Rutas SPA (`/` y `/<path:asset_path>`) si hay `dist_dir` | [V: app.py:469-503] |

## Threads / daemons que arrancan
- **Stale recovery guardian** — re-ejecuta `recover_stale_running_tickets` cada `STACKY_REAPER_INTERVAL_SECONDS` (default 120). [V: app.py:299-304]
- **Manifest watcher** — polea `backend/data/codex_runs/<id>/MANIFEST.json`, cierra runs terminales huérfanos. [V: app.py:312-317; services/manifest_watcher.py docstring]
- **Output watcher** — detecta artifacts en `Agentes/outputs/` y cierra runs VS Code huérfanos / crea Tasks. [V: app.py:326-331; services/output_watcher.py docstring]
- **Orphan reaper** — reconcilia executions `running` sin heartbeat (boot + periódico). [V: app.py:251-256; services/orphan_reaper.py docstring]
- **Digest daemon** — `stacky-digest-daemon`, dispara webhook `digest.ready` cada N horas. [V: app.py:369-382]
- **Memory review daemon** — `stacky-memory-review-daemon`, marca observaciones para revisión. [V: app.py:389-406]
- **Evals scheduler** — corre evals golden cada N horas si habilitado. [V: app.py:342-347]
- **Stacky logger writer thread** — escribe `system_logs` en background (compartido vía shared-cache SQLite en tests). [INF: db.py:10-24 comenta el writer thread]

## Boot a nivel módulo (`app = create_app()`)
Importa `app` ⇒ ejecuta TODO el boot, incluido arrancar daemons. Relevante para tests y para WSGI. [V: app.py:508]

## Cómo se sirve el SPA
- `frontend_dist_dir()` busca `index.html` en `STACKY_FRONTEND_DIST`, `app_root/frontend/dist`, `backend_root.parent/frontend/dist`, `cwd/frontend/dist`. [V: runtime_paths.py:139-155]
- `GET /` → `index.html`; `GET /<path:asset_path>` → archivo si existe (con Content-Type forzado por extensión), si no → `index.html` (fallback SPA). Rutas que empiezan con `api/` devuelven 404. [V: app.py:486-503]
- Si no hay dist (modo dev), CORS se habilita para `/api/*`. [V: app.py:185-186]

## Puntos de entrada / salida
- **Entrada HTTP**: API REST `/api/*` + SPA. [V: api/__init__.py:43]
- **Entrada filesystem**: artifacts del agente en `Agentes/outputs/` y `codex_runs/<id>/MANIFEST.json`. [V: app.py:308-333]
- **Salida**: writes al tracker (ADO/Jira/Mantis), webhooks salientes, notificaciones desktop, archivos en disco. → ver [09-integraciones](09-integraciones.md).

## Resolución de paths (`runtime_paths.py`)
`is_frozen()` distingue deploy congelado vs fuentes; `repo_root()` resuelve dónde el agente escribe outputs (override `STACKY_REPO_ROOT`, o `workspace_root` del proyecto activo en frozen, o sentinel inexistente con WARNING). [V: runtime_paths.py:26-136]
