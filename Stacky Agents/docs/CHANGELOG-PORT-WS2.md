# Changelog — Portación selectiva WS2 → WS1

Registro de qué se trajo del fork WS2 (`N:\SVN\RS\Agentes\Stacky Agents\`) a WS1 (`N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky Agents\`), qué commit/snapshot de WS2 se usó y las adaptaciones realizadas.

---

## Sprint 1 — 2026-05-23

### Branch WS2 de referencia

SVN rev: snapshot al 2026-05-23 (`N:\SVN\RS\Agentes\Stacky Agents\`)

---

### P0.1 — `api/ado_manager.py`

**Origen:** `N:\SVN\RS\Agentes\Stacky Agents\backend\api\ado_manager.py` (99 líneas)

**Destino:** `Tools/Stacky/Stacky Agents/backend/api/ado_manager.py`

**Estado previo WS1:** archivo vacío (0 líneas, módulo no implementado)

**Cambios de adaptación:** ninguno — el código usa únicamente `project_manager.get_project_config` y `services.ticket_service.create_task`, ambos ya presentes en WS1 tras P0.2.

**Registro en `api/__init__.py`:** `ado_manager_bp` importado y registrado.

**Endpoint expuesto:** `POST /api/projects/<project_name>/tasks`

```json
{
  "agent_id": "AnalistaFuncionalPacifico.agent.md",
  "title": "RF-001 — Filtro por fecha",
  "description": "<p>HTML o texto</p>",
  "parent_id": 42
}
```

Respuesta 201:

```json
{
  "ticket_id": "1234",
  "ticket_url": "https://...",
  "tracker_type": "azure_devops",
  "initial_state": "Technical review",
  "work_item_type": "Task"
}
```

**Prerequisito de config:** el `config.json` del proyecto debe tener:

```json
{
  "agent_workflow_configs": {
    "AnalistaFuncionalPacifico.agent.md": {
      "task_creation": {
        "work_item_type": "Task",
        "initial_state": "Technical review"
      }
    }
  }
}
```

---

### P0.2 — `services/ticket_service.py`

**Origen:** `N:\SVN\RS\Agentes\Stacky Agents\backend\services\ticket_service.py` (251 líneas)

**Destino:** `Tools/Stacky/Stacky Agents/backend/services/ticket_service.py`

**Estado previo WS1:** no existía.

**Cambios de adaptación:** ninguno — `ticket_service` depende únicamente de `project_manager` y de los clientes `ado_client`, `jira_client`, `mantis_client`, todos presentes en WS1.

**Dependencias resueltas en este sprint:**

- `jira_client.JiraClient.create_issue` — AGREGADO a WS1 (ver abajo)
- `jira_client.JiraClient.update_issue_fields` — AGREGADO a WS1
- `jira_client.JiraClient.normalize_field_for_update` — AGREGADO a WS1
- `jira_client.JiraClient.fetch_attachments` — AGREGADO a WS1
- `jira_client.JiraClient.delete_attachment` — AGREGADO a WS1
- `jira_client.JiraClient.upload_attachment` — AGREGADO a WS1
- `jira_client.JiraClient.get_project_statuses` — AGREGADO a WS1
- `jira_client.JiraClient.get_issue_types` — AGREGADO a WS1
- `jira_client.JiraClient._download_text` — AGREGADO a WS1
- `mantis_client.MantisClient.create_issue` — AGREGADO a WS1

**Archivos modificados en WS1:**

- `services/jira_client.py` — métodos nuevos insertados dentro de la clase `JiraClient`, helper `_is_text_attachment` y `_TEXT_EXTENSIONS` agregados. El resto del archivo (secrets_store integration, SSL fallback) se preservó tal cual.
- `services/mantis_client.py` — método `create_issue` insertado al final de la clase `MantisClient` (REST), antes de la clase SOAP.

**Nota:** Los métodos de jira_client de WS2 no usan `secrets_store` para credenciales (diferencia de diseño); WS1 mantiene su integración con `secrets_store` en `_resolve_credentials`. Los métodos nuevos portados usan únicamente `self._auth` y `self._api_base` que ya existen en WS1.

---

### P3.3 — Restauración de `trunk/docs/agentic_manual/tecnica/`

**Problema:** en la branch `PruebaFlujoAgentico` se borraron 30 archivos del manual técnico agéntico de dominio RSPacifico.

**Acción:** restaurados desde `git checkout HEAD` los 30 archivos borrados:

```
01_ARQUITECTURA_SISTEMA.md  ... 28_PIPELINES_CICD.md  _ROADMAP.md
```

**Fuente usada:** `git HEAD` (más completa que WS2: incluye 28_PIPELINES_CICD.md y _ROADMAP.md que WS2/DOCUM no tiene).

**No restaurado:** `00_INDICE_MAESTRO.md` — fue modificado intencionalmente en esta branch (cambio deliberado, no borrado accidental).

**No tocado:** los 9 archivos untracked nuevos creados en esta branch (01_FORMULARIO_BASE.md ... 09_BATCH_REENGANCHE.md).

---

## Sprint 2 — 2026-05-23

### Deuda técnica resuelta antes de Sprint 2

#### Fix encoding — `services/mantis_client.py`

**Problema:** el archivo tenía corrupción double-encoded Windows-1252/UTF-8 (secuencias tipo `\xc3\xa2\xe2\x82\xac\xe2\x80\x9d` para em-dash) en todo el archivo, más comillas tipográficas U+201C/U+201D usadas como delimitadores de string Python en el método `create_issue` portado en Sprint 1. Resultado: `ast.parse` fallaba con `SyntaxError` en línea 290.

**Fix:** script de reparación binaria que reemplazó 8 secuencias double-encoded específicas y luego sustituyó los 381 bytes U+201C/U+201D por `"` ASCII. Resultado: UTF-8 válido, `ast.parse OK`.

#### Fix 4 tests fallando — `tests/test_create_child_task_endpoint.py`

**Problema:** TU-01, TU-03, TU-04, TU-06 fallaban porque parcheaban `"api.tickets.AdoClient"` directamente, pero el endpoint usa `_ado_client_for_ticket()` → `build_ado_client()` — el mock nunca se aplicaba. TU-01 evidencia: retornaba `task_ado_id == 192` (llamada ADO real) en lugar de `5000` (mock).

**Fix:**
- Patch target corregido a `"api.tickets._ado_client_for_ticket", return_value=fake_ado` en los 4 tests.
- `FakeAdoClientExt.create_work_item` actualizado a firma unificada con `parent_ado_id` y `parent_id` como kwargs con precedencia `parent_ado_id > parent_id`.

**Resultado:** 14/14 tests PASS en 10.09s.

---

### P1.3 — Endpoints de ejecuciones extendidos

**Archivo modificado:** `backend/api/executions.py`

**Estado previo WS1:** 151 líneas — solo list/get/logs/stream/approve/discard/publish-to-ado/diff.

**Endpoints agregados:**

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/executions/<id>/cancel` | Marca cancelled; mata proceso codex_cli si aplica |
| `DELETE` | `/api/executions/<id>` | Elimina ejecución en estado terminal (completed/error/cancelled/published/discarded/failed) |
| `DELETE` | `/api/executions/bulk-by-ticket` | Borrado masivo por `ticket_id` + `agent_filename`; omite in-progress |
| `POST` | `/api/executions/<id>/answer` | Reenvía respuesta a `agent_runner.answer_question()` con guard `hasattr` WS1 |
| `GET` | `/api/executions/<id>/output-files` | Lista archivos del directorio de salida del ticket |
| `DELETE` | `/api/executions/<id>/output-files` | Elimina archivos listados en body `{"files": [...]}` con protección path traversal |

**Adaptaciones WS1:**

- `derive_ticket_key` (WS2 `output_watcher`) no existe en WS1 — reemplazado por `_resolve_ticket_output_dir_ws1()` que usa heurística: metadata override → `Output/tickets/{ado_id}` → `Output/tickets/azure_devops-{ado_id}`.
- `agent_runner.answer_question` no existe en WS1 — guard `if not hasattr(_runner, "answer_question"): abort(501, ...)`.
- Importaciones: `PROJECTS_DIR, get_project_config, get_active_project, find_project_for_tracker` de `project_manager`.

**Resultado:** `ast.parse OK`.

---

### P1.2 — Chat multi-turno

**Archivo nuevo:** `backend/api/chat.py`

**Registrado en:** `api/__init__.py` como `chat_bp`.

**Endpoint expuesto:** `POST /api/chat/turn`

**Body:**

```json
{
  "agent_filename": "DevPacifico.agent.md",
  "model": "gpt-4o",
  "messages": [
    {"role": "assistant", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "workspace_dir": null,
  "runtime": null,
  "project_name": null
}
```

**Respuesta 200:**

```json
{
  "ok": true,
  "text": "respuesta del agente",
  "tool_log": [],
  "turns": 1,
  "model_used": "gpt-4o",
  "logs": ["[info] turno 1"]
}
```

**Runtimes soportados:**

| Runtime | Comportamiento |
|---|---|
| `codex_cli` | Llama `codex_cli_runner.run_sync()` con guard `hasattr` |
| `vscode_bridge` + `invoke_hybrid` disponible | Usa `copilot_bridge.invoke_hybrid()` (WS2 merge futuro) |
| `vscode_bridge` sin `invoke_hybrid` (WS1 actual) | Fallback a `copilot_bridge.invoke()` con historial como texto plano |
| mock / otro | Llama `copilot_bridge._invoke_mock()` |

**Adaptaciones WS1:**

- `_read_agent_system_prompt` (WS2) no existe en WS1 — reemplazado por `_get_system_prompt()` que usa `vscode_agents.get_agent_by_filename()`.
- `invoke_hybrid` verificado con `hasattr(copilot_bridge, "invoke_hybrid")` — no aborta si no está.
- `config.CODEX_CLI_MODEL` accedido con `getattr(config, "CODEX_CLI_MODEL", "codex")` (safe).

**Resultado:** `ast.parse OK`.

---

### P1.5 — Global Config API

**Archivo nuevo:** `backend/api/global_config.py`

**Registrado en:** `api/__init__.py` como `global_config_bp`.

**Gestiona:** archivo `.env` en `backend/.env` — 22 keys ADO/Jira/Mantis/Codex.

**Endpoints expuestos:**

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/global-config` | Lee config actual; con `?reveal=1` incluye secrets en claro |
| `PUT` | `/api/global-config` | Actualiza .env y `os.environ` en-process |
| `POST` | `/api/global-config/test-connection` | Prueba conectividad ADO/Jira/Mantis |
| `POST` | `/api/global-config/test-codex` | Verifica binario Codex CLI; retorna lista de modelos curada |
| `POST` | `/api/global-config/codex-login` | Ejecuta `codex login` (OAuth, timeout 5 min) |
| `GET` | `/api/global-config/codex-session` | Check file-based + CLI probe de sesión activa |
| `DELETE` | `/api/global-config/codex-session` | `codex logout` o borrado directo del archivo de sesión |

**Claves secretas** (redactadas en GET sin `?reveal=1`): `ADO_PAT`, `JIRA_TOKEN`, `MANTIS_TOKEN`, `MANTIS_PASSWORD`, `OPENAI_API_KEY`.

**Adaptaciones WS1:**

- Test-connection Mantis usa `client.list_projects()` — `get_project_statuses()` de WS2 no está portado a WS1.

**Resultado:** `ast.parse OK`.

---

## Cosas a NO portar (decisión cerrada)

| Ítem | Razón |
|---|---|
| `MejorasStackyAgent.md` (WS2) | WS1 tiene versión 25x más completa. |
| `FileViewerModal.tsx` | `DocViewer.tsx` de WS1 ya cumple. |
| `api/system.py` | Redundante con `api/logs.py`. |
| `invoke_autonomous` en `copilot_bridge.py` | Conflicto con política human-in-the-loop. |
| `services/odm_sync.py` + `api/odm_sync_api.py` | P1.6 congelado — sin casos ODM activos. |

---

## Sprint 3 — 2026-05-24

### Verificacion: endpoint `/agent-workflows`

**Estado:** PRESENTE en WS1 — `api/projects.py` linea 748 (`GET /projects/<name>/agent-workflows`). No requiere portacion.

---

### P2.1 — `api/agent_roles.py` + `AgentConfigModal.tsx`

**Estado:** YA COMPLETO — portado en sprint anterior (detectado en verificacion Sprint 3).

**Evidencia:**
- `backend/api/agent_roles.py` — GET/PUT `/api/agent-roles`, persiste en `data/agent_roles.json`. Adaptacion WS1: usa `config.VSCODE_PROMPTS_DIR` en lugar de `config.agents_dir`.
- `frontend/src/components/AgentConfigModal.tsx` + `.module.css` — tabla de flags por agente.
- `frontend/src/api/endpoints.ts` — `AgentRoleEntry` + `AgentRoles.list()` / `AgentRoles.update()` desde linea 1676.
- Registrado en `api/__init__.py` como `agent_roles_bp`.

---

### P1.4 (complemento) — Expansion `services/mantis_client.py`

**Archivo modificado:** `backend/services/mantis_client.py`

**Estado previo WS1:** solo tenia `create_issue` de los metodos nuevos WS2. Faltaban todos los demas.

**Helpers agregados (nivel modulo):**

| Simbolo | Descripcion |
|---|---|
| `_STANDARD_STATUS_IDS` | Mapa nombre→ID numerico Mantis por defecto |
| `_TEXT_EXTENSIONS` | Frozenset de extensiones que se descargan como texto |
| `_is_text_attachment(filename)` | True si la extension esta en `_TEXT_EXTENSIONS` |
| `_resolve_mantis_status_id(name)` | Busca ID numerico en `_STANDARD_STATUS_IDS` |
| `_parse_mantis_enum(raw)` | Parsea string enum Mantis `"10:new,20:feedback,..."` |

**`MantisClient.__init__` extendido:** agrega `self._current_user_id` (leido del auth JSON si existe `user_id`, o `None`) y `self._auth_username` para fallback de lookup.

**Metodos agregados a `MantisClient`:**

| Metodo | Descripcion |
|---|---|
| `get_current_user_id()` | Cache + /users/me + /users?username — retorna None si falla |
| `fetch_attachments(issue_id)` | Lista adjuntos del issue; descarga texto para archivos <= 100 KB |
| `delete_attachment(issue_id, attachment_id)` | DELETE /issues/{id}/files/{att_id} |
| `_download_text(url)` | Descarga URL con auth Mantis; maneja JSON+base64 o texto plano |
| `upload_attachment(issue_id, file_name, content_bytes)` | POST /issues/{id}/files JSON+base64 |
| `get_project_statuses()` | GET /config?option[]=status_enum_string, fallback issues |
| `get_project_categories()` | GET /projects/{id}/categories, fallback issues |

**Nota de diseno:** `fetch_open_issues()` en WS1 NO filtra por usuario (retorna todos los no-resueltos). WS2 agrega ese filtro via `get_current_user_id()`. Se preservo el comportamiento WS1 — el filtro por usuario es opt-in para el caller si lo necesita.

**Validacion:** `ast.parse OK`

---

### P1.4 (complemento) — Expansion `services/jira_client.py`

**Archivo modificado:** `backend/services/jira_client.py`

**Metodo agregado:**

| Metodo | Descripcion |
|---|---|
| `fetch_issue_ids_for_jql(jql)` | GET /search paginado, retorna `set[int]` de IDs internos Jira |

Insertado despues de `issue_url()`, antes de `fetch_comments()`.

**Validacion:** `ast.parse OK`

---

### P2.6 — Agentes nuevos portados desde WS2

**Origen:** `N:\SVN\RS\Agentes\Stacky Agents\Agentes\`

#### DesarrolladorSVN.agent.md (v1.1.0)

**Destino:** `N:\GIT\RS\RSPACIFICO\Agentes\Agente DesarrolladorSVN\DesarrolladorSVN.agent.md`

**Nueva carpeta creada:** `Agentes/Agente DesarrolladorSVN/`

**Funcion:** Developer Senior que genera parches SVN unified diff. Complementa a `DevPacifico.agent.md` (que edita codigo directamente). Este agente NUNCA edita `trunk/` — genera PATCH_*.diff que el humano aplica con `svn patch`. Opera en modo batch Stacky exclusivamente.

**Sin conflicto con DevPacifico:** diferentes filosofias de entrega. Coexisten.

#### DocConsultor.agent.md

**Destino:** `N:\GIT\RS\RSPACIFICO\Agentes\DocConsultor\DocConsultor.agent.md`

**Nueva carpeta creada:** `Agentes/DocConsultor/`

**Funcion:** Agente utilitario RAG. Responde preguntas sobre documentacion del workspace (ficheros .md). Trabaja con fragmentos de documentacion inyectados en contexto — no accede a codigo fuente ni a trackers. Pensado para integrarse con ChatDrawer (P1.1, pendiente).

**Nota:** Sin el endpoint de RAG (`api/docs_rag.py`, P1.1 pendiente), este agente puede usarse directamente en VS Code Chat como agente utilitario con acceso manual a docs.

#### AgenteNegocio.agent.md (v2.0.0)

**Destino:** `N:\GIT\RS\RSPACIFICO\Agentes\Agente de Negocio\AgenteNegocio.agent.md`

**Coexiste con:** `agente-de-negocio.md` (v1 sin frontmatter Stacky, hardcoded paths Hackaton)

**Diferencias clave v2.0.0 vs v1:**
- Frontmatter `.agent.md` con `tools:` y `version:` — compatible con Stacky selector
- **Modo B:** acepta contenido de ticket entregado por Stacky (sin leer carpeta Input)
- Paths relativos al workspace activo (`Input/`, `Contexto/funcional/`, `Output/req/`) en vez de rutas hardcodeadas
- Flujo de Stacky documentado explicitamente (no accede al tracker, Stacky gestiona publicacion)

**Decision:** `agente-de-negocio.md` se mantiene sin modificar (legacy). `AgenteNegocio.agent.md` es el agente oficial para flujos Stacky.

---

### tsc --noEmit

**Resultado:** 0 errores (sin cambios en frontend Sprint 3 — todo portado previamente).

---

## Sprint 4 — 2026-05-24

### Branch WS2 de referencia

SVN rev: snapshot al 2026-05-24 (`N:\SVN\RS\Agentes\Stacky Agents\`)

---

### P1.1 — RAG documental (`docs_rag` + `ChatDrawer`)

**Archivos creados/modificados:**

| Archivo | Accion |
|---|---|
| `backend/services/docs_rag.py` | Copiado integro desde WS2. Incluye modelo `DocChunk` (tabla `docs_index`), indexador TF-IDF, IDF cache, expansion de ficheros. |
| `backend/api/docs_rag.py` | Portado desde WS2 con adaptacion: `_read_agent_system_prompt` sustituida por `vscode_agents.get_agent_by_filename` (patron WS1). `AUTONOMOUS_WORKSPACE_DIR` con fallback `getattr`. |
| `backend/api/__init__.py` | Registro del blueprint `docs_rag_bp`. |
| `backend/db.py` | Import de `DocChunk` en `init_db()` para que `create_all` cree la tabla `docs_index` automaticamente. |
| `frontend/src/components/ChatDrawer.tsx` | Copiado desde WS2. Adaptacion: `runtime` → `agentRuntime` (alias WS1). `Tickets.list` con 1 argumento. |
| `frontend/src/components/ChatDrawer.module.css` | Copiado integro desde WS2. |
| `frontend/src/api/endpoints.ts` | Agregados: `ChatTurnMessage`, `ChatToolLog`, `ChatTurnResponse`, `Chat`, `DocsRagSource`, `DocsRagChatResponse`, `DocsRagIndexResponse`, `DocsRagStatsResponse`, `DocsRag`. Agregado `Projects.agentBootstrap`. |
| `frontend/src/store/workbench.ts` | Agregadas props: `chatDrawerOpen`, `chatDrawerModel`, `chatDrawerTicketId`, `setChatDrawerOpen`, `setChatDrawerModel`, `setChatDrawerTicketId`. |

**Endpoints expuestos:**

- `POST /api/docs-rag/index` — indexa .md del proyecto
- `GET  /api/docs-rag/stats` — estadisticas del indice
- `POST /api/docs-rag/search` — busqueda de chunks (debug)
- `POST /api/docs-rag/chat` — chat RAG con contexto documental

**Modelo DB:** tabla `docs_index` creada via `create_all` (no alembic; WS1 usa create_all + migraciones manuales).

**Validacion:** `ast.parse` OK en todos los .py (1777 archivos). `tsc --noEmit` 0 errores.

---

### P3.1 — Scripts de distribucion

| Archivo | Accion |
|---|---|
| `build_dist.ps1` | Copiado desde WS2. Paths relativos al script son correctos para estructura WS1. Agregado comentario de portacion. |
| `Setup Stacky.ps1` | Copiado integro desde WS2. |

**Nota:** `Setup Stacky.ps1` contiene `Read-Host` al final — comportamiento normal para script de setup interactivo. El `$DIST_BASE = "C:\AIS"` es el destino de distribucion para maquina del cliente, no el repo.

**Validacion:** Parse PowerShell OK en ambos scripts.

---

### P3.2 — Documentacion de referencia WS2

| Archivo | Accion |
|---|---|
| `docs/13_STACKY_AGENTS_REFERENCE_WS2.md` | `STACKY_AGENTS_COMPLETE.md` de WS2 (spec tecnica 52 moats). No sobrescribe ningún doc WS1. |
| `docs/14_MANUAL_PARA_AGENTES_WS2.md` | `README_PARA_AGENTES.md` de WS2 (manual operativo). No sobrescribe ningún doc WS1. |

---

### P2.5 — File Modals

| Archivo | Accion |
|---|---|
| `frontend/src/components/FileManagerModal.tsx` | Copiado desde WS2. Adaptacion: `a.created` → `a.created_at` para compatibilidad con `TicketAttachment` de WS1. |
| `frontend/src/components/FileManagerModal.module.css` | Copiado integro desde WS2. |
| `frontend/src/components/FileSelectorModal.tsx` | Copiado integro desde WS2. |
| `frontend/src/components/FileSelectorModal.module.css` | Copiado integro desde WS2. |

**Dependencias backend:** endpoints `GET /tickets/{id}/attachments` y `DELETE /tickets/{id}/attachments` presentes desde P1.4 (Sprint 3).

**Validacion:** `tsc --noEmit` 0 errores.

---

## Archivos WS1 blindados (no modificar sin decisión explícita)

- `api/qa_uat.py` — WS1 tiene 1831 líneas vs 242 en WS2. NO reemplazar.
- `api/tickets.py` — WS1 tiene 2443 líneas vs 1010 en WS2. NO reemplazar.
- `agent_runner.py` — WS1 tiene 729 líneas con observabilidad completa. NO portar cambios.
