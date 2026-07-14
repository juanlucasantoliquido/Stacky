# Plan 134 — Awareness total de runs: notificaciones accesibles y señales persistentes

**Estado:** PROPUESTO v1 (2026-07-13)
**Origen:** auditoría UX multi-lente 2026-07-13, pedido del operador de mejorar UX sin romper nada.
**Alcance:** frontend + 1 cambio backend aditivo (2 campos JSON opt-in en la serialización de ejecuciones). Cero migraciones, cero endpoints nuevos, cero stores nuevos.
**Flag:** NINGUNA fase lleva flag de harness (decisión de diseño justificada en §3.1, por fase).
**Ortogonal a:** Planes 132 (comparte `ActiveRunsPanel.tsx`), 135 (comparte `ActiveRunsPanel.tsx`, `App.tsx`) y 136 (comparte `App.tsx`, `SettingsPage.tsx`, `TopBar.tsx`) → **staging quirúrgico obligatorio** (`git add -- <paths>` explícitos, nunca `git add -A`) y ediciones ancladas por CONTENIDO, no por número de línea (ver §3.3). Los archivos NUEVOS de este plan no colisionan con nadie.

> Este documento está redactado para que un MODELO MENOR (Haiku, Codex CLI o GitHub
> Copilot Pro) lo implemente SIN inferir nada. Rutas, símbolos, claves y comandos son
> LITERALES. Prohibido desviarse de los nombres exactos, prohibido ampliar el alcance.
> Todo lo ambiguo ya fue decidido acá.

---

## 1. Objetivo + KPIs binarios

El operador lanza agentes que corren varios minutos y hoy la única señal de fin de run
es un flash del título de la pestaña de 4 segundos (que además tiene un bug real que lo
deja pegado). Este plan convierte a Stacky en un sistema del que el operador puede
apartar la vista sin perder NADA: notificaciones opt-in accesibles desde la UI, título
de pestaña que refleja el estado real de forma persistente, badges vivos en TopBar y en
el tab Revisión, y filas del panel de runs que dicen QUÉ está corriendo y DÓNDE.

**KPIs (todos binarios, verificables con comando o con un vistazo):**

- **KPI-1 (notificaciones accesibles):** existe el sub-tab `Notificaciones` en
  Configuración con 2 toggles que escriben EXACTAMENTE las claves localStorage
  `stacky.notify.sound` y `stacky.notify.desktop` (las mismas que ya lee
  `services/executionNotifier.ts:11-12`). Hoy: 0 UI, solo devtools. Cumple la directiva
  del operador "toda config del operador va por UI".
- **KPI-2 (título vivo, bug muerto):** con N runs activos el título de la pestaña es
  `(N▶) Stacky Agents`; al terminar el último run queda `✅ Stacky Agents` (o
  `❌ Stacky Agents` si hubo error/needs_review) hasta que el operador vuelve a mirar
  la pestaña. El bug del flash pegado queda IMPOSIBLE: `grep -r "🤖 done" src` = 0 hits
  tras F3 (el código del flash se elimina).
- **KPI-3 (rastro de revisión):** con ≥1 ejecución en `needs_review`/`error` (últimos
  30 días, proyecto activo) el botón de nav `🧭 Revisión` muestra un badge numérico SIN
  abrir la página. Hoy: `ReviewInboxPage` desmontada = ciega (`App.tsx:243`).
- **KPI-4 (TopBar despierta):** el badge "Agente trabajando…" del TopBar se enciende
  con CUALQUIER run activo real de CUALQUIER runtime y muestra el conteo. Hoy: cableado
  a un campo muerto que ningún flujo real setea → nunca se enciende (evidencia §2 GAP 4).
- **KPI-5 (cero avisos tragados):** dos runs que terminan en el mismo segundo generan
  DOS notificaciones (test puro `shouldNotifyExecution`, F2). Hoy: el segundo se
  descarta para siempre (`MIN_GAP_MS=1500` global, `executionNotifier.ts:85-90`).
- **KPI-6 (contexto en el panel):** cada fila de "EJECUCIONES ACTIVAS" y el confirm de
  cancelar muestran proyecto y título del ticket. Hoy: solo ids crudos
  (`ActiveRunsPanel.tsx:134-137` y `:146-148`).
- **KPI-7 (no degradar la red):** el neto de polling BAJA: se elimina la query propia
  del notificador (1 request cada 5 s) fusionándola con la query ya existente del panel,
  y solo se agrega 1 request liviana cada 60 s para el badge de Revisión (compartida con
  la página cuando está abierta). Detalle en §3.2.

## 2. Por qué ahora / gaps que cierra (evidencia re-verificada 2026-07-13 en HEAD)

**GAP 1 — Notificaciones de fin de run existen pero son inaccesibles.**
- `frontend/src/services/executionNotifier.ts:4-6` — el propio comentario del módulo
  declara el opt-in vía localStorage `stacky.notify.sound` / `stacky.notify.desktop`
  (claves definidas en `:11-12`). No existe NINGUNA UI que las escriba.
- `executionNotifier.ts:54-56` — `setSoundEnabled` exportado, **cero callers** en `src/`
  (grep verificado: solo la definición). `:66-77` — `requestDesktopPermission`
  exportado, **cero callers**. `pages/SettingsPage.tsx` no tiene sección de
  notificaciones (sub-tabs actuales en `:17`: flow/sections/client-profile/transfer/
  webhooks/harness/playground).
- `executionNotifier.ts:107-112` — el único fallback default es el flash del título de
  4 s.
- `frontend/src/hooks/useGlobalExecutionNotifier.ts:10-43` — el hook global (montado en
  `App.tsx:64`) ya detecta fines de run cada 5 s. **La plomería está lista; falta el
  interruptor.**

**GAP 2 — El título de la pestaña no refleja actividad y el flash tiene un bug real
que lo deja pegado.**
- `executionNotifier.ts:107-112` — el flash captura `document.title` (posiblemente YA
  flasheado) y agenda un revert a 4 s. Secuencia del bug (reproducible): fin de run A en
  t=0 → título "🤖 done — Stacky Agents", revert A agendado a t=4s. Fin de run B en
  t=1.6s (permitido: `MIN_GAP_MS=1500`, `:85-86`) → captura como "original" el título
  YA flasheado y agenda revert B a t=5.6s. El revert A (t=4s) restaura bien, pero el
  revert B (t=5.6s) **re-instala el título flasheado** → "🤖 done — Stacky Agents"
  queda PERMANENTE hasta F5.
- `:97` — el `verb` distingue completed/error para la notificación de escritorio, pero
  el flash (`:109`) es SIEMPRE la constante "🤖 done", incluso en error.
- Grep verificado: `document.title` en `src/` aparece SOLO en
  `executionNotifier.ts:108,109,111`; `favicon` = 0 hits. Título base real:
  `frontend/index.html` → `<title>Stacky Agents</title>`.

**GAP 3 — Runs en needs_review/error no dejan rastro navegable.**
- `frontend/src/App.tsx:161-166` — el botón de nav `🧭 Revisión` no tiene badge ni
  contador.
- `frontend/src/pages/ReviewInboxPage.tsx:40-50` — la query de needs_review/error
  (`queryKey ["review-inbox", activeProjectName]`, `status: ["needs_review","error"]`,
  `limit: 200`, `days: 30`, `refetchInterval: 30000`) vive DENTRO de la página, que solo
  se monta con el tab activo (`App.tsx:243`). Página cerrada = ciega.

**GAP 4 — El indicador "Agente trabajando…" del TopBar está cableado a un campo
muerto: nunca se enciende.**
- `frontend/src/components/TopBar.tsx:17-18` — `isRunning = runningExecutionId != null`
  (del store workbench). `:196-201` badge + `:207` progressbar condicionados a eso.
- `frontend/src/hooks/useAgentRun.ts:41` — el ÚNICO `setRunningExecution(id≠null)` del
  repo; su único consumidor es `components/InputContextEditor.tsx:31`, que NO está
  montado en ninguna página (grep `<InputContextEditor` = 0 hits). El único clear está
  en `components/OutputPanel.tsx:24-28`, también huérfano (grep `<OutputPanel` = 0
  hits).
- Los flujos reales lanzan vía `launchAgentWithRuntime` (`pages/TicketBoard.tsx:300` y
  `:591`, `components/AgentLaunchModal.tsx:236`, `components/TicketGraphView.jsx:328`),
  que NO toca ese campo del store.
- **Fuente viva elegida (decisión cerrada):** la query `["executions","active-global"]`
  del panel `ActiveRunsPanel` (`ActiveRunsPanel.tsx:63-67`, fetcher `:37-46` con
  `all_projects: true` y estados running/preparing/queued, refetch 5 s). Se descartó
  `useRunningStatus` (`hooks/useRunningStatus.ts:43-80`) porque monta 4 queries
  project-scoped (tickets + 3 listas) — más pesada y ciega a otros proyectos. Con la
  query compartida el costo de red del TopBar es CERO (react-query dedupea por queryKey).

**GAP 5 — El notificador global es ciego a otros proyectos y a muertes tempranas, y
con fines simultáneos se traga avisos.**
- `useGlobalExecutionNotifier.ts:16` —
  `Executions.list({ status: "running", project: activeProjectName })`: solo proyecto
  activo, solo `running`.
- `components/ActiveRunsPanel.tsx:37-46` — el panel hermano usa `all_projects: true` e
  incluye `preparing`/`queued` (comentario de intención en `:31-36`): asimetría directa.
