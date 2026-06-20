# Stacky Output Watcher — plan de cierre automático para runs VSCode

> Generado: 2026-05-16
> Contexto: el flujo `/api/agents/open-chat` arranca el agente en VSCode Copilot Chat y la `AgentExecution` queda en `running` hasta que el agente PATCHea `/stacky-status`. Si el agente no llega al paso final o el PATCH falla, el run queda colgado para siempre. Este plan agrega un watcher de filesystem que cierra el run automáticamente cuando el agente deposita los artifacts esperados.

---

## 1. TL;DR

El agente Funcional (y los demás) escriben archivos en `Agentes/outputs/...` y luego están **obligados** a hacer `PATCH /api/tickets/by-ado/{ADO_ID}/stacky-status` con `status=completed`. Cuando ese PATCH falla (Flask caído, ado_publisher faltante, agente que no ejecutó el snippet PowerShell, etc.) el run queda en `running` indefinidamente.

Solución: un daemon que polea `Agentes/outputs/` y, cuando detecta artifacts terminales para una `AgentExecution` aún en `running`, dispara el mismo cierre que haría el PATCH. La policy de qué dispara el cierre depende del modo:

- **Modo B (comment.html)** → cierre inmediato + auto-publish a ADO (con dedupe por SHA256).
- **Modo A (pending-task.json en epic-*)** → cierre del Epic una vez que estabilizó (debounce) o explícitamente vía sentinel file.

---

## 2. Estado actual — flujo end-to-end

### Flow A — el agente PATCHea solo (camino feliz, ya funciona)

```
operador → /api/agents/open-chat → VSCode bridge → Copilot Chat
                              ↓
                  AgentExecution(status=running)
                              ↓
agente trabaja, escribe archivos en disco
                              ↓
agente ejecuta Invoke-RestMethod PATCH /stacky-status
                              ↓
backend marca execution=completed + dispara ado_publisher (auto-publish)
```

### Flow B — el agente no PATCHea (el bug actual)

```
operador → /api/agents/open-chat → Chat
                              ↓
                  AgentExecution(status=running)
                              ↓
agente trabaja, escribe archivos en disco
                              ↓
agente NO ejecuta el PATCH (no llegó al paso final, falló silente, etc.)
                              ↓
                  AgentExecution(status=running) ← FOREVER
```

Lo que las Fases 1+4 del plan de remediación **no resuelven**: el reaper de heartbeat (Caso C) no aplica porque el agente corre en VSCode (fuera de proceso), nunca escribió un heartbeat. El timeout absoluto (Caso B, 120 min) eventualmente cierra el run con `error`, pero pierde el output y la publicación.

---

## 3. Casuística — qué archivos produce cada modo

### Modo A — Análisis de Epic (Functional sobre Epic)

Por cada RF detectado en el Epic, el agente escribe:

```
Agentes/outputs/epic-{EPIC_ADO_ID}/{RF-XXX}-{slug}/
  ├── analisis-funcional.md
  ├── plan-de-pruebas.md
  └── pending-task.json
```

Salida operativa: el operador ve los `pending-task.json` listados por el endpoint `/by-ado/{epic_ado_id}/pending-tasks` y los crea en ADO uno a uno desde el botón **"Crear Tasks en ADO"** (UI que ya funciona). El watcher **NO debe** crear las Tasks en ADO automáticamente — ese gate sigue siendo del operador.

**No hay `comment.html`** en este modo. El Epic en sí no recibe un comentario en ADO.

### Modo B — Respuesta a ticket Blocked (Functional sobre Task Blocked, Developer, Technical, QA)

El agente escribe:

```
Agentes/outputs/{ADO_ID}/
  └── comment.html   ← lo que se publica como comentario en ADO
```

Salida operativa: server-side el `ado_publisher.publish_from_execution` postea el HTML como comentario nuevo en el work item ADO. Idempotencia DB-level por `(execution_id, html_sha256)` evita doble-publish.

### Casuística cruzada

