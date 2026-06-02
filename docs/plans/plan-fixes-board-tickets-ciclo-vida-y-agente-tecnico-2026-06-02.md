# Plan — Fixes Vista Tickets ADO, Ciclo de Vida y Agente Técnico

**Fecha:** 2026-06-02
**Autor:** Stacky (asistido)
**Objetivo del operador:** corregir 7 bugs/mejoras reportados sobre la vista de Tickets
ADO, el ciclo de vida de las tareas (asignación + estado de cierre) y el
comportamiento de bloqueo del Agente Técnico.

Bugs reportados (texto original del operador):

1. **B1** — "Filtro de solo asignadas a mí no está funcionando".
2. **B2** — "Que se configure desde Stacky (que ya lo hace cuando creás un empleado)
   debe dejar la tarea en el estado estipulado cuando termina una tarea".
3. **B3** — "Cuando una tarea no tiene nadie asignado y alguien ejecuta un agente
   sobre esa task debe asignársela al que disparó el agente".
4. **B4** — "En Run Personalizado de la vista de tickets ADO, mejorar UI: el
   dropdown se ve todo blanco con letras blancas y no pega con la UI de Stacky Agents".
5. **B5** — "Run Sugerido solo funciona en las EPIC; luego no me sugiere ni
   Technical ni Developer".
6. **B6** — "Botón de cancelar run en la vista de tickets ADO para cancelar algún run".
7. **B7** — "El Agente Técnico, antes de realizar un bloqueo, debe preguntarle al
   humano cómo desbloquear".

---

## Resumen ejecutivo

| # | Área | Severidad | Archivos clave | Esfuerzo | Riesgo |
|---|------|-----------|----------------|----------|--------|
| B1 | Board · filtro | Media | `frontend/.../TicketBoard.tsx` (+ opcional backend) | Bajo | Bajo |
| B2 | Ciclo de vida · estado de cierre | **Alta** | `services/agent_completion_internal.py`, runners, `project_manager.py` | Medio-Alto | Medio |
| B3 | Asignación | Media | `api/agents.py` + helper nuevo, `ado_client.py` | Medio | Bajo-Medio |
| B4 | UI/CSS | Baja | `TicketBoard.module.css` / `theme.css` | Trivial | Muy bajo |
| B5 | Board · sugerencias | Media | `TicketGraphView.jsx`, `TicketBoard.tsx` (+ opcional backend) | Medio | Bajo-Medio |
| B6 | Board · control de runs | Media | `api/executions.py`, `TicketBoard.tsx` | Bajo-Medio | Bajo |
| B7 | Agente Técnico · bloqueo | **Alta** | `*.agent.md` ×2, `agents/technical.py` (+ opcional guard backend) | Medio | Medio (cambio de comportamiento) |

**Hallazgo transversal clave:** B1 y B3 dependen ambos de *resolver la identidad ADO
del operador* y *comparar contra el assignee del ticket de forma tolerante*. Ya
existe la maquinaria (`_resolve_me_unique_name`, `_user_matches`,
`update_work_item_assigned_to`); el plan la centraliza para no duplicar lógica de
matcheo de identidad. B2 y B7 comparten el canal de transición de estado ADO
(`target_ado_state` → `update_work_item_state`); se diseñan en conjunto para que B2
aplique el estado de éxito configurado y B7 cambie únicamente la rama de bloqueo.

---

## Diagnóstico

### B1 — Filtro "solo asignadas a mí" no funciona

- **UI del filtro:** checkbox "Mostrar todas las tareas" en
  `Stacky Agents/frontend/src/pages/TicketBoard.tsx:771-792`, estado `showAll`
  (default `true`) en línea 603. Desmarcar = modo "Mis tareas".
- **Predicado (sitio del bug):** `TicketBoard.tsx:659-669`. El filtrado es 100%
  client-side sobre la jerarquía, con comparación **cruda, sensible a
  mayúsculas/minúsculas y sin fallback**:

  ```ts
  const mine = (t: { assigned_to_ado?: string | null }) =>
    (t.assigned_to_ado ?? null) === myUniqueName;   // ← === crudo
  ```

- **Identidad del operador:** `myUniqueName = adoUser?.linked ? adoUser.ado_unique_name : null`
  (`TicketBoard.tsx:648-654`), que viene de `GET /api/tickets/ado-user`
  (`backend/api/tickets.py:2907-2970`) → `AdoClient.get_authenticated_user()`
  (`backend/services/ado_client.py:342-374`), i.e. el **email** del `Account` del PAT
  (ej. `jluca@ubimia.com`).
- **Campo assignee en el dato:** `assigned_to_ado` (`frontend/src/types.ts:96`,
  `backend/models.py:63`), poblado en sync desde `System.AssignedTo.uniqueName`
  **con fallback a `.displayName`** (`backend/services/ado_sync.py:123-130` y
  `263-267`). O sea, el valor almacenado puede ser un email **o** un nombre para
  mostrar ("Juan L. Santoliquido").

