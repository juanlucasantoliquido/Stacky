# Stacky Agents — Documentación canónica del sistema

Fuente única de verdad de la documentación del sistema, modular y verificada contra el código.
Cada archivo cubre un área. Abrí solo lo que necesites; no hace falta leer todo.

> Confianza global de esta doc: **MEDIA-ALTA**. La mayoría de los claims están verificados [V]
> contra archivo:línea. Lo inferido o no comprobado está marcado.

## Leyenda de marcas de confianza
- `[V: evidencia]` — Verificado contra evidencia real (archivo:línea, símbolo, comando, doc citada).
- `[INF: base]` — Inferido por deducción razonable a partir de evidencia parcial.
- `[NV]` — No verificado / desconocido. No se pudo comprobar con la exploración realizada.

## Mapa de navegación
| Archivo | Qué contiene |
|---------|--------------|
| [01-overview.md](01-overview.md) | Qué es Stacky Agents, propósito, actores, casos de uso, fuera de alcance, supuestos. |
| [02-arquitectura.md](02-arquitectura.md) | Flask `create_app()`, secuencia de boot, daemons que arrancan, cómo se sirve el SPA. |
| [03-modelo-datos.md](03-modelo-datos.md) | Tablas reales de `models.py` (campos, índices, relaciones) + migración SQLite. |
| [04-api.md](04-api.md) | Blueprints registrados y endpoints por blueprint (tickets, executions, agents primero). |
| [05-agentes-runtimes.md](05-agentes-runtimes.md) | Registry de agentes, prompts canónicos, runtimes, regla NO-fallback, cap de modelos. |
| [06-servicios-daemons.md](06-servicios-daemons.md) | Servicios/daemons clave de `backend/services` y sus flags `STACKY_*`. |
| [07-frontend.md](07-frontend.md) | Stack React/Vite, entrada `App.tsx`, tabs/ruteo, consumo de API, build. |
| [08-configuracion-flags.md](08-configuracion-flags.md) | `config.py`: variables de entorno, flags `STACKY_*`, defaults (secretos REDACTADOS). |
| [09-integraciones.md](09-integraciones.md) | ADO/Jira/Mantis, webhooks, notificaciones desktop, outputs en filesystem. |
| [10-grafo.md](10-grafo.md) | Grafo del sistema: tabla de nodos, aristas, Mermaid y vista YAML para agentes. |
| [11-estado-planes.md](11-estado-planes.md) | Resumen del estado de los planes `docs/19_*..46_*` (1-2 líneas c/u). |

## Invariantes globales del sistema
1. **Selector de runtime sin fallback silencioso**: si elegís `codex_cli` o `claude_code_cli`, un error del runner es error real; NUNCA cae a `github_copilot`. [V: agent_runner.py:273-282,347-355]
2. **Cap duro de modelos Claude**: jamás se usa un tier prohibido (opus/fable) salvo la allowlist Opus exclusiva del flujo brief→épica. Todo pasa por `clamp_model()`. [V: services/llm_router.py:35-54]
3. **`Stacky/agents` es la fuente canónica de los `.agent.md`**; `VSCODE_PROMPTS_DIR` y `agents_dir` de proyecto se ignoran si difieren. [V: config.py:97-122]
4. **Mono-operador, sin auth real**: `current_user` viene de un header sin validar; no hay login/roles/403. [INF: MEMORY stacky-no-auth-substrate; ver app.py:422 `X-User-Email`]
5. **DB SQLite con migración aditiva** (`Base.metadata.create_all` + ALTER TABLE seguros); las tablas nuevas no requieren migración destructiva. [V: db.py:40-129]
6. **El backend sirve el SPA** desde `frontend/dist` con Content-Type forzado por extensión. [V: app.py:469-503]

## staleness_check (¿esta doc quedó vieja?)
- Cambió la lista de blueprints en `backend/api/__init__.py` → revisar **04-api.md**. [V: api/__init__.py:3-82]
- Cambió `registry` en `backend/agents/__init__.py` o los `.agent.md` de `backend/Stacky/agents` → revisar **05-agentes-runtimes.md**.
- Cambió `clamp_model` / `CLAUDE_CAP_MODEL` / `_OPUS_ALLOWLIST` en `services/llm_router.py` → revisar **05** y **08**.
- Se agregaron clases `Base` en `models.py` o tablas en `db.init_db()` → revisar **03-modelo-datos.md**.
- Se agregaron daemons/threads en `create_app()` (`app.py`) o flags nuevos en `config.py` → revisar **02**, **06**, **08**.
- Se agregó/quitó un tab en `frontend/src/App.tsx` → revisar **07-frontend.md**.
- Se agregó un doc `docs/47_*` o cambió el estado de un plan → revisar **11-estado-planes.md**.
