# API endpoints Mantis ↔ GitLab usados por Stacky + guía del migrador

> Documentación **derivada del código** (no inventada). Cada endpoint está anclado a
> `archivo:línea`. Lo que la migración necesitaría pero Stacky **no toca hoy** está
> marcado como **`[NO usado por Stacky hoy — requerido por el migrador]`**, con la
> referencia a la API oficial pero **sin inventar firmas**.
>
> Archivos fuente verificados:
> - `backend/services/mantis_client.py` (cliente Mantis REST + SOAP)
> - `backend/services/gitlab_client.py` (cliente HTTP GitLab v4 de bajo nivel)
> - `backend/services/gitlab_provider.py` (adapter TrackerProvider de GitLab)
> - `backend/services/tracker_provider.py` (puerto + factory)
> - `backend/project_manager.py` (auth por proyecto)

---

## 1. Autenticación y forma de las llamadas

### Mantis (REST)
- **Base URL:** `{url}/api/rest` — `mantis_client.py:226`.
- **Header de auth:** `Authorization: <token>` (token crudo, **sin** prefijo `Bearer`),
  más `Content-Type: application/json` y `Accept: application/json` — `mantis_client.py:228-233`.
- **Resolución de credenciales:** primero variables de entorno
  `MANTIS_URL`/`MANTIS_TOKEN`/`MANTIS_PROJECT_ID`, luego `projects/{NAME}/auth/mantis_auth.json`
  — `mantis_client.py:110-165`. El token se guarda **cifrado con DPAPI** vía
  `project_manager.write_mantis_auth` (`project_manager.py:580-606`) y se descifra al leer.
- **Paginación:** manual con `page` + `page_size` (50 por página) — `mantis_client.py:273-296`.
- **Errores:** `HTTPError` → `MantisApiError` con código + cuerpo (máx 500 chars);
  `URLError` → `MantisApiError` "no accesible" — `mantis_client.py:250-254`.
- **SSL:** `verify_ssl=False` desactiva verificación (instalaciones internas) — `mantis_client.py:241-244`.

### Mantis (SOAP / MantisConnect — alternativa)
- **WSDL:** `{url}/api/soap/mantisconnect.php?wsdl` — `mantis_client.py:806`.
- **Auth:** `username` + `password` como parámetros **en cada llamada** SOAP — `mantis_client.py:817-925`.
- Requiere `zeep` instalado — `mantis_client.py:795-804`.

### GitLab (REST v4)
- **Base URL:** `{GITLAB_URL}/api/v4` — `gitlab_client.py:130-133`.
- **Header de auth:** `PRIVATE-TOKEN: <token>` + `Accept: application/json` — `gitlab_client.py:95-96`.
- **Resolución del token:** env `GITLAB_TOKEN` (`config.py:785`) > `auth/gitlab_auth.json`
  (campo `token` o `private_token`, **texto plano, NO DPAPI**) — `gitlab_client.py:62-93`.
  El token **nunca** se persiste por `PUT /global-config` (es secreto) — `global_config.py:75-86`.
- **Encoding del project path:** `grupo/sub/proj` → `grupo%2Fsub%2Fproj`; un id numérico pasa igual
  — `gitlab_client.py:98-103`.
- **Paginación:** `_request_paginated` sigue `X-Next-Page`, `per_page=100`, tope `page_cap=40`
  — `gitlab_client.py:177-210`.
- **Reintentos:** en `429` respeta `Retry-After`, hasta 3 veces — `gitlab_client.py:145-151`.
- **Errores:** `TrackerApiError(status, message, kind)` con `kind` semántico
  (`auth`/`not_found`/`rate_limited`/`server`) — `gitlab_client.py:31-40,153-159`.

