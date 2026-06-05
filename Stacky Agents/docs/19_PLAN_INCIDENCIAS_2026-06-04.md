# Plan de trabajo — Resolución de incidencias (2026-06-04)

> Alcance: 3 incidencias reportadas en Stacky Agents.
> 1. Unificación de datos de conexión.
> 2. Publicación duplicada de comentarios por Stacky Agents.
> 3. Creación incorrecta de comentarios en lugar de tasks funcionales (épicas 241 y 242 de Pacífico).
>
> Metodología: el análisis se construyó leyendo el código real (backend Python/Flask + frontend React) y verificando de forma adversarial cada hipótesis de causa raíz contra los archivos citados. Todas las referencias usan rutas relativas a `Stacky Agents/` con `archivo:línea`.

---

## Resumen ejecutivo

| # | Incidencia | Causa raíz confirmada (resumen) | Severidad | Esfuerzo |
|---|------------|----------------------------------|-----------|----------|
| 1 | Datos de conexión duplicados | El mismo dato de conexión se edita/persiste en **dos lugares** de la pestaña de Configuración (campo superior "hint" en el JSON de perfil vs. campo inferior que escribe el fichero de credencial/`config.json`), sin una única fuente de verdad ni regla de precedencia. | Media | Bajo–Medio |
| 2 | Comentarios duplicados | La idempotencia está cableada a `(execution_id, html_sha256)` y se aplica **después** del POST a ADO. Varios disparadores (output_watcher Modo B, `finish_work`, PATCH `stacky-status`, fallback directo) pueden publicar el mismo contenido — por carrera entre hilos o porque el `execution_id` difiere — antes de que el `UNIQUE` lo bloquee. La hipótesis del "eco del agente" se **descarta**. | Alta | Medio |
| 3 | Comentario en la épica en vez de task | La creación de la Task funcional depende de una cadena frágil: el agente **decide** escribir `pending-task.json` (→ crea Task) o `comment.html` (→ publica comentario); si la auto-creación falla (p. ej. jerarquía Epic→Task no permitida en el process template de Pacífico, sin validación preflight) el `pending-task.json` queda sin consumir y `finish_work` **degrada a un comentario de cierre** en la épica. | Alta | Medio |

**Relación entre incidencias 2 y 3:** ambas comparten la misma arquitectura de cierre/publicación (`output_watcher` Modo A/B → `close_execution_with_publish` → `ado_publisher` / `create_child_task`). Conviene abordarlas en conjunto.

---

## Incidencia 1 — Unificación de datos de conexión

### Descripción del problema
En la pestaña de **Configuración** de la app, los datos de conexión existen **duplicados**: el mismo valor se puede capturar y persistir en más de un campo/lugar. La regla de negocio pedida es **unificar y conservar únicamente el dato ubicado más abajo en la pestaña de configuración**, eliminando o derivando el resto para evitar inconsistencias (drift entre copias).

Se identificaron **tres** familias de duplicación candidatas (a confirmar cuál es la que el reporte señala — ver Pasos de análisis):

1. **Conexión a Base de Datos (candidato más literal a "el de más abajo").**
   En `frontend/src/components/ClientProfileEditor.tsx` el campo **"Server"** y **"Usuario readonly"** aparecen **dos veces dentro de la misma sub-pestaña "Perfil del cliente"**:
   - Arriba — sección "Base de datos" (JSON del perfil): `ClientProfileEditor.tsx:790` (`database.server`) y `:791` (`database.readonly_user_hint`). Son *hints* no secretos que se guardan en `config.json`.
   - Abajo — tarjeta "Credencial BD readonly": `ClientProfileEditor.tsx:942` (`dbServer`) y `:944` (`dbUser`), que escriben el **fichero de credencial real** `backend/projects/{proyecto}/auth/db_readonly.json` (cifrado con DPAPI) vía `DbReadonlyAuth.save` (`:565`).
   - El propio formulario inferior **sincroniza hacia arriba** al guardar (`onSaveDbAuth` copia `server`/`readonly_user_hint` al JSON del perfil: `:586-590`), y un *hint* en `:823-826` ya indica que "el password se gestiona en la sección de más abajo".
   → El **campo de más abajo (tarjeta de credencial)** es de facto la fuente de verdad operativa; el de arriba es un duplicado editable que puede divergir.