- `executionNotifier.ts:85-91` — `MIN_GAP_MS=1500` es un gate global POR TIEMPO, no por
  execution_id: el segundo fin en <1.5 s se descarta para siempre. Además
  `hooks/useExecutionStream.ts:94` TAMBIÉN llama `notifyExecutionFinished` (dock
  abierto): el fix debe deduplicar por execution_id, no solo ajustar el gap.

**GAP 6 — El panel de runs activos no dice proyecto ni título del ticket.**
- `ActiveRunsPanel.tsx:134-137` — la fila muestra solo `#id`, `ticket {e.ticket_id}`,
  `agent_type`, `status`. `:146-148` — el `window.confirm` de cancelar también usa solo
  ids crudos.
- `backend/models.py:280-302` — `AgentExecution.to_dict` no incluye proyecto ni título.
  La relación existe: `models.py:234` `ticket: Mapped[Ticket] = relationship(...)`
  (lazy `select` por default → riesgo N+1 si se accede por fila; mitigación decidida en
  F1). Los datos están a un join: `Ticket.stacky_project_name` (`models.py:48`) y
  `Ticket.title` (`models.py:50`).
- Precedente en el MISMO archivo: `backend/api/executions.py:227` ya usa
  `row.ticket.stacky_project_name if row.ticket else None`.

## 3. Principios y guardarraíles (no negociables)

1. **Paridad 3 runtimes** (Codex CLI, Claude Code CLI, GitHub Copilot Pro): TODAS las
   señales de este plan leen la API de Executions (`/api/executions`, `byId`, SSE) que
   es agnóstica del runtime — un run de cualquier runtime aparece igual en el título,
   el TopBar, el badge de Revisión, las notificaciones y el panel. Cada fase lo declara.
2. **Cero trabajo extra del operador:** todo es invisible/automático, salvo los 2
   toggles de notificaciones que son opt-in con el default actual intacto (OFF).
3. **Human-in-the-loop:** este plan SOLO agrega señales. Nada ejecuta, decide, relanza
   ni cancela por sí solo.
4. **Mono-operador sin auth:** sin RBAC, sin permisos, sin usuarios.
5. **No degradar:** no se cambia ningún intervalo de polling existente; el neto de
   requests BAJA (§3.2). Prohibido subir frecuencias o agregar queries pesadas.
6. **Reusar lo existente:** `executionNotifier`, `useGlobalExecutionNotifier`, la query
   del panel, el patrón de sub-tabs de SettingsPage. Prohibido reinventar notificadores,
   stores o mecanismos de polling nuevos.

### 3.1 Decisión de diseño: SIN flag de harness (justificación por fase)

Precedente directo: plan 132 §3.1 (feature de UI puramente aditiva y reversible va sin
flag, porque un flag agrega trabajo al operador y superficie de test sin mitigar riesgo
real). Aplicación por fase:

- **F0** (refactor extractivo): byte-equivalente en comportamiento de red; sin flag.
- **F1** (backend): campos JSON **aditivos** detrás de un kwarg nuevo con default
  `False` — todos los callers existentes de `to_dict` quedan byte-idénticos (test F1
  caso 3); ningún consumidor JSON se rompe por claves extra. Sin flag.
- **F2** (dedup + alcance del notificador): corrige dos defectos (avisos tragados,
  ceguera a otros proyectos); las notificaciones siguen siendo opt-in OFF. Sin flag.
- **F3** (título persistente — el único cambio de COMPORTAMIENTO visible always-on):
  decidido SIN flag porque (a) corrige un bug real reproducible (título pegado) — un
  flag OFF obligaría a mantener viva la rama buggy del flash; (b) `document.title` no
  es contrato de ningún código (grep §2 GAP 2: las únicas referencias son el propio
  flash); (c) el nuevo comportamiento se auto-restaura al volver el foco; (d) revert =
  revertir 1 archivo.
- **F4/F5/F6/F7** (badges, toggles, fila): puramente aditivas y reversibles; sin flag.

Por lo tanto: **cero FlagSpec, cero cambios en `services/harness_flags.py`,
`harness_flags_help.py`, `config.py` ni `HarnessFlagsPanel`** en este plan.

### 3.2 Presupuesto de red (cerrado, verificable)

| Movimiento | Antes | Después |
|---|---|---|
| Notificador global (`executions-running-global`, 5 s) | 12 req/min | **0** (consume la query compartida del panel) |
| Panel runs activos (3 listas × 5 s) | 36 req/min | 36 req/min (sin cambios de intervalo) |
| TopBar badge | 0 | **0** (misma queryKey compartida → dedup react-query) |
| Título de pestaña | 0 | **0** (deriva de la query compartida) |
| Badge Revisión | 0 | 1 req/60 s (y CERO extra con la página abierta: misma queryKey que la página) |
| `Executions.byId` por fin de run | ya existe | igual (1 por run terminado) |

Neto: **−11 req/min** en reposo con runs activos. La lista de Revisión viaja con
`include_output=False` (serialización de `api/executions.py:82`) y `limit: 200`.

### 3.3 Convivencia con los planes hermanos (132/135/136)

- Los archivos NUEVOS (`services/activeRuns.ts`, `services/notifierCore.ts`,
  `services/tabTitle.ts`, `services/reviewInbox.ts`, `hooks/useActiveRunsGlobal.ts`,
  `hooks/useReviewInboxCount.ts`, tests nuevos, `backend/tests/test_executions_ticket_context.py`)
  son propiedad exclusiva de este plan.
- En archivos COMPARTIDOS (`ActiveRunsPanel.tsx`, `App.tsx`, `TopBar.tsx`,
  `SettingsPage.tsx`): anclar cada edición por el CONTENIDO citado en la fase (el
  número de línea puede haber corrido si otro plan tocó antes). Si el plan 132 ya
  insertó su botón "Ver consola" en la fila del panel, F7 inserta ALREDEDOR sin tocarlo.
- Staging: SIEMPRE `git add -- "<ruta1>" "<ruta2>"` con las rutas exactas de la fase
  (regla de la casa; el working tree tiene WIP ajeno).
- NO tocar: manejo de errores/toasts/ErrorBoundary (plan 135), doble-submit/backdrop/
  higiene de cambio de proyecto/persistencia de consola (plan 136), botón "Ver consola"
  (plan 132).

## 4. Entorno de tests (leer ANTES de empezar)

- **Tests de componente** (`@testing-library/react` + jsdom) **no pueden ejecutarse en
  este checkout** — gap preexistente documentado en
  `frontend/src/components/__tests__/ActiveRunsPanel.test.tsx:12-17`. NO resolverlo (no
  es parte de este plan). Los tests de componente de F7 se escriben igual y "quedan
  listos para correr".
- **Tests de lógica pura SÍ corren**: `vite.config.ts` no define bloque `test` →
  entorno `node` por default, y el repo ya tiene 30+ archivos `.test.ts` puros verdes
  (precedentes: `src/utils/__tests__/resolveSuggestedAgent.test.ts`,
  `src/docs/backlinks.test.ts`). Por eso este plan EXTRAE toda lógica nueva no trivial
  a funciones puras (F0/F2/F5) testeables sin DOM.
  - Comando exacto (desde `Stacky Agents/frontend`): `npx vitest run <archivo>`
  - Gate binario global frontend: `npx tsc --noEmit` (desde `Stacky Agents/frontend`).
- **Backend (F1):** el venv real es `.venv` DENTRO de `Stacky Agents/backend`
  (verificado: existe `Stacky Agents/backend/.venv/Scripts/python.exe`; `backend/venv`
  NO existe). Comando literal (PowerShell, desde `Stacky Agents/backend`):
  ```powershell
  & ".\.venv\Scripts\python.exe" -m pytest .\tests\test_executions_ticket_context.py -q
  ```
  Correr pytest POR ARCHIVO (regla del repo; la suite completa tiene ruido preexistente).
- **Ratchet de tests backend:** todo archivo de test backend nuevo DEBE registrarse en
  `backend/scripts/run_harness_tests.sh` (array `HARNESS_TEST_FILES`, línea 20) y en
  `backend/scripts/run_harness_tests.ps1` (array `$HarnessTestFiles`, línea 13), o el
  meta-test del plan 49 falla. F1 lo instruye.

---

## 5. Fases

### F0 — Sustrato compartido: una sola fuente de "runs activos globales"

**Objetivo (1 frase):** extraer el fetcher del panel a un módulo compartido + hook, para
que panel, TopBar (F4) y notificador (F2/F3) consuman la MISMA query de react-query
(misma queryKey ⇒ una sola request cada 5 s, sin importar cuántos consumidores haya).

**Archivo NUEVO 1:** `Stacky Agents/frontend/src/services/activeRuns.ts`

```ts
/**
 * Fuente única de "runs activos globales" (running/preparing/queued de TODOS
 * los proyectos). Extraída de ActiveRunsPanel.tsx (plan 134 F0) para que el
 * panel, el TopBar y el notificador global compartan la MISMA query de
 * react-query. A propósito NO se filtra por proyecto (misma intención que el
 * comentario original del panel): el objetivo es visibilidad global, incluidos
 * runs huérfanos/colgados de otro proyecto.
 */
import { Executions } from "../api/endpoints";
import type { AgentExecution } from "../types";

export const ACTIVE_RUNS_QUERY_KEY = ["executions", "active-global"] as const;
export const ACTIVE_RUNS_REFRESH_MS = 5_000;

/**
 * Merge puro y determinista: dedup por id (si un run aparece en dos listas por
 * carrera entre requests, gana la ÚLTIMA en orden running→preparing→queued —
 * comportamiento idéntico al código original del panel), orden id descendente.
 */
export function mergeActiveRuns(
  running: AgentExecution[],
  preparing: AgentExecution[],
  queued: AgentExecution[],
): AgentExecution[] {
  const byId = new Map<number, AgentExecution>();
  for (const e of [...running, ...preparing, ...queued]) byId.set(e.id, e);
  return [...byId.values()].sort((a, b) => b.id - a.id);
}

export async function fetchActiveRuns(): Promise<AgentExecution[]> {
  const [running, preparing, queued] = await Promise.all([
    Executions.list({ status: "running", all_projects: true }),
    Executions.list({ status: "preparing", all_projects: true }),
    Executions.list({ status: "queued", all_projects: true }),
  ]);
  return mergeActiveRuns(running, preparing, queued);
}
```

