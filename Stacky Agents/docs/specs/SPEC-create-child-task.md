# SPEC-create-child-task — Creación de Task hija desde pending-task.json

**Versión:** 1.0.0
**Fecha:** 2026-05-15
**Autor:** Stacky Tool Architect (SDD)
**Branch:** fix/funcional-analyst-auto-publish
**Fase:** 2 del desacoplamiento del Agente Funcional

---

## 1. Identidad del Feature

| Campo | Valor |
|---|---|
| Nombre | Create Child Task from pending-task.json |
| Objetivo | Consumir el `pending-task.json` que el Agente Funcional v1.2.0 escribe en disco y crear la Task hija en ADO (con adjunto del plan de pruebas) desde la UI de Stacky, sin intervención manual del operador en ADO. |
| Alcance | Backend: extensión de `AdoClient` + endpoint nuevo en `tickets.py`. Frontend: componente `CreateChildTaskButton` + integración en `TicketBoard`/`TicketGraphView`. |
| Fuera de scope | Creación automática (sin gate del operador). Soporte multi-Epic simultáneo en un solo POST. Locking distribuido para despliegues multi-proceso. Notificación push al completar (solo invalidación de queries React Query). Modificación del flujo Fase 1 (el agente sigue escribiendo el archivo, no cambia). |

---

## 2. Actores y Permisos

| Actor | Rol | Precondición |
|---|---|---|
| Operador Stacky | Inicia la creación de la Task | Acceso a la UI de Stacky, PAT con permisos `vso.work_write` en ADO |
| Agente Funcional v1.2.0 | Productor del `pending-task.json` | Solo escribe el archivo — no interactúa con este flujo |
| Backend Stacky | Ejecutor de la cadena create → upload → link | ADO PAT configurado en `backend/.env` o `Tools/PAT-ADO` |

**Permisos ADO mínimos requeridos por el PAT:**
- `vso.work_write` — crear work items y editar relaciones
- `vso.work` — leer work items (para verificar Epic)
- `vso.workitemsearch` — opcional, no requerido
- Upload de adjuntos: incluido en `vso.work_write`

---

## 3. Contratos de Entrada: Schema de `pending-task.json`

El `pending-task.json` es el **contrato entre el Agente Funcional y Stacky**. Su schema es inmutable desde Stacky — el agente lo produce, Stacky lo consume.

```json
{
  "generated_at": "2026-05-15T10:30:00",
  "generated_by": "AnalistaFuncional v1.2.0",
  "epic_id": "149",
  "rf_id": "RF-001",
  "target_state": "Technical review",
  "title": "RF-001 — Gestión de perfiles de usuario",
  "description_html": "<h2>Análisis Funcional</h2><p>...</p>",
  "plan_de_pruebas_path": "output/tickets/epic-149/rf-001-gestion-perfiles/plan-de-pruebas.md",
  "parent_link_type": "System.LinkTypes.Hierarchy-Reverse",
  "status": "pending_manual_creation"
}
```

**Campos obligatorios para que Stacky procese el archivo:**

| Campo | Tipo | Descripción |
|---|---|---|
| `generated_at` | string (ISO 8601) | Timestamp de generación |
| `generated_by` | string | Identificador del agente productor |
| `epic_id` | string | ID del Epic en ADO (sin prefijo "ADO-") |
| `rf_id` | string | Identificador del RF (RF-XXX) |
| `title` | string | Título de la Task a crear en ADO |
| `description_html` | string | HTML del análisis funcional para el campo Description de ADO |
| `plan_de_pruebas_path` | string | Ruta relativa (desde raíz del repo) al `plan-de-pruebas.md` |
| `parent_link_type` | string | Tipo de link ADO — debe ser `"System.LinkTypes.Hierarchy-Reverse"` |
| `status` | string | Estado del archivo — debe ser `"pending_manual_creation"` para ser procesable |

**Campos que Stacky agrega tras consumir:**

| Campo | Tipo | Descripción |
|---|---|---|
| `consumed_at` | string (ISO 8601) | Timestamp de consumo exitoso |
| `task_ado_id` | integer | ID de la Task creada en ADO |
| `attachment_id` | string o null | ID del adjunto subido en ADO |
| `operator_reason` | string | Motivo del operador registrado en auditoría |

---

## 4. Pre-condiciones del Sistema

