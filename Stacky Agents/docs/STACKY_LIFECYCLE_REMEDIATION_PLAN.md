# Stacky Lifecycle Remediation Plan

> Generado: 2026-05-15  
> Autor: StackyToolArchitect 2.0  
> Base de código inspeccionada: `N:/GIT/RS/RSPACIFICO/Tools/Stacky/Stacky Agents/` + `Tools/Stacky/Stacky pipeline/`

---

## TL;DR ejecutivo

El sistema tiene dos capas de runtime con contratos de completado distintos y **sin puente entre ellas**: el backend Flask (`agent_runner.py`, `codex_cli_runner.py`) usa `AgentExecution.status` + `log_streamer` como canal de completado; el pipeline (`pipeline_reconciler.py`, `pipeline_watcher.py`) usa flags de filesystem (`*_COMPLETADO.flag`). Nunca se hablan.

Los cinco bugs son consecuencia directa de esta brecha:

1. La graph view se pone en blanco porque `TicketNodeCard` no tiene error boundary y el SSE de `useExecutionStream` no distingue el evento `log` del evento `completed` correctamente.
2. `FinishWorkButton` solo aparece cuando `isRunning && !inconsistency.isInconsistent` — condición imposible de cumplir cuando el agente colgó pero `stacky_status` quedó `running`.
3. El agente pregunta "¿crear tarea?" porque no existe ningún short-circuit que chequee si la task ya existe en disco antes de consultar la DB.
4. Stacky no detecta automáticamente el fin de trabajo porque `codex_cli_runner` completa el run solo si el proceso Codex CLI termina con exit_code=0 — si Copilot cierra el chat sin generar exit, el hilo queda vivo y nunca escribe `completed`.
5. No hay reconciliación periódica activa. `schedule_stale_recovery` existe en los tests pero **no está implementada en `ticket_status.py`** — la función solo tiene el shim `stop_stale_recovery` (no-op). `pipeline_reconciler.py` existe y es sofisticado pero opera sobre state.json del pipeline, no sobre `AgentExecution` de la DB del backend.

El plan se estructura en 6 fases de 1-2 semanas cada una.

---

## 1. Diagnóstico forense

### Bug 1: UI en blanco en graph view al expandir nodo en ejecución

**Síntoma observado**: hacer click en un nodo con `isRunning=true` expande el `nodeBody` y deja la vista en blanco (pantalla negra o vacía).

**Trazado end-to-end**

1. `TicketGraphView.jsx:528` — `TicketGraphView` recibe `runningByTicket: Map` desde `TicketBoard.tsx`.
2. `TicketGraphView.jsx:249` — `isRunning = !!runningExecution || runningByTicket.has(ticket.id)`.
3. `TicketGraphView.jsx:348-396` — Al expandir (`expanded=true`), se renderiza `nodeBody` que incluye `inferResult`, `FinishWorkButton`, `CreateChildTaskButton`, etc.
4. `TicketGraphView.jsx:385-395` — `FinishWorkButton` se renderiza si `!isEpic && !isClosed && isRunning && !inconsistency.isInconsistent`. En ese render, `ticket.stacky_status` puede ser `null` o un valor inesperado — `detectInconsistencyFromRunning` puede lanzar si `runningExecution` no tiene la forma esperada.
5. `useExecutionStream.ts:26-28` — El listener `onLog` parsea `JSON.parse(e.data)` sin try/catch. Si el servidor emite un evento de tipo distinto a `log` (por ejemplo el `ping` registrado en `:13: event: ping`) el evento `e.data` puede no ser JSON válido.

**Causa raíz**

Doble fuente:

a) **Sin error boundary**: `TicketNodeCard` en `.jsx` (no TypeScript) no tiene `<ErrorBoundary>`. Si cualquier hijo lanza durante el render expandido (e.g. `detectInconsistencyFromRunning` sobre un `runningExecution` con shape inesperada), React desmonta el árbol completo y queda la vista en blanco sin mensaje de error visible.

b) **Race condition en SSE**: `useExecutionStream.ts:26-28` — `onLog` hace `JSON.parse(e.data)` sin guard. El backend en `executions.py:49-52` emite:
```
event: ping\ndata: {"type":"ping"}\n\n
```
El handler `onLog` solo escucha el evento `log`, pero si hay una re-subscripción o el `es.addEventListener("log", onLog)` del anterior `useEffect` no se limpió correctamente (ver `useExecutionStream.ts:44-47`), puede procesar un payload `ping` que `JSON.parse` resuelve como objeto sin `level`/`message`, lo que revienta cuando el componente usa `data.level.toUpperCase()`.

**Evidencia**
```
// useExecutionStream.ts:26-28
const onLog = (e: MessageEvent) => {
  const data = JSON.parse(e.data);          // sin try/catch
  setState((s) => ({ ...s, lines: [...s.lines, data] }));
};
```
```
// executions.py:49-52
for event in log_streamer.stream(execution_id):
    event_type = event.get("type") or "log"
    data = json.dumps(event, ensure_ascii=False)
    yield f"event: {event_type}\ndata: {data}\n\n"
```
```
// log_streamer.py:124-127
try:
    event = listener.get(timeout=15.0)
except queue.Empty:
    yield {"type": "ping"}   # <-- emite dict con solo "type", sin level/message
```
El `onLog` del frontend solo se registra para `event: log`, pero si hay listener duplicado (dependencias de `useEffect` mal declaradas) puede dispararse para `ping`.

**Hipótesis descartadas**
- SSE re-subscription en bucle: no es así, `useExecutionStream.ts:48` tiene `[executionId, qc]` como deps y el cleanup `es.close()` en el return. El problema es el JSON parsing sin guard, no la re-subscription en sí.
- Suspense sin fallback: no hay `<Suspense>` en `TicketGraphView.jsx`.