**Archivo NUEVO 2:** `Stacky Agents/frontend/src/hooks/useActiveRunsGlobal.ts`

```ts
import { useQuery } from "@tanstack/react-query";
import {
  ACTIVE_RUNS_QUERY_KEY,
  ACTIVE_RUNS_REFRESH_MS,
  fetchActiveRuns,
} from "../services/activeRuns";

/**
 * Runs activos (running/preparing/queued) de TODOS los proyectos, refresco 5 s.
 * Todos los consumidores comparten queryKey ⇒ react-query hace UNA request.
 */
export function useActiveRunsGlobal() {
  return useQuery({
    queryKey: ACTIVE_RUNS_QUERY_KEY,
    queryFn: fetchActiveRuns,
    refetchInterval: ACTIVE_RUNS_REFRESH_MS,
  });
}
```

**Archivo a EDITAR:** `Stacky Agents/frontend/src/components/ActiveRunsPanel.tsx`
(3 ediciones ancladas por contenido):

1. Eliminar la constante `const REFRESH_MS = 5_000;` (hoy línea 9).
2. Eliminar el bloque completo del comentario "Trae TODOS los runs activos…" + la
   función `async function fetchActiveRuns(...) { ... }` (hoy líneas 31-46; el
   comentario de intención ya vive en el módulo nuevo).
3. Reemplazar el `useQuery` inline (hoy líneas 63-67):
   ```tsx
   // ANTES
   const { data } = useQuery({
     queryKey: ["executions", "active-global"],
     queryFn: fetchActiveRuns,
     refetchInterval: REFRESH_MS,
   });
   // DESPUÉS
   const { data } = useActiveRunsGlobal();
   ```
   Agregar `import { useActiveRunsGlobal } from "../hooks/useActiveRunsGlobal";` junto
   a los imports existentes, y limpiar los imports que queden sin uso (si `useQuery` o
   `AgentExecution` quedan huérfanos, `npx tsc --noEmit` lo denuncia; `Executions` se
   CONSERVA porque `cancelMutation` lo usa).

**Tests PRIMERO** — archivo NUEVO
`Stacky Agents/frontend/src/services/__tests__/activeRuns.test.ts`, casos exactos:

1. `"deduplica por id y gana la lista más tardía (running→preparing→queued)"` — mismo
   id en running y queued → 1 entrada con el objeto de queued (congela el
   comportamiento actual del panel).
2. `"ordena por id descendente"` — ids [3,1,7] repartidos → [7,3,1].
3. `"tres listas vacías → []"`.

Construir filas con `const mk = (id: number, status: string) => ({ id, status } as unknown as AgentExecution);`
(solo se ejercita `mergeActiveRuns`, que es pura — no hace falta mockear `Executions`).

- **Comando exacto:** `npx vitest run src/services/__tests__/activeRuns.test.ts`
  (desde `Stacky Agents/frontend`). Los 3 tests deben FALLAR antes de crear el módulo
  (no existe) y PASAR después.
- **Criterio de aceptación (binario):** vitest 3/3 verde + `npx tsc --noEmit` exit 0 +
  `grep -c "fetchActiveRuns" src/components/ActiveRunsPanel.tsx` = 0.
- **Flag:** no aplica (§3.1 F0 — refactor extractivo, red byte-equivalente).
- **Paridad runtimes:** N/A (no cambia comportamiento observable).
- **Trabajo del operador: ninguno.**

---

### F1 — Backend: `project` y `ticket_title` en la serialización de ejecuciones (GAP 6, mitad backend)

**Objetivo (1 frase):** exponer proyecto y título de ticket como campos JSON aditivos
opt-in en `AgentExecution.to_dict`, con `joinedload` en el listado para que el N+1 sea
imposible.

**Archivo a EDITAR 1:** `Stacky Agents/backend/models.py`

Reemplazar la firma y el cierre de `AgentExecution.to_dict` (hoy líneas 280-302):

```python
    def to_dict(self, include_output: bool = True, include_ticket_context: bool = False) -> dict:
        d = {
            # ... (las claves existentes id..contract_result quedan EXACTAMENTE igual)
        }
        if include_ticket_context:
            # Plan 134 F1: contexto de ticket para vistas globales (panel de runs,
            # notificaciones). Opt-in: el default False deja byte-idéntico a todos
            # los callers existentes. Guard `is not None` por ejecuciones cuyo
            # ticket fue borrado (trap conocida de tasks eliminadas).
            t = self.ticket
            d["project"] = t.stacky_project_name if t is not None else None
            d["ticket_title"] = t.title[:120] if t is not None else None
        if include_output:
            d["output"] = self.output
        return d
```

Decisiones cerradas: truncado del título a **120 caracteres exactos** con slicing
`t.title[:120]` (sin elipsis — la elipsis visual la pone el CSS del frontend);
`Ticket.title` es `nullable=False` (`models.py:50`) así que no hace falta guard de None
sobre el título, solo sobre la relación.

**Archivo a EDITAR 2:** `Stacky Agents/backend/api/executions.py`

1. Agregar import (debajo de `from sqlalchemy import and_, or_, select`, hoy línea 8):
   ```python
   from sqlalchemy.orm import joinedload
   ```
2. En `list_executions`, inmediatamente después de `q = session.query(AgentExecution)`
   (hoy línea 59), agregar:
   ```python
        # Plan 134 F1: eager-load del ticket para servir project/ticket_title sin
        # N+1 (la relación es lazy="select" por default — models.py:234).
        q = q.options(joinedload(AgentExecution.ticket))
   ```
3. Reemplazar la serialización del listado (hoy línea 82):
   ```python
        return jsonify([r.to_dict(include_output=False, include_ticket_context=True) for r in rows])
   ```
4. En `get_execution`, reemplazar (hoy línea 91):
   ```python
        return jsonify(row.to_dict(include_ticket_context=True))
   ```
   (Fila única: el lazy-load agrega a lo sumo 1 SELECT — aceptable y medido; el
   precedente `:227` del mismo archivo ya hace este acceso.)

**Análisis N+1 (evidencia, decisión explícita):** los otros bucles que llaman
`AgentExecution.to_dict` en listas (`api/diag.py:605`, `api/tickets.py:662,733`,
`api/packs.py:60`) NO pasan `include_ticket_context` → siguen sin tocar la relación:
**cero lazy-loads nuevos fuera del endpoint modificado**. En `list_executions` el
`joinedload` convierte el riesgo en un único LEFT OUTER JOIN. El `joinedload` convive
sin conflicto con el `q.join(Ticket, ...)` del filtro por proyecto (hoy línea 61):
SQLAlchemy usa un alias propio para el eager-load.

**Archivo a EDITAR 3:** `Stacky Agents/frontend/src/types.ts` — dentro de
`interface AgentExecution` (hoy líneas 121-139), después de la línea de
`contract_result`, agregar:

```ts
  /** Plan 134: contexto de ticket — presente solo cuando el backend lo incluye. */
  project?: string | null;
  ticket_title?: string | null;
```

**Archivo a EDITAR 4 y 5 (ratchet, obligatorio):** agregar la entrada
`"tests/test_executions_ticket_context.py"` al array `HARNESS_TEST_FILES` de
`backend/scripts/run_harness_tests.sh` (línea 20) y al array `$HarnessTestFiles` de
`backend/scripts/run_harness_tests.ps1` (línea 13), al final del bloque más reciente.

**Tests PRIMERO** — archivo NUEVO
`Stacky Agents/backend/tests/test_executions_ticket_context.py`, siguiendo EXACTAMENTE
el patrón de blueprint aislado de `tests/test_plan117_insights_api.py:16-79`
(`DATABASE_URL=sqlite:///:memory:` antes de importar, `_stub_api_pkg()` + carga de
`api/executions.py` vía `importlib`, `app.register_blueprint(m.bp, url_prefix="/api/executions")`).
Usar SIEMPRE `all_projects=true` en las requests (evita `resolve_project_context`).
Casos exactos (nombres literales):

1. `test_list_incluye_project_y_ticket_title` — crear `Ticket(id=1, ado_id=999001,
   project="P", stacky_project_name="proj-x", title="Mi ticket")` + una
   `AgentExecution(ticket_id=1, status="running", agent_type="developer",
   input_context_json="[]", started_by="t")` → `GET /api/executions?all_projects=true&status=running`
   → la fila tiene `project == "proj-x"` y `ticket_title == "Mi ticket"`.
2. `test_ticket_title_truncado_a_120` — ticket con `title="x" * 200` →
   `len(row["ticket_title"]) == 120`.
3. `test_to_dict_default_sin_ticket_context` — unit directo sobre el modelo dentro de
   `db.session_scope()`: `d = row.to_dict()` → `"project" not in d` y
   `"ticket_title" not in d` (garantía de byte-identidad para los demás callers).
4. `test_exec_con_ticket_borrado_no_rompe` — crear ticket+exec, `session.delete(ticket)`
   (sqlite en memoria no fuerza FKs por default) → `GET /api/executions?all_projects=true`
   responde 200 y la fila tiene `project is None` y `ticket_title is None`.