Para que el endpoint `POST /api/tickets/by-ado/{epic_ado_id}/create-child-task` pueda ejecutarse correctamente:

1. El `pending-task.json` existe en la ruta especificada por `pending_task_path`.
2. El archivo tiene `status == "pending_manual_creation"` (no `consumed_at`).
3. El `epic_ado_id` en la URL coincide con `pending-task.json.epic_id` (validación cruzada).
4. El ADO PAT está configurado y tiene permisos `vso.work_write`.
5. El Epic con `epic_ado_id` existe y es accesible en ADO.
6. El archivo `plan-de-pruebas.md` existe en la ruta indicada por `plan_de_pruebas_path` (si no existe, se omite el adjunto y se registra en `actions` con `ok: false, reason: "ATTACHMENT_FILE_NOT_FOUND"`).

---

## 5. Criterios de Aceptación

### CA-01 — Creación exitosa de Task hija en ADO

**DADO** un Epic con `ado_id=149` en ADO
Y un `pending-task.json` válido en `Agentes/outputs/epic-149/rf-001-slug/pending-task.json` con `status=pending_manual_creation`
Y un `plan-de-pruebas.md` presente en la ruta indicada por `plan_de_pruebas_path`

**CUANDO** el operador invoca `POST /api/tickets/by-ado/149/create-child-task` con body `{ "pending_task_path": "Agentes/outputs/epic-149/rf-001-slug/pending-task.json" }`

**ENTONCES**:
- Se llama a `_apis/wit/workitems/$Task` con JSON Patch que incluye los campos `System.Title`, `System.Description`, y la relación `System.LinkTypes.Hierarchy-Reverse` al Epic padre.
- La Task se crea exitosamente en ADO con estado inicial `"Technical review"`.
- La respuesta tiene `ok: true`, `task_ado_id` con el ID real de ADO, `task_url` válida, `pending_task_consumed: true`.
- El `pending-task.json` en disco se actualiza con `consumed_at`, `task_ado_id`, y `attachment_id`.

**Mapea a:** TU-01

---

### CA-02 — Adjunto del plan de pruebas subido y vinculado

**DADO** la misma pre-condición de CA-01 con `plan-de-pruebas.md` presente

**CUANDO** la Task se crea exitosamente (CA-01 cumplido)

**ENTONCES**:
- Se llama a `_apis/wit/attachments?fileName=plan-de-pruebas.md` con el contenido del archivo en stream binario.
- ADO devuelve una URL de adjunto (`attachment_url`).
- Se llama PATCH al work item de la Task agregando la relación `AttachedFile` con la `attachment_url`.
- En la respuesta, `attachment_id` no es null.
- El `actions` incluye `{ "action": "upload_attachment", "ok": true }` y `{ "action": "link_attachment", "ok": true }`.

**Mapea a:** TU-02

---

### CA-03 — pending-task.json se marca como consumido tras éxito

**DADO** que CA-01 y CA-02 completaron sin error

**CUANDO** el endpoint devuelve `ok: true`

**ENTONCES**:
- El archivo `pending-task.json` en disco contiene `consumed_at` (ISO 8601) y `task_ado_id` (entero).
- El campo `status` del archivo pasa a ser `"consumed"`.
- `GET /api/tickets/by-ado/149/pending-tasks` ya no lista ese RF como pendiente.

**Mapea a:** TU-03

---

### CA-04 — Idempotencia: segunda invocación no recrea la Task

**DADO** que el `pending-task.json` ya fue consumido (tiene `consumed_at` y `task_ado_id`)

**CUANDO** el operador invoca el endpoint nuevamente con el mismo `pending_task_path`

**ENTONCES**:
- El endpoint devuelve HTTP 200 con `ok: true`, `task_ado_id` del valor previo, `pending_task_consumed: true`.
- **No** se llama a ningún endpoint de ADO (ni create, ni upload, ni link).
- El body de respuesta incluye `idempotent: true` y `reason: "PENDING_TASK_ALREADY_CONSUMED"`.
- Ninguna nueva entrada en `system_logs` como `trigger=create_child_task` (solo se registra la detección de idempotencia).

**Nota de garantía:** La comprobación de `consumed_at` se realiza dentro de un lock de archivo OS-level. En despliegue single-process Flask, esto garantiza exclusión mutua. En multi-proceso, el degraded state es documentado: puede haber una ventana de race hasta que el lock sea distribuido.