**Causa raíz (hipótesis ordenadas):**
1. *(más probable)* mismatch `displayName` vs email: `assigned_to_ado` guarda el
   display name en tickets donde ADO no expone `uniqueName`, mientras `myUniqueName`
   es siempre el email → `"Juan L. Santoliquido" === "jluca@..."` → falso →
   **board vacío**.
2. diferencias de casing/dominio en `uniqueName` (`JLuca@` vs `jluca@`) → el `===`
   falla.
3. `myUniqueName === null` (PAT sin resolver / `linked:false`) → el filtro hace
   no-op (línea 661) → "no pasa nada al desmarcar".

El backend **ya tiene** un matcher tolerante para esto que el board **no usa**:
`_user_matches()` en `backend/api/adoption.py:40-48` (match exacto → si no, compara
el local-part antes de `@`, en minúsculas). El board tampoco usa el filtro backend
ya testeado (`Tickets.list(project, "me")`, `backend/api/tickets.py:287-296`,
test `test_tickets_assigned_filter.py`).

### B2 — El estado de transición configurado por empleado no se aplica al terminar

- **Config UI:** dropdown "Estado de transición al terminar" →
  `value.transition_state` en
  `Stacky Agents/frontend/src/components/AgentWorkflowForm.tsx:96-119` (usado por
  `EmployeeEditDrawer.tsx` y `TeamManageDrawer.tsx`).
- **Persistencia:** `PUT /projects/<p>/agent-workflow/<filename>`
  (`backend/api/projects.py:836-869`) → `project_manager.set_agent_workflow_config`
  (`backend/project_manager.py:408-420`) guarda en `config.json` bajo
  `agent_workflow_configs[<agent_filename>].transition_state`. Se lee de vuelta con
  `get_agent_workflow_config` (`project_manager.py:392-405`).

**Causa raíz:** la config se **guarda pero nunca se lee** en el cierre de tarea.
- El cierre real (producción) llama `ticket_status.on_execution_end(...)` **sin
  target_state**: `backend/agent_runner.py:612-617`,
  `services/claude_code_cli_runner.py:571-576`, `services/codex_cli_runner.py:445`,
  `services/manifest_watcher.py:293`, `services/qa_browser_runner.py:180`.
- `ticket_status.on_execution_end / set_status`
  (`backend/services/ticket_status.py:95-149, 213-265`) sólo actualiza el
  `stacky_status` **local**; **nunca** llama a ADO. El único post-hook registrado
  (`ado_publisher.ado_publish_post_hook`, `services/ado_publisher.py:373-398`)
  publica el comentario pero **no cambia el estado**.
- El único punto que sí puede transicionar (`close_execution_with_publish`,
  `services/agent_completion_internal.py:62-214`) exige que el caller pase
  `target_ado_state`, y los runners de producción **no lo invocan** (sólo
  `output_watcher.py:377-387` lo usa, tomando el valor del `comment.meta.json` que
  escribe el agente, no de la config).
- El "puente" previsto (`agent_completion._apply_workflow_transition`,
  `services/agent_completion.py:859-907`) hace `import services.ado_workflow`, módulo
  que **no existe** → siempre cae en `ImportError`; además el gateway está **apagado
  por default** (`STACKY_COMPLETION_GATEWAY`).
- `update_work_item_state(ado_id, new_state)` (`services/ado_client.py:846-857`) es
  la función real que mueve el estado; sus callers nunca derivan el valor desde
  `transition_state`.

→ En resumen: `transition_state` es **write-only**. Nada lo consume al terminar.

### B3 — Auto-asignar tarea sin responsable al que dispara el agente

- **Trigger frontend (punto único):** `launchAgentWithRuntime`
  (`frontend/src/services/agentLaunch.ts:105-153`) → `Agents.runWithOptions`
  (`POST /api/agents/run`) o `Agents.openChat` (`POST /api/agents/open-chat`). El
  payload **no incluye identidad de usuario**. Call sites: `TicketBoard.tsx:287, 496`,
  `AgentLaunchModal.tsx:235`, `useAgentRun.ts:28`.
- **Endpoint backend:** `POST /agents/run` (`backend/api/agents.py:187-294`) — ya
  conoce `ticket_id` + `project` y pasa `user=current_user()` a
  `agent_runner.run_agent(...)` (líneas 274-290). El path de GitHub Copilot es un
  endpoint **aparte**: `POST /agents/open-chat` (`agents.py:421-662`).
- **Identidad:** `current_user()` (`backend/api/_helpers.py:4-5`) devuelve
  `X-User-Email`, pero el frontend lo **hardcodea a `"dev@local"`**
  (`frontend/src/api/client.ts:37, 72`). La identidad **real del usuario no llega**.
  PERO la identidad **ADO del operador** sí es resoluble server-side (Stacky es
  single-operator por instancia): `_resolve_me_unique_name(project)`
  (`backend/api/tickets.py:182-200`) + `services/ado_identity.py`.
- **Infra ya existente (gran parte hecho):**
  - WRITE de assignee: `AdoClient.update_work_item_assigned_to(ado_id, unique_name)`
    (`services/ado_client.py:859-875`, requiere PAT scope `vso.work_write`).
  - Endpoint de asignación de referencia: `POST /api/tickets/<id>/assign`
    (`api/tickets.py:2718-2857`) — patrón completo (PATCH ADO + update local).
  - Check de "sin asignar": `ticket.assigned_to_ado is None`.