| Agente | Modo típico | Output principal | Acción Stacky al cerrar |
|---|---|---|---|
| Functional | Epic (Modo A) | `pending-task.json` por RF | mark completed (sin publish) |
| Functional | Blocked (Modo B) | `comment.html` | mark completed + auto-publish |
| Technical | siempre | `comment.html` | mark completed + auto-publish |
| Developer | siempre | `comment.html` | mark completed + auto-publish |
| QA | siempre | `comment.html` | mark completed + auto-publish |
| Business | siempre | `comment.html` | mark completed + auto-publish |

Regla simple: **si hay `comment.html` para el `ado_id` del ticket, es Modo B. Si hay `pending-task.json` en `epic-{ado_id}/*/`, es Modo A.** Los dos pueden coexistir (un Epic con análisis y un comment al mismo tiempo). En la práctica del actual prompt, no coexisten — pero el código no debe asumirlo.

---

## 4. Diseño del watcher

### 4.1 Módulo nuevo

`backend/services/output_watcher.py` — daemon `AdoOutputWatcher` con la misma forma que `ManifestWatcher` (Fase 1):

```python
class AdoOutputWatcher:
    def __init__(self, outputs_dir: Path, poll_interval=3.0): ...
    def start(self) -> threading.Thread: ...
    def stop(self) -> None: ...
    def scan_once(self) -> dict[str, int]:  # {comment_html: N, pending_task: M}
        ...
```

Singleton `start_output_watcher(...)` / `stop_output_watcher()`. Wiring desde `app.create_app()` detrás de `STACKY_OUTPUT_WATCHER_ENABLED` (default `true`).

### 4.2 Algoritmo por scan

Para cada subcarpeta de `Agentes/outputs/`:

```
outputs/
├── 122/                ← Modo B candidate (sólo si comment.html dentro)
├── 149/                ← Modo B candidate
├── epic-149/           ← Modo A candidate (RFs dentro)
│   ├── RF-001-.../pending-task.json
│   └── RF-002-.../pending-task.json
```

1. Si el dir es `epic-{N}` → **Modo A**, procesar como Epic con N=ado_id.
2. Si el dir es solo `{N}` → **Modo B**, procesar como ticket con N=ado_id.
3. Cualquier otra cosa → ignorar.

### 4.3 Modo B — trigger inmediato por `comment.html`

```python
for dir in outputs_dir.iterdir():
    if not dir.name.isdigit(): continue
    ado_id = int(dir.name)
    comment = dir / "comment.html"
    if not comment.is_file(): continue
    self._maybe_close_mode_b(ado_id, comment)
```

`_maybe_close_mode_b`:
1. Stat → `(mtime_ns, size)`. Cache visto previamente — skip si no cambió.
2. Si el archivo se modificó hace < `STABLE_DELAY_SECONDS` (default 2.0s), espera próxima ronda (anti-write-en-curso).
3. Leer bytes, calcular SHA256.
4. Query DB:
   - Buscar ticket por `ado_id`. Si no existe → skip + log.
   - Buscar última `AgentExecution(running)` para ese ticket. Si no hay → skip + log "comment.html sin execution running".
   - Buscar `AgentHtmlPublish` con `(execution_id, html_sha256)` exacto. Si existe → ya se cerró + auto-publish ese exec antes; cachear visto y skip.
   - Verificar `mtime_file > execution.started_at - 5s` (margen de relojes). Si no, el archivo es de un run viejo → log + skip.
5. Disparar el cierre — **reutilizar exactamente el path que hace el PATCH endpoint para `status=completed` + `html_output_path`**:
   - `_mark_terminal(execution_id, status="completed")` + `ticket_status.on_execution_end(...)`
   - `ado_publisher.publish_from_execution(...)` con `triggered_by="output_watcher"`
   - Log a `system_logs` con un nuevo event_type `output_watcher.mode_b_close`.
6. Cachear `(path, mtime, sha256)` para la próxima ronda.

### 4.4 Modo A — trigger con debounce por `pending-task.json`