> **Hecho de arquitectura clave:** el **factory** `get_tracker_provider`
> (`tracker_provider.py:105-124`) instancia provider formal **solo** para `gitlab` y
> `azure_devops`. **Mantis (y Jira) se rechazan explícitamente** ("usa su path de sync
> existente"). Por eso GitLab tiene API rica de **creación** (provider) y Mantis solo
> tiene el **cliente legacy de lectura** (`mantis_client.py`).

---

## 2. Endpoints de Mantis que usa Stacky

| Método HTTP / op | Ruta (sobre `…/api/rest`) | Para qué sirve | Dónde en el código |
|---|---|---|---|
| `GET` | `/projects` | Listar proyectos accesibles | `mantis_client.py:256-267` (`list_projects`) |
| `GET` | `/issues?project_id=&page_size=&page=` | Listar issues del proyecto. **OJO: descarta status 80/90 (resueltos/cerrados)** | `mantis_client.py:269-297` (`fetch_open_issues`) |
| `GET` | `/issues/{id}` | Issue completo (incluye `notes` y `attachments`) | `mantis_client.py:302-315` (`fetch_notes`), `:371-414` (`fetch_attachments`) |
| `GET` | `/issues/{id}` (campo `notes`) | Comentarios/notas de un issue | `mantis_client.py:302-315` (`fetch_notes`) |
| `GET` | `/users/me` | Resolver el usuario del token | `mantis_client.py:333-340` (`get_current_user_id`) |
| `GET` | `/users?username=` | Resolver user id por username (SOAP fallback) | `mantis_client.py:344-361` |
| `GET` | `/files/{id}` | Descargar contenido de adjunto (**solo texto ≤100 KB hoy**) | `mantis_client.py:400-413,454-491` |
| `GET` | `/config?option[]=status_enum_string` | Enum de estados de la instalación | `mantis_client.py:552-585` (`get_project_statuses`) |
| `GET` | `/projects/{id}/categories` | Categorías del proyecto | `mantis_client.py:625-640` (`get_project_categories`) |
| `POST` | `/issues` | Crear issue (summary, description, category, status) | `mantis_client.py:690-749` (`create_issue`) |
| `POST` | `/issues/{id}/files` (JSON+base64) | Subir adjunto | `mantis_client.py:493-540` (`upload_attachment`) |
| `PATCH` | `/issues/{id}` (body `status`) | Cambiar estado | `mantis_client.py:660-688` (`transition_issue`) |
| `DELETE` | `/issues/{issue_id}/files/{file_id}` | Borrar adjunto | `mantis_client.py:416-452` (`delete_attachment`) |
| SOAP | `mc_projects_get_user_accessible` | Listar proyectos (SOAP) | `mantis_client.py:817-833` |
| SOAP | `mc_project_get_issues(user,pass,pid,page,size)` | Listar issues (SOAP; **también filtra resueltos**) | `mantis_client.py:837-867` |
| SOAP | `mc_issue_get(user,pass,id)` | Issue + notes (SOAP) | `mantis_client.py:888-904,913` |
| SOAP | `mc_issue_update(user,pass,id,data)` | Actualizar issue/estado (SOAP) | `mantis_client.py:906-934` |

**Lo que el migrador necesita y Stacky NO cubre hoy (lado Mantis):**
- **Listar TODOS los issues (incl. cerrados):** `GET /api/rest/issues` paginando sin el
  filtro de `_RESOLVED_STATUS_IDS`. **`[NO usado por Stacky hoy — requerido por el
  migrador]`** (Mantis REST acepta paginación completa por `page`/`page_size`; el filtro
  de cerrados lo aplica Stacky en cliente, no la API).
- **Relaciones/jerarquía** (`relationships`: parent/child, related, duplicate): vienen en
  el JSON de `/issues/{id}` pero Stacky **no las parsea**. **`[NO usado por Stacky hoy —
  requerido por el migrador]`**.
- **Reporter/handler (autor/asignado)**: presentes en el issue crudo; Stacky solo extrae
  el `reporter` de cada nota, no el del issue ni el `handler`. **`[NO usado por Stacky
  hoy — requerido por el migrador]`**.
- **Descarga de adjuntos binarios** (imágenes, PDF, zip): `GET /api/rest/files/{id}`;
  Stacky solo baja texto ≤100 KB (`mantis_client.py:407`). El migrador debe bajar el
  binario completo. **`[parcialmente usado — binarios requeridos por el migrador]`**.

---

## 3. Endpoints de GitLab que usa Stacky

Todas sobre `…/api/v4`; `{proj}` = project path URL-encodeado (`gitlab_client.py:98-103`).

| Método HTTP | Ruta | Para qué sirve | Dónde en el código |
|---|---|---|---|
| `GET` | `/user` | Usuario autenticado del token | `gitlab_provider.py:141-148` (`get_authenticated_user`) |
| `GET` | `/users?username=` | Resolver username → user id (assignee) | `gitlab_provider.py:89-97` (`_resolve_assignee_id`) |
| `GET` | `/projects/{proj}/issues` (paginado; params `state`,`labels`,`milestone`,`assignee_username`,`search`) | Listar issues; **base de la idempotencia (search por marcador)** | `gitlab_provider.py:150-157` (`fetch_open_items`) |
| `GET` | `/projects/{proj}/issues/{id}` | Issue puntual | `gitlab_provider.py:159-162` (`get_item`) |
| `POST` | `/projects/{proj}/issues` | **Crear issue** (title, description, labels, assignee_ids) | `gitlab_provider.py:207-231` (`create_item`) |
| `PUT` | `/projects/{proj}/issues/{id}` | Actualizar estado / labels / assignee / descripción | `gitlab_provider.py:173-205,318-332,280-296` |
| `GET` | `/projects/{proj}/issues/{id}/notes` (paginado) | Leer comentarios (excluye system) | `gitlab_provider.py:235-250` |
| `POST` | `/projects/{proj}/issues/{id}/notes` | **Postear comentario** | `gitlab_provider.py:252-260` (`post_comment`) |
| `POST` | `/projects/{proj}/uploads` (multipart) | **Subir adjunto** → devuelve `{markdown,url}` | `gitlab_provider.py:268-278` (`upload_attachment`) |
| `POST` | `/groups/{group}/epics/{parent}/issues` | Vincular issue a **epic nativo** (Premium) | `gitlab_provider.py:104-110` (`_link_parent`) |
| `POST` | `/projects/{proj}/issues/{child}/links` | **Fallback** de jerarquía: issue-link (sin licencia) | `gitlab_provider.py:118-123` (`_link_parent`) |
| `GET` | `/projects/{proj}/issues/{parent}/links` | Buscar hijos vinculados (idempotencia jerárquica) | `gitlab_provider.py:341-345` (`find_child_by_marker`) |
| `GET` | `/projects/{proj}/issues/{id}/resource_label_events` (paginado) | Auditoría de labels | `gitlab_provider.py:374-386` (`fetch_item_updates`) |
| `GET` | `/projects/{proj}/issues/{id}/resource_state_events` (paginado) | Auditoría de estados | `gitlab_provider.py:391-402` |
| `GET` | `/projects/{proj}/pipelines` (paginado; param `ref`) | Pipelines CI | `gitlab_provider.py:432-454` (`fetch_pipelines`) |

**Lo que el migrador necesita y Stacky NO cubre hoy (lado GitLab):**
- **Preservar autor/fecha originales:** la API de GitLab fija autor=token y fecha=ahora.
  No hay forma estándar por API; se usa **cabecera de procedencia** en el cuerpo. La
  impersonación con `sudo=<user>` requiere **token de admin** y no la usa Stacky.
  **`[NO usado por Stacky hoy — opcional, requiere admin]`**.
- **Crear Epics nativos** (no solo vincular a uno existente): Stacky vincula
  (`/groups/{group}/epics/{parent}/issues`) pero **no crea** el epic. Si la jerarquía
  Mantis se mapea a Epics nativos, el migrador debe `POST /groups/{group}/epics` primero.
  **`[NO usado por Stacky hoy — requerido si se usan Epics nativos]`** (con licencia
  Premium/Ultimate; si no, se usa el fallback issue-links que Stacky sí hace).

---

## 4. Guía de uso

### 4.1 Ejemplos de llamada (patrón real del código)

**Mantis REST — listar issues de un proyecto (curl equivalente a `_get`):**
```bash
curl -H "Authorization: $MANTIS_TOKEN" -H "Accept: application/json" \
  "$MANTIS_URL/api/rest/issues?project_id=3&page=1&page_size=50"
```

**Mantis REST — descargar un adjunto:**
```bash
curl -H "Authorization: $MANTIS_TOKEN" \
  "$MANTIS_URL/api/rest/files/123" -o adjunto.bin
```

**GitLab v4 — crear un issue (patrón de `create_item`):**
```bash
curl -X POST -H "PRIVATE-TOKEN: $GITLAB_TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"...","description":"... [[mantis:#123]]","labels":"type::issue,stacky::accepted"}' \
  "$GITLAB_URL/api/v4/projects/grp%2Fproj/issues"
```

**GitLab v4 — subir adjunto y postear comentario:**
```bash
curl -X POST -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  -F "file=@captura.png" "$GITLAB_URL/api/v4/projects/grp%2Fproj/uploads"
curl -X POST -H "PRIVATE-TOKEN: $GITLAB_TOKEN" -H "Content-Type: application/json" \
  -d '{"body":"nota migrada"}' \
  "$GITLAB_URL/api/v4/projects/grp%2Fproj/issues/42/notes"
```

En código, lo idiomático es **reutilizar las clases de Stacky** en vez de curl:
`MantisClient` (lectura) y `GitLabTrackerProvider` (creación) ya resuelven auth, base URL,
paginación y errores.

### 4.2 Secuencia exacta de endpoints del migrador Mantis → GitLab

**A. LEER de Mantis (origen):**
1. `GET /api/rest/projects` — descubrir `project_id`. *(`list_projects`)*
2. `GET /api/rest/issues?project_id=X&page=N&page_size=M` — **paginar TODO, incluidos
   cerrados** (no usar `fetch_open_issues`, que filtra status 80/90).
   **`[el migrador llama directo, sin el filtro de resueltos]`**
3. `GET /api/rest/issues/{id}` — por cada issue, traer detalle: `notes`, `attachments`,
   `relationships` (jerarquía), `reporter`/`handler`. *(Stacky parsea notes+attachments;
   relationships/reporter/handler **los lee el migrador del JSON crudo**)*
4. `GET /api/rest/files/{att_id}` — por cada adjunto, **descargar binario completo**.
   **`[binarios requeridos por el migrador]`**

**B. CREAR en GitLab (destino) — reutilizando `GitLabTrackerProvider`:**
5. **Idempotencia:** `GET /api/v4/projects/{proj}/issues?search=[[mantis:#<id>]]`
   (`fetch_open_items`). Si aparece, **omitir** (ya migrado).
6. `POST /api/v4/projects/{proj}/uploads` por cada adjunto (`upload_attachment`) → guardar
   el `markdown` devuelto.
7. `POST /api/v4/projects/{proj}/issues` (`create_item`) con:
   - `title` = summary Mantis;
   - `description` = cabecera de procedencia ("Creado por X el FECHA en Mantis #N") +
     marcador `[[mantis:#<id>]]` + cuerpo original + markdown de adjuntos;
   - `labels` = `type::issue` + label de estado (de Mantis status) + label de prioridad
     (de `_PRIORITY_MAP`);
   - `assignee` = username GitLab resuelto por **tabla de mapeo** (Mantis handler → GitLab).
8. `POST /api/v4/projects/{proj}/issues/{iid}/notes` por cada nota Mantis (`post_comment`).
9. **Jerarquía** (`_link_parent`): si hay Epics nativos + licencia →
   `POST /api/v4/groups/{group}/epics/{parent}/issues`; si no →
   `POST /api/v4/projects/{proj}/issues/{child}/links`.
10. **Estado:** si el issue Mantis estaba cerrado/resuelto →
    `PUT /api/v4/projects/{proj}/issues/{iid}` con `state_event=close` (`update_item_state`).

**C. VERIFICAR:**
11. `GET /api/v4/projects/{proj}/issues?search=[[mantis:` (paginado) — contar creados.
12. Reconciliar **conteo Mantis-total ↔ GitLab-creados** por marcador; reportar
    faltantes/duplicados.

---

## 5. Resumen de gaps (código de hoy vs migración)

| Necesidad de la migración | ¿Lo cubre Stacky hoy? | Acción del migrador |
|---|---|---|
| Listar **todos** los tickets Mantis (incl. cerrados) | **No** (`fetch_open_issues` filtra status 80/90) | Llamar `GET /issues` directo, paginando sin filtro |
| Leer **relaciones/jerarquía** Mantis | **No** (no se parsea `relationships`) | Leer `relationships` del JSON crudo del issue |
| Leer **reporter/handler** del issue | **No** (solo reporter de notas) | Leer campos crudos del issue |
| **Descargar adjuntos binarios** | **Parcial** (solo texto ≤100 KB) | `GET /files/{id}` para binarios |
| **Crear issues/comentarios/adjuntos** en GitLab | **Sí** (`GitLabTrackerProvider`) | Reutilizar el provider |
| **Jerarquía** en GitLab (epic-link o issue-link) | **Sí** (`_link_parent`, con fallback) | Reutilizar; crear Epic nativo aparte si aplica |
| **Idempotencia** por marcador | **Sí** (patrón `search`/`comment_exists`/`find_child_by_marker`) | Marcador `[[mantis:#id]]` + search previo |
| **Preservar autor/fecha originales** | **No** (límite de la API de GitLab) | Cabecera de procedencia en el cuerpo |
| **Mapeo de usuarios** Mantis→GitLab | **No** (resuelve username GitLab, no traduce) | Proveer tabla de mapeo |
| **Tracker Mantis como provider formal** | **No** (factory lo rechaza, `tracker_provider.py:122-124`) | Usar `MantisClient` (legacy) para leer |
