# Plan 66 — Desatascador de tickets: visibilidad total de ejecutados + subida forzada de artifacts

> Versión: v1 | Estado: PROPUESTO | Fecha: 2026-06-22
> Autor: StackyArchitectaUltraEficientCode

---

## 1. Objetivo + KPI

El desatascador (`UnblockerPage`) es el fallback puntual del operador: cuando el agente produjo artifacts que no se autopublicaron, el operador los destrava a mano desde la UI. Hoy el board solo muestra tickets **en ejecución o con artifacts pendientes**. Si el agente terminó OK y el artifact ya fue consumido, el ticket desaparece del board. El operador queda sin superficie para subir manualmente un archivo alternativo (p. ej. una versión corregida del `comment.html` o un nuevo `pending-task.json` para forzar la creación de una task).

**Objetivo:** dar al operador visibilidad total de todos los tickets que alguna vez tuvieron ejecución, y permitirle subir forzadamente un artifact a cualquiera de ellos — incluyendo los ya completados — sin necesidad de re-correr el agente.

**KPIs (criterios binarios aceptados como DoD):**

| KPI | Criterio de aceptación |
|-----|------------------------|
| Visibilidad total | Tickets con última ejecución `completed`/`ok`/`done` y sin artifacts pendientes aparecen en el board con readiness `completed_ok` cuando `include_completed=true` (default) |
| Opt-out limpio | Con `include_completed=false`, el board es byte-idéntico al comportamiento anterior |
| Subida forzada universal | El file picker (input type=file) aparece en TODAS las cards (no solo `completed_ok`); llama la misma lógica que el drop-zone existente |
| Toggle informativo | El header muestra "Mostrar completados (N)" con el count real de `counts.completed_ok` |
| Tests verdes | `pytest test_unblocker_board.py -q` pasa sin falsos verdes (incluye casos UB-06, UB-07, UB-08) |
| TypeScript limpio | `tsc --noEmit` = 0 errores |

---

## 2. Por qué ahora / gap que cierra

### Gap verificado en código

**Backend `tickets.py:2448`:**
```python
# línea 2448 — filtro actual
if not (running or has_artifacts):
    continue
```

Consecuencia: un ticket cuyo agente terminó bien (`stacky_status="completed"` o última exec `status="completed"`) y cuyos artifacts ya fueron consumidos (`total_pending=0`, `comment.html` ausente, sin stale, sin parse errors) es `running=False` y `has_artifacts=False` → **invisible**.

La información para incluirlos YA EXISTE en `last_exec_by_ticket.get(t.id)` (construida en líneas 2391-2400). Solo falta usarla.

**Frontend `UnblockerPage.tsx:132` — `handleDrop`:**
La lógica de rescate forzado (drag-and-drop → `rescue_artifact` → `create-child-task` o `finish-work`) YA funciona mecánicamente. El backend `rescue_artifact` (línea 2594) escribe un archivo nuevo con `rescue_uploaded_at`, generando un SHA distinto al del original, lo que bypasea la idempotencia de `create-child-task` (línea 3728). El único problema es que las cards de tickets completados no aparecen, haciendo inaccesible el drop-zone.

**El file picker como fallback del drag-and-drop:** drag-and-drop es incómodo en algunos navegadores y contextos de SO. Un `<input type="file">` visible es la alternativa nativa del navegador — misma lógica de back, zero código nuevo de dominio.

### Rieles duros no afectados

- Los 3 runtimes de agente (Codex, Claude Code, Copilot) no cambian una línea. El cambio es puramente backend endpoint + UI de board.
- Human-in-the-loop: el operador sube el archivo manualmente. El sistema no autopublica nada nuevo.
- Mono-operador, sin auth: sin cambios.
- No degrada: `include_completed=false` = comportamiento previo exacto.

---

## 3. Principios y guardarraíles