```python
for dir in outputs_dir.iterdir():
    if not dir.name.startswith("epic-"): continue
    try: epic_ado_id = int(dir.name[5:])
    except ValueError: continue
    self._maybe_close_mode_a(epic_ado_id, dir)
```

`_maybe_close_mode_a`:
1. Listar `pending-task.json` bajo `dir/*/pending-task.json`. Si vacío → skip.
2. Calcular `max_mtime` entre todos los `pending-task.json` + sus carpetas hermanas (`analisis-funcional.md`, `plan-de-pruebas.md`).
3. **Debounce**: si `now - max_mtime < STABLE_DELAY_SECONDS_MODE_A` (default 30s) → skip, esperá a que el agente termine de escribir todos los RFs.
4. Query DB:
   - Buscar ticket Epic por `ado_id=epic_ado_id`. Si no existe o no es `work_item_type=Epic` → skip + warning.
   - Buscar última `AgentExecution(running)` para ese ticket. Si no hay → skip.
   - Buscar `TicketStatusEvent` reciente con `reason LIKE '%output_watcher.mode_a%'` para esta execution_id. Si existe → ya cerrado, skip.
5. Disparar cierre:
   - `_mark_terminal(execution_id, status="completed")` + `ticket_status.on_execution_end(...)` con metadata `{"output_watcher": "mode_a", "pending_tasks_count": N}`.
   - **NO** dispara ado_publisher (no hay comment.html para Epics en Modo A).
   - **NO** dispara create-child-task automáticamente — sigue siendo gate del operador.
6. Cachear el set de paths con mtime — no re-disparar si el agente reescribe pending-task.json en una corrida posterior **para el mismo execution_id**. Si arranca un NUEVO execution sobre el mismo Epic, los timestamps y la nueva execution row evitan el dedupe falso.

### 4.5 Path de cierre unificado

Para no duplicar lógica del PATCH endpoint, extraer una helper a `services/agent_completion_internal.py`:

```python
def close_running_execution(
    *,
    execution_id: int,
    final_status: str,
    html_output_path: str | None = None,
    publish: bool = False,
    triggered_by: str = "internal",
    metadata: dict | None = None,
) -> CloseResult:
    """Path único de cierre — usado por PATCH /stacky-status, finish-work, output_watcher."""
    ...
```

Este refactor es opcional para Fase 1 del watcher pero altamente recomendado para que no haya tres copias del cierre divergiendo.

---

## 5. Idempotencia y dedupe

### 5.1 Modo B

- **DB-level**: tabla `agent_html_publish` ya tiene `UNIQUE(execution_id, html_sha256)`. Si el watcher dispara y luego el agente PATCHea (race), uno de los dos gana — el otro recibe `IntegrityError` y se trata como `skipped=true` (ya implementado en `publish_from_execution`).
- **In-memory**: cache `(path, mtime_ns)` del watcher para no re-leer/parsear archivos sin cambios.

### 5.2 Modo A

- **DB-level**: `TicketStatusEvent` con `changed_by='system:output_watcher:mode_a'`. Si ya existe uno para `execution_id` con `new_status='completed'`, skip.
- **In-memory**: cache `epic_ado_id → (execution_id, last_close_ts)`.

### 5.3 Race entre PATCH del agente y watcher

Caso: el agente PATCHea casi al mismo tiempo que el watcher detecta el archivo.

- Si el PATCH gana: `execution.status='completed'`. El watcher luego encuentra que ya no está `running` y no hace nada. ✓
- Si el watcher gana: marca `completed`. El PATCH luego encuentra `current_stacky=completed` y devuelve 409 (lo que ya hace el endpoint hoy). El agente loguea el 409 pero no es crítico — el ticket está cerrado. ✓

---

## 6. Edge cases