**Mapea a:** TU-04

---

### CA-05 — dry_run no toca ADO

**DADO** un `pending-task.json` válido en estado pendiente

**CUANDO** el operador invoca el endpoint con `{ "pending_task_path": "...", "dry_run": true }`

**ENTONCES**:
- No se realiza ninguna llamada a ADO (`create_work_item`, `upload_attachment`, `link_attachment_to_work_item` no se invocan).
- El archivo `pending-task.json` no se modifica.
- La respuesta tiene `ok: true, dry_run: true`.
- El campo `actions` lista el plan de acciones que se ejecutarían: `[{ "action": "create_work_item", "would_call": "..." }, { "action": "upload_attachment", ... }, { "action": "link_attachment", ... }]`.
- El campo `pending_task_consumed: false`.

**Mapea a:** TU-05

---

### CA-06 — Rollback / degraded state ante fallo parcial

**DADO** que la Task se creó exitosamente en ADO (CA-01 ok) pero la subida del adjunto falla (ADO devuelve 5xx o el archivo `plan-de-pruebas.md` no existe)

**CUANDO** el endpoint intenta ejecutar `upload_attachment`

**ENTONCES**:
- La Task creada en ADO **no se revierte** (ADO no provee transacciones atómicas para work items). Esto es el degraded state documentado.
- La respuesta tiene `ok: false`, `task_ado_id` con el ID real (la Task SÍ existe), `pending_task_consumed: false`.
- El `actions` lista: `{ "action": "create_work_item", "ok": true, "task_ado_id": NNN }`, `{ "action": "upload_attachment", "ok": false, "reason": "ATTACHMENT_UPLOAD_FAILED" }`.
- El `pending-task.json` **no** se marca como consumido (para permitir reintento).
- Un `SystemLog` con `level=WARNING`, `source=create_child_task`, `action=partial_failure` registra el `task_ado_id` creado para facilitar reconciliación manual.
- El campo `human_action_required` en la respuesta indica: `"Task ADO-NNN creada; subida de adjunto falló. Revisar plan-de-pruebas.md y reintentar, o adjuntar manualmente en ADO-NNN."`.

**Mapea a:** TU-06

---

### CA-07 — operator_reason persiste en SystemLog y en comentario de la Task

**DADO** una invocación exitosa con `{ "pending_task_path": "...", "operator_reason": "Revisado y aprobado por Product Owner" }`

**CUANDO** la Task se crea en ADO

**ENTONCES**:
- El `operator_reason` se persiste en `SystemLog.context_json` (campo `operator_reason`).
- En ADO, el comentario de la Task recién creada incluye el texto del `operator_reason` (vía una llamada POST a `_apis/wit/workitems/{id}/comments` o incluyéndolo en el `System.Description` como sección final).
- **Nota de implementación:** Se agrega como comentario separado para no contaminar el HTML funcional del Description.

**Mapea a:** TU-07

---

### CA-08 — Header X-Completion-Source queda registrado en auditoría

**DADO** que el frontend envía el header `X-Completion-Source: manual_ui` en el POST

**CUANDO** el endpoint procesa la solicitud

**ENTONCES**:
- El `SystemLog` registrado contiene `completion_source: "manual_ui"`.
- Si el header está ausente, el valor default es `"manual"`.

**Mapea a:** TU-08

---

### CA-09 — Retry con backoff para 429/5xx de ADO

**DADO** que ADO devuelve HTTP 429 (Too Many Requests) o un 5xx en cualquier llamada de la cadena

**CUANDO** el `AdoClient` recibe ese error

**ENTONCES**:
- El cliente reintenta la llamada hasta 3 veces con backoff exponencial: 1s → 2s → 4s.
- Si ADO devuelve un header `Retry-After`, se respeta ese valor (con un máximo de 30s).
- Si los 3 intentos agotan, se eleva `AdoApiError` con `correlation_id` UUID y el código HTTP original.
- La respuesta del endpoint incluye `correlation_id` para trazabilidad.
- Se registra en logs: `logger.warning("ado_client", "retry_exhausted", ...)`.

**Mapea a:** TU-09

---

### CA-10 — Schema inválido del pending-task.json → 400 sin tocar ADO

**DADO** un `pending-task.json` con campos faltantes (ej: sin `title`, sin `epic_id`, o `parent_link_type` con valor incorrecto)