1. **Default muestra todo:** `include_completed=true` por defecto → el operador no necesita configurar nada para ver los tickets completados. El toggle es opt-out, no opt-in.
2. **Cero lógica de rescate nueva:** `rescue_artifact` + `create-child-task` + `finish-work` ya funcionan; este plan solo expone la superficie de UI para tickets que antes eran invisibles.
3. **Cards `completed_ok` son solo drop-zone:** sin botones de acción automática (no hay artifact detectado, no hay task ni comment pendiente). Solo la caja de subida forzada.
4. **File picker en TODAS las cards:** la mejora del input visible no es exclusiva de `completed_ok`; aplica a todas para mejorar la DX del flujo de rescate.
5. **Backward compat de tipos:** el frontend comprueba `counts.completed_ok ?? 0` para soportar backends que no mandan ese campo (despliegue gradual).
6. **TDD estricto:** los tres casos nuevos (UB-06, UB-07, UB-08) se escriben ANTES de tocar `tickets.py`.

---

## 4. Fases

### F0 — Backend: incluir tickets con ejecución previa aunque estén completados

**Archivo:** `Stacky Agents/backend/api/tickets.py`
**Test primero:** `Stacky Agents/backend/tests/test_unblocker_board.py`

#### 4.0.1 Tests a agregar (TDD — escribir antes del fix)

```python
# UB-06: ticket completado (sin artifacts, sin running) → aparece con completed_ok
#        cuando include_completed=true (default)
def test_ub06_completed_ticket_visible_by_default(client, tmp_repo):
    """Ticket con última ejecución 'completed' y sin artifacts → completed_ok en el board."""
    from db import session_scope
    from models import Ticket, AgentExecution
    ticket_id = _seed_ticket(7006, work_item_type="Task", title="Task 7006 OK")
    with session_scope() as session:
        session.add(AgentExecution(
            ticket_id=ticket_id,
            agent_type="FunctionalAnalyst",
            status="completed",
        ))
    board = _get_board(client)  # include_completed omitido → default True
    it = _item(board, 7006)
    assert it is not None, "Ticket completado debe aparecer con include_completed=true"
    assert it["readiness"] == "completed_ok"
    assert it["total_pending"] == 0
    assert it["comment"]["exists"] is False


# UB-07: ticket completado → NO aparece con include_completed=false
def test_ub07_completed_ticket_excluded_when_flag_false(client, tmp_repo):
    """Con include_completed=false el board es byte-idéntico al comportamiento anterior."""
    from db import session_scope
    from models import Ticket, AgentExecution
    ticket_id = _seed_ticket(7007, work_item_type="Task", title="Task 7007 OK")
    with session_scope() as session:
        session.add(AgentExecution(
            ticket_id=ticket_id,
            agent_type="FunctionalAnalyst",
            status="completed",
        ))
    resp = client.get("/api/tickets/unblocker-board?include_completed=false")
    assert resp.status_code == 200
    board = resp.get_json()
    it = _item(board, 7007)
    assert it is None, "Ticket completado NO debe aparecer con include_completed=false"


# UB-08: orden — task_ready aparece antes que completed_ok en el mismo board
def test_ub08_order_task_ready_before_completed_ok(client, tmp_repo):
    """Tickets con readiness task_ready deben preceder a completed_ok en el orden del board."""
    from db import session_scope
    from models import Ticket, AgentExecution
    # Ticket completado (order=6)
    tid_ok = _seed_ticket(7008, work_item_type="Task", title="Task 7008 OK")
    with session_scope() as session:
        session.add(AgentExecution(
            ticket_id=tid_ok,
            agent_type="FunctionalAnalyst",
            status="completed",
        ))
    # Ticket con pending-task (order=1)
    _seed_ticket(7009, work_item_type="Epic", title="Epic 7009")
    _write_pending(tmp_repo, 7009, "RF-099", "orden", plan=True)

    board = _get_board(client)
    readiness_list = [it["readiness"] for it in board["items"] if it["ado_id"] in (7008, 7009)]
    assert readiness_list.index("task_ready") < readiness_list.index("completed_ok"), (
        "task_ready debe aparecer antes que completed_ok en el sort"
    )
```

