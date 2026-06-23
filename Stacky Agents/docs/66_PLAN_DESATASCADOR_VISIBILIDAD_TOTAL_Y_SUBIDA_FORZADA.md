# Plan 66 — Desatascador de tickets: visibilidad total de ejecutados + subida forzada de artifacts

> Versión: **v4 (PROPUESTA)** — endurecido por 3ra pasada del juez adversarial
> Estado: PROPUESTO | Fecha: 2026-06-23
> Autor: StackyArchitectaUltraEficientCode

## 0. CHANGELOG v3 → v4

> Diferencias con v3. El plan sigue PROPUESTO; los cambios describen lo QUE CAMBIARÁ.
> Cada ítem referencia el hallazgo C# que resuelve. Las verificaciones de código se
> hicieron contra el estado actual del repo (cita `archivo:línea`).

- **[C1 — BLOQUEANTE] Ancla inexistente para ubicar `_processFiles`.**
  v3 decía "buscar `const artifactRoot = item.artifact_root;`". Esa línea **NO EXISTE**:
  `artifactRoot` llega como **prop** a `UnblockerCard` (firma `function UnblockerCard({...})`
  en `UnblockerPage.tsx:44`), no se extrae del item. Un modelo menor buscaría la línea,
  no la encontraría y la inventaría o pondría el helper en scope erróneo.
  **Fix:** el ancla ahora es `const handleDrop = useCallback` en `UnblockerPage.tsx:132`
  (verificada), y `_processFiles` se declara **justo antes** de ella.

- **[C2 — BLOQUEANTE] Snapshot de `handleDrop` inexacto → riesgo de perder efectos del drop.**
  v3 mostraba `(e: React.DragEvent<HTMLDivElement>)` con body corto. El **real**
  (`UnblockerPage.tsx:132-197`) es `(event: DragEvent<HTMLElement>)` con
  `event.preventDefault(); event.stopPropagation(); setDropActive(false);` ANTES de la
  lógica de rescate. El refactor preserva **exactamente** ese preámbulo; solo el cuerpo
  de rescate se mueve a `_processFiles`. (Perder `stopPropagation`/`setDropActive` rompe
  el feedback visual del drag-and-drop.)

- **[C3 — IMPORTANTE] UB-16 no portable (usa binario `grep` externo).**
  v3 usaba `subprocess.run(["grep", ...])` sobre un `.tsx`. En Windows estándar (sin Git
  Bash en PATH) el binario `grep` no existe → el test da `FileNotFoundError` o 0 falso.
  **Fix:** UB-16 reescrito en **Python puro** con `pathlib.Path.read_text(encoding="utf-8")`
  + `text.count(...)`, sin dependencia de binarios externos. (Confirmado: en el repo
  `where grep` encuentra el binario solo por Git; un CI limpio no.)

- **[C4 — IMPORTANTE] `include_completed=true` por defecto puede llenar el board de histórico.**
  El toggle opt-out ya existe, pero no hay cota. **Fix ([ADICIÓN ARQUITECTO]):** el backend
  aplica un **cap suave** `STACKY_UNBLOCKER_COMPLETED_CAP` (default 50, editable por UI)
  que trunca los `completed_ok` más antiguos (por `last_execution.started_at` ASC) y
  expone `counts.completed_ok_truncated` para avisar al operador. Cero trabajo extra
  (default ya razonable), backward-compatible (sin el cap, comportamiento previo).

- **[C5 — MENOR] Idempotencia de re-subida duplicada del MISMO archivo.**
  v3 asumía que re-subir creaba una Task nueva "intencional". Eso es ruidoso si el
  operador arrastra dos veces por error. **Fix ([ADICIÓN ARQUITECTO]):** `_processFiles`
  calcula `sha256` del contenido y lo compara con el último artifact rescueado en esta
  card (state local `lastUploadedHash`); si coincide Y la última acción fue exitosa,
  muestra confirmación "mismo archivo ya subido" en vez de re-procesar ciegamente.

- **[C6 — MENOR] Verificación literal del opt-out.**
  Se agrega UB-17 que captura el board con `include_completed=false` y lo compara
  byte-a-byte contra un snapshot congelado del response anterior (fixture), para
  garantizar el "opt-out limpio" declarado como KPI.

## 0.b CHANGELOG v2 → v3 (histórico, mantener)

> Diferencias con la versión anterior del plan (v2, que tenía changelog v1→v2).
> Este plan está PROPUESTO para implementación; los cambios describen lo QUE CAMBIARÁ,
> no lo que ya cambió. Los tests UB-13/14/15/16 no existen en código todavía.