**CUANDO** el endpoint recibe el `pending_task_path`

**ENTONCES**:
- El endpoint devuelve HTTP 400 con `{ "ok": false, "error": "PENDING_TASK_SCHEMA_INVALID", "missing_fields": ["title", "epic_id"], "message": "..." }`.
- No se realiza ninguna llamada a ADO.
- El `pending-task.json` no se modifica.

**Casos específicos de error de schema:**
- `PENDING_TASK_FILE_NOT_FOUND`: el archivo no existe en la ruta indicada.
- `PENDING_TASK_SCHEMA_INVALID`: campos requeridos ausentes o tipos incorrectos.
- `PENDING_TASK_EPIC_MISMATCH`: `pending-task.json.epic_id` != `epic_ado_id` de la URL.

**Mapea a:** TU-10

---

### CA-11 — UI lista pending-tasks y condiciona visibilidad del botón

**DADO** un Epic con `ado_id=149` que tiene 2 RFs con `pending-task.json` en estado `pending_manual_creation` y 1 RF ya consumido

**CUANDO** la vista `TicketBoard` o `TicketGraphView` renderiza el card del Epic

**ENTONCES**:
- El componente `CreateChildTaskButton` llama a `GET /api/tickets/by-ado/149/pending-tasks`.
- La respuesta lista 2 items pendientes (no el consumido).
- El botón se muestra con la etiqueta "Crear Tasks en ADO (2 pendientes)".
- Si todos los pending-tasks están consumidos (count=0), el botón **no se muestra**.
- Si el endpoint devuelve error (ej: 500), el botón se muestra con estado de error pero no bloquea el render del card.

**Mapea a:** TU-11

---

### CA-12 — Tras crear exitoso desde UI, refresca listado y queries de tickets

**DADO** que el operador creó una Task exitosamente desde `CreateChildTaskButton`

**CUANDO** el POST retorna `ok: true`

**ENTONCES**:
- Se invalidan las React Query keys: `["pending-tasks", epicAdoId]`, `["tickets"]`, `["tickets-hierarchy"]`.
- El listado de pending-tasks se actualiza (el RF creado ya no aparece como pendiente).
- Si todos los RFs del Epic fueron procesados, el botón desaparece.
- Se muestra un toast de éxito con `task_ado_id` y `task_url`.

**Mapea a:** TU-12

---

## 6. Contratos de API

### 6.1 `GET /api/tickets/by-ado/{epic_ado_id}/pending-tasks`

**Response 200:**
```json
{
  "ok": true,
  "epic_ado_id": 149,
  "pending_tasks": [
    {
      "rf_id": "RF-001",
      "title": "RF-001 — Gestión de perfiles",
      "pending_task_path": "Agentes/outputs/epic-149/rf-001-slug/pending-task.json",
      "generated_at": "2026-05-15T10:30:00",
      "plan_de_pruebas_path": "output/tickets/epic-149/rf-001-slug/plan-de-pruebas.md",
      "plan_exists": true,
      "status": "pending_manual_creation"
    }
  ],
  "total_pending": 1,
  "total_consumed": 2
}
```

**Response 404:** Epic no encontrado en BD local.

**Response 200 con `total_pending: 0`:** No hay pending-tasks (no devuelve 404 — permite que la UI condicione el botón).

---

### 6.2 `POST /api/tickets/by-ado/{epic_ado_id}/create-child-task`

**Request body:**
```json
{
  "pending_task_path": "Agentes/outputs/epic-149/rf-001-slug/pending-task.json",
  "operator_reason": "Revisado en daily, listo para técnico",
  "dry_run": false
}
```

| Campo | Tipo | Obligatorio | Default |
|---|---|---|---|
| `pending_task_path` | string | Sí | — |
| `operator_reason` | string | No | `""` |
| `dry_run` | boolean | No | `false` |

**Response 200 — éxito:**
```json
{
  "ok": true,
  "dry_run": false,
  "epic_ado_id": 149,
  "task_ado_id": 1234,
  "task_url": "https://dev.azure.com/org/project/_workitems/edit/1234",
  "attachment_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "actions": [
    { "action": "create_work_item", "ok": true, "task_ado_id": 1234 },
    { "action": "upload_attachment", "ok": true, "attachment_id": "xxx..." },
    { "action": "link_attachment", "ok": true },
    { "action": "post_comment", "ok": true }
  ],
  "pending_task_consumed": true,
  "idempotent": false,
  "correlation_id": "uuid"
}
```