**Comando de verificación:**
```
& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_unblocker_board.py" -q
```

#### 4.0.2 Cambios en `tickets.py`

**Cambio 1 — Query param `include_completed`**

En `unblocker_board()`, justo después de `project_name = _request_project_name()` (línea 2355):

```python
# Nuevo query param — default True (muestra completados por defecto, opt-out)
include_completed_str = request.args.get("include_completed", "true").lower()
include_completed = include_completed_str not in ("false", "0", "no")
```

**Cambio 2 — Agregar `completed_ok` al dict `counts`**

En la inicialización de `counts` (línea 2360-2363), agregar la clave:

```python
counts = {
    "running": 0, "comment_ready": 0, "task_ready": 0,
    "waiting_files": 0, "files_error": 0, "stale_consumed": 0,
    "completed_ok": 0,   # ← AGREGAR
}
```

**Cambio 3 — Ampliar el filtro de inclusión**

Reemplazar el filtro en línea 2448:

```python
# ANTES:
if not (running or has_artifacts):
    continue

# DESPUÉS:
has_prior_execution = last_exec_by_ticket.get(t.id) is not None
completed_statuses = {"completed", "ok", "done"}
last_ex = last_exec_by_ticket.get(t.id)
is_completed_ok = (
    has_prior_execution
    and not running
    and not has_artifacts
    and last_ex is not None
    and (last_ex.status or "").lower() in completed_statuses
)

if not (running or has_artifacts or (include_completed and is_completed_ok)):
    continue
```

NOTA: `last_exec_by_ticket` se construye en orden `asc` por `id` con last-wins (línea 2397-2400), por lo tanto `last_exec_by_ticket.get(t.id)` ya es la ejecución MÁS RECIENTE del ticket. No se requiere ninguna query adicional.

**Cambio 4 — Readiness para `completed_ok`**

En el bloque de asignación de readiness (actualmente termina en `else: readiness = "artifacts_idle"`, línea 2492-2493), agregar antes de ese else final:

```python
# Dentro del bloque de readiness, el flujo llega aquí cuando
# running=False, has_artifacts=False, is_completed_ok=True.
# Por construcción del filtro, si llegamos al else de readiness
# sin running ni artifacts, es porque is_completed_ok permitió pasar.
# Reemplazar el else final:
else:
    if is_completed_ok:
        readiness = "completed_ok"
    else:
        readiness = "artifacts_idle"
```

**Cambio 5 — Incrementar el counter de `completed_ok`**

En el bloque de contadores (líneas 2496-2506), agregar:

```python
elif readiness == "completed_ok":
    counts["completed_ok"] += 1
```

**Cambio 6 — `_order` dict: agregar posición 6 para `completed_ok`**

En línea 2542-2545:

```python
_order = {
    "files_error": 0, "task_ready": 1, "stale_consumed": 2,
    "comment_ready": 3, "waiting_files": 4, "artifacts_idle": 5,
    "completed_ok": 6,   # ← AGREGAR — siempre al final, detrás de idle
}
```

**Criterio binario F0:** `pytest test_unblocker_board.py -q` verde incluyendo UB-06, UB-07, UB-08. Ningún test previo (UB-01..UB-05 y resto) puede romperse.

---

### F1 — Frontend: tipos TypeScript actualizados

**Archivo:** `Stacky Agents/frontend/src/api/endpoints.ts`

No hay lógica nueva. Solo tipos.

**Cambio 1 — `UnblockerReadiness` union**

Línea 430-436:

```typescript
// ANTES:
export type UnblockerReadiness =
  | "task_ready"
  | "stale_consumed"
  | "comment_ready"
  | "waiting_files"
  | "artifacts_idle"
  | "files_error";

// DESPUÉS: agregar "completed_ok"
export type UnblockerReadiness =
  | "task_ready"
  | "stale_consumed"
  | "comment_ready"
  | "waiting_files"
  | "artifacts_idle"
  | "files_error"
  | "completed_ok";
```