**Causa raíz / gap:** no existe ningún punto en el flujo de disparo que verifique
"¿el ticket está sin asignar?" y, si lo está, lo asigne al operador. La pieza
faltante es **cablear** la auto-asignación; la identidad se resuelve server-side
(no requiere cambio de frontend).

### B4 — Dropdown blanco-sobre-blanco en Run Personalizado

- **Modal:** `RunModal` inline en `TicketBoard.tsx:98-221`, abierto por el botón
  "⚙ Run Custom" (`TicketBoard.tsx:417-424`), renderizado por `createPortal` al body.
- **Dropdown culpable:** `<select className={styles.modalSelect}>` (Agente), sólo en
  `mode === "custom"`, `TicketBoard.tsx:155-163` — es un `<select>` **nativo**.
- **CSS:** `.modalSelect` en
  `Stacky Agents/frontend/src/pages/TicketBoard.module.css:635-646`. **No tiene
  `color-scheme`** ni regla `option`.
- **Tema:** GitHub Dark (`frontend/src/theme.css:3-46`); `--text-primary:#e6edf3`
  (casi blanco). El `:root` **no declara `color-scheme: dark`** (sólo lo hacen
  `TopBar.module.css` y `NewProjectModal.module.css`, a nivel componente).

**Causa raíz:** sin `color-scheme: dark`, el navegador pinta el popup nativo del
`<select>` con el esquema **claro** (fondo blanco), pero el texto de las `<option>`
hereda el `--text-primary` casi blanco → **blanco sobre blanco**. Es el bug clásico
de `<select>` nativo en tema oscuro. Patrón correcto a copiar:
`TopBar.module.css:82-92` (`.projectSelect` con `color-scheme: dark`) y
`NewProjectModal.module.css:67-78`.

### B5 — Run Sugerido sólo aparece en EPIC

La sugerencia se computa por **dos caminos distintos** según el tipo de ticket:

- **EPIC (hardcodeado, siempre funciona):** `epicPipelineSummary()` devuelve
  `next_suggested: "functional"` (`frontend/src/components/TicketGraphView.jsx:64-71`,
  usado en línea 307; en el árbol, botón "🔍 Funcional" hardcodeado en
  `TicketBoard.tsx:488, 546-561`).
- **No-EPIC (sólo FlowConfig — acá se rompe):** la sugerencia sale **exclusivamente**
  del mapa FlowConfig keyeado por `ado_state` (NO por tipo de ticket):
  `TicketGraphView.jsx:301-308` y `TicketBoard.tsx:252-264`:

  ```js
  const flowAgentType = !isEpic && ticket.ado_state
    ? (flowConfigMap.get(ticket.ado_state.trim().toLowerCase()) ?? null)
    : null;
  const next = isEpic ? summary.next_suggested : flowNext;  // ignora pipeline para no-epics
  ```

  El botón se deshabilita si `next` es falsy (`TicketBoard.tsx:403`,
  `TicketGraphView.jsx:466`).

**Causa raíz:** los tickets no-EPIC sólo reciben sugerencia si su `ado_state` exacto
está en una regla de FlowConfig. El seed default sólo cubre `New→business`,
`Active→developer`, `Code Review→qa`, `Resolved→qa`
(`backend/services/flow_config_store.py:57-62`). Un Feature/Technical/Task en un
estado no mapeado (ej. "To Do", "Technical review", "Committed") → `null` → botón
deshabilitado → **nunca sugiere Technical/Developer**. Agrava: la regla de
supresión `business` fuerza `null` en Tasks (`TicketBoard.tsx:262-263`,
`TicketGraphView.jsx:306`), así que un Task "New" tampoco sugiere nada.

Dato útil: `pipeline_status.get_pipeline_summary` (`services/pipeline_status.py:243-261`)
**ya** calcula un `next_suggested` por etapas (chain `business→functional→technical→
developer→qa`, `services/next_agent.py:34-40`) y se adjunta a **cada** ticket
(`tickets.py:256, 310`), pero el frontend **lo descarta a propósito** para no-epics.
La lógica además está **duplicada** entre el árbol (`.tsx`) y el grafo (`.jsx`,
vista default).

### B6 — Falta botón "Cancelar run" en la vista de tickets

**Gran parte ya existe.**
- **Endpoint:** `POST /api/executions/<id>/cancel`
  (`backend/api/executions.py:175-203`) — marca `status="cancelled"` y, según
  runtime, **mata el proceso CLI**.
- **Kill real:** `codex_cli` y `claude_code_cli` usan registry de procesos
  (`_PROCESSES`) + `proc.terminate()/kill()` (`services/codex_cli_runner.py:138-151`,
  `services/claude_code_cli_runner.py:156-190`). `github_copilot` es **cooperativo**
  vía flag in-memory (`copilot_bridge`), ya cableado en `agent_runner.py:618-634`.
- **Status `cancelled`** ya existe en todo el modelo
  (`models.py:212`; terminal set en `executions.py:215`).