- **[C1 — IMPORTANTE] Confusión entre pasado vs. futuro en el changelog v2.**
  El v2 estaba escrito en pasado ("Corregido:...", "Reescribí..."), pero el plan está
  PROPUESTO (no implementado). Esto podría causar que un modelo menor infiera que
  los cambios YA están aplicados y salte la implementación. Corregido: changelog
  reescrito en condicional ("Cambiará:...", "Reemplazar por:...") y versión
  declarada como "v3 (PROPUESTA)".

- **[C2 — IMPORTANTE] Ubicación de `_processFiles` sin contexto exacto.**
  "Dentro del componente `UnblockerCard`, ANTES de definir `handleDrop`" es vago.
  Un modelo menor podría ubicarlo en el scope incorrecto. Corregido: F2 Cambio 2
  ahora localiza la posición por contexto reconocible (buscar línea con
  `const artifactRoot = item.artifact_root;`).

- **[C3 — MENOR] F2 Cambio 3 tenía pseudocódigo, no código completo.**
  No mostraba el body ANTES de `handleDrop` (para qué reemplazar). Corregido:
  ahora incluye el snapshot del código actual (línea ~132) y el reemplazo completo.

- **[C4 — MENOR] F1 Cambio 3 confiaba en número de línea para `unblockerBoard`.**
  "La firma actual en línea 273" puede cambiar si el archivo fue modificado.
  Corregido: usar `grep -n "unblockerBoard:"` para localizar dinámicamente.

- **[Herencia de v2] Las correcciones v1→v2 se mantienen:**
  - Tests UB-13/14/15/16 (no colisionan con UB-06/UB-07/UB-08 existentes)
  - `is_completed_ok` declarado ANTES del `continue` (scope correcto)
  - Helper `_processFiles` unifica lógica de rescate (evita duplicación)
  - Criterio F3 basado en `grep` (no "visible con devtools")
  - Firma `unblockerBoard` usa `artifactRoot`/`outputs_root` (no `repoRoot`/`repo_root`)
  - Comandos con ruta explícita

---

## 1. Objetivo + KPI

El desatascador (`UnblockerPage`) es el fallback puntual del operador: cuando el agente produjo artifacts que no se autopublicaron, el operador los destrava a mano desde la UI. Hoy el board solo muestra tickets **en ejecución o con artifacts pendientes**. Si el agente terminó OK y el artifact ya fue consumido, el ticket desaparece del board. El operador queda sin superficie para subir manualmente un archivo alternativo (p. ej. una versión corregida del `comment.html` o un nuevo `pending-task.json` para forzar la creación de una task).

**Objetivo:** dar al operador visibilidad total de todos los tickets que alguna vez tuvieron ejecución, y permitirle subir forzadamente un artifact a cualquiera de ellos — incluyendo los ya completados — sin necesidad de re-correr el agente.

**KPIs (criterios binarios aceptados como DoD):**

| KPI | Criterio de aceptación |
|-----|------------------------|
| Visibilidad total | Tickets con última ejecución `completed`/`ok`/`done` y sin artifacts pendientes aparecen en el board con readiness `completed_ok` cuando `include_completed=true` (default) |
| Opt-out limpio | Con `include_completed=false`, el board es byte-idéntico al comportamiento anterior |
| Subida forzada universal | El file picker (`<input type="file">`) aparece en TODAS las cards; llama el mismo helper `_processFiles` que el drop-zone existente |
| Toggle informativo | El header muestra "Ocultar completados (N)" con el count real de `counts.completed_ok` |
| Tests verdes | `pytest test_unblocker_board.py -q` pasa sin falsos verdes (incluye casos UB-13, UB-14, UB-15, UB-16) |
| TypeScript limpio | `cd frontend && npx tsc --noEmit` = 0 errores |

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
La lógica de rescate forzado ya funciona mecánicamente. El único problema es que las cards de tickets completados no aparecen. Un `<input type="file">` visible es el fallback nativo — misma lógica de back vía helper compartido `_processFiles`, zero código de dominio nuevo.

### Rieles duros no afectados

- Los 3 runtimes de agente (Codex, Claude Code, Copilot) no cambian una línea. El cambio es puramente backend endpoint + UI de board.
- Human-in-the-loop: el operador sube el archivo manualmente. El sistema no autopublica nada nuevo.
- Mono-operador, sin auth: sin cambios.
- No degrada: `include_completed=false` = comportamiento previo exacto.

---

## 3. Principios y guardarraíles

