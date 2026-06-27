# Plan 70 — Desacople de los CONSUMIDORES del puerto TrackerProvider

> **Estado:** PROPUESTO (no implementado).
> **Pre-requisito:** Plan 65 (puerto TrackerProvider) — COMPLETO.
> **Roadmap:** Primer eslabón del bloque GitLab-Main 70-76 (desacople → pipeline infer agnóstico → trigger CI → creador pipelines → migrador ADO→GitLab → deep links → eval codebase-memory-mcp).
> **Versión doc:** v1.

---

## 1. Objetivo y KPI

Migrar los **18 call sites** de `api/tickets.py` que hoy consumen `AdoClient` (vía el helper `_ado_client_for_ticket(...) -> AdoClient`) para que consuman el **puerto formal `TrackerProvider`** (Plan 65) a través de un nuevo helper `_provider_for_ticket(...)`. Esto cierra el último agujero que mantiene a `tickets.py` casado con Azure DevOps aunque el proyecto tenga `issue_tracker.type=gitlab`.

**KPI global (DoD):** un proyecto con `issue_tracker.type=gitlab` (y `STACKY_GITLAB_ENABLED=true`) ejecuta los flujos de `api/tickets.py` end-to-end (sincronización, comentarios, attachments, creación de épicas/issues/tareas, asignación, estado, idempotencia, observabilidad) **sin construir ni tocar `AdoClient` en ningún punto del path**.

---

## 2. Por qué ahora / gap que cierra

El Plan 65 construyó el puerto pero **no migró a los consumidores**. Verificado en código:

- `services/tracker_provider.py:56` define `TrackerProvider(Protocol)` con 18 métodos (`PORT_METHODS`, tracker_provider.py:79-98) y la fábrica `get_tracker_provider(project)` (tracker_provider.py:105).
- `api/tickets.py:340` define `_ado_client_for_ticket(...) -> AdoClient` como thin wrapper de `build_ado_client()` (services/project_context.py:221, seam legítima que **se mantiene**).
- Hay **18 call sites** en `tickets.py` (líneas 508, 566, 787, 820, 1146, 1730, 1951, 3776, 3853, 3873, 4012, 5049, 5189, 5303, 5903, 6242, 6326, 6474) que invocan métodos ADO-específicos sobre el `AdoClient` retornado.
- El centinela `tests/test_no_adoclient_outside_ado_provider.py` **SOLO** busca construcción literal `AdoClient(` (línea 56). **No captura `tickets.py`** porque ahí no hay construcción literal: el acoplamiento es por el helper tipado y por los métodos ADO consumidos. Resultado: hoy GitLab puede construirse como provider pero `tickets.py` (el corazón del flujo tracker en producción) sigue siendo ADO-only.

Sin este plan, el roadmap GitLab-Main 70-76 está bloqueado: el Plan 71 (pipeline infer agnóstico) y el Plan 74 (migrador ADO→GitLab) requieren que los consumers ya hablen por el puerto.

---

## 3. Principios y guardarraíles

- **3 runtimes con paridad** (Codex, Claude Code, GitHub Copilot Pro): este plan NO toca el runtime del agente ni los prompts; el cambio vive en la capa de servicios/API. Los 3 runtimes siguen operativos sin cambios.
- **Cero trabajo extra al operador**: la migración está protegida por un flag opt-in `STACKY_TICKETS_PROVIDER_ENABLED` default **OFF**, editable por UI (HarnessFlagsPanel). Con flag OFF el comportamiento es byte-idéntico al actual.
- **Human-in-the-loop innegociable**: el flag lo prende el operador; nada autónomo. La creación de work items sigue requiriendo los gates y aprobaciones existentes.
- **Mono-operador sin auth**: las credenciales siguen viniendo del `client_profile` (PAT ADO / token GitLab); sin RBAC, sin login.
- **No degradar / backward-compatible**: se reutilizan `get_tracker_provider` y `build_ado_client` existentes; `_ado_client_for_ticket` se conserva como fallback con flag OFF.
- **TDD + funciones puras + ratchet + no falsos verdes**: cada fase migra test-first; el centinela se refuerza (no se debilita); el ratchet meta del Plan 49 sigue verde.
- **Migración incremental, NUNCA big-bang**: los 18 call sites se migran por **grupos cohesivos** (una fase por grupo), cada grupo con tests propios.
- **Prohibido lo vago**: todo call site, archivo y símbolo citado con `archivo:línea`.

---

## 4. Fases

### F0 — Inventario (entregable: tabla call-site → método ADO → método puerto → OK/GAP)

**Trabajo:** abrir `api/tickets.py` en cada uno de los 18 call sites, anotar el método ADO exacto y sus argumentos, y verificar contra `PORT_METHODS` (tracker_provider.py:79-98).

**Tabla F0 (verificada contra código el 2026-06-27):**

