# Plan 152 — Centro de notificaciones / actividad unificado

> **Estado:** CRITICADO v2 · **Autor:** StackyArchitectaUltraEficientCode · **Juez:** StackyArchitectaUltraEficientCode (adversarial) · **Versión:** v1 -> v2 (criticado 2026-07-16)
> **Serie UX/UI:** las series 131-141, 142-143 y 144-149 están **IMPLEMENTADAS** (verificado en árbol 2026-07-16). Este plan aterriza sobre infra REAL, no sobre planes en papel.
> **Depende de (reuso, no reimplementación — TODO existe hoy):** 134 (`activeRuns.ts`/`useActiveRunsGlobal`), 138 (primitivas `ui/IconButton.tsx`, `ui/Skeleton.tsx`), 140 (`EmptyState.tsx`), 141/143 (tokens tema+motion en `theme.css`), 135 (`PageErrorBoundary.tsx`, `Toast.tsx`), 142 (`CostCapIndicator.tsx`).
> **Runtimes:** 100% frontend (presentación + reuso de la infra existente) ⇒ idéntico en Codex, Claude Code y GitHub Copilot Pro. Sin dependencia de SSE; el refresco es el polling react-query ya existente.
> **Flag:** `STACKY_NOTIFICATION_CENTER_ENABLED` — **default ON** (UI aditiva, opt-out por `HarnessFlagsPanel`). Ninguna de las 4 excepciones duras aplica (§4.4).
> **Backend nuevo:** NINGÚN endpoint/ruta/streaming/persistencia nuevos. Único toque backend: registro canónico del flag (config pura, F3), leído vía el endpoint EXISTENTE `/api/harness-flags`.

## CHANGELOG v1 -> v2 (crítica adversarial 2026-07-16)

- **C1 (IMPORTANTE, premisas stale):** v1 trataba 135/140/142/143 como "en papel" y diseñaba degradaciones (`<button>` propio en vez de `IconButton`, placeholder en vez de `Skeleton`, tokens "que pueden faltar"). HOY todo existe (verificado: `frontend/src/components/ui/IconButton.tsx`, `ui/Skeleton.tsx`, `EmptyState.tsx`, `PageErrorBoundary.tsx`, `Toast.tsx`, `CostCapIndicator.tsx`). v2 REUSA las primitivas reales (F4) y elimina los branches de degradación de 138/140/143. La degradación honesta §4.5 queda SOLO como contrato de extensibilidad futura de `kind`s.
- **C2 (IMPORTANTE, flag OFF no gateaba la captura):** v1 decía "la captura corre siempre". Con flag OFF eso disparaba `Executions.byId` + escrituras a localStorage de una feature apagada (degrada red/CPU). v2: `useRunActivityCapture(enabled: boolean)` con early-return.
- **C3 (IMPORTANTE, anclas de línea stale):** el árbol cambió desde v1 (sesión concurrente). Re-anclado: `useGlobalExecutionNotifier()` en `App.tsx:99` (no :70), `<TopBar ... shellV2={...}/>` en `App.tsx:245` (no :158), `styles.actions` en `TopBar.tsx:202`, `<CostCapIndicator/>` en `:211`, `FLAG_REGISTRY` en `harness_flags.py:309` (no :295), `_CATEGORY_KEYS` en `:117` (no :114), `HarnessFlags.list` en `endpoints.ts:908` (no :873). Regla v2: anclar ediciones por TEXTO normativo; los números de línea son referencia del día, no ancla.
- **C4 (IMPORTANTE, vaguedad de categoría):** v1 decía "si no fuera `capacidades_optin`, usar la más cercana" (frase vaga prohibida). Verificado: `capacidades_optin` EXISTE (`harness_flags.py:103`). v2 la fija literal, sin alternativa.
- **C5 (IMPORTANTE, ratchet uiDebtRatchet omitido):** F4 crea .tsx nuevos y v1 no citaba el gate real del plan 138. v2 agrega **KPI-7**: `npx vitest run src/__tests__/uiDebtRatchet.test.ts` → exit 0, y la regla dura: 0 `style={}` inline en los .tsx nuevos (todo en `.module.css` con tokens; para anchos dinámicos usar ref+effect imperativo, gotcha conocido).
- **C6 (MENOR, venv ambiguo):** "venv del repo" no es literal para modelos menores. Verificado: el venv real es `N:\GIT\RS\STACKY\Stacky\.venv`. v2 fija el comando exacto (KPI-5).
- **C7 (MENOR, gotcha grep-gate propio):** KPI-6 grepea `setInterval|new EventSource|fetch\(` sobre los archivos nuevos. v2 agrega la regla: los COMENTARIOS de esos archivos tienen PROHIBIDO contener esos literales (gotcha recurrente comentario-choca-con-su-gate, 6 ocurrencias históricas).
- **C8 (MENOR, divergencia semántica declarada):** `severityFromRunStatus` separa `error→"error"` de `needs_review→"attention"`, mientras `combineOutcome` (`notifierCore.ts:34`) colapsa ambos en `attention`. v2 lo declara como refinamiento consciente (el feed distingue fallo de revisión), no como reuso literal.
- **C9 (MENOR, semántica de leído):** abrir el panel marca todo leído en ese instante; eventos que lleguen con el panel abierto cuentan como no-leídos hasta la próxima apertura. v2 lo fija como comportamiento esperado (test F1 caso 4b).
- **[ADICIÓN ARQUITECTO] F6 — Wiring REAL de las fuentes 135 y 142 (una línea por fuente, ancla verificada):** v1 dejaba el seam "para cuando aterricen". Ya aterrizaron. v2 agrega F6: publicar `kind:"error"` desde `PageErrorBoundary.componentDidCatch` (`PageErrorBoundary.tsx:29`, verificado) y `kind:"cost"` desde `CostCapIndicator` en la TRANSICIÓN a `alert|over|blocked` (verificado: `CostCapResponse.state`). El centro nace UNIFICADO de verdad (runs + errores + costos) el día 1, no "runs-only con promesa".

---

## 1. Encabezado / contexto

Hoy las señales de "qué pasó / qué está pasando" en Stacky están **dispersas y efímeras**:
- Los fines de run producen aviso de escritorio + beep + título de pestaña, pero **no dejan rastro** consultable (`executionNotifier.ts` / `tabTitle.ts` son side-effects, no un feed).
- Los errores de la UI (plan 135, **implementado**) se muestran en `Toast.tsx` / `PageErrorBoundary.tsx` pero son **efímeros o locales a la página**.
- Los costos (plan 142, **implementado**) viven en `CostCapIndicator` y el Centro de Costos, **sin push** consultable cuando algo cruza umbral.