5. `test_get_execution_incluye_ticket_context` — `GET /api/executions/<id>` → claves
   `project` y `ticket_title` presentes.

- **Comando exacto** (PowerShell, desde `Stacky Agents/backend`):
  `& ".\.venv\Scripts\python.exe" -m pytest .\tests\test_executions_ticket_context.py -q`
  Los 5 deben FALLAR antes del cambio (KeyError/claves ausentes) y PASAR después.
- **Criterio de aceptación (binario):** 5/5 verdes + el archivo aparece en AMBOS
  scripts de ratchet + `npx tsc --noEmit` (frontend) exit 0.
- **Flag:** no aplica (§3.1 F1 — aditivo opt-in, default byte-idéntico probado por el caso 3).
- **Paridad runtimes:** los campos salen de la fila `AgentExecution`+`Ticket`, idénticos
  para runs de los 3 runtimes.
- **Trabajo del operador: ninguno.**

---

### F2 — Notificador: dedup por execution_id, alcance global y muertes tempranas (GAP 5)

**Objetivo (1 frase):** que NINGÚN fin de run se pierda — dedup por execution_id (no por
tiempo), cobertura de todos los proyectos y de fallos en `preparing`/`queued`, y texto
con proyecto/ticket.

**Archivo NUEVO:** `Stacky Agents/frontend/src/services/notifierCore.ts` — 100% puro
(PROHIBIDO referenciar `window`, `document`, `localStorage` o `Notification` en este
módulo; es la garantía de que corre en vitest/node):

```ts
/** Lógica pura del notificador y del título de pestaña (plan 134 F2/F3). */

export type FinishOutcome = "ok" | "attention" | null;

/** TTL del registro de ejecuciones ya notificadas. */
export const NOTIFIED_TTL_MS = 10 * 60_000;

/**
 * Dedup por execution_id: true si execId NO fue notificado dentro del TTL.
 * Muta `seen` (registra execId y poda entradas vencidas). Determinista dado
 * (execId, nowMs, seen).
 */
export function shouldNotifyExecution(
  execId: number,
  nowMs: number,
  seen: Map<number, number>,
  ttlMs: number = NOTIFIED_TTL_MS,
): boolean {
  for (const [id, at] of seen) {
    if (nowMs - at > ttlMs) seen.delete(id);
  }
  if (seen.has(execId)) return false;
  seen.set(execId, nowMs);
  return true;
}

/**
 * Combina el desenlace acumulado con el status de un run recién terminado.
 * "attention" (error/needs_review) es pegajoso: nunca lo pisa un completed.
 * "cancelled" (u otro status desconocido) no cambia la señal: lo canceló el
 * propio operador, no es novedad.
 */
export function combineOutcome(prev: FinishOutcome, status: string): FinishOutcome {
  if (status === "error" || status === "needs_review") return "attention";
  if (status === "completed") return prev === "attention" ? "attention" : "ok";
  return prev;
}

/** Título de pestaña derivado del estado real (F3). Actividad gana al desenlace. */
export function computeTabTitle(
  activeCount: number,
  lastOutcome: FinishOutcome,
  baseTitle: string,
): string {
  if (activeCount > 0) return `(${activeCount}▶) ${baseTitle}`;
  if (lastOutcome === "ok") return `✅ ${baseTitle}`;
  if (lastOutcome === "attention") return `❌ ${baseTitle}`;
  return baseTitle;
}

/** Cuerpo de la notificación con contexto de proyecto/ticket (campos F1, opcionales). */
export function buildNotificationBody(row: {
  ticket_id?: number | null;
  project?: string | null;
  ticket_title?: string | null;
}): string {
  const parts: string[] = [];
  if (row.project) parts.push(row.project);
  if (row.ticket_title) parts.push(row.ticket_title);
  else if (row.ticket_id != null) parts.push(`Ticket ${row.ticket_id}`);
  return parts.length > 0 ? parts.join(" · ") : "Ejecución finalizada.";
}
```

**Archivo a EDITAR 1:** `Stacky Agents/frontend/src/services/executionNotifier.ts`

1. Agregar import: `import { shouldNotifyExecution } from "./notifierCore";`
2. `interface FinishedPayload` (hoy líneas 79-83): agregar el campo
   ```ts
     /** Plan 134 F2: dedup — el mismo run notificado por el stream del dock y por
      *  el notificador global debe producir UN solo aviso. */
     execution_id?: number;
   ```
3. Reemplazar el estado del gate (hoy líneas 85-86) por:
   ```ts
   let lastNotifiedAt = 0;
   const MIN_GAP_MS = 1500; // solo fallback para payloads legacy SIN execution_id
   const notifiedExecIds = new Map<number, number>();
   // El beep conserva un gate corto propio: 5 fines simultáneos = 1 solo beep
   // (el aviso de escritorio y el título SÍ salen uno por run).
   let lastBeepAt = 0;
   const BEEP_GAP_MS = 1000;
   ```
4. Reemplazar el cuerpo de `notifyExecutionFinished` (hoy líneas 88-113) por:
   ```ts
   export function notifyExecutionFinished(payload: FinishedPayload): void {
     const now = Date.now();
     if (payload.execution_id != null) {
       if (!shouldNotifyExecution(payload.execution_id, now, notifiedExecIds)) return;
     } else {
       if (now - lastNotifiedAt < MIN_GAP_MS) return;
       lastNotifiedAt = now;
     }

     if (isSoundEnabled() && now - lastBeepAt >= BEEP_GAP_MS) {
       lastBeepAt = now;
       playBeep();
     }

     if (isDesktopEnabled()) {
       try {
         const verb = payload.status === "completed" ? "terminó" : payload.status;
         const title = `Stacky · agente ${payload.agent_type} ${verb}`;
         const body = payload.ticket_label ?? "Ejecución finalizada.";
         const n = new Notification(title, { body, silent: true });
         // Plan 134: click en la notificación = volver a la pestaña de Stacky.
         n.onclick = () => {
           try {
             window.focus();
             n.close();
           } catch {
             // ignore
           }
         };
         window.setTimeout(() => n.close(), 6000);
       } catch {
         // ignore
       }
     }

     // Status bar flash (window icon won't change but title does).
     const originalTitle = document.title;
     document.title = "🤖 done — " + originalTitle;
     window.setTimeout(() => {
       document.title = originalTitle;
     }, 4000);
   }
   ```
   NOTA: el bloque del flash queda INTACTO en F2 (para que la fase sea verificable
   sola sin perder la señal actual); F3 lo elimina y entrega el reemplazo.

**Archivo a EDITAR 2:** `Stacky Agents/frontend/src/hooks/useGlobalExecutionNotifier.ts`
— contenido COMPLETO nuevo (el archivo actual tiene 43 líneas; se reemplaza entero):

```ts
import { useEffect, useRef } from "react";
import { Executions } from "../api/endpoints";
import { notifyExecutionFinished } from "../services/executionNotifier";
import { buildNotificationBody } from "../services/notifierCore";
import { useActiveRunsGlobal } from "./useActiveRunsGlobal";

/**
 * U0.4 + plan 134 F2 — Notifica la finalización de CUALQUIER run de CUALQUIER
 * proyecto. Consume la query compartida del panel (running/preparing/queued,
 * all_projects) ⇒ también detecta muertes tempranas en preparing/queued y no
 * agrega NINGUNA request propia. Un id que desaparece del set se confirma con
 * Executions.byId (status final real) antes de notificar.
 */
export function useGlobalExecutionNotifier() {
  const activeQ = useActiveRunsGlobal();
  const prevActive = useRef<Set<number> | null>(null);

  useEffect(() => {
    if (activeQ.data == null) return; // sin snapshot (carga o error): no comparar
    const current = new Set<number>(activeQ.data.map((e) => e.id));
    const prev = prevActive.current;
    prevActive.current = current;
    if (prev == null) return; // primer snapshot: nada contra qué comparar

    for (const prevId of prev) {
      if (!current.has(prevId)) {
        void Executions.byId(prevId)
          .then((row) => {
            notifyExecutionFinished({
              execution_id: row.id,
              agent_type: String(row.agent_type || "agente"),
              status:
                (row.status as "completed" | "error" | "cancelled" | "needs_review") ||
                "completed",
              ticket_label: buildNotificationBody(row),
            });
          })
          .catch(() => {});
      }
    }
  }, [activeQ.data]);
}
```

Notas de corrección incluidas en este rewrite (decididas, no opcionales):
- El guard `activeQ.data == null` evita el falso "terminaron todos" cuando la query
  entra en error de red (el hook viejo trataba `undefined` como lista vacía en `:22`).
- Un run que transiciona `queued→running` sigue en el set → NO se notifica de más.
- `buildNotificationBody(row)` usa `project`/`ticket_title` de F1 si están (deploy
  nuevo) y degrada a `Ticket {id}` si no.

**Archivo a EDITAR 3:** `Stacky Agents/frontend/src/hooks/useExecutionStream.ts` —
reemplazar la llamada (hoy línea 94):

```ts
      // ANTES
      notifyExecutionFinished({ agent_type: agentType, status });
      // DESPUÉS  (executionId es el parámetro del hook, non-null dentro del efecto)
      notifyExecutionFinished({
        agent_type: agentType,
        status,
        execution_id: executionId ?? undefined,
      });
```

**Tests PRIMERO** — archivo NUEVO
`Stacky Agents/frontend/src/services/__tests__/notifierCore.test.ts`, casos exactos:

1. `"shouldNotifyExecution: primera vez true, repetido false"` — mismo id, mismo now.
2. `"shouldNotifyExecution: dos ids distintos en el mismo instante → ambos true"` (KPI-5).
3. `"shouldNotifyExecution: pasado el TTL el id vuelve a notificar y el mapa se poda"` —
   usar `ttlMs` explícito chico (p. ej. 1000) y `nowMs` manual.
4. `"combineOutcome: tabla de verdad"` — `(null,"completed")→"ok"`,
   `(null,"error")→"attention"`, `(null,"needs_review")→"attention"`,
   `("attention","completed")→"attention"`, `("ok","cancelled")→"ok"`,
   `(null,"cancelled")→null`.
5. `"computeTabTitle: actividad gana, desenlace persiste, base intacta"` —
   `(3,null,"Stacky Agents")→"(3▶) Stacky Agents"`, `(0,"ok",…)→"✅ Stacky Agents"`,
   `(0,"attention",…)→"❌ Stacky Agents"`, `(0,null,…)→"Stacky Agents"`,
   `(2,"attention",…)→"(2▶) Stacky Agents"`.
6. `"buildNotificationBody: project+título, solo ticket_id, vacío"` —
   `{project:"p",ticket_title:"t"}→"p · t"`, `{ticket_id:7}→"Ticket 7"`,
   `{}→"Ejecución finalizada."`.

- **Comando exacto:** `npx vitest run src/services/__tests__/notifierCore.test.ts`
  (desde `Stacky Agents/frontend`). Deben FALLAR antes (módulo inexistente) y PASAR después.
- **Criterio de aceptación (binario):** 6/6 verdes + `npx tsc --noEmit` exit 0 +
  `grep -c "executions-running-global" -r src` = 0 (la query vieja del notificador ya no existe).
- **Flag:** no aplica (§3.1 F2). Las notificaciones siguen opt-in OFF por default.
- **Paridad runtimes:** la detección es por listas/`byId` de `/api/executions` y por el
  SSE del dock — idéntica para codex_cli / claude_code_cli / github_copilot.
- **Trabajo del operador: ninguno** (los avisos siguen apagados hasta que él los active en F6).

---

### F3 — Título de pestaña derivado del estado real + eliminación del flash (GAP 2)

**Objetivo (1 frase):** que el título de la pestaña muestre `(N▶)` mientras haya runs
activos y `✅`/`❌` persistente al terminar el último (hasta que el operador vuelva a
mirar), eliminando el flash de 4 s y su bug de título pegado.

**Archivo NUEVO:** `Stacky Agents/frontend/src/services/tabTitle.ts` — capa impura
FINA sobre la lógica pura de `notifierCore` (este módulo NO se testea con vitest
porque toca `document`; su lógica de decisión ya quedó testeada en F2 caso 5):

```ts
/**
 * Dueño ÚNICO de document.title (plan 134 F3). Reemplaza el flash de 4 s de
 * executionNotifier, que podía dejar el título pegado en "🤖 done — …" para
 * siempre si dos fines de run llegaban separados por 1.5–4 s (el revert tardío
 * re-instalaba un título ya flasheado). Acá el título se DERIVA del estado y el
 * título base se captura UNA sola vez, así ningún reorden de eventos lo corrompe.
 */
import { combineOutcome, computeTabTitle, type FinishOutcome } from "./notifierCore";

let baseTitle: string | null = null;
let activeCount = 0;
let lastOutcome: FinishOutcome = null;

function apply(): void {
  if (baseTitle == null) return;
  const next = computeTabTitle(activeCount, lastOutcome, baseTitle);
  if (document.title !== next) document.title = next;
}

/** Captura el título base una sola vez (idempotente — seguro ante StrictMode/HMR). */
export function initTabTitle(): void {
  if (baseTitle == null) baseTitle = document.title;
}

export function setActiveRunCount(n: number): void {
  initTabTitle();
  activeCount = Math.max(0, n);
  apply();
}

export function reportRunOutcome(status: string): void {
  initTabTitle();
  lastOutcome = combineOutcome(lastOutcome, status);
  apply();
}

/** El operador volvió a mirar la pestaña: limpiar el desenlace persistente. */
export function clearOutcome(): void {
  if (lastOutcome == null) return;
  lastOutcome = null;
  apply();
}
```

**Archivo a EDITAR 1:** `Stacky Agents/frontend/src/services/executionNotifier.ts` —
ELIMINAR el bloque del flash al final de `notifyExecutionFinished` (el comentario
`// Status bar flash…` + las 6 líneas de `originalTitle`/`document.title`/`setTimeout`,
hoy líneas 107-112, conservadas a propósito por F2). Tras esta edición el archivo no
debe contener NINGUNA referencia a `document.title`.

**Archivo a EDITAR 2:** `Stacky Agents/frontend/src/hooks/useGlobalExecutionNotifier.ts`
— 3 adiciones sobre la versión de F2:

1. Import: `import { clearOutcome, reportRunOutcome, setActiveRunCount } from "../services/tabTitle";`
2. Dentro del `.then((row) => { ... })` del `Executions.byId`, inmediatamente DESPUÉS de
   `notifyExecutionFinished({...});`, agregar:
   ```ts
             reportRunOutcome(String(row.status || "completed"));
   ```
3. Agregar estos dos efectos al final del cuerpo del hook (antes del cierre):
   ```ts
     // F3 — el título refleja el conteo real de runs activos.
     useEffect(() => {
       if (activeQ.data != null) setActiveRunCount(activeQ.data.length);
     }, [activeQ.data]);

     // F3 — mirar la pestaña (foco, visibilidad o click) limpia el ✅/❌ persistente.
     useEffect(() => {
       const clear = () => clearOutcome();
       const onVisibility = () => {
         if (document.visibilityState === "visible") clearOutcome();
       };
       window.addEventListener("focus", clear);
       window.addEventListener("pointerdown", clear);
       document.addEventListener("visibilitychange", onVisibility);
       return () => {
         window.removeEventListener("focus", clear);
         window.removeEventListener("pointerdown", clear);
         document.removeEventListener("visibilitychange", onVisibility);
       };
     }, []);
   ```

Casos borde ya decididos (no re-decidir): `cancelled` no pinta glifo (lo canceló el
operador — `combineOutcome` lo ignora); `attention` es pegajoso hasta el próximo
foco/click; si el operador está MIRANDO la pestaña cuando termina el run, el glifo
aparece y su siguiente click/foco lo limpia — sin timers, comportamiento determinista.

- **Tests:** la lógica de decisión ya está cubierta por
  `notifierCore.test.ts` casos 4-5 (F2). `tabTitle.ts` es glue de DOM sin test vitest
  propio — declarado y aceptado (gap RTL/jsdom, §4).
- **Comando / criterio de aceptación (binario):** `npx tsc --noEmit` exit 0 +
  `grep -rc "🤖 done" src` = 0 + `grep -c "document.title" src/services/executionNotifier.ts` = 0
  (todas desde `Stacky Agents/frontend`; en PowerShell usar
  `Select-String -Path src -Pattern "🤖 done" -SimpleMatch` → 0 resultados) + smoke F8.
- **Flag:** no aplica — justificación completa en §3.1 F3 (corrige bug real; el título
  no es contrato; revert = 1 archivo).
- **Paridad runtimes:** el conteo y los desenlaces salen de `/api/executions` —
  idéntico para los 3 runtimes.
- **Trabajo del operador: ninguno** (cero config; funciona solo).

---

### F4 — TopBar: badge "N agentes trabajando…" cableado a la fuente viva (GAP 4)

**Objetivo (1 frase):** recablear el badge y la progressbar del TopBar de
`workbench.runningExecutionId` (campo muerto) a la query compartida de runs activos,
mostrando el conteo real.

**Archivo a EDITAR (único):** `Stacky Agents/frontend/src/components/TopBar.tsx`

1. Agregar import: `import { useActiveRunsGlobal } from "../hooks/useActiveRunsGlobal";`
2. Reemplazar (hoy líneas 17-18):
   ```tsx
   // ANTES
   const runningExecutionId = useWorkbench((s) => s.runningExecutionId);
   const isRunning = runningExecutionId != null;
   // DESPUÉS
   // Plan 134 F4: fuente VIVA — la misma query compartida del panel global
   // (services/activeRuns.ts). El campo workbench.runningExecutionId estaba
   // muerto: solo lo seteaba useAgentRun (consumidor huérfano InputContextEditor)
   // y los flujos reales (launchAgentWithRuntime) nunca lo tocaron.
   const activeRunsCount = useActiveRunsGlobal().data?.length ?? 0;
   const isRunning = activeRunsCount > 0;
   ```
   (`useWorkbench` se CONSERVA: sigue usándose en las líneas siguientes — hoy
   `TopBar.tsx:19-23` — para `setActiveProject`, `setPinnedAgents`,
   `setAgentWorkflows`, `setTeamLoading` y `setGetAgentsError`.)
3. Reemplazar el texto del badge (hoy línea 199, dentro del span
   `styles.runningBadge`):
   ```tsx
   // ANTES
   Agente trabajando…
   // DESPUÉS
   {activeRunsCount === 1
     ? "Agente trabajando…"
     : `${activeRunsCount} agentes trabajando…`}
   ```
   El markup y las clases CSS (`runningBadge`, `badgeSpinner`, `progressBar` en la
   línea 207) quedan EXACTAMENTE iguales — cambio de lectura pura.

**PROHIBIDO en esta fase:** tocar `useAgentRun.ts`, `OutputPanel.tsx`,
`InputContextEditor.tsx` o `store/workbench.ts` (los componentes huérfanos y el campo
muerto NO se limpian acá — fuera de scope §8).