**Cambio 2 — `UnblockerBoardResponse.counts`**

Líneas 513-520:

```typescript
// ANTES:
counts: {
  running: number;
  comment_ready: number;
  task_ready: number;
  waiting_files: number;
  files_error: number;
  stale_consumed: number;
};

// DESPUÉS: agregar completed_ok con optional para compat con backend viejo
counts: {
  running: number;
  comment_ready: number;
  task_ready: number;
  waiting_files: number;
  files_error: number;
  stale_consumed: number;
  completed_ok?: number;   // ← AGREGAR — optional: backend viejo no lo manda
};
```

**Criterio binario F1:** `tsc --noEmit` = 0 errores.

---

### F2 — Frontend: toggle + card `completed_ok` + file picker en card

**Archivos:** `Stacky Agents/frontend/src/pages/UnblockerPage.tsx` y `UnblockerPage.module.css`

#### 4.2.1 Cambios en `UnblockerPage.tsx`

**Cambio 1 — `READINESS_LABEL` y `READINESS_CLASS`**

Agregar a los mapas en líneas 26-42:

```typescript
const READINESS_LABEL: Record<UnblockerReadiness, string> = {
  task_ready: "Task lista para crear",
  stale_consumed: "⚠️ Task borrada en ADO — recrear",
  comment_ready: "Comentario listo para publicar",
  waiting_files: "Esperando archivos del agente",
  artifacts_idle: "Artifacts en disco",
  files_error: "⚠️ pending-task.json malformado",
  completed_ok: "Ejecutado OK — sin pendientes",   // ← AGREGAR
};

const READINESS_CLASS: Record<UnblockerReadiness, string> = {
  task_ready: styles.badgeTask,
  stale_consumed: styles.badgeError,
  comment_ready: styles.badgeComment,
  waiting_files: styles.badgeWaiting,
  artifacts_idle: styles.badgeIdle,
  files_error: styles.badgeError,
  completed_ok: styles.badgeCompleted,   // ← AGREGAR
};
```

**Cambio 2 — `handleFileSelect` en `UnblockerCard` (reutilización de lógica de drop)**

Dentro del componente `UnblockerCard`, después de `handleDrop` (línea 197), agregar el handler para el file picker. La lógica es idéntica a `handleDrop` pero recibe `FileList` en lugar de un `DragEvent`:

```typescript
const handleFileSelect = useCallback(async (fileList: FileList) => {
  if (!item.ado_id) return;
  const dropped = Array.from(fileList);
  if (dropped.length === 0) return;

  setBusy(true);
  setActionMessage("Leyendo archivo(s)...");
  try {
    const files = await Promise.all(
      dropped.map(async (file) => ({
        name: file.name,
        content: await file.text(),
      }))
    );
    const hasPending = files.some((f) => f.name.toLowerCase() === "pending-task.json");
    const hasComment = files.some((f) => f.name.toLowerCase().endsWith(".html"));
    const rescueRoot = hasComment && !hasPending ? null : artifactRoot;
    const rescue = await Tickets.rescueArtifact(item.ado_id, {
      artifact_type: "auto",
      files,
      project: activeProjectName,
      repo_root: rescueRoot,
    });
    if (!rescue.ok) {
      throw new Error(rescue.message || rescue.error || "No se pudo preparar el artifact.");
    }

    if (rescue.artifact_type === "pending_task" && rescue.pending_task_path) {
      setActionMessage("Artifact preparado. Creando Task...");
      const created = await Tickets.createChildTask(item.ado_id, {
        pending_task_path: rescue.pending_task_path,
        operator_reason: "Desatascador: creación desde archivo subido",
        project: activeProjectName,
        repo_root: rescue.repo_root || rescueRoot,
      });
      if (!created.ok) {
        throw new Error(created.message || created.error || "create-child-task falló");
      }
      setActionMessage(`Task creada: ADO-${created.task_ado_id}`);
    } else if (rescue.artifact_type === "comment" && rescue.html_output_path) {
      setActionMessage("Comentario preparado. Publicando...");
      const published = await Tickets.finishWork(item.ticket_id, {
        operator_reason: "Desatascador: publicación desde comment.html subido",
        publish_to_ado: true,
        html_output_path: rescue.html_output_path,
        force_publish: true,
        force_finish: true,
        cancel_active_execution: true,
      });
      if (!published.ok) {
        throw new Error("finish-work no pudo completar la publicación.");
      }
      setActionMessage("Comentario publicado.");
    } else {
      throw new Error("El backend no reconoció pending-task.json ni comment.html.");
    }
    onChanged();
  } catch (err) {
    setActionMessage((err as Error)?.message ?? "No se pudo procesar el archivo.");
  } finally {
    setBusy(false);
  }
}, [item.ado_id, item.ticket_id, activeProjectName, artifactRoot, onChanged]);
```

