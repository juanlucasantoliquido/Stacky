# Plan: creacion efectiva de tareas y comentarios ADO

| Campo | Valor |
| --- | --- |
| Fecha | 2026-05-29 |
| Proyecto | Stacky Agents / RSPACIFICO |
| Alcance | Creacion de Tasks hijas desde `pending-task.json` y publicacion de comentarios desde `comment.html` |
| Objetivo operativo | Que cada intento termine en una confirmacion ADO verificable, una repeticion idempotente verificable, o una falla visible con retry/rescate. Nunca en silencio. |

## 1. Hallazgo puntual: ADO-167

La evidencia local indica que ADO-167 no esta en estado "sin tarea creada" desde el primer flujo:

- `system_logs.source='create_child_task'` registra exito el 2026-05-19 18:50:28 para `ado_id=167`.
- El mismo log informa `task_ado_id=172`.
- El archivo `C:/Desarrollo/GIT/RS/RSPACIFICO/Agentes/outputs/epic-167/rf-019-marca-oficial-en-el-mantenedor-de-direcciones/pending-task.json` esta en `status="consumed"` con `task_ado_id=172`.
- La ejecucion nueva sobre ADO-167 del 2026-05-29 quedo en `error` por `heartbeat stale`; como el `pending-task.json` ya estaba `consumed`, el flujo actual no vuelve a crear ni actualizar la tarea.

Conclusion: el sistema necesita distinguir claramente entre:

1. "Ya cree la tarea ADO-172 y esta es la evidencia".
2. "El operador regenero archivos y quiere actualizar o crear una nueva tarea".
3. "No pude crear/publicar y quedo en cola de retry".

Hoy esos estados se mezclan y el operador puede percibir "ejecutado pero no creo ticket".

## 2. Principio de garantia

No existe un 100% absoluto frente a ADO caido, PAT vencido, permisos insuficientes o reglas del proceso ADO. La garantia real debe ser:

- Exito confirmado: Stacky llama a ADO, recibe ID/respuesta y verifica por lectura posterior.
- Idempotencia confirmada: Stacky detecta que ya existe la tarea/comentario esperado y muestra la evidencia.
- Falla recuperable: Stacky no marca consumido ni completado; deja operacion pendiente con reintentos.
- Falla bloqueada: Stacky requiere accion humana y muestra causa, payload, correlacion y boton de retry/rescate.

## 3. Fallas actuales que hay que cerrar

1. `pending-task.json` con `status="consumed"` bloquea re-ejecuciones aunque el contenido haya cambiado despues (`v2_refresh_at`, nuevos archivos o nuevo analisis).
2. El watcher de outputs llama al endpoint `create-child-task` via self-HTTP; si falla la conexion o ADO, puede cerrar/cachear la ejecucion y no reintentar bien.
3. La creacion de Task se registra principalmente en `SystemLog`; falta una tabla durable de operaciones ADO con estado, retry, payload hash y resultado verificado.
4. `AdoClient.post_comment()` degrada devolviendo `{}` cuando falla; varios callers pueden tratar eso como exito.
5. `agent_html_publish` registra comentarios, pero el exito no exige verificar que el comentario exista en ADO.
6. El modelo ORM no declara explicitamente columnas operativas como `html_output_path` y `completion_source`; depender de atributos dinamicos vuelve fragil la persistencia.
7. Despues de crear una Task hija, Stacky no garantiza un upsert inmediato en `tickets`; por eso una tarea creada puede no aparecer en la UI local hasta un sync, o quedar invisible si el sync no la trae.
8. Hay formatos distintos de `pending-task.json`: el endpoint espera un contrato simple por RF, mientras algunos archivos contienen `tasks_pending` agregado a nivel epic. Eso debe ser soportado o rechazado de forma visible.

## 4. Arquitectura propuesta

### 4.1 Outbox ADO obligatoria

Crear una tabla `ado_write_operations` como fuente de verdad para toda escritura ADO.