1. **`comment.html` viejo, run nuevo**: mitiga el check `mtime_file > execution.started_at`.
2. **Agente sigue escribiendo (file open)**: mitiga el debounce de 2s (Modo B) / 30s (Modo A).
3. **Operador borra manualmente la carpeta `outputs/{ado_id}/`**: watcher no hace nada (sin archivo → sin acción).
4. **Operador edita `comment.html` con cambios externos**: nuevo SHA → watcher re-publica como comentario NUEVO en ADO. **Decisión a tomar**: ¿permitir esto o requerir flag explícito? Default sugerido: permitir, porque equivale a un "amendment" del operador.
5. **Múltiples runs en paralelo sobre el mismo ticket**: improbable porque `open-chat` evita duplicados (línea 357), pero el código del watcher elige siempre la última execution `running`.
6. **Ticket sin `ado_id` (interno)**: skip silente — el watcher solo opera sobre dirs cuyo nombre es `{int}` o `epic-{int}`.
7. **Filesystem en red lento (WSL/SMB)**: el cache de mtime evita re-stats costosos. Polling interval de 3s es tolerante.
8. **`agent_html_publish` ya tiene una row OK para el mismo SHA**: skip silente (ya publicado).
9. **`agent_html_publish` ya tiene una row `failed`**: ¿reintentar? Default sugerido: SÍ, porque la falla puede ser transitoria (ADO caído). Configurar via `STACKY_OUTPUT_WATCHER_RETRY_FAILED` (default `true`).
10. **Modo A: el agente terminó pero el operador borró un `pending-task.json` antes que el watcher pase**: si quedan otros pending-tasks, igual dispara el cierre. Si no queda ninguno (borrados todos), skip (no es modo A real).

---

## 7. Integración con app.py

```python
# Después del manifest_watcher armado en Fase 1
_output_watcher_enabled = os.getenv("STACKY_OUTPUT_WATCHER_ENABLED", "true").lower() == "true"
if _output_watcher_enabled:
    from services.output_watcher import start_output_watcher
    _output_watcher_interval = float(os.getenv("STACKY_OUTPUT_WATCHER_INTERVAL_SECONDS", "3.0"))
    start_output_watcher(poll_interval=_output_watcher_interval)
    logger.info("output watcher armed (interval=%.1fs)", _output_watcher_interval)
```

Env vars nuevos:

| Var | Default | Uso |
|---|---|---|
| `STACKY_OUTPUT_WATCHER_ENABLED` | `true` | Habilita el daemon |
| `STACKY_OUTPUT_WATCHER_INTERVAL_SECONDS` | `3.0` | Polling interval |
| `STACKY_OUTPUT_WATCHER_STABLE_DELAY_B` | `2.0` | Debounce Modo B |
| `STACKY_OUTPUT_WATCHER_STABLE_DELAY_A` | `30.0` | Debounce Modo A |
| `STACKY_OUTPUT_WATCHER_RETRY_FAILED` | `true` | Reintenta publish_from_execution si la row anterior es `failed` |

---

## 8. Failure modes

| Falla | Comportamiento del watcher | Mitigación |
|---|---|---|
| `ado_publisher` raises | Try/catch interno, marca execution `error` con razón | El operador puede re-ejecutar manualmente vía "Terminar trabajo" |
| DB locked | Catch + retry en próximo ciclo | Backoff implícito por polling interval |
| Filesystem unavailable | Catch IOError + log warning, no propaga | Próximo ciclo intenta de nuevo |
| Path symlink/loop | `iterdir()` no follows symlinks por default | OK |
| Watcher crashea | Daemon thread muere, logger.exception captura | Operador reinicia Flask o llama endpoint manual de recovery |

Rollback: setear `STACKY_OUTPUT_WATCHER_ENABLED=false` y reiniciar. El flujo PATCH del agente sigue funcionando.

---

## 9. Tests

`backend/tests/test_output_watcher.py` con setup `tmp_path + monkeypatch STACKY_REPO_ROOT`:

| Test | Caso |
|---|---|
| `test_mode_b_closes_running_execution_on_comment_html` | Path normal: nuevo comment.html → close + publish |
| `test_mode_b_skips_when_no_running_execution` | comment.html aparece pero no hay execution running → no-op |
| `test_mode_b_skips_when_html_sha_already_published` | Ya publicado mismo SHA → idempotente |
| `test_mode_b_respects_stable_delay` | mtime muy reciente → espera próxima ronda |
| `test_mode_b_skips_when_mtime_older_than_execution_start` | Archivo viejo + execution nueva → no-op |
| `test_mode_b_retries_after_publish_failed_row` | Row failed previa → retry permitido |
| `test_mode_a_closes_epic_execution_on_stable_pending_tasks` | pending-task.json estables → close del Epic execution |
| `test_mode_a_respects_long_stable_delay` | Archivos recién escritos → espera 30s |
| `test_mode_a_does_not_trigger_child_task_creation` | Watcher NO crea tasks en ADO automáticamente |
| `test_mode_a_skips_when_no_pending_tasks` | Carpeta epic-{ID} vacía → no-op |
| `test_mode_a_skips_when_already_closed_by_watcher` | Re-scan no re-cierra |
| `test_scan_handles_malformed_dir_names` | `outputs/foo/`, `outputs/epic-abc/` → ignorados sin error |
| `test_concurrent_close_with_patch_endpoint_safe` | PATCH y watcher simultáneos → uno gana, el otro 409, sin error |

---

## 10. Decisiones pendientes (necesito tu input)

1. **¿Modo A debe cerrar el Epic automáticamente o requerir confirmación del operador?**
   - **Opción 1 (recomendada)**: cerrar automático tras debounce. El operador ya tiene "Crear Tasks en ADO" para la siguiente acción.
   - Opción 2: el watcher solo notifica via SSE/system_log; el operador debe clickear un botón para confirmar.

2. **¿Re-publish si el operador edita `comment.html` manualmente?**
   - **Opción 1 (recomendada)**: nuevo SHA → re-publish como comentario nuevo en ADO (segunda iteración del análisis del agente — vista como amendment).
   - Opción 2: una sola publicación por execution; futuras ediciones requieren `force_finish` desde la UI.

3. **¿Debounce de Modo A: 30s suficiente o hace falta una señal explícita?**
   - **Opción 1 (recomendada)**: arrancar con 30s y monitorear false-positives.
   - Opción 2: pedir al agente que escriba un sentinel `_DONE.json` al final del Epic en una próxima versión del .agent.md, y el watcher dispara con ese signal en lugar de debounce.

4. **¿Crear la helper `close_running_execution` ahora o después?**
   - **Opción 1 (recomendada)**: ahora, porque el watcher es un tercer caller del cierre — sin la helper se duplica lógica.
   - Opción 2: duplicar ahora y refactorizar después.

5. **¿Loguear cada scan o solo cierres?**
   - **Opción 1 (recomendada)**: solo loguear cierres y skips relevantes (no cada scan vacío). Métricas via `/api/diag/metrics` con un nuevo counter `output_watcher.closes`.

6. **¿Modo A también debe disparar algo para tickets bloqueados?**
   - No. Modo A es exclusivo de Epics; el agente Funcional sobre tickets Blocked hace Modo B con `comment.html`.

---

## 11. Roadmap

- **Fase W1** (1-2 días): módulo `output_watcher.py` + helper `close_running_execution` + tests Modo B.
- **Fase W2** (1 día): tests Modo A + integración app.py.
- **Fase W3** (opcional, 1 día): endpoint `/api/diag/output-watcher` con stats (scans, closes Modo A, closes Modo B, skips por idempotencia).
- **Fase W4** (opcional): backfill — endpoint `POST /api/diag/output-watcher/scan-now` que dispara una pasada manual, útil para cerrar runs colgados después de bugs como el de hoy sin esperar 3s.

---

## 12. Lo que este watcher NO resuelve

- No crea Tasks en ADO automáticamente — sigue siendo gate del operador via UI.
- No detecta agentes que escribieron archivos parciales/corruptos (depende del agente generar HTML válido).
- No reemplaza al reaper Caso B (timeout absoluto) ni Caso C (heartbeat) — son redes de seguridad complementarias.
- No abre el chat en VSCode ni gestiona la sesión del operador en VSCode.
