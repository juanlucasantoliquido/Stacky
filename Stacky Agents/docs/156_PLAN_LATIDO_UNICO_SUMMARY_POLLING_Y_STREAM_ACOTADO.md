# Plan 156 — Latido único: summary de polling y stream acotado

> **Estado:** PROPUESTO v1 (2026-07-16) · **Autor:** StackyArchitectaUltraEficientCode
> **Origen:** debate adversarial 2026-07-16 con auditoría empírica de los logs del deploy y del árbol de frontend. Toda la evidencia archivo:línea de este doc fue **re-verificada contra el árbol el 2026-07-16**; los números de línea son referencia de ese día — **toda edición se ancla por TEXTO normativo citado, no por número de línea**.
> **Orden en el roadmap:** **tercero**, después del plan del ledger de publicación transaccional (153) y el del arnés veraz (154). Independiente de ambos: ninguno lo bloquea a él ni él a ellos. Sus fases F1/F2 son **GATE** del plan del centro de notificaciones y actividad unificada (152, aún sin implementar): ese plan DEBE consumir el canal de summary de F1/F2 en lugar de nacer con poller propio.
> **Runtimes:** este plan es **UI de observación + un endpoint backend de lectura**, 100% agnóstico del runtime de agentes (Codex CLI, Claude Code CLI, GitHub Copilot Pro). Ninguna fase toca el camino de ejecución de agentes ni el de publicación; el endpoint nuevo agrega objetos ya serializados por el mismo `to_dict` que ven los 3 runtimes. La paridad de runtimes es automática por vacuidad. Se declara igual por fase.
> **Flags nuevas:** **NINGUNA.** Endpoint aditivo con paridad testeada + cambios internos de frontend + ampliación de un filtro de log ya existente. Precedente directo: los planes de estados universales (140), tema claro/oscuro (141) y sistema de movimiento (143) se implementaron sin flag. NO se toca `FLAG_REGISTRY`, NO se toca `_CURATED_DEFAULTS_ON`, NO hay panel nuevo.
> **Human-in-the-loop:** N/A — no hay acciones automáticas hacia afuera; no hay decisiones que se le quiten al operador. El plan REDUCE ruido y carga sin cambiar ninguna decisión suya.

---

## 1. Objetivo + KPI / impacto esperado

**Objetivo (1 párrafo):** un avión no tiene 12 relojes preguntándole al motor cada uno por su cuenta; tiene UN bus de datos y N instrumentos que lo leen. Hoy la UI de Stacky hace lo contrario: dispara **6 GET `/api/executions`** por tick (dos módulos distintos, cada uno con 3 llamadas por estado) y el **87-89% del access-log del deploy es la UI hablándose a sí misma**; en la otra punta, el stream de logs de ejecución **crece sin límite en memoria** (lista de líneas + Set de dedup, ambos infinitos) y **TicketBoard entero se re-renderiza cada segundo** por un reloj de "hace Xs" que vive dentro de un hook global. Este plan instala el **latido único**: un endpoint `GET /api/executions/summary` que colapsa las 6 llamadas en 1, un **poller central** con backoff en pestaña oculta, un **ring-buffer** que acota el stream a 5000 líneas, un reloj **aislado en una hoja**, y la extensión del **filtro de access-log ya existente** para que los pollers 200 dejen de ensuciar el archivo. Menos red, menos render, misma información, y el canal queda listo para que el plan del centro de notificaciones (152) lo consuma en vez de nacer con su propio poller.

**KPIs binarios (comandos exactos; backend desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend` con `.venv\Scripts\python.exe` — el venv real verificado en disco es `backend\.venv` py3.13, `backend/venv` NO existe; frontend desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend` con `npx vitest run`):**

- **KPI-1 — Summary verde y con paridad:** `.venv\Scripts\python.exe -m pytest tests/test_executions_summary.py -q` → exit 0 (incluye el test de paridad exacta de campos vs `/api/executions`).
- **KPI-2 — Poller central verde:** `npx vitest run src/services/__tests__/executionsSummary.test.ts` → exit 0 (una request por tick vía react-query core; backoff de visibilidad ×4).
- **KPI-3 — Ring-buffer verde:** `npx vitest run src/hooks/__tests__/logRingBuffer.test.ts` → exit 0 (20.000 líneas → `lines.length ≤ 5000` Y `seen.size ≤ 5000` Y `dropped === 15000`).
- **KPI-4 — Reloj aislado verde:** `npx vitest run src/components/__tests__/syncStatus.test.ts` → exit 0 (helpers puros de "hace Xs" y stale) **y** `grep -c "setInterval" src/hooks/useTicketSync.ts` → `0`.
- **KPI-5 — Filtro de access-log verde:** `.venv\Scripts\python.exe -m pytest tests/test_access_log_suppress_pollers.py -q` → exit 0 (las rutas nuevas se descartan del FileHandler; el mecanismo env `STACKY_ACCESS_LOG_SUPPRESS_PATHS` sigue intacto).
- **KPI-6 — Tipos verdes:** `npx tsc --noEmit` → exit 0.
- **KPI-7 — Ratchet de deuda visual verde:** `npx vitest run src/__tests__/uiDebtRatchet.test.ts` → exit 0 (los .tsx nuevos nacen con 0 `style={{` inline **y** el contador nuevo de diálogos nativos del navegador no aumenta).
- **KPI-8 — Ratchet de tests registrado:** `grep -c "test_executions_summary.py" scripts/run_harness_tests.sh` → `1` e ídem `.ps1` → `1`, y lo mismo para `test_access_log_suppress_pollers.py`.

**KPIs de impacto (proyectados, verificables por observación manual en el deploy):**

| Métrica | Hoy | Con el plan |
|---|---|---|
| GET `/api/executions` de runs activos por tick | 6 | 1 (`/api/executions/summary`) |
| Líneas de polling en el access-log del archivo | ~87-89% del total | ~0 (suprimidas por el filtro) |
| Líneas del stream retenidas en memoria del frontend | ilimitado | ≤ 5000 (+ Set de dedup ≤ 5000) |
| Re-renders de TicketBoard por minuto causados por el reloj | 60 | ~0 |

**Impacto esperado:** el navegador abre 1/6 de las conexiones que abre hoy para lo mismo; el archivo de log del deploy pasa a ser legible (deja de estar dominado por GETs 200 de no-op); una ejecución larga deja de acumular memoria sin cota en el cliente; el board deja de reconciliarse 60 veces por minuto por un contador de segundos; y el canal de summary queda disponible para el centro de notificaciones (152).

---

## 2. Por qué ahora / gap que cierra (evidencia verificada 2026-07-16)

### 2.1 L6 — Ráfagas de polling: 6 GET `/api/executions` por tick, en dos módulos

- `frontend/src/services/activeRuns.ts:31-34` — `fetchActiveRuns()` hace `Promise.all` de **3** `Executions.list(...)`: `{status:"running", all_projects:true}` (`:32`), `{status:"preparing", all_projects:true}` (`:33`), `{status:"queued", all_projects:true}` (`:34`). Cadencia: `ACTIVE_RUNS_REFRESH_MS = 5_000` (`:13`). Consumido por el panel de runs activos, el TopBar y el notificador global (comentario `:2-7`).
- `frontend/src/hooks/useRunningStatus.ts:63,70,77` — el hook hace **otros 3** `Executions.list(...)` por proyecto: running (`:63`), preparing (`:70`), queued (`:77`), cada uno con `refetchInterval: EXEC_POLL_INTERVAL` = `5_000` (`:38`, aplicado en `:64/:71/:78`).
- Suma: **6 GET `/api/executions` en el mismo segundo**, cada 5 s. Esto explica los ~4.505 GETs de executions en 30 h observados en los logs del deploy, sumado a `/api/diag/local` cada ~17 s (6.364×), `/api/cost-cap` (3.430×) y `/api/streak` (688×). El polling total es **~87-89% del access-log**.
- **`GET /api/executions/summary` NO existe hoy** (verificado: `grep summary backend/api/executions.py` → 0 matches). El endpoint que colapsa las 6 llamadas hay que crearlo (F1).

### 2.2 Callers que NO se migran (inventario cerrado en el debate — no tocarlos)