**Response 200 — idempotente:**
```json
{
  "ok": true,
  "dry_run": false,
  "epic_ado_id": 149,
  "task_ado_id": 1234,
  "task_url": "https://dev.azure.com/org/project/_workitems/edit/1234",
  "attachment_id": null,
  "actions": [],
  "pending_task_consumed": true,
  "idempotent": true,
  "reason": "PENDING_TASK_ALREADY_CONSUMED",
  "correlation_id": "uuid"
}
```

**Response 200 — dry_run:**
```json
{
  "ok": true,
  "dry_run": true,
  "epic_ado_id": 149,
  "task_ado_id": null,
  "task_url": null,
  "attachment_id": null,
  "actions": [
    { "action": "create_work_item", "would_call": "POST _apis/wit/workitems/$Task", "payload_preview": { "title": "RF-001 — ...", "parent": 149 } },
    { "action": "upload_attachment", "would_call": "POST _apis/wit/attachments?fileName=plan-de-pruebas.md", "file_exists": true },
    { "action": "link_attachment", "would_call": "PATCH work_item/{task_id}/relations/-" }
  ],
  "pending_task_consumed": false,
  "correlation_id": "uuid"
}
```

**Response 400 — schema inválido:**
```json
{
  "ok": false,
  "error": "PENDING_TASK_SCHEMA_INVALID",
  "missing_fields": ["title"],
  "message": "El campo 'title' es obligatorio en pending-task.json",
  "correlation_id": "uuid"
}
```

**Response 200 — fallo parcial (Task creada, adjunto falló):**
```json
{
  "ok": false,
  "dry_run": false,
  "epic_ado_id": 149,
  "task_ado_id": 1234,
  "task_url": "https://dev.azure.com/org/project/_workitems/edit/1234",
  "attachment_id": null,
  "actions": [
    { "action": "create_work_item", "ok": true, "task_ado_id": 1234 },
    { "action": "upload_attachment", "ok": false, "reason": "ATTACHMENT_UPLOAD_FAILED", "detail": "HTTP 503 from ADO" }
  ],
  "pending_task_consumed": false,
  "human_action_required": "Task ADO-1234 creada; subida de adjunto falló. Reintentar o adjuntar plan-de-pruebas.md manualmente en ADO-1234.",
  "correlation_id": "uuid"
}
```

---

### 6.3 JSON Patch para `create_work_item`

El body enviado a `POST /_apis/wit/workitems/$Task?api-version=7.1`:

```json
[
  { "op": "add", "path": "/fields/System.Title", "value": "RF-001 — Título" },
  { "op": "add", "path": "/fields/System.Description", "value": "<h2>...</h2>" },
  { "op": "add", "path": "/fields/System.State", "value": "Technical review" },
  { "op": "add", "path": "/relations/-", "value": {
    "rel": "System.LinkTypes.Hierarchy-Reverse",
    "url": "https://dev.azure.com/{org}/{project}/_apis/wit/workitems/{epic_ado_id}",
    "attributes": { "comment": "Task hija del Epic creada por Stacky Agents" }
  }}
]
```

**Content-Type del request:** `application/json-patch+json`

---

### 6.4 TypeScript interfaces (frontend)

```typescript
export interface PendingTaskItem {
  rf_id: string;
  title: string;
  pending_task_path: string;
  generated_at: string;
  plan_de_pruebas_path: string;
  plan_exists: boolean;
  status: "pending_manual_creation" | "consumed";
}

export interface ListPendingTasksResponse {
  ok: boolean;
  epic_ado_id: number;
  pending_tasks: PendingTaskItem[];
  total_pending: number;
  total_consumed: number;
}

export interface CreateChildTaskAction {
  action: string;
  ok?: boolean;
  task_ado_id?: number | null;
  attachment_id?: string | null;
  reason?: string | null;
  would_call?: string;
  payload_preview?: Record<string, unknown>;
  file_exists?: boolean;
  detail?: string;
}

export interface CreateChildTaskResponse {
  ok: boolean;
  dry_run: boolean;
  epic_ado_id: number;
  task_ado_id: number | null;
  task_url: string | null;
  attachment_id: string | null;
  actions: CreateChildTaskAction[];
  pending_task_consumed: boolean;
  idempotent?: boolean;
  reason?: string;
  human_action_required?: string;
  correlation_id: string;
  error?: string;
  missing_fields?: string[];
  message?: string;
}
```