**Cambio 3 — File picker en el JSX de `UnblockerCard`**

El drop-zone actual (línea 331-333) queda como está. Agregar el file picker justo debajo:

```tsx
{/* Drop-zone existente sin cambios */}
<div className={styles.dropZone}>
  Arrastrá pending-task.json, plan-de-pruebas.md o comment.html para rescatar este ADO.
</div>

{/* File picker — fallback accesible del drag-and-drop */}
<label className={styles.filePicker}>
  <input
    type="file"
    multiple
    accept=".json,.html,.md"
    style={{ display: "none" }}
    onChange={(e) => {
      if (e.target.files && e.target.files.length > 0) {
        handleFileSelect(e.target.files);
        e.target.value = "";   // reset para permitir re-selección del mismo archivo
      }
    }}
    disabled={busy}
  />
  📁 Elegir archivo(s)
</label>
```

**Cambio 4 — Acciones de la card `completed_ok`**

En el bloque de acciones (líneas 311-330), el tramo `!isEpicWithPending && !hasStaleConsumed && !canPublishComment` actualmente muestra "Sin archivos listos todavía". Para `completed_ok` necesitamos un texto diferente. Reemplazar:

```tsx
{/* ANTES: */}
{!isEpicWithPending && !hasStaleConsumed && !canPublishComment && (
  <span className={styles.noAction}>
    Sin archivos listos todavía — refrescar cuando el agente termine.
  </span>
)}

{/* DESPUÉS: */}
{!isEpicWithPending && !hasStaleConsumed && !canPublishComment && (
  <span className={styles.noAction}>
    {item.readiness === "completed_ok"
      ? "No hay pendientes. Subí un archivo para forzar la creación/publicación."
      : "Sin archivos listos todavía — refrescar cuando el agente termine."}
  </span>
)}
```

**Cambio 5 — Toggle `includeCompleted` y pasarlo al endpoint**

En `UnblockerPage` (componente raíz, líneas 339-355), agregar el state:

```typescript
const [includeCompleted, setIncludeCompleted] = useState(true);
```

Modificar el `queryKey` y `queryFn` del `useQuery` para incluir el param:

```typescript
// queryKey: agregar includeCompleted
queryKey: ["unblocker-board", activeProjectName, artifactRoot, includeCompleted],

// queryFn: pasar include_completed al endpoint
queryFn: () => Tickets.unblockerBoard(activeProjectName, artifactRoot, includeCompleted),
```

Nota: el método `Tickets.unblockerBoard` vive en `endpoints.ts`. Agregar el tercer param opcional:

```typescript
// En endpoints.ts, función unblockerBoard (buscarla por nombre):
// Agregar parámetro opcional includeCompleted con default true,
// y pasarlo como query param: include_completed=false solo si es false
unblockerBoard(
  project?: string | null,
  repoRoot?: string | null,
  includeCompleted: boolean = true,
): Promise<UnblockerBoardResponse> {
  const params = new URLSearchParams();
  if (project) params.set("project", project);
  if (repoRoot) params.set("repo_root", repoRoot);
  if (!includeCompleted) params.set("include_completed", "false");
  return fetchJson(`/api/tickets/unblocker-board?${params}`);
}
```