Campos minimos:

- `id`, `operation_id`, `kind`: `create_task`, `post_comment`, `upload_attachment`, `link_attachment`, `update_state`.
- `status`: `queued`, `in_progress`, `succeeded`, `idempotent_succeeded`, `retryable_failed`, `blocked`, `dead_letter`.
- `source`: `output_watcher`, `manual_ui`, `agent_completion`, `finish_work`, `rescue`.
- `execution_id`, `ticket_id`, `parent_ado_id`, `target_ado_id`.
- `idempotency_key`, `payload_sha256`, `payload_path`, `payload_json`.
- `attempt_count`, `next_retry_at`, `last_attempt_at`.
- `ado_request_json`, `ado_response_json`, `ado_verified_at`.
- `error_code`, `error_message`, `correlation_id`.

Regla: ningun flujo marca `pending-task.json` como consumido ni una publicacion como exitosa hasta que exista una operacion `succeeded` o `idempotent_succeeded` verificada.

### 4.2 Idempotencia por contenido y marcador Stacky

Para Tasks:

- `idempotency_key = task:{parent_ado_id}:{rf_id}:{payload_sha256}`.
- Insertar un marcador invisible en `System.Description`, por ejemplo `<!-- stacky-task:{idempotency_key} -->`.
- Antes de crear, buscar si ya existe una Task hija con ese marcador o con `task_ado_id` registrado.
- Si el archivo esta `consumed` pero el `payload_sha256` cambio, mostrar decision explicita:
  - actualizar ADO-172;
  - crear nueva Task;
  - mantener ADO-172 y registrar solo nuevo comentario.

Para comentarios:

- `idempotency_key = comment:{ado_id}:{execution_id}:{html_sha256}`.
- Insertar marcador invisible `<!-- stacky-comment:{idempotency_key} -->`.
- `post_comment` debe devolver `comment_id` o lanzar error; `{}` no puede ser exito.
- Verificar con `fetch_comments()` que el marcador o `comment_id` exista.

### 4.3 Worker de escritura con retry

Reemplazar escrituras directas desde watcher/endpoints por un worker:

1. Endpoint o watcher valida artifacts y encola operacion.
2. Worker toma `queued`, ejecuta ADO, verifica por lectura posterior.
3. Si ADO falla con red/5xx/rate limit, queda `retryable_failed` con backoff.
4. Si falla con permisos, campo invalido o politica ADO, queda `blocked`.
5. UI muestra cola, causa, retry manual y accion sugerida.

El endpoint puede ofrecer modo sincrono para UI, pero internamente igual crea la operacion durable antes de tocar ADO.

## 5. Flujo de tareas propuesto

### 5.1 Escritura de artifacts por agente

El agente debe escribir de forma atomica:

1. `analisis-funcional.md`
2. `plan-de-pruebas.md`
3. `pending-task.json.tmp`
4. rename a `pending-task.json`
5. `.stacky-done.json` con:
   - `status="completed"`
   - lista de archivos
   - SHA-256 de cada archivo
   - `generated_at`
   - `execution_id` si esta disponible

### 5.2 Validacion preflight

Antes de crear:

- Resolver `repo_root` y mostrarlo en respuesta/log.
- Validar que `pending_task_path` cae bajo `<workspace_root>/Agentes/outputs`.
- Validar schema por version.
- Validar que `epic_id` coincide con la URL.
- Validar existencia de `plan_de_pruebas_path`.
- Calcular `payload_sha256`.
- Determinar si es nuevo, replay exacto, refresh de tarea consumida o contrato incompatible.

### 5.3 Creacion confirmada

La Task se considera creada solo si:

- ADO devuelve `id`.
- Stacky puede leer el work item creado.
- El work item tiene relacion padre a la Epic.
- La descripcion o comentario contiene el marcador Stacky.
- Si hay adjunto requerido, el attachment esta linkeado o queda una operacion separada pendiente, no un exito total falso.