---

## 7. Invariantes

### 7.1 Idempotencia
La presencia de `consumed_at` en el JSON del archivo en disco es la fuente de verdad. La verificación se realiza bajo lock de archivo OS-level (`portalocker` o equivalente) para prevenir race conditions en un proceso Flask single-threaded o con workers Gunicorn (un worker → sin problema; multi-worker → degraded, documentado).

**Degraded state para multi-proceso:** Si Stacky corre con múltiples workers de Gunicorn, existe una ventana de race de ~1ms entre la lectura de `consumed_at` y su escritura. En ese escenario, dos Tasks podrían crearse para el mismo RF. Solución futura: mover el lock a Redis o a una tabla de BD con unique constraint.

### 7.2 Atomicidad
ADO no provee transacciones atómicas entre `create_work_item`, `upload_attachment`, y `link_attachment`. El flujo es best-effort con degraded state documentado (CA-06). El `pending-task.json` solo se marca `consumed` si `create_work_item` Y (`upload_attachment` + `link_attachment`) completan sin error. Si solo falla el adjunto, la Task existe en ADO pero el archivo no se marca consumido — el operador puede reintentar.

### 7.3 No-destrucción del contrato Fase 1
El agente funcional sigue escribiendo `pending-task.json` sin cambios. Stacky es el consumidor exclusivo. Si Stacky escribe campos adicionales (`consumed_at`, etc.), los preserva al releer el archivo — usa `json.load` → update dict → `json.dump`, no reescritura desde cero.

### 7.4 Auditoría
Toda ejecución del endpoint (incluyendo dry_run, idempotente, y fallos) genera una entrada en `SystemLog` con:
- `source="create_child_task"`
- `trigger="create_child_task"`
- `completion_source` desde el header `X-Completion-Source` (default `"manual"`)
- `correlation_id` UUID generado por el endpoint

### 7.5 No-publicación automática sin gate
El endpoint requiere invocación explícita del operador (HTTP POST). No existe ningún watcher de filesystem que auto-consuma `pending-task.json`.

---

## 8. Casos de Error Nombrados

| Código de error | HTTP | Causa | Acción requerida |
|---|---|---|---|
| `PENDING_TASK_FILE_NOT_FOUND` | 400 | El archivo en `pending_task_path` no existe | Verificar ruta; re-ejecutar el Agente Funcional |
| `PENDING_TASK_SCHEMA_INVALID` | 400 | Campos requeridos ausentes o tipos incorrectos | Verificar el pending-task.json y re-ejecutar el agente |
| `PENDING_TASK_EPIC_MISMATCH` | 400 | `epic_id` en el JSON != `epic_ado_id` de la URL | Verificar que se está usando el endpoint correcto para el Epic |
| `PENDING_TASK_ALREADY_CONSUMED` | 200 (idempotente) | `consumed_at` ya presente en el archivo | No acción; retorna `task_ado_id` previo |
| `EPIC_NOT_FOUND_IN_ADO` | 502 | ADO devuelve 404 al verificar el Epic | Verificar `epic_ado_id` y sincronización ADO |
| `ADO_CREATE_REJECTED_BY_POLICY` | 502 | ADO devuelve 403 o error de política al crear la Task | Verificar permisos del PAT y area path del proyecto |
| `ATTACHMENT_FILE_NOT_FOUND` | 200 (parcial) | `plan_de_pruebas_path` no existe en disco | Verificar que el agente generó el plan; adjuntar manualmente |
| `ATTACHMENT_UPLOAD_FAILED` | 200 (parcial) | ADO devuelve error al subir el adjunto | Reintentar o adjuntar manualmente en ADO |
| `ADO_RETRY_EXHAUSTED` | 502 | 3 reintentos con backoff agotados por 429/5xx | Verificar estado de ADO; esperar y reintentar |
| `ADO_CONFIG_MISSING` | 503 | PAT no configurado | Setear `ADO_PAT` o llenar `Tools/PAT-ADO` |

---

## 9. Métricas Observables