NOTA: localizar la implementación actual de `unblockerBoard` en `endpoints.ts` y extenderla con el tercer parámetro. No reemplazar la firma completa si ya tiene lógica de params.

**Cambio 6 — Botón toggle en el header**

En el JSX de `UnblockerPage` (dentro del `<header className={styles.pageHeader}>`, junto al botón "↻ Refrescar", línea 373-380):

```tsx
<button
  className={styles.refreshBtn}
  onClick={() => refetch()}
  disabled={isFetching}
>
  {isFetching ? "Refrescando…" : "↻ Refrescar"}
</button>

{/* Toggle includeCompleted — nuevo botón */}
<button
  className={`${styles.refreshBtn} ${includeCompleted ? styles.toggleActive : ""}`}
  onClick={() => setIncludeCompleted((v) => !v)}
  title={includeCompleted ? "Ocultar tickets ya completados" : "Mostrar tickets ya completados"}
>
  {includeCompleted
    ? `Ocultar completados (${counts?.completed_ok ?? 0})`
    : "Mostrar completados"}
</button>
```

**Cambio 7 — Counts bar: mostrar `completed_ok`**

En el bloque de counts (líneas 431-446), agregar la pastilla:

```tsx
{(counts?.completed_ok ?? 0) > 0 && includeCompleted && (
  <span className={styles.countCompleted}>
    {counts!.completed_ok} completado(s)
  </span>
)}
```

#### 4.2.2 Cambios en `UnblockerPage.module.css`

Agregar al final del archivo:

```css
/* completed_ok — verde tenue, claramente "sin urgencia" */
.badgeCompleted { background: #052e16; color: #86efac; }
.card[data-readiness="completed_ok"] { border-left: 4px solid #86efac; }
.countCompleted { color: #86efac; border-color: #14532d !important; }

/* toggle activo */
.toggleActive {
  border-color: #166534 !important;
  background: #052e16 !important;
  color: #bbf7d0 !important;
}

/* file picker label — apariencia de botón secundario */
.filePicker {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
  border-radius: 6px;
  border: 1px dashed var(--border, #334155);
  background: transparent;
  color: var(--text-muted, #94a3b8);
  font-size: 12px;
  cursor: pointer;
  user-select: none;
}
.filePicker:hover { border-color: #38bdf8; color: #e2e8f0; }
```

**Criterio binario F2:** `tsc --noEmit` = 0 errores.

---

### F3 — Frontend: file picker en TODAS las cards (no solo `completed_ok`)

Este cambio es consecuencia de F2. El file picker agregado en `UnblockerCard` (Cambio 3 de F2) ya está dentro del componente genérico, por lo que **se aplica automáticamente a TODAS las cards** (task_ready, comment_ready, stale_consumed, waiting_files, artifacts_idle, files_error, completed_ok). No hay código adicional en F3.

La única acción de F3 es verificar en el JSX que el file picker no queda escondido o deshabilitado en states distintos a `completed_ok`. El handler `handleFileSelect` no tiene condición de readiness: funciona en cualquier estado.

**Criterio binario F3:** `tsc --noEmit` = 0 errores. El file picker es visible (inspeccionando el DOM con devtools) en una card de cualquier readiness.

---

## 5. Riesgos y mitigaciones