| # | Línea | Método ADO invocado (args) | Método puerto equivalente | Estado |
|---|------|----------------------------|---------------------------|--------|
| 1 | 508 | `sync_tickets(client=AdoClient)` | — (ver F1-GAP-A) | **GAP-A** |
| 2 | 566 | `client.fetch_comments(ado_id, top=30)` | `provider.fetch_comments(item_id)` | OK (kwarg `top` se pierde; ver F1-GAP-C) |
| 3 | 787 | `client.fetch_comments(ado_id)` | `provider.fetch_comments(item_id)` | OK |
| 4 | 820 | `client.fetch_attachments(ado_id)` | `provider.fetch_attachments(item_id)` | OK |
| 5 | 1146 | `client.update_work_item_state(int(ado_id), state)` | `provider.update_item_state(item_id, logical_state)` | OK |
| 6 | 1730 | `client.update_work_item_state(int(ado_id), state)` | `provider.update_item_state(item_id, logical_state)` | OK |
| 7 | 1951 | `client.work_item_url(int(task_ado_id))` | `provider.item_url(item_id)` | OK |
| 8 | 3776 | helper `_consumed_task_ado_status(ado=...)` → internamente `ado.get_work_item(...)` (vía `getattr`) | `provider.get_item(item_id)` | **GAP-B** (`get_work_item` ≠ `get_item`) |
| 9 | 3853 | helper `_consumed_task_ado_status(ado=...)` → `ado.get_work_item(...)` (vía `getattr`) | `provider.get_item(item_id)` | **GAP-B** |
| 10 | 3873 | `idempotency_ado.work_item_url(int(prev_task_id))` | `provider.item_url(item_id)` | OK |
| 11 | 4012 | `ado` se usa en cadena: `_parent_exists_preflight(ado=...)` (`get_work_item` vía `getattr`), `ado.create_work_item(work_item_type=, fields=, parent_ado_id=)`, `ado.work_item_url(...)`, `ado.update_work_item_state(...)`, `ado.upload_attachment(file_path=, file_name=)`, `ado.link_attachment_to_work_item(work_item_id=, attachment_url=, comment=)`, `ado.post_comment(task_ado_id, comment_text, fmt="html")` | mixto | **GAP-B** (`get_work_item`), **GAP-D** (`link_attachment_to_work_item` ≠ `link_attachment`), **GAP-E** (`create_work_item` con `fields=`/`parent_ado_id=` ≠ `create_item(TrackerItem)`), **GAP-F** (`post_comment(..., fmt="html")` kwarg extra) |
| 12 | 5049 | `client.update_work_item_assigned_to(ado_id, unique_name)` | `provider.update_item_assignee(item_id, assignee)` | OK |
| 13 | 5189 | `client.get_authenticated_user()` | `provider.get_authenticated_user()` | OK |
| 14 | 5303 | `sync_tickets(client=AdoClient)` | — (ver F1-GAP-A) | **GAP-A** |
| 15 | 5903 | `client.create_work_item(work_item_type="Epic", title=, description=)` + `client.work_item_url(ado_id)` | `provider.create_item(TrackerItem)` + `provider.item_url(item_id)` | **GAP-E** (firma) |
| 16 | 6242 | `_rev_client.get_work_item(ado_id, fields=["System.Rev"])` | `provider.get_item(item_id)` | **GAP-B** (kwarg `fields`) |
| 17 | 6326 | `client.create_work_item(work_item_type="Issue", title=, description=)` + `client.work_item_url(ado_id)` | `provider.create_item(TrackerItem)` + `provider.item_url(item_id)` | **GAP-E** (firma) |
| 18 | 6474 | `_post_phase_comment(client, ...)` → `client.comment_exists(ado_id, marker)` + `client.post_comment(ado_id, marked_html, fmt="html")` | `provider.comment_exists` + `provider.post_comment(item_id, body_html)` | **GAP-F** (`fmt="html"` kwarg) |

**GAPs detectados (alimentan F1):**

- **GAP-A** (`sync_tickets`): `services/ticket_service.py:116` (legacy) define `sync_tickets(client=AdoClient)` tipado al cliente ADO concreto. **Decision:** `sync_tickets` es ADO-only por construcción (su lógica interna usa campos ADO). Se introduce `provider_sync_items(provider)` paralelo en F1; los call sites 508/5303 caen a un branch `if provider.name == "azure_devops": sync_tickets(...)` con fallback explícito documentado (GitLab usa `provider.fetch_open_items` directo). **Riesgo #3** (ver sección 5).
- **GAP-B** (`get_work_item` vs `get_item`): el puerto tiene `get_item(item_id) -> dict`. Los helpers `_parent_exists_preflight` (tickets.py:3380) y `_consumed_task_ado_status` (tickets.py:3516) usan `getattr(ado, "get_work_item", None)` y la firma `get_work_item(id, [fields])`. **Decision:** en F1 se **aliasa** `get_item` en `AdoTrackerProvider`/`GitLabTrackerProvider` y se expone un método **`get_item_fields(item_id, fields)`** opcional en el puerto; los helpers se reescriben para llamar `provider.get_item(item_id)` y leer del dict retornado los campos solicitados (filtrado post-fetch determinista). El kwarg `fields` NO pasa al puerto (es optimización ADO); se filtra en el caller.
- **GAP-C** (`fetch_comments(top=30)`): el sitio 566 pide top=30. **Decision:** el puerto `fetch_comments(item_id)` retorna los "recientes"; se acepta que GitLab retorna sus N por defecto y ADO un top razonable hardcodeado en el adapter (`AdoTrackerProvider.fetch_comments` ya implementado en Plan 65). No se añade kwarg al puerto. Documentado.
- **GAP-D** (`link_attachment_to_work_item` vs `link_attachment`): el puerto tiene `link_attachment(item_id, attachment)`. **Decision:** el adapter `AdoTrackerProvider.link_attachment` (Plan 65) ya envuelve `link_attachment_to_work_item`; el caller 4335 se reescribe para llamar `provider.link_attachment(item_id, attach_result)` (el dict retornado por `upload_attachment`).
- **GAP-E** (`create_work_item` con `fields=`/`parent_ado_id=`/`title`/`description` vs `create_item(TrackerItem)`): **GAP principal de firma.** El puerto recibe `TrackerItem(item_type, title, description_html, labels, assignee, parent_id, fields)`. Los callers 3245/4148/5904/6326/6941/6958 construyen actualmente `fields={"System.Title":..., "System.Description":...}`. **Decision:** se introduce un **adapter local** `_tracker_item_from_kwargs(work_item_type, title=None, description=None, fields=None, parent_ado_id=None)` en `tickets.py` (función PURA) que normalice las dos firmas usadas (kwargs-style y fields-style) al dataclass `TrackerItem`. El caller migra a `provider.create_item(_tracker_item_from_kwargs(...))`. El `parent_id` se mapea desde `parent_ado_id`. Los campos no estándar viajan en `TrackerItem.fields`.
- **GAP-F** (`post_comment(..., fmt="html")`): el puerto `post_comment(item_id, body_html)` no tiene `fmt`. **Decision:** los adapters asumen HTML (GitLab y ADO postean HTML/markdown nativamente). El caller 4415/6364 deja de pasar `fmt="html"`. Documentado.