- `frontend/src/services/reviewInbox.ts:12-19` — `fetchReviewInbox()` llama `Executions.list({status:["needs_review","error"], limit:200, days:30})`. Tiene **cache y cadencia propias de react-query** (página abierta 30 s, badge 60 s; comentario `:1-5`, MISMA `queryKey` compartida). Es un dominio distinto (inbox de revisión, no runs activos). **NO se fuerza al poller central.**
- `frontend/src/hooks/useAutoFillBlocks.ts:31` — `Executions.list({ticket_id, agent_type, status:"completed"})` dentro de un `useQuery` **on-demand** (`enabled: activeTicketId != null && precedingType != null`, `:36`), sin `refetchInterval`. No es polling.
- `frontend/src/components/AgentHistoryPage.tsx:387` — `Executions.list({ticket_id, agent_filename, include_output:true, limit:100})` dentro de un `useEffect` disparado por cambios de props (`:384-396`). **On-demand**, no polling.

### 2.3 U2 — El stream de logs crece sin cota (lista + Set de dedup, ambos infinitos)

- `frontend/src/hooks/useExecutionStream.ts:75` — cada evento de log hace `setState((s) => ({ ...s, lines: [...s.lines, data!] }))`: la lista `lines` crece **sin límite** durante toda la vida del stream.
- `frontend/src/hooks/useExecutionStream.ts:39` — `seenKeys` es un `useRef<Set<string>>` de dedup; se le hace `.has()` (`:72`) y `.add()` (`:73`) por cada línea y **nunca se poda**: crece igual de infinito que `lines`.
- **3 consumidores del mismo hook** (corrección de drift respecto del texto del debate, que citaba 2): `frontend/src/components/LogsPanel.tsx:10`, `frontend/src/components/CodexConsoleDock.tsx:62` y `frontend/src/components/OutputPanel.tsx:22`. Acotar en el hook los cubre a los **tres** de una vez.
- `frontend/src/components/LogsPanel.tsx:27` — `{stream.lines.map((l, i) => ...)}` renderiza **todas** las líneas, sin ventana de render.
- `frontend/package.json` — NO tiene ninguna librería de virtualización (no `react-window`, no `@tanstack/react-virtual`). La cota se implementa **sin libs nuevas**.

### 2.4 U8 — El reloj de "hace Xs" re-renderiza TicketBoard entero cada segundo

- `frontend/src/hooks/useTicketSync.ts:55` — `const [, setTick] = useState(0); // para forzar re-render del reloj`.
- `frontend/src/hooks/useTicketSync.ts:65-68` — un `useEffect` con `setInterval(() => setTick(t => t + 1), 1000)`: cada segundo fuerza un re-render del hook.
- Consumidor único: `frontend/src/pages/TicketBoard.tsx:757` (`useTicketSync({...})`), un archivo de **1133 líneas** (corrección de drift: el debate citaba 1102; hoy son 1133). Como el hook vive dentro del componente del board, ese `setTick` reconcilia el board completo **60 veces por minuto** solo para actualizar un contador de segundos.
- El texto del reloj se renderiza en una hoja: `frontend/src/components/SyncStatusBar.tsx` (TicketBoard le pasa `lastSyncedAt`/`secondsSinceSync`/`isStale` en `:995-1000`). El hook ya expone `lastSyncedAt` (`:29`, `:235`); mover el tic-tac a la hoja es directo.

### 2.5 Sustrato de supresión de access-log ya existente (se REUSA y se amplía)

- `backend/services/local_file_logging.py:68` — `_DEFAULT_SUPPRESSED_PATHS = ("/api/v1/pipeline/status",)`: el mecanismo de supresión del access-log del FileHandler **ya existe** (introducido por el plan de higiene de logs, 145).
- `backend/services/local_file_logging.py:75-80` — `_suppressed_paths()` concatena el default con el CSV de la env `STACKY_ACCESS_LOG_SUPPRESS_PATHS` (extensión del operador, `:76`).
- `backend/services/local_file_logging.py:83-98` — `_AccessLogNoiseFilter.filter()` solo actúa sobre records del logger `werkzeug` (`:92`) y descarta si **cualquier** path suprimido es substring del mensaje (`:98`, `p in message`). El default de hoy solo cubre `pipeline/status`; NO cubre los pollers 200 (diag/local, cost-cap, streak, executions).

### 2.6 Infra existente que se REUSA (leída, no supuesta)

| Símbolo | Archivo:línea (2026-07-16) | Rol en 156 |
|---|---|---|
| `list_executions` + su query | `backend/api/executions.py:28-86` | F1 extrae la construcción de filtros a un helper y la reusa por estado; el serializer es `to_dict(include_output=False, include_ticket_context=True)` (`:86`) — el summary usa EXACTAMENTE el mismo. |
| Blueprint `executions` | `backend/api/executions.py:24` (`url_prefix="/executions"`, registrado bajo `/api`) | La ruta nueva es `@bp.get("/summary")` → resuelve a `/api/executions/summary`. La ruta estática `/summary` NO colisiona con `/<int:execution_id>` (`:89`): el conversor `int` no matchea "summary" y Flask prioriza rutas estáticas. |
| `resolve_project_context` | `backend/services/project_context.py` (usado en `executions.py:57`) | El summary resuelve scope idéntico a `list_executions`. |
| `Executions.list` | `frontend/src/api/endpoints.ts` (grupo `Executions`; firma `list(params)` con `streamUrl`) | F2 agrega `Executions.summary(scope)` al mismo grupo. |
| `mergeActiveRuns` | `frontend/src/services/activeRuns.ts:20-28` | Selector PURO que F2 reusa tal cual sobre las 3 listas del summary. |
| `ACTIVE_RUNS_QUERY_KEY` / `ACTIVE_RUNS_REFRESH_MS` | `frontend/src/services/activeRuns.ts:12-13` | F2 reemplaza el fetch de 3 llamadas por 1 al summary bajo una `queryKey` central única. |
| `document.visibilityState` | patrón ya usado en `frontend/src/hooks/useTicketSync.ts:201` | F2 lo lee en el `refetchInterval` del poller central (×4 si `hidden`). |
| `dedupKey` | `frontend/src/hooks/useExecutionStream.ts:56-57` | F3 lo mueve al módulo puro del ring-buffer (para poder evictar la key de una línea que sale de ventana). |
| `SyncStatusBar` | `frontend/src/components/SyncStatusBar.tsx` | F4 le da su propio reloj de 1 s y lo memoiza. |
| `uiDebtRatchet` + baseline | `frontend/src/__tests__/uiDebtRatchet.test.ts` + `frontend/src/__tests__/uiDebtBaseline.json` (helper `countMatches` exportado `:29`, regen con `UI_DEBT_REGEN=1` `:104`) | F6 agrega una tercera dimensión (`nativeDialogByFile`) al MISMO baseline. |
| `_AccessLogNoiseFilter` / `_suppressed_paths` / `_DEFAULT_SUPPRESSED_PATHS` | `backend/services/local_file_logging.py:68-98` | F5 amplía `_DEFAULT_SUPPRESSED_PATHS`; NO toca el mecanismo env. |
| `HARNESS_TEST_FILES` (sh + ps1) | `backend/scripts/run_harness_tests.sh` y `.ps1` | Registro de los 2 tests backend nuevos (F1, F5). |

---

## 3. Principios y guardarraíles