---

### Bug 2: Botón "Finish Work" no aparece correctamente

**Síntoma observado**: el operador no puede encontrar el botón en situaciones en que sería necesario (ticket colgado).

**Trazado end-to-end**

1. `TicketGraphView.jsx:385-395` — Condición de render:
```jsx
{!isEpic && !isClosed && isRunning && !inconsistency.isInconsistent && (
  <FinishWorkButton ... />
)}
```
2. `isRunning` (`TicketGraphView.jsx:249`) depende de que `runningByTicket.has(ticket.id)` sea `true`.
3. `runningByTicket` se construye en `TicketBoard.tsx` a partir del hook `useRunningStatus`:
```tsx
// TicketBoard.tsx:10
import { useRunningStatus } from "../hooks/useRunningStatus";
```
4. Si `stacky_status='running'` pero la ejecución ya terminó (bug #5), `useRunningStatus` puede devolver un Map vacío (depende de qué endpoint consulta).
5. La condición `!inconsistency.isInconsistent` bloquea el botón en el único caso donde más se necesitaría: cuando hay inconsistencia (ticket running pero sin ejecución activa en DB).

**Causa raíz**

La visibilidad del botón depende de `isRunning && !inconsistency.isInconsistent`, que son condiciones **mutuamente necesarias pero semánticamente opuestas al caso de uso**. Un ticket colgado que necesita cierre manual típicamente tiene `inconsistency.isInconsistent=true` (stacky_status=running pero execution terminada), lo que oculta el botón. La condición correcta debería ser: "ticket con stacky_status != completed y sin agente realmente activo".

Adicionalmente, en `TicketBoard.tsx` el `FinishWorkButton` tiene su propia condición:
```tsx
// TicketBoard.tsx line ~385 (tree view)
{!CLOSED_STATES.includes(ticket.ado_state) && (
  <FinishWorkButton ticket={ticket} ... />
)}
```
La condición en tree view es diferente a la condición en graph view, lo que genera comportamiento inconsistente entre vistas.

**Hipótesis descartadas**
- Bug en el endpoint `finish-work`: el endpoint existe y tiene tests en `test_finish_work.py` — funciona. El problema es solo de visibilidad del botón en UI.

---

### Bug 3: El agente pregunta "¿querés crear la task?" cuando los archivos ya existen

**Síntoma observado**: el agente funcional (u otro con capacidad de crear tasks) pregunta al operador si debe crear la task en ADO, aun cuando ya existe un `pending-task.json` o las tasks ya fueron creadas.

**Trazado end-to-end**

1. `agent_runner.py:279` — `result = agent.run(masked_blocks, log=log, execution_id=execution_id, run_ctx=run_ctx)` invoca al agente (modelo de lenguaje via Copilot/Codex).
2. El agente recibe el contexto construido a partir de `masked_blocks` (`raw_blocks` del request). No hay bloque que informe "ya existe `pending-task.json` en disco".
3. El agente solo sabe lo que está en el contexto inyectado. Si no se inyecta el estado de los artifacts del filesystem, pregunta al operador.
4. `api/tickets.py:28-52` — El endpoint `create_child_task` verifica si existe `pending-task.json`:
```python
# api/tickets.py linea ~200
_PENDING_TASK_REQUIRED_FIELDS = {
    "generated_at", "generated_by", "epic_id", "rf_id",
    "title", "description_html", "plan_de_pruebas_path",
    "parent_link_type", "status",
}
```
Pero este check ocurre en el endpoint de creación, no como context block inyectado al agente antes de que pregunte.

5. `ado_task_creator.py:38-69` — `create_child_tasks_from_tareas` lee `TAREAS_DESARROLLO.md` y llama a ADO directamente. No escribe ningún sentinel de "ya creado" en disco ni en DB.

**Causa raíz**

No existe un **context block de filesystem state** que el runner inyecte automáticamente antes de invocar al agente. El agente recibe el ticket y el contexto del operador, pero nunca recibe "estos artifacts ya existen en disco: `[pending-task.json]`". Sin esa información, el LLM aplica su prior (preguntar antes de hacer) en lugar de un short-circuit determinista.

El `ado_task_creator.py` del pipeline no escribe ningún flag de idempotencia al crear tasks (a diferencia del pattern usado en `pipeline_reconciler.py` con `PM_COMPLETADO.flag`, `DEV_COMPLETADO.md`, etc.).

**Evidencia**
```python
# ado_task_creator.py:55-69
created_ids = []
for task in tasks:
    try:
        child_id = self._create_child_task(parent_work_item_id, task, project)
        if child_id:
            created_ids.append(child_id)
    except Exception as e:
        logger.error("Failed to create child task '%s': %s", task.get("title", "?"), e)
# <-- no escribe ningún sentinel de completado
```

**Hipótesis descartadas**
- Bug en el endpoint `/api/tickets/<id>/create-child-task`: el endpoint verifica `pending-task.json` correctamente. El problema es upstream (no se inyecta el estado al agente).

---

### Bug 4: Stacky no detecta automáticamente fin de trabajo aunque el agente generó outputs

**Síntoma observado**: el agente terminó de trabajar (archivos generados, Copilot chat cerrado) pero el run queda en `status=running` indefinidamente.

**Trazado end-to-end**

**Flujo via agent_runner.py (agentes internos Flask):**
1. `agent_runner.py:90-103` — El thread daemon llama a `_run_in_background`.
2. `agent_runner.py:279` — `result = agent.run(...)` — esto llama al agente que, internamente, invoca Copilot via `copilot_bridge.py`.
3. `agent_runner.py:302-316` — Si el agente retorna sin excepción, escribe `status='completed'`.
4. **Problema**: si `copilot_bridge` cierra la conexión sin respuesta completa (timeout, disconnect), puede lanzar `CancelledError` o simplemente retornar `result` con `output=None`. Si lanza `Exception` se captura en línea 382 y se marca `error`. Si retorna silenciosamente, `row.status = "completed"` se ejecuta incluso con output vacío.

**Flujo via codex_cli_runner.py (runtime Codex CLI):**
1. `codex_cli_runner.py:301` — `return_code = proc.wait()` — el runner espera el exit del proceso Codex CLI.
2. `codex_cli_runner.py:324-338` — Si `return_code == 0`, llama a `_mark_terminal(status="completed")`.
3. **Problema crítico**: si el usuario cierra el chat de Copilot sin terminar (o Copilot CLI falla silenciosamente después de generar output), `proc.wait()` puede bloquearse indefinidamente. El hilo `codex-cli-{execution_id}` es `daemon=True` (línea 123), lo que significa que muere con el proceso Flask pero NO cierra la ejecución con ningún estado terminal — queda `running` en DB.
4. **Segunda forma**: Codex CLI genera el archivo `last_message.md` y luego cierra con exit code no-cero (error de red, timeout de API). `codex_cli_runner.py:352-376` lo marca `error`, pero si el archivo tiene output válido, el operador pierde ese output y tiene que hacer recovery manual.

**Causa raíz**

El modelo de completado del sistema es **basado en respuesta del proceso/agente** (exit code, retorno de `agent.run()`), no en **eventos del filesystem** (artifact escrito). Si el proceso muere abruptamente o el agente cierra el canal sin enviar exit signal, el run queda `running` para siempre. `log_streamer.py:168-186` tiene `reconcile_orphans()` que solo se llama **al arrancar** (`app.py:126-128`), con un cutoff de 1 hora, y no hay ningún daemon periódico que lo re-ejecute.

**Evidencia**
```python
# app.py:126-128
fixed = reconcile_orphans()
if fixed:
    logger.info("reconciled %d orphan executions", fixed)
```
```python
# log_streamer.py:168-186
def reconcile_orphans() -> int:
    cutoff = datetime.utcnow() - timedelta(hours=1)
    # Solo se llama una vez al startup
```
```python
# codex_cli_runner.py:114-123
thread = threading.Thread(
    target=_run_in_background,
    ...
    daemon=True,   # muere con Flask, sin cleanup de estado
    name=f"codex-cli-{execution_id}",
)
```

**Hipótesis descartadas**
- La detección de exit code está correctamente implementada para el caso normal. El problema es exclusivamente el caso de muerte abrupta del proceso o del hilo.

---

### Bug 5: Falta mecanismo robusto de sincronización filesystem ↔ execution.status ↔ UI

**Síntoma observado**: runs quedan perpetuamente en `running`. No hay reconciliación activa.

**Trazado end-to-end**

1. `ticket_status.py:287-434` — `recover_stale_running_tickets()` existe y funciona correctamente (tests pasan).
2. `ticket_status.py:437-442` — `stop_stale_recovery()` es un **no-op shim**:
```python
def stop_stale_recovery() -> None:
    """No-op compatibility shim — el recovery es on-demand, no hay thread que detener."""
    pass
```
3. El test `test_stale_recovery_guardian.py:219-242` espera que `schedule_stale_recovery(interval_seconds=1)` retorne un thread que corre periódicamente. Esa función **no existe en `ticket_status.py`** — los tests la importan pero fallará con `ImportError` al correr.
4. `pipeline_reconciler.py` tiene un reconciliador sofisticado que deriva estado desde filesystem, pero opera sobre `state.json` del pipeline (un JSON en disco), no sobre `AgentExecution` del backend Flask (SQLite). Son dos stores distintos sin sincronización.
5. `process_health_monitor.py` monitorea recursos (RAM, CPU, conexiones) de procesos batch — no está relacionado con el lifecycle de `AgentExecution`.
6. `sse_bus.py` (pipeline) y `log_streamer.py` (backend) son dos SSE buses distintos. El frontend escucha `log_streamer` del backend. El pipeline SSE bus no está conectado al frontend de Stacky Agents.

**Causa raíz**

`schedule_stale_recovery` es una función que los tests declaran como requisito pero que **nunca fue implementada** en `ticket_status.py`. El código de reconciliación existe (`recover_stale_running_tickets`) pero solo se ejecuta: (a) al startup si `STACKY_RECOVERY_ON_STARTUP=true`, y (b) via POST manual a `/api/tickets/recover-stale-status`. No hay daemon periódico.

**Evidencia**
```python
# ticket_status.py:437-442
def stop_stale_recovery() -> None:
    """No-op compatibility shim — el recovery es on-demand, no hay thread que detener.
    Existe para compatibilidad con tests que importan esta función.
    """
    pass
# NOTA: schedule_stale_recovery() no existe en este archivo
```
```python
# test_stale_recovery_guardian.py:222-223
from services.ticket_status import (
    schedule_stale_recovery,   # ImportError en runtime real
    stop_stale_recovery,
    ...
)
```

**[Bug adicional detectado] — `EXECUTION_TIMEOUT_MINUTES` con nombre incorrecto**

`ticket_status.py:302` usa `_os.getenv("EXECUTION_TIMEOUT_MINUTES", "120")` pero el test en `test_stale_recovery_guardian.py:26` setea `STACKY_EXECUTION_TIMEOUT_MINUTES`. La variable de entorno tiene prefijos distintos en test y en producción — el timeout nunca toma el valor del test por este typo.

```python
# ticket_status.py:302
timeout_minutes = int(_os.getenv("EXECUTION_TIMEOUT_MINUTES", "120"))
# test_stale_recovery_guardian.py:26
os.environ.setdefault("STACKY_EXECUTION_TIMEOUT_MINUTES", "30")
# El test importa STACKY_EXECUTION_TIMEOUT_MINUTES pero el código lee EXECUTION_TIMEOUT_MINUTES
```

---

## 2. Estado actual del sistema

| Componente | Estado | Conectado a backend Flask? |
|---|---|---|
| `log_streamer.py` — SSE de ejecución | Funcional | Si — via `/api/executions/<id>/logs/stream` |
| `log_streamer.reconcile_orphans()` | Solo en startup, cutoff 1h | Si — `app.py:126` |
| `ticket_status.recover_stale_running_tickets()` | Funcional, on-demand | Si — endpoint POST |
| `ticket_status.schedule_stale_recovery()` | **NO EXISTE** (solo en tests) | No |
| `pipeline_reconciler.py` | Funcional, sofisticado | No — opera sobre state.json pipeline |
| `pipeline_watcher.py` | Funcional — watchdog/polling | No — opera sobre flags del pipeline, no sobre `AgentExecution` |
| `process_health_monitor.py` | Funcional — métricas de batch | No — no relacionado con AgentExecution |
| `state_machine_verifier.py` | Funcional — verifica transiciones en batch | No — no relacionado con estados de AgentExecution |
| `sse_bus.py` (pipeline) | Funcional — SSE del pipeline dashboard | No conectado al frontend de Stacky Agents |
| `ado_task_creator.py` | Funcional — crea tasks en ADO | Solo via pipeline, no via backend Flask |
| `agent_completion.py` (gateway) | Funcional en modo shadow/on | Si — via `/api/tickets/<ado_id>/agent-completion` |
| `codex_cli_runner.py` | Funcional para caso normal | Si — via `/api/agents/open-chat` |
| `useExecutionStream.ts` | Funcional para caso normal | Si — EventSource directa |
| `FinishWorkButton.tsx` | Funcional | Si — endpoint `POST /finish-work` |
| `TicketGraphView.jsx` | Sin error boundary | Si |

---

## 3. Arquitectura propuesta

### 3.1 Execution State Machine determinista

Estados válidos de `AgentExecution.status`:

```
                    ┌─────────────────────────────────────────┐
                    │           Estado inicial                 │
                    └────────────────┬────────────────────────┘
                                     │ run_agent() / start_codex_cli_run()
                                     ▼
                               ┌─────────┐
                    ┌──────────│ running │──────────────────────────────────┐
                    │          └────┬────┘                                  │
                    │               │                                       │
            process.exited(0)       │ process.exited(!=0)         reconciler.timeout
            agent.completed()       │ agent.error()               reconciler.orphan
                    │               │                                       │
                    ▼               ▼                                       ▼
              ┌──────────┐    ┌─────────┐                          ┌───────────────┐
              │completed │    │  error  │◄─── cancel()             │    stale      │
              └────┬─────┘    └─────────┘                          │ (intermedio)  │
                   │                                               └───────┬───────┘
           operator.approve()                                              │
                   │                                              reconciler.recover()
                   ▼                                                       │
              ┌──────────┐                                                 ▼
              │ approved │                                          ┌───────────────┐
              └──────────┘                                          │    error      │
                                                                    └───────────────┘
```

Transiciones legales (validadas por `contract_validator` antes de persistir):

| Desde | Evento | Hacia | Responsable |
|---|---|---|---|
| `running` | `agent.completion_signal` | `completed` | `agent_runner._run_in_background` |
| `running` | `process.exit_code != 0` | `error` | `codex_cli_runner._run_in_background` |
| `running` | `operator.cancel()` | `cancelled` | `copilot_bridge.cancel()` |
| `running` | `reconciler.timeout > N min` | `error` | `ReconcilerDaemon` (nuevo) |
| `running` | `manifest.signals.work_completed` | `completed` | `FilesystemWatcher` (nuevo) |
| `error` | `operator.rescue()` | `running` | `rescue_execution.py` |
| `completed` | `operator.approve()` | `approved` | `/executions/<id>/approve` |

Estado `stale` es **transitorio e interno** al reconciler — no se persiste en DB (para no romper compatibilidad). El reconciler detecta `running` + ausencia de heartbeat/proceso y transiciona directamente a `error`.

### 3.2 Artifact Contract (MANIFEST.json schema)

Cada agente debe escribir (o actualizar) un `MANIFEST.json` en su workdir al completar. Este archivo es la fuente de verdad del run desde el punto de vista del filesystem.

**Path canónico**: `backend/data/codex_runs/<execution_id>/MANIFEST.json`

**Schema JSON (versión 1)**:
```json
{
  "$schema": "http://json-schema.org/draft-07/schema",
  "title": "StackyRunManifest",
  "version": "1",
  "type": "object",
  "required": ["schema_version", "run_id", "agent_type", "status", "written_at"],
  "properties": {
    "schema_version": { "type": "string", "enum": ["1"] },
    "run_id": { "type": "integer", "description": "AgentExecution.id" },
    "agent_type": { "type": "string" },
    "status": { "type": "string", "enum": ["running", "completed", "error", "cancelled"] },
    "written_at": { "type": "string", "format": "date-time" },
    "artifacts": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["path", "kind"],
        "properties": {
          "path": { "type": "string" },
          "kind": { "type": "string", "enum": ["output_html", "output_md", "task_json", "test_result", "other"] },
          "sha256": { "type": "string" },
          "size_bytes": { "type": "integer" }
        }
      }
    },
    "signals": {
      "type": "object",
      "properties": {
        "work_completed": { "type": "boolean" },
        "task_created_in_ado": { "type": "boolean" },
        "child_tickets": { "type": "array", "items": { "type": "integer" } },
        "ado_comment_published": { "type": "boolean" },
        "ado_state_updated": { "type": "string" }
      }
    },
    "heartbeat": {
      "type": "object",
      "properties": {
        "last_activity_ts": { "type": "string", "format": "date-time" },
        "pid": { "type": "integer" },
        "phase": { "type": "string" }
      }
    },
    "exit_code": { "type": ["integer", "null"] },
    "error_message": { "type": ["string", "null"] }
  }
}
```

**Regla de idempotencia**: si `MANIFEST.json` ya existe con `status=completed` y `run_id` coincide, el watcher no re-procesa. El reconciler lee el MANIFEST antes de aplicar corrección.

### 3.3 Filesystem Watcher

**Módulo nuevo**: `backend/services/manifest_watcher.py`

Extiende `pipeline_watcher.PipelineWatcher` (no duplicar) pero opera sobre `backend/data/codex_runs/*/MANIFEST.json` en lugar de `tickets_base/*.flag`.

**Justificación watchdog vs polling**: usar `watchdog` (ya en pipeline) cuando disponible, fallback a polling cada 2s. Para Windows la latencia de `watchdog` puede ser 500ms-2s por restricciones del filesystem NTFS; polling a 2s es equivalente en práctica pero más predecible.

```python
# backend/services/manifest_watcher.py — interfaz pública

class ManifestWatcher:
    """
    Observa backend/data/codex_runs/ para eventos MANIFEST.json.
    Al detectar status=completed, dispara on_manifest_complete(execution_id, manifest_data).
    """
    def __init__(self, runs_dir: Path, on_manifest_complete: Callable, poll_interval: float = 2.0):
        ...

    def start(self) -> None: ...
    def stop(self) -> None: ...

def start_manifest_watcher(app: Flask) -> ManifestWatcher:
    """Llamar desde create_app() para arrancar el watcher con el contexto de la app."""
    ...
```

**Integración con `app.py`**: agregar llamada en `create_app()` después de `init_db()`.

**Evento generado al detectar MANIFEST.json con status=completed**:
```python
# Llama a ticket_status.on_execution_end() con final_status="completed"
# Emite log_streamer.push(execution_id, "info", "manifest: work_completed detected")
# Cierra log_streamer.close(execution_id)
```

### 3.4 Reconciliation Daemon

**Módulo**: implementar `schedule_stale_recovery` en `backend/services/ticket_status.py` (actualmente ausente).

```python
# ticket_status.py — agregar estas funciones

_RECOVERY_THREAD: threading.Thread | None = None
_RECOVERY_STOP: threading.Event = threading.Event()

def schedule_stale_recovery(interval_seconds: int = 120) -> threading.Thread:
    """
    Lanza un daemon que ejecuta recover_stale_running_tickets() cada interval_seconds.
    Idempotente: si ya hay un thread activo, retorna el mismo.
    """
    global _RECOVERY_THREAD, _RECOVERY_STOP
    if _RECOVERY_THREAD and _RECOVERY_THREAD.is_alive():
        return _RECOVERY_THREAD
    _RECOVERY_STOP.clear()
    def _loop():
        while not _RECOVERY_STOP.wait(timeout=interval_seconds):
            try:
                recover_stale_running_tickets(trigger="reaper")
            except Exception as exc:
                logger.error("reaper cycle failed: %s", exc)
    _RECOVERY_THREAD = threading.Thread(target=_loop, daemon=True, name="stacky-reaper")
    _RECOVERY_THREAD.start()
    return _RECOVERY_THREAD

def stop_stale_recovery() -> None:
    """Detiene el daemon de recovery (real, no no-op)."""
    global _RECOVERY_THREAD
    _RECOVERY_STOP.set()
    if _RECOVERY_THREAD:
        _RECOVERY_THREAD.join(timeout=5)
    _RECOVERY_THREAD = None
    _RECOVERY_STOP.clear()
```

**Corrección de variable de entorno**: unificar a `STACKY_EXECUTION_TIMEOUT_MINUTES` en `ticket_status.py:302`.

**Integración con `app.py`**: llamar `schedule_stale_recovery()` en `create_app()` cuando `STACKY_RECOVERY_ON_STARTUP=true` o `STACKY_REAPER_ENABLED=true`.

### 3.5 Heartbeat Protocol

El agente (especialmente `codex_cli_runner`) escribe `heartbeat.json` en su run dir cada 30s mientras está vivo.

**Path**: `backend/data/codex_runs/<execution_id>/heartbeat.json`

```json
{
  "execution_id": 42,
  "last_activity_ts": "2026-05-15T10:00:00Z",
  "pid": 12345,
  "phase": "generating_output"
}
```

**Integración en `codex_cli_runner.py`**: agregar thread de heartbeat que escribe el archivo mientras `proc.poll() is None`.

**Umbral de stale**: si `now - heartbeat.last_activity_ts > STACKY_HEARTBEAT_TIMEOUT_MINUTES (default 10)`, el reconciler considera el run stale y aplica transición a `error`.

**Prioridad de detección** (reconciler, en orden):
1. MANIFEST.json con `status=completed/error` → transición inmediata.
2. Process vivo (`psutil.pid_exists(pid)`) → no intervenir.
3. Process muerto + heartbeat reciente (< 10 min) → dar gracia period.
4. Process muerto + heartbeat viejo (> 10 min) + execution en `running` → marcar `error`.
5. No heartbeat + execution en `running` + started_at > timeout → marcar `error`.

### 3.6 Event Bus & SSE

**No hay que crear un nuevo bus**. El backend Flask ya tiene `log_streamer.py` con SSE bien implementado. El `sse_bus.py` del pipeline es independiente y no debe mezclarse.

**Cambio necesario**: agregar eventos de dominio al `log_streamer` para que el frontend pueda reaccionar sin solo-polling:

```python
# Nuevos event types en log_streamer.stream()
# Actualmente: "log", "ping", "completed"
# Agregar: "manifest_detected", "stale_recovery", "heartbeat_timeout"
```

**Topics propuestos** (dentro del stream SSE existente):
```
event: log       → línea de log normal
event: completed → ejecución terminó
event: ping      → heartbeat SSE (15s)
event: manifest_detected  → watcher detectó MANIFEST.json (nuevo)
event: stale_recovery     → reconciler corrigió estado (nuevo)
```

**Frontend**: `useExecutionStream.ts` debe agregar handlers para los nuevos tipos y hacer `qc.invalidateQueries` apropiado.

### 3.7 Frontend Graph View Hardening

**Cambios en `TicketGraphView.jsx`**:

1. **Error boundary** alrededor de `TicketNodeCard`:
```jsx
// Nuevo componente wrapper
class NodeErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { hasError: false }; }
  static getDerivedStateFromError() { return { hasError: true }; }
  render() {
    if (this.state.hasError) {
      return <div className={styles.nodeError}>Error al renderizar nodo — recargá la página</div>;
    }
    return this.props.children;
  }
}
// Uso: <NodeErrorBoundary key={ticket.id}><TicketNodeCard .../></NodeErrorBoundary>
```

2. **Corrección de condición FinishWorkButton** (`TicketGraphView.jsx:385`):
```jsx
// ANTES:
{!isEpic && !isClosed && isRunning && !inconsistency.isInconsistent && (

// DESPUÉS (mostrarlo cuando el ticket está stuck, no solo cuando está corriendo clean):
{!isEpic && !isClosed && ticket.stacky_status !== "completed" && (
  <FinishWorkButton
    ticket={ticket}
    disabled={isRunning && !inconsistency.isInconsistent}  // deshabilitar si está corriendo limpio
    ...
  />
)}
```

3. **`useExecutionStream.ts` — JSON guard y dedup**:
```typescript
const onLog = (e: MessageEvent) => {
  try {
    const data = JSON.parse(e.data);
    if (!data || typeof data !== "object") return;
    // Dedup por timestamp + message (previene duplicados en re-subscripción)
    setState((s) => {
      const key = `${data.timestamp}_${data.message}`;
      if (s.seenKeys?.has(key)) return s;
      return { ...s, lines: [...s.lines, data], seenKeys: new Set([...(s.seenKeys || []), key]) };
    });
  } catch { /* ignorar eventos no-JSON */ }
};
```

4. **SSE reconnection con backoff exponencial**:
```typescript
// Agregar a useExecutionStream.ts
const retryMs = useRef(1000);
es.onerror = () => {
  es.close();
  if (retryMs.current < 30000) {
    setTimeout(() => { /* re-crear EventSource */ }, retryMs.current);
    retryMs.current = Math.min(retryMs.current * 2, 30000);
  } else {
    setState((s) => ({ ...s, error: "stream error — recargá la página" }));
  }
};
```

### 3.8 Observabilidad forense

**Endpoint nuevo**: `GET /api/diag/execution/<id>`

```json
{
  "ok": true,
  "execution": { "id": 42, "status": "running", "started_at": "...", "agent_type": "developer" },
  "ticket": { "id": 5, "ado_id": 27698, "stacky_status": "running" },
  "manifest": { "exists": true, "status": "completed", "signals": { "work_completed": true } },
  "heartbeat": { "exists": true, "last_activity_ts": "...", "age_seconds": 45 },
  "process": { "pid": 12345, "alive": false },
  "logs_count": 142,
  "recovery_history": [ { "kind": "execution_timeout", "at": "...", "trigger": "reaper" } ],
  "diagnosis": "process_dead_no_manifest_written",
  "recommended_action": "POST /api/tickets/recover-stale-status"
}
```

**`execution.jsonl` por run**: cada evento del lifecycle se append-only al archivo `backend/data/codex_runs/<execution_id>/events.jsonl`. Permite reconstrucción forense post-mortem sin acceso a SQLite.

**Métricas Prometheus-style** (via `/api/diag/metrics`):
```
stacky_executions_total{status="running"} 2
stacky_executions_total{status="completed"} 145
stacky_execution_duration_ms_p50 8500
stacky_stale_recoveries_total{trigger="reaper"} 3
stacky_manifest_detections_total 78
stacky_heartbeat_timeouts_total 1
```

---

## 4. Roadmap por fases

### Fase 0: Preflight — cableo de módulos huérfanos

**Duración**: 3-4 días  
**Objetivo**: arreglar bugs críticos de infraestructura que bloquean las demás fases.

**Entregables**:
- `backend/services/ticket_status.py`: implementar `schedule_stale_recovery()` y `stop_stale_recovery()` (reemplazar no-op).
- Corregir variable de entorno `EXECUTION_TIMEOUT_MINUTES` → `STACKY_EXECUTION_TIMEOUT_MINUTES`.
- `app.py`: llamar `schedule_stale_recovery()` cuando `STACKY_REAPER_ENABLED=true` (default: `true`).
- Ejecutar test suite de `test_stale_recovery_guardian.py` para confirmar que todos los casos pasan (actualmente fallan por `ImportError`).

**Criterios de aceptación**:
- `schedule_stale_recovery(interval_seconds=1)` retorna un `threading.Thread` vivo.
- `test_schedule_stale_recovery_runs_periodically` pasa sin modificar el test.
- `test_schedule_stale_recovery_is_idempotent` pasa.
- `STACKY_EXECUTION_TIMEOUT_MINUTES=5` es respetado por `recover_stale_running_tickets`.

**Riesgos**:
- El reaper periódico puede causar race conditions si el timeout es muy corto en desarrollo. Mitigación: `STACKY_REAPER_ENABLED=false` en dev por defecto, `true` en producción.

**Rollback**: setear `STACKY_REAPER_ENABLED=false`.

---

### Fase 1: Artifact Contract + Manifest Watcher + State Machine

**Duración**: 5-7 días  
**Objetivo**: cerrar Bug #4 parcialmente (caso Codex CLI).

**Entregables**:
- `backend/services/manifest_watcher.py`: `ManifestWatcher`, `start_manifest_watcher()`.
- `backend/services/manifest_schema.json`: schema JSON v1 del MANIFEST.
- `codex_cli_runner.py`: escribir `MANIFEST.json` al completar con `status=completed/error`.
- `codex_cli_runner.py`: agregar thread de heartbeat que escribe `heartbeat.json` cada 30s.
- `app.py`: llamar `start_manifest_watcher()` en `create_app()`.
- Tests: `backend/tests/test_manifest_watcher.py` (unit + integración).

**Criterios de aceptación**:
- Al finalizar un run de codex_cli, existe `backend/data/codex_runs/<id>/MANIFEST.json` con `status=completed`.
- El watcher detecta el MANIFEST en < 5s y llama `ticket_status.on_execution_end()`.
- El reconciler (Fase 0) detecta un run sin heartbeat después del umbral y lo marca `error`.

**Dependencias**: Fase 0 completa.

**Riesgos**: escritura de MANIFEST puede fallar si el disco está lleno. Mitigación: write en try/except, no bloquear la completion del agente.

**Rollback**: feature flag `STACKY_MANIFEST_WATCHER_ENABLED=false`.

---

### Fase 2: Frontend Graph View Hardening

**Duración**: 3-4 días  
**Objetivo**: cerrar Bug #1 y hacer robusta la UI.

**Entregables**:
- `TicketGraphView.jsx`: `NodeErrorBoundary` alrededor de `TicketNodeCard`.
- `useExecutionStream.ts`: guard JSON, dedup por key, backoff exponencial.
- `TicketGraphView.jsx`: corrección de condición `FinishWorkButton` (Bug #2 parcial).
- Tests: `frontend/src/hooks/useExecutionStream.test.ts` (vitest/jest).

**Criterios de aceptación**:
- Un nodo que lanza durante render muestra fallback sin blanquear toda la vista.
- `useExecutionStream` no duplica logs en re-subscripción.
- El SSE reconnecta automáticamente con backoff hasta 30s.

**Dependencias**: ninguna (puede hacerse en paralelo con Fase 1).

**Riesgos**: cambio en JSX de `TicketGraphView.jsx` puede afectar posicionamiento de SVG connectors. Testear con múltiples epics.

**Rollback**: revert del PR.

---

### Fase 3: FinishWork Selector + Agent Completion Idempotente

**Duración**: 4-5 días  
**Objetivo**: cerrar Bug #2 completamente y Bug #3.

**Entregables**:
- `TicketGraphView.jsx`: nueva condición de visibilidad de `FinishWorkButton` (basada en `stacky_status != completed` en lugar de `isRunning && !inconsistency`).
- `TicketBoard.tsx`: unificar condición con graph view.
- `agent_runner.py`: inyectar context block `filesystem-artifacts-status` antes de invocar al agente si existe `MANIFEST.json` o `pending-task.json`.
- `backend/services/artifact_context.py` (nuevo): genera el context block de estado de artifacts.
- `ado_task_creator.py` (pipeline): escribir sentinel `CHILD_TASKS_CREATED.json` al crear tasks en ADO.
- Tests: `backend/tests/test_artifact_context.py`.

**Criterios de aceptación**:
- `FinishWorkButton` es visible en cualquier ticket con `stacky_status != completed` (no solo cuando `isRunning`).
- Al invocar el agente, si `MANIFEST.json` existe con `signals.task_created_in_ado=true`, el context block informativo lo indica.
- `POST /api/executions/<id>/finish` devuelve 409 si `manifest.signals.work_completed=false` y `dry_run=false`.

**Dependencias**: Fase 0 para que el status sea confiable.

---

### Fase 4: Reconciliation Daemon + Heartbeat + Recovery Automático

**Duración**: 5-7 días  
**Objetivo**: cerrar Bug #5 completamente y Bug #4 residual (casos no-Codex-CLI).

**Entregables**:
- `ticket_status.py`: `schedule_stale_recovery()` ya funcionando (Fase 0) + integración con heartbeat check.
- `backend/services/heartbeat_monitor.py` (nuevo): lee `heartbeat.json` y evalúa si el proceso está vivo.
- `agent_runner.py`: hilo de heartbeat para ejecuciones vía Copilot bridge (no solo Codex CLI).
- `app.py`: wiring completo del reaper + manifest watcher + heartbeat monitor.
- Endpoint nuevo: `GET /api/diag/execution/<id>` (observabilidad forense).
- Tests: `backend/tests/test_heartbeat_monitor.py`, `backend/tests/test_reconciler_integration.py`.

**Criterios de aceptación**:
- Un run que no recibe heartbeat en 10 minutos es marcado `error` por el reaper.
- `GET /api/diag/execution/<id>` devuelve diagnosis correcta.
- `recover_stale_running_tickets(trigger="reaper")` corre cada 120s (configurable).

**Dependencias**: Fases 0 y 1.

---

### Fase 5: Observabilidad forense + dashboards + SLOs

**Duración**: 3-4 días  
**Objetivo**: instrumentar métricas para detectar regresiones.

**Entregables**:
- `backend/api/diag.py` (nuevo): blueprint con `/api/diag/execution/<id>` y `/api/diag/metrics`.
- `backend/data/codex_runs/<id>/events.jsonl`: append-only event log por run.
- Documentación de umbrales: `docs/OBSERVABILITY.md`.

**Criterios de aceptación**:
- `/api/diag/metrics` retorna conteos de ejecuciones por estado.
- `events.jsonl` tiene al menos 3 eventos por run: `started`, `heartbeat`, `completed/error`.

**Dependencias**: Fases 1 y 4.

---

## 5. Métricas, SLOs y alertas

| Métrica | SLO | Alerta |
|---|---|---|
| `stacky_executions_total{status="running"}` | < 3 runs en running simultáneamente | Alert si > 5 por 10 min |
| Tiempo promedio de ejecución | p50 < 15 min, p99 < 60 min | Alert si p50 > 20 min |
| `stacky_stale_recoveries_total` | < 2 por hora en estado estable | Alert si > 5 en 1h |
| `stacky_heartbeat_timeouts_total` | 0 en condiciones normales | Alert en primer timeout |
| `stacky_manifest_detections_total` | > 0 si hay runs completados | Monitor diario |
| Runs en `running` > 2h | 0 | Alert inmediato |

---

## 6. Apéndices

### A. MANIFEST.json — ejemplo completo

```json
{
  "schema_version": "1",
  "run_id": 42,
  "agent_type": "functional",
  "status": "completed",
  "written_at": "2026-05-15T10:30:00Z",
  "artifacts": [
    {
      "path": "Agentes/outputs/27698/comment.html",
      "kind": "output_html",
      "sha256": "abc123...",
      "size_bytes": 8420
    },
    {
      "path": "Agentes/outputs/27698/pending-task.json",
      "kind": "task_json",
      "sha256": "def456...",
      "size_bytes": 1250
    }
  ],
  "signals": {
    "work_completed": true,
    "task_created_in_ado": false,
    "child_tickets": [],
    "ado_comment_published": false,
    "ado_state_updated": null
  },
  "heartbeat": {
    "last_activity_ts": "2026-05-15T10:29:50Z",
    "pid": 12345,
    "phase": "writing_manifest"
  },
  "exit_code": 0,
  "error_message": null
}
```

### B. Eventos SSE propuestos

```
id: 1
event: log
data: {"timestamp":"2026-05-15T10:00:01Z","level":"info","message":"start codex cli runtime"}

id: 2
event: manifest_detected
data: {"execution_id":42,"status":"completed","signals":{"work_completed":true},"detected_at":"2026-05-15T10:30:01Z"}

id: 3
event: completed
data: {"type":"completed"}
```

### C. Decision log

| Decisión | Alternativa descartada | Justificación |
|---|---|---|
| Extender `pipeline_watcher.py` para MANIFEST en lugar de crear watchdog nuevo | Watchdog nuevo independiente | Evita duplicación; `pipeline_watcher` ya maneja fallback polling |
| `schedule_stale_recovery` en `ticket_status.py` (no en servicio separado) | Servicio Python separado | El recoverer ya lee `AgentExecution` vía SQLAlchemy; mismo contexto |
| Feature flags `STACKY_*` para cada componente nuevo | Feature flags en DB | Los flags de entorno son reversibles sin migración |
| Heartbeat en archivo JSON (no en DB) | Columna `last_heartbeat_at` en `agent_executions` | Evita migraciones de schema; legible externamente por el watcher |
| Corregir condición `FinishWorkButton` a `stacky_status != completed` | Condición basada en MANIFEST | El MANIFEST no existe hasta Fase 1; la corrección de UI debe ir en Fase 0/2 |
| Mantener `log_streamer.py` como único SSE del backend | Integrar `sse_bus.py` del pipeline | Los dos sistemas tienen stores distintos; mezclarlos generaría acoplamiento |

### D. Archivos clave a crear/modificar (índice rápido)

**Fase 0**:
- `backend/services/ticket_status.py` — implementar `schedule_stale_recovery()` / `stop_stale_recovery()`
- `backend/services/ticket_status.py:302` — corregir env var `EXECUTION_TIMEOUT_MINUTES` → `STACKY_EXECUTION_TIMEOUT_MINUTES`
- `backend/app.py` — wiring del reaper

**Fase 1**:
- `backend/services/manifest_watcher.py` (nuevo)
- `backend/services/manifest_schema.json` (nuevo)
- `backend/services/codex_cli_runner.py` — escritura de MANIFEST + heartbeat thread

**Fase 2**:
- `frontend/src/components/TicketGraphView.jsx` — NodeErrorBoundary + condición FinishWorkButton
- `frontend/src/hooks/useExecutionStream.ts` — JSON guard + dedup + backoff

**Fase 3**:
- `frontend/src/components/TicketGraphView.jsx` — condición final FinishWorkButton
- `frontend/src/pages/TicketBoard.tsx` — unificar condición
- `backend/services/artifact_context.py` (nuevo)
- `backend/agent_runner.py` — inyección de artifact context block

**Fase 4**:
- `backend/services/heartbeat_monitor.py` (nuevo)
- `backend/agent_runner.py` — heartbeat thread
- `backend/app.py` — wiring completo

**Fase 5**:
- `backend/api/diag.py` (nuevo)
- Registro en `backend/api/__init__.py`