2. **Conexión ADO + rutas de docs en el modal de proyecto.**
   En `frontend/src/components/EditProjectModal.tsx` conviven el formato **plano** y el **anidado** del mismo dato:
   - `docs_technical_path`/`docs_functional_path` (plano) y `docs_paths` (anidado) se inicializan **ambos** en el estado (`EditProjectModal.tsx:18-20`) y se envían **ambos** en el payload (`buildPayload`, `:181-185`).
   - ADO: campos planos `organization`/`ado_project` (`:22-23`) que el backend mapea a/desde `issue_tracker.organization`/`issue_tracker.project` en `config.json` (`backend/api/projects.py` `_project_to_dict` ~`:80-111`).
   - En el PATCH, la resolución usa `data.get("ado_project") or tracker.get("project")` (`backend/api/projects.py:471-472`): si el usuario envía el campo **vacío** para borrarlo, se **preserva el valor anterior** (no se puede vaciar).

3. **Credenciales ADO repartidas entre múltiples fuentes sin precedencia clara.**
   El mismo dato (org / project / PAT) existe en: `config.json` por proyecto (`issue_tracker.*` + `auth_file`), el fichero `auth/ado_auth.json`, y variables globales `.env` (`ADO_ORG`, `ADO_PROJECT`, `ADO_PAT`) declaradas como *managed keys* en `backend/api/global_config.py` (~`:34-66`) y expuestas en `backend/config.py:207-209`. La resolución efectiva la hace `services/ado_client.py` (`_resolve_active_project_defaults`, `_resolve_auth_header`) con *fallbacks* a `.env`/rutas legacy sin una jerarquía documentada.

> Cabo suelto relacionado: en `git status` figura `deleted: Stacky Agents/RSSICREA/config.json`. Hay que confirmar si la baja del proyecto RSSICREA fue intencional y si quedaron datos de conexión huérfanos en disco/BD.

### Posible causa
- **Deuda de esquema/legacy:** se mantuvieron simultáneamente dos representaciones del mismo dato (plano vs. anidado; hint del perfil vs. credencial real) sin migrar ni marcar una como autoritativa.
- **Falta de "single source of truth":** ningún punto del código declara qué campo gana cuando ambos están presentes; el último que se escribe en el estado o el orden de resolución del backend deciden de forma implícita.
- **Fallback de preservación incorrecto** en el PATCH (`or` en lugar de "tomar el valor enviado tal cual"), que impide vaciar/normalizar el campo.