No existe **un solo lugar** que responda "¿qué pasó mientras no miraba?". Este plan crea ese lugar: un **Centro de Actividad** client-side (campana en la TopBar + feed desplegable con no-leídos) que **agrega** las fuentes ya existentes sin reinventar streaming ni polling.

---

## 2. Objetivo + KPIs binarios

**Objetivo:** un centro de notificaciones **informativo** (nunca ejecutor) que acumula eventos con timestamp/tipo/severidad/leído, muestra un contador de no-leídos en la TopBar, y ofrece navegación ("ver run") a la superficie relevante — **amplificando** al operador, sin agregarle trabajo ni pasos.

**KPIs (todos BINARIOS, con comando exacto; vitest/tsc desde `Stacky Agents/frontend/`):**
- **KPI-1 — Reducer puro verde:** `npx vitest run src/services/__tests__/activityReducer.test.ts` → exit 0 (dedup por key, tope N=50, no-leídos, agrupación, mute, hydrate tolerante).
- **KPI-2 — Store singleton verde:** `npx vitest run src/services/__tests__/activityCenter.test.ts` → exit 0 (pub/sub, `markAllRead`, persistencia guardada, extensibilidad: kinds sin eventos ⇒ sin sección).
- **KPI-3 — Captura de runs pura verde:** `npx vitest run src/services/__tests__/runCapture.test.ts` → exit 0 (`diffFinishedIds` + `shouldPublishCostTransition`).
- **KPI-4 — Tipos verdes:** `npx tsc --noEmit` → exit 0 (campana + panel + wiring compilan).
- **KPI-5 — Flag canónico verde:** desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend`: `N:\GIT\RS\STACKY\Stacky\.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q` → exit 0 (`test_default_known_only_for_curated` + `test_every_registry_flag_is_categorized` pasan con el flag nuevo). **No se crea archivo de test backend nuevo ⇒ NO hay alta en `HARNESS_TEST_FILES`** (run_harness_tests.sh queda intacto).
- **KPI-6 — Cero polls nuevos (grep binario):** `grep -rEn "new EventSource|setInterval|refetchInterval|fetch\(" src/services/activityCenter.ts src/services/activityReducer.ts src/services/runCapture.ts src/hooks/useRunActivityCapture.ts` → **0 matches**. La única fuente de refresco es la query compartida `useActiveRunsGlobal`; `Executions.byId` on-finish no es un poll. **Regla anti-gotcha (C7): PROHIBIDO que los comentarios/JSDoc de esos 4 archivos contengan los literales `setInterval`, `EventSource`, `refetchInterval` o `fetch(`** — reescribir la prosa del comentario, el gate siempre gana.
- **KPI-7 — Ratchet de deuda UI verde (C5):** `npx vitest run src/__tests__/uiDebtRatchet.test.ts` → exit 0. Los .tsx nuevos de F4 tienen alcance cero-deuda: **0 `style={}` inline**; todo estilo en `.module.css` con tokens.

---

## 3. Por qué ahora / gap (evidencia por grep, re-verificada 2026-07-16)

### 3.1 Infra YA existente que se REUSA (leída, no supuesta)

| Símbolo reusado | Archivo:línea (hoy) | Qué aporta a 152 |
|---|---|---|
| `useActiveRunsGlobal()` | `frontend/src/hooks/useActiveRunsGlobal.ts:12` | Query compartida react-query de runs activos, refresco 5 s. Todos los consumidores comparten `queryKey` ⇒ UNA sola request. |
| `ACTIVE_RUNS_QUERY_KEY`, `ACTIVE_RUNS_REFRESH_MS`, `mergeActiveRuns`, `fetchActiveRuns` | `frontend/src/services/activeRuns.ts:12,13,20,30` | Fuente única de runs, diseñada para ser compartida. |
| Patrón diff prev/current + `Executions.byId` | `frontend/src/hooks/useGlobalExecutionNotifier.ts` | Detección de "run que desapareció del set activo" → confirma status final. 152 replica el diff en helper puro SIN tocar este archivo caliente. |
| `buildNotificationBody(row)` | `frontend/src/services/notifierCore.ts:52` | Cuerpo humano "proyecto · ticket" — se reusa tal cual. |
| `combineOutcome`/`FinishOutcome` | `frontend/src/services/notifierCore.ts:33` | Semántica pegajosa base. **152 la refina (C8):** `error→"error"` ≠ `needs_review→"attention"` (divergencia consciente, el feed distingue fallo de revisión). |
| Slot de acciones de la TopBar | `frontend/src/components/TopBar.tsx:202` (`<div className={styles.actions}>`), vecinos `<CostCapIndicator>` (`:211`) y `<StreakBadge/>` (`:212`) | Lugar EXACTO donde se inserta la campana. Ancla = el TEXTO, no la línea. |
| Montaje de hooks globales | `frontend/src/App.tsx:99` (`useGlobalExecutionNotifier();`), `<TopBar onGoToTeam={...} shellV2={...}/>` en `App.tsx:245` | Punto EXACTO donde 152 monta `useRunActivityCapture(notifEnabled)`. |
| Endpoint de flags existente | `HarnessFlags.list()` en `frontend/src/api/endpoints.ts:908`; `HarnessFlagView.value: boolean \| number \| string` (`endpoints.ts:710`) | Lectura del valor efectivo del flag SIN endpoint nuevo. Comparar con `=== true` (el flag es bool). |
| `EmptyState` | `frontend/src/components/EmptyState.tsx` (presets `executions\|packs\|tickets\|agents\|history\|generic`) | Estado vacío del feed. Existe hoy. |
| `IconButton`, `Skeleton` (plan 138, **implementado**) | `frontend/src/components/ui/IconButton.tsx`, `ui/Skeleton.tsx` (verificados en árbol) | La campana ES un `IconButton`; la carga usa `Skeleton`. **v2 elimina el `<button>` propio y el placeholder ad-hoc de v1 (C1): duplicar la primitiva viola reuso.** |
| Tokens tema/motion (141/143, **implementados**) | `theme.css`: `--transition-opacity`, `--transition-transform`, `--focus-ring` | Entrada/salida del panel. 152 JAMÁS escribe `@media (prefers-reduced-motion)` (dueño único: 141 F5). |
| Fuente de errores (135, **implementado**) | `frontend/src/components/PageErrorBoundary.tsx:29` (`componentDidCatch`), `Toast.tsx` | Punto de publicación `kind:"error"` (F6). |
| Fuente de costos (142, **implementado**) | `frontend/src/components/CostCapIndicator.tsx` (`CostCapResponse.state: "unset"\|"ok"\|"alert"\|"over"\|"blocked"`) | Punto de publicación `kind:"cost"` en transición de estado (F6). |
| `lucide-react ^0.453.0` | `package.json` | Icono `Bell` — sin dependencia nueva. |

### 3.2 Evidencia de AUSENCIA de un centro de notificaciones

- `grep -rEn "publishActivity|activityCenter" frontend/src` → **0 matches** (re-verificado 2026-07-16). `grep -riEn "notification|bell|unread" frontend/src/components` → solo botones ajenos. No hay campana, contador ni feed. El gap es real.

### 3.3 Tabla de dependencias (estado real 2026-07-16 — C1)

| Fuente / dependencia | Plan | Estado hoy | Rol en 152 |
|---|---|---|---|
| Runs activos/finalizados | 134 | **IMPLEMENTADO** | Fuente base (F2). |
| TopBar (slot campana) | 139 | **IMPLEMENTADO**, flag `STACKY_UI_SHELL_V2_ENABLED` default OFF | La campana va en el slot `styles.actions` de la TopBar ACTUAL; funciona igual con shell v1 (flag OFF, default) y v2 (misma TopBar, prop `shellV2`). **No depende del valor del flag de 139.** |
| `EmptyState` / `Skeleton` / `IconButton` | 140/138 | **IMPLEMENTADOS** | Se usan directo, sin fallback ad-hoc (C1). |
| Tokens `--transition-*` + reduced-motion | 143+141 | **IMPLEMENTADOS** | Se referencian por `var()`. |
| Errores UI | 135 | **IMPLEMENTADO** (`PageErrorBoundary`, `Toast`) | Publica `kind:"error"` (F6a). |
| Costos | 142 | **IMPLEMENTADO** (`CostCapIndicator`, Centro de Costos) | Publica `kind:"cost"` en transición (F6b). |

---

## 4. Principios, guardarraíles y regla de extensibilidad

1. **Reuso, no reinvención.** El refresco de runs es la query compartida `useActiveRunsGlobal` (0 requests nuevos). 152 no crea intervalos, ni EventSource, ni fetch de polling (KPI-6). UI con primitivas de 138 (KPI-7).
2. **Human-in-the-loop.** El centro es **informativo**. Cada notificación puede llevar UNA acción de **navegación** ("ver run" → `selectTab`). **Prohibido** ejecutar acciones destructivas, publicar, crear tickets o mutar estado desde el centro. Amplifica, no reemplaza.
3. **Cero trabajo extra al operador.** UI aditiva, opt-out. La campana aparece sola; silenciar tipos y opt-out son opcionales, nunca requeridos. Anti-ruido: dedup por `key`, agrupación por `kind`, mute por `kind`, publicación de costos SOLO en transición (no en cada poll).
4. **No degradar performance.** Tope **N=50** eventos (cola acotada). Animación solo de `opacity`/`transform`. Reducer/store puros O(n≤50) en memoria. Sin backend nuevo. **Con flag OFF la captura NO corre** (C2): cero requests, cero escrituras.
5. **Mono-operador sin auth.** No hay roles; el feed es local a la sesión del navegador (más `localStorage` acotado). No es un log auditable multi-usuario.
6. **Backward-compatible.** Firmas nuevas aditivas. Archivos calientes (`App.tsx`, `TopBar.tsx`, `PageErrorBoundary.tsx`, `CostCapIndicator.tsx`) reciben ediciones **aditivas mínimas ancladas por texto normativo**. Con flag OFF, la TopBar queda **idéntica** a hoy.

### 4.4 Confirmación: ninguna de las 4 excepciones duras aplica

El Centro de Actividad es UI **aditiva, informativa, sin autonomía, sin escritura destructiva, sin superficie de seguridad ni de pérdida de datos**: (1) no bypasea revisión humana, (2) no es destructivo/irreversible, (3) no requiere prerequisito no garantizado (todo lo que consume existe en la instalación default), (4) no reduce seguridad. Por lo tanto: **default ON**.

### 4.5 REGLA DE EXTENSIBILIDAD (antes "degradación honesta")

> Con 135/142 ya implementados (C1), esta regla deja de ser un plan de contingencia y queda como **contrato de extensibilidad**: el seam es un **pub/sub** (`publishActivity`). El panel renderiza **solo** las secciones (`kind`) con al menos un evento (`groupByKind` no crea bucket vacío). Un `kind` futuro (p. ej. `"deploy"`) se enchufa con UNA línea `publishActivity(...)` en su fuente, sin tocar 152. Kinds desconocidos se renderizan bajo su nombre (forward-compatible).
>
> **Cómo se testea:** KPI-2 incluye un test que publica solo eventos `run` y asegura que `groupByKind(snapshot)` no contiene buckets `error` ni `cost`; y otro que publica un `kind` silenciado (mute) y asegura que no entra al snapshot.

---

## 5. Glosario

| Término | Definición |
|---|---|
| **ActivityEvent** | Registro inmutable: `{ key, kind, severity, title, body?, ts, nav? }`. `key` identifica unívocamente el evento para dedup (p. ej. `run:1234`). |
| **kind** | Fuente/categoría del evento: `"run" \| "error" \| "cost"` (extensible sin romper: buckets desconocidos se renderizan bajo su nombre). |
| **severity** | `"info" \| "success" \| "attention" \| "error"` — solo estética (color/icono), no comportamiento. |
| **nav** | Intención de navegación opcional `{ tab: string; executionId?: number }`. Se ejecuta vía `selectTab` del `App`. **Nunca** destructiva. |
| **no-leído (unread)** | Evento con `ts > lastReadAt`. Abrir el panel setea `lastReadAt = Date.now()`. Eventos que llegan con el panel ya abierto quedan no-leídos hasta la próxima apertura (C9, comportamiento esperado). |
| **tope N** | Cap de la cola = **50** eventos (`ACTIVITY_CAP`). Al llegar al tope se descarta el más viejo. |
| **seam / pub-sub** | `publishActivity(evt)` (fuentes escriben) + `subscribeActivity(cb)` (UI lee). Único punto de acoplamiento entre 152 y sus fuentes. |
| **mute** | Silenciar un `kind`: eventos de ese kind se descartan en `publishActivity` (no se guardan, no cuentan). Config del operador por UI (opcional), persistida en `localStorage`. |
| **transición de costo** | Cambio de `CostCapResponse.state` desde `unset\|ok` hacia `alert\|over\|blocked` (o entre estos tres). Solo la TRANSICIÓN publica evento; el poll de 60 s repetido en el mismo estado NO re-publica (anti-ruido, F6b). |

---

## 6. Fases F0..F6

> **Pre-flight OBLIGATORIO por fase que toque archivo caliente** (`App.tsx`, `TopBar.tsx`, `PageErrorBoundary.tsx`, `CostCapIndicator.tsx`): `git status -- "<ruta>"`. Si hay WIP ajeno, **STOP y avisar al orquestador** antes de editar. Staging quirúrgico por path explícito. **El implementador NO commitea** (lo hace el orquestador).
>
> **Comandos vitest/tsc** se corren desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend`, **por archivo** (gotcha vitest test-order pollution). **pytest** con `N:\GIT\RS\STACKY\Stacky\.venv\Scripts\python.exe`, **por archivo** (C6).
> **Anclas:** toda edición se ancla por TEXTO normativo citado; los `archivo:línea` de este doc son referencia del 2026-07-16 y pueden derivar (C3).

---

### F0 — Contrato + reducer PURO (tests primero)

**Objetivo (1 frase):** definir tipos y la lógica pura de acumulación (dedup, tope, no-leídos, agrupación, mute, hydrate) — el corazón testeable sin DOM. **Valor:** toda la corrección vive acá y se blinda con tests puros (no hay `@testing-library/react` ni jsdom en `package.json` — gap estructural verificado; los helpers no tocan DOM).

**Archivos:**
- NUEVO `frontend/src/services/activityReducer.ts`
- NUEVO `frontend/src/services/__tests__/activityReducer.test.ts`

**Símbolos/keys EXACTOS (exports de `activityReducer.ts`):**
```ts
export type ActivityKind = "run" | "error" | "cost";
export type Severity = "info" | "success" | "attention" | "error";
export interface ActivityEvent {
  key: string;          // dedup, p. ej. "run:1234"
  kind: ActivityKind;
  severity: Severity;
  title: string;
  body?: string;
  ts: number;           // epoch ms
  nav?: { tab: string; executionId?: number };
}
export interface ActivityState { events: ActivityEvent[]; lastReadAt: number; muted: ActivityKind[]; }

export const ACTIVITY_CAP = 50;
export const LS_STATE_KEY = "stacky.activity.v1";   // única clave localStorage

export function emptyState(): ActivityState;                                   // { events:[], lastReadAt:0, muted:[] }
export function appendEvent(s: ActivityState, e: ActivityEvent): ActivityState; // dedup + tope + orden
export function unreadCount(s: ActivityState): number;                          // events con ts > lastReadAt
export function markAllRead(s: ActivityState, nowMs: number): ActivityState;    // lastReadAt = nowMs
export function groupByKind(events: ActivityEvent[]): Record<string, ActivityEvent[]>; // solo kinds presentes
export function isMuted(s: ActivityState, kind: ActivityKind): boolean;
export function setMuted(s: ActivityState, kind: ActivityKind, on: boolean): ActivityState;
export function severityFromRunStatus(status: string): Severity;               // refina combineOutcome (C8): error ≠ needs_review
export function serializeState(s: ActivityState): string;                      // JSON, recorta a ACTIVITY_CAP
export function hydrateState(raw: string | null): ActivityState;               // tolerante: corrupto/null → emptyState()
```

**Pseudocódigo con casos borde:**
```ts
export function appendEvent(s, e) {
  // evento DUPLICADO: misma key ya presente → conserva el de ts MÁS NUEVO, no agrega fila
  const rest = s.events.filter(x => x.key !== e.key);
  const merged = [e, ...rest].sort((a, b) => b.ts - a.ts);   // más nuevo primero
  // COLA LLENA: recorta al tope (descarta los más viejos del final)
  return { ...s, events: merged.slice(0, ACTIVITY_CAP) };
}
export function groupByKind(events) {
  const out: Record<string, ActivityEvent[]> = {};
  for (const e of events) (out[e.kind] ??= []).push(e);       // kind sin eventos ⇒ nunca crea bucket
  return out;
}
export function severityFromRunStatus(status) {
  if (status === "error") return "error";
  if (status === "needs_review") return "attention";          // C8: refinamiento consciente vs combineOutcome
  if (status === "completed") return "success";
  return "info";                                              // cancelled/desconocido: informativo, no alarma
}
export function hydrateState(raw) {
  if (!raw) return emptyState();
  try { const p = JSON.parse(raw); /* valida shape mínima */ return normalize(p); }
  catch { return emptyState(); }                              // JSON INVÁLIDO ⇒ estado vacío, nunca throw
}
```

**Tests (archivo exacto + casos):** `activityReducer.test.ts`
1. `appendEvent` con key nueva agrega y ordena desc por ts.
2. `appendEvent` con key duplicada NO duplica y conserva el ts más nuevo.
3. `appendEvent` respeta `ACTIVITY_CAP=50` (51 eventos → longitud 50, se cae el más viejo).
4. `unreadCount` cuenta solo `ts > lastReadAt` (borde `ts === lastReadAt` → leído).
5. `markAllRead` deja `unreadCount === 0`.
6. `groupByKind` con eventos solo `run` → **sin** claves `error`/`cost` (extensibilidad §4.5).
7. `isMuted`/`setMuted` round-trip.
8. `severityFromRunStatus`: error→"error", needs_review→"attention", completed→"success", cancelled→"info".
9. `hydrateState(null)` y `hydrateState("{corrupto")` → `emptyState()` sin throw.
10. `serializeState`→`hydrateState` round-trip preserva orden y recorta a 50.

**Comando:** `npx vitest run src/services/__tests__/activityReducer.test.ts` — **criterio: exit 0.**
**Flag:** n/a. **Runtime:** TS puro, idéntico en los 3. **Trabajo del operador:** ninguno.

---

### F1 — Store singleton + pub/sub + persistencia guardada (tests)

**Objetivo:** el estado vivo compartido y su API de suscripción, sobre el reducer puro. **Valor:** un único punto donde fuentes escriben y la UI lee, con persistencia acotada y tolerante.

**Archivos:**
- NUEVO `frontend/src/services/activityCenter.ts`
- NUEVO `frontend/src/services/__tests__/activityCenter.test.ts`

**Símbolos EXACTOS (exports de `activityCenter.ts`):**
```ts
export function publishActivity(e: ActivityEvent): void;   // aplica mute + appendEvent + persiste + notifica
export function subscribeActivity(cb: () => void): () => void;  // devuelve unsubscribe
export function getActivitySnapshot(): ActivityState;      // REFERENCIA ESTABLE entre cambios (para useSyncExternalStore)
export function markActivityRead(): void;                  // lastReadAt = Date.now() + notifica
export function getMuted(): ActivityKind[];
export function setActivityMuted(kind: ActivityKind, on: boolean): void;
export function __resetActivityForTests(): void;           // limpia estado + storage (solo tests)
```

**Detalles clave:**
- Estado en variable de módulo (singleton, mismo patrón que `tabTitle.ts`/`executionNotifier.ts`).
- **`getActivitySnapshot` debe devolver la MISMA referencia** hasta que haya un cambio (requisito de `useSyncExternalStore` para no loopear): se guarda el `ActivityState` actual y solo se reemplaza al mutar.
- Persistencia vía wrapper `safeStorage` interno: `try { localStorage.getItem/setItem } catch {}` y `typeof localStorage !== "undefined"` (tolerante a entorno node de vitest y a modo privado). **Nunca throw.**
- Hidrata al primer acceso (lazy) con `hydrateState(safeStorage.get(LS_STATE_KEY))`.
- `publishActivity`: si `isMuted(state, e.kind)` → **descarta** (no guarda, no notifica). Si no, `state = appendEvent(...)`, persiste `serializeState`, notifica a todos los `subscribers`.
- **C7:** los comentarios de este archivo NO pueden contener los literales del grep KPI-6.

**Tests (`activityCenter.test.ts`) — usan `__resetActivityForTests()` en `beforeEach`:**
1. `publishActivity` + `getActivitySnapshot` refleja el evento; subscriber es llamado 1 vez.
2. `unsubscribe` deja de recibir notificaciones.
3. `getActivitySnapshot` estable: sin publish entre dos llamadas → **misma referencia** (`===`).
4. `markActivityRead` → `unreadCount(getActivitySnapshot()) === 0`.
4b. (C9) publish DESPUÉS de `markActivityRead` → `unreadCount === 1` (lo nuevo queda no-leído).
5. Dedup end-to-end: publicar `run:1` dos veces → snapshot con 1 solo evento.
6. Tope: publicar 60 eventos → snapshot con 50.
7. **Extensibilidad:** publicar solo `kind:"run"` → `groupByKind` sin `error`/`cost`.
8. **Mute:** `setActivityMuted("error", true)` y luego `publishActivity({kind:"error"...})` → snapshot NO contiene el evento.
9. Persistencia guardada: con `localStorage` disponible, tras publish el `safeStorage` tiene JSON válido; con `localStorage` forzado a throw (stub), `publishActivity` no rompe.

**Comando:** `npx vitest run src/services/__tests__/activityCenter.test.ts` — **criterio: exit 0.**
**Flag:** n/a. **Runtime:** idéntico. **Trabajo del operador:** ninguno.

---

### F2 — Captura de runs (reuso de la query compartida, 0 requests nuevos, gateada por flag)

**Objetivo:** poblar la categoría `run` reusando `useActiveRunsGlobal` (misma `queryKey` ⇒ 0 requests nuevos) y confirmando el status final on-finish. **Valor:** el feed tiene contenido real desde el día 1 sin tocar archivos calientes ni agregar polling.

**Archivos:**
- NUEVO `frontend/src/services/runCapture.ts` (lógica pura del diff + helper de transición de costo para F6b)
- NUEVO `frontend/src/services/__tests__/runCapture.test.ts`
- NUEVO `frontend/src/hooks/useRunActivityCapture.ts` (wiring react-query, sin lógica testeable-crítica)

**Símbolos EXACTOS:**
```ts
// runCapture.ts
export function diffFinishedIds(prev: Set<number> | null, current: Set<number>): number[];
// devuelve ids que estaban en prev y ya NO están en current (finalizaron/desaparecieron)
export function shouldPublishCostTransition(prev: string | null, next: string): boolean;
// true SOLO si next ∈ {"alert","over","blocked"} y next !== prev  (helper puro para F6b)

// useRunActivityCapture.ts
export function useRunActivityCapture(enabled: boolean): void;  // C2: enabled=false ⇒ early-return total
```

**Pseudocódigo `useRunActivityCapture` (replica el patrón de `useGlobalExecutionNotifier.ts`, SIN editar ese archivo):**
```ts
export function useRunActivityCapture(enabled: boolean) {
  const activeQ = useActiveRunsGlobal();               // MISMA query compartida ⇒ 0 requests nuevos
  const prev = useRef<Set<number> | null>(null);
  useEffect(() => {
    if (!enabled) return;                              // C2: flag OFF ⇒ cero trabajo (ni byId ni storage)
    if (activeQ.data == null) return;                  // sin snapshot (carga/error): no comparar
    const current = new Set(activeQ.data.map(e => e.id));
    const finished = diffFinishedIds(prev.current, current);
    prev.current = current;                            // PRIMER snapshot: prev era null ⇒ diff = [] (no falsos positivos)
    for (const id of finished) {
      const key = `run:${id}`;
      // doble-emisión con el notificador de 134: si ya está en el store, NO re-consultamos byId
      if (getActivitySnapshot().events.some(e => e.key === key)) continue;
      void Executions.byId(id).then(row => {
        publishActivity({
          key, kind: "run",
          severity: severityFromRunStatus(String(row.status || "completed")),
          title: `Agente ${row.agent_type || "agente"} — ${row.status}`,
          body: buildNotificationBody(row),           // reuso notifierCore.ts:52
          ts: Date.now(),
          nav: { tab: "team", executionId: row.id },  // "team" verificado: selectTab("team") en App.tsx:245
        });
      }).catch(() => { /* byId falló: se ignora, no se inventa evento */ });
    }
  }, [activeQ.data, enabled]);
}
```

**Casos borde cubiertos:** primer snapshot (`prev=null` ⇒ sin eventos), sin cambios (diff vacío), varios fines simultáneos (loop), evento duplicado (guard por key + store dedup), `byId` con error (catch silencioso), cola llena (el store recorta), flag OFF (early-return, C2).

**Tests puros (`runCapture.test.ts`):**
1. `diffFinishedIds(null, {1,2})` → `[]` (primer snapshot).
2. `diffFinishedIds({1,2}, {2})` → `[1]`.
3. `diffFinishedIds({1,2,3}, {})` → `[1,2,3]`.
4. `diffFinishedIds({1}, {1,2})` → `[]` (aparecer no es finalizar).
5. `diffFinishedIds({1}, {1})` → `[]` (sin cambios).
6. `shouldPublishCostTransition(null,"ok")` → false; `("ok","alert")` → true; `("alert","alert")` → false; `("alert","over")` → true; `("over","ok")` → false.

**Comando:** `npx vitest run src/services/__tests__/runCapture.test.ts` — **criterio: exit 0.**
**Flag:** la captura entera recibe `enabled` desde F3/F4 (C2). **Runtime:** reusa el polling por intervalo de `activeRuns.ts` (no SSE) ⇒ idéntico en los 3 runtimes. **Trabajo del operador:** ninguno.

> **Nota de costo (declarada):** on-finish, `useRunActivityCapture` puede disparar un `Executions.byId` que `useGlobalExecutionNotifier` (134) también dispara. Es **1 request por run finalizado** (no un poll), acotado por runs concurrentes, y **solo** cuando `run:${id}` no está ya en el store. Se elige este costo mínimo para **no editar** el archivo caliente `useGlobalExecutionNotifier.ts`. Optimización futura (fuera de scope): que 134 publique al seam y este diff se apague (§8).

---

### F3 — Flag canónico `STACKY_NOTIFICATION_CENTER_ENABLED` (default ON)

**Objetivo:** registrar el flag por la vía canónica para que el operador pueda opt-out desde `HarnessFlagsPanel`, gateando la UI vía el endpoint EXISTENTE. **Valor:** control por UI sin endpoint nuevo.

**Archivos (config pura, único toque backend):**
- `backend/services/harness_flags.py`:
  - Agregar `FlagSpec` a `FLAG_REGISTRY` (tupla, hoy `harness_flags.py:309`), tipo `bool`, `default=True`, `env_only=False`, con `label`/`description`/`plain_help` (`what/on_effect/off_effect/example`).
  - Agregar la key `"STACKY_NOTIFICATION_CENTER_ENABLED"` a `_CATEGORY_KEYS` (hoy `harness_flags.py:117`) bajo la categoría **`capacidades_optin`** — id VERIFICADO existente (`harness_flags.py:103`, C4; sin alternativas). *(Sin esto rompe `test_every_registry_flag_is_categorized`.)*
- `backend/tests/test_harness_flags.py`:
  - Agregar la key a `_CURATED_DEFAULTS_ON` (set, hoy `test_harness_flags.py:467`). *(Sin esto rompe `test_default_known_only_for_curated`; gotcha: `default=True` fuera de la curada rompe el ratchet.)*
- `backend/config.py`:
  - Alta del default efectivo `"true"` (el default RUNTIME vive en `config.py`; solo FlagSpec = cosmético — gotcha conocido).
- **NO** regenerar `deployment/.../harness_defaults.env` (generador `deployment/export_harness_defaults.py`; prohibido tocarlo a mano, plan 133 §3.6; drift preexistente conocido).
- **Ratchet de tests backend:** NO se crea archivo `test_*.py` nuevo ⇒ NO hay alta en `HARNESS_TEST_FILES` (sh ni ps1). El flag no usa `requires=` ⇒ NO se toca `test_harness_flags_requires.py`.

**Gating en el frontend (parte de F4, se describe acá por dependencia):** en `App.tsx`, leer el valor efectivo vía el endpoint existente (`HarnessFlags.list()`, `endpoints.ts:908`). NOTA: `probeFlagHealth` (135 F6, `App.tsx:134`) es para endpoints health, NO aplica acá:
```ts
const [notifEnabled, setNotifEnabled] = useState(true);   // FAIL-OPEN: default ON aunque el flag no esté en la respuesta
useEffect(() => {
  HarnessFlags.list()
    .then(r => {
      const f = r.flags.find(x => x.key === "STACKY_NOTIFICATION_CENTER_ENABLED");
      setNotifEnabled(f ? f.value === true : true);        // value es boolean para flags bool (endpoints.ts:710)
    })
    .catch(() => setNotifEnabled(true));                   // error ⇒ true (no romper UI aditiva)
}, []);
```

**Tests/comando (C6, literal):** desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend`:
`N:\GIT\RS\STACKY\Stacky\.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q`
**Criterio binario:** exit 0 (en particular `test_default_known_only_for_curated` y `test_every_registry_flag_is_categorized`).
**Flag:** este ES el flag, default **ON**. **Runtime:** se lee igual en los 3 (config backend + endpoint compartido). **Trabajo del operador:** ninguno (default ON; opt-out opcional desde el panel de flags).

---

### F4 — Campana + panel + wiring (UI, primitivas reales de 138/140)

**Objetivo:** la campana con contador de no-leídos en la TopBar y el panel-feed desplegable con estados vacío/carga (140), micro-interacciones (143) y navegación no destructiva. **Valor:** la superficie visible del centro.

**Archivos NUEVOS:**
- `frontend/src/components/NotificationBell.tsx` + `NotificationBell.module.css`
- `frontend/src/components/NotificationPanel.tsx` + `NotificationPanel.module.css`
- NUEVO `frontend/src/hooks/useActivityCenter.ts`

**Regla dura (C5/KPI-7):** los .tsx nuevos tienen **0 `style={}` inline** (gate `src/__tests__/uiDebtRatchet.test.ts`, alcance cero-deuda para archivos nuevos). Todo estilo en `.module.css` con tokens de `theme.css`. Si algún ancho/valor es dinámico, usar ref + effect imperativo (patrón documentado, NO replicar la deuda heredada de `PipelineStatus`).

**Archivos CALIENTES editados (aditivo, anclado por TEXTO normativo; pre-flight `git status` OBLIGATORIO):**
- `frontend/src/App.tsx`:
  - Junto a la línea `useGlobalExecutionNotifier();` (hoy `App.tsx:99`) agregar `useRunActivityCapture(notifEnabled);` y el estado `notifEnabled` (F3).
  - En el JSX `<TopBar onGoToTeam={() => selectTab("team")} shellV2={shellV2Enabled} />` (hoy `App.tsx:245`) pasar props aditivas: `notificationsEnabled={notifEnabled}` y `onActivityNavigate={(nav) => selectTab(nav.tab)}`.
- `frontend/src/components/TopBar.tsx`:
  - Firma: agregar props opcionales `notificationsEnabled?: boolean` y `onActivityNavigate?: (nav: { tab: string; executionId?: number }) => void` a `TopBarProps`.
  - Render: dentro de `<div className={styles.actions}>` (hoy `TopBar.tsx:202`), **antes** de `<CostCapIndicator` (hoy `:211`), insertar:
    `{notificationsEnabled && <NotificationBell onNavigate={onActivityNavigate} />}`

**Símbolos:**
```ts
// useActivityCenter.ts
export function useActivityCenter(): {
  snapshot: ActivityState;
  unread: number;
  groups: Record<string, ActivityEvent[]>;
  markRead: () => void;
};   // usa useSyncExternalStore(subscribeActivity, getActivitySnapshot). SIN requests nuevos.
```

**`NotificationBell.tsx` (C1: primitivas reales, sin fallback ad-hoc):**
- Usa **`IconButton` de `components/ui`** (existe, plan 138 implementado) con icono `Bell` de `lucide-react` (sin dep nueva).
- Badge de no-leídos: muestra `unread` (o `"9+"` si `unread > 9`); oculto si `unread === 0`.
- Click → toggle del panel; **al ABRIR** llama `markRead()` (C9: lo que llegue con el panel abierto queda no-leído hasta la próxima apertura).
- `aria-label="Notificaciones"`, `aria-expanded`, foco visible con `--focus-ring` (141, existe).

**`NotificationPanel.tsx`:**
- Lista `groups` en orden `run` → `error` → `cost` → (otros). Cada sección solo si tiene eventos (§4.5).
- **VACÍO** (0 eventos totales): `<EmptyState variant="history" .../>` (existe). Regla vacío-vs-error de 140: `EmptyState` solo cuando no hay error de fuente base.
- **CARGA** (primer snapshot de runs pendiente y 0 eventos): **`Skeleton` de `components/ui`** (existe, C1). No agrega requests/timers.
- **Micro-interacciones (143, implementado):** panel e ítems con `transition: var(--transition-opacity), var(--transition-transform);`. **152 NUNCA escribe `@media (prefers-reduced-motion)`** (dueño único: 141 F5).
- Cada ítem: `title`, `body`, hora relativa, color/icono por `severity`, y botón **"Ver"** → `onNavigate(item.nav)`. **Solo navegación**; prohibido cualquier acción destructiva/de escritura.
- (Opcional) engranaje → mute por `kind` (`setActivityMuted`), persistido; es config por UI, no requerida.

**Tests:** los componentes React **no** son testeables sin `@testing-library/react`/jsdom (ausentes en `package.json` — gap estructural verificado; este plan NO las agrega). Por lo tanto:
- **Criterios binarios de F4:** `npx tsc --noEmit` → exit 0 **y** `npx vitest run src/__tests__/uiDebtRatchet.test.ts` → exit 0 (KPI-7).
- **Verificación conductual:** smoke manual documentado (§9.2), requerido para DoD.

**Flag:** gateado por `notificationsEnabled` (F3); OFF ⇒ TopBar idéntica a hoy y captura apagada (C2). **Runtime:** 100% presentación, idéntico en los 3. **Trabajo del operador:** ninguno.

---

### F5 — Seam pub/sub documentado + extensibilidad testeada + mute

**Objetivo:** dejar documentado y testeado el contrato pub/sub para fuentes futuras (`kind`s nuevos), sin que 152 dependa de ellas. **Valor:** el centro crece con UNA línea por fuente nueva, sin re-tocar 152.

**Archivos:**
- (Doc/contrato) esta sección + comentario JSDoc en `activityCenter.ts:publishActivity` (C7: sin literales del grep KPI-6 en la prosa).
- Extensión de tests en `activityCenter.test.ts` (ya listada en F1 casos 7-8): extensibilidad (solo `run` ⇒ sin `error`/`cost`) y mute.

**Contrato genérico para una fuente futura (ejemplo `kind:"deploy"`):**
```ts
publishActivity({ key: `deploy:${targetId}`, kind: "deploy" as ActivityKind, severity: "info",
                  title: "Deploy finalizado", body: targetName, ts: Date.now(),
                  nav: { tab: "devops" } });
```
Sin esa línea, no hay eventos de ese kind y el panel no muestra esa sección. **Nada que importar en 152, nada que romper.**

**Tests:** cubiertos por `activityCenter.test.ts` (casos 7-8). **Comando:** `npx vitest run src/services/__tests__/activityCenter.test.ts` — **criterio: exit 0.**
**Flag:** heredado de F3. **Runtime:** idéntico. **Trabajo del operador:** mute opcional por UI; nada requerido.

---

### F6 — [ADICIÓN ARQUITECTO] Wiring REAL de las fuentes 135 (errores) y 142 (costos)

**Justificación:** v1 dejaba estas fuentes "para cuando aterricen"; 135 y 142 están **implementados hoy** (C1). Con dos ediciones aditivas de una línea (más un ref), el centro nace **unificado de verdad** (runs + errores + costos) el día 1. Human-in-the-loop intacto (solo informa), cero requests nuevos (reusa datos que esos componentes ya tienen), anti-ruido garantizado por dedup + publicación solo-en-transición.

**F6a — Errores (fuente 135). Archivo caliente:** `frontend/src/components/PageErrorBoundary.tsx` (pre-flight `git status` obligatorio).
- Ancla: método `componentDidCatch(error: Error, info: React.ErrorInfo)` (hoy `PageErrorBoundary.tsx:29`). Agregar al FINAL del método (sin tocar su lógica existente):
```ts
publishActivity({ key: `error:${Date.now()}`, kind: "error", severity: "error",
                  title: "Error en la UI", body: String(error?.message || error), ts: Date.now() });
```
- Import aditivo: `import { publishActivity } from "../services/activityCenter";`
- Sin `nav` (el boundary no sabe la superficie destino; no inventar). El evento queda consultable aunque el toast/boundary se haya ido — exactamente el gap que motiva 152.

**F6b — Costos (fuente 142). Archivo caliente:** `frontend/src/components/CostCapIndicator.tsx` (pre-flight obligatorio).
- Ancla: el `.then((d) => { if (!cancelled) setData(d); })` del `refresh()` (verificado). Cambiar a:
```ts
.then((d) => {
  if (cancelled) return;
  if (shouldPublishCostTransition(prevStateRef.current, d.state)) {
    publishActivity({ key: `cost:${d.project ?? "global"}:${d.state}`, kind: "cost", severity: "attention",
                      title: `Costo mensual en estado ${d.state}`,
                      body: `$${d.spent_usd.toFixed(2)} / $${d.monthly_cap_usd.toFixed(2)} (${d.spent_pct.toFixed(0)}%)`,
                      ts: Date.now() });
  }
  prevStateRef.current = d.state;
  setData(d);
})
```
- Agregar `const prevStateRef = useRef<string | null>(null);` e imports aditivos (`useRef`, `publishActivity`, `shouldPublishCostTransition`).
- **Anti-ruido crítico:** el poll de 60 s de este componente repite el mismo `state`; `shouldPublishCostTransition` (helper puro, testeado en F2 caso 6) publica SOLO en transición hacia/entre `alert|over|blocked`. La key incluye el `state` ⇒ re-transiciones al mismo estado deduplican; una transición nueva (`alert`→`over`) genera evento nuevo. Jamás se re-marca no-leído por el poll.

**Tests:** la lógica de decisión es `shouldPublishCostTransition` (pura, F2 caso 6, KPI-3). Los componentes en sí quedan cubiertos por `npx tsc --noEmit` (KPI-4) + smoke §9.2 (casos 6-7).
**Flag:** ambos wirings publican al store; con flag OFF la campana no se renderiza y el store solo acumula en memoria/localStorage acotado (≤50) — impacto nulo. **Runtime:** idéntico en los 3. **Trabajo del operador:** ninguno.

---

## 7. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | **Sesiones concurrentes editando los mismos archivos calientes** (`App.tsx`, `TopBar.tsx`, `PageErrorBoundary.tsx`, `CostCapIndicator.tsx`). | Ediciones aditivas mínimas ancladas a TEXTO normativo (no líneas, C3). Pre-flight `git status` por archivo; WIP ajeno ⇒ STOP. Staging quirúrgico por path explícito. |
| R2 | **Doble `byId` / doble evento** con el notificador de 134. | Dedup por `key=run:${id}` en el store + guard "si ya está en el store, no consultar byId". Doble emisión es inofensiva (dedup) y el byId extra es acotado (§F2 nota de costo). |
| R3 | **Ruido del poll de costos (60 s)** re-publicando el mismo estado. | `shouldPublishCostTransition` publica SOLO en transición (F6b, testeado F2 caso 6); key incluye el estado ⇒ dedup. |
| R4 | **`useSyncExternalStore` re-render infinito** por snapshot inestable. | `getActivitySnapshot` devuelve referencia estable entre cambios (test F1 caso 3). |
| R5 | **Crecimiento sin límite / localStorage lleno.** | Tope duro `ACTIVITY_CAP=50` (testeado); `safeStorage` con try/catch tolerante a cuota. |
| R6 | **`localStorage` corrupto** rompe el arranque. | `hydrateState` tolerante (JSON inválido → `emptyState()`, testeado). |
| R7 | **Flag OFF dejando trabajo residual.** | C2: `useRunActivityCapture(enabled)` early-return; campana no renderizada; F6a/F6b publican a un store inerte y acotado (sin UI, sin requests propios). |
| R8 | **Gate KPI-6 disparado por comentarios propios** (gotcha recurrente 6x). | C7: prohibición explícita de los literales del grep en comentarios de los 4 archivos fuente. |
| R9 | **uiDebtRatchet rojo por inline styles en .tsx nuevos.** | C5/KPI-7: 0 `style={}`; anchos dinámicos vía ref+effect imperativo. |
| R10 | **Colisión de numeración** (v1 se propuso como 146; franja 144-149 ocupada por serie concurrente). | RESUELTO: renumerado a 152 (hermanos 150/151), serie ajena 144-149 intacta. Referencias internas actualizadas. |

---

## 8. Fuera de scope

- **NO es un log auditable.** Es un feed efímero de conveniencia, local al navegador, acotado a 50 eventos. La telemetría/auditoría real es backend, fuera de este plan.
- **NO agrega backend** (endpoint, ruta, streaming, tabla, persistencia server-side). Único toque backend: registro del flag (config pura).
- **NO ejecuta acciones.** Solo navegación no destructiva. Nada de publicar, crear tickets, cancelar runs, etc. desde el centro.
- **NO reimplementa** streaming/polling: reusa `useActiveRunsGlobal` y los polls ya existentes de `CostCapIndicator`. **NO** crea intervalos/EventSource/fetch de polling (KPI-6).
- **NO redefine** `prefers-reduced-motion` ni el focus ring (dueño: 141). **NO** modifica el Toast de 135 (F6a engancha en el boundary, no en el toast).
- **NO agrega** `@testing-library/react`/jsdom (gap estructural preexistente; el gate de componentes es tsc + ratchet + smoke).
- **Optimización futura (no acá):** que 134 publique fines de run directamente al seam para apagar el `byId` extra de F2.

---

## 9. Orden de implementación + DoD

### 9.1 Orden (por dependencia)
`F0 (reducer puro)` → `F1 (store + pub/sub)` → `F2 (captura runs + helper transición)` → `F3 (flag canónico)` → `F4 (campana + panel + wiring)` → `F5 (seam documentado)` → `F6 (wiring fuentes 135/142)`.

- F0/F1/F2 son puros y no tocan archivos calientes → primero, sin coordinar.
- F3 es backend-config aislado.
- **F4 y F6 editan archivos calientes** (`App.tsx`, `TopBar.tsx`, `PageErrorBoundary.tsx`, `CostCapIndicator.tsx`): al final, con pre-flight `git status` por archivo y STOP si hay WIP ajeno.

### 9.2 Smoke manual (DoD conductual, documentado)
1. Con flag ON: la campana aparece en la TopBar (junto al indicador de costo). Sin runs, el panel muestra `EmptyState`.
2. Lanzar un agente; al finalizar, aparece 1 evento `run` con severidad correcta y badge de no-leídos = 1.
3. Abrir el panel → badge vuelve a 0 (marcado leído). "Ver" navega a la superficie de runs.
4. Flag OFF (desde `HarnessFlagsPanel`): la campana desaparece; TopBar idéntica a hoy; sin errores en consola; sin requests `byId` de la captura (Network tab).
5. Recargar la página: los eventos recientes (≤50) y el estado leído persisten.
6. (F6a) Forzar un error de render en una página (o simularlo) → aparece evento `error` en el feed.
7. (F6b) Con un proyecto con cap configurado cerca del umbral: al cruzar `alert`, aparece UN evento `cost`; el poll siguiente NO duplica ni re-marca no-leído.

### 9.3 Definition of Done
- KPI-1..KPI-7 en verde (comandos §2), con el **output real** leído por el implementador (cero falsos verdes).
- Smoke §9.2 ejecutado y OK (casos 6-7 pueden simularse).
- Pre-flight `git status` sin WIP ajeno pisado; staging quirúrgico por paths explícitos.
- Sin regenerar `harness_defaults.env`; sin altas en `HARNESS_TEST_FILES` (no hay test backend nuevo).

---

### Resumen ejecutivo
152 crea el **Centro de Actividad**: una campana (`IconButton` + `Bell`) en la TopBar con contador de no-leídos y un feed desplegable que **unifica desde el día 1** runs (134), errores (135, wiring real en `PageErrorBoundary`) y costos (142, wiring real en `CostCapIndicator`, solo-en-transición), **reusando** la query compartida `useActiveRunsGlobal` (0 requests nuevos) y un **pub/sub extensible** donde cada fuente futura se enchufa con una línea. Es 100% frontend (idéntico en los 3 runtimes), aditivo y opt-out (flag default ON, gateando también la captura), **informativo y solo-navegación** (human-in-the-loop), con la lógica crítica en **helpers puros testeables sin DOM** y gates binarios que incluyen el ratchet de deuda UI.