| Métrica | Cómo se mide |
|---|---|
| `pending_tasks_consumed_count` | Suma de `SystemLog` con `action=create_child_task_succeeded` |
| `pending_tasks_partial_failure_count` | Suma de `SystemLog` con `action=partial_failure` |
| `ado_create_retry_count` | Suma de eventos `retry_decision` en logs |
| `pending_task_idempotent_count` | Suma de respuestas con `idempotent=true` |
| `time_pending_to_consumed_p50` | `consumed_at - generated_at` por RF (calculable desde los JSONs) |
| `attachment_success_rate` | `link_attachment ok / create_work_item ok` |

---

## 10. Plan de Tests (TU-XXX)

Cada TU mapea 1-a-1 con un CA. Los tests de backend son pytest; los de frontend son Vitest + Testing Library.

### Backend — Unit Tests (`tests/test_ado_client_extensions.py`)

| ID | Descripción | Mock |
|---|---|---|
| TU-01a | `AdoClient.create_work_item` construye JSON Patch correcto con link Hierarchy-Reverse | `urllib.request.urlopen` mockeado con respuesta 200 |
| TU-01b | `create_work_item` pasa `Content-Type: application/json-patch+json` | Verificar headers del request |
| TU-02a | `upload_attachment` hace POST con stream binario y `fileName` correcto en querystring | Mock response con `id` y `url` |
| TU-02b | `link_attachment_to_work_item` hace PATCH con `rel: AttachedFile` y la URL correcta | Mock response 200 |
| TU-09a | `_request_with_retry` reintenta 3 veces en 429 con backoff | Mock que devuelve 429 dos veces, luego 200 |
| TU-09b | Respeta header `Retry-After` (máx 30s clampeado) | Mock con `Retry-After: 60` → clampea a 30 |
| TU-09c | Eleva `AdoApiError` con `correlation_id` tras agotar reintentos | Mock que siempre devuelve 503 |

### Backend — Integration Tests (`tests/test_create_child_task_endpoint.py`)

| ID | Descripción | Setup |
|---|---|---|
| TU-01 | POST exitoso: crea Task, sube adjunto, linkea, marca consumido | Fixtures: pending-task.json válido + plan-de-pruebas.md + ADO mock |
| TU-03 | Tras éxito: pending-task.json contiene consumed_at y task_ado_id | Leer archivo tras request |
| TU-04 | Segunda invocación con mismo archivo devuelve idempotent=true sin llamar ADO | Contar llamadas a ADO mock |
| TU-05 | dry_run=true: no llama ADO, no modifica archivo, devuelve actions con would_call | Assert 0 llamadas ADO |
| TU-06 | upload_attachment falla: task creada, pending_task_consumed=false, human_action_required presente | Mock: create_work_item ok, upload 503 |
| TU-07 | operator_reason en SystemLog y en comentario ADO | Verificar SystemLog.context_json |
| TU-08 | Header X-Completion-Source: manual_ui → registrado en SystemLog | Verificar campo completion_source |
| TU-10a | Schema inválido (title faltante) → 400, sin llamadas ADO | Fixture: pending-task.json sin title |
| TU-10b | Archivo no encontrado → 400 con PENDING_TASK_FILE_NOT_FOUND | No crear el archivo |
| TU-10c | epic_id mismatch → 400 con PENDING_TASK_EPIC_MISMATCH | epic_id="999" en JSON, URL con 149 |

### Backend — Unit Tests para `list_pending_tasks` (`tests/test_list_pending_tasks.py`)

| ID | Descripción |
|---|---|
| TU-11a | Lista solo los pending-tasks con status=pending_manual_creation |
| TU-11b | No lista los que tienen consumed_at |
| TU-11c | Devuelve total_pending y total_consumed correctos |
| TU-11d | Devuelve plan_exists=false si plan-de-pruebas.md no existe |

### Frontend — Component Tests (`src/components/__tests__/CreateChildTaskButton.test.tsx`)

| ID | Descripción |
|---|---|
| TU-11e | No renderiza el botón cuando total_pending=0 |
| TU-11f | Renderiza el botón con label correcto cuando total_pending>0 |
| TU-12 | Tras POST exitoso: invalida queries y muestra toast de éxito |
| TU-FC-01 | Modal muestra lista de RFs con preview del payload |
| TU-FC-02 | Checkbox dry_run disponible en modal |
| TU-FC-03 | Error de red en POST muestra error en UI sin crashear |
| TU-FC-04 | Botón Crear Task deshabilitado mientras hay request en vuelo |