- **API client:** `Executions.cancel(id)` ya existe (`frontend/src/api/endpoints.ts:607-608`).
- **`RunButton`** ya soporta estado `cancelling` + `onCancel`
  (`frontend/src/components/RunButton.tsx:4-22`).
- **Dónde se ve un run activo:** `TicketCard` en `TicketBoard.tsx:234-464`; el bloque
  `isRunning && !inconsistency` (`371-381`) ya renderiza `FinishWorkButton` y tiene
  `runningExecution.id` en scope.

**Gap real (chico):** el endpoint A **no** llama a
`ticket_status.on_execution_end(...)`, así que `Ticket.stacky_status` queda en
`running` hasta el próximo reconcile; y para `github_copilot` no dispara el flag
cooperativo. Falta también el botón en `TicketCard`. Hoy el único cancel desde UI es
indirecto (cerrar `CodexConsoleDock`, `:151`, o "Finish work").

### B7 — El Agente Técnico bloquea sin preguntar al humano

- **Definición del agente (2 capas):** persona Python `backend/agents/technical.py:35`
  ("Si detectás un bloqueante, lo declarás explícitamente…") y, lo que realmente
  corre, los prompts `.agent.md`:
  `Stacky Agents/backend/Stacky/agents/TechnicalAnalyst.agent.md` (legacy v1.2.0) y
  `TechnicalAnalyst.v2.agent.md` (v2.0.0). Copias desplegadas en
  `DeployStackyAgents/Stacky/agents/` y `DeployStackyAgents/github_copilot_agents/`.
- **Qué es "bloquear":** transicionar `System.State` del work item a "Blocked"
  (`tracker_state_machine.technical.blocked_state` en
  `backend/services/client_profile_defaults/azure_devops.json:53-70`, inyectado al
  prompt por `services/context_enrichment.py`). El PATCH real lo hace
  `ado_client.update_work_item_state` (`:846`).