### 5.4 Consumo del pending-task

`pending-task.json` se marca `consumed` solo con:

- `task_ado_id`.
- `operation_id`.
- `payload_sha256`.
- `verified_at`.
- `ado_url`.
- resultado de attachment/comment/state por separado.

Si el archivo cambia despues de consumido, se genera `revision=2` y el sistema no lo ignora: pide politica de actualizacion o crea nueva operacion.

## 6. Flujo de comentarios propuesto

### 6.1 Cierre de ejecucion

El cierre valido debe pasar por un unico gateway:

- `POST /api/tickets/by-ado/{ado_id}/agent-completion`
- o fallback interno `output_watcher` que llama a la misma logica, no a una copia.

Columnas a mapear explicitamente en `AgentExecution`:

- `html_output_path`
- `completion_source`
- `last_artifact_sha256`
- `completion_correlation_id`

### 6.2 Publicacion

`ado_publisher.publish_from_execution()` debe:

1. Leer y validar `comment.html`.
2. Calcular `html_sha256`.
3. Encolar `post_comment` en `ado_write_operations`.
4. Publicar con marcador `stacky-comment`.
5. Exigir `comment_id` o verificacion por `fetch_comments`.
6. Persistir en `agent_html_publish` solo cuando este verificado.

Si `post_comment` falla, la ejecucion puede cerrarse localmente, pero el comentario queda en `retryable_failed` o `blocked` y visible en UI.

## 7. Cambios concretos por archivo

- `Stacky Agents/backend/services/ado_client.py`
  - Cambiar `post_comment()` para que no oculte errores. Debe devolver respuesta con `id` o lanzar `AdoApiError`.
  - Agregar helpers de verificacion: `get_work_item()`, `find_child_by_marker()`, `comment_exists()`.

- `Stacky Agents/backend/api/tickets.py`
  - `create_child_task()` debe crear una operacion outbox antes de ADO.
  - No marcar `consumed` si create/upload/link/comment no quedaron verificados segun politica.
  - Agregar branch para `consumed + payload_sha256 distinto`.
  - Incluir `ticket_id`, `execution_id`, `operation_id`, `repo_root` y `payload_sha256` en auditoria.

- `Stacky Agents/backend/services/output_watcher.py`
  - No cerrar/cachear Modo A si auto-create deja errores.
  - Reemplazar self-HTTP por llamada interna al servicio/outbox.
  - Reintentar operaciones pendientes hasta verificacion o bloqueo.

- `Stacky Agents/backend/services/ado_publisher.py`
  - Persistir exito solo tras verificacion del comentario.
  - Tratar `{}` de ADO como falla.
  - Guardar `operation_id` y `comment_id`.

- `Stacky Agents/backend/models.py`
  - Mapear columnas reales de `agent_executions`: `html_output_path`, `completion_source`.
  - Agregar modelos `AdoWriteOperation`, `PendingTaskReceipt` y/o `CommentPublishReceipt`.

- `Stacky Agents/backend/services/ado_sync.py`
  - Tras crear Task, upsert inmediato en `tickets`.
  - Agregar reconciliacion para hijos creados por Stacky aunque el sync general no los traiga.

## 8. UI y diagnostico

Agregar una vista "Publicaciones ADO" con:

- Pendientes.
- En progreso.
- Confirmadas.
- Reintentables.
- Bloqueadas.

Para cada operacion mostrar:

- ADO padre/destino.
- archivo origen.
- SHA del payload.
- ultimo error ADO.
- proximo retry.
- boton `Reintentar`.
- boton `Marcar resuelto manualmente` con motivo obligatorio.
- link al work item ADO cuando exista.

Agregar endpoint diagnostico:

- `GET /api/ado-writes?status=...`
- `POST /api/ado-writes/{operation_id}/retry`
- `POST /api/tickets/by-ado/{ado_id}/reconcile-artifacts`
- `GET /api/tickets/by-ado/{ado_id}/artifact-status`