| Riesgo | Probabilidad | Mitigación |
|--------|-------------|------------|
| El volumen de tickets completados hace el board enorme | Media | El toggle "Ocultar completados" permite volver al comportamiento previo con un click; `completed_ok` siempre va último en el sort (orden 6) |
| `last_exec_by_ticket` ya se carga para todos los tickets, performance OK | Baja | La query existente (líneas 2391-2400) ya itera todas las ejecuciones sin query adicional; no hay N+1 |
| Backend viejo (sin `completed_ok` en counts) + frontend nuevo | Media | `counts?.completed_ok ?? 0` en todos los accesos al campo; `completed_ok?` optional en el tipo |
| Doble-subida de un archivo ya procesado | Baja | `rescue_artifact` genera `rescue_uploaded_at` → SHA distinto → `create-child-task` crea una Task nueva (duplicado intencional, confirmado por análisis del filtro de idempotencia línea 3728). El operador ve el resultado inmediato en `actionMessage`. |
| `handleFileSelect` duplica código de `handleDrop` | Baja | Aceptado: la alternativa (refactorizar `handleDrop` a un helper compartido) agrega superficie de test sin reducir complejidad observable. El código es pequeño y localizado. |

---

## 6. Fuera de scope

- **Paginación del board**: si el número de tickets completados crece, la paginación es un plan futuro independiente. El toggle de ocultado es el mecanismo de control de volumen por ahora.
- **Filtro por rango de fecha de ejecución**: no pedido.
- **Badge de "completado hace X horas"**: se puede agregar en una iteración futura; `last_execution.started_at` ya está disponible en el item.
- **Notificación push cuando el agente completa**: fuera de scope de este plan (es la feature de notificaciones del sistema).
- **Cambios en los 3 runtimes de agente** (Codex, Claude Code, Copilot): no hay ninguno. Este plan es exclusivamente backend endpoint + frontend board.
- **Nuevo flag de harness / env var**: no aplica. El toggle es de estado local de UI (`useState`), no de configuración del operador persistida.

---

## 7. Glosario, Orden de implementación y DoD

### Glosario

| Término | Definición en este plan |
|---------|------------------------|
| `completed_ok` | Nuevo readiness: ticket con última ejecución en estado terminal exitoso (`completed`/`ok`/`done`) y sin artifacts pendientes en disco |
| `include_completed` | Query param de `GET /api/tickets/unblocker-board`. Default `true`. Si `false`, comportamiento idéntico al previo (solo running + has_artifacts) |
| `rescue_artifact` | Endpoint existente `POST /api/tickets/{ado_id}/rescue-artifact`. Acepta el archivo subido, lo escribe en disco con `rescue_uploaded_at`, retorna el path y tipo detectado |
| File picker | `<input type="file">` visible en la card como fallback accesible del drag-and-drop |
| Toggle | Botón en el header de `UnblockerPage` que alterna `includeCompleted` state (default ON) |

### Orden de implementación (estricto, TDD)

```
1. Escribir UB-06, UB-07, UB-08 en test_unblocker_board.py → correr → ROJO esperado
2. Implementar F0 en tickets.py (cambios 1-6) → correr → VERDE
3. Implementar F1 en endpoints.ts (tipos) → tsc → 0 errores
4. Localizar e implementar el parámetro includeCompleted en Tickets.unblockerBoard (endpoints.ts)
5. Implementar F2+F3 en UnblockerPage.tsx y UnblockerPage.module.css → tsc → 0 errores
6. Correr la suite completa: pytest test_unblocker_board.py -q → todos los UB verdes
```

### Definition of Done (DoD) — verificación binaria

- [ ] `pytest "Stacky Agents/backend/tests/test_unblocker_board.py" -q` = verde, incluyendo UB-01..UB-08
- [ ] Ningún test previo roto (ratchet no retrocede)
- [ ] `tsc --noEmit` en `Stacky Agents/frontend` = 0 errores
- [ ] Con `include_completed=false`: el board no incluye tickets con `readiness=completed_ok`
- [ ] Con `include_completed=true` (default, sin pasar el param): tickets con última ejecución `completed` aparecen
- [ ] El file picker `<input type="file">` es visible en TODAS las cards y dispara la misma lógica de rescate que el drag-and-drop
- [ ] El toggle en el header muestra el count correcto de `counts.completed_ok`
- [ ] Impacto en runtimes de agente: ninguno (0 archivos cambiados fuera de `tickets.py`, `endpoints.ts`, `UnblockerPage.tsx`, `UnblockerPage.module.css`, `test_unblocker_board.py`)