1. **Un bus, N instrumentos.** El summary es una fuente única: todos los que hoy pollean runs activos leen de la MISMA `queryKey` de react-query (dedup nativo de react-query ⇒ 1 request de red aunque haya N suscriptores). No se inventan pollers paralelos.
2. **Paridad byte por byte, no reimplementación.** El summary NO reimplementa la serialización: reusa el mismo helper de query y el mismo `to_dict` que `/api/executions`. El test de paridad (F1) exige que, para los mismos filtros, los objetos sean idénticos. Así el endpoint viejo y el nuevo nunca divergen.
3. **Acotar, nunca borrar.** El ring-buffer limita la ventana **en memoria del frontend**; el log completo sigue en disco en el backend. La `dedup window` se ata a la `ring window` a propósito (§4). Nada se pierde del sustrato; solo se acota lo que el navegador retiene.
4. **Cero trabajo extra al operador.** Ninguna config nueva, ningún flag, todo invisible y automático. El endpoint viejo `/api/executions` NO se elimina (backward-compatible: quien lo llame directo sigue funcionando).
5. **No degradar.** El endpoint agregado REDUCE carga de red; el ring-buffer PROTEGE la memoria; el aislamiento del reloj BAJA los renders; la supresión de log MEJORA la observabilidad. Ningún eje empeora.
6. **Respetar los callers que ya están bien.** `reviewInbox` tiene su propia cache/cadencia react-query por una razón (dominio distinto): NO se lo fuerza al poller central. Los callers on-demand (`useAutoFillBlocks`, `AgentHistoryPage`) no son polling: no se tocan.
7. **RTL/jsdom no existen en este repo.** `@testing-library/react` y `jsdom` NO están en `frontend/package.json` (gap estructural conocido). Todo test de frontend de este plan es de **lógica pura** (funciones puras) o usa el **core de react-query sin DOM** (`QueryClient`/`QueryObserver` corren en node). Cero `render()`. El gate real de UI = `tsc --noEmit` + los tests puros + smoke manual.
8. **Anti-gamear gates.** La prosa de comentarios y docstrings NO debe contener la llamada literal de diálogo nativo del navegador que caza el contador de F6 (ver §9, gotcha con 6 recurrencias históricas). El gate siempre gana: se reescribe la prosa perifrásticamente, jamás se relaja el gate.
9. **Mono-operador sin auth.** Nada de RBAC; el endpoint nuevo es de lectura y no valida `current_user` (no hay nada que validar en el sustrato).
10. **Este plan es GATE, no dueño, del 152.** Se agrega una NOTA NORMATIVA para que el centro de notificaciones consuma el canal; NO se implementa ni se modifica el 152 más allá de esa nota.

---

## 4. Glosario (para un modelo menor que no conoce Stacky)

| Término | Definición |
|---|---|
| **poller central** | Un único `useQuery` de react-query (una `queryKey` + una `queryFn` que llama `GET /api/executions/summary`) del que derivan TODOS los consumidores de runs activos. Como react-query deduplica por `queryKey`, N suscriptores ⇒ 1 sola request de red por tick. |
| **tick** | Cada disparo del intervalo de refetch del poller (hoy cada 5 s). "6 GET por tick" = 6 requests en el mismo disparo. |
| **backoff de visibilidad** | Cuando la pestaña está oculta (`document.visibilityState === "hidden"`), el intervalo de refetch se multiplica por 4 (de 5 s a 20 s): el navegador de fondo pollea 4 veces menos. Al volver a `visible`, vuelve al intervalo normal. |
| **ring-buffer** | Buffer circular de tamaño fijo: cuando se llena, cada elemento nuevo expulsa al más viejo. Acá acota `lines` del stream a un máximo (5000) sin crecer sin fin. |
| **dedup window** | La ventana de líneas sobre la que el Set `seen` recuerda claves para descartar duplicados. Se ata a la ring window: cuando una línea sale del ring, su clave sale de `seen`. Consecuencia documentada y ACEPTABLE: un duplicado tardío de una línea ya expulsada puede re-entrar (su original ya no está en ventana). |
| **access-log** | Las líneas que el logger `werkzeug` (servidor de desarrollo de Flask) escribe por cada request HTTP (`"GET /api/... HTTP/1.1" 200 -`). En Stacky se guardan en el FileHandler diario de `data/logs/`. |
| **uiDebtRatchet** | Test de vitest (plan 138) que congela, POR ARCHIVO, contadores de deuda visual (colores hex en `*.module.css`, `style={{` en `*.tsx`) en un baseline JSON. La deuda solo puede BAJAR; subir rompe el test. |
| **ratchet only-decrease** | Mecanismo de trinquete: un contador congelado que falla si sube. Bajar (limpiar deuda) está permitido y requiere regenerar el baseline. |
| **diálogo nativo del navegador** | Las funciones de bloqueo modal que el navegador provee de fábrica (confirmación/aviso/entrada). Son el antipatrón que reemplazan `ConfirmButton` (plan 136) y los toasts/notificaciones (planes 135/152). F6 congela su conteo para que solo baje. |
| **selector puro** | Función sin efectos ni DOM que transforma la respuesta del summary en la forma que cada consumidor necesita (p. ej. `mergeActiveRuns`). Testeable sin react ni jsdom. |

---

## 5. Fases

> **Pre-flight OBLIGATORIO por fase que toque archivo caliente** (`backend/api/executions.py`, `backend/services/local_file_logging.py`, `backend/scripts/run_harness_tests.sh`, `backend/scripts/run_harness_tests.ps1`, `frontend/src/services/activeRuns.ts`, `frontend/src/hooks/useRunningStatus.ts`, `frontend/src/hooks/useExecutionStream.ts`, `frontend/src/hooks/useTicketSync.ts`, `frontend/src/components/LogsPanel.tsx`, `frontend/src/components/SyncStatusBar.tsx`, `frontend/src/pages/TicketBoard.tsx`, `frontend/src/__tests__/uiDebtRatchet.test.ts`, `frontend/src/__tests__/uiDebtBaseline.json`): `git status -- "<ruta>"`. Si hay WIP ajeno, STOP y avisar al orquestador (sesiones paralelas en el mismo árbol son un escenario real conocido). Staging quirúrgico por path explícito. **El implementador NO commitea** (lo hace el orquestador).
>
> **Comandos:** backend SIEMPRE por archivo desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend` con `.venv\Scripts\python.exe -m pytest tests/<archivo> -q` (equivalente POSIX: `cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/<archivo> -q`). Frontend SIEMPRE por archivo desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend` con `npx vitest run src/<archivo>` (equivalente POSIX: `cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend" && npx vitest run src/<archivo>`). NUNCA suite completa en un solo proceso: cross-file pollution conocida y documentada en este repo, en ambos lados.
>
> **Orden de implementación:** F0 → F1 → F2 → F3 → F4 → F5 → F6 (coincide con la numeración; F1 debe existir antes de F2 porque F2 consume el endpoint; el resto son independientes entre sí). F6 va último porque congela el baseline de diálogos nativos DESPUÉS de que las fases anteriores agreguen sus `.tsx`/`.ts` (que no deben introducir diálogos nativos nuevos).

---

### F0 — Contrato del summary congelado (fase de documentación, solo lectura)

**Objetivo (1 frase):** dejar escrito, dentro del propio plan y en el docstring del endpoint que se creará en F1, el shape EXACTO de la respuesta del summary y la lista EXACTA de campos que los callers consumen HOY, para que F1 no invente nada. **Valor:** el endpoint nace de un contrato verificado contra los consumidores reales, no de una suposición.

**Archivos:** ninguno se modifica (fase de solo lectura; el contrato se materializa como docstring en F1).

**Shape acordado de la respuesta** (`GET /api/executions/summary`):

```jsonc
{
  "scope": "project",            // eco del param recibido: "project" | "all_projects"
  "running":   [ <AgentExecution>, ... ],
  "preparing": [ <AgentExecution>, ... ],
  "queued":    [ <AgentExecution>, ... ]
}
```

- Cada `<AgentExecution>` es el objeto **idéntico** que devuelve `/api/executions` hoy: `to_dict(include_output=False, include_ticket_context=True)` (`backend/api/executions.py:86`). No se agregan ni quitan campos.
- Param `scope`: `project` (default; resuelve el proyecto activo igual que `list_executions` sin `all_projects`) o `all_projects` (equivale a `?all_projects=true`, visibilidad global sin filtrar por proyecto).
- Los tres arrays se ordenan `started_at desc` (igual que `list_executions`, `:85`).

**Campos que los callers consumen HOY (enumerados verificando el árbol — el implementador DEBE confirmar con grep en F1):**

| Caller | Campos leídos |
|---|---|
| `activeRuns.ts` → `mergeActiveRuns` (`:25-27`) | `id` (dedup por Map + orden desc) |
| `useRunningStatus.ts` (`:91-102`) | `ticket_id` (Set de activos), y el objeto completo en `runningByTicket` (Map ticket_id→ejecución) |
| `ActiveRunsPanel.tsx` (`:116-155`) | `id`, `project`, `ticket_id`, `ticket_title`, `agent_type`, `status` |

Todos esos campos vienen de `to_dict(include_ticket_context=True)`; como el summary usa ESE mismo serializer, la cobertura es total y el test de paridad de F1 la garantiza.