**Criterio binario F0:** la tabla de arriba está completa y cada fila cita `tickets.py:línea` con el método ADO exacto. **Cumplido en este doc.**

**Trabajo del operador F0:** ninguno.

---

### F1 — Ampliación del puerto (solo si hay GAPs)

Como F0 detectó GAPs B, E y F (que requieren-normalización en callers y adapters, NO nuevos métodos al puerto) y GAP-A (que se resuelve con branch explícito), **F1 = verificación + adapter local, SIN cambios al `Protocol`**. Concretamente:

- **No se agregan métodos a `TrackerProvider.PORT_METHODS`** (los 18 existentes cubren todos los casos).
- **Sí se modifica** `services/ado_provider.py` (si `AdoTrackerProvider.link_attachment` o `create_item` no aceptan ya el dict/`TrackerItem` tal cual) para que la firma coincida con el puerto. Verificar contra Plan 65 (estos adapters ya existen; F1 solo confirma signatures).
- **Sí se agrega** un **adapter local puro** en `api/tickets.py`: `_tracker_item_from_kwargs(...)` (GAP-E). Esta función NO toca el puerto; vive en el caller.

**Archivos exactos F1:**
- `services/ado_provider.py` — verificar firmas de `create_item(TrackerItem)`, `link_attachment(item_id, attachment)`, `get_item(item_id)`; ajustar si divergen (diff mínimo).
- `services/gitlab_provider.py` — ídem (verificar que retorna los campos que GAP-B filtra en el caller: `System.Rev`, `System.WorkItemType`, `System.State` viajan en el dict crudo del provider, el caller los lee con `.get`).
- `api/tickets.py` — agregar `_tracker_item_from_kwargs(...)` (función PURA).

**Tests F1 (TDD primero):**
- Archivo: `backend/tests/test_plan70_tracker_item_adapter.py`.
- Casos:
  1. `create_item` con kwargs-style (`work_item_type="Task", title="x", description="y"`) → `TrackerItem(item_type="Task", title="x", description_html="y")`.
  2. `create_item` con fields-style (`work_item_type="Task", fields={"System.Title":"x","System.Description":"y"}, parent_ado_id=42`) → `TrackerItem(item_type="Task", title="x", description_html="y", parent_id="42")`.
  3. Campos no estándar en `fields` se conservan en `TrackerItem.fields`.
  4. `description_html` vacía cuando falte (no None).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan70_tracker_item_adapter.py -q`.

**Criterio binario F1:** los 4 casos pasan; `_tracker_item_from_kwargs` es pura (sin I/O); no se agregó nada a `PORT_METHODS`.

**Impacto por runtime:** ninguno (capa de servicios).

**Flag F1:** ninguna (la función es pura, inerte hasta F2).

**Trabajo del operador F1:** ninguno.

---

### F2 — Wrapper de compatibilidad `_provider_for_ticket()`

**Trabajo:** crear en `api/tickets.py` un helper espejo de `_ado_client_for_ticket` (tickets.py:340) que retorne el provider vía `get_tracker_provider(project)`:

```python
def _provider_for_ticket(ticket: "Ticket | None" = None, project_name: str | None = None):
    """Plan 70 — Devuelve el TrackerProvider para el proyecto/ticket.

    Espejo provider-agnóstico de _ado_client_for_ticket. Migración gateada por
    STACKY_TICKETS_PROVIDER_ENABLED (default OFF): flag OFF → retorna None y el
    caller cae a _ado_client_for_ticket (backward-compat)."""
    if not config.STACKY_TICKETS_PROVIDER_ENABLED:
        return None
    proj = project_name or (ticket.stacky_project_name if ticket is not None else None)
    try:
        return get_tracker_provider(proj)
    except TrackerConfigError:
        return None  # caller cae a fallback ADO
```

`_ado_client_for_ticket` se **conserva intacto** como fallback (flag OFF o provider no disponible).

**Archivos exactos F2:** `api/tickets.py` (nueva función `_provider_for_ticket`), `config.py` (nuevo atributo `STACKY_TICKETS_PROVIDER_ENABLED: bool = False`), `harness_defaults.env` (línea `STACKY_TICKETS_PROVIDER_ENABLED=false`).

**Tests F2 (TDD primero):**
- Archivo: `backend/tests/test_plan70_provider_for_ticket.py`.
- Casos:
  1. Flag OFF → `_provider_for_ticket(...)` retorna `None`.
  2. Flag ON + proyecto ADO → retorna instancia con `.name == "azure_devops"`.
  3. Flag ON + proyecto gitlab sin `STACKY_GITLAB_ENABLED` → retorna `None` (fallback ADO).
  4. Flag ON + proyecto gitlab habilitado → retorna instancia con `.name == "gitlab"`.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan70_provider_for_ticket.py -q`.