- **Tests:** la lógica nueva es `data?.length ?? 0 > 0` — trivial; el merge que la
  alimenta ya está testeado en F0. Test de componente omitido con justificación: gap
  RTL (§4) y TopBar exige mockear Projects/Health/react-query completos.
- **Comando / criterio de aceptación (binario):** `npx tsc --noEmit` exit 0 +
  `grep -c "runningExecutionId" src/components/TopBar.tsx` = 0 + smoke F8 paso 4.
- **Flag:** no aplica (§3.1). **Costo de red: 0** (queryKey compartida, §3.2).
- **Paridad runtimes:** el conteo incluye runs de cualquier runtime y cualquier proyecto.
- **Trabajo del operador: ninguno.**

---

### F5 — Badge numérico en el tab Revisión (GAP 3)

**Objetivo (1 frase):** que el botón `🧭 Revisión` muestre cuántos runs esperan revisión
(needs_review/error, 30 días, proyecto activo) aunque la página nunca se haya abierto,
compartiendo la query con la página para no duplicar requests.

**Archivo NUEVO 1:** `Stacky Agents/frontend/src/services/reviewInbox.ts`

```ts
/**
 * Query compartida página↔badge del inbox de revisión (plan 134 F5).
 * MISMA queryKey ⇒ react-query mantiene UNA sola cache y una sola request
 * (con la página abierta manda su intervalo de 30 s; cerrada, el del badge de 60 s).
 */
import { Executions } from "../api/endpoints";
import type { AgentExecution } from "../types";

export const reviewInboxQueryKey = (project: string | null) =>
  ["review-inbox", project] as const;

export function fetchReviewInbox(project: string | null): Promise<AgentExecution[]> {
  return Executions.list({
    project,
    status: ["needs_review", "error"],
    limit: 200,
    days: 30,
  });
}

/** Texto del badge: null = no renderizar badge. */
export function reviewBadgeLabel(count: number): string | null {
  if (count <= 0) return null;
  return count > 99 ? "99+" : String(count);
}
```

**Archivo NUEVO 2:** `Stacky Agents/frontend/src/hooks/useReviewInboxCount.ts`

```ts
import { useQuery } from "@tanstack/react-query";
import { useWorkbench } from "../store/workbench";
import { fetchReviewInbox, reviewInboxQueryKey } from "../services/reviewInbox";

/** Conteo de runs en needs_review/error (proyecto activo, 30 días) para el badge. */
export function useReviewInboxCount(): number {
  const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);
  const q = useQuery({
    queryKey: reviewInboxQueryKey(activeProjectName),
    queryFn: () => fetchReviewInbox(activeProjectName),
    refetchInterval: 60_000,
  });
  return q.data?.length ?? 0;
}
```

**Archivo a EDITAR 1:** `Stacky Agents/frontend/src/pages/ReviewInboxPage.tsx` —
migrar la query (hoy líneas 40-50) a la fuente compartida SIN cambiar su intervalo:

```tsx
  // ANTES: queryKey/queryFn inline
  // DESPUÉS
  const executionsQ = useQuery({
    queryKey: reviewInboxQueryKey(activeProjectName),
    queryFn: () => fetchReviewInbox(activeProjectName),
    refetchInterval: 30000,
  });
```

+ import `{ fetchReviewInbox, reviewInboxQueryKey }` de `../services/reviewInbox`.
La invalidación existente `qc.invalidateQueries({ queryKey: ["review-inbox", activeProjectName] })`
(hoy línea 73) sigue funcionando: la key compartida tiene exactamente esa forma.

**Archivo a EDITAR 2:** `Stacky Agents/frontend/src/App.tsx` — 3 ediciones ancladas
por contenido:

1. Imports (junto al import de `useGlobalExecutionNotifier`, hoy línea 27):
   ```tsx
   import { useReviewInboxCount } from "./hooks/useReviewInboxCount";
   import { reviewBadgeLabel } from "./services/reviewInbox";
   ```
2. Dentro de `App()`, inmediatamente después de `useGlobalExecutionNotifier();` (hoy
   línea 64):
   ```tsx
     const reviewCount = useReviewInboxCount();
     const reviewBadge = reviewBadgeLabel(reviewCount);
   ```
3. En el botón `🧭 Revisión` (hoy líneas 161-166), después del texto `🧭 Revisión`:
   ```tsx
             🧭 Revisión
             {reviewBadge != null && (
               <span
                 className={styles.navBadge}
                 aria-label={`${reviewCount} ejecuciones esperando revisión`}
               >
                 {reviewBadge}
               </span>
             )}
   ```

**Archivo a EDITAR 3:** `Stacky Agents/frontend/src/App.module.css` — agregar AL FINAL
del archivo:

```css
/* Plan 134 F5: contador de runs en needs_review/error sobre el tab Revisión.
   Rojo fijo con texto blanco: contraste garantizado en tema claro y oscuro. */
.navBadge {
  display: inline-block;
  margin-left: 6px;
  padding: 0 6px;
  min-width: 16px;
  border-radius: 8px;
  background: #b91c1c;
  color: #ffffff;
  font-size: 11px;
  font-weight: 700;
  line-height: 16px;
  text-align: center;
}
```

**Justificación del costo (guardarraíl 5):** con la página cerrada el badge agrega 1
request/60 s con `include_output=False` y `limit 200`; con la página abierta NO hay
request extra (queryKey compartida — react-query funde observadores y aplica el
intervalo más corto, 30 s, el mismo de hoy). Ningún intervalo existente cambia.

**Tests PRIMERO** — archivo NUEVO
`Stacky Agents/frontend/src/services/__tests__/reviewInbox.test.ts`, casos exactos:

1. `"reviewBadgeLabel: 0 y negativos → null"` — `reviewBadgeLabel(0) === null`,
   `reviewBadgeLabel(-3) === null`.
2. `"reviewBadgeLabel: 1..99 literal"` — `"1"`, `"99"`.
3. `"reviewBadgeLabel: >99 → 99+"` — `reviewBadgeLabel(100) === "99+"`.
4. `"reviewInboxQueryKey: forma exacta compartida con la página"` —
   `reviewInboxQueryKey("p")` deep-equal `["review-inbox", "p"]` y
   `reviewInboxQueryKey(null)` deep-equal `["review-inbox", null]`.

(`fetchReviewInbox` es un wrapper fino de `Executions.list` — sin test unitario propio,
declarado.)

- **Comando exacto:** `npx vitest run src/services/__tests__/reviewInbox.test.ts`.
  Deben FALLAR antes (módulo inexistente) y PASAR después.
- **Criterio de aceptación (binario):** 4/4 verdes + `npx tsc --noEmit` exit 0 + smoke
  F8 paso 5.
- **Flag:** no aplica (§3.1). **Paridad runtimes:** el conteo viene de
  `/api/executions` — runs de los 3 runtimes cuentan igual.
- **Trabajo del operador: ninguno.**

---

### F6 — Configuración → sub-tab "Notificaciones" (GAP 1)

**Objetivo (1 frase):** exponer en la UI los dos opt-in que el servicio ya soporta
(sonido y escritorio), persistiendo en las MISMAS claves localStorage que
`executionNotifier` ya lee, con estado visible del permiso del navegador.

**Archivo a EDITAR 1:** `Stacky Agents/frontend/src/services/executionNotifier.ts` —
2 exports nuevos (después de `requestDesktopPermission`, hoy línea 77):

```ts
/** Plan 134 F6: apagado explícito del aviso de escritorio desde la UI. */
export function setDesktopEnabled(enabled: boolean): void {
  localStorage.setItem(DESKTOP_KEY, enabled ? "true" : "false");
}

/** Plan 134 F6: beep de prueba — el click del toggle es el gesto de usuario que
 *  desbloquea el AudioContext del navegador, y de paso confirma que se oye. */
export function playTestBeep(): void {
  playBeep();
}
```

**Archivo a EDITAR 2:** `Stacky Agents/frontend/src/pages/SettingsPage.tsx` —
4 ediciones ancladas por contenido:

1. Ampliar el tipo (hoy línea 17):
   ```ts
   type SubTab = "flow" | "sections" | "client-profile" | "transfer" | "webhooks" | "notifications" | "harness" | "playground";
   ```
2. Import (junto a los imports existentes del archivo):
   ```ts
   import {
     isDesktopEnabled,
     isSoundEnabled,
     playTestBeep,
     requestDesktopPermission,
     setDesktopEnabled,
     setSoundEnabled,
   } from "../services/executionNotifier";
   ```
3. Botón del sub-tab: insertar DESPUÉS del botón `Webhooks` (hoy líneas 127-132) y
   ANTES del botón `Arnes`:
   ```tsx
           <button
             className={`${styles.subTab} ${sub === "notifications" ? styles.active : ""}`}
             onClick={() => setSub("notifications")}
           >
             Notificaciones
           </button>
   ```
4. Render del contenido: insertar después de la línea
   `{sub === "webhooks" && <WebhooksPanel />}` (hoy línea 152):
   ```tsx
           {sub === "notifications" && <NotificationsPanel />}
   ```
5. Componente NUEVO, agregado AL FINAL del archivo (mismo patrón in-file que
   `WebhooksPanel`, hoy línea 171; reusa las clases CSS existentes del módulo — CERO
   CSS nuevo):