**Procedimiento EXACTO:**
1. `grep -rn "e\.\(id\|ticket_id\|status\|agent_type\|ticket_title\|project\)\b" frontend/src/services/activeRuns.ts frontend/src/hooks/useRunningStatus.ts frontend/src/components/ActiveRunsPanel.tsx` — confirmar la tabla de arriba y ampliarla si aparece otro campo consumido.
2. Copiar el shape + la tabla de campos en el docstring del endpoint de F1 y en el resumen de implementación.

**Criterio de aceptación BINARIO:** el shape y la lista completa de campos consumidos están escritos (en el docstring del endpoint F1 y en el resumen). No hay campo consumido por un caller que no esté presente en `to_dict(include_ticket_context=True)`.

**Flag:** N/A. **Runtimes:** N/A (solo lectura). **Trabajo del operador: ninguno.**

---

### F1 — `GET /api/executions/summary` con paridad testeada

**Objetivo (1 frase):** crear el endpoint que agrupa running/preparing/queued en una sola respuesta, reusando el helper de filtrado y el serializer de `/api/executions`, con un test de paridad exacta de campos. **Valor:** una request reemplaza a seis; y como reusa el mismo serializer, nunca puede divergir del endpoint viejo.

**Archivos:**
- MODIFICADO `backend/api/executions.py` (extraer helper de filtros + nueva ruta `/summary`)
- NUEVO `backend/tests/test_executions_summary.py`
- MODIFICADO `backend/scripts/run_harness_tests.sh` y `backend/scripts/run_harness_tests.ps1` (registrar el test, bloque `# — Plan 156 · Latido único —`)

**Paso 1 — Extraer el armado de la query a un helper** (refactor mínimo y seguro; las pruebas existentes de executions deben seguir verdes). En `backend/api/executions.py`, agregar a nivel de módulo (cerca de `list_executions`) un helper que encapsule EXACTAMENTE los filtros que hoy están inline en `list_executions:59-85`:

```python
def _query_active_executions(session, *, project_ctx, status_values, limit):
    """Plan 156 F1 — misma logica de filtro/orden que list_executions, aislada
    para que /api/executions y /api/executions/summary NUNCA diverjan."""
    q = session.query(AgentExecution).options(joinedload(AgentExecution.ticket))
    if project_ctx is not None:
        q = q.join(Ticket, Ticket.id == AgentExecution.ticket_id).filter(
            or_(
                Ticket.stacky_project_name == project_ctx.stacky_project_name,
                and_(
                    Ticket.stacky_project_name.is_(None),
                    Ticket.project == project_ctx.tracker_project,
                ),
            )
        )
    if status_values:
        if len(status_values) == 1:
            q = q.filter(AgentExecution.status == status_values[0])
        else:
            q = q.filter(AgentExecution.status.in_(status_values))
    return q.order_by(AgentExecution.started_at.desc()).limit(limit).all()
```

Y reescribir el cuerpo de `list_executions` para que use este helper cuando corresponda (conservando su soporte de `ticket_id`, `agent_type`, `days`, que el summary NO necesita — el summary solo filtra por estado y scope). **Regla dura:** el refactor NO debe cambiar la salida de `/api/executions`; correr las pruebas existentes de executions tras el cambio (buscar con `ls tests | grep -i execution` y correr las que apliquen por archivo).

**Paso 2 — Nueva ruta** (misma blueprint `bp`, después de `list_executions`):

```python
@bp.get("/summary")
def executions_summary():
    """Plan 156 F1 — latido unico: running/preparing/queued en UNA respuesta.

    Shape: {"scope": "project"|"all_projects",
            "running":[...], "preparing":[...], "queued":[...]}
    Cada objeto es identico a /api/executions (to_dict include_output=False,
    include_ticket_context=True). scope=all_projects => sin filtro de proyecto.
    """
    scope = (request.args.get("scope") or "project").strip().lower()
    all_projects = scope in ("all", "all_projects", "global")
    project_name = (request.args.get("project") or "").strip() or None
    limit = request.args.get("limit", default=50, type=int)

    if all_projects:
        project_ctx = None
    else:
        project_ctx = (
            resolve_project_context(project_name=project_name)
            if project_name else resolve_project_context()
        )

    out = {"scope": "all_projects" if all_projects else "project"}
    with session_scope() as session:
        for status in ("running", "preparing", "queued"):
            rows = _query_active_executions(
                session, project_ctx=project_ctx, status_values=[status], limit=limit,
            )
            out[status] = [
                r.to_dict(include_output=False, include_ticket_context=True) for r in rows
            ]
    return jsonify(out)
```

**Paso 3 — Test.** `backend/tests/test_executions_summary.py` (patrón DB real: `os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")` ANTES de importar la app, `init_db()` en el test; calcar `tests/test_ado_publisher_attachments.py:11,21`). Casos:

| Test | Qué afirma |
|---|---|
| `test_summary_agrupa_por_estado` | Con ejecuciones seeded en running/preparing/queued/completed, el body tiene las 3 keys y NO incluye completed en ninguna. |
| `test_summary_paridad_de_campos_running` | Para el mismo scope, `GET /api/executions?status=running&all_projects=true` y `GET /api/executions/summary?scope=all_projects` devuelven, para running, la MISMA lista de dicts (mismos `id`, y `dict` completo campo por campo — `assert list_running == summary["running"]`). Es el test de paridad EXACTA. |
| `test_summary_scope_project_filtra` | Con dos proyectos seeded, `scope=project` (proyecto activo) NO trae ejecuciones del otro proyecto; `scope=all_projects` las trae todas. |
| `test_summary_vacio_ok` | Sin ejecuciones activas → las 3 keys presentes con arrays vacíos, HTTP 200. |

**Paso 4 — Registrar** `tests/test_executions_summary.py` en `run_harness_tests.sh` Y `.ps1` (bloque `# — Plan 156 · Latido único —`, mismo formato que las entradas vecinas: `  tests/test_executions_summary.py` en sh; `  "tests/test_executions_summary.py",` en ps1).

**Criterio de aceptación BINARIO:** `.venv\Scripts\python.exe -m pytest tests/test_executions_summary.py -q` → exit 0; las pruebas existentes de executions siguen verdes; `grep -c "test_executions_summary.py" scripts/run_harness_tests.sh` → `1` e ídem `.ps1` → `1`.

**Flag:** ninguna. **Runtimes:** endpoint de lectura compartido; los 3 runtimes ven el mismo backend. **Trabajo del operador: ninguno.**

---

### F2 — Poller central único + backoff de visibilidad + migración de los 2 módulos

**Objetivo (1 frase):** un solo `useQuery` que llama al summary, con `refetchInterval` que hace ×4 en pestaña oculta, y del que derivan `activeRuns` y `useRunningStatus` vía selectores puros; `reviewInbox` NO se toca. **Valor:** las 6 requests por tick colapsan en 1; el navegador de fondo pollea 4× menos.

**Archivos:**
- MODIFICADO `frontend/src/api/endpoints.ts` (agregar `Executions.summary(scope)`)
- NUEVO `frontend/src/services/executionsSummary.ts` (query key central + fetch + `refetchInterval` puro + selectores)
- NUEVO `frontend/src/services/__tests__/executionsSummary.test.ts`
- MODIFICADO `frontend/src/services/activeRuns.ts` (derivar del summary)
- MODIFICADO `frontend/src/hooks/useRunningStatus.ts` (derivar del summary)

**Paso 1 — `endpoints.ts`:** en el grupo `Executions`, agregar:

```ts
summary: (scope: "project" | "all_projects" = "project", project?: string | null) => {
  const qs = new URLSearchParams();
  qs.set("scope", scope);
  if (project) qs.set("project", project);
  return api.get<ExecutionsSummary>(`/api/executions/summary?${qs.toString()}`);
},
```

Tipo (en `endpoints.ts` o `types.ts`): `interface ExecutionsSummary { scope: "project" | "all_projects"; running: AgentExecution[]; preparing: AgentExecution[]; queued: AgentExecution[]; }`.

**Paso 2 — `frontend/src/services/executionsSummary.ts`** (núcleo del poller central; funciones PURAS + constantes):

