# Plan — Vista "Desatascador de tickets" + Fix FunctionalAnalyst v2.0.0

**Fecha:** 2026-06-01
**Autor:** Stacky (asistido)
**Objetivo del operador:**
1. Disponer de una vista donde estén todos los tickets en ejecución del copilot. Al
   refrescar, detectar si cada ticket tiene todos los archivos necesarios para
   terminar (comment.html / pending-task.json + plan) y permitir, con un botón,
   generar el **comentario** o crear la **Task** en ADO con los archivos ya
   producidos — sin frenar al dev (degradación graceful / desatascador).
2. Corregir el bug detectado en el Epic ADO "3 EP 01": `FunctionalAnalyst v2.0.0`
   propuso **3 Tasks** cuando debía proponer **1** (debe agrupar como hacía
   `AnalistaFuncionalPacifico`) y además **no creó la Task**.

---

## Diagnóstico

### Bug FunctionalAnalyst (over-split + no crea task)

Comparando los dos `.agent.md` (`backend/Stacky/agents/`):

- `AnalistaFuncionalPacifico.agent.md` (v1.2.0) tiene **reglas de extracción
  explícitas** en su protocolo:
  - Divide `System.Description` por `<hr><h2>`; cada fragmento posterior = 1 RF.
  - **"Si no existe ningún `<hr><h2>` en la descripción, trata el contenido
    íntegro como un único requisito."** ← guardrail anti-sobre-división.
  - "Conserva el ID original RF-XXX. No renumeres."
  - "Muestra la lista de requisitos extraídos y **confirma el total** antes de
    iniciar el bucle."
- `FunctionalAnalyst.agent.md` (v2.0.0) sólo dice *"extraer cada RF-XXX (fragmento
  HTML separado por `<hr><h2>`). Mismo protocolo de extracción que el agente
  legacy"* — **sin** el fallback de requisito único ni la confirmación de total.

→ Cuando el Epic no viene limpiamente segmentado por `<hr><h2>`, v2.0.0 infiere y
**sobre-divide** (3 RFs/Tasks en lugar de 1).

"Tampoco creó la Task" es **comportamiento de diseño**: ambos agentes sólo
escriben `pending-task.json` (delegación exclusiva a Stacky). La creación es
manual vía `POST /by-ado/{epic}/create-child-task`. La nueva vista cierra ese gap
operativo.

### Estado del backend (ya existe)

- `GET /api/tickets/by-ado/{ado_id}/pending-tasks` — pendientes por Epic.
- `GET /api/tickets/by-ado/{ado_id}/artifact-status` — diagnóstico por Epic.
- `POST /api/tickets/by-ado/{ado_id}/create-child-task` — crea Task hija.
- `POST /api/tickets/{id}/finish-work` — publica comment.html y/o cambia estado.

Falta una vista **agregada a nivel board** (cross-epic/cross-ticket) que liste
todo lo "en ejecución" + readiness de artifacts.

---

## Cambios

### 1. Fix `FunctionalAnalyst.agent.md` (bug de sobre-división)

Archivo: `Stacky Agents/backend/Stacky/agents/FunctionalAnalyst.agent.md`

- En **Paso A.1**, reemplazar la línea vaga por las reglas de extracción
  explícitas portadas de `AnalistaFuncionalPacifico`:
  - Delimitador `<hr><h2>`; primer fragmento = encabezado de la épica (descartar).
  - **Fallback:** si no hay `<hr><h2>`, todo el contenido = **un único requisito**.
  - Conservar IDs `RF-XXX`, no renumerar.
  - Mostrar la lista de RFs extraídos y **confirmar el total** antes del bucle.
  - Nota de no inventar/duplicar RFs: 1 `pending-task.json` por RF real, ni más.
- Bump de versión a `2.0.1`; actualizar `generated_by` del payload y el footer.

### 2. Backend — endpoint agregado `GET /api/tickets/unblocker-board`

Archivo: `Stacky Agents/backend/api/tickets.py`

Devuelve, por cada ticket "en ejecución" o con artifacts en disco:

- Datos del ticket (`id`, `ado_id`, `title`, `work_item_type`, `ado_state`,
  `stacky_status`, `ado_url`).
- `running`: hay `AgentExecution.status == running` o `stacky_status == running`.
- `comment`: `{ exists, path, size_bytes }` para `Agentes/outputs/{ado_id}/comment.html`.
- `pending_tasks`: lista `{ rf_id, title, pending_task_path, plan_exists, status }`
  + `total_pending`, `total_consumed` (scan de `epic-{ado_id}/`).
- `readiness`: `task_ready | comment_ready | waiting_files | artifacts_idle`.
- `blockers`: lista de razones legibles si está corriendo pero sin archivos.
- `last_execution`: `{ id, agent_type, status, started_at }`.

Filtra por proyecto activo (`?project=`). Incluye un ticket si: está corriendo,
o tiene `comment.html`, o tiene `pending-task.json` pendientes.

### 3. Frontend — Vista "Desatascador"

- `frontend/src/api/endpoints.ts`: `Tickets.unblockerBoard(project?)` + tipos
  `UnblockerItem` / `UnblockerBoardResponse`.
- `frontend/src/pages/UnblockerPage.tsx` (+ `.module.css`): tabla/cards de items,
  botón **Refrescar** (re-fetch + detección de readiness), badges de estado y por
  fila:
  - **Crear Task(s) en ADO** → reusa `CreateChildTaskButton` (epics con pendientes).
  - **Generar comentario en ADO** → `Tickets.finishWork` con `publish_to_ado`
    (tickets con `comment.html`).
- `frontend/src/App.tsx`: nuevo tab `unblocker` → `/unblocker` ("🧹 Desatascador").

### 3.bis Automatización (la creación/publicación es automática; el desatascador es fallback)

Aclaración del operador (2026-06-01): la detección y creación de Task /
publicación de comentario debe ser **automática**; el desatascador es sólo un
fallback puntual.

- El `output_watcher` (Mode A) ya tenía `_auto_create_pending_tasks` (flag
  `STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS`, default ON) pero estaba **gateado
  detrás de un `AgentExecution` running**: si el agente corría fuera del tracking
  de Stacky o su execution ya estaba cerrada, Mode A hacía `return` temprano y
  **nunca** llegaba a auto-crear → ese era el "no me creó la task".
- Fix (`services/output_watcher.py::_process_mode_a`): la auto-creación ahora se
  ejecuta **antes** del gate de execution, directamente desde el scan de disco
  (estable por mtime/done-marker). Es best-effort e idempotente (create-child-task
  marca `consumed`) y **no bloquea** el cierre del run. El cierre de la execution
  sigue requiriendo un run vivo. Si auto-create falla por error transitorio y no
  hay run que cerrar, no se cachea el mtime → reintenta en el próximo scan.
- Comentarios (Mode B) ya auto-publican incluso con execution terminal.

### 4. Tests

- `backend/tests/test_unblocker_board.py`: monta artifacts en `tmp_path`, fija
  `REPO_ROOT`, valida readiness (comment / pending / waiting).
- Contrato del agente: asserts de las nuevas reglas de extracción en
  `FunctionalAnalyst.agent.md` (fallback de requisito único + confirmar total).

---

## Verificación

- `pytest` de los nuevos tests + suite de tickets/contratos existente.
- Build de frontend (`tsc`/vite) sin errores de tipos.
- Smoke manual: tab Desatascador lista el Epic de prueba, botón crea la Task.