**Criterio binario F2:** los 4 casos pasan; con flag OFF `_provider_for_ticket` siempre es `None` (byte-idéntico).

**Impacto por runtime:** ninguno.

**Flag F2:** `STACKY_TICKETS_PROVIDER_ENABLED` default **OFF**, `env_only=False` (editable por UI en HarnessFlagsPanel, categoría "Tickets / Tracker Provider").

**Trabajo del operador F2:** ninguno (default OFF; el operador puede opt-in por UI cuando quiera probar GitLab).

---

### F3 — Migración GRUPO "comentarios" (call sites 566, 787 + helper `_post_phase_comment` en 6360/6364)

**Patrón de migración (aplica a todos los grupos):**

```python
provider = _provider_for_ticket(ticket=t, project_name=project_name)
if provider is not None:
    ado_comments = provider.fetch_comments(str(ado_id))   # puerto
else:
    client = _ado_client_for_ticket(ticket=t)             # fallback ADO
    ado_comments = client.fetch_comments(ado_id, top=30)  # legacy
```

**Call sites de este grupo:**
- **566** (`fetch_comments` con `top=30`): branch provider `provider.fetch_comments(str(ado_id))`; fallback preserva `top=30`.
- **787** (`fetch_comments`): branch provider directo; fallback idéntico.
- **6360/6364** (`_post_phase_comment`): `provider.comment_exists(ado_id, marker)` + `provider.post_comment(ado_id, marked_html)` (sin `fmt`); fallback deja `fmt="html"`. El cliente 6474 pasa el provider al helper.

**Archivos exactos F3:** `api/tickets.py` (líneas 566, 787, 6348-6369 `_post_phase_comment`, 6474).