```ts
import { Executions } from "../api/endpoints";
import type { AgentExecution } from "../types";
import { mergeActiveRuns } from "./activeRuns";

export const EXECUTIONS_SUMMARY_REFRESH_MS = 5_000;
export const HIDDEN_TAB_BACKOFF_FACTOR = 4;

/** Query key central: TODOS los consumidores de runs activos la comparten
 *  => react-query hace 1 sola request por tick aunque haya N suscriptores. */
export const executionsSummaryQueryKey = (scope: "project" | "all_projects") =>
  ["executions", "summary", scope] as const;

/** refetchInterval PURO: ×4 cuando la pestaña esta oculta. */
export function summaryRefetchInterval(
  visibility: DocumentVisibilityState,
  baseMs: number = EXECUTIONS_SUMMARY_REFRESH_MS,
): number {
  return visibility === "hidden" ? baseMs * HIDDEN_TAB_BACKOFF_FACTOR : baseMs;
}

export function fetchExecutionsSummary(scope: "project" | "all_projects") {
  return Executions.summary(scope);
}

/** Selector PURO: runs activos globales (reusa mergeActiveRuns existente). */
export function selectActiveRuns(s: ExecutionsSummary): AgentExecution[] {
  return mergeActiveRuns(s.running, s.preparing, s.queued);
}

/** Selector PURO: Set de ticket_ids activos + Map ticket_id -> ejecucion. */
export function selectRunningByTicket(
  s: ExecutionsSummary,
): { ids: Set<number>; byTicket: Map<number, AgentExecution> } {
  const ids = new Set<number>();
  const byTicket = new Map<number, AgentExecution>();
  for (const e of [...s.preparing, ...s.running, ...s.queued]) {
    ids.add(e.ticket_id);
    if (!byTicket.has(e.ticket_id)) byTicket.set(e.ticket_id, e);
  }
  return { ids, byTicket };
}
```

(El orden `preparing, running, queued` de `selectRunningByTicket` replica EXACTAMENTE el de `useRunningStatus.ts:91/99` para no cambiar cuál ejecución gana en el Map.)

**Paso 3 — Migrar `activeRuns.ts`:** `fetchActiveRuns()` deja de hacer 3 llamadas y pasa a `const s = await fetchExecutionsSummary("all_projects"); return selectActiveRuns(s);`. Conservar `mergeActiveRuns` (lo reusa el selector). Los consumidores que usan `ACTIVE_RUNS_QUERY_KEY` deben migrar a `executionsSummaryQueryKey("all_projects")` con `refetchInterval: () => summaryRefetchInterval(document.visibilityState)` para compartir la MISMA cache que useRunningStatus (mismo scope ⇒ misma key ⇒ 1 request). Documentar en el `useQuery` que la key es compartida.

**Paso 4 — Migrar `useRunningStatus.ts`:** reemplazar los 3 `useQuery` (`:61-80`) por UNO:

```ts
const { data: summary } = useQuery<ExecutionsSummary>({
  queryKey: executionsSummaryQueryKey("project"),
  queryFn: () => fetchExecutionsSummary("project"),
  refetchInterval: () => summaryRefetchInterval(document.visibilityState),
  staleTime: 0,
});
const { ids, byTicket } = useMemo(
  () => (summary ? selectRunningByTicket(summary) : { ids: new Set<number>(), byTicket: new Map() }),
  [summary],
);
```

Mantener la Fuente 1 (stacky_status del listado de tickets, `:48-58`) tal cual — esa NO es polling de executions. Unir `ids` con los ticket_ids de `stacky_status === "running"` como hoy.

**NOTA NORMATIVA (para el implementador del plan del centro de notificaciones, 152):** el notificador global de actividad DEBE suscribirse a `executionsSummaryQueryKey("all_projects")` con `fetchExecutionsSummary` en vez de crear su propio poller de `/api/executions`. Implementar el 152 DESPUÉS de este plan.

**Paso 5 — Test** `frontend/src/services/__tests__/executionsSummary.test.ts` (puro + core de react-query sin DOM):

| Test | Qué afirma |
|---|---|
| `test_backoff_visibilidad` | `summaryRefetchInterval("visible", 5000) === 5000`; `summaryRefetchInterval("hidden", 5000) === 20000`. |
| `test_selectActiveRuns_dedup_orden` | Dos listas con un id repetido → una sola aparición, orden id desc (reusa mergeActiveRuns). |
| `test_selectRunningByTicket` | Set con los ticket_ids correctos; Map se queda con la PRIMERA ejecución por ticket en orden preparing→running→queued. |
| `test_una_sola_request_por_key` | Con `@tanstack/react-query` core (`QueryClient` + dos `QueryObserver` con la MISMA `executionsSummaryQueryKey("project")` y una `queryFn` mockeada que cuenta invocaciones), tras un fetch la `queryFn` fue llamada **exactamente 1 vez** (prueba de que N suscriptores ⇒ 1 request). Sin DOM: react-query core corre en node. |

**Criterio de aceptación BINARIO:** `npx vitest run src/services/__tests__/executionsSummary.test.ts` → exit 0; `npx tsc --noEmit` → exit 0; `grep -c "Executions.list" src/hooks/useRunningStatus.ts` → `0` (ya no pollea el endpoint viejo) y `grep -c "Executions.list" src/services/activeRuns.ts` → `0`.

**Flag:** ninguna. **Runtimes:** UI compartida; paridad automática. **Trabajo del operador: ninguno.**

---

### F3 — Ring-buffer del stream + evict simétrico del dedup + contador visible + cap de render

**Objetivo (1 frase):** acotar `lines` a 5000 con un módulo puro, evictar del Set `seen` la clave de cada línea que sale de ventana (dedup window = ring window), exponer cuántas se descartaron, y cap de render en LogsPanel — todo sin libs nuevas. **Valor:** una ejecución larga deja de acumular memoria sin cota en los 3 consumidores del stream.

**Archivos:**
- NUEVO `frontend/src/hooks/logRingBuffer.ts` (módulo puro)
- NUEVO `frontend/src/hooks/__tests__/logRingBuffer.test.ts`
- MODIFICADO `frontend/src/hooks/useExecutionStream.ts` (usar el ring + exponer `dropped`)
- MODIFICADO `frontend/src/components/LogsPanel.tsx` (contador "N líneas anteriores descartadas" + cap de render)

**Paso 1 — `frontend/src/hooks/logRingBuffer.ts`:**

```ts
import type { LogLine } from "../types";

export const LOG_RING_CAP = 5000;

/** Clave de dedup (movida desde useExecutionStream para poder evictarla). */
export function dedupKey(l: LogLine): string {
  return `${l.timestamp ?? ""}|${l.level ?? ""}|${l.message ?? ""}`;
}

export interface RingState {
  lines: LogLine[];
  seen: Set<string>;
  dropped: number;
}

export function emptyRing(): RingState {
  return { lines: [], seen: new Set(), dropped: 0 };
}

/** Append acotado + dedup dentro de ventana + evict simetrico del Set.
 *  Devuelve el MISMO objeto si la linea era duplicado en ventana (no-op). */
export function appendBounded(
  state: RingState,
  line: LogLine,
  cap: number = LOG_RING_CAP,
): RingState {
  const key = dedupKey(line);
  if (state.seen.has(key)) return state; // duplicado dentro de la ventana actual

  const seen = new Set(state.seen);
  seen.add(key);
  let lines = [...state.lines, line];
  let dropped = state.dropped;

  if (lines.length > cap) {
    const removeCount = lines.length - cap;
    for (let i = 0; i < removeCount; i++) {
      // evict simetrico: la clave de la linea que sale del ring sale del Set.
      // Consecuencia ACEPTADA: un duplicado tardio de esa linea puede re-entrar
      // (su original ya no esta en ventana). dedup window == ring window.
      seen.delete(dedupKey(lines[i]));
    }
    lines = lines.slice(removeCount);
    dropped += removeCount;
  }
  return { lines, seen, dropped };
}
```