## 9. Reconciliacion automatica

Job cada 1-5 minutos:

1. Escanea `Agentes/outputs`.
2. Detecta `pending-task.json` sin receipt, consumidos sin Task verificable, comentarios sin publish verificado.
3. Consulta ADO por marcadores Stacky.
4. Repara DB local (`tickets`, `agent_html_publish`, receipts).
5. Reencola operaciones faltantes.
6. Emite alertas si hay `blocked` o `dead_letter`.

## 10. Casos de prueba obligatorios

- ADO-167: archivo `consumed` con `task_ado_id=172` y mismo hash devuelve idempotencia con evidencia.
- ADO-167 refresh: archivo `consumed` con hash nuevo no se ignora; crea decision explicita update/new/comment.
- Watcher con self-call/ADO caido no cierra ni cachea como completado sin operacion pendiente.
- `post_comment()` con error ADO no se registra como exito.
- Comentario publicado se verifica por `comment_id` o marcador.
- Task creada se verifica por GET work item y relacion padre.
- Attachment fallido deja operacion separada pendiente o estado degraded visible, no exito total.
- `pending-task.json` root con `tasks_pending` es soportado o rechazado con error claro en UI.
- `repo_root` equivocado muestra diagnostico con ruta esperada, ruta real y cantidad de artifacts detectados.
- Reintento tras 5xx ADO termina en `succeeded` sin duplicar tareas.

## 11. Fases de implementacion

### Fase 0 - Hotfix de visibilidad (0.5 dia)

- Agregar endpoint/diagnostico para ADO-167 que muestre: `pending-task.json`, `status`, `task_ado_id`, `payload_sha256`, `SystemLog` y link ADO.
- Cambiar UI para que un consumed muestre "ya creado como ADO-172" en vez de parecer pendiente.
- Loggear `repo_root` y `operation_id` en cada create/publish.

### Fase 1 - Correccion de comentarios (1 dia)

- Hacer que `post_comment()` no oculte errores.
- Exigir `comment_id` o verificacion.
- Mapear `html_output_path` y `completion_source` en ORM.
- Tests de publish fallido, replay y verificacion.

### Fase 2 - Outbox de tareas (2-3 dias)

- Crear `ado_write_operations`.
- Convertir `create_child_task` para encolar y ejecutar con estado durable.
- Marcar `pending-task.json` consumido solo tras verificacion.
- Upsert inmediato de Task creada en `tickets`.

### Fase 3 - Watcher robusto (1-2 dias)

- Eliminar self-HTTP como mecanismo principal.
- No cerrar Modo A cuando auto-create deja errores sin operacion retryable.
- Soportar `.stacky-done.json` como fuente principal y mtime como fallback.

### Fase 4 - Reconciliacion y UI (2 dias)

- Job de reconciliacion.
- Vista "Publicaciones ADO".
- Botones de retry/rescate.
- Alertas para bloqueadas/dead-letter.

### Fase 5 - Contratos de agente (1 dia)

- Versionar `pending-task.json`.
- Definir contrato unico para una Task y para multiples Tasks.
- Instruir agentes a escribir atomico, marcador done y SHA.

## 12. Criterio de aceptacion final

El plan queda completo cuando, para cualquier ADO ID:

- Si el agente escribe todos los archivos requeridos, aparece una operacion ADO trazable.
- Si ADO crea la Task/comentario, Stacky guarda ID y verificacion.
- Si ADO no responde o rechaza, Stacky deja retry/bloqueo visible y no marca falso exito.
- Si se re-ejecuta el mismo output, Stacky no duplica y muestra evidencia.
- Si se re-ejecuta con contenido nuevo, Stacky pide/ejecuta politica explicita.
- La UI local y la DB reflejan inmediatamente las tareas creadas, sin esperar un sync incierto.