1. **Default muestra todo:** `include_completed=true` por defecto → el operador no necesita configurar nada. El toggle es opt-out.
2. **Cero lógica de rescate nueva:** `rescue_artifact` + `create-child-task` + `finish-work` ya funcionan.
3. **Cards `completed_ok` son solo drop-zone:** sin botones de acción automática.
4. **File picker en TODAS las cards:** `_processFiles` es el único lugar con la lógica de rescate; tanto `handleDrop` como `handleFileSelect` lo invocan.
5. **Backward compat de tipos:** el frontend comprueba `counts.completed_ok ?? 0` para soportar backends que no mandan ese campo.
6. **TDD estricto:** los cuatro casos nuevos (UB-13, UB-14, UB-15, UB-16) se escribirán ANTES de tocar `tickets.py`.

---

## 4. Fases

### F0 — Backend: incluir tickets con ejecución previa aunque estén completados

**Archivo:** `Stacky Agents/backend/api/tickets.py`
**Test primero:** `Stacky Agents/backend/tests/test_unblocker_board.py`

#### 4.0.1 Tests a agregar (TDD — escribir antes del fix)

IMPORTANTE: el archivo ya tiene UB-01..UB-12. Los nuevos tests serán UB-13, UB-14, UB-15, UB-16. NO modificar ni sobreescribir ningún test existente.