**Paso 2 — `useExecutionStream.ts`:** reemplazar el `seenKeys` ref (`:39`), la `dedupKey` local (`:56-57`) y el `setState((s) => ({ ...s, lines: [...s.lines, data!] }))` (`:75`) por el ring. El estado del hook pasa a llevar `dropped`. Diseño:
- `const ring = useRef<RingState>(emptyRing());` (reset en el cleanup y al cambiar `executionId`, donde hoy se resetea `seenKeys` — `:43/:48`).
- `StreamState` gana `dropped?: number`.
- En `onLog` (tras validar `data`): `const next = appendBounded(ring.current, data); if (next !== ring.current) { ring.current = next; setState((s) => ({ ...s, lines: next.lines, dropped: next.dropped })); }` — el `!== ` evita re-render en duplicados.
- Importar `emptyRing, appendBounded, RingState` de `./logRingBuffer`; borrar la `dedupKey` local.

**Paso 3 — `LogsPanel.tsx`:** cap de render + contador. Agregar constante `const RENDER_CAP = 2000;` y renderizar solo la cola:
- Reemplazar `{stream.lines.map(...)}` (`:27`) por `{stream.lines.slice(-RENDER_CAP).map(...)}`.
- Antes de la lista, si hay descartes o recorte de render, un aviso (sin `style={{`; clase de `LogsPanel.module.css`): `{(stream.dropped ?? 0) > 0 && (<div className={styles.dropped}>{stream.dropped} líneas anteriores descartadas</div>)}`.
- (CodexConsoleDock y OutputPanel heredan la cota del hook automáticamente; mostrar el contador ahí es opcional y NO requerido por este plan.)

**Paso 4 — Test** `frontend/src/hooks/__tests__/logRingBuffer.test.ts` (100% puro):

| Test | Qué afirma |
|---|---|
| `test_cota_20000_lineas` | Insertar 20.000 líneas ÚNICAS → `lines.length === 5000`, `seen.size === 5000`, `dropped === 15000`. |
| `test_dedup_en_ventana` | Insertar la MISMA línea dos veces seguidas → `appendBounded` devuelve el mismo objeto la 2ª vez; `lines.length === 1`. |
| `test_duplicado_tardio_reentra` | Insertar A, llenar el ring hasta expulsar A, reinsertar A → A vuelve a estar (dedup window == ring window). |
| `test_cap_configurable` | Con `cap=3` e insertar 5 → `lines.length === 3`, `dropped === 2`, y `seen.size === 3`. |

**Criterio de aceptación BINARIO:** `npx vitest run src/hooks/__tests__/logRingBuffer.test.ts` → exit 0; `npx tsc --noEmit` → exit 0.

**Flag:** ninguna. **Runtimes:** el stream es el mismo para los 3 runtimes; paridad automática. **Trabajo del operador: ninguno.**

---

### F4 — Aislar el reloj: SyncStatusBar con su propio tic-tac, useTicketSync sin ticker global

**Objetivo (1 frase):** sacar el `setInterval(...,1000)` de `useTicketSync` y darle su propio reloj a la hoja `SyncStatusBar`, que calcula "hace Xs"/stale localmente a partir de `lastSyncedAt`. **Valor:** TicketBoard (1133 líneas) deja de reconciliarse 60 veces por minuto por un contador de segundos.

**Archivos:**
- NUEVO `frontend/src/components/syncStatus.ts` (helpers puros)
- NUEVO `frontend/src/components/__tests__/syncStatus.test.ts`
- MODIFICADO `frontend/src/hooks/useTicketSync.ts` (quitar `setTick` + el `useEffect` del ticker)
- MODIFICADO `frontend/src/components/SyncStatusBar.tsx` (reloj propio + `React.memo`)
- MODIFICADO `frontend/src/pages/TicketBoard.tsx` (pasar `lastSyncedAt`/`intervalMs` a SyncStatusBar; dejar de pasar los valores que ya no ticquean)

**Paso 1 — `frontend/src/components/syncStatus.ts` (puro):**

```ts
export function secondsSince(lastSyncedAt: string | null, nowMs: number = Date.now()): number | null {
  if (!lastSyncedAt) return null;
  return Math.floor((nowMs - new Date(lastSyncedAt).getTime()) / 1000);
}

export function isStaleAt(
  lastSyncedAt: string | null,
  intervalMs: number,
  nowMs: number = Date.now(),
): boolean {
  const secs = secondsSince(lastSyncedAt, nowMs);
  return secs !== null && secs * 1000 > intervalMs * 2;
}
```

(Réplica EXACTA de la lógica hoy inline en `useTicketSync.ts:70-74`.)

**Paso 2 — `useTicketSync.ts`:** BORRAR el estado `const [, setTick] = useState(0)` (`:55`) y el `useEffect` del ticker (`:65-68`). Como consecuencia, `secondsSinceSync` (`:70-72`) e `isStale` (`:74`) dejan de actualizarse solos cada segundo: quitarlos del objeto de retorno y de `UseTicketSyncResult` (`:30`, `:34`, `:236`, `:240`). El hook sigue exponiendo `lastSyncedAt` (que el reloj de la hoja consumirá). El resto del hook (mutación de sync, backoff, visibility) NO se toca. Verificar que ningún otro consumidor use `secondsSinceSync`/`isStale` del hook (`grep -rn "secondsSinceSync\|isStale" frontend/src` — el único consumidor de `useTicketSync` es TicketBoard; el `isStale` de DocsPage/DocViewer es de otro dominio).

**Paso 3 — `SyncStatusBar.tsx`:** que reciba `lastSyncedAt: string | null` e `intervalMs: number` (en vez de `secondsSinceSync`/`isStale` ya calculados). Adentro:
- Un `useState` de `now` + un `useEffect` con `setInterval(() => setNow(Date.now()), 1000)` (el reloj vive ACÁ, en la hoja).
- `const secs = secondsSince(lastSyncedAt, now); const stale = isStaleAt(lastSyncedAt, intervalMs, now);` (helpers puros del Paso 1).
- Envolver el export con `export default React.memo(SyncStatusBar)` para que un cambio de `now` en el padre no lo re-renderice de más y, sobre todo, para que su propio tic-tac NO suba al padre.

**Paso 4 — `TicketBoard.tsx`:** en el uso de `useTicketSync` (`:751-757`) dejar de desestructurar `secondsSinceSync`/`isStale`; en el `<SyncStatusBar .../>` (`:995-1000`) pasar `lastSyncedAt={lastSyncedAt}` e `intervalMs={45_000}` en vez de `secondsSinceSync`/`isStale`.

**Paso 5 — Test** `frontend/src/components/__tests__/syncStatus.test.ts` (puro):

| Test | Qué afirma |
|---|---|
| `test_secondsSince_null` | `secondsSince(null)` → `null`. |
| `test_secondsSince_calcula` | Con `lastSyncedAt` = now-90s y `nowMs` fijo → `90`. |
| `test_isStale_umbral` | `isStaleAt(now-91s, 45000, now)` → `true`; `isStaleAt(now-30s, 45000, now)` → `false` (umbral = intervalMs*2 = 90s). |

**Criterio de aceptación BINARIO:** `npx vitest run src/components/__tests__/syncStatus.test.ts` → exit 0; `grep -c "setInterval" src/hooks/useTicketSync.ts` → `0`; `grep -c "setInterval" src/components/SyncStatusBar.tsx` → `1`; `npx tsc --noEmit` → exit 0. **Verificación manual (documentada, sin operador):** abrir el board con el highlight de renders de React DevTools; el board no debe parpadear cada segundo (solo SyncStatusBar).

**Flag:** ninguna. **Runtimes:** UI compartida; paridad automática. **Trabajo del operador: ninguno.**

---

### F5 — Ampliar el filtro de access-log con los pollers 200 conocidos

**Objetivo (1 frase):** agregar al default de rutas suprimidas los pollers 200 (`/api/diag/local`, `/api/cost-cap`, `/api/streak`) y el nuevo `/api/executions/summary`, manteniendo intacto el mecanismo env `STACKY_ACCESS_LOG_SUPPRESS_PATHS`. **Valor:** el archivo de log del deploy deja de estar dominado por GETs 200 de no-op y vuelve a ser legible.

**Archivos:**
- MODIFICADO `backend/services/local_file_logging.py` (solo la tupla `_DEFAULT_SUPPRESSED_PATHS`, `:68`)
- NUEVO `backend/tests/test_access_log_suppress_pollers.py`
- MODIFICADO `backend/scripts/run_harness_tests.sh` y `.ps1` (registrar el test, bloque `# — Plan 156 · Latido único —`)