**Tests F3 (TDD primero):**
- Archivo: `backend/tests/test_plan70_group_comments.py`.
- Casos:
  1. Flag ON + provider mock → `fetch_comments` llama al provider (no a ADO).
  2. Flag OFF → `fetch_comments` llama a `AdoClient.fetch_comments` (preserva `top=30` en 566).
  3. `_post_phase_comment` con provider → `post_comment` SIN `fmt`.
  4. `_post_phase_comment` con provider → idempotencia vía `comment_exists`.
  5. Provider lanza excepción → fallback ADO cuando aplique (solo si `_provider_for_ticket` ya era None).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan70_group_comments.py -q`.

**Criterio binario F3:** los 5 casos pasan; flag OFF → comportamiento idéntico al pre-plan.

**Impacto por runtime:** ninguno.

**Trabajo del operador F3:** ninguno.

---

### F4 — Migración GRUPO "estado" (call sites 1146, 1730, 4231)

**Call sites:**
- **1146** (`update_work_item_state(int(ado_id), state)`): branch `provider.update_item_state(str(ado_id), state)`; fallback idéntico.
- **1730** (`update_work_item_state(int(ado_id), state)`): ídem.
- **4231** (dentro del bloque create_child_task, `ado.update_work_item_state(task_ado_id, target_state)`): ídem.

**Archivos exactos F4:** `api/tickets.py` (1146, 1730, 4231).

**Tests F4:** `backend/tests/test_plan70_group_state.py`. Casos: (1) Flag ON → provider recibe `update_item_state(id, state)`; (2) Flag OFF → ADO; (3) excepción provider → no fallback silencioso (estado es write, se propaga al caller con logging). Comando: `.\.venv\Scripts\python.exe -m pytest tests/test_plan70_group_state.py -q`.

**Criterio binario F4:** 3 casos pasan; flag OFF idéntico.

**Trabajo del operador F4:** ninguno.

---

### F5 — Migración GRUPO "url" (call sites 1951, 3873, 4157, 5914, 6337)

**Call sites:**
- **1951** (`work_item_url(int(task_ado_id))`): `provider.item_url(str(...))`.
- **3873** (`work_item_url(int(prev_task_id))`): ídem.
- **4157** (`work_item_url(task_ado_id)` dentro create_child_task): ídem.
- **5914** (`client.work_item_url(ado_id)` fallback de `_links`): ídem.
- **6337** (`client.work_item_url(ado_id)` fallback de `_links`): ídem.

**Archivos exactos F5:** `api/tickets.py` (1951, 3810, 4157, 5914, 6337).

**Tests F5:** `backend/tests/test_plan70_group_url.py`. Casos: (1) Flag ON → `item_url`; (2) Flag OFF → `work_item_url`; (3) retorna string no vacío en ambos branches. Comando: `.\.venv\Scripts\python.exe -m pytest tests/test_plan70_group_url.py -q`.

**Trabajo del operador F5:** ninguno.

---

### F6 — Migración GRUPO "assignments + auth" (call sites 5049, 5189)

**Call sites:**
- **5049** (`update_work_item_assigned_to(ado_id, unique_name)`): `provider.update_item_assignee(str(ado_id), unique_name)`.
- **5189** (`get_authenticated_user()`): `provider.get_authenticated_user()`.

**Archivos exactos F6:** `api/tickets.py` (5049, 5189).

**Tests F6:** `backend/tests/test_plan70_group_assignee_auth.py`. Casos: (1) Flag ON assign → provider; (2) Flag OFF → ADO; (3) Flag ON auth → provider dict con mismo shape que ADO (`{"uniqueName":..., "displayName":...}`); el adapter GitLab debe normalizar al shape ADO (decisión de F1, verificar en `gitlab_provider.py`). Comando: `.\.venv\Scripts\python.exe -m pytest tests/test_plan70_group_assignee_auth.py -q`.

**Trabajo del operador F6:** ninguno.

---

### F7 — Migración GRUPO "attachments" (call sites 820 + bloque 4321-4339)

**Call sites:**
- **820** (`fetch_attachments(ado_id)`): `provider.fetch_attachments(str(ado_id))`.
- **4321** (`upload_attachment(file_path, file_name)`): `provider.upload_attachment(file_path, file_name)`.
- **4335** (`link_attachment_to_work_item(work_item_id, attachment_url, comment)`): `provider.link_attachment(str(work_item_id), attach_result)` (GAP-D).

**Archivos exactos F7:** `api/tickets.py` (820, 4321, 4335).

**Tests F7:** `backend/tests/test_plan70_group_attachments.py`. Casos: (1) fetch Flag ON/OFF; (2) upload Flag ON retorna dict con `id`/`url` consumible por `link_attachment`; (3) link Flag ON → `link_attachment` recibe el dict de upload (no URL suelta). Comando: `.\.venv\Scripts\python.exe -m pytest tests/test_plan70_group_attachments.py -q`.

**Trabajo del operador F7:** ninguno.

---

### F8 — Migración GRUPO "creación de work items" (call sites 5903, 6326, + bloque create_child_task 4148/3245 + `publish_epic_children` 6930/6941/6958)

**Es el grupo más grande por GAP-E (firma).**

**Call sites:**
- **5903** (`create_work_item(work_item_type="Epic", title=, description=)`): `provider.create_item(_tracker_item_from_kwargs(work_item_type="Epic", title=title, description=clean_html))`.
- **6326** (`create_work_item(work_item_type="Issue", ...)`): ídem con `item_type="Issue"`.
- **4148** (`create_work_item(work_item_type="Task", fields={...}, parent_ado_id=...)`): `provider.create_item(_tracker_item_from_kwargs(work_item_type="Task", fields=..., parent_ado_id=...))`.
- **3245** (dentro del bridge de jerarquía multi-nivel, mismo patrón fields-style): ídem.
- **6930/6941/6958** (`publish_epic_children`): esta función usa `build_ado_client(project_name)` directo (tickets.py:6930) cuando `ado is None`. Migrar el default del parámetro `ado=None` a `provider = _provider_for_ticket(project_name=project_name) or build_ado_client(project_name)`; los `create_work_item` internos se envuelven con `_tracker_item_from_kwargs(...)`.

**Retorno:** `provider.create_item(TrackerItem) -> dict`. El dict debe exponer `["id"]` y `["_links"]["html"]["href"]` (o fallback a `provider.item_url(id)`). El adapter GitLab debe normalizar al shape ADO (decisión F1; verificar en `gitlab_provider.py:create_item`).

**Archivos exactos F8:** `api/tickets.py` (3245, 4148, 5903, 6326, 6910-6970 `publish_epic_children`).

**Tests F8:** `backend/tests/test_plan70_group_create.py`. Casos: (1) Epic Flag ON → `create_item` con `TrackerItem(item_type="Epic")`; (2) Issue Flag ON → idem Issue; (3) Task fields-style + parent → `TrackerItem.parent_id` correcto; (4) `publish_epic_children` Flag ON → usa provider; (5) Flag OFF → `AdoClient.create_work_item` con firma original. Comando: `.\.venv\Scripts\python.exe -m pytest tests/test_plan70_group_create.py -q`.

**Trabajo del operador F8:** ninguno.

---

### F9 — Migración GRUPO "helpers de verificación" (`_parent_exists_preflight`, `_consumed_task_ado_status`, call sites 3776, 3853, 6242)

**GAP-B (get_work_item → get_item).**

**Trabajo:**
- `_parent_exists_preflight` (tickets.py:3353-3397): reemplazar `getattr(ado, "get_work_item", None)` por `getattr(provider, "get_item", None)` cuando `provider is not None`; la llamada `get_wi(epic_ado_id, [...])` se reemplaza por `provider.get_item(str(epic_ado_id))` y el filtrado de campos se hace post-fetch sobre el dict retornado.
- `_consumed_task_ado_status` (tickets.py:3495-3540): mismo patrón. `get_wi(task_id_int, ["System.Id","System.WorkItemType","System.State"])` → `provider.get_item(str(task_id_int))` + `.get("fields", {})` filtering en el caller.
- Call site **6242** (`get_work_item(ado_id, fields=["System.Rev"])`): `provider.get_item(str(ado_id))` + lectura `.get("fields",{}).get("System.Rev")` en el caller.
- Los call sites **3776** y **3853** pasan el `ado`/`provider` a `_consumed_task_ado_status`; migrar el kwarg a `provider=` cuando el flag está ON.

**Archivos exactos F9:** `api/tickets.py` (3353, 3495, 3776, 3853, 6242).

**Tests F9:** `backend/tests/test_plan70_group_helpers.py`. Casos: (1) `_parent_exists_preflight` con provider → usa `get_item`; (2) `_consumed_task_ado_status` con provider → "exists"/"missing"/"unknown" classify correcto; (3) Flag OFF → `getattr(ado,"get_work_item")` original; (4) `System.Rev` leído del dict post-fetch en 6242. Comando: `.\.venv\Scripts\python.exe -m pytest tests/test_plan70_group_helpers.py -q`.

**Trabajo del operador F9:** ninguno.

---

### F10 — Migración GRUPO "sync" (call sites 508, 5303) — GAP-A

**GAP-A:** `sync_tickets(client=AdoClient)` está tipado a ADO (services/ticket_service.py:116). Branch explícito:

```python
provider = _provider_for_ticket(project_name=project_name)
if provider is not None and provider.name != "azure_devops":
    # Path no-ADO: el provider expone fetch_open_items(TrackerQuery)
    items = provider.fetch_open_items(TrackerQuery(state="open"))
    result = _apply_synced_items(items, project_name)  # helper nuevo, pura