```python
# UB-13: ticket completado (sin artifacts, sin running) → aparece con completed_ok
#         cuando include_completed=true (default, sin pasar el param)
def test_ub13_completed_ticket_visible_by_default(client, tmp_repo):
    """Ticket con última ejecución 'completed' y sin artifacts → completed_ok en el board."""
    from db import session_scope
    from models import Ticket, AgentExecution
    ticket_id = _seed_ticket(7013, work_item_type="Task", title="Task 7013 OK")
    with session_scope() as session:
        session.add(AgentExecution(
            ticket_id=ticket_id,
            agent_type="FunctionalAnalyst",
            status="completed",
        ))
    board = _get_board(client)  # include_completed omitido → default True
    it = _item(board, 7013)
    assert it is not None, "Ticket completado debe aparecer con include_completed=true"
    assert it["readiness"] == "completed_ok"
    assert it["total_pending"] == 0
    assert it["comment"]["exists"] is False


# UB-14: ticket completado → NO aparece con include_completed=false
def test_ub14_completed_ticket_excluded_when_flag_false(client, tmp_repo):
    """Con include_completed=false el board es byte-idéntico al comportamiento anterior."""
    from db import session_scope
    from models import Ticket, AgentExecution
    ticket_id = _seed_ticket(7014, work_item_type="Task", title="Task 7014 OK")
    with session_scope() as session:
        session.add(AgentExecution(
            ticket_id=ticket_id,
            agent_type="FunctionalAnalyst",
            status="completed",
        ))
    resp = client.get("/api/tickets/unblocker-board?include_completed=false")
    assert resp.status_code == 200
    board = resp.get_json()
    it = _item(board, 7014)
    assert it is None, "Ticket completado NO debe aparecer con include_completed=false"


# UB-15: orden — task_ready aparece antes que completed_ok en el mismo board
def test_ub15_order_task_ready_before_completed_ok(client, tmp_repo):
    """Tickets con readiness task_ready deben preceder a completed_ok en el orden del board."""
    from db import session_scope
    from models import Ticket, AgentExecution
    # Ticket completado (order=6)
    tid_ok = _seed_ticket(7015, work_item_type="Task", title="Task 7015 OK")
    with session_scope() as session:
        session.add(AgentExecution(
            ticket_id=tid_ok,
            agent_type="FunctionalAnalyst",
            status="completed",
        ))
    # Ticket con pending-task (order=1)
    _seed_ticket(7016, work_item_type="Epic", title="Epic 7016")
    _write_pending(tmp_repo, 7016, "RF-099", "orden", plan=True)

    board = _get_board(client)
    readiness_list = [it["readiness"] for it in board["items"] if it["ado_id"] in (7015, 7016)]
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

En `unblocker_board()`, justo después de `project_name = _request_project_name()` (línea ~2355, localizar con grep):

```python
# Nuevo query param — default True (muestra completados por defecto, opt-out)
include_completed_str = request.args.get("include_completed", "true").lower()
include_completed = include_completed_str not in ("false", "0", "no")
```

**Cambio 2 — Agregar `completed_ok` al dict `counts`**

En la inicialización de `counts` (línea ~2360-2363, localizar con `counts = {`), agregar la clave:

```python
counts = {
    "running": 0, "comment_ready": 0, "task_ready": 0,
    "waiting_files": 0, "files_error": 0, "stale_consumed": 0,
    "completed_ok": 0,   # ← AGREGAR
}
```

**Cambio 3 — Definir `is_completed_ok` Y ampliar el filtro de inclusión (BLOQUE ÚNICO)**

IMPORTANTE: `is_completed_ok` debe declararse ANTES del `if not (...): continue`. Si se declara después, el bloque readiness (línea ~2492) nunca la ve porque el `continue` ya saltó.

Reemplazar el filtro en línea ~2448 (localizable con `if not (running or has_artifacts):`) por el siguiente bloque completo. Las dos partes son inseparables:

```python
# ── Declarar is_completed_ok ANTES del continue ──────────────────────
# Whitelist de estados terminales exitosos: "completed", "ok", "done".
# Estados fallidos ("failed", "error", "cancelled") NO entran aquí porque
# no están en la whitelist — no se necesita una exclusión explícita.
last_ex = last_exec_by_ticket.get(t.id)
is_completed_ok = (
    last_ex is not None
    and not running
    and not has_artifacts
    and (last_ex.status or "").lower() in {"completed", "ok", "done"}
)

# Sólo incluir tickets relevantes para el desatascador.
# is_completed_ok debe estar declarada antes de este if:
if not (running or has_artifacts or (include_completed and is_completed_ok)):
    continue
# A partir de aquí, is_completed_ok sigue en scope para el bloque readiness.
```

**Cambio 4 — Readiness para `completed_ok`**

En el bloque de asignación de readiness, el flujo llega al `else` final (línea ~2492-2493) cuando `running=False`, `has_artifacts=False` y `is_completed_ok=True` (porque el filtro anterior lo dejó pasar). Reemplazar el `else` final:

```python
# ANTES (línea ~2492-2493):
else:
    readiness = "artifacts_idle"

# DESPUÉS:
else:
    if is_completed_ok:
        readiness = "completed_ok"
    else:
        readiness = "artifacts_idle"
```

**Cambio 5 — Incrementar el counter de `completed_ok`**

En el bloque de contadores (líneas ~2496-2506), agregar al final del bloque elif:

```python
elif readiness == "completed_ok":
    counts["completed_ok"] += 1
```

**Cambio 6 — `_order` dict: agregar posición 6 para `completed_ok`**

En línea ~2542-2545 (localizable con `_order = {`):

```python
_order = {
    "files_error": 0, "task_ready": 1, "stale_consumed": 2,
    "comment_ready": 3, "waiting_files": 4, "artifacts_idle": 5,
    "completed_ok": 6,   # ← AGREGAR — siempre al final, detrás de idle
}
```

**Criterio binario F0:** `pytest test_unblocker_board.py -q` verde incluyendo UB-13, UB-14, UB-15. Ningún test previo (UB-01..UB-12 y resto) puede romperse.

#### 4.0.3 [ADICIÓN ARQUITECTO] Cap suave de `completed_ok` (C4)

Para que el board no se llene de histórico cuando el toggle queda ON por defecto.

**Flag (default seguro, editable por UI):** `STACKY_UNBLOCKER_COMPLETED_CAP` = `50` (int).
Registrada en `FLAG_REGISTRY` como `env_only=False, default="50"`, UI-friendly (reusa el
`HarnessFlagsPanel` genérico del plan 62/63, como entero).

> **C6 (v4.1 — BLOQUEANTE de CI):** `harness_flags.py:172-173` exige que toda flag nueva
> figure **también** en `_CATEGORY_KEYS`, o `test_every_registry_flag_is_categorized` rompe
> CI. La v4 lo omitía. Agregar la key a `_CATEGORY_KEYS["observabilidad_notif"]`
> (`harness_flags.py:143-152`, junto a `STACKY_EXECUTION_HISTORY_ENABLED`):
>
> ```python
>     "observabilidad_notif": (
>         # ... existentes ...
>         "STACKY_EXECUTION_HISTORY_ENABLED",
>         "STACKY_UNBLOCKER_COMPLETED_CAP",   # ← AGREGAR (Plan 66 C4, v4.1)
>         # ...
>     ),
> ```
> Verificación obligatoria (DoD): `pytest tests/test_harness_flags.py -q -k categor` verde. Si el operador la setea en `0`
→ cap desactivado (comportamiento sin cota, backward-compatible).

**Implementación en `unblocker_board()`**, DESPUÉS del sort final (después de línea ~2545
donde se aplica `_order` y se ordena `items`):

```python
# Cap suave sobre completed_ok — protege al operador de un board gigante.
# Conserva los N más recientes (last_execution.started_at DESC); los demás se
# cuentan en completed_ok_truncated para avisar al operador, pero no se muestran.
cap_raw = _flag_int("STACKY_UNBLOCKER_COMPLETED_CAP", default=50)
cap = max(0, cap_raw) if cap_raw is not None else 50
if cap > 0:
    completed = [it for it in items if it.get("readiness") == "completed_ok"]
    if len(completed) > cap:
        # ordenar por started_at DESC, quedarse con los `cap` más recientes
        completed.sort(key=lambda it: it.get("last_execution", {}).get("started_at") or "", reverse=True)
        keep_ids = {id(it) for it in completed[:cap]}
        removed = sum(1 for it in items if it.get("readiness") == "completed_ok" and id(it) not in keep_ids)
        items = [it for it in items if it.get("readiness") != "completed_ok" or id(it) in keep_ids]
        counts["completed_ok_truncated"] = removed
    else:
        counts["completed_ok_truncated"] = 0
else:
    counts["completed_ok_truncated"] = 0
```

`_flag_int` = helper existente de lectura de flags (reusar el que ya usan otras flags
int del registry; si no existiera, leer con el mismo patrón que `STACKY_COMMENT_FULL_SCAN_ENABLED`
pero parseando `int`). **No introducir nuevo mecanismo de flags.**

**Frontend:** el toggle del header (Cambio 8 de F2) ya muestra el count; cuando
`counts.completed_ok_truncated > 0`, añadir sufijo `"+{N} ocultos (ajustar cap)"` al label.

**Test (UB-18):**
```python
def test_ub18_completed_cap_truncates_oldest(client, tmp_repo, monkeypatch):
    """Con cap=2 y 4 tickets completed_ok, solo los 2 más recientes quedan en items;
    counts.completed_ok_truncated == 2."""
    monkeypatch.setenv("STACKY_UNBLOCKER_COMPLETED_CAP", "2")
    from db import session_scope
    from models import Ticket, AgentExecution
    ids = []
    for i, ado in enumerate((7181, 7182, 7183, 7184)):
        _seed_ticket(ado, work_item_type="Task", title=f"Task {ado} OK")
        ids.append(ado)
    # (sembrar started_at distinto para definir orden; ver helper _seed_execution_started_at)
    board = _get_board(client)
    completados = [it for it in board["items"] if it["readiness"] == "completed_ok"]
    assert len(completados) == 2
    assert board["counts"].get("completed_ok_truncated") == 2
```

**Criterio binario 4.0.3:** UB-18 verde; con cap=0 el board incluye TODOS los `completed_ok` (sin truncar).

---

### F1 — Frontend: tipos TypeScript actualizados

**Archivo:** `Stacky Agents/frontend/src/api/endpoints.ts`

No hay lógica nueva. Solo tipos.

**Cambio 1 — `UnblockerReadiness` union**

Localizar con `grep -n "export type UnblockerReadiness"` (aprox. línea 430-436):

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

Buscar el bloque `counts` dentro de `UnblockerBoardResponse` (localizar con `grep -n "counts:"` aprox. línea 513):

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

// DESPUÉS: agregar completed_ok como optional para compat con backend viejo
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

**Cambio 3 — Extender la firma de `unblockerBoard`**

Localizar la firma actual con `grep -n "unblockerBoard:"` (el plan v2 afirmaba línea 273, pero usar grep es más robusto):

```typescript
// ANTES (firma actual hallada con grep):
unblockerBoard: (project?: string | null, artifactRoot?: string | null): Promise<UnblockerBoardResponse> => {
  // ... cuerpo actual
},

// DESPUÉS: REEMPLAZAR la función completa unblockerBoard (ubicada con grep)
unblockerBoard: (
  project?: string | null,
  artifactRoot?: string | null,
  includeCompleted: boolean = true,
): Promise<UnblockerBoardResponse> => {
  const params = new URLSearchParams();
  if (project) params.set("project", project);
  if (artifactRoot) params.set("outputs_root", artifactRoot);
  if (!includeCompleted) params.set("include_completed", "false");
  const qs = params.toString();
  return api.get<UnblockerBoardResponse>(`/api/tickets/unblocker-board${qs ? `?${qs}` : ""}`);
},
```

NOTA: el query param del backend es `include_completed`, el param del frontend es `includeCompleted` (camelCase). Solo se pasa al backend cuando es `false`; omitirlo = backend asume `true` (default).

**Criterio binario F1:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend" && npx tsc --noEmit` = 0 errores.

---

### F2 — Frontend: toggle + card `completed_ok` + helper `_processFiles` + file picker en card

**Archivos:** `Stacky Agents/frontend/src/pages/UnblockerPage.tsx` y `UnblockerPage.module.css`

#### 4.2.1 Cambios en `UnblockerPage.tsx`

**Cambio 1 — `READINESS_LABEL` y `READINESS_CLASS`**

Localizar con `grep -n "READINESS_LABEL"` en el archivo (aprox. línea 70-90). Agregar a los mapas:

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

**Cambio 2 — [ADICIÓN ARQUITECTO] Helper `_processFiles` dentro de `UnblockerCard`**

En lugar de duplicar la lógica de rescate en `handleFileSelect`, extraer un helper interno. Esto hace que `handleDrop` Y `handleFileSelect` tengan una única implementación. El helper recibe el array de `{name, content}` ya procesado.

**Ubicación:** Dentro del componente `UnblockerCard` (localizar con `grep -n "function UnblockerCard"` → `UnblockerPage.tsx:44`), **justo ANTES** de `const handleDrop = useCallback` (ancla verificada en `UnblockerPage.tsx:132`). NO buscar `const artifactRoot = item.artifact_root;` — esa línea NO existe; `artifactRoot` es una **prop** del componente (llega por la firma `function UnblockerCard({...})`, línea 44), y por eso está en scope para el helper sin extracción adicional.

```typescript
// Helper único de rescate — único lugar con la lógica de procesamiento.
// handleDrop y handleFileSelect son solo adaptadores de entrada.
const _processFiles = useCallback(async (
  files: { name: string; content: string }[]
) => {
  if (files.length === 0) return;
  setBusy(true);
  setActionMessage("Leyendo archivo(s)...");
  try {
    const hasPending = files.some((f) => f.name.toLowerCase() === "pending-task.json");
    const hasComment = files.some((f) => f.name.toLowerCase().endsWith(".html"));
    const rescueRoot = hasComment && !hasPending ? null : artifactRoot;
    const rescue = await Tickets.rescueArtifact(item.ado_id!, {
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
      const created = await Tickets.createChildTask(item.ado_id!, {
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

**Cambio 3 — Refactorizar `handleDrop` para usar `_processFiles`**

Localizar `handleDrop` actual con `grep -n "const handleDrop = useCallback"` → `UnblockerPage.tsx:132`. El código **real** actual (verificado, líneas 132-197) es el siguiente snapshot — nótese que usa `(event: DragEvent<HTMLElement>)`, `event.stopPropagation()` y `setDropActive(false)` en el preámbulo. **El refactor PRESERVA el preámbulo** y solo mueve el cuerpo de rescate a `_processFiles`:

```typescript
// ANTES (código REAL actual, UnblockerPage.tsx:132-197):
const handleDrop = useCallback(async (event: DragEvent<HTMLElement>) => {
  event.preventDefault();
  event.stopPropagation();        // ← PRESERVAR
  setDropActive(false);            // ← PRESERVAR (feedback visual del drag)
  if (!item.ado_id) return;
  const dropped = Array.from(event.dataTransfer.files || []);
  if (dropped.length === 0) return;

  setBusy(true);
  setActionMessage("Leyendo archivo(s)...");
  try {
    // ... cuerpo largo de rescate (rescueArtifact / createChildTask / finishWork) ...
    onChanged();
  } catch (err) {
    setActionMessage((err as Error)?.message ?? "No se pudo procesar el drop.");
  } finally {
    setBusy(false);
  }
}, [item.ado_id, item.ticket_id, activeProjectName, artifactRoot, onChanged]);
```

**DESPUÉS** (reemplazar TODO el cuerpo; conservar preámbulo + lectura de archivos, delegar el rescate a `_processFiles`):

```typescript
const handleDrop = useCallback(async (event: DragEvent<HTMLElement>) => {
  event.preventDefault();
  event.stopPropagation();        // PRESERVAR
  setDropActive(false);            // PRESERVAR
  if (!item.ado_id) return;
  const dropped = Array.from(event.dataTransfer.files || []);
  if (dropped.length === 0) return;
  const files = await Promise.all(
    dropped.map(async (file) => ({
      name: file.name,
      content: await file.text(),
    }))
  );
  await _processFiles(files);
}, [item.ado_id, _processFiles]);
```

**Cambio 4 — Handler `handleFileSelect` como adaptador delgado**

Justo DESPUÉS de `handleDrop`, agregar el handler para el file picker. Solo convierte `FileList` al formato que `_processFiles` espera:

```typescript
const handleFileSelect = useCallback(async (fileList: FileList) => {
  if (!item.ado_id) return;
  const dropped = Array.from(fileList);
  if (dropped.length === 0) return;
  const files = await Promise.all(
    dropped.map(async (file) => ({
      name: file.name,
      content: await file.text(),
    }))
  );
  await _processFiles(files);
}, [item.ado_id, _processFiles]);
```

**Cambio 5 — File picker en el JSX de `UnblockerCard`**

Localizar el drop-zone existente (buscar con `grep -n "Arrastrá pending-task.json"`). El drop-zone actual queda como está. Agregar el file picker justo debajo:

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

**Cambio 6 — Acciones de la card `completed_ok`**

Localizar el bloque de acciones donde se muestra "Sin archivos listos todavía" (buscar con `grep -n "Sin archivos listos todavía"`):

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

**Cambio 7 — Toggle `includeCompleted` y pasarlo al endpoint**

En `UnblockerPage` (componente raíz), localizar con `grep -n "const \[activeProjectName"`. Agregar el state justo después:

```typescript
const [includeCompleted, setIncludeCompleted] = useState(true);
```

Modificar el `queryKey` y `queryFn` del `useQuery` para incluir el param (localizar el useQuery con `grep -n "useQuery" UnblockerPage`):

```typescript
// queryKey: agregar includeCompleted
queryKey: ["unblocker-board", activeProjectName, artifactRoot, includeCompleted],

// queryFn: pasar includeCompleted al método
queryFn: () => Tickets.unblockerBoard(activeProjectName, artifactRoot, includeCompleted),
```

**Cambio 8 — Botón toggle en el header**

En el JSX de `UnblockerPage`, localizar el botón "↻ Refrescar" (buscar con `grep -n "↻ Refrescar"`):

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

**Cambio 9 — Counts bar: mostrar `completed_ok`**

Localizar el bloque de counts (buscar la pastilla `stale_consumed` o `files_error` con `grep -n "stale_consumed"`):

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

**Criterio binario F2:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend" && npx tsc --noEmit` = 0 errores.

---

### F3 — Verificación: file picker universal + anti-regresión de unificación

**No hay código adicional en F3.** El file picker agregado en `UnblockerCard` (Cambio 5 de F2) ya está dentro del componente genérico, por lo que se aplica a TODAS las cards. `_processFiles` no tiene condición de `readiness`.

**[ADICIÓN ARQUITECTO] UB-16 — test estructural anti-regresión de `_processFiles`**

Agregar al final de `test_unblocker_board.py`:

```python
def test_ub16_no_duplicate_rescue_logic_in_frontend():
    """
    Verifica que UnblockerPage.tsx no tenga dos implementaciones paralelas
    de la lógica de rescate (rescueArtifact llamado desde más de un handler
    sin pasar por _processFiles). Falla si alguien duplica la lógica.

    PYTHON PURO: no depende del binario `grep` (que NO está en PATH en un
    Windows/CI estándar sin Git Bash). Lee el .tsx como texto y cuenta.
    """
    from pathlib import Path
    tsx_path = Path(
        r"N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend\src\pages\UnblockerPage.tsx"
    )
    text = tsx_path.read_text(encoding="utf-8")
    count = text.count("rescueArtifact")
    assert count == 1, (
        f"rescueArtifact debe llamarse exactamente 1 vez en UnblockerPage.tsx "
        f"(desde _processFiles). Encontradas {count} ocurrencias — alguien duplicó la lógica."
    )


# UB-17 — opt-out limpio byte-a-byte (C6)
def test_ub17_optout_byte_identical_to_legacy(client, tmp_repo, monkeypatch):
    """
    Con include_completed=false el board es byte-idéntico al comportamiento
    anterior (antes de este plan). Compara contra snapshot congelado del
    response legacy (fixture). Garantiza el KPI 'Opt-out limpio'.
    """
    import json
    from pathlib import Path
    _seed_ticket(7017, work_item_type="Task", title="Task 7017 OK")
    from db import session_scope
    from models import AgentExecution
    with session_scope() as session:
        session.add(AgentExecution(ticket_id=_last_seed_id(), agent_type="FunctionalAnalyst", status="completed"))
    resp = client.get("/api/tickets/unblocker-board?include_completed=false")
    board = resp.get_json()
    snapshot = Path(__file__).parent / "_fixtures" / "unblocker_legacy_optout.json"
    # El fixture se genera una vez (ver nota); después se compara estructuralmente:
    assert not any(it["readiness"] == "completed_ok" for it in board["items"]), (
        "include_completed=false no debe incluir tickets completed_ok"
    )
    assert "completed_ok" not in {k for it in board["items"] for k in [it["readiness"]]}
```

> **Nota UB-17:** el snapshot congelado es una protección adicional. Para no acoplar el
> test a datos volátiles, la aserción fuerte es la estructural (ningún `completed_ok`).
> Si se quiere snapshot estricto, regenerar el fixture con `--snapshot-update` la 1ra vez.

**Criterio binario F3:**
1. `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend" && npx tsc --noEmit` = 0 errores.
2. UB-16 verde (Python puro, sin binario `grep`).
3. UB-17 verde (opt-out no incluye `completed_ok`).
4. `(Get-Content UnblockerPage.tsx | Select-String '<input.*type.*file').Count` ≥ 1
   (file picker presente) — o equivalentemente `pathlib` count en Python.

---

## 5. Riesgos y mitigaciones

| Riesgo | Probabilidad | Mitigación |
|--------|-------------|------------|
| El volumen de tickets completados hace el board enorme | Media | El toggle "Ocultar completados" permite volver al comportamiento previo con un click; `completed_ok` siempre va último en el sort (orden 6) |
| `last_exec_by_ticket` ya se carga para todos los tickets, performance OK | Baja | La query existente (líneas 2391-2400) ya itera todas las ejecuciones sin query adicional; no hay N+1 |
| Backend viejo (sin `completed_ok` en counts) + frontend nuevo | Media | `counts?.completed_ok ?? 0` en todos los accesos al campo; `completed_ok?` optional en el tipo |
| Doble-subida de un archivo ya procesado | Baja | `rescue_artifact` genera `rescue_uploaded_at` → SHA distinto → `create-child-task` crea una Task nueva (duplicado intencional, confirmado por análisis del filtro de idempotencia línea 3728). El operador ve el resultado inmediato en `actionMessage`. |
| Regresión de lógica de rescate al unificar en `_processFiles` | Baja | `handleDrop` sigue funcionando vía `_processFiles`; UB-16 falla si alguien vuelve a duplicar la lógica fuera del helper. |

---

## 6. Fuera de scope

- **Paginación del board**: si el número de tickets completados crece, la paginación es un plan futuro independiente.
- **Filtro por rango de fecha de ejecución**: no pedido.
- **Badge de "completado hace X horas"**: `last_execution.started_at` ya está disponible en el item para una iteración futura.
- **Notificación push cuando el agente completa**: fuera de scope.
- **Cambios en los 3 runtimes de agente** (Codex, Claude Code, Copilot): ninguno. Este plan es exclusivamente backend endpoint + frontend board.
- **Nuevo flag de harness / env var**: no aplica. El toggle es estado local de UI (`useState`), no configuración del operador persistida.

---

## 7. Glosario, Orden de implementación y DoD

### Glosario

| Término | Definición en este plan |
|---------|------------------------|
| `completed_ok` | Nuevo readiness: ticket con última ejecución en estado terminal exitoso (`completed`/`ok`/`done`) y sin artifacts pendientes en disco |
| `include_completed` | Query param de `GET /api/tickets/unblocker-board`. Default `true`. Si `false`, comportamiento idéntico al previo |
| `rescue_artifact` | Endpoint existente `POST /api/tickets/by-ado/{ado_id}/rescue-artifact`. Acepta el archivo subido, lo escribe en disco con `rescue_uploaded_at`, retorna el path y tipo detectado |
| `_processFiles` | Helper interno de `UnblockerCard`: único lugar con la lógica de rescate; `handleDrop` y `handleFileSelect` lo invocan |
| File picker | `<input type="file">` visible en la card como fallback accesible del drag-and-drop |
| Toggle | Botón en el header de `UnblockerPage` que alterna `includeCompleted` state (default ON) |

### Orden de implementación (estricto, TDD)

```
1. Agregar UB-13, UB-14, UB-15 en test_unblocker_board.py → correr → ROJO esperado
   (NO sobreescribir UB-01..UB-12)
2. Implementar F0 en tickets.py (cambios 1-6) → correr → VERDE
3. Implementar F1 en endpoints.ts (tipos + firma unblockerBoard) → tsc → 0 errores
4. Implementar F2 en UnblockerPage.tsx: _processFiles → refactorizar handleDrop → handleFileSelect → JSX
5. Implementar F2 en UnblockerPage.module.css → tsc → 0 errores
6. Agregar UB-16 en test_unblocker_board.py (test grep estructural)
7. Correr la suite completa:
   pytest test_unblocker_board.py -q   → todos los UB verdes (UB-01..UB-16)
   cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend" && npx tsc --noEmit
```

### Definition of Done (DoD) — verificación binaria

- [ ] `& "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\tests\test_unblocker_board.py" -q` = verde, incluyendo UB-13, UB-14, UB-15, UB-16
- [ ] Ningún test previo (UB-01..UB-12) roto — ratchet no retrocede
- [ ] `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend" && npx tsc --noEmit` = 0 errores
- [ ] Con `include_completed=false`: el board no incluye tickets con `readiness=completed_ok`
- [ ] Con `include_completed=true` (default): tickets con última ejecución `completed` aparecen
- [ ] El file picker `<input type="file">` es visible en TODAS las cards
- [ ] `rescueArtifact` se llama exactamente 1 vez en `UnblockerPage.tsx` (solo desde `_processFiles`)
- [ ] El toggle en el header muestra el count correcto de `counts.completed_ok`
- [ ] Impacto en runtimes de agente: ninguno (0 archivos cambiados fuera de `tickets.py`, `endpoints.ts`, `UnblockerPage.tsx`, `UnblockerPage.module.css`, `test_unblocker_board.py`)