**Paso 1 — Ampliar el default** (ancla de texto: `_DEFAULT_SUPPRESSED_PATHS = ("/api/v1/pipeline/status",)`, `:68`). Reemplazar por:

```python
_DEFAULT_SUPPRESSED_PATHS = (
    "/api/v1/pipeline/status",
    "/api/diag/local",
    "/api/cost-cap",
    "/api/streak",
    "/api/executions/summary",
)
```

**DECISIÓN DE DISEÑO (corrección de drift respecto del texto del debate):** NO se agrega un `/api/executions` "con query de polling" a la tupla. Motivo verificado: `_AccessLogNoiseFilter.filter()` hace `p in message` (substring del mensaje completo de werkzeug, `:98`); un substring `/api/executions` desnudo suprimiría TAMBIÉN `/api/executions/history`, `/api/executions/<id>` y llamadas legítimas — sobre-supresión. El polling de `/api/executions` por estado que existe HOY lo ELIMINA F2 (consolidación en el summary), no la supresión de log. Por eso solo se suprime el endpoint nuevo `/api/executions/summary` (el único poller de executions que quedará) y los tres no-op de siempre.

**Paso 2 — Test** `backend/tests/test_access_log_suppress_pollers.py` (unitario del filtro, sin red; construye `logging.LogRecord` de nombre `"werkzeug"` con mensajes de acceso simulados):

| Test | Qué afirma |
|---|---|
| `test_suprime_pollers_nuevos` | `_AccessLogNoiseFilter(_suppressed_paths())` con records `"GET /api/diag/local HTTP/1.1" 200 -`, idem cost-cap, streak, executions/summary → `filter()` devuelve `False` (descarta) para los 4. |
| `test_no_suprime_history_ni_id` | Records `"GET /api/executions/history ..."` y `"GET /api/executions/42 ..."` → `filter()` devuelve `True` (NO se suprimen). |
| `test_no_suprime_otros_loggers` | Un record de nombre `"stacky"` (no werkzeug) con `/api/diag/local` en el mensaje → `filter()` devuelve `True`. |
| `test_env_extra_sigue_funcionando` | Con `monkeypatch.setenv("STACKY_ACCESS_LOG_SUPPRESS_PATHS", "/api/foo")`, `_suppressed_paths()` incluye `/api/foo` ADEMÁS del default nuevo. |

(Para `test_env_extra`: `_suppressed_paths()` lee la env en cada llamada, así que el monkeypatch basta; no hay estado global cacheado.)

**Paso 3 — Registrar** el test en `run_harness_tests.sh` Y `.ps1` (bloque `# — Plan 156 · Latido único —`).

**Criterio de aceptación BINARIO:** `.venv\Scripts\python.exe -m pytest tests/test_access_log_suppress_pollers.py -q` → exit 0; `grep -c "test_access_log_suppress_pollers.py" scripts/run_harness_tests.sh` → `1` e ídem `.ps1` → `1`. **Verificación manual (documentada):** arrancar el backend dev en frío, dejar la UI abierta 1 minuto, abrir el `data/logs/stacky-*.log` del día → sin líneas de acceso de los 4 paths suprimidos.

**Flag:** ninguna (el mecanismo env `STACKY_ACCESS_LOG_SUPPRESS_PATHS` sigue siendo la vía del operador, sin cambios). **Runtimes:** logging compartido; paridad automática. **Trabajo del operador: ninguno.**

---

### F6 — Ratchet only-decrease de diálogos nativos del navegador (adelantado del debate)

**Objetivo (1 frase):** extender el `uiDebtRatchet` existente con un contador POR ARCHIVO de llamadas a diálogos nativos del navegador (confirmación/aviso/entrada) que solo puede BAJAR, para proteger a los demás planes mientras el plan del diálogo canónico espera al final de la cola. **Valor:** hace estructuralmente imposible que crezca el antipatrón que `ConfirmButton` (plan 136) y los toasts (135/152) vienen reemplazando.

**Archivos:**
- MODIFICADO `frontend/src/__tests__/uiDebtRatchet.test.ts` (tercera dimensión)
- MODIFICADO `frontend/src/__tests__/uiDebtBaseline.json` (regenerado una vez para sembrar el conteo en frío)

**Paso 1 — Recontar en frío la baseline.** El regex de diálogos nativos (definido perifrásticamente para NO auto-cazarse; ver §9) es:

```
/(?<![.\w])(?:window\.)?(?:confirm|alert|prompt)\s*\(/g
```

- Requiere `(` después del identificador ⇒ una prosa como `"sin window.confirm)"` (comentario real en `ConfirmButton.tsx`) NO matchea, y `obj.confirm(` (método ajeno) tampoco (lookbehind `(?<![.\w])`, salvo el prefijo explícito `window.`).
- Escanear `.ts` y `.tsx` bajo `src/` EXCLUYENDO cualquier ruta que contenga `/__tests__/` (para que el propio archivo del ratchet no se cuente).
- **DRIFT CORREGIDO respecto del debate:** el debate contó "20 ocurrencias en 12 archivos"; un scan en frío 2026-07-16 con este regex encuentra **materialmente más** (~35 llamadas reales en ~17 archivos, p. ej. `AgentHistoryPage.tsx` ×8, `devops/PipelineBuilderSection.tsx` ×5, `TopBar.tsx` ×2, `useAgentRun.ts` ×1 — nótese que este último es `.ts`, por eso el scan DEBE incluir `.ts`, no solo `.tsx`). **NO confiar en el 20**: el conteo real es el que dé el scan al momento de implementar (otros planes tocan frontend en paralelo). Recontar y congelar ESE número.

**Paso 2 — Extender el test** `uiDebtRatchet.test.ts`:
- Agregar a `interface Baseline` el campo `nativeDialogByFile: Record<string, number>;`.
- En `computeCurrent()`, escanear `.ts`/`.tsx` (excluyendo `/__tests__/`) contando matches del regex de diálogos nativos → `nativeDialogByFile`.
- En `assertNoIncrease()`, el helper `check` debe ser robusto a que el baseline viejo AÚN no tenga la clave: `const allowedBase = (baseline[kind] ?? {})[file] ?? 0;`. Agregar `check("nativeDialogByFile")` (sin `forcedZero`: es deuda heredada distribuida).
- El mensaje de error de la nueva dimensión debe nombrar la solución perifrásticamente (p. ej. "usar ConfirmButton / el sistema de notificaciones en vez de los diálogos modales nativos del navegador"), SIN escribir la llamada literal.

**Paso 3 — Regenerar el baseline UNA vez** (el regen valida que no haya aumentos antes de escribir, `:104-111`):

```
PowerShell:  $env:UI_DEBT_REGEN='1'; npx vitest run src/__tests__/uiDebtRatchet.test.ts; Remove-Item Env:\UI_DEBT_REGEN
bash:        UI_DEBT_REGEN=1 npx vitest run src/__tests__/uiDebtRatchet.test.ts
```

Esto agrega `nativeDialogByFile` a `uiDebtBaseline.json` con el conteo en frío por archivo. Después correr el test normal (sin la env) → debe pasar.

**Paso 4 — Demostración de que el ratchet muerde** (manual, documentada, revertida): agregar temporalmente una llamada de diálogo nativo en cualquier `.tsx` de `src/` → `npx vitest run src/__tests__/uiDebtRatchet.test.ts` FALLA con el mensaje de la dimensión nueva; revertir → verde.

**Criterio de aceptación BINARIO:** `npx vitest run src/__tests__/uiDebtRatchet.test.ts` → exit 0 con `nativeDialogByFile` presente en el baseline; la demostración de que subir el conteo rompe el test está en el resumen; `git diff` de `src/` limpio salvo el test y el baseline JSON.

**Flag:** ninguna. **Runtimes:** infraestructura de tests de frontend; agnóstica de runtime. **Trabajo del operador: ninguno.**

---

## 6. Orden de implementación (numerado)

