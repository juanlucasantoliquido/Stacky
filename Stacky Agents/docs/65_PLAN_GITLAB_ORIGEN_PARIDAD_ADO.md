# Plan 65 — GitLab como tracker de primer nivel con paridad funcional completa frente a Azure DevOps

> Versión: **v2** (criticada y endurecida) · Estado: PROPUESTO (no implementado) · Autor: StackyArchitectaUltraEficientCode · Fecha: 2026-06-22
> Veredicto del juez: **APROBADO-CON-CAMBIOS** (no había bloqueantes irreparables, pero sí 1 cuasi-bloqueante de coherencia arquitectónica + varias imprecisiones de seam verificadas contra el código).

## 0. CHANGELOG v1 -> v2 (qué cambió y por qué)

Esta v2 corrige afirmaciones del v1 que NO resistieron la verificación contra el código (grep dirigido, sin leer archivos enteros), y endurece TDD/anti-falso-verde.

- **[C1 — IMPORTANTE→arquitectura] El eje de selección de tracker YA EXISTE y es por-proyecto, no global.** El v1 inventaba `STACKY_TRACKER_PROVIDER=ado|gitlab` (env global). Pero `project_context.py:73` ya resuelve `tracker_type = issue_tracker.type` con ramas `azure_devops|jira|mantis`, y `build_ado_client` (`project_context.py:217`) **rechaza** proyectos no-ADO. La fábrica F10 ahora se ancla en `issue_tracker.type` (valor canónico **`gitlab`**, junto a `azure_devops|jira|mantis`), NO en una env paralela. `STACKY_GITLAB_ENABLED` queda solo como kill-switch.
- **[C2 — IMPORTANTE] El v1 afirmaba "NO existe abstracción de provider, todo cableado a ADO": FALSO.** El repo YA tiene `jira_client.py`/`jira_sync.py`/`mantis_client.py`/`mantis_sync.py` y `test_global_tracker_connection` con ramas `azure_devops|jira|mantis` (`global_config.py:208,229,249`). Corregida la sección §2; agregada §2.bis que define la relación GitLab↔Jira/Mantis (GitLab es el primer tracker en adoptar el puerto formal; Jira/Mantis quedan como están, sin regresión, y se documenta el camino para portarlos luego — fuera de scope de este plan).
- **[C3 — IMPORTANTE] "35 call-sites de `AdoClient(` en `tickets.py`": FALSO.** `grep -c 'AdoClient('` en `tickets.py` = **0**. El acceso real es vía `ado_publisher._client_for_ticket_project()` / `_default_client()` (`ado_publisher.py:373,573,579,607`). F10 reescrita para apuntar al seam REAL (los dos factory-helpers de `ado_publisher`, más `build_ado_client` de `project_context`), no a un patrón inexistente.
- **[C4 — IMPORTANTE] El v1 decía que F10 cambia `ado_write_outbox._apply` para "despachar al provider": FALSO.** `_apply` (`ado_write_outbox.py:334`) solo persiste estado en DB (`setattr` sobre `AdoWriteOperation`); no llama a ningún cliente. El consumidor que ejecuta la escritura real es otro. F10/fila 27 corregidas: se identifica el consumidor real por grep antes de tocar nada; el outbox-store NO se toca.
- **[C5 — IMPORTANTE] Campo del profile equivocado.** El v1 hablaba de `tracker.auth_file`; el campo real es `issue_tracker` (`project_manager.py:100`, `project_context.py:72`). Corregido en GP-3, F1, F2, F11. El auth-file de GitLab sigue el patrón YA existente (`auth/jira_auth.json`, `auth/mantis_auth.json` → `auth/gitlab_auth.json`).
- **[C6 — BLOQUEANTE de falso-verde] El conformance del v1 solo probaba existencia (`callable`).** Un adapter con métodos que existen pero lanzan `NotImplementedError` pasaría → FALSO VERDE. F0/F12 endurecidas: el conformance prueba **comportamiento** con HTTP doubles por método y un test explícito anti-stub que falla si un PORT_METHOD lanza `NotImplementedError`/`pass`. (Ver **[ADICIÓN ARQUITECTO #1]**.)
- **[C7 — IMPORTANTE] Pseudocódigo con `...` no implementable por Haiku.** Rellenados los huecos de F3 (`update_item_state`), F7 (`_link_parent` ids), F1 (delegaciones). Cada `...` que escondía lógica no trivial ahora es literal.
- **[C8 — IMPORTANTE] Dependencias inter-fase rotas.** F3 `create_item` llamaba `_resolve_assignee_id` (F6) y `_link_parent` (F7) antes de que existieran → el test de F3 fallaría. Resuelto con **stubs explícitos en F3** (definidos no-op y sobreescritos en F6/F7) + nota de orden. Ver §8 orden.
- **[C9 — MENOR] Defaults de flags ahora explícitos y tabulados** (§3.bis), incluido `STACKY_GITLAB_CI_INFERENCE`.
- **[ADICIÓN ARQUITECTO #1]** Test anti-falso-verde `test_no_port_method_is_a_stub` (F12): instancia el GitLabProvider con un transporte double y verifica que NINGÚN PORT_METHOD lanza `NotImplementedError`; los que escriben/leen prueban el efecto observable (request emitido + shape normalizado). Convierte KPI-1 en una garantía real de comportamiento, no de firma.
- **[ADICIÓN ARQUITECTO #2]** Guard de CI `test_no_adoclient_outside_ado_provider` + grep en el ratchet (F13): falla si `AdoClient(` aparece fuera de `ado_provider.py`/`project_context.py`/`ado_*` internos, sellando la regresión "alguien vuelve a cablear ADO directo".
- **[ADICIÓN ARQUITECTO #3]** Modo **shadow/dry-run** de GitLab (F11.bis): un botón "Probar conexión + permisos" que valida credenciales, lectura paginada y permiso de escritura SIN crear nada (usa `GET /user`, `GET /projects/{id}`, y un `POST` a un recurso de prueba con rollback/o solo `HEAD`/scopes), reusando el patrón de `test_global_tracker_connection`. Cero escritura, cero trabajo extra, opt-in.

## 1. Título, objetivo y KPI

**Objetivo.** Introducir GitLab (gitlab.com o self-managed, REST v4) como **tracker de origen/integración de primer nivel** en Stacky Agents, con **paridad funcional COMPLETA** frente a Azure DevOps (ADO). Todo lo que hoy Stacky hace contra ADO (leer work items, crear épicas/issues/tasks jerárquicas, comentar idempotentemente, subir adjuntos, resolver identidad/assignee, inferir pipelines/CI, sincronizar, aprender de ediciones del operador) debe poder hacerse contra GitLab a través de un **único puerto agnóstico** `TrackerProvider`, sin cambiar el comportamiento ADO existente (byte-idéntico) y sin agregar trabajo al operador (opt-in, default `ado`).

El plan **no reescribe** la lógica ADO: la **envuelve** detrás de un puerto y agrega un segundo adapter GitLab. La garantía "no falta ninguna función" se vuelve **verificable por un test de conformance** que recorre la matriz de paridad y falla si algún método del puerto no está implementado en GitLab.

**KPI / impacto esperado (binarios).**
- KPI-1: `python -m pytest backend/tests/test_tracker_provider_conformance.py -q` pasa con AMBOS adapters (ADO y GitLab) cubriendo el 100% de los métodos del puerto, incluido el test **anti-stub** (`test_no_port_method_is_a_stub`, ADICIÓN #1): ningún método existe vacío/`NotImplementedError`; los de escritura emiten el request esperado y los de lectura devuelven el shape canónico. Falla si falta uno o si alguno es un stub.
- KPI-2: La suite ADO existente (`test_ado_*.py`, `test_tickets*.py`, conformance de runtime) sigue verde sin cambios de comportamiento con `issue_tracker.type=azure_devops` (default). 0 regresiones.
- KPI-3: Con `issue_tracker.type=gitlab` + `STACKY_GITLAB_ENABLED=true`, un brief→épica produce el MISMO artefacto lógico (épica + hijos + comentarios idempotentes por marcador) que contra ADO, verificado por `test_gitlab_provider.py` con HTTP doubles.
- KPI-4: `tsc --noEmit` en `frontend/` = 0 errores tras agregar el selector de provider en la UI.

## 2. Por qué ahora / gap que cierra (CORREGIDO en v2, verificado contra código)

**Estado real (no el del v1).** Stacky YA es multi-tracker para sync/lectura: existen `jira_client.py`/`jira_sync.py`/`mantis_client.py`/`mantis_sync.py`, y la selección se hace **por proyecto** vía `issue_tracker.type` (`project_context.py:73` → ramas `azure_devops|jira|mantis`; default `azure_devops`). `global_config.test_global_tracker_connection` ya enruta por `tracker_type` (`global_config.py:199,208,229,249`) y resuelve secretos por archivo por tracker (`auth/jira_auth.json`, `auth/mantis_auth.json`). Lo que NO existe es un **puerto formal y completo** que cubra TODA la superficie de escritura/jerarquía/idempotencia/edit-learning de ADO; los trackers alternos hoy solo cubren sync/lectura básica.

**El gap real que cierra el plan:**
- No hay un contrato único (`TrackerProvider`) que garantice paridad funcional COMPLETA con ADO (épicas/issues/tasks jerárquicas, comentarios idempotentes, attachments, identity, edit-learning, pipeline). Jira/Mantis cubren un subconjunto sin contrato verificable.
- `build_ado_client` (`project_context.py:217`) **rechaza** explícitamente proyectos no-ADO para el camino de escritura rico (`ado_publisher`, etc.). Ese es el muro a romper con el puerto.
- Evidencia ADO-céntrica que persiste: `ado_client.py` con base URL `https://dev.azure.com/...`; ~11 módulos `ado_*.py`; el camino de publicación de épicas (planes 51/55/59/60) está atado a `AdoClient`.

**Imprecisiones del v1 corregidas (medidas con grep):**
- `grep -c 'AdoClient(' backend/api/tickets.py` = **0** (no "35 call-sites"). El acceso a cliente en `tickets.py` es indirecto vía `ado_publisher._client_for_ticket_project()`/`_default_client()`. Ver C3.
- `ado_write_outbox._apply` (`ado_write_outbox.py:334`) NO despacha a ningún cliente: solo persiste estado. Ver C4.

**Seam ya existente que aprovechamos (verificado):**
- **Selección por proyecto:** `project_context.resolve_project_context` + `build_ado_client` (`project_context.py:175,208`). La fábrica nueva se inserta AQUÍ, NO en una env global.
- **Estados lógicos:** `client_profile.tracker_state_machine` (functional/technical/developer) — validado en `client_profile.py:144`. Punto de mapeo estado-lógico↔tracker.
- **Secreto por archivo:** patrón ya usado por ADO/Jira/Mantis (`auth/<tracker>_auth.json`). GitLab reusa el mismo patrón → `auth/gitlab_auth.json`. El secreto NUNCA va en `issue_tracker` del profile.

### 2.bis Relación GitLab ↔ Jira/Mantis (decisión explícita)

Para no romper lo existente ni inflar el scope:
- GitLab es el **primer tracker que adopta el puerto formal `TrackerProvider`** con paridad COMPLETA verificada por conformance.
- ADO se envuelve en `AdoTrackerProvider` (F1) byte-idéntico.
- **Jira y Mantis quedan exactamente como están** (sync/lectura por su propio path). NO se tocan, NO se degradan, NO entran al conformance en este plan. Su migración al puerto es **fuera de scope** (se deja anotada como evolución futura en §7).
- La fábrica `get_tracker_provider` devuelve `AdoTrackerProvider` o `GitLabTrackerProvider`; para `issue_tracker.type in {jira,mantis}` **lanza `TrackerConfigError` explícito** ("tracker sin puerto formal todavía") en los call-sites de escritura rica que hoy ya rechazan no-ADO — es decir, mismo comportamiento que hoy (`build_ado_client` ya rechaza no-ADO), sin regresión.

El puerto + conformance test hace robusto y verificable agregar GitLab sin `if tracker_type == ...` esparcidos.

## 3. Principios y guardarraíles (no negociables, codificados en cada fase)

- **GP-1 Retro-compatibilidad byte-idéntica.** La selección es por `issue_tracker.type` por proyecto (default `azure_devops`). Para proyectos ADO, el código pasa por `AdoTrackerProvider`, wrapper delgado que **no cambia ningún comportamiento** del camino ADO actual. 0 regresiones es criterio de aceptación, no aspiración.
- **GP-2 Opt-in, cero trabajo al operador.** GitLab solo se activa si el operador setea `issue_tracker.type=gitlab` por UI + `STACKY_GITLAB_ENABLED=true` (kill-switch) + credenciales. Sin pasos manuales nuevos obligatorios para quien usa ADO/Jira/Mantis.
- **GP-3 Secretos por archivo, nunca en profile.** `GITLAB_TOKEN` se resuelve por env o por archivo bajo `auth/gitlab_auth.json` (mismo patrón que `auth/jira_auth.json`/`auth/mantis_auth.json`). El `issue_tracker` del profile solo guarda referencias no-secretas (`auth_file`, `gitlab_url`, `gitlab_project`, `gitlab_group`).
- **GP-4 Config del operador siempre por UI.** El selector de provider y los campos GitLab son editables desde la UI (regla dura del repo), reusando `client_profile`/settings/harness flags. Solo kill-switches internos quedan env-only.
- **GP-5 Paridad de 3 runtimes.** Esto es integración de BACKEND/tracker, NO del runtime del agente (Codex CLI / Claude Code CLI / GitHub Copilot Pro). Los 3 runtimes publican/leen vía el MISMO puerto agnóstico y producen los mismos artefactos. Ninguna fase ata lógica a un runtime.
- **GP-6 Human-in-the-loop innegociable.** Nada de autonomía proactiva nueva. La única auto-publicación que existe (épica desde brief, solo Claude CLI) se mantiene idéntica, solo que su escritura pasa por el puerto.
- **GP-7 Mono-operador, sin auth real.** No se introduce RBAC ni multiusuario.
- **GP-8 No degradar.** Reusar `ado_read_cache`/`ado_write_outbox`/memoria colaborativa/flags del arnés/telemetría como mecanismos **agnósticos** (renombrar lógico opcional, no reescribir). No reinventar paginación, retries ni caché. Reusar `build_ado_client`/`resolve_project_context` (`project_context.py`) como el seam de construcción, no instanciar clientes pelados.

### 3.bis Flags y defaults (todos seguros; default ADO intacto)

| Flag / campo | Tipo | Default | Quién lo setea | Notas |
|---|---|---|---|---|
| `issue_tracker.type` (profile) | str | `azure_devops` | UI (ClientProfileEditor) | Valores: `azure_devops\|jira\|mantis\|gitlab`. Es el ÚNICO selector de tracker (no hay env paralela). |
| `STACKY_GITLAB_ENABLED` | bool | `false` | UI (harness flag) + env | Kill-switch. Aunque `type=gitlab`, si está `false` la fábrica degrada con `TrackerConfigError` ruidoso (no silencioso). |
| `STACKY_GITLAB_EPICS_NATIVE` | bool | `false` | UI (harness flag) + env | Epics nativos (Premium, nivel grupo). Default fallback issues+links. |
| `STACKY_GITLAB_CI_INFERENCE` | bool | `true` | UI (harness flag) + env | Solo aplica cuando `type=gitlab`. Si no hay pipelines/CI → fallback a inferencia LLM existente. Default `true` no cambia nada para ADO. |
| `GITLAB_URL` / `GITLAB_PROJECT` / `STACKY_GITLAB_GROUP` | str | `""` | UI + env | No-secretos. URL self-managed o gitlab.com. |
| `GITLAB_TOKEN` | secreto | (archivo) | archivo `auth/gitlab_auth.json` | NUNCA por UI/profile/endpoint de config. |

> Regla dura del repo (memoria `operator-config-always-via-ui`): toda flag que el operador deba setear es editable por UI reusando el panel de harness flags / ClientProfileEditor; solo kill-switches internos quedan env-only. Las 3 flags `STACKY_GITLAB_*` se exponen en el panel de flags (default off/seguro).

## 4. MATRIZ DE PARIDAD EXHAUSTIVA (capacidad ADO → método del puerto → recurso GitLab → fallback)

> Esta tabla es el **contrato del puerto**. El test de conformance (F0/F12) la refleja: cada fila debe estar implementada en `GitLabTrackerProvider` o el test falla. Sin "etc.".
> GitLab API v4 base: `{GITLAB_URL}/api/v4`. Proyecto: `/projects/{id|url-encoded-path}`. Grupo (para Epics): `/groups/{id}`.

### 4.1 Cliente núcleo (de `ado_client.py`)

| # | Capacidad ADO (símbolo) | Método del puerto `TrackerProvider` | Recurso GitLab v4 | Casos borde / fallback |
|---|---|---|---|---|
| 1 | `AdoClient.__init__(org, project, auth_path)` | `provider.connect()` / construcción del adapter | `{GITLAB_URL}` + `GITLAB_PROJECT` + token via archivo | self-managed (URL custom) vs gitlab.com; project como **id numérico** o **path url-encoded** (`group%2Fsub%2Fproj`). |
| 2 | `_request(method,url,body)` | interno del adapter (no en el puerto) | `requests`/`urllib` a `/api/v4/...` con header `PRIVATE-TOKEN` | Header GitLab es `PRIVATE-TOKEN: <token>` (NO `Authorization: Basic`). |
| 3 | `_request_with_retry` | interno | mismo + retry | Reusar la política de retry existente; respetar `Retry-After` (rate limit GitLab). |
| 4 | `ado_pat_present()` | `provider.credentials_present() -> bool` | token presente (env o archivo) | Igual semántica; sin tocar red. |
| 5 | `get_authenticated_user()` | `provider.get_authenticated_user() -> dict` | `GET /api/v4/user` | Devuelve `{id, username, name, email?}` normalizado al shape que hoy consume identity. |
| 6 | `fetch_open_work_items(wiql)` + `_wiql_ids` + `_batch_get` | `provider.fetch_open_items(query: TrackerQuery) -> list[dict]` | `GET /api/v4/projects/{id}/issues?state=opened&...` (paginado) | **WIQL no existe** en GitLab. F3 define `TrackerQuery` (dataclass: state, labels, milestone, assignee, search, parent_epic). El AdoProvider traduce `TrackerQuery→WIQL`; el GitLabProvider traduce `TrackerQuery→querystring`. |
| 7 | `work_item_url(id)` | `provider.item_url(id) -> str` | `{GITLAB_URL}/{project_path}/-/issues/{iid}` | OJO: GitLab issues tienen `id` global y `iid` por-proyecto; la URL usa `iid`. El puerto guarda ambos. |
| 8 | `get_work_item(id)` | `provider.get_item(id) -> dict` | `GET /projects/{id}/issues/{iid}` | Normalizar campos a `{id, iid, title, description, state, labels, assignees, web_url, updated_at, parent}`. |
| 9 | `fetch_states()` | `provider.fetch_states() -> list[str]` | estados fijos `["opened","closed"]` + labels de board | ADO tiene workflow rico; GitLab solo opened/closed + **labels** + **board lists**. El mapeo estado-lógico↔tracker vive en `tracker_state_machine` (F3). |
| 10 | `update_work_item_state(id,state)` | `provider.update_item_state(id, logical_state) -> dict` | `PUT /projects/{id}/issues/{iid}` con `state_event=close|reopen` y/o `add_labels`/`remove_labels` | Estado lógico (functional/technical/developer) → en GitLab = label de workflow (`stacky::functional`) + opened/closed. Mapa en `tracker_state_machine`. |
| 11 | `fetch_comments(id)` | `provider.fetch_comments(id) -> list[dict]` | `GET /projects/{id}/issues/{iid}/notes` | Notas incluyen system-notes; filtrar `system==true` salvo que se pidan. |
| 12 | `fetch_all_comments(id)` (paginado continuationToken) | `provider.fetch_all_comments(id) -> list[dict]` | `GET .../notes?per_page=100` + paginación por header `X-Next-Page` | **GitLab NO usa continuationToken**: paginar con headers `Link`/`X-Next-Page`/`X-Total-Pages`. Documentar en F2. Cap igual a ADO (40 páginas configurable). |
| 13 | `post_comment(id, html)` | `provider.post_comment(id, body) -> dict` | `POST /projects/{id}/issues/{iid}/notes` `{body}` | GitLab notes son **Markdown**, no HTML. F4 define `render_for_tracker(html)` → HTML para ADO, HTML-en-Markdown (GitLab acepta HTML embebido en MD) o conversión mínima. Mantener marcador idempotente intacto. |
| 14 | `comment_exists(id, marker)` | `provider.comment_exists(id, marker) -> bool` | scan de notas buscando substring del marcador | Idempotencia por marcador idéntica a ADO (substring HTML-comment-like). |
| 15 | `create_work_item(type, fields, parent?)` | `provider.create_item(item: TrackerItem) -> dict` | `POST /projects/{id}/issues` (`title`,`description`,`labels`,`assignee_ids`,`milestone_id`) | "type" (Epic/Feature/Story/Task) → en GitLab = **label de tipo** (`type::epic`...) o GitLab Epic real (F7). Parent vía F7. |
| 16 | `find_child_by_marker(parent, marker)` | `provider.find_child_by_marker(parent_id, marker) -> dict\|None` | listar hijos (F7) + scan de marcador | Reusa F7 (links/epics) + F14 idempotencia. |
| 17 | `update_work_item_assigned_to(id, identity)` | `provider.update_item_assignee(id, assignee) -> dict` | `PUT /projects/{id}/issues/{iid}` `{assignee_ids:[user_id]}` | GitLab usa `assignee_ids` (lista de **ids numéricos**), no display name. F6 resuelve username→id. |
| 18 | `fetch_attachments(id)` | `provider.fetch_attachments(id) -> list[dict]` | parsear links de upload en `description`/notas (`/uploads/...`) | GitLab NO tiene "attachments" como entidad: son **uploads** referenciados en Markdown. Listar = extraer del cuerpo. |
| 19 | `upload_attachment(file)` | `provider.upload_attachment(file) -> dict` | `POST /projects/{id}/uploads` (multipart) → devuelve `{markdown, url}` | Devuelve markdown `![](path)`. F5 lo inserta en el cuerpo (no hay "link_attachment_to_work_item" separado). |
| 20 | `link_attachment_to_work_item(id, att)` | `provider.link_attachment(id, att) -> dict` | editar `description`/nota para incluir el markdown del upload | En GitLab no es API separada: es texto en el cuerpo. F5 lo absorbe (no-op + edición de cuerpo). |
| 21 | `fetch_work_item_updates(id, since?)` | `provider.fetch_item_updates(id, since?) -> list[dict]` | `GET .../resource_label_events`, `.../resource_state_events`, `.../notes` (merge ordenado por fecha) | ADO `updates` es un stream unificado; GitLab lo parte en **resource_*_events**. F8 normaliza a la forma que consume `ado_edit_learning`. |

### 4.2 Servicios derivados (de `ado_*.py`)

| # | Servicio ADO (símbolo público) | Estrategia de paridad | Recurso GitLab / Fallback |
|---|---|---|---|
| 22 | `ado_publisher.publish_from_execution(...)` (épicas/issues/tasks idempotentes, jerarquía) | Refactor: reemplazar `_default_client()`/`_client_for_ticket_project()` por `get_tracker_provider(project)`. Toda llamada `client.create_work_item/post_comment/...` → `provider.*`. | Jerarquía via F7. Marcador idempotente y locks (`_get_ado_publish_lock`) intactos (renombrar lógicamente a `_publish_lock`). |
| 23 | `ado_context.build_ado_context_blocks/enrich` | Parametrizar por provider: lee items+comments+attachments vía puerto. | `build_tracker_context_blocks`. Misma forma de salida. |
| 24 | `ado_identity.resolve_me_unique_name/save_identity/get_cached_identity/user_matches` | Adapter de identidad por provider: ADO=`get_authenticated_user().uniqueName`; GitLab=`/user.username` + id. Caché de identidad reusa el mismo store (`_map_path`). | GitLab assignee = id numérico; cachear `{username, id}`. |
| 25 | `ado_pipeline_inference.infer_pipeline/invalidate_cache` | Fuente de pipelines por provider. ADO=inferencia LLM sobre ticket; GitLab=**CI real**. | `GET /projects/{id}/pipelines` + `/pipelines/{pid}/jobs`. Fallback si CI deshabilitado: mantener inferencia LLM existente. Caché reusa `PipelineInferenceCache`. |
| 26 | `ado_read_cache.get_or_fetch/invalidate/is_warm/clear` | **Agnóstico ya** (cachea por `key` tuple + `fetch_fn`). Solo cambia quién es `fetch_fn` (el provider). | Reusar tal cual. Renombrar lógico opcional a `tracker_read_cache` sin romper imports (alias). |
| 27 | `ado_write_outbox.enqueue/claim/claim_due/mark_*/list_operations/summary` | **Agnóstico ya** (encola operaciones + persiste estado; `_apply` solo hace `setattr` en DB, NO llama clientes — `ado_write_outbox.py:334`). El despacho real lo hace el **consumidor** de la outbox (identificarlo por grep en F10 antes de tocar: `grep -rn 'claim_due\|claim(' backend`), y ESE consumidor usa `get_tracker_provider()`. | El store/backoff/tabla quedan INTACTOS. Solo el consumidor cambia su forma de construir el cliente. |
| 28 | `ado_sync.sync_tickets/upsert_single_work_item/purge_*/get_last_sync_at` | Parametrizar la fuente: `fetch_open_items` + `get_item` vía puerto. `_extract_assignee` se vuelve provider-aware (ADO fields vs GitLab assignees). | `sync_tickets(provider=...)`. Modelo local `Ticket` sin cambios (guarda `tracker_id`, `tracker_project`). |
| 29 | `ado_edit_learning.learn_from_work_item/sweep_recent_runs/edit_to_lesson_content` | Consume `fetch_item_updates` (F8) vía puerto en lugar de `AdoClient.fetch_work_item_updates`. | Delta de edición se computa desde resource_*_events. Golden/corpus intactos. |
| 30 | `ado_edit_ledger` (ledger de ediciones) | **Agnóstico** (persistencia local). Solo cambia el origen del fetch (F8). | Sin cambios estructurales. |
| 31 | `ado_feedback.comment_run_outcome` | Usa `provider.post_comment`. | Mismo marcador/idempotencia. |
| 32 | `api/ado_manager.create_project_task` | Usa `provider.create_item`. | Trivial. |
| 33 | `api/tickets.py` (acceso INDIRECTO al cliente) | `tickets.py` NO instancia `AdoClient(` (grep=0). El cliente se obtiene vía `ado_publisher._client_for_ticket_project()`/`_default_client()` (`ado_publisher.py:373,573,579,607`). F10 reescribe ESOS dos helpers para devolver `get_tracker_provider(project)` (un solo punto), y las ~37 referencias `ado_*`/`import ado` de `tickets.py` siguen funcionando porque el puerto expone los mismos métodos. | Enumerar los call-sites de `ado_publisher` y `tickets.py` por grep en F10; ninguno queda con `AdoClient` directo salvo `ado_provider.py`/`project_context.build_ado_client`. |
| 34 | Estados lógicos (`client_profile.tracker_state_machine`) | El mapa estado-lógico→tracker se parametriza por provider dentro del profile (subsección `gitlab`/`ado`). | ADO=nombres de estado; GitLab=labels + opened/closed. |
| 35 | `work_item_url` en footers/telemetría (`ado_publisher._render_run_footer`) | Usa `provider.item_url`. | URL GitLab por `iid`. |

**Resumen de gaps GitLab y su fallback explícito:**
- **G1 — Epics solo en GitLab Premium y a nivel GRUPO.** Fallback (F7): si `STACKY_GITLAB_EPICS_NATIVE=false` (default) o el plan no es Premium, modelar la jerarquía con **issues + labels de tipo (`type::epic|feature|story|task`) + links padre/hijo** vía `POST /projects/{id}/issues/{iid}/links`. Si `true` y hay grupo, usar `/groups/{gid}/epics` + `/epics/{eid}/issues`.
- **G2 — WIQL no existe.** Fallback: `TrackerQuery` dataclass agnóstica traducida por cada adapter (F3).
- **G3 — Paginación distinta.** GitLab usa headers `Link`/`X-Next-Page`, no `continuationToken` (F2/F12).
- **G4 — Comentarios Markdown, no HTML.** GitLab notes aceptan HTML embebido en Markdown; F4 mantiene el HTML del artefacto y solo garantiza que el marcador idempotente sobreviva.
- **G5 — Attachments = uploads en cuerpo.** No hay entidad attachment (F5).
- **G6 — Estados pobres (opened/closed).** El workflow lógico se modela con labels (F3/estado-máquina del profile).

## 5. Fases F0..F13

> Convención de comando de test (Windows/PowerShell, venv del repo):
> `& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "backend/tests/<archivo>" -q`
> (equivalente bash: `backend/.venv/Scripts/python.exe -m pytest backend/tests/<archivo> -q`). Correr **por archivo** (pin pywin32==306 roto en 3.13 contamina full-suite). Frontend gate: `cd frontend; npx tsc --noEmit` (vitest NO instalado).

---

### F0 — Puerto `TrackerProvider` + contrato + conformance esqueleto

**Objetivo (1 frase).** Definir el puerto único `TrackerProvider` (Protocol/ABC) que abstrae las 21 capacidades del cliente + tipos de dominio, sin implementación todavía. **Valor:** congela el contrato que verifica "no falta ninguna función".

**Archivos a CREAR:**
- `backend/services/tracker_provider.py`
- `backend/tests/test_tracker_provider_conformance.py`

**Símbolos exactos a crear en `tracker_provider.py`:**
```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable, Optional

# --- Tipos de dominio agnósticos ---
@dataclass(frozen=True)
class TrackerQuery:
    state: str = "open"            # "open" | "closed" | "all"
    labels: tuple[str, ...] = ()
    milestone: Optional[str] = None
    assignee: Optional[str] = None
    search: Optional[str] = None
    parent_id: Optional[str] = None

@dataclass(frozen=True)
class TrackerItem:
    item_type: str                 # "epic" | "feature" | "story" | "task" | "issue"
    title: str
    description_html: str
    labels: tuple[str, ...] = ()
    assignee: Optional[str] = None
    parent_id: Optional[str] = None
    fields: dict = field(default_factory=dict)

class TrackerError(RuntimeError): ...
class TrackerConfigError(TrackerError): ...
class TrackerApiError(TrackerError):
    def __init__(self, status: int, message: str, *, kind: str = "unknown"):
        super().__init__(message); self.status = status; self.kind = kind

@runtime_checkable
class TrackerProvider(Protocol):
    name: str                                      # "ado" | "gitlab"
    def credentials_present(self) -> bool: ...
    def get_authenticated_user(self) -> dict: ...
    def fetch_open_items(self, query: TrackerQuery) -> list[dict]: ...
    def get_item(self, item_id: str) -> dict: ...
    def item_url(self, item_id: str) -> str: ...
    def fetch_states(self) -> list[str]: ...
    def update_item_state(self, item_id: str, logical_state: str) -> dict: ...
    def fetch_comments(self, item_id: str) -> list[dict]: ...
    def fetch_all_comments(self, item_id: str) -> list[dict]: ...
    def post_comment(self, item_id: str, body_html: str) -> dict: ...
    def comment_exists(self, item_id: str, marker: str) -> bool: ...
    def create_item(self, item: TrackerItem) -> dict: ...
    def find_child_by_marker(self, parent_id: str, marker: str) -> Optional[dict]: ...
    def update_item_assignee(self, item_id: str, assignee: str) -> dict: ...
    def fetch_attachments(self, item_id: str) -> list[dict]: ...
    def upload_attachment(self, file_path: str, file_name: str) -> dict: ...
    def link_attachment(self, item_id: str, attachment: dict) -> dict: ...
    def fetch_item_updates(self, item_id: str, since: Optional[str] = None) -> list[dict]: ...

# Lista canónica de métodos que el conformance recorre (refleja la matriz).
PORT_METHODS: tuple[str, ...] = (
    "credentials_present","get_authenticated_user","fetch_open_items","get_item",
    "item_url","fetch_states","update_item_state","fetch_comments","fetch_all_comments",
    "post_comment","comment_exists","create_item","find_child_by_marker",
    "update_item_assignee","fetch_attachments","upload_attachment","link_attachment",
    "fetch_item_updates",
)
```

**Tests primero (`test_tracker_provider_conformance.py`), casos:**
- `test_port_methods_list_matches_protocol`: cada nombre en `PORT_METHODS` existe como método declarado en `TrackerProvider`. (Detecta drift entre matriz y puerto.)
- `test_tracker_query_and_item_are_frozen`: instanciar y verificar inmutabilidad (`dataclasses.FrozenInstanceError` al asignar).
- `test_api_error_carries_status_and_kind`: `TrackerApiError(404,"x",kind="not_found").status==404` y `.kind=="not_found"`.

> Nota anti-falso-verde (C6): este F0 solo congela el CONTRATO. La verificación de COMPORTAMIENTO (que ningún método sea un stub `NotImplementedError`) vive en F12 (**[ADICIÓN ARQUITECTO #1]**), no aquí.

**Comando:** `& "...\.venv\Scripts\python.exe" -m pytest "backend/tests/test_tracker_provider_conformance.py" -q`
**Criterio binario:** los 3 tests pasan.
**Flag:** ninguno (solo define tipos). **Impacto runtime:** ninguno (no se cablea aún). **Trabajo del operador:** ninguno.

---

### F1 — `AdoTrackerProvider` (wrapper byte-idéntico sobre `AdoClient`)

**Objetivo.** Implementar el adapter ADO que envuelve el `AdoClient`/`ado_publisher` actuales 1:1, sin cambiar comportamiento. **Valor:** prueba que el puerto cubre 100% de ADO y deja el camino default intacto.

**Archivos a CREAR:** `backend/services/ado_provider.py`, `backend/tests/test_ado_provider.py`.
**Archivos a EDITAR:** ninguno de los `ado_*` (solo se envuelven).

**Símbolos a crear (`ado_provider.py`):**
```python
from services.project_context import build_ado_client   # REUSO: resuelve org/project/auth y setea tracker_type (project_context.py:208)
from services.ado_client import AdoClient                # solo para fallback explícito de tests

class AdoTrackerProvider:               # implementa TrackerProvider (duck/Protocol)
    name = "ado"
    def __init__(self, project: str | None = None, *, client: AdoClient | None = None):
        # REUSO del seam existente (no instanciar AdoClient pelado): build_ado_client ya
        # resuelve org/project/auth_file y valida tracker_type==azure_devops.
        self._client = client if client is not None else build_ado_client(project_name=project)
    # cada método delega 1:1, normalizando al shape canónico de _normalize_issue (mismo dict
    # que GitLab: {id,iid,title,description,state,labels,assignees,web_url,updated_at,parent}):
    def name_attr(self): return self.name
    def credentials_present(self):        return self._client.ado_pat_present()
    def get_authenticated_user(self):     return self._client.get_authenticated_user()
    def fetch_open_items(self, query):    return self._client.fetch_open_work_items(_query_to_wiql(query))
    def get_item(self, item_id):          return _normalize_ado(self._client.get_work_item(int(item_id)))
    def item_url(self, item_id):          return self._client.work_item_url(int(item_id))
    def fetch_states(self):               return self._client.fetch_states()
    def update_item_state(self, item_id, logical_state):
        return self._client.update_work_item_state(int(item_id), _logical_to_ado_state(logical_state))
    def fetch_comments(self, item_id):    return self._client.fetch_comments(int(item_id))
    def fetch_all_comments(self, item_id):return self._client.fetch_all_comments(int(item_id))
    def post_comment(self, item_id, body_html): return self._client.post_comment(int(item_id), body_html)
    def comment_exists(self, item_id, marker):  return self._client.comment_exists(int(item_id), marker)
    def create_item(self, item):
        return _normalize_ado(self._client.create_work_item(
            _item_type_to_ado(item.item_type), _item_to_fields(item),
            parent=int(item.parent_id) if item.parent_id else None))
    def find_child_by_marker(self, parent_id, marker):
        return self._client.find_child_by_marker(int(parent_id), marker)
    def update_item_assignee(self, item_id, assignee):
        return self._client.update_work_item_assigned_to(int(item_id), assignee)
    def fetch_attachments(self, item_id):       return self._client.fetch_attachments(int(item_id))
    def upload_attachment(self, file_path, file_name): return self._client.upload_attachment(file_path, file_name)
    def link_attachment(self, item_id, attachment):    return self._client.link_attachment_to_work_item(int(item_id), attachment)
    def fetch_item_updates(self, item_id, since=None): return self._client.fetch_work_item_updates(int(item_id))

def _query_to_wiql(query: TrackerQuery) -> str: ...   # construye el WIQL que hoy se usa (snapshot exacto del WIQL vigente)
def _item_type_to_ado(t: str) -> str:                 # "epic"->"Epic","feature"->"Feature","story"->"User Story","task"->"Task","issue"->"Issue"
    return {"epic":"Epic","feature":"Feature","story":"User Story","task":"Task","issue":"Issue"}[t]
def _item_to_fields(item: TrackerItem) -> dict:       # {"System.Title":item.title,"System.Description":item.description_html, ...labels/assignee}
    ...
def _logical_to_ado_state(logical_state: str) -> str: ...  # del tracker_state_machine del profile (rama ado); identidad si no hay mapa
def _normalize_ado(wi: dict) -> dict:                 # mapea campos ADO -> shape canónico (id=iid=id ADO; parent de relations)
    ...
```
> Nota: cada método del puerto está aquí explícito (18 de `PORT_METHODS`). No queda ningún `...` con lógica de despacho; los `...` restantes son helpers puros de mapeo cuyo contrato está descrito inline (entrada→salida), implementables por Haiku sin inferir.

**Tests primero (`test_ado_provider.py`), casos (con `AdoClient` mockeado, sin red):**
- `test_ado_provider_is_tracker_provider`: `isinstance(AdoTrackerProvider(), TrackerProvider)` (runtime_checkable) Y `all(hasattr(p, m) for m in PORT_METHODS)`.
- `test_fetch_open_items_builds_same_wiql`: `_query_to_wiql` produce el WIQL esperado (string snapshot del actual).
- `test_create_item_maps_type_and_fields`: epic/feature/story/task → tipos ADO correctos.
- `test_post_comment_delegates_unchanged`: el body pasa intacto a `post_comment`.
- `test_fetch_item_updates_delegates`: id se castea a int.

**Comando:** `... -m pytest "backend/tests/test_ado_provider.py" -q`
**Criterio binario:** todos pasan; `AdoTrackerProvider` satisface `PORT_METHODS` completo.
**Flag:** ninguno propio — la selección la hace la fábrica F10 vía `issue_tracker.type` (default `azure_devops`); aquí el provider se construye explícito en los tests.
**Impacto runtime:** ninguno aún (no se cablea hasta F10). **Trabajo del operador:** ninguno.

---

### F2 — Cliente GitLab REST núcleo (`gitlab_client.py`)

**Objetivo.** Cliente REST v4 con auth por `PRIVATE-TOKEN`, `_request`, retry con `Retry-After`, paginación por headers `Link`/`X-Next-Page`, y taxonomía de errores `GitLabApiError` mapeada a `TrackerApiError`. **Valor:** base de red robusta y reutilizable.

**Archivos a CREAR:** `backend/services/gitlab_client.py`, `backend/tests/test_gitlab_client.py`.
**Archivos a EDITAR:** `backend/config.py` (env GitLab).

**Env nuevas en `config.py` (junto a ADO, ~líneas 445-447):**
```python
GITLAB_URL = os.getenv("GITLAB_URL", "")            # e.g. https://gitlab.com  (sin trailing slash)
GITLAB_PROJECT = os.getenv("GITLAB_PROJECT", "")    # id numérico o path "grupo/sub/proj"
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN", "")        # PAT (fallback; preferir archivo auth/)
STACKY_GITLAB_GROUP = os.getenv("STACKY_GITLAB_GROUP", "")  # para Epics nativos (F7)
```
**Resolución de secreto (espejo del patrón Jira/Mantis ya existente, `gitlab_client.py`):** orden `env GITLAB_TOKEN` → archivo `issue_tracker.auth_file` del profile activo (campo `token`) → default `auth/gitlab_auth.json` (campo `token`). NUNCA leer token del `issue_tracker` plano del profile. (El campo del profile es `issue_tracker`, NO `tracker` — `project_manager.py:100`, `project_context.py:72`. Default auth-file por tracker como en `global_config.py:93-97`.)

**Símbolos a crear (`gitlab_client.py`):**
```python
class GitLabConfigError(TrackerConfigError): ...
class GitLabApiError(TrackerApiError): ...
def gitlab_token_present() -> bool: ...
class GitLabClient:
    def __init__(self, base_url=None, project=None, auth_path=None): ...
    def _headers(self) -> dict: return {"PRIVATE-TOKEN": self._token, "Accept":"application/json"}
    def _project_path(self) -> str: ...   # url-encode si es path con "/"
    def _request(self, method, path, *, params=None, json=None, files=None) -> tuple[dict|list, dict]:
        # devuelve (body, response_headers); mapea status->GitLabApiError(kind=...)
    def _request_paginated(self, path, *, params=None, page_cap=40) -> list:
        # sigue X-Next-Page hasta agotar o page_cap
    def _map_error(self, status: int) -> str:  # 401/403->"auth", 404->"not_found", 429->"rate_limited", 5xx->"server"
```

**Tests primero (`test_gitlab_client.py`), casos (con `requests`/transport mockeado, sin red):**
- `test_headers_use_private_token`.
- `test_project_path_urlencodes_slash_path`: `"grp/sub/proj"` → `"grp%2Fsub%2Fproj"`; id numérico queda igual.
- `test_pagination_follows_x_next_page`: 3 páginas simuladas → lista concatenada; respeta `page_cap`.
- `test_retry_honors_retry_after_on_429`: 429 con `Retry-After: 0` → reintenta y luego 200.
- `test_error_mapping_taxonomy`: 401→kind="auth", 404→"not_found", 429→"rate_limited", 503→"server".
- `test_missing_token_raises_config_error`.

**Comando:** `... -m pytest "backend/tests/test_gitlab_client.py" -q`
**Criterio binario:** todos pasan; cero llamadas de red reales.
**Flag:** `STACKY_GITLAB_ENABLED` (default `false`). **Impacto runtime:** ninguno (no se cablea). **Trabajo del operador:** opt-in (default off).

---

### F3 — `GitLabTrackerProvider`: issues CRUD + estados + `TrackerQuery`→filtros

**Objetivo.** Adapter GitLab para items (filas 5-10,15 de la matriz): user, fetch_open_items, get_item, item_url, fetch_states, update_item_state, create_item. **Valor:** lectura/escritura básica de issues con paridad de query y estados lógicos.

**Archivos a CREAR:** `backend/services/gitlab_provider.py`, `backend/tests/test_gitlab_provider.py`.
**Archivos a EDITAR:** `backend/services/client_profile.py` (subsección `tracker_state_machine.gitlab`: mapa estado-lógico→`{label, closed:bool}`; default sano si ausente).

**Símbolos a crear (`gitlab_provider.py`):**
```python
class GitLabTrackerProvider:
    name = "gitlab"
    def __init__(self, project=None):
        self._c = GitLabClient(project=project)
    def credentials_present(self): return gitlab_token_present()
    def get_authenticated_user(self):
        u,_ = self._c._request("GET","/user"); return {"id":u["id"],"username":u["username"],"name":u.get("name"),"email":u.get("email")}
    def fetch_open_items(self, query):
        return self._c._request_paginated(f"/projects/{self._c._project_path()}/issues", params=_query_to_gitlab_params(query))
    def get_item(self, item_id):
        body,_ = self._c._request("GET", f"/projects/{self._c._project_path()}/issues/{item_id}")
        return _normalize_issue(body)
    def item_url(self, item_id):   # usa iid + web_url
        return self.get_item(item_id)["web_url"]
    def fetch_states(self): return ["opened","closed"]
    def update_item_state(self, item_id, logical_state):
        # Mapa estado-lógico -> {label, closed:bool} desde el profile (default sano si ausente).
        entry = _state_map_for_gitlab().get(logical_state, {"label": f"stacky::{logical_state}", "closed": False})
        payload: dict = {"add_labels": entry["label"]}
        # state_event solo si el mapeo indica cierre/reapertura; GitLab acepta close|reopen.
        payload["state_event"] = "close" if entry.get("closed") else "reopen"
        body, _ = self._c._request("PUT", f"/projects/{self._c._project_path()}/issues/{item_id}", json=payload)
        return _normalize_issue(body)
    def create_item(self, item):
        payload = {"title":item.title, "description":item.description_html,
                   "labels":",".join((*item.labels, _type_label(item.item_type)))}
        if item.assignee:
            uid = _resolve_assignee_id(self._c, item.assignee)   # F3 stub: lambda c,u: None  (sobreescrito en F6)
            if uid: payload["assignee_ids"]=[uid]
        body,_ = self._c._request("POST", f"/projects/{self._c._project_path()}/issues", json=payload)
        if item.parent_id:
            _link_parent(self._c, body["iid"], item.parent_id)   # F3 stub: lambda c,ci,pi: None  (sobreescrito en F7)
        return _normalize_issue(body)
def _query_to_gitlab_params(q: TrackerQuery) -> dict:
    # state "open"->"opened","closed"->"closed","all"->"all"; labels -> csv; milestone, assignee->assignee_username, search
    state = {"open":"opened","closed":"closed","all":"all"}.get(q.state, "opened")
    p: dict = {"state": state}
    if q.labels: p["labels"] = ",".join(q.labels)
    if q.milestone: p["milestone"] = q.milestone
    if q.assignee: p["assignee_username"] = q.assignee
    if q.search: p["search"] = q.search
    return p
def _normalize_issue(body: dict) -> dict:
    # SHAPE CANÓNICO exacto (mismas claves que _normalize_ado de F1):
    return {"id": body.get("id"), "iid": body.get("iid"), "title": body.get("title"),
            "description": body.get("description"), "state": body.get("state"),
            "labels": tuple(body.get("labels") or ()), "assignees": body.get("assignees") or [],
            "web_url": body.get("web_url"), "updated_at": body.get("updated_at"),
            "parent": body.get("epic") or None}
def _type_label(t: str) -> str: return f"type::{t}"
def _state_map_for_gitlab() -> dict:
    # Lee client_profile.tracker_state_machine (rama gitlab). Default sano si ausente:
    # {"functional":{"label":"stacky::functional","closed":False},
    #  "technical":{"label":"stacky::technical","closed":False},
    #  "developer":{"label":"stacky::developer","closed":False}}
    ...
# === STUBS DE DEPENDENCIA INTER-FASE (C8) — definidos en F3, sobreescritos luego ===
def _resolve_assignee_id(client, username):  # F3: stub no-op; F6 lo implementa de verdad.
    return None
def _link_parent(client, child_iid, parent_id):  # F3: stub no-op; F7 lo implementa de verdad.
    return None
```
> **Orden/dependencias (C8):** `_resolve_assignee_id` (F6) y `_link_parent` (F7) se declaran como **stubs no-op en F3** para que el test de F3 NO dependa de fases posteriores. F6 y F7 reemplazan el cuerpo del stub (misma firma). El test `test_create_item_with_parent_calls_link` de F3 mockea `_link_parent` (verifica que se invoca), no su implementación real. Así cada fase es verde de forma aislada.

**Tests primero (`test_gitlab_provider.py`), casos (con `GitLabClient` mockeado):**
- `test_fetch_open_items_translates_query`: `TrackerQuery(state="open", labels=("a",), search="x")` → params `{state:"opened", labels:"a", search:"x"}`.
- `test_create_item_sets_type_label`: epic → label `type::epic` presente.
- `test_create_item_with_parent_calls_link`: parent_id → invoca `_link_parent` (mock F7).
- `test_update_item_state_maps_logical_to_label_and_close`.
- `test_normalize_issue_shape`: salida tiene exactamente las claves del shape canónico.
- `test_get_authenticated_user_shape`.

**Comando:** `... -m pytest "backend/tests/test_gitlab_provider.py" -q`
**Criterio binario:** todos pasan.
**Flag:** `STACKY_GITLAB_ENABLED` (default false). **Impacto runtime:** ninguno (sin cablear). **Trabajo del operador:** opt-in.

---

### F4 — Comments/notes idempotentes por marcador

**Objetivo.** Implementar `post_comment`, `fetch_comments`, `fetch_all_comments`, `comment_exists`, `find_child_by_marker` en GitLab con el MISMO marcador idempotente que ADO. **Valor:** garantiza que re-publicar no duplica (idempotencia inter-tracker).

**Archivos a EDITAR:** `backend/services/gitlab_provider.py`, `backend/tests/test_gitlab_provider.py` (agregar casos).

**Pseudocódigo:**
```python
def post_comment(self, item_id, body_html):
    body,_ = self._c._request("POST", f"/projects/{self._c._project_path()}/issues/{item_id}/notes",
                              json={"body": _render_note(body_html)})
    return body
def fetch_comments(self, item_id):
    notes = self._c._request_paginated(f".../issues/{item_id}/notes")
    return [n for n in notes if not n.get("system")]
def fetch_all_comments(self, item_id):  # incluye system, paginado completo, cap configurable
    return self._c._request_paginated(f".../notes", page_cap=_comment_page_cap())
def comment_exists(self, item_id, marker):
    return any(marker in (n.get("body") or "") for n in self.fetch_all_comments(item_id))
def _render_note(html: str) -> str:  # marcador HTML-comment sobrevive en Markdown de GitLab
    return html   # GitLab acepta HTML embebido; marcador intacto
```
**Casos borde:** notas `system==true` excluidas de `fetch_comments` pero incluidas en `comment_exists`/`fetch_all_comments`; cap de páginas reusa flag `STACKY_COMMENT_FULL_SCAN_ENABLED` (ya existe, plan 52).

**Tests (agregados a `test_gitlab_provider.py`):**
- `test_comment_exists_finds_marker`.
- `test_comment_exists_false_when_absent`.
- `test_fetch_comments_excludes_system_notes`.
- `test_post_comment_preserves_marker_substring`.

**Comando:** `... -m pytest "backend/tests/test_gitlab_provider.py" -q`
**Criterio binario:** todos pasan.
**Flag:** `STACKY_GITLAB_ENABLED`. **Impacto runtime:** ninguno. **Trabajo del operador:** opt-in.

---

### F5 — Attachments/uploads

**Objetivo.** `upload_attachment`, `link_attachment`, `fetch_attachments` en GitLab vía `/uploads` + inserción de markdown en el cuerpo. **Valor:** los artefactos HTML con adjuntos se publican igual que en ADO.

**Archivos a EDITAR:** `backend/services/gitlab_provider.py`, `backend/tests/test_gitlab_provider.py`.

**Pseudocódigo:**
```python
def upload_attachment(self, file_path, file_name):
    body,_ = self._c._request("POST", f"/projects/{self._c._project_path()}/uploads",
                              files={"file": (file_name, open(file_path,"rb"))})
    return {"markdown": body["markdown"], "url": body["url"], "alt": body.get("alt", file_name)}
def link_attachment(self, item_id, attachment):
    # GitLab no liga: edita description para incluir attachment["markdown"]
    item = self.get_item(item_id)
    new_desc = (item["description"] or "") + "\n\n" + attachment["markdown"]
    body,_ = self._c._request("PUT", f".../issues/{item_id}", json={"description": new_desc})
    return body
def fetch_attachments(self, item_id):
    desc = self.get_item(item_id)["description"] or ""
    return _extract_uploads(desc)   # regex de "/uploads/<hash>/<name>"
```
**Casos borde:** archivo inexistente → `TrackerApiError(kind="not_found")`; nombre con espacios → `_safe_upload_name` (reusar de `ado_publisher.py:826`).

**Tests:**
- `test_upload_returns_markdown_and_url`.
- `test_link_attachment_appends_to_description`.
- `test_fetch_attachments_parses_upload_links`.

**Comando:** `... -m pytest "backend/tests/test_gitlab_provider.py" -q`
**Criterio binario:** todos pasan. **Flag:** `STACKY_GITLAB_ENABLED`. **Impacto runtime:** ninguno. **Trabajo del operador:** opt-in.

---

### F6 — Identity / assignees

**Objetivo.** `update_item_assignee` + resolución `username→id` y `resolve_me`, integrando `ado_identity` como capa agnóstica. **Valor:** asignación de responsables funciona en ambos trackers.

**Archivos a EDITAR:** `backend/services/gitlab_provider.py`, `backend/services/ado_identity.py` (hacer `resolve_me_unique_name` provider-aware o agregar `resolve_me(provider)`), `backend/tests/test_gitlab_provider.py`.

**Pseudocódigo (`gitlab_provider.py`):**
```python
def update_item_assignee(self, item_id, assignee):
    uid = _resolve_assignee_id(self._c, assignee)
    body,_ = self._c._request("PUT", f".../issues/{item_id}", json={"assignee_ids":[uid] if uid else []})
    return body
def _resolve_assignee_id(client, username):
    if username is None: return None
    users = client._request("GET","/users", params={"username": username})[0]
    return users[0]["id"] if users else None   # cachear en ado_identity store
```
**Casos borde:** username no existe → assignee vacío (no error duro), log warning. `resolve_me` para GitLab = `get_authenticated_user()["username"]`.

**Tests:**
- `test_resolve_assignee_id_by_username`.
- `test_update_assignee_sets_assignee_ids`.
- `test_unknown_username_clears_assignee`.
- (en `test_ado_identity.py` si existe) `test_resolve_me_dispatches_by_provider`.

**Comando:** `... -m pytest "backend/tests/test_gitlab_provider.py" -q`
**Criterio binario:** todos pasan. **Flag:** `STACKY_GITLAB_ENABLED`. **Impacto runtime:** ninguno. **Trabajo del operador:** opt-in.

---

### F7 — Jerarquía épica↔hijos (Epics nativos Premium con fallback issues+links)

**Objetivo.** Implementar `create_item` con parent y `find_child_by_marker` para jerarquía Epic/Feature/Story/Task. **Valor:** la descomposición épica→hijos (planes 55/59) funciona en GitLab.

**Archivos a EDITAR:** `backend/services/gitlab_provider.py`, `backend/tests/test_gitlab_provider.py`. **Env:** `STACKY_GITLAB_EPICS_NATIVE` (default `false`).

**Dos modos (pseudocódigo):**
```python
def _link_parent(client, child_iid, parent_id):
    if config.STACKY_GITLAB_EPICS_NATIVE and config.STACKY_GITLAB_GROUP:
        # parent es un Epic de grupo: POST /groups/{gid}/epics/{eid}/issues
        client._request("POST", f"/groups/{group}/epics/{parent_id}/issues", params={"issue_id": child_global_id})
    else:
        # FALLBACK: issue-link padre/hijo
        client._request("POST", f"/projects/{path}/issues/{child_iid}/links",
                        json={"target_project_id": project_id, "target_issue_iid": parent_iid, "link_type":"is_child_of"})
def find_child_by_marker(self, parent_id, marker):
    children = self._list_children(parent_id)   # /links o /epics/{id}/issues según modo
    for c in children:
        if self.comment_exists(c["iid"], marker) or marker in (c.get("description") or ""):
            return c
    return None
```
**Casos borde:** sin Premium y `EPICS_NATIVE=true` → GitLab responde 403 → capturar y **degradar a fallback** con log warning (no romper). Sin grupo configurado → forzar fallback. Epic global_id vs iid: documentar y normalizar.

**Tests:**
- `test_link_parent_uses_issue_links_in_fallback`.
- `test_link_parent_uses_group_epic_when_native_and_group_set`.
- `test_native_epics_403_degrades_to_fallback` (mock 403 → segunda llamada a /links).
- `test_find_child_by_marker_matches_description_or_comment`.

**Comando:** `... -m pytest "backend/tests/test_gitlab_provider.py" -q`
**Criterio binario:** todos pasan. **Flags:** `STACKY_GITLAB_ENABLED`, `STACKY_GITLAB_EPICS_NATIVE` (default false). **Impacto runtime:** ninguno. **Trabajo del operador:** opt-in.

---

### F8 — Updates / edit-learning ↔ resource events

**Objetivo.** `fetch_item_updates` en GitLab fusionando `resource_label_events` + `resource_state_events` + notes, normalizado a la forma que consume `ado_edit_learning`. **Valor:** el aprendizaje bidireccional de ediciones (plan 60) funciona con GitLab.

**Archivos a EDITAR:** `backend/services/gitlab_provider.py`, `backend/services/ado_edit_learning.py` (consumir vía puerto `provider.fetch_item_updates` en lugar de `AdoClient.fetch_work_item_updates`), `backend/tests/test_gitlab_provider.py`.

**Pseudocódigo:**
```python
def fetch_item_updates(self, item_id, since=None):
    label_ev = self._c._request_paginated(f".../issues/{item_id}/resource_label_events")
    state_ev = self._c._request_paginated(f".../issues/{item_id}/resource_state_events")
    notes    = self._c._request_paginated(f".../issues/{item_id}/notes")
    merged = _merge_events(label_ev, state_ev, notes, since)   # ordena por created_at, normaliza a {field, old, new, by, at}
    return merged
```
**Casos borde:** `since` ISO → filtrar `created_at > since`; eventos sin `old`/`new` (label add/remove) → mapear a `{field:"label", new:label}`.

**Tests:**
- `test_fetch_item_updates_merges_and_sorts`.
- `test_fetch_item_updates_filters_by_since`.
- `test_label_event_normalized_shape`.
- (`test_ado_edit_learning.py`) `test_learn_uses_provider_updates` (mock provider).

**Comando:** `... -m pytest "backend/tests/test_gitlab_provider.py" -q` y `... test_ado_edit_learning.py -q`.
**Criterio binario:** todos pasan; `ado_edit_learning` no referencia `AdoClient` directo.
**Flag:** `STACKY_GITLAB_ENABLED`. **Impacto runtime:** ninguno. **Trabajo del operador:** opt-in.

---

### F9 — Pipeline inference ↔ GitLab CI

**Objetivo.** Hacer `ado_pipeline_inference.infer_pipeline` provider-aware: GitLab usa CI real (`/pipelines`); ADO mantiene inferencia LLM. **Valor:** el contexto de pipeline es real (no inferido) cuando hay GitLab CI.

**Archivos a EDITAR:** `backend/services/ado_pipeline_inference.py` (rama por tracker; o nuevo `gitlab_provider.fetch_pipelines`), `backend/tests/test_gitlab_provider.py`. **Env:** `STACKY_GITLAB_CI_INFERENCE` (default `true`; solo tiene efecto cuando `issue_tracker.type=gitlab`).

**Pseudocódigo (en `gitlab_provider.py`):**
```python
def fetch_pipelines(self, item_id=None, ref=None) -> list[dict]:
    params = {"ref": ref} if ref else {}
    pipelines = self._c._request_paginated(f"/projects/{path}/pipelines", params=params)
    return [{"id":p["id"],"status":p["status"],"ref":p["ref"],"web_url":p["web_url"]} for p in pipelines]
```
`infer_pipeline` decide: si `issue_tracker.type=gitlab` y `STACKY_GITLAB_CI_INFERENCE` on → `fetch_pipelines` + mapear a `PipelineInferenceResult`; si CI deshabilitado/sin pipelines → **fallback** a la inferencia LLM existente. Caché reusa `PipelineInferenceCache`.

**Tests:**
- `test_fetch_pipelines_normalizes`.
- `test_infer_pipeline_uses_ci_when_gitlab` (mock).
- `test_infer_pipeline_falls_back_to_llm_when_no_ci`.

**Comando:** `... -m pytest "backend/tests/test_gitlab_provider.py" -q`.
**Criterio binario:** todos pasan. **Flags:** `STACKY_GITLAB_ENABLED`, `STACKY_GITLAB_CI_INFERENCE`. **Impacto runtime:** ninguno. **Trabajo del operador:** opt-in.

---

### F10 — Wiring: fábrica de provider + reemplazo de call-sites

**Objetivo.** Fábrica `get_tracker_provider(project?)` que selecciona adapter por `issue_tracker.type` del proyecto (el seam YA existente, `project_context.py:73`), y reescritura del **seam de construcción de cliente real** (`ado_publisher._client_for_ticket_project()`/`_default_client()`), NO de un patrón `AdoClient(` inexistente en `tickets.py`. **Valor:** todo el sistema usa el puerto; ADO sigue default byte-idéntico.

**Archivos a EDITAR:**
- `backend/services/tracker_provider.py` (agregar fábrica).
- `backend/config.py` (`STACKY_GITLAB_ENABLED` ya en F2; aquí nada nuevo — NO se crea `STACKY_TRACKER_PROVIDER`).
- `backend/services/ado_publisher.py` — los DOS helpers de construcción: `_default_client()` (`:573`) y `_client_for_ticket_project()` (`:579`) devuelven `get_tracker_provider(project)`. Verificar por grep que las llamadas a `client.<metodo_ado>` ya correspondan a métodos del puerto; renombrar las pocas que difieran (lista exacta por grep, abajo).
- El **consumidor de la outbox** (identificar por `grep -rn 'claim_due\|ado_write_outbox' backend` — NO `_apply`, que solo persiste): que construya el cliente vía la fábrica.
- `backend/services/ado_context.py`, `backend/services/ado_sync.py`, `backend/services/ado_feedback.py`, `backend/api/ado_manager.py`: reemplazar la construcción de cliente por la fábrica donde hoy usan `build_ado_client`/`AdoClient`.
- **CREAR:** `backend/tests/test_tracker_factory.py`.

> Para Jira/Mantis: la fábrica NO los cubre (ver §2.bis). Si `issue_tracker.type in {jira,mantis}` en un call-site de escritura rica, la fábrica lanza `TrackerConfigError` (mismo rechazo que hoy hace `build_ado_client` para no-ADO — sin regresión). Los paths sync de Jira/Mantis siguen intactos por su propio camino.

**Grep para enumerar call-sites a tocar (NO leer archivos enteros):**
```
grep -nE '_default_client|_client_for_ticket_project|build_ado_client|AdoClient\(' backend/services/ado_publisher.py backend/services/ado_context.py backend/services/ado_sync.py backend/services/ado_feedback.py backend/api/ado_manager.py backend/api/tickets.py
```

**Fábrica (`tracker_provider.py`):**
```python
def get_tracker_provider(project: str | None = None) -> "TrackerProvider":
    from services.project_context import resolve_project_context
    import config
    ctx = resolve_project_context(project_name=project)     # ya resuelve issue_tracker.type
    ttype = (ctx.tracker_type or "azure_devops").strip().lower()
    if ttype == "gitlab":
        if not getattr(config, "STACKY_GITLAB_ENABLED", False):
            from .tracker_provider import TrackerConfigError
            raise TrackerConfigError("issue_tracker.type=gitlab pero STACKY_GITLAB_ENABLED=false")
        from .gitlab_provider import GitLabTrackerProvider
        return GitLabTrackerProvider(project=project)
    if ttype == "azure_devops":
        from .ado_provider import AdoTrackerProvider
        return AdoTrackerProvider(project=project)
    # jira/mantis: sin puerto formal todavía (§2.bis); mismo rechazo que build_ado_client.
    from .tracker_provider import TrackerConfigError
    raise TrackerConfigError(f"tracker '{ttype}' sin puerto formal (usa su path de sync existente)")
```
> Sin import dinámico por-request costoso: la fábrica es barata (resuelve un dict del profile cacheado por `resolve_project_context`). No agrega latencia material vs `build_ado_client` actual.

**Tests primero (`test_tracker_factory.py`):**
- `test_factory_defaults_to_ado`: profile sin `issue_tracker.type` → `AdoTrackerProvider` (default `azure_devops`).
- `test_factory_returns_gitlab_when_type_and_enabled`: `type=gitlab` + `STACKY_GITLAB_ENABLED=true` (monkeypatch ctx+config) → `GitLabTrackerProvider`.
- `test_factory_raises_when_gitlab_disabled`: `type=gitlab` + ENABLED=false → `TrackerConfigError` (NO degrada silencioso a ADO; ruidoso para no publicar en el tracker equivocado).
- `test_factory_raises_for_jira_mantis`: `type in {jira,mantis}` → `TrackerConfigError`.
**Regresión obligatoria:** correr `test_ado_provider.py`, `test_tickets*.py`, `test_ado_publisher*`, `test_ado_sync*` y conformance de runtime → 0 cambios.

**[ADICIÓN ARQUITECTO #2] Guard anti-recableo (CREAR `backend/tests/test_no_adoclient_outside_ado_provider.py`):**
```python
# Falla si 'AdoClient(' aparece fuera de la allowlist; sella la regresión "alguien vuelve a cablear ADO directo".
ALLOWED = {"services/ado_provider.py", "services/ado_client.py", "services/project_context.py"}
def test_no_adoclient_construction_outside_allowlist():
    hits = grep_repo(r"AdoClient\(", root="backend")     # helper simple con pathlib/re
    offenders = [h for h in hits if normalize(h.path) not in ALLOWED]
    assert offenders == [], f"AdoClient() construido fuera de la allowlist: {offenders}"
```
Se registra en `HARNESS_TEST_FILES` (F13).

**Comando:** `... -m pytest "backend/tests/test_tracker_factory.py" "backend/tests/test_no_adoclient_outside_ado_provider.py" -q` + suite ADO afectada.
**Criterio binario:** factory + guard pasan Y suite ADO sigue verde sin cambios.
**Flag:** `issue_tracker.type` (default `azure_devops`), `STACKY_GITLAB_ENABLED` (default false).
**Impacto runtime:** los 3 runtimes (Codex/Claude CLI/Copilot) publican/leen vía la fábrica; con `type=azure_devops` el comportamiento es idéntico. **Fallback por runtime:** ninguno aplica (backend común; ninguna rama por runtime). **Trabajo del operador:** ninguno (default ADO).

---

### F11 — UI: selector de provider + campos GitLab (config por UI, regla dura)

**Objetivo.** Exponer en la UI la selección de provider y los campos GitLab (URL, project, referencia al archivo de token), reusando `ClientProfileEditor`/global-config; el secreto se referencia por archivo, nunca se tipea en el profile plano. **Valor:** cumple GP-4 (toda config del operador por UI).

**Archivos a EDITAR:** `backend/api/global_config.py` (agregar rama `gitlab` a `test_global_tracker_connection` — ya tiene `azure_devops|jira|mantis`, `global_config.py:208,229,249`; y persistir `gitlab_url`/`gitlab_project`/`gitlab_group`/`gitlab_auth_file` vía `_write_env`), `backend/api/client_profile.py` (subsección `issue_tracker` con `type=gitlab` no-secreto + `tracker_state_machine.gitlab`), `frontend/src/components/ClientProfileEditor.tsx` (agregar `gitlab` al selector de tracker que YA existe + campos condicionales GitLab), `frontend/src/pages/DiagnosticsPage.tsx` (botón test de conexión, reusa el existente). **CREAR:** `backend/tests/test_global_config_gitlab.py`.

**Pseudocódigo backend (extiende lo que YA existe, no reinventa):**
```python
# test_global_tracker_connection: AGREGAR rama gitlab al if/elif por tracker_type existente.
elif t_type == "gitlab":
    from services.gitlab_client import GitLabClient, GitLabConfigError
    base = _merge("gitlab_url", "GITLAB_URL").rstrip("/")
    proj = _merge("gitlab_project", "GITLAB_PROJECT")
    if not base or not proj:
        return {"ok": False, "error": "Falta GITLAB_URL o GITLAB_PROJECT"}
    c = GitLabClient(base_url=base, project=proj)   # token resuelto por archivo/env (NO del payload)
    user, _ = c._request("GET", "/user")            # lectura: valida credenciales
    return {"ok": bool(user.get("id")), "user": user.get("username")}
# put_global_config: agrega gitlab_url/gitlab_project/gitlab_group/gitlab_auth_file a _write_env.
#   El TOKEN NO viaja por este endpoint: se sube por archivo auth/gitlab_auth.json (mismo flujo que PAT ADO/Jira/Mantis).
```
**UI (`ClientProfileEditor.tsx`):** el selector de tracker YA existe (ado/jira/mantis); **agregar opción `gitlab`** (default sigue "azure_devops"); si `gitlab`, mostrar inputs `gitlab_url`, `gitlab_project`, `gitlab_group` (opcional) y un campo de **ruta** de archivo de token (no el token). Exponer las 3 flags `STACKY_GITLAB_*` en el panel de harness flags (default off). Botón "Probar conexión" → `test_global_tracker_connection`.

**Tests:**
- `test_put_config_persists_gitlab_fields_without_token`: el token NUNCA se escribe por este endpoint (solo `gitlab_url`/`project`/`group`/`auth_file`).
- `test_connection_check_uses_gitlab_branch`: con `tracker_type=gitlab` enruta a la rama GitLab y NO toca ADO.
- Frontend gate: `cd frontend; npx tsc --noEmit` → 0 errores.

**Comando:** `... -m pytest "backend/tests/test_global_config_gitlab.py" -q` + `tsc --noEmit`.
**Criterio binario:** tests pasan; tsc 0 errores; el token JAMÁS viaja por el endpoint de config.
**Flag:** `issue_tracker.type`, `STACKY_GITLAB_ENABLED`, `STACKY_GITLAB_EPICS_NATIVE`, `STACKY_GITLAB_CI_INFERENCE` (expuestas en panel de flags). **Impacto runtime:** ninguno. **Trabajo del operador:** opt-in (solo si elige GitLab).

---

### F11.bis — [ADICIÓN ARQUITECTO #3] Modo shadow / dry-run de conexión GitLab (validar sin escribir)

**Objetivo.** Extender el botón "Probar conexión" a un **chequeo de permisos no destructivo**: además de credenciales (`GET /user`), valida (a) acceso de LECTURA al proyecto y paginación (`GET /projects/{id}/issues?per_page=1`), y (b) **permiso de ESCRITURA sin crear nada**, leyendo los scopes del token / el rol del usuario en el proyecto (`GET /projects/{id}/members/all/{user_id}` → `access_level >= 30` Developer). **Valor:** el operador sabe ANTES de publicar si el token tiene scope `api` y rol suficiente, evitando una épica a medio publicar por 403. Reusa el patrón `test_global_tracker_connection`; CERO escritura; opt-in (solo si elige GitLab).

**Archivos a EDITAR:** `backend/api/global_config.py` (ampliar la rama gitlab del test con los 2 chequeos extra), `backend/tests/test_global_config_gitlab.py` (casos).

**Pseudocódigo (dentro de la rama `gitlab` del test de conexión):**
```python
checks = {"auth": False, "read": False, "write_permission": False}
user, _ = c._request("GET", "/user"); checks["auth"] = bool(user.get("id"))
items, _ = c._request("GET", f"/projects/{c._project_path()}/issues", params={"per_page": 1}); checks["read"] = True
member, _ = c._request("GET", f"/projects/{c._project_path()}/members/all/{user['id']}")
checks["write_permission"] = (member.get("access_level", 0) >= 30)   # Developer+
return {"ok": all(checks.values()), "checks": checks}
```
**Casos borde:** 404 en members → token sin visibilidad de miembros → reportar `write_permission: unknown` (no romper); 401/403 → `auth:false` con mensaje claro.

**Tests:**
- `test_shadow_check_reports_all_three` (mock 200s → ok true).
- `test_shadow_check_flags_insufficient_role` (access_level 20 Reporter → write_permission false, ok false).
- `test_shadow_check_never_writes` (assert: NINGÚN `POST`/`PUT`/`DELETE` emitido por el transporte double).

**Comando:** `... -m pytest "backend/tests/test_global_config_gitlab.py" -q`.
**Criterio binario:** los 3 casos pasan; el test verifica explícitamente cero escrituras.
**Flag:** `STACKY_GITLAB_ENABLED`. **Impacto runtime:** ninguno (es chequeo de UI). **Trabajo del operador:** opt-in (botón, no obligatorio).

---

### F12 — Conformance cross-provider (la garantía "no falta ninguna función")

**Objetivo.** Un único test que recorre `PORT_METHODS` y verifica que AMBOS adapters implementan todo, más una suite de **comportamiento equivalente** corrida contra ambos con HTTP doubles. **Valor:** convierte "no falta ninguna función" en verificable, no en promesa.

**Archivos a EDITAR:** `backend/tests/test_tracker_provider_conformance.py` (ampliar). **CREAR:** `backend/tests/conformance/fixtures_tracker.py` (doubles ADO/GitLab).

**Casos:**
- `test_both_adapters_implement_all_port_methods`: `for adapter in (AdoTrackerProvider, GitLabTrackerProvider): for m in PORT_METHODS: assert callable(getattr(adapter_instance, m))`. **Si GitLab no implementa una fila de la matriz, falla aquí.** (Existencia — necesario pero NO suficiente, ver siguiente.)
- **[ADICIÓN ARQUITECTO #1] `test_no_port_method_is_a_stub[adapter]`** (anti-falso-verde, C6): instancia cada provider con un **transporte double** que captura requests y devuelve fixtures por endpoint; invoca CADA `PORT_METHOD` con args válidos mínimos y verifica que:
  1. NINGÚN método lanza `NotImplementedError` (y no es un cuerpo vacío `pass`/`return None` cuando el contrato exige dict);
  2. los métodos de LECTURA devuelven el shape canónico (claves mínimas `{id,iid,title,state,...}`);
  3. los métodos de ESCRITURA emiten el request HTTP esperado (método+path+payload clave) al double.
  ```python
  @pytest.mark.parametrize("provider", [ado_with_double(), gitlab_with_double()])
  def test_no_port_method_is_a_stub(provider, double):
      for m in PORT_METHODS:
          try:
              result = invoke_with_min_args(provider, m)   # tabla de args mínimos por método
          except NotImplementedError:
              pytest.fail(f"{provider.name}.{m} es un stub NotImplementedError")
          assert_contract(m, result, double.requests)       # shape (lectura) o request emitido (escritura)
  ```
  Esto convierte KPI-1 de "las firmas existen" a "los métodos HACEN lo que dicen". Un adapter con métodos vacíos FALLA aquí.
- `test_create_then_find_child_by_marker_idempotent[adapter]` (parametrizado ado/gitlab con doubles): crear hijo con marcador → `find_child_by_marker` lo encuentra; segunda publicación no duplica.
- `test_post_comment_idempotent[adapter]`: `comment_exists` true tras post; re-post no duplica.
- `test_fetch_open_items_returns_normalized_shape[adapter]`: ambas devuelven dicts con claves canónicas mínimas.

**Comando:** `... -m pytest "backend/tests/test_tracker_provider_conformance.py" -q`
**Criterio binario:** parametrizado verde para ado Y gitlab, incluido el anti-stub. **(KPI-1.)**
**Flag:** ninguno (test). **Impacto runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F13 — Ratchet de registro + telemetría + docs

**Objetivo.** Registrar los nuevos archivos de test en `HARNESS_TEST_FILES` (sh+ps1) para que el meta-test del arnés (plan 49 F4) no falle, agregar telemetría `tracker_provider` a `epic_summary`/run footer, y documentar GitLab en la matriz viva. **Valor:** evita falso-verde del arnés y deja observabilidad.

**Archivos a EDITAR:** los scripts que listan `HARNESS_TEST_FILES` (buscar con `grep -rln HARNESS_TEST_FILES backend` — recordar: hay versión .sh y .ps1, ambas; memoria `ratchet-obliga-registrar-tests`), `backend/services/ado_publisher.py:_render_run_footer` (incluir `tracker_provider`), telemetría `epic_summary`. **Registrar TODOS los tests nuevos** en `HARNESS_TEST_FILES`: `test_tracker_provider_conformance.py`, `test_ado_provider.py`, `test_gitlab_client.py`, `test_gitlab_provider.py`, `test_tracker_factory.py`, `test_no_adoclient_outside_ado_provider.py` (ADICIÓN #2), `test_global_config_gitlab.py`. **CREAR:** entrada en docs/sistema si aplica (no obligatorio para el gate).

**Tests:** correr el meta-test del ratchet (plan 49) → verde con los nuevos archivos registrados.
**Comando:** el del ratchet (ver plan 49 status).
**Criterio binario:** ratchet verde; footer/telemetría incluyen `tracker_provider`.
**Flag:** ninguno. **Impacto runtime:** los 3 runtimes registran `tracker_provider` en telemetría (mismo valor para los 3; sin ramas por runtime). **Trabajo del operador:** ninguno.

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| **Epics solo Premium** (a nivel grupo) | `STACKY_GITLAB_EPICS_NATIVE=false` por default → fallback issues+labels+`/links` (F7). 403 en modo nativo **degrada** a fallback con log, no rompe. |
| **Rate limits GitLab** (429) | `_request` respeta `Retry-After` (F2); retries acotados; outbox absorbe escrituras (F10/F27). |
| **Paginación distinta** (Link/X-Next-Page, NO continuationToken) | `_request_paginated` por headers (F2); cap de páginas reusa flag existente (plan 52). |
| **self-managed vs gitlab.com** | `GITLAB_URL` configurable; sin hardcode de host (F2). Test de conexión por UI (F11). |
| **GraphQL vs REST** | Plan usa REST v4 (suficiente para toda la matriz). GraphQL queda **fuera de scope** (solo se documenta que Epics nativos tienen mejor soporte GraphQL; el fallback REST cubre la paridad). |
| **id global vs iid de issues** | `_normalize_issue` guarda ambos; URLs/links usan `iid`, epics usan id global (F3/F7). Documentado. |
| **Comentarios Markdown vs HTML** | Marcador idempotente sobrevive como HTML-comment embebido en MD (F4); test lo verifica. |
| **Regresión del camino ADO** | F1 es wrapper byte-idéntico; F10 mantiene default `azure_devops` (fábrica anclada en `issue_tracker.type`, no env nueva); guard ADICIÓN #2 sella el recableo; KPI-2 exige suite ADO verde sin cambios. |
| **Jira/Mantis se rompen al meter el puerto** | NO se tocan (§2.bis); la fábrica lanza `TrackerConfigError` para ellos en escritura rica = mismo rechazo que hoy hace `build_ado_client`. Sin regresión; migrarlos al puerto es plan futuro. |
| **Conformance falso-verde (métodos stub)** | `test_no_port_method_is_a_stub` (ADICIÓN #1) prueba comportamiento con doubles, no solo existencia; un método vacío/`NotImplementedError` falla el gate. |
| **Drift matriz↔puerto** | `PORT_METHODS` + conformance (F0/F12): si la matriz crece y el puerto no, el test falla. |

## 7. Fuera de scope

- GitLab **GraphQL** API (solo REST v4).
- Merge Requests / code review / branches (Stacky es tracker de work items; MRs no tienen equivalente ADO en el flujo actual).
- Migración de datos ADO→GitLab (no se mueven tickets; cada proyecto elige UN provider).
- Multi-provider simultáneo en un mismo proyecto activo (un proyecto = un tracker; el selector es `issue_tracker.type` por proyecto).
- **Migración de Jira/Mantis al puerto `TrackerProvider`** (evolución futura). Hoy Jira/Mantis siguen por su path de sync existente sin tocarse (§2.bis). El puerto queda diseñado para que un plan posterior cree `JiraTrackerProvider`/`MantisTrackerProvider` sin reescribir la fábrica.
- RBAC / multiusuario (mono-operador, GP-7).
- Webhooks/eventos push de GitLab (Stacky es pull/poll, como hoy con ADO).

## 8. Glosario, Orden de implementación y DoD

### Glosario
- **Puerto/Adapter:** patrón hexagonal. `TrackerProvider` (puerto) define el contrato; `AdoTrackerProvider`/`GitLabTrackerProvider` (adapters) lo implementan contra un sistema concreto.
- **WIQL:** Work Item Query Language (ADO). GitLab no lo tiene → se abstrae con `TrackerQuery`.
- **Work item (ADO) / Issue (GitLab):** unidad de trabajo. Mapeo 1:1 vía el puerto.
- **GitLab Epic vs Issue:** Epic es entidad de GRUPO (solo Premium); Issue es de proyecto. Sin Premium, la jerarquía se modela con issues + labels + links.
- **Marcador idempotente:** comentario/substring HTML-comment que Stacky inserta para detectar publicaciones previas y no duplicar.
- **Outbox:** cola transaccional local (`ado_write_outbox`) que serializa escrituras y reintenta; agnóstica al provider.
- **resource_*_events:** streams de GitLab (`resource_label_events`, `resource_state_events`) que reemplazan el `updates` unificado de ADO.
- **iid vs id:** `iid` = id por-proyecto (visible en URLs); `id` = id global (para epics/links).
- **Estado lógico:** functional/technical/developer (en `tracker_state_machine`); se mapea a estado/label del tracker concreto.

### Orden de implementación
1. F0 (puerto + conformance esqueleto)
2. F1 (AdoTrackerProvider wrapper) + correr suite ADO → confirmar 0 regresión
3. F2 (gitlab_client núcleo)
4. F3 (issues CRUD/estados/query)
5. F4 (comments idempotentes)
6. F5 (attachments)
7. F6 (identity/assignees)
8. F7 (jerarquía épica + fallback)
9. F8 (updates/edit-learning)
10. F9 (pipeline/CI)
11. F10 (fábrica anclada en `issue_tracker.type` + wiring del seam real `ado_publisher` + guard ADICIÓN #2) + regresión ADO completa
12. F11 (UI selector + global-config) + F11.bis (shadow/dry-run, ADICIÓN #3)
13. F12 (conformance cross-provider + anti-stub ADICIÓN #1) → KPI-1
14. F13 (ratchet: registrar TODOS los tests nuevos + telemetría `tracker_provider`)

### Definición de Hecho (DoD) global
- [ ] `TrackerProvider` define las 18 firmas de `PORT_METHODS`; matriz §4 sin "etc." y reflejada por `PORT_METHODS`.
- [ ] `AdoTrackerProvider` y `GitLabTrackerProvider` pasan `test_tracker_provider_conformance.py` (ambos), incluido `test_no_port_method_is_a_stub` (ADICIÓN #1, sin falsos verdes) — KPI-1.
- [ ] Suite ADO (`test_ado_*`, `test_tickets*`, conformance runtime) verde sin cambios con default `azure_devops` — KPI-2, 0 regresiones.
- [ ] Flujo brief→épica produce artefacto lógico equivalente en GitLab con doubles — KPI-3.
- [ ] `tsc --noEmit` 0 errores con la opción `gitlab` agregada al selector de tracker — KPI-4.
- [ ] Cada flag nuevo (`STACKY_GITLAB_ENABLED`, `STACKY_GITLAB_EPICS_NATIVE`, `STACKY_GITLAB_CI_INFERENCE`) con default seguro y expuesto en el panel de flags por UI (GP-4); selección de tracker por `issue_tracker.type` en ClientProfileEditor. NO existe `STACKY_TRACKER_PROVIDER` (se descartó por duplicar `issue_tracker.type`, C1).
- [ ] Token GitLab JAMÁS en `issue_tracker` del profile ni en el endpoint de config (GP-3) — verificado por test.
- [ ] Default `azure_devops`, GitLab opt-in, cero pasos manuales nuevos para usuarios ADO/Jira/Mantis (GP-2).
- [ ] Ningún archivo referencia `AdoClient(` directo salvo allowlist (`ado_provider.py`/`ado_client.py`/`project_context.py`) — verificado por `test_no_adoclient_outside_ado_provider` (ADICIÓN #2) en el ratchet.
- [ ] Jira/Mantis NO tocados ni degradados; la fábrica lanza `TrackerConfigError` para ellos en escritura rica (mismo comportamiento que hoy) — §2.bis.
- [ ] Nuevos archivos de test registrados en `HARNESS_TEST_FILES` (.sh y .ps1; ratchet plan 49 verde).
- [ ] Los 3 runtimes (Codex/Claude CLI/Copilot) operan vía la misma fábrica, mismos artefactos, sin ramas por runtime (GP-5).
- [ ] Botón "Probar conexión + permisos" GitLab valida auth/lectura/permiso-de-escritura SIN escribir nada (ADICIÓN #3, F11.bis) — verificado por `test_shadow_check_never_writes`.