```tsx
/**
 * Plan 134 F6 — Notificaciones de fin de run (opt-in, default OFF intacto).
 * Escribe las MISMAS claves localStorage que ya lee services/executionNotifier
 * (stacky.notify.sound / stacky.notify.desktop): cero mecanismos nuevos.
 */
function NotificationsPanel() {
  const [sound, setSound] = useState<boolean>(() => isSoundEnabled());
  const [desktop, setDesktop] = useState<boolean>(() => isDesktopEnabled());
  const [permission, setPermission] = useState<string>(() =>
    typeof Notification === "undefined" ? "unsupported" : Notification.permission
  );

  const toggleSound = () => {
    const next = !sound;
    setSoundEnabled(next);
    setSound(next);
    if (next) playTestBeep();
  };

  const toggleDesktop = async () => {
    if (desktop) {
      setDesktopEnabled(false);
      setDesktop(false);
      return;
    }
    const granted = await requestDesktopPermission();
    setDesktop(granted);
    setPermission(
      typeof Notification === "undefined" ? "unsupported" : Notification.permission
    );
  };

  return (
    <div className={styles.sectionsPanel}>
      <p className={styles.sectionsIntro}>
        Avisos al terminar una ejecución — de cualquier runtime y cualquier proyecto.
        Ambos son opt-in y quedan guardados en este navegador.
      </p>
      <div className={styles.row}>
        <div className={styles.rowLabel}>
          <span className={styles.rowTitle}>Sonido al terminar un run</span>
          <span className={styles.rowHint}>
            Beep corto (al activarlo se reproduce uno de prueba).
          </span>
        </div>
        <button className={styles.subTab} onClick={toggleSound}>
          {sound ? "Desactivar" : "Activar"}
        </button>
      </div>
      <div className={styles.row}>
        <div className={styles.rowLabel}>
          <span className={styles.rowTitle}>Notificación de escritorio</span>
          <span className={styles.rowHint}>
            {permission === "denied"
              ? "El navegador tiene el permiso BLOQUEADO para este sitio; habilitalo en la configuración del navegador y reintentá."
              : permission === "unsupported"
                ? "Este navegador no soporta notificaciones de escritorio."
                : "Requiere permiso del navegador (se pide al activar). Click en la notificación = volver a Stacky."}
          </span>
        </div>
        <button
          className={styles.subTab}
          onClick={toggleDesktop}
          disabled={permission === "unsupported" || (permission === "denied" && !desktop)}
        >
          {desktop ? "Desactivar" : "Activar"}
        </button>
      </div>
    </div>
  );
}
```

Casos borde ya decididos: permiso `denied` → botón deshabilitado + hint explicativo
(no hay forma programática de re-pedir un permiso denegado); navegador sin
`Notification` → deshabilitado con hint; activar sonido reproduce beep de prueba (el
click es el gesto que exige la política de autoplay del navegador).

- **Tests:** los toggles delegan 1:1 en funciones del servicio ya existentes
  (`isSoundEnabled`/`setSoundEnabled`/`isDesktopEnabled`/`requestDesktopPermission`) y
  en 2 exports nuevos triviales; no hay lógica pura nueva no trivial que extraer. Test
  de componente omitido con justificación (gap RTL §4). Verificación = criterios
  binarios de abajo + smoke F8 pasos 1-3.
- **Criterio de aceptación (binario):** `npx tsc --noEmit` exit 0; en la app:
  activar "Sonido" deja `localStorage["stacky.notify.sound"] === "true"` (verificable
  en devtools) y suena el beep de prueba; activar "Escritorio" dispara el prompt del
  navegador y con permiso concedido deja `localStorage["stacky.notify.desktop"] === "true"`.
- **Flag:** no aplica (§3.1) — y los defaults actuales (ambos OFF) quedan intactos.
- **Paridad runtimes:** los avisos que estos toggles habilitan se disparan por fin de
  run de cualquier runtime (F2).
- **Trabajo del operador: opt-in (default off)** — única fase con interacción opcional.

---

### F7 — Fila del panel con proyecto y título del ticket (GAP 6, mitad frontend)

**Objetivo (1 frase):** que cada fila de "EJECUCIONES ACTIVAS" y el confirm de cancelar
digan proyecto y título del ticket (campos de F1), degradando exactamente al texto
actual si el backend aún no los envía.

**Archivo a EDITAR:** `Stacky Agents/frontend/src/components/ActiveRunsPanel.tsx`
(2 ediciones ancladas por CONTENIDO — el plan 132 puede haber insertado su botón en la
misma fila; NO tocarlo):

1. Reemplazar el span de meta (hoy líneas 135-137):
   ```tsx
   // ANTES
   <span className={styles.meta}>
     ticket {e.ticket_id} · {e.agent_type} · {e.status}
   </span>
   // DESPUÉS — visible: proyecto · título (o ticket N) · agente · status.
   // El hover (title) lleva el detalle completo; la clase meta ya tiene ellipsis.
   <span
     className={styles.meta}
     title={`${e.project ?? "proyecto ?"} · ticket ${e.ticket_id}${e.ticket_title ? ` · ${e.ticket_title}` : ""} · ${e.agent_type} · ${e.status}`}
   >
     {e.project ? `${e.project} · ` : ""}
     {e.ticket_title ?? `ticket ${e.ticket_id}`} · {e.agent_type} · {e.status}
   </span>
   ```