1. **F0** — escribir el contrato (solo lectura; confirmar campos con grep).
2. **F1** — endpoint `/api/executions/summary` + test de paridad + registro en el arnés. Correr las pruebas existentes de executions tras el refactor.
3. **F2** — poller central + selectores + migrar `activeRuns` y `useRunningStatus` (NO tocar `reviewInbox`). Dejar la NOTA NORMATIVA para el 152.
4. **F3** — módulo puro `logRingBuffer` + integrarlo en `useExecutionStream` + contador/cap en `LogsPanel`.
5. **F4** — helpers puros `syncStatus` + sacar el ticker de `useTicketSync` + reloj propio en `SyncStatusBar` + ajustar `TicketBoard`.
6. **F5** — ampliar `_DEFAULT_SUPPRESSED_PATHS` + test del filtro + registro en el arnés.
7. **F6** — extender el `uiDebtRatchet` + regenerar baseline (último, para congelar después de que F2/F3/F4 agreguen sus archivos sin diálogos nativos nuevos).

Correr `npx tsc --noEmit` al terminar cada fase de frontend (F2/F3/F4/F6). Cada test SIEMPRE por archivo.

---

## 7. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | El refactor de `list_executions` (F1) cambia sutilmente la salida del endpoint viejo. | El helper `_query_active_executions` replica EXACTAMENTE los filtros inline; correr las pruebas existentes de executions por archivo tras el cambio; el test de paridad de F1 compara dict a dict. |
| R2 | La migración de `activeRuns`/`useRunningStatus` a una key compartida cambia cuál ejecución "gana" en el Map o el orden de la lista. | `selectRunningByTicket` replica el orden `preparing→running→queued` de hoy (`useRunningStatus.ts:91/99`); `selectActiveRuns` reusa `mergeActiveRuns` sin cambios; tests puros lo fijan. |
| R3 | El evict del Set en el ring reintroduce duplicados visibles. | Es comportamiento **documentado y aceptado** (dedup window == ring window): un duplicado tardío de una línea fuera de ventana es raro y benigno (el original ya no está a la vista). Test `test_duplicado_tardio_reentra` lo fija como contrato. |
| R4 | Sacar el ticker de `useTicketSync` deja el "hace Xs" congelado. | El reloj se MUEVE a `SyncStatusBar` (hoja) con su propio `setInterval`; el texto sigue vivo, pero solo re-renderiza la hoja. Gate: `setInterval` = 0 en el hook, 1 en la hoja. |
| R5 | La supresión de log oculta un error real en un poller (un 500 en `/api/streak`). | El filtro solo mira el path como substring; werkzeug loguea el código de estado en la MISMA línea, así que un 500 igual queda suprimido. **Aceptado**: estos endpoints ya tienen su propio manejo de error y UI (HealthBanner/CostCapIndicator/StreakBadge); el archivo no es el canal de diagnóstico de sus fallos. Si se quisiera, `STACKY_ACCESS_LOG_SUPPRESS=false` restaura el access-log completo (mecanismo existente). |
| R6 | El baseline de F6 se hardcodea al 20 del debate y rompe por drift. | El plan es explícito: **recontar en frío**, nunca confiar en 20. El regen del baseline captura el número real del día. |
| R7 | Un `.tsx`/`.ts` nuevo de este plan introduce deuda (inline-style o diálogo nativo) que rompe el ratchet. | Los archivos nuevos (`executionsSummary.ts`, `logRingBuffer.ts`, `syncStatus.ts`) son lógica pura sin JSX ni diálogos; `SyncStatusBar`/`LogsPanel` usan clases de `*.module.css` (para estilos dinámicos, ref+effect imperativo, NUNCA `style={{}}` — gotcha uiDebtRatchet conocido). |

---

## 8. Fuera de scope (explícito)

- **SSE / WebSocket para el summary.** Recortado en el debate: el backoff de visibilidad + el latido único bastan. NO se agrega push server→cliente.
- **Virtualización con librerías externas** (`react-window`, `@tanstack/react-virtual`, etc.). El cap de render se hace con `slice`/CSS, sin sumar dependencias a `package.json`.
- **Migrar `reviewInbox`** al poller central. Tiene cache/cadencia propias por diseño (dominio distinto). No se toca.
- **Eliminar `/api/executions`.** El endpoint viejo permanece (backward-compatible). Este plan solo AGREGA el summary.
- **Implementar o modificar el plan del centro de notificaciones (152)** más allá de la NOTA NORMATIVA de F2 (que le indica consumir este canal).
- **Triage de la deuda de diálogos nativos.** F6 solo CONGELA el contador (only-decrease); reemplazar cada llamada por `ConfirmButton`/toast es trabajo de otro plan (el del diálogo canónico, al final de la cola).
- **Tests de render (`render()`/RTL).** Imposibles en este repo (sin `@testing-library/react` ni `jsdom`); todo test es puro o de core react-query sin DOM.

---

## 9. Advertencias para el implementador (leer antes de tocar nada)

- **RTL/jsdom NO están en `frontend/package.json`** (gap estructural conocido). Prohibido `render()`/`renderHook` de `@testing-library/react`. Tests = funciones puras + `tsc --noEmit` + (F2) core de react-query en node. El gate de UI real es tsc + los tests puros + smoke manual.
- **vitest SIEMPRE por archivo** (`npx vitest run src/<archivo>`): la corrida completa contamina cross-file, igual que pytest en el backend.
- **pytest SIEMPRE por archivo** con el venv real `backend\.venv\Scripts\python.exe` (py3.13); `backend/venv` NO existe.
- **`reviewInbox.ts` NO se toca**: mantiene su cache/cadencia react-query propia.
- **Callers on-demand** (`useAutoFillBlocks.ts:31`, `AgentHistoryPage.tsx:387`) NO son polling: no migrarlos.
- **Archivos `.tsx` nuevos y el uiDebtRatchet**: el ratchet le da alcance CERO a `style={{` en `.tsx` nuevos; para estilos dinámicos usar `ref`+`useEffect` imperativo, JAMÁS `style={{}}`. Usar clases de `*.module.css` con tokens de `theme.css`.
- **Gotcha comentario-choca-con-gate (6 recurrencias históricas):** la prosa de este plan, los comentarios del código y los mensajes de test de F6 NO deben contener la llamada literal de diálogo nativo que caza el regex (`confirmación/aviso/entrada` seguidos de paréntesis). Nombrarla perifrásticamente ("diálogos modales nativos del navegador"). El gate siempre gana.
- **En `backend/api/` la instancia de flags es `config.config`, NO el módulo `config`** (gotcha planes 131/148). Este plan no lee flags nuevas, pero si se toca alguna lectura de config, respetarlo.
- **Ruta del blueprint:** los blueprints se registran en `backend/api/__init__.py`, NO en `app.py` (gotcha conocido). Este plan solo AGREGA una ruta a un blueprint YA registrado (`executions`), así que no toca el registro.
- **Sesión concurrente en el mismo árbol:** `git status -- "<ruta>"` antes de cada fase caliente; staging quirúrgico por path; el implementador NO commitea.

---

## 10. Definition of Done (global)

- [ ] KPI-1..KPI-8 en verde con los comandos exactos de §1, cada test corrido por archivo con el intérprete/venv correcto y su salida pegada en el resumen.
- [ ] `GET /api/executions/summary` existe, con paridad exacta de campos vs `/api/executions` demostrada por test; el endpoint viejo intacto.
- [ ] `activeRuns` y `useRunningStatus` derivan de UNA sola query central (`grep Executions.list` en ambos → 0); `reviewInbox` sin cambios.
- [ ] `useExecutionStream` acota `lines` y `seen` a ≤ 5000 vía módulo puro testeado; `LogsPanel` muestra el contador de descartadas y capea el render.
- [ ] `useTicketSync` sin `setInterval` (grep = 0); el reloj vive en `SyncStatusBar` (grep = 1) memoizado.
- [ ] `_DEFAULT_SUPPRESSED_PATHS` incluye los 3 pollers no-op + `/api/executions/summary`; el mecanismo env intacto; test del filtro verde.
- [ ] `uiDebtRatchet` tiene la dimensión `nativeDialogByFile` con baseline recontado en frío; subir el conteo rompe el test (demostrado y revertido).
- [ ] `npx tsc --noEmit` verde; 2 tests backend nuevos registrados en `run_harness_tests.sh` Y `.ps1`.
- [ ] NOTA NORMATIVA para el plan 152 escrita en el código/plan (consumir el canal de summary).
- [ ] Pre-flight `git status` por archivo caliente hecho; sin WIP ajeno arrastrado; el implementador NO commiteó.
- [ ] "Trabajo del operador: ninguno" se cumple: sin config nueva, sin flags, backward-compatible.