else:
    client = _ado_client_for_ticket(project_name=project_name)
    result = sync_tickets(client=client)
```

**`_apply_synced_items(items, project_name)`** es una función PURA nueva en `tickets.py` que aplica la misma lógica de upsert local que `sync_tickets` hace post-fetch ADO. Se extrae del path legacy sin romperlo (refactor safe: `sync_tickets` la invoca internamente después).

**Archivos exactos F10:** `api/tickets.py` (508, 5303, nueva `_apply_synced_items`), `services/ticket_service.py` (extraer la lógica de upsert a `_apply_synced_items` reusable — diff mínimo, no romper callers existentes).

**Tests F10:** `backend/tests/test_plan70_group_sync.py`. Casos: (1) Flag ON + ADO → cae a `sync_tickets` (provider.name == "azure_devops"); (2) Flag ON + GitLab → `fetch_open_items` + `_apply_synced_items`; (3) Flag OFF → `sync_tickets` ADO; (4) `_apply_synced_items` es pura (idempotente). Comando: `.\.venv\Scripts\python.exe -m pytest tests/test_plan70_group_sync.py -q`.

**Riesgo #3 (ver sección 5):** `sync_tickets` para GitLab podría necesitar lógica específica (labels GitLab ≠ states ADO). Si `_apply_synced_items` no cubre el caso GitLab en F10, se documenta como limitación y se deja el branch ADO-only con `provider.name == "azure_devops"` guard; el path GitLab lanza `NotImplementedError` ruidoso (no silencioso). **Esta decisión la toma el operador al activar la flag para un proyecto GitLab real.**

**Trabajo del operador F10:** ninguno (default OFF). Si el operador quiere usar un proyecto GitLab, debe confirmar que F10 cubre su caso o aceptar que sync queda ADO-only.

---

### F11 — Migración de `ado_publisher.py` y `ado_sync.py` (construcción literal)

**Trabajo:** migrar las construcciones literales `AdoClient(` en:
- `services/ado_publisher.py:258` (lambda default), `:579` (factory).
- `services/ado_sync.py:111`.

A `get_tracker_provider(project)` cuando aplique. Para los sites donde el uso es intrínsecamente ADO (ej. lógica interna de `ado_publisher` que armar payloads ADO-específicos), se **deja la construcción literal** y se **mantiene en `_ALLOWED`** con un comentario "ADO-only por diseño (X razón)".

**Criterio:** cada site se decide individualmente. Los que migren se quitan de `_ALLOWED` en F12; los que no, quedan documentados.

**Archivos exactos F11:** `services/ado_publisher.py` (258, 579), `services/ado_sync.py` (111).

**Tests F11:** `backend/tests/test_plan70_publisher_sync.py`. Casos por site migrado: contract test de que el flujo equivalente funciona con provider mock. Comando: `.\.venv\Scripts\python.exe -m pytest tests/test_plan70_publisher_sync.py -q`.

**Trabajo del operador F11:** ninguno.

> **Fuera de scope (ver sección 6):** `api/pm.py`, `services/qa_browser_context.py`, `services/agent_completion_internal.py`, `services/ado_edit_learning.py`, `services/ticket_service.py` se quedan en `_ALLOWED` como legacy auxiliar (NO están en el flujo tracker principal).

---

### F12 — Centinela REFORZADO

**Trabajo:** el centinela actual (`tests/test_no_adoclient_outside_ado_provider.py:56`) solo busca `AdoClient(` literal. **Se refuerza** con un NUEVO test que capture el acoplamiento tipado residual:

**Nuevo archivo:** `backend/tests/test_plan70_no_typed_adoclient_in_api.py`.

**Patrón del test (3 controles):**
1. **Import de `AdoClient`** en cualquier archivo de `api/` → debe estar en un allowlist residual explícito (ej. ninguno tras F2-F10, salvo el fallback legítimo en `_ado_client_for_ticket` que se conserva).
2. **Type-hint `-> AdoClient`** en `api/` fuera del allowlist → falla.
3. **Call sites `_ado_client_for_ticket(`** en `api/tickets.py` → después de F3-F10 deben ser SOLO los que están dentro de la rama `else` (fallback flag OFF). Se permite el helper mismo (definición) y sus llamadas desde el branch fallback; se prohíben nuevos usos fuera del branch fallback.

**Allowlist residual F12 (post-migración):**
- `services/ado_provider.py`, `services/ado_client.py`, `services/project_context.py` (puerto + seam).
- `api/tickets.py::_ado_client_for_ticket` (definición + llamadas fallback explícito).
- Legacy que F11 decida no migrar.

**Qué captura:** cualquier nuevo archivo `api/*.py` que importe `AdoClient`, cualquier type-hint `-> AdoClient` fuera del allowlist, cualquier nuevo `_ado_client_for_ticket(` que NO esté en el branch fallback explícito.

**Tests F12:**
- Archivo: `backend/tests/test_plan70_no_typed_adoclient_in_api.py`.
- Casos:
  1. Sin imports nuevos de `AdoClient` en `api/` fuera de allowlist → pass.
  2. Sin type-hints `-> AdoClient` en `api/` fuera de allowlist → pass.
  3. `_ado_client_for_ticket(` solo aparece en definición + branches `else` fallback → pass (cuenta exacta tras F3-F10).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan70_no_typed_adoclient_in_api.py -q`.

**Criterio binario F12:** los 3 casos pasan; el centinela viejo (`test_no_adoclient_outside_ado_provider.py`) sigue verde; allowlist residual está explícitamente documentado en el test.

**Trabajo del operador F12:** ninguno.

---

### F13 — Flag kill-switch + ratchet

**Trabajo:**
- Confirmar `STACKY_TICKETS_PROVIDER_ENABLED` en `config.py` con `env_only=False` (editable por UI en HarnessFlagsPanel).
- Agregar la línea al `harness_defaults.env`: `STACKY_TICKETS_PROVIDER_ENABLED=false`.
- Agregar la línea a `.env.example` (si existe).
- Registrar TODOS los archivos de test del Plan 70 en el ratchet del Plan 49 (`HARNESS_TEST_FILES` en sh + ps1) o el meta-test F4 falla.

**Archivos exactos F13:** `config.py`, `harness_defaults.env`, `.env.example`, `tests/conformance/test_harness_ratchet.py` (o el artefacto ratchet que aplique — ver memoria `ratchet-obliga-registrar-tests`).

**Tests F13:**
- Correr el meta-test del Plan 49 F4 y confirmar verde tras registrar los 11 archivos nuevos del Plan 70.
- Correr el centinela viejo + el nuevo (F12).
- Comando: `.\.venv\Scripts\python.exe -m pytest tests/conformance/test_harness_ratchet.py tests/test_no_adoclient_outside_ado_provider.py tests/test_plan70_no_typed_adoclient_in_api.py -q`.

**Criterio binario F13:** ratchet verde; centinelas verde; flag aparece en `harness_defaults.env` y en la UI (HarnessFlagsPanel, categoría "Tickets / Tracker Provider").

**Trabajo del operador F13:** ninguno.

---

## 5. Riesgos y mitigaciones

1. **`tickets.py` es el corazón del flujo tracker en producción** (661 archivos,LOC alto, múltiples rutas críticas: create_child_task, autopublish épica/issue, sync). **Mitigación:** flag `STACKY_TICKETS_PROVIDER_ENABLED` default OFF (byte-idéntico), migración incremental por grupos cohesivos (F3-F10), backward-compat total (`_ado_client_for_ticket` se conserva), cada grupo con tests TDD propios.
2. **`create_work_item` → `create_item(TrackerItem)` cambia firma** (GAP-E). **Mitigación:** adapter local puro `_tracker_item_from_kwargs(...)` (F1) normaliza las dos firmas usadas (kwargs-style y fields-style) sin tocar el puerto; tests F1 cubren las dos formas.
3. **`sync_tickets` es ADO-only** (GAP-A, ticket_service.py:116). **Mitigación:** branch explícito por `provider.name`; path GitLab usa `fetch_open_items` + `_apply_synced_items` (pura, extraída del legacy); si el caso GitLab no está cubierto, se lanza `NotImplementedError` ruidoso (no silencioso) y el operador decide.
4. **`get_work_item` vs `get_item`** (GAP-B) y kwarg `fields`. **Mitigación:** el caller filtra campos post-fetch del dict retornado; no se añade kwarg al puerto.
5. **Adapter GitLab debe normalizar shapes ADO** (`get_authenticated_user` → `{uniqueName, displayName}`; `create_item` → `{id, _links.html.href}`; `get_item` → `{fields:{...}}`). **Mitigación:** verificar en F1 (`gitlab_provider.py`); si falta, agregar normalización determinista en el adapter (no en el caller).
6. **Falso verde en migración** (los tests del fallback ADO pasan pero el branch provider nunca se ejecuta). **Mitigación:** cada test F3-F10 tiene un caso "Flag ON → provider llamado" explícito con mock; además F12 cuenta call sites para asegurar que el branch fallback es el único residual.
7. **3 runtimes** (Codex/Claude Code/Copilot). **Mitigación:** el plan NO toca prompts ni runtime del agente; todo el cambio es capa de servicios/API; los 3 runtimes siguen operativos.

---

## 6. Fuera de scope

- **NO** reconstruir el puerto TrackerProvider (Plan 65) — ya está completo.
- **NO** migrar `api/pm.py`, `services/qa_browser_context.py`, `services/agent_completion_internal.py`, `services/ado_edit_learning.py`, `services/ticket_service.py` — son legacy auxiliar fuera del flujo tracker principal; se quedan en `_ALLOWED` del centinela.
- **NO** auth/RBAC (mono-operador, sin login).
- **NO** agregar kwarg `top`/`fields`/`fmt` al puerto (se normaliza en callers/adapters).
- **NO** romper la backward-compat: `_ado_client_for_ticket` y `build_ado_client` se conservan.
- **NO** UX/notifications (la capa perceptible no se toca).

---

## 7. Glosario

- **TrackerProvider:** `Protocol` formal (services/tracker_provider.py:56) con 18 métodos que todo adapter de tracker debe implementar.
- **PORT_METHODS:** tupla canónica de los 18 nombres de método del puerto (tracker_provider.py:79-98); fuente de verdad para "qué hace el puerto".
- **`_ado_client_for_ticket`:** helper en api/tickets.py:340 que retorna un `AdoClient` (thin wrapper de `build_ado_client`). Se conserva como fallback flag OFF.
- **`build_ado_client`:** seam legítima de construcción en services/project_context.py:221 (se MANTIENE; el puerto la usa internamente vía `AdoTrackerProvider`).
- **`get_tracker_provider(project)`:** fábrica (tracker_provider.py:105) que retorna el adapter según `issue_tracker.type`.
- **`issue_tracker.type`:** campo del `client_profile` del proyecto: `azure_devops` (default) o `gitlab`.
- **`STACKY_GITLAB_ENABLED`:** flag env (default false) requerida para instanciar `GitLabTrackerProvider`.
- **`STACKY_TICKETS_PROVIDER_ENABLED`:** flag nueva de este plan (default OFF, editable por UI) que gatea la migración de los 18 call sites.
- **Ratchet:** mecanismo del Plan 49 que obliga a registrar todo test nuevo en `HARNESS_TEST_FILES`; meta-test que falla si se agregan tests sin registrar.
- **Centinela:** test anti-recableo. Viejo: `tests/test_no_adoclient_outside_ado_provider.py` (busca `AdoClient(` literal). Nuevo: `tests/test_plan70_no_typed_adoclient_in_api.py` (captura acoplamiento tipado).
- **GAP-A/B/C/D/E/F:** ver tabla F0.

---

## 8. Orden de implementación

1. **F0** — Inventario (cumplido en este doc).
2. **F1** — Adapter local `_tracker_item_from_kwargs` + verificar adapters ADO/GitLab.
3. **F2** — Wrapper `_provider_for_ticket` + flag `STACKY_TICKETS_PROVIDER_ENABLED` default OFF.
4. **F3** — Grupo comentarios (566, 787, `_post_phase_comment`/6474).
5. **F4** — Grupo estado (1146, 1730, 4231).
6. **F5** — Grupo url (1951, 3810, 4157, 5914, 6337).
7. **F6** — Grupo assignments + auth (5049, 5189).
8. **F7** — Grupo attachments (820, 4321, 4335).
9. **F8** — Grupo creación work items (3245, 4148, 5903, 6326, `publish_epic_children`).
10. **F9** — Grupo helpers verificación (`_parent_exists_preflight`, `_consumed_task_ado_status`, 3776, 3853, 6242).
11. **F10** — Grupo sync (508, 5303) — branch explícito ADO/GitLab.
12. **F11** — ado_publisher.py + ado_sync.py (decidir migrar o documentar como ADO-only).
13. **F12** — Centinela reforzado (`test_plan70_no_typed_adoclient_in_api.py`).
14. **F13** — Flag en harness_defaults.env + UI + ratchet.

Cada fase es auto-contenida y se puede implementar/commitear de forma independiente (cada una deja el sistema verde y backward-compatible).

---

## 9. DoD global (Definition of Done)

- [ ] **(a)** Tabla F0 completa y verificada (cada fila cita `tickets.py:línea` con método ADO exacto). — **Cumplido en este doc.**
- [ ] **(b)** Los 18 call sites migrados (grupos F3-F10) con branch provider + fallback ADO.
- [ ] **(c)** Centinela reforzado (F12) verde **sin** `_ado_client_for_ticket` en `api/` fuera del allowlist residual (definición + branches fallback explícitos).
- [ ] **(d)** Flag `STACKY_TICKETS_PROVIDER_ENABLED` default **OFF**; byte-idéntico con flag OFF (tests F2-F10 lo verifican en cada grupo).
- [ ] **(e)** Un proyecto con `issue_tracker.type=gitlab` (y `STACKY_GITLAB_ENABLED=true`) pasa un smoke test end-to-end de los flujos de `tickets.py` sin construir ni tocar `AdoClient` en ningún punto del path. (Smoke test manual o script en `tests/plan70_smoke_gitlab.py`.)
- [ ] **(f)** Los 3 runtimes (Codex, Claude Code, GitHub Copilot Pro) operativos sin cambios (el plan no toca prompts/runtime del agente).
- [ ] **(g)** Ratchet verde (Plan 49 F4) con los 11 archivos de test nuevos registrados.
- [ ] **(h)** Centinela viejo (`test_no_adoclient_outside_ado_provider.py`) sigue verde; allowlist residual explícito y documentado.

---

## 10. Notas de implementación (para el modelo menor que ejecute esto)

- **Venv del repo:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest <test> -q`. El venv es py3.13 (ver memoria `stacky-backend-dev-test-env`); correr tests por archivo, no la suite completa.
- **Patrón mock (TDD):** importar `db` a nivel módulo; lazy-imports se parchean en el módulo origen (ver memoria `plan-28-lifecycle`). Para mockear el provider, parchear `api.tickets._provider_for_ticket` y `api.tickets._ado_client_for_ticket`.
- **Cada commit deja el sistema verde y backward-compatible.** No acumular fases en un solo commit si una falla.
- **Falsos verdes prohibidos:** cada test "Flag ON → provider llamado" debe afirmar que el mock del provider fue invocado (no solo que no lanza).
- **Si una fase revela un GAP no listado en F0**, detener y actualizar este doc antes de seguir (no improvisar).