---

## 11. Notas de Implementación (Pre-decisiones para Fase 2)

### Backend
- `AdoClient.create_work_item` usa `Content-Type: application/json-patch+json` (diferente del `application/json` del resto de métodos). Se agrega overload en `_headers()`.
- El lock de archivo usa `fcntl.flock` en Linux/Mac y `msvcrt.locking` en Windows. Se abstrae en `_file_lock(path)` context manager.
- El endpoint vive en `tickets.py` bajo el blueprint `/tickets` para mantener consistencia con los endpoints `by-ado` existentes.
- `operator_reason` se agrega como comentario usando la API `POST _apis/wit/workitems/{id}/comments` si ADO lo soporta (ver `fetch_comments` existente que usa `7.1-preview.3`). Si falla, se degrada gracefully y se registra en `actions`.

### Frontend
- `CreateChildTaskButton` sigue el patrón de `FinishWorkButton`: modal + dry-run automático al abrir + doble confirmación.
- No usa doble confirmación (a diferencia de `FinishWorkButton`) porque el dry_run ya es la "preview" — solo un click "Crear Task en ADO".
- Los queries de pending-tasks se hacen con `useQuery` dentro del componente con key `["pending-tasks", epicAdoId]` y staleTime de 60 segundos.
- El componente se monta **solo** en cards de work_item_type === "epic".

### Credenciales ADO
El PAT necesario (`vso.work_write`) usa el mismo mecanismo de resolución ya implementado en `AdoClient._resolve_auth_header()`. No se requiere configuración adicional si el PAT actual ya tiene `vso.work_write`. Si el PAT solo tiene `vso.work` (read-only), las llamadas de creación fallarán con HTTP 403 → error `ADO_CREATE_REJECTED_BY_POLICY`.

**Verificación pre-implementación recomendada:**
```bash
# Verificar permisos del PAT actual (dry-run contra ADO)
curl -u :<PAT> "https://dev.azure.com/{org}/{project}/_apis/wit/workitems/$Task?api-version=7.1" \
  -X POST -H "Content-Type: application/json-patch+json" \
  -d '[{"op":"add","path":"/fields/System.Title","value":"[TEST] Stacky PAT check - DELETE ME"}]'
```

---

## 12. Diagrama de Flujo (Secuencia)

```
Operador (UI)
    │ click "Crear Task en ADO"
    │
    ▼
CreateChildTaskButton
    │ GET /api/tickets/by-ado/{epic_ado_id}/pending-tasks
    │ → muestra lista de RFs pendientes
    │
    │ Operador selecciona RF, escribe reason, click Confirmar
    │
    ▼
POST /api/tickets/by-ado/{epic_ado_id}/create-child-task
    │
    ├─ [1] Leer y validar pending-task.json (schema + idempotencia)
    │       → si consumed_at → return idempotent=true (sin tocar ADO)
    │
    ├─ [2] AdoClient.create_work_item(Task, fields, epic_ado_id)
    │       → JSON Patch con Title, Description, State, Hierarchy-Reverse link
    │       → retorna task_ado_id
    │
    ├─ [3] AdoClient.upload_attachment(plan_de_pruebas.md)
    │       → POST _apis/wit/attachments?fileName=plan-de-pruebas.md
    │       → retorna attachment_url
    │       → si falla: registrar degraded state, NO marcar consumed
    │
    ├─ [4] AdoClient.link_attachment_to_work_item(task_ado_id, attachment_url)
    │       → PATCH work item relations/-
    │
    ├─ [5] post_comment con operator_reason en la Task
    │
    ├─ [6] Marcar pending-task.json como consumed (bajo file lock)
    │       consumed_at = now, task_ado_id = NNN, status = "consumed"
    │
    ├─ [7] SystemLog(source=create_child_task, trigger=create_child_task)
    │
    └─ [8] Return response con ok, task_ado_id, task_url, actions
    │
    ▼
CreateChildTaskButton
    │ toast de éxito con link a ADO
    │ invalidar ["pending-tasks", epicAdoId], ["tickets"], ["tickets-hierarchy"]
    │ re-render: si total_pending=0 → botón desaparece
```

---

*Fin de SPEC-create-child-task v1.0.0*