- **Cómo bloquea hoy (autónomo):** el prompt (PASO 4 — legacy líneas 94-103, v2
  100-107) decide solo y emite `target_ado_state: "Blocked"` vía PATCH
  `/stacky-status` (`api/tickets.py:629-872`) y/o `comment.meta.json`
  (`services/output_watcher.py:637-661` → `agent_completion_internal.py:186-282`). El
  comentario de bloqueo recién le habla al humano **después** de bloquear ("Responder
  en este ticket y mover a Technical review", legacy líneas 312-314).
- **¿Existe un "pausar y preguntar" (HITL)?** **No, usable.** El chat es stateless
  (`api/chat.py`); la burbuja `question` de `ChatDrawer.tsx:24, 641-650` está
  **inerte** (`isActiveQuestion={false}`); `pause_after` de packs
  (`backend/packs/definitions.py:8`) es un gate entre agentes, no intra-run. El
  status terminal `needs_review` existe en el contrato pero no se produce/maneja.

**Causa raíz:** el bloqueo es una decisión **autónoma del prompt**, aplicada en el
mismo paso final, sin confirmación humana previa. El arreglo es **principalmente de
prompt** (la maquinaria de transición ya soporta dejar el ticket en el estado de
revisión en lugar de "Blocked").

---

## Cambios

> Orden sugerido de implementación: **B4 → B6 → B1 → B5 → B3 → B2 → B7**
> (de menor a mayor riesgo; B4/B6 son quick wins; B2/B7 son los de mayor impacto).

### B4 — Dropdown legible en Run Personalizado *(quick win)*

Archivo: `Stacky Agents/frontend/src/pages/TicketBoard.module.css`

- En `.modalSelect` (líneas 635-646) agregar `color-scheme: dark;` (fix primario,
  igual que `TopBar.module.css:82-92` / `NewProjectModal.module.css:67-78`).
- Robustez cross-browser (Firefox/Linux): agregar regla explícita de `option`:

  ```css
  .modalSelect option {
    background-color: var(--bg-elev);   /* #21262d */
    color: var(--text-primary);          /* #e6edf3 */
  }
  ```

- **Decisión abierta D-B4 (ver más abajo):** opción global recomendada — agregar
  `color-scheme: dark;` una sola vez al bloque `html, body, #root` de
  `frontend/src/theme.css:51-62`, que corrige este dropdown **y todos** los `<select>`
  nativos del app (ModelPicker, FlowConfig, ChatDrawer, EmployeeEditDrawer,
  EditProjectModal, etc.). Es la más consistente con un app dark-theme global.

### B6 — Botón "Cancelar run" en la vista de tickets

**(a) Backend — cerrar el gap de sincronización** en `cancel_execution`
(`Stacky Agents/backend/api/executions.py:175-203`): capturar `ticket_id`/`agent_type`
dentro del `session_scope`, y tras la rama por runtime:

```python
# github_copilot no tiene subproceso → disparar el flag cooperativo
if runtime not in ("codex_cli", "claude_code_cli"):
    import agent_runner
    agent_runner.cancel(execution_id)
# mantener Ticket.stacky_status en sync (hoy el endpoint A lo omite)
from services import ticket_status
ticket_status.on_execution_end(
    ticket_id=ticket_id, execution_id=execution_id,
    final_status="cancelled", agent_type=agent_type,
    reason_override="cancelado manualmente desde el board",
)
```

Esto deja un único endpoint correcto para los 3 runtimes y saca el ticket de
"running" de inmediato.

**(b) Frontend — botón en `TicketCard`** (`frontend/src/pages/TicketBoard.tsx`, en el
bloque `isRunning && !inconsistency.isInconsistent`, líneas 371-381, junto a
`FinishWorkButton`):

- Estado local `isCancelling`.
- Al click: `confirm("¿Cancelar el run en curso?")` → `Executions.cancel(runningExecution.id)`
  (guardar `runningExecution != null`) → invalidar queries:
  `["executions-active", project]`, `["tickets", project]`,
  `["tickets-hierarchy", project]` (claves que usa `useRunningStatus`).
- Manejar **409** (carrera: el run ya terminó) como toast suave, no como error.
- `github_copilot` cancela cooperativamente → mostrar "cancelando…" y confiar en el
  polling de 5 s para confirmar.
- Reusar `RunButton` con `onCancel`/`state="cancelling"` para consistencia visual;
  de paso, cablear `onCancel` en `InputContextEditor.tsx:146` (hoy queda inerte).

No requiere migración de modelo, ni endpoint nuevo, ni método de API nuevo.

### B1 — Filtro "solo asignadas a mí" tolerante

**Fix primario (frontend)** — `frontend/src/pages/TicketBoard.tsx:662-663`: reemplazar
el `===` crudo por una comparación normalizada que replique `_user_matches`
(minúsculas + trim + fallback a local-part antes de `@`):

```ts
const norm = (s?: string | null) => (s ?? "").trim().toLowerCase();
const localPart = (s?: string | null) => norm(s).split("@", 1)[0];
const mine = (t: { assigned_to_ado?: string | null }) => {
  const a = norm(t.assigned_to_ado), me = norm(myUniqueName);
  if (!a || !me) return false;
  return a === me || localPart(t.assigned_to_ado) === localPart(myUniqueName);
};
```

**Soporte recomendado (consistencia de datos):**
- `backend/services/ado_sync.py:126, 265`: normalizar `assigned_to_ado` a
  `uniqueName` en minúsculas de forma consistente y evitar mezclar `displayName`
  (es lo que hace frágil cualquier igualdad). Como mínimo, normalizar a lowercase.
- `backend/services/ado_client.py:342-374`: asegurar que `unique_name` sea siempre
  el email/`uniqueName` (no `providerDisplayName`).
- **UX para hipótesis 3** (`linked:false`): el aviso "⚠ ADO no vinculado"
  (`TicketBoard.tsx:787-791`) ya existe; ofrecer el re-resolve (`refresh=1`) más
  visible para no confundir "filtro roto" con "identidad no resuelta".

**Alternativa más robusta (single source of truth):** rutear el modo "Mis tareas" por
el filtro backend ya testeado (`Tickets.list(project, "me")` →
`tickets.py:182-200, 287-296`, que usa la semántica de `_user_matches`) en vez de
filtrar client-side. Ver decisión D-B1.

> **Sinergia con B3:** extraer `_user_matches` y `_resolve_me_unique_name` a un
> servicio compartido (ej. `services/ado_identity.py`) para que B1 (filtro) y B3
> (auto-asignación) usen exactamente la misma semántica de identidad.

### B5 — Run Sugerido para Technical/Developer (no sólo EPIC)

**Objetivo:** que un ticket no-EPIC sugiera el agente correcto aunque su `ado_state`
no esté mapeado en FlowConfig.

**Cambio (frontend):** extraer un resolver compartido y darle **fallback por etapa /
por tipo** cuando FlowConfig devuelve `null`. Hoy la lógica está duplicada en
`frontend/src/components/TicketGraphView.jsx:301-308` (grafo, vista default) y
`frontend/src/pages/TicketBoard.tsx:252-264` (árbol).

1. Crear `frontend/src/utils/resolveSuggestedAgent.ts` con una función única
   `resolveSuggestedAgent({ workItemType, adoState, flowConfigMap, pipelineNext })`:
   - **(1)** FlowConfig por estado (señal explícita del operador) — como hoy.
   - **(2)** *fallback* al `next_suggested` del **pipeline summary** que ya viene del
     backend (`summary.next_suggested`, de `pipeline_status`) — encode la cadena
     `business→functional→technical→developer→qa`.
   - **(3)** *fallback final por tipo* si los anteriores son `null`: ej.
     `epic→functional`, `feature→technical`, `task/user story/bug→developer`
     (mapa configurable; ver D-B5).
   - Cambiar la **supresión `business`**: en lugar de forzar `null` en Tasks, **caer**
     al siguiente agente del fallback (así un Task "New" no queda sin sugerencia).
2. Usar ese resolver en ambas vistas, eliminando la duplicación y la divergencia
   (hoy `TicketBoard` suprime `business` para `isTask || isEpic` y `TicketGraphView`
   sólo para `isTask`).

**Opcional (backend autoritativo):** extender `flow_config_store.resolve()`
(`services/flow_config_store.py:333`) para aceptar `work_item_type` y aplicar el
fallback por tipo server-side, exponiéndolo en `next_suggested`. Mantiene una sola
fuente de verdad.

> **Nota de implementación:** confirmar en el momento que `summary.next_suggested`
> rinde Technical/Developer correctamente para los tipos reales del proceso ADO del
> cliente; si no, priorizar el fallback por tipo (paso 3).

### B3 — Auto-asignar al disparar un agente sobre ticket sin responsable

**Helper nuevo** (sugerido en `backend/services/ticket_assigner.py` si existe, o
nuevo módulo) `auto_assign_on_run(ticket_id, project_name) -> str | None`:

1. Cargar el ticket; si `ticket.assigned_to_ado` ya tiene valor → **no-op**
   (idempotente; sólo asigna si está sin responsable).
2. Resolver la identidad ADO del operador reusando el helper compartido (ver
   sinergia B1): `_resolve_me_unique_name(project)` → cache
   (`services/ado_identity.py`) → fallback `AdoClient.get_authenticated_user()` →
   `save_identity`. Si vuelve vacío → log warning y **skip silencioso** (no romper el
   run).
3. `client.update_work_item_assigned_to(ticket.ado_id, ado_unique_name)`
   (`services/ado_client.py:859-875`).
4. En éxito, `ticket.assigned_to_ado = ado_unique_name` en la DB local (espejo de
   `assign_ticket`, `tickets.py:2810-2812`). Opcional: upsert del operador en `users`
   (`User.ado_unique_name`, `models.py:108`) para que "Mis tareas" (B1) y el
   recomendador queden consistentes.
5. **try/except defensivo:** una falla de asignación **nunca** debe romper el lanzamiento
   del agente (mismo estilo que la transición de `stacky_status` en
   `agents.py:639-654`). Emitir evento `stacky_logger` (`assignment_applied`).

**Puntos de inserción:**
- `backend/api/agents.py`, dentro de `run()` (~línea 273, junto al
  `agent_runner.run_agent(...)`) — cubre TicketBoard, AgentLaunchModal y `useAgentRun`.
- `backend/api/agents.py`, dentro de `open_chat()` (~líneas 603-654) — path GitHub
  Copilot (ya tiene `local_ticket_id`, `resolved_project_name` en scope).

**Notas:**
- **No** reusar `POST /api/tickets/<id>/assign` tal cual: por default es `dry_run=True`
  y exige que el target exista en la tabla `users` (404 si no) — inadecuado para
  auto-asignar. Llamar directo a `update_work_item_assigned_to` + update local.
- **No** requiere cambio de frontend: la identidad se resuelve server-side
  (single-operator). El `X-User-Email: dev@local` no es bloqueante.
- PAT scope `vso.work_write` (los flujos de `update_work_item_state`/`post_comment`
  ya escriben, así que el PAT casi seguro ya lo tiene).

### B2 — Aplicar el estado de transición configurado al terminar

**Recomendado (ruta liviana, sobre el path activo)** — resolver `transition_state`
desde la config y aplicarlo en el cierre, **gated** por publicación exitosa del
comentario (regla "no Done sin comment publicado" ya vigente,
`agent_completion_internal.py:186-204`).

1. **Resolución de la config:** en el cierre, cuando `target_ado_state is None`, mapear
   `(project, agent_type) → filename → transition_state`:
   - `project_manager.get_agent_workflow_config(project, filename).transition_state`
     (`project_manager.py:392-405`).
   - **Sub-tarea — mapeo `agent_type`→`filename`:** `agent_workflow_configs` está
     keyeado por nombre de `.agent.md`, pero la execution guarda `agent_type`. Opción
     preferida: **persistir el filename del agente en `AgentExecution.metadata` al
     lanzar** (el endpoint `agents.py:run` ya recibe `vscode_agent_filename`) y leerlo
     al cerrar. Alternativa: resolver vía frontmatter `stacky_agent_type` de los
     `.agent.md`.
2. **Aplicación:** centralizar en `close_execution_with_publish`
   (`services/agent_completion_internal.py:62`), que ya soporta `target_ado_state` y
   ya gatea por `publish.ok`. Cuando el caller no pase target, resolver desde config
   (paso 1) y pasarlo a `_attempt_state_change` → `update_work_item_state`.
3. **Rutear los runners de producción** por este path: hoy `agent_runner.py:612`,
   `claude_code_cli_runner.py:571`, `codex_cli_runner.py:445` llaman
   `on_execution_end` directo y lo saltean. Dos opciones:
   - **(a)** cambiarlos a `close_execution_with_publish`, o
   - **(b)** registrar un **post-hook** en `ticket_status` (`register_post_hook`,
     junto a `ado_publish_post_hook`) que, tras publicación exitosa, resuelva
     `transition_state` y llame `update_work_item_state`. Cuidar el **orden**: la
     transición debe correr **después** de que el comentario se publicó OK.
4. **Fix secundario (finish manual):** en `frontend/src/components/FinishWorkButton.tsx`
   (`:33, 190-198`) pre-cargar `targetState` desde el `transition_state` del agente
   activo (disponible vía `Projects.getAgentWorkflow`) en vez de string vacío, para
   que el estado configurado venga pre-rellenado.

**Alternativa (ruta pesada / futura):** implementar el módulo faltante
`backend/services/ado_workflow.py` (`apply_transition`) que invoca
`agent_completion._apply_workflow_transition` (`agent_completion.py:859-907`),
**hacer que aplique** el resultado a ADO (hoy sólo lo loguea) y **encender** el
gateway (`STACKY_COMPLETION_GATEWAY`). Mayor superficie y hoy off en producción. Ver
decisión D-B2 — se recomienda la ruta liviana.

> **Sinergia con B7:** ambos pasan por `target_ado_state`/`update_work_item_state`.
> B2 define el estado de **éxito** (ej. "To Do"/"Done") por config; B7 redefine la
> rama de **bloqueo**. Implementarlos coordinados evita que la resolución de estado
> de B2 pise el cambio de comportamiento de B7.

### B7 — El Agente Técnico pregunta antes de bloquear

**Diseño recomendado (D7-1, prompt-first, menor riesgo):** que el Técnico, al
detectar un bloqueante, **NO** transicione a "Blocked"; en su lugar publique una
**consulta pre-bloqueo** al humano y deje el ticket en su estado de revisión
(`input_states[0]`, ej. "Technical review"), esperando respuesta.

Editar (y redeployar copias):
`Stacky Agents/backend/Stacky/agents/TechnicalAnalyst.agent.md` (legacy) y
`TechnicalAnalyst.v2.agent.md`, más la persona `backend/agents/technical.py:35`.
Redeploy a `DeployStackyAgents/Stacky/agents/` y
`DeployStackyAgents/github_copilot_agents/` (revisar `deployment/build_release.ps1`).

1. **Reescribir PASO 4** (legacy 94-103 / v2 100-107): ante un bloqueante real,
   publicar un comentario **"❓ CONSULTA TÉCNICA (pre-bloqueo)"** con (a) la condición
   bloqueante concreta, (b) por qué bloquea, (c) **una pregunta accionable + las
   opciones propuestas para desbloquear**; y setear `target_ado_state` al estado de
   revisión (`tracker_state_machine.technical.input_states[0]`), **NO** a
   `blocked_state`. Indicar explícitamente que debe esperar la respuesta humana y
   **no** aplicar "Blocked" por su cuenta.
2. **Reescribir la sección "Formato comentario BLOQUEADO"** (legacy 284-315) como
   formato de **pregunta pre-bloqueo**: conservar "Acción requerida / pregunta
   accionable"; el cierre pasa a "Respondé esta consulta (en el ticket o en el chat de
   Stacky); si confirmás que no hay forma de avanzar, Stacky/el operador marcará
   Blocked".
3. **Corregir los snippets de PATCH/meta** para que la rama de bloqueo no emita
   "Blocked" autónomamente: legacy línea 150 (`target_ado_state = "To Do" # o
   "Blocked"`) y la regla de `comment.meta.json` (legacy 138-140) deben emitir el
   estado de revisión ante una consulta.
4. `backend/agents/technical.py:35`: "Si detectás un bloqueante, **NO bloquees el
   ticket**: primero publicá una consulta al humano (Funcional) describiendo el
   bloqueante y preguntando cómo desbloquearlo; esperá la respuesta antes de aplicar
   cualquier estado `Blocked`."

**Diseño opcional (D7-2, guard server-side, defensa en profundidad):** además del
prompt, agregar un guard en `set_stacky_status_by_ado` (`api/tickets.py:840-872`) y en
`_attempt_state_change` (`services/agent_completion_internal.py:231-282`): si
`target_ado_state == tracker_state_machine.{agent_type}.blocked_state` **y** el origen
es el agente (no operador `X-User-Email`, no `finish_work`), **denegar** el auto-bloqueo
y forzar el estado de revisión, dejándolo logueado. Garantiza por código que un agente
nunca pueda auto-bloquear, dejando "Blocked" sólo para acciones confirmadas por el
operador (`finish_work`, `tickets.py:~1118-1411`, ya soporta `target_ado_state`).

> Recomendación: shippear **D7-1** como fix primario; sumar **D7-2** si se quiere
> garantía dura. (No tocar la vista "Desatascador"/`UnblockerPage.tsx`: es un fallback
> de artifacts, no el estado "Blocked".)

---

## Sinergias y orden de implementación

1. **Identidad ADO compartida (B1 + B3):** primero extraer `_resolve_me_unique_name`
   (`api/tickets.py:182-200`) y `_user_matches` (`api/adoption.py:40-48`) a
   `services/ado_identity.py`. Luego B1 (filtro) y B3 (auto-asignación) consumen el
   mismo matcher. Evita dos semánticas de identidad divergentes.
2. **Canal de transición de estado (B2 + B7):** ambos viven en
   `update_work_item_state` / `target_ado_state`. Diseñar juntos: B2 = estado de éxito
   por config; B7 = rama de bloqueo → consulta. Implementar B2 primero (define el
   "happy path") y luego B7 (acota el bloqueo) sobre la misma maquinaria.
3. **Quick wins primero:** B4 (CSS) y B6 (cancelar, casi todo hecho) entran sin
   dependencias y dan valor inmediato.

Secuencia propuesta: **B4 → B6 → (extraer identidad) → B1 → B5 → B3 → B2 → B7**.

---

## Decisiones abiertas (requieren confirmación del operador)

- **D-B4 — Alcance del fix de dropdown:** ¿`color-scheme: dark` *global* en
  `theme.css` (corrige todos los `<select>` nativos) o *scoped* sólo a `.modalSelect`?
  **Recomendado: global.**
- **D-B1 — Filtro client-side vs backend:** ¿comparación tolerante en el front (mínimo)
  o rutear "Mis tareas" por el filtro backend ya testeado (single source of truth)?
  **Recomendado: front tolerante ahora + considerar backend después.**
- **D-B5 — Mapa de fallback por tipo:** confirmar el mapeo
  `feature→technical`, `task→developer`, `bug→developer` (y si Feature debe sugerir
  functional o technical según el proceso ADO real del cliente).
- **D-B2 — Ruta liviana vs gateway:** ¿resolver `transition_state` en el path de
  cierre activo (recomendado) o construir `services/ado_workflow.py` + encender el
  gateway? **Recomendado: ruta liviana.**
- **D-B7 — Sólo prompt (D7-1) o + guard server-side (D7-2):** **Recomendado: D7-1
  primero**; D7-2 si se quiere garantía dura de que el agente no pueda auto-bloquear.

---

## Verificación

**Backend (`pytest`):**
- B1/B3: test de matcheo de identidad compartido (exacto, casing, dominio, local-part);
  test de `auto_assign_on_run` (no-op si ya asignado; asigna + update local si vacío;
  skip silencioso si identidad no resuelta; no rompe el run ante excepción).
- B2: test de resolución `(project, agent_type)→filename→transition_state` y de que
  `close_execution_with_publish` aplica el estado **sólo** tras publish OK; test de que
  los 3 runtimes de producción terminan llamando la transición.
- B6: test de `cancel_execution` que ahora sincroniza `stacky_status` y dispara el flag
  de `github_copilot`; mantiene 409 para estados no cancelables.
- B7: asserts de contrato sobre los `.agent.md` (PASO 4 = consulta pre-bloqueo,
  `target_ado_state` = estado de revisión, no `Blocked`); si se hace D7-2, test del
  guard que deniega `blocked_state` de origen agente.

**Frontend (`tsc` + vitest):**
- B1: unit del predicado `mine` (displayName vs email, casing, null).
- B5: unit de `resolveSuggestedAgent` (FlowConfig hit; fallback pipeline; fallback por
  tipo; Task "New" ya no queda sin sugerencia) — usado por árbol y grafo.
- B6: el botón llama `Executions.cancel`, invalida queries y maneja 409.
- Build de frontend (`tsc`/vite) sin errores de tipos.

**Smoke manual:**
- B1: desmarcar "Mostrar todas" → el board lista sólo mis tickets (no vacío).
- B2: configurar `transition_state` en un empleado, correr y terminar una tarea → el
  work item ADO queda en el estado estipulado (verificar en ADO).
- B3: correr un agente sobre un ticket sin responsable → queda asignado al operador en
  ADO y en el board.
- B4: abrir "⚙ Run Custom" → el dropdown de Agente es legible (texto sobre fondo
  oscuro).
- B5: en un Feature/Technical/Task no-EPIC, el botón "Run Sugerido" propone
  Technical/Developer (no deshabilitado).
- B6: con un run activo, "Cancelar run" → el run se detiene y el ticket sale de
  "running" sin esperar reconcile.
- B7: forzar un bloqueante → el Técnico publica una **consulta** (no bloquea); el ticket
  queda en "Technical review" esperando respuesta humana.

---

## Riesgos y rollback

- **B2** (mayor riesgo funcional): un mapeo `agent_type→filename` incorrecto podría
  aplicar un estado equivocado. Mitigación: resolver vía filename persistido en la
  execution; gatear por publish OK; feature-flag para activar la transición por config
  y poder revertir sin redeploy.
- **B7** (cambio de comportamiento visible): agentes que hoy bloquean dejarán de
  hacerlo y pedirán confirmación → más tickets en "Technical review". Mitigación:
  comunicar el cambio; D7-2 sólo si se requiere garantía dura. Rollback = revertir los
  `.agent.md` y redeploy.
- **B6** `github_copilot`: cancelación cooperativa puede tardar hasta que retorne el
  HTTP en vuelo; el watchdog/reaper existente (`STACKY_EXECUTION_TIMEOUT_MINUTES`,
  `recover_stale_running_tickets`) cubre el peor caso.
- **B1/B5**: cambios acotados y testeables; bajo riesgo. Si el fallback de B5 sugiere
  de más, es no-destructivo (sólo una sugerencia; el operador decide).
- **B3**: una asignación errónea es reversible desde ADO; el helper es idempotente y
  defensivo (nunca bloquea el run).