2. Reemplazar el texto del `window.confirm` (hoy líneas 146-148):
   ```tsx
   // ANTES
   `¿Cancelar la ejecución #${e.id} (ticket ${e.ticket_id}, ${e.agent_type})? Se detendrá la sesión del agente.`
   // DESPUÉS
   `¿Cancelar la ejecución #${e.id}? ${e.project ? `[${e.project}] ` : ""}${e.ticket_title ?? `ticket ${e.ticket_id}`} · ${e.agent_type}. Se detendrá la sesión del agente.`
   ```

Sin cambios de CSS: `styles.meta` ya trunca con ellipsis (verificado por plan 132 §6,
riesgo de layout). Degradación garantizada: con un backend viejo (sin F1) los campos
son `undefined` → la fila muestra `ticket {id} · agente · status`, igual que hoy.

**Tests PRIMERO** — archivo NUEVO
`Stacky Agents/frontend/src/components/__tests__/ActiveRunsPanel.ticketContext.test.tsx`
(archivo SEPARADO del test existente para no colisionar con las ediciones del plan 132;
copiar el patrón exacto de mocks/wrap/mockRuns de
`ActiveRunsPanel.test.tsx:20-78`, incluida la NOTA DE ENTORNO de sus líneas 12-17),
2 tests con estos nombres:

1. `"muestra proyecto y título del ticket cuando el backend los envía"` — run con
   `project: "proj-x"`, `ticket_title: "Migrar login"` → la fila contiene
   `proj-x · Migrar login`.
2. `"degrada a 'ticket N' cuando el backend no envía contexto"` — run sin esos campos →
   la fila contiene `ticket 42` y NO contiene `proj-x`.

- **Comando exacto:** `npx vitest run src/components/__tests__/ActiveRunsPanel.ticketContext.test.tsx`
  — hoy fallará SOLO por el gap RTL/jsdom preexistente (§4); cualquier otro error
  bloquea. Queda listo para correr.
- **Criterio de aceptación (binario):** `npx tsc --noEmit` exit 0 + smoke F8 paso 6.
- **Flag:** no aplica (§3.1). **Paridad runtimes:** la fila muestra contexto para runs
  de cualquier runtime (los campos vienen del ticket, no del runtime).
- **Trabajo del operador: ninguno.**

---

### F8 — Verificación integral (estática + smoke manual)

**Objetivo (1 frase):** demostrar con comandos y con la app corriendo que las 6 señales
funcionan y nada se degradó.

**Comandos exactos, en este orden:**

1. Desde `Stacky Agents/frontend`:
   - `npx tsc --noEmit` → **exit 0, 0 errores.**
   - `npx vitest run src/services/__tests__/activeRuns.test.ts` → 3/3.
   - `npx vitest run src/services/__tests__/notifierCore.test.ts` → 6/6.
   - `npx vitest run src/services/__tests__/reviewInbox.test.ts` → 4/4.
   - `npx vitest run src/components/__tests__/ActiveRunsPanel.ticketContext.test.tsx` →
     verde, o rojo SOLO por el gap RTL/jsdom preexistente (§4).
2. Desde `Stacky Agents/backend` (PowerShell):
   - `& ".\.venv\Scripts\python.exe" -m pytest .\tests\test_executions_ticket_context.py -q` → 5/5.
3. NO correr la suite completa de ninguno de los dos lados (regla del repo: por archivo).

**Smoke manual (8 pasos, con backend y frontend levantados):**

1. Configuración → Notificaciones: activar "Sonido" → suena beep de prueba y
   `localStorage["stacky.notify.sound"]==="true"`. Activar "Escritorio" → prompt del
   navegador; conceder → estado reflejado.
2. Lanzar un agente cualquiera (runtime `claude_code_cli` o `codex_cli`) → el título de
   la pestaña pasa a `(1▶) Stacky Agents` y el TopBar muestra "Agente trabajando…" con
   spinner y progressbar.
3. Cambiar el foco a OTRA ventana y esperar el fin del run → notificación de
   escritorio con proyecto/título del ticket + beep; click en la notificación →
   Chrome/Edge enfoca la pestaña de Stacky.
4. Al terminar el último run activo, el título queda `✅ Stacky Agents` (o `❌` si
   terminó en error) SIN revertirse solo; al hacer foco/click en la pestaña vuelve a
   `Stacky Agents`. Esperar 2 minutos: el título NO vuelve a flashear (bug del flash
   pegado: muerto).
5. Con ≥1 ejecución en needs_review/error (30 días): el tab `🧭 Revisión` muestra el
   badge rojo con el número SIN abrir la página; abrir la página → los conteos
   coinciden.
6. Con un run activo, el panel "EJECUCIONES ACTIVAS" muestra
   `{proyecto} · {título} · {agente} · {status}` en la fila; click en "✕ Cancelar" →
   el confirm menciona proyecto y título.
7. Lanzar 2 runs cortos casi simultáneos (p. ej. dos tickets con runtime `mock` o
   `github_copilot`) → al terminar ambos llegan DOS notificaciones (no una).
8. Runtime `github_copilot`: repetir el paso 2-4 con un run de ese runtime → todas las
   señales (título, TopBar, notificación, panel) se comportan igual (paridad).

- **Criterio de aceptación (binario):** todos los comandos del punto 1-2 en verde (con
  la única excepción documentada del gap RTL) y los 8 pasos del smoke pasan tal cual.
- **Trabajo del operador: ninguno** (el smoke lo hace quien implementa).

## 6. Paridad de runtimes (tabla resumen)

| Señal | codex_cli | claude_code_cli | github_copilot (y mock) | Mecanismo común |
|---|---|---|---|---|
| Título de pestaña `(N▶)`/`✅`/`❌` | ✔ | ✔ | ✔ | query compartida `/api/executions` (F0) |
| Notificación escritorio + beep | ✔ | ✔ | ✔ | notificador global + `byId` (F2); el SSE del dock también notifica y el dedup por execution_id evita el doble aviso |
| TopBar "N agentes trabajando…" | ✔ | ✔ | ✔ | misma query compartida (F4) |
| Badge Revisión | ✔ | ✔ | ✔ | `/api/executions?status=needs_review,error` (F5) |
| Proyecto/título en panel y confirm | ✔ | ✔ | ✔ | campos de `Ticket` vía `to_dict` (F1/F7) |

No hay fallback por runtime que implementar: ninguna señal lee nada específico del
runtime.

## 7. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Colisión de líneas con planes 132/135/136 en `ActiveRunsPanel.tsx`/`App.tsx`/`TopBar.tsx`/`SettingsPage.tsx` | Ediciones ancladas por CONTENIDO (§3.3); orden sugerido: implementar 132 antes de F7; staging quirúrgico con pathspec explícito; los módulos nuevos no colisionan con nadie. |
| N+1 por acceso a `AgentExecution.ticket` en listas | `joinedload` en `list_executions` (1 JOIN) + kwarg opt-in default False → cero lazy-loads nuevos en los demás callers (evidencia F1). |
| `joinedload` + `join(Ticket)` del filtro por proyecto | SQLAlchemy aísla el eager-load en un alias propio; cubierto por los tests F1 (caso 1 con `all_projects`, y el filtro por proyecto no cambia). |
| Permiso de Notification denegado / navegador sin soporte | La UI muestra el estado y deshabilita el toggle con hint accionable (F6); `isDesktopEnabled` ya exige `permission === "granted"` (`executionNotifier.ts:58-64`). |
| AudioContext bloqueado por política de autoplay | El beep de prueba se dispara en el click del toggle (gesto de usuario) → desbloquea el contexto (F6). |
| Título con glifo pegado (el bug que motivó F3) | Imposible por construcción: título base capturado UNA vez + derivación de estado (sin captura-y-revert); verificado por grep (KPI-2). |
| `pointerdown` limpia el ✅/❌ "demasiado rápido" | Intencional: un click DENTRO de la página significa que el operador ya está mirando — la señal cumplió su función. |
| Muchos runs terminando juntos → ráfaga de beeps | Gate de beep de 1 s (`BEEP_GAP_MS`) SOLO para el sonido; los avisos de escritorio y el desenlace del título salen todos (F2). |
| Query del badge de Revisión duplicando la de la página | Misma queryKey ⇒ una sola cache/request (F5); congelada por el test de forma de key. |
| Backend viejo sin campos F1 (deploy desfasado) | El frontend degrada explícitamente al texto actual (`ticket {id}`) — F7 test 2 y `buildNotificationBody` con fallback. |
| Falso "terminaron todos" si la query de runs entra en error de red | Guard `activeQ.data == null` en el notificador (F2): sin snapshot no se compara. |

## 8. Fuera de scope (prohibido en este plan)

- Manejo de errores de carga/mutación, ErrorBoundary y toasts unificados (**plan 135**).
- Doble-submit, guards de backdrop, higiene de cambio de proyecto, persistencia de la
  consola tras F5 (**plan 136**).
- Botón "Ver consola" en `ActiveRunsPanel` (**plan 132**, ya propuesto).
- Limpiar los componentes huérfanos (`InputContextEditor`, `OutputPanel`) o el campo
  muerto `workbench.runningExecutionId` — se documenta el hallazgo, no se borra código
  ajeno a las señales.
- Favicon dinámico (0 referencias hoy; queda como evolución futura si el operador lo pide).
- Resolver el gap de entorno RTL/jsdom de los tests de componente.
- Notificaciones por webhook/Teams (ya cubiertas por el panel Webhooks existente).
- Cualquier flag de harness, migración de DB o endpoint nuevo.

## 9. Glosario (para un modelo menor sin contexto de Stacky)

- **Run / ejecución:** una fila `AgentExecution` (backend `models.py:207`) — una corrida
  de un agente IA sobre un ticket. Estados: `queued`, `preparing`, `running`,
  `completed`, `error`, `cancelled`, `needs_review`.
- **Runtime:** el motor que ejecuta el agente. Hay 3 productivos: `codex_cli`,
  `claude_code_cli` y `github_copilot` (más `mock` para tests). Toda feature debe
  funcionar con los 3 ("paridad de runtimes").
- **needs_review:** estado final que exige veredicto humano (human-in-the-loop). La
  página que los lista es `ReviewInboxPage` (tab `🧭 Revisión`).
- **Workbench store:** store global zustand del frontend
  (`frontend/src/store/workbench.ts`) — proyecto activo, consola abierta, overrides.
- **ADO:** Azure DevOps, el tracker de tickets. `ticket_id` es el id LOCAL de la DB de
  Stacky (no el id de ADO).
- **Harness flags:** feature-flags del backend (`services/harness_flags.py`) visibles
  en Configuración → Arnés. Este plan NO agrega ninguna (§3.1).
- **queryKey / dedup de react-query:** dos `useQuery` con la MISMA key comparten cache
  y red — es el mecanismo que hace gratis al TopBar (F4) y al badge (F5).
- **Dock / consola:** `CodexConsoleDock` (montado en `App.tsx:269`), stream SSE de logs
  de una ejecución; su `useExecutionStream` también notifica fines de run.
- **Opt-in por localStorage:** las claves `stacky.notify.sound` /
  `stacky.notify.desktop` con valor literal `"true"` activan sonido/escritorio
  (`executionNotifier.ts:11-12`); cualquier otro valor = apagado.

## 10. Orden de implementación

1. **F0** — sustrato compartido (`activeRuns.ts` + `useActiveRunsGlobal` + migración del panel) — tests `activeRuns.test.ts` primero.
2. **F1** — backend `project`/`ticket_title` + `joinedload` + types.ts + ratchet — tests pytest primero.
3. **F2** — `notifierCore.ts` + dedup + alcance global del notificador — tests `notifierCore.test.ts` primero.
4. **F3** — `tabTitle.ts` + eliminación del flash + wiring en el hook global.
5. **F4** — TopBar recableado.
6. **F5** — badge Revisión (service + hook + página + App + CSS) — tests `reviewInbox.test.ts` primero.
7. **F6** — Settings → Notificaciones (exports nuevos + sub-tab + panel).
8. **F7** — fila del panel con contexto — test de componente nuevo primero (listo para correr).
9. **F8** — verificación integral + smoke de 8 pasos.

Cada fase termina con `npx tsc --noEmit` en verde antes de pasar a la siguiente.

## 11. Definición de Hecho (DoD global)

- [ ] `npx tsc --noEmit` (frontend) = 0 errores.
- [ ] Vitest por archivo: `activeRuns.test.ts` 3/3, `notifierCore.test.ts` 6/6,
      `reviewInbox.test.ts` 4/4 — todos ejecutados de verdad, output leído.
- [ ] Pytest por archivo: `test_executions_ticket_context.py` 5/5 con
      `backend/.venv/Scripts/python.exe`, y el archivo registrado en
      `run_harness_tests.sh` Y `run_harness_tests.ps1`.
- [ ] `ActiveRunsPanel.ticketContext.test.tsx` existe, compila, y falla SOLO por el gap
      RTL preexistente (o pasa, si el gap se resolvió).
- [ ] KPI-1..KPI-7 de §1 verificados (KPI-2 y KPI-4 incluyen sus greps binarios).
- [ ] Grep-gates: `grep -rc "🤖 done" src` = 0; `document.title` solo en
      `services/tabTitle.ts`; `executions-running-global` = 0 hits;
      `runningExecutionId` = 0 hits en `TopBar.tsx`.
- [ ] Los defaults de notificaciones siguen OFF (claves localStorage ausentes = sin
      sonido, sin escritorio) — cero trabajo nuevo obligatorio para el operador.
- [ ] Ningún intervalo de polling existente cambió (5 s panel, 30 s página Revisión,
      1.5 s OutputPanel, 60 s tickets): diff revisado.
- [ ] Ningún cambio en `harness_flags.py`, `config.py`, `harness_flags_help.py`,
      `HarnessFlagsPanel`, migraciones ni endpoints nuevos.
- [ ] Smoke F8 (8 pasos) pasado, incluido el paso 8 de paridad `github_copilot`.
- [ ] Diff limitado a los archivos listados en las fases (7 nuevos frontend + 1 nuevo
      backend test + 8 editados); staging con pathspec explícito, sin arrastrar WIP ajeno.