### Pasos de análisis
1. **Confirmar con el reportante a qué "datos de conexión" se refiere** (BD, ADO, o ambos) y cuál es la "pestaña de configuración" exacta. El candidato más alineado con "el dato de más abajo" es la **conexión BD en "Perfil del cliente"** (`ClientProfileEditor.tsx`), pero conviene validarlo con captura de pantalla.
2. Mapear, para el dato confirmado, **todos los puntos de captura (UI), persistencia (config.json / auth/*.json / .env) y lectura (resolución runtime)**. Para BD: `ClientProfileEditor.tsx:786-827` (arriba) y `:931-967` (abajo) + `DbReadonlyAuth.save`/`.meta`. Para ADO: `EditProjectModal.tsx` + `backend/api/projects.py` + `services/ado_client.py`.
3. Determinar empíricamente **el orden visual** en la pestaña (cuál renderiza "más abajo") y **cuál se usa realmente en runtime**. En BD, el de más abajo (credencial) es el que consume el agente para conectarse; el de arriba es solo hint.
4. Reproducir el drift: editar el campo superior y el inferior con valores distintos, guardar, recargar y observar cuál persiste y cuál usa el runtime.
5. Auditar `config.json` de cada proyecto (`DeployStackyAgents/projects/*/config.json`) y los `auth/*.json` para detectar copias divergentes ya existentes.
6. Resolver el cabo de RSSICREA: `git log` del fichero, BD (`SELECT count(*) FROM tickets WHERE stacky_project_name='RSSICREA'`) y disco (`projects/RSSICREA/auth/`).

### Propuesta de solución
**Principio rector:** el dato de conexión válido es **el ubicado más abajo en la pestaña** (la credencial/fichero real); el resto se vuelve **derivado de solo lectura** o se elimina.

1. **BD (Perfil del cliente) — unificar a la tarjeta inferior:**
   - Hacer que los campos "Server"/"Usuario readonly" de la sección "Base de datos" superior (`:790-791`) sean **solo lectura** y se rellenen automáticamente desde la credencial (`DbReadonlyAuth.meta`), o eliminarlos del formulario editable y mostrarlos como informativos.
   - Mantener `onSaveDbAuth` (`:556-617`) como **único** punto de escritura del server/usuario; conservar la sincronización hacia el JSON del perfil para que el `config.json` refleje el valor canónico.
2. **ADO/docs (modal de proyecto) — colapsar a una sola representación:**
   - Eliminar el formato plano `docs_technical_path`/`docs_functional_path` del estado y del payload (`EditProjectModal.tsx:18-20`, `:181-185`); usar **solo** `docs_paths` anidado. Equivalente para Jira/Mantis.
   - En backend, devolver **una sola** representación en `_project_to_dict` (preferentemente la anidada) y actualizar los tipos de frontend (`types.ts`).
   - Corregir el fallback de preservación: cambiar `data.get("ado_project") or tracker.get("project")` por una semántica que respete el valor enviado (incluido vacío para borrar) con `data.get("ado_project", tracker.get("project"))` y `.strip()` (`backend/api/projects.py:471-472`), aplicando lo mismo a `organization` y análogos.
3. **Credenciales ADO — jerarquía única y documentada:**
   - Definir y documentar la precedencia: `proyecto explícito → proyecto activo (auth/ado_auth.json + issue_tracker de config.json) → .env/legacy` y registrar un `WARNING` cuando se cae a `.env`/legacy.
   - Evaluar retirar `ADO_ORG/ADO_PROJECT/ADO_PAT` de `_MANAGED_KEYS` si solo son defaults vacíos.
4. **RSSICREA:** decidir baja intencional (`git rm` + commit) o restauración (`git restore`), y limpiar/migrar datos huérfanos.
5. Añadir nota de deprecación y migración para los campos legacy.

### Criterios de validación
- Editar el dato en el campo **superior** ya no afecta el runtime; solo el **inferior** (credencial) cambia la conexión efectiva. Verificación: guardar, recargar y conectar.
- `GET` del proyecto devuelve **una única** representación del dato (sin duplicado plano+anidado).
- Enviar el campo ADO **vacío** ahora **lo borra** en `config.json` (no preserva el anterior).
- No quedan dos valores distintos para el mismo dato en `config.json`/`auth/*.json` tras guardar.
- Tests: unit de `buildPayload` (no emite campos planos), integración PATCH (vaciar borra), integración `DbReadonlyAuth` (el server del perfil queda alineado con la credencial).
- Estado de RSSICREA resuelto y sin huérfanos.

### Riesgos o puntos a revisar
- **Ambigüedad del alcance:** si "datos de conexión" se refería solo a ADO (no a BD), reorientar a la familia 2/3. Confirmar antes de tocar UI.
- Quitar el formato plano puede romper consumidores que aún lo lean → buscar usos antes de eliminar (`organization`, `ado_project`, `docs_technical_path`).
- Cambiar el fallback `or` por respeto al vacío puede borrar datos si el frontend envía vacíos sin intención → validar que el formulario solo envía los campos editados.
- Tocar la resolución de credenciales puede dejar sin conexión a proyectos que dependían del `.env` legacy → desplegar con `WARNING` y feature flag de rollback.
- Secretos: no loguear PAT/passwords; mantener DPAPI en la credencial inferior.

---

## Incidencia 2 — Publicación duplicada de comentarios por Stacky Agents

### Descripción del problema
Cuando Stacky Agents debe publicar **un** comentario HTML en un work item de Azure DevOps, lo publica **varias veces**. La hipótesis inicial del reporte es que el agente "detecta el comentario mientras aún lo está creando y por eso lo republica". Esa hipótesis se evaluó explícitamente y se **descarta** como causa raíz (ver abajo): la publicación está centralizada en backend y los agentes no republican.

### Posible causa
La causa raíz confirmada es de **idempotencia insuficiente en el publicador**, por la combinación de:

1. **La clave de idempotencia es `(execution_id, html_sha256)` y se aplica mayormente DESPUÉS del POST a ADO.**
   - `UNIQUE(execution_id, html_sha256)` en `services/ado_publisher.py:95-98`.
   - El dedupe **pre-ADO** (`:259-280`) y el POST (`:300`) **no están bajo lock**; entre el check y el POST hay una ventana. Si dos hilos pasan el check antes de que el primero haga `INSERT`, **ambos postean** y el segundo solo recibe `IntegrityError` (`:337-379`) — pero el comentario **ya se publicó dos veces**. La protección es *post-ADO*, no *pre-ADO*.
2. **Múltiples disparadores publican la misma ejecución/contenido:**
   - `output_watcher` Modo B → `close_execution_with_publish` → `_attempt_publish` → `publish_from_execution` (`services/output_watcher.py:377`, `services/agent_completion_internal.py:193,414`).
   - `finish_work` (`backend/api/tickets.py:1395`).
   - PATCH `stacky-status` (`set_stacky_status_by_ado`) también cierra+publica.
   - **Fallback directo** en `finish_work` que llama `post_comment` **saltándose el dedupe del publisher** cuando no hay HTML del agente (`backend/api/tickets.py:1416`).
3. **Duplicados entre ejecuciones (determinista, no solo carrera):** el guard por `(ticket_id, sha)` solo existe en el watcher (`_find_publish_by_sha`, `services/output_watcher.py:311-319,576-594`), **no** dentro de `publish_from_execution`. Si el mismo contenido se publica bajo un `execution_id` distinto (re-ejecución, o el watcher usa `latest_exec` mientras el PATCH usa otra ejecución), el dedupe por `(execution_id, sha)` **no dispara** y se duplica.
4. **Lectura del `comment.html` "a medio escribir":** el Modo B usa un *debounce* de solo `stable_delay_b = 2s` (`services/output_watcher.py:107-108,284-298`). Si el agente escribe el fichero en varias pasadas con pausas > 2s, cada snapshot con **SHA distinto** se publica por separado (cada uno pasa el dedupe por contenido). Este es el mecanismo más cercano a la hipótesis del reporte (se "lee mientras se crea"), aunque el observable sería contenido parcial, no idéntico.

> **Hipótesis del reporte ("el agente detecta el comentario mientras lo crea") — VEREDICTO: descartada como causa primaria.** `services/ado_publisher.py:1-23` documenta que solo el publicador puede llamar `post_comment`; los agentes escriben el HTML en disco y no republican. `services/ado_sync.py` solo lee/upsertea work items (no publica). No existe un bucle de "eco" agente→ADO→agente. Lo real es la combinación de disparadores + idempotencia post-ADO descrita arriba.

### Pasos de análisis
1. **Cuantificar y caracterizar el duplicado en logs/BD:**
   - `SELECT execution_id, html_sha256, status, triggered_by, published_at, comment_id FROM agent_html_publish ORDER BY published_at` para un ticket afectado: ¿hay varias filas `ok` con el mismo `sha` y distinto `execution_id`? ¿`idempotent_replay` presentes? ¿`triggered_by` distintos?
   - Revisar eventos `ado_publish.ok` en `stacky_logger` para el mismo `execution_id` con timestamps cercanos (carrera) vs. lejanos (re-ejecución).
2. **Determinar si los duplicados tienen contenido idéntico o parcial** (vía `comment_id`/contenido en ADO): idéntico → multi-trigger/cross-execution; parcial → lectura a medio escribir.
3. Mapear **todos** los llamadores de `publish_from_execution` y de `post_comment`:
   - `grep` `publish_from_execution(` y `post_comment(` en backend.
   - Confirmar cuáles se disparan en el flujo real (output_watcher habilitado? `finish_work` con `force_publish`?).
4. Reproducir la carrera: invocar en paralelo `output_watcher.scan_once()` y `finish_work`/PATCH para una misma ejecución con `comment.html` presente; verificar nº de POST a ADO con `AdoClient.post_comment` mockeado.
5. Verificar la ventana del debounce: escribir `comment.html` en dos tramos separados >2s y observar si se publican dos snapshots.
6. Confirmar que `ado_publish_post_hook` (`services/ado_publisher.py:385-410`) **no** está registrado en `_POST_HOOKS` (no añade un disparo extra) — la verificación indica que no lo está; reconfirmar con `grep register_post_hook`.

### Propuesta de solución
**Objetivo:** publicar **exactamente una vez** por comentario lógico, y solo cuando el contenido esté completo.

1. **(P0) Idempotencia verdadera basada en marcador, antes del POST.** Ya existe la infraestructura: `_stacky_comment_marker`/`_inject_stacky_marker` (`services/ado_publisher.py:481-508`) y `comment_exists(ado_id, marker)` en `services/ado_client.py:764-781`. Antes de `post_comment` (`:300`), hacer un **GET de comentarios y buscar el marcador**; si existe → devolver `idempotent_replay` sin postear. Esto cubre carreras, re-ejecuciones y reinicios.
2. **(P0) Serializar por ticket/work item.** Tomar un lock (en memoria para single-process; tabla `publication_locks` o `BEGIN EXCLUSIVE` en SQLite para multi-proceso) que cubra desde el check pre-ADO hasta el `INSERT` (`:259-348`), keyed por `ado_id`/`ticket_id` (no solo `execution_id`, para cubrir cross-execution).
3. **(P0) Unificar la clave de dedupe a `(ticket_id/ado_id, content_sha)`** dentro de `publish_from_execution`, replicando el guard que hoy solo está en el watcher (`_find_publish_by_sha`). Así el mismo contenido no se republica aunque cambie el `execution_id`.
4. **(P1) Eliminar el POST de fallback no idempotente** de `finish_work` (`backend/api/tickets.py:1408-1424`): enrutar esa nota de cierre por el mismo publicador (con marcador y dedupe) en vez de `post_comment` directo.
5. **(P1) Reforzar la estabilidad del `comment.html`** del Modo B: exigir un done-marker para comentarios (equivalente al `.stacky-done.json` del Modo A, `services/output_watcher.py:60,604-634`) o subir/asegurar el debounce y la estabilidad de mtime+tamaño antes de publicar, para no leer a medio escribir.
6. **(P1) Centralizar el cierre+publicación** en un único punto (gateway `agent_completion`) para que `finish_work`, PATCH y watcher converjan en una sola ruta idempotente.
7. **(Observabilidad)** Alerta cuando existan ≥2 filas `ok` con el mismo `(ado_id, content_sha)` en una ventana corta.

### Criterios de validación
- Disparar en paralelo watcher + `finish_work` para la misma ejecución/contenido → **un solo** `post_comment` a ADO y **una sola** fila `ok` en `agent_html_publish` (la segunda, `idempotent_replay`).
- Re-ejecutar el agente con el mismo contenido bajo otro `execution_id` → **no** se crea un segundo comentario (lo bloquea el marcador / dedupe por contenido).
- Con `force_publish=true` y mismo contenido → no duplica (lo frena el `comment_exists` por marcador).
- Escribir `comment.html` en dos tramos → solo se publica el contenido final (una vez).
- El work item en ADO tiene **un** comentario por comentario lógico (verificación por `comment_exists`/`fetch_comments`).
- Tests nuevos en `tests/test_ado_publisher*.py` que reproduzcan carrera y cross-execution.

### Riesgos o puntos a revisar
- **Multi-proceso:** un lock en memoria no sincroniza varios workers; usar lock a nivel DB si aplica. Confirmar el modelo de despliegue (single vs multi-instancia).
- El GET previo a cada publicación añade latencia y otra llamada a ADO → cachear/limitar y manejar errores de red sin bloquear el cierre.
- ADO podría **stripear** comentarios HTML/markers en ciertos proyectos → el código ya usa doble marca (comentario HTML + `span` oculto, `:494-508`); validar que sobrevive en Pacífico/SICREA.
- Cambiar la clave de dedupe a contenido podría **bloquear re-publicaciones legítimas** (mismo texto a propósito); reservar `force` para HTML distinto (distinto sha) y documentarlo.
- No romper el flujo de adjuntos (`_prepare_html_attachments`) al introducir el lock.

---

## Incidencia 3 — Creación incorrecta de comentarios en lugar de tasks funcionales

### Descripción del problema
Al ejecutar el agente **funcional** sobre una épica, en algunos casos **no se crea la Task funcional** (work item hijo de tipo Task) y, en su lugar, **aparece un comentario dentro de la épica**. Casos reportados: **épicas 241 y 242 de Pacífico (RSPACIFICO, `UbimiaPacifico`/`Strategist_Pacifico`)**.

### Posible causa
La creación de la Task depende de una cadena con varios puntos de fallo que **degradan silenciosamente a comentario**:

1. **El agente decide el artefacto, sin enforcement.** El prompt del agente funcional (`backend/agents/functional.py:18-39`) instruye: para crear Task, dejar `Agentes/outputs/epic-<ID>/<RF>/pending-task.json`; "si el output es solo un comentario funcional para el Epic", escribir `Agentes/outputs/<ID>/comment.html`. Es una **decisión del LLM**: si escribe `comment.html` para el `ado_id` de la épica, el `output_watcher` **Modo B** publica un comentario en la épica (`services/output_watcher.py:271-396`) en vez de crear la Task.
2. **La auto-creación de Tasks puede fallar y dejar el `pending-task.json` sin consumir.** El Modo A (`_process_mode_a`, `services/output_watcher.py:400-571`) llama vía self-HTTP a `create-child-task`. Si falla, incrementa `errors` y **no** marca consumido (`:664-763`).
   - *Bug histórico ya corregido en HEAD:* la auto-creación estaba **gateada detrás de una `AgentExecution` en estado `running`**; si el agente corría fuera del tracking o su ejecución ya estaba cerrada, nunca se creaba la Task. El fix mueve la auto-creación **antes** del gate (`:461-482`). Conviene confirmar que el incidente de 241/242 es anterior o posterior a ese fix.
3. **`create-child-task` no valida la jerarquía ni verifica la creación.** En `backend/api/tickets.py:2012+`, crea la Task con `System.LinkTypes.Hierarchy-Reverse` hacia la épica (`:2283-2290`). En procesos **Agile**, una **Epic no admite Task como hijo directo** (cadena Epic→Feature→Story→Task). RSPACIFICO no declara `process_template` en `DeployStackyAgents/projects/RSPACIFICO/config.json:107-112`, y **no hay validación preflight**. Si ADO rechaza (400/403 → `ADO_CREATE_REJECTED_BY_POLICY`/`ADO_CREATE_WORK_ITEM_FAILED`, `:2298-2338`), la Task no se crea.
   - Además, el `pending-task.json` se marca **consumido sin verificación post-creación** (no hay GET del work item creado ni chequeo de la relación padre), por lo que un fallo parcial puede dar por hecho un trabajo inexistente.
4. **`finish_work` degrada a comentario de cierre.** Si al cerrar no hay HTML ni ejecución (porque el `pending-task.json` quedó sin consumir), `finish_work` publica una **nota de cierre manual** directamente en la épica (`backend/api/tickets.py:1408-1424`) — el comentario observado en lugar de la Task.

### Pasos de análisis
1. **Forense de 241 y 242 (lo primero):**
   - ¿Existen en disco `Agentes/outputs/epic-241/**/pending-task.json` (y 242)? ¿con `status` `pending_manual_creation`, `consumed`, o malformado? ¿Existe además `Agentes/outputs/241/comment.html`?
   - `SystemLog` con `source='create_child_task'` para `ado_id` 241/242: ¿se intentó crear? ¿qué error devolvió ADO (texto exacto del 400/403)?
   - Logs de `output_watcher` Modo A/B para esas épicas: ¿auto-create invocado? ¿`AdoClient.create_work_item` llamado?
   - Estado actual en ADO: ¿la épica tiene comentario de Stacky pero **ninguna** Task hija?
2. **Confirmar el process template real** de `UbimiaPacifico/Strategist_Pacifico` (Agile/Scrum/CMMI) vía `GET _apis/work/processes` o el proyecto, y si Epic→Task está permitido o requiere Feature/Story intermedio.
3. Revisar si el agente escribió `comment.html` además de (o en lugar de) `pending-task.json` — eso determina si la causa fue de **decisión del agente** (cae en Modo B) o de **fallo de creación** (Modo A).
4. Revisar el marcado de `consumed` en `create_child_task` (`backend/api/tickets.py` ~`:2440-2520`) y si ocurre antes de verificar la Task en ADO.
5. Revisar el contrato `docs/specs/SPEC-create-child-task.md` vs. la implementación actual.

### Propuesta de solución
1. **(P0) Validación preflight de jerarquía** en `create_child_task` antes de `create_work_item`: consultar tipos/relaciones permitidos del process template y, si Epic→Task no es válido, **no degradar a comentario**: devolver error claro (`ADO_HIERARCHY_NOT_SUPPORTED`) con sugerencia (crear Feature/Story intermedio) y **dejar el `pending-task.json` sin consumir**.
2. **(P0) Declarar `process_template`** (y el mapeo de tipos padre→hijo) en `config.json` de RSPACIFICO y demás proyectos; consumirlo en `ado_client` para construir relaciones correctas. Donde corresponda, **crear automáticamente el nivel intermedio** (Epic→Feature→Task) o documentar el target correcto.
3. **(P0) Verificación post-creación**: tras crear la Task, hacer `GET` del work item y comprobar `id` + relación `Hierarchy-Reverse` al Epic + título; solo entonces marcar `consumed`. Si falla, marcar `error/retryable` y dejar el `pending-task.json` pendiente.
4. **(P1) No degradar a comentario cuando hay trabajo de Task pendiente.** En `finish_work` (`:1393-1434`), antes del fallback de cierre, **detectar `pending-task.json` sin consumir** para la épica y **rechazar el cierre** (HTTP 400 con `PENDING_TASKS_NOT_CONSUMED`) u ofrecer override explícito con motivo; nunca publicar la nota silenciosamente.
5. **(P1) Reducir la ambigüedad del agente:** que el agente funcional sobre una épica **siempre** produzca `pending-task.json` por RF (y el done-marker), reservando `comment.html` para casos sin Tasks; o mover la decisión "task vs comentario" a una regla determinista en Stacky en vez de al LLM.
6. **(P2) Durabilidad:** encolar la operación en `ado_write_operations` (outbox, `services/ado_write_outbox.py`) **antes** de tocar ADO y marcar `consumed` solo tras `succeeded` verificado; reemplazar el self-HTTP del watcher por la cola.
7. **(UI) Visibilidad** del bloqueo en el "Desatascador"/`artifact-status`/`unblocker-board`: mostrar "Error ADO: jerarquía no soportada" + el `pending-task.json` + acción de reintento/creación manual.

### Criterios de validación
- Test que simule Epic 241/242: intentar crear Task hija bajo Epic con process Agile → el endpoint devuelve **400/403 con mensaje claro** (no 200 con comentario) y el `pending-task.json` **no** queda `consumed`.
- Con `process_template` configurado, la jerarquía se construye correctamente (o se crea el Feature/Story intermedio) y la **Task aparece en ADO** vinculada a la épica.
- La verificación post-creación detecta una creación fallida/incompleta y evita marcar `consumed`.
- `finish_work` **no** publica nota de cierre cuando hay `pending-task.json` pendiente (rechaza u obliga a crear la Task / override explícito).
- Reintento idempotente: ejecutar `create-child-task` dos veces con el mismo `pending-task.json` no duplica la Task.
- Forense 241/242 cerrado: o bien la Task se crea (rescate), o queda documentada la causa (jerarquía/decisión del agente) con remediación aplicada.

### Riesgos o puntos a revisar
- Si Epic→Task **no** está soportado en Pacífico, crear Feature/Story intermedio automáticamente puede requerir campos/permisos adicionales y generar nuevos 400 → validar permisos y campos obligatorios del template.
- Bloquear el cierre por `pending-task.json` pendiente puede **trabar al operador** → ofrecer override con motivo registrado.
- Puede haber **épicas ya "cerradas" con comentario y sin Task** (incluidas 241/242) que parezcan completas → auditar y rescatar.
- `process_template` no declarado podría afectar a **otros proyectos** con defaults incorrectos → revisar todas las `config.json`.
- Interacción con Incidencia 2: el fallback de comentario en `finish_work` es a la vez fuente de duplicados y de "comentario en vez de task"; resolver ambos de forma coordinada.

---

## Priorización sugerida

1. **P0 inmediatos (estabilidad):**
   - Inc. 2: idempotencia por marcador + lock por ticket + dedupe por contenido (`ado_publisher`).
   - Inc. 3: preflight de jerarquía + verificación post-creación + `process_template` en RSPACIFICO; no marcar `consumed` sin verificar.
2. **P1 (robustez):**
   - Inc. 2/3: eliminar/encauzar el fallback de comentario directo de `finish_work`; centralizar cierre+publicación; done-marker para `comment.html`.
   - Inc. 3: bloqueo de cierre con Tasks pendientes; reducir ambigüedad del agente.
   - Inc. 1: unificar campos (BD y ADO/docs) a la fuente de verdad inferior; corregir fallback de preservación.
3. **P2 (deuda/durabilidad):**
   - Inc. 3: outbox `ado_write_operations` end-to-end.
   - Inc. 1: jerarquía de credenciales documentada; resolución de RSSICREA.

## Apéndice — Referencias de código citadas
- Publicación de comentarios: `backend/services/ado_publisher.py` (`:95-98` UNIQUE, `:259-280` dedupe pre-ADO, `:300` POST, `:337-379` IntegrityError, `:481-508` marcador).
- Disparadores de publicación: `backend/services/output_watcher.py` (`:271-396` Modo B, `:400-571` Modo A, `:60/604-634` done-marker, `:664-763` auto-create), `backend/services/agent_completion_internal.py` (`:62-242`, `:395-441`), `backend/api/tickets.py` (`:1395` publish, `:1408-1424` fallback, `:2012+` create_child_task).
- Sincronización (descarta eco): `backend/services/ado_sync.py`.
- Agente funcional: `backend/agents/functional.py:18-39`.
- Conexión BD/ADO (frontend): `frontend/src/components/ClientProfileEditor.tsx` (`:786-827`, `:931-967`, `:556-617`), `frontend/src/components/EditProjectModal.tsx` (`:18-39`, `:181-185`), `frontend/src/pages/SettingsPage.tsx`.
- Conexión/credenciales (backend): `backend/api/projects.py` (`:80-111`, `:471-472`), `backend/api/global_config.py` (~`:34-66`), `backend/config.py:207-209`, `backend/services/ado_client.py`.
- Config de proyecto: `DeployStackyAgents/projects/RSPACIFICO/config.json`.
