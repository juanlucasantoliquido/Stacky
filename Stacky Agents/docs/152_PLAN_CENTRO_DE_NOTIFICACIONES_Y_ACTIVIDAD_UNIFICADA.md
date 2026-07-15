# Plan 152 — Centro de notificaciones / actividad unificado

> **Estado:** PROPUESTO v1 · **Autor:** StackyArchitectaUltraEficientCode · **Fecha:** 2026-07-15
> **Serie UX/UI:** aterriza DESPUÉS de 134→(138→139→140→141→143), idealmente tras 135 y 142.
> **Depende de (reuso, no reimplementación):** 134 (infra de runs `activeRuns.ts`/`useActiveRunsGlobal` — YA existe), 139 (TopBar donde vive la campana), 140 (`EmptyState`/`Skeleton` para vacío/carga), 143 (tokens `--transition-*` + `prefers-reduced-motion` de 141), 135 (fuente de errores, pub/sub), 142 (fuente de costos, pub/sub).
> **Runtimes:** 100% frontend (presentación + reuso de la infra existente) ⇒ idéntico en Codex, Claude Code y GitHub Copilot Pro.
> **Flag:** `STACKY_NOTIFICATION_CENTER_ENABLED` — **default ON** (UI aditiva, opt-out). Ninguna de las 4 excepciones duras aplica (§4.4).
> **Backend nuevo:** NINGÚN endpoint/ruta/streaming/persistencia nuevos. El único toque backend es el registro canónico del flag (config pura, F3), gateado vía el endpoint EXISTENTE `/api/harness-flags`.

> **NOTA DE NUMERACIÓN (resuelta).** Este plan se propuso originalmente como **146**, pero ese número —y toda la franja **144–149**— ya estaba tomado en disco por una serie concurrente de confiabilidad/observabilidad de OTRA sesión (`docs/146_PLAN_FIXES_VERIFICADOS_IMPORT_LEDGER_FALLBACK_CONTRATOS.md` y hermanos, derivados de `docs/reportes/2026-07-15_AUDITORIA_LOGS_deploy_vs_dev.md`). El orquestador **renumeró este plan a 152** (y a sus hermanos UX/UI a **150 = densidad/responsive** y **151 = onboarding**), **sin tocar** la serie ajena 144–149. Todas las referencias internas ya están actualizadas a **152**. Ver §7 R9.

---

## 1. Encabezado / contexto

Hoy las señales de "qué pasó / qué está pasando" en Stacky están **dispersas y efímeras**:
- Los fines de run producen aviso de escritorio + beep + título de pestaña, pero **no dejan rastro** consultable (`executionNotifier.ts` / `tabTitle.ts` son side-effects, no un feed).
- Los errores de la UI (plan 135) serán toasts **efímeros** (se van solos).
- Los KPIs de costo (plan 142) viven en su propia vista, **sin push** cuando algo cruza un umbral.

No existe **un solo lugar** que responda "¿qué pasó mientras no miraba?". Este plan crea ese lugar: un **Centro de Actividad** client-side (campana en la TopBar + feed desplegable con no-leídos) que **agrega** las fuentes ya existentes/planeadas sin reinventar streaming ni polling, y que **degrada honestamente** si una fuente todavía no está implementada.

---

## 2. Objetivo + KPIs binarios

**Objetivo:** un centro de notificaciones **informativo** (nunca ejecutor) que acumula eventos con timestamp/tipo/severidad/leído, muestra un contador de no-leídos en la TopBar, y ofrece navegación ("ver run") a la superficie relevante — **amplificando** al operador, sin agregarle trabajo ni pasos.

**KPIs (todos BINARIOS, con comando exacto):**
- **KPI-1 — Reducer puro verde:** `npx vitest run src/services/__tests__/activityReducer.test.ts` → exit 0 (dedup por key, tope N=50, no-leídos, agrupación, mute, hydrate tolerante).
- **KPI-2 — Store singleton verde:** `npx vitest run src/services/__tests__/activityCenter.test.ts` → exit 0 (pub/sub, `markAllRead`, persistencia guardada, **degradación: fuentes ausentes ⇒ sin sección**).
- **KPI-3 — Captura de runs pura verde:** `npx vitest run src/services/__tests__/runCapture.test.ts` → exit 0 (`diffFinishedIds`).
- **KPI-4 — Tipos verdes:** `npx tsc --noEmit` (desde `frontend/`) → exit 0 (campana + panel + wiring compilan).
- **KPI-5 — Flag canónico verde:** `python -m pytest "backend/tests/test_harness_flags.py" -q` (venv del repo) → exit 0 (`test_default_known_only_for_curated` + `test_every_registry_flag_is_categorized` pasan con el flag nuevo).
- **KPI-6 — Cero polls nuevos (grep binario):** `grep -rEn "new EventSource|setInterval|refetchInterval|fetch\(" src/services/activityCenter.ts src/services/activityReducer.ts src/services/runCapture.ts src/hooks/useRunActivityCapture.ts` → **0 matches** (la única fuente de refresco es la query compartida `useActiveRunsGlobal`, reusada; `Executions.byId` on-finish no es un poll).

---

## 3. Por qué ahora / gap (evidencia por grep)

### 3.1 Evidencia de la infra YA existente que se REUSA (leída, no supuesta)

| Símbolo reusado | Archivo:línea | Qué aporta a 152 |
|---|---|---|
| `useActiveRunsGlobal()` | `frontend/src/hooks/useActiveRunsGlobal.ts:12` | Query compartida react-query de runs activos (running/preparing/queued, all_projects), refresco 5 s, `refetchIntervalInBackground:true` (`:22`). **Todos los consumidores comparten `queryKey` ⇒ UNA sola request.** |
| `ACTIVE_RUNS_QUERY_KEY`, `ACTIVE_RUNS_REFRESH_MS`, `mergeActiveRuns`, `fetchActiveRuns` | `frontend/src/services/activeRuns.ts:12,13,20,30` | Fuente única de runs; diseñada explícitamente para ser compartida por panel + TopBar + notificador (comentario `activeRuns.ts:1-8`). |
| Patrón diff prev/current + `Executions.byId` | `frontend/src/hooks/useGlobalExecutionNotifier.ts:19-43` | Detección de "run que desapareció del set activo" → confirma status final con `Executions.byId` (`:28`). 152 **replica el diff** (extraído a helper puro) sin tocar este archivo caliente. |
| `buildNotificationBody(row)` | `frontend/src/services/notifierCore.ts:52` | Cuerpo humano "proyecto · ticket" — se reusa tal cual para el texto del evento. |
| `combineOutcome`/`FinishOutcome` | `frontend/src/services/notifierCore.ts:33` | Semántica de severidad pegajosa (attention nunca lo pisa completed) — base de `severityFromRunStatus`. |
| Slot de acciones de la TopBar | `frontend/src/components/TopBar.tsx:201` (`<div className={styles.actions}>`), vecinos `<CostCapIndicator>` (`:210`) y `<StreakBadge/>` (`:211`) | Lugar EXACTO donde se inserta la campana. |
| Montaje del notificador global | `frontend/src/App.tsx:70` (`useGlobalExecutionNotifier()`), TopBar en `App.tsx:158` | Punto EXACTO donde 152 monta `useRunActivityCapture()` (hermano, 0 requests nuevos). |
| Gating de feature por flag backend | `frontend/src/App.tsx:104-107` (`fetch("/api/db-compare/health") → flag_enabled`) y endpoint EXISTENTE `HarnessFlags.list()` (`frontend/src/api/endpoints.ts:873-874`), campo `HarnessFlagView.value` (`endpoints.ts:675`) | Patrón para leer el valor efectivo del flag SIN endpoint nuevo. |
| `EmptyState` compartido | `frontend/src/components/EmptyState.tsx:1-90` (presets `executions\|packs\|tickets\|agents\|history\|generic`; props `variant/title/message/actionLabel/onAction/icon` `:12-19`) | Estado vacío del feed. **YA existe hoy** (aunque con 0 importadores; 152 es uno de sus primeros consumidores reales). |
| `lucide-react ^0.453.0` | `package.json` (verificado por plan 139 §6.2) | Icono `Bell` para la campana — sin agregar dependencia. |
| Tokens de movimiento | `theme.css` (plan 143 F2): `--transition-opacity`, `--transition-transform` | Entrada/salida barata del panel/ítems. Si 143 no aterrizó, `var(--transition-*)` es indefinido y la propiedad no se anima (degrade instantáneo, sin branch). |

### 3.2 Evidencia de AUSENCIA de un centro de notificaciones actual

- `grep -rEn "notification\|bell\|campana\|unread" frontend/src/components` → solo `RecoverExecutionButton.tsx` y `CreateChildTaskButton.tsx` (botones ajenos). **No hay campana, contador de no-leídos ni feed.** El gap es real.

### 3.3 Tabla de dependencias (estado real hoy)

| Fuente / dependencia | Plan | Estado hoy | Rol en 152 |
|---|---|---|---|
| Runs activos/finalizados | 134 | **Infra existe** (en implementación concurrente; `activeRuns.ts`/`useActiveRunsGlobal` leídos en el árbol) | Fuente **base garantizada** (F2). |
| TopBar donde va la campana | 139 | TopBar actual existe; shell v2 en papel (flag `STACKY_APP_SHELL_V2` OFF) | Se usa el slot `styles.actions` actual. La campana **no** depende de shell v2. |
| `EmptyState` / `Skeleton` | 140 | `EmptyState` **existe hoy**; `Skeleton`/`SkeletonList` en papel | Vacío con `EmptyState` (presente); carga con placeholder token-only si `Skeleton` no está. |
| Tokens `--transition-*` + reduced-motion | 143 (+141) | En papel | Se referencian por `var()`; degrade instantáneo si faltan. 152 **jamás** escribe `@media (prefers-reduced-motion)`. |
| Errores UI (Toast/ErrorBoundary) | 135 | **En papel** | Fuente **pub/sub**: 135 publicará `kind:"error"`. Ausente ⇒ sección error nunca aparece. |
| Costos / KPIs de tokens | 142 | **En papel** | Fuente **pub/sub**: 142 publicará `kind:"cost"`. Ausente ⇒ sección cost nunca aparece. |

---

## 4. Principios, guardarraíles y regla de degradación

1. **Reuso, no reinvención.** El refresco de runs es la query compartida `useActiveRunsGlobal` (0 requests nuevos: react-query dedup por `queryKey`). 152 no crea intervalos, ni EventSource, ni fetch de polling (KPI-6).
2. **Human-in-the-loop.** El centro es **informativo**. Cada notificación puede llevar UNA acción de **navegación** ("ver run" → `selectTab`). **Prohibido** ejecutar acciones destructivas, publicar, crear tickets o mutar estado desde el centro. Amplifica, no reemplaza.
3. **Cero trabajo extra al operador.** UI aditiva, opt-out. La campana aparece sola; silenciar tipos y opt-out son opcionales, nunca requeridos.
4. **No degradar performance.** Tope **N=50** eventos (cola acotada). Animación solo de props baratas (`opacity`/`transform`). Reducer/store son O(1)–O(n≤50) puros en memoria. Sin backend nuevo.
5. **Mono-operador sin auth.** No hay roles; el feed es local a la sesión del navegador (más `localStorage` acotado). No es un log auditable multi-usuario.
6. **Backward-compatible.** Todas las firmas nuevas son aditivas. Los archivos calientes (`App.tsx`, `TopBar.tsx`) reciben ediciones **aditivas de una línea**, ancladas por texto normativo (§6.F4). Con el flag OFF, la TopBar queda **idéntica** a hoy.

### 4.4 Confirmación: ninguna de las 4 excepciones duras aplica

La directiva de barrido (flags nuevas → default ON, salvo 4 excepciones reservadas para flags **destructivas / autónomas / de riesgo de seguridad / experimentales-inestables**) **no** afecta a este flag: el Centro de Actividad es UI **aditiva, informativa, sin autonomía, sin escritura destructiva, sin superficie de seguridad ni de pérdida de datos**. Por lo tanto: **default ON**.

### 4.5 REGLA DE DEGRADACIÓN HONESTA (contrato central)

> **Cada fuente se feature-detecta por PRESENCIA DE EVENTOS, no por import.** El seam es un **pub/sub** (`publishActivity`). El panel renderiza **solo** las secciones (`kind`) que tienen al menos un evento (`groupByKind` no crea bucket vacío). Consecuencia: si 135 o 142 **no** están implementados, **nadie publica** `error`/`cost`, esas secciones **nunca aparecen** — sin import de 135/142, sin dependencia dura, sin error. 152 funciona **parcial** (solo `run`) desde el día 1 y **completo** a medida que 135/142 aterricen y agreguen su línea `publishActivity(...)`.
>
> **La única fuente con acoplamiento estático es `run` (134)**, porque reusa `useActiveRunsGlobal`; esa infra **existe hoy** (leída), así que el acoplamiento está satisfecho. Si por reordenamiento 134 no estuviera, F2 no compilaría (fallo ruidoso en tsc), y F2 se pospone — el resto del plan (campana vacía + seam) sigue funcionando.
>
> **Cómo se testea (mock de fuentes ausentes):** KPI-2 incluye un test que publica **solo** eventos `run` y asegura que `groupByKind(snapshot)` **no** contiene buckets `error` ni `cost`; y otro que publica un `kind` silenciado (mute) y asegura que no entra al snapshot.

---

## 5. Glosario

| Término | Definición |
|---|---|
| **ActivityEvent** | Registro inmutable: `{ key, kind, severity, title, body?, ts, nav? }`. `key` identifica unívocamente el evento para dedup (p. ej. `run:1234`). |
| **kind** | Fuente/categoría del evento: `"run" \| "error" \| "cost"` (extensible sin romper: buckets desconocidos se renderizan bajo su nombre). |
| **severity** | `"info" \| "success" \| "attention" \| "error"` — solo estética (color/icono), no comportamiento. |
| **nav** | Intención de navegación opcional `{ tab: string; executionId?: number }`. Se ejecuta vía `selectTab` del `App`. **Nunca** destructiva. |
| **no-leído (unread)** | Evento con `ts > lastReadAt`. Abrir el panel setea `lastReadAt = Date.now()` (marca todo leído). |
| **tope N** | Cap de la cola = **50** eventos (`ACTIVITY_CAP`). Al llegar al tope se descarta el más viejo. |
| **seam / pub-sub** | `publishActivity(evt)` (fuentes escriben) + `subscribeActivity(cb)` (UI lee). Único punto de acoplamiento entre 152 y 135/142. |
| **mute** | Silenciar un `kind`: eventos de ese kind se descartan en `publishActivity` (no se guardan, no cuentan). Config del operador por UI (opcional), persistida en `localStorage`. |

---

## 6. Fases F0..F5

> **Pre-flight OBLIGATORIO por fase que toque archivo caliente** (`App.tsx`, `TopBar.tsx`): `git status -- "<ruta>"`. Si hay WIP ajeno (hoy 134/135/139 los editan), **STOP y avisar al orquestador** antes de editar. Staging quirúrgico por path explícito. **El implementador NO commitea** (lo hace el orquestador).
>
> **Comandos vitest/tsc** se corren desde `Stacky Agents/frontend/`. **pytest** con el venv del repo, **por archivo**.

---

### F0 — Contrato + reducer PURO (tests primero)

**Objetivo (1 frase):** definir tipos y la lógica pura de acumulación (dedup, tope, no-leídos, agrupación, mute, hydrate) — el corazón testeable sin DOM. **Valor:** toda la corrección vive acá y se blinda con tests puros (no hay `@testing-library/react` ni jsdom en el repo — verificado; los helpers no tocan DOM).

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
export function severityFromRunStatus(status: string): Severity;               // reusa semántica de combineOutcome
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
  for (const e of events) (out[e.kind] ??= []).push(e);       // FUENTE AUSENTE: kind sin eventos ⇒ nunca crea bucket
  return out;
}
export function severityFromRunStatus(status) {
  if (status === "error") return "error";
  if (status === "needs_review") return "attention";
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
6. `groupByKind` con eventos solo `run` → **sin** claves `error`/`cost` (degradación).
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

**Tests (`activityCenter.test.ts`) — usan `__resetActivityForTests()` en `beforeEach`:**
1. `publishActivity` + `getActivitySnapshot` refleja el evento; subscriber es llamado 1 vez.
2. `unsubscribe` deja de recibir notificaciones.
3. `getActivitySnapshot` estable: sin publish entre dos llamadas → **misma referencia** (`===`).
4. `markActivityRead` → `unreadCount(getActivitySnapshot()) === 0`.
5. Dedup end-to-end: publicar `run:1` dos veces → snapshot con 1 solo evento.
6. Tope: publicar 60 eventos → snapshot con 50.
7. **Degradación (mock de fuentes ausentes):** publicar solo `kind:"run"` → `groupByKind` sin `error`/`cost`.
8. **Mute:** `setActivityMuted("error", true)` y luego `publishActivity({kind:"error"...})` → snapshot NO contiene el evento.
9. Persistencia guardada: con `localStorage` disponible, tras publish el `safeStorage` tiene JSON válido; con `localStorage` forzado a throw (stub), `publishActivity` no rompe.

**Comando:** `npx vitest run src/services/__tests__/activityCenter.test.ts` — **criterio: exit 0.**
**Flag:** n/a. **Runtime:** idéntico. **Trabajo del operador:** ninguno.

---

### F2 — Captura de runs (reuso de la query compartida, 0 requests nuevos)

**Objetivo:** poblar la categoría `run` reusando `useActiveRunsGlobal` (misma `queryKey` ⇒ 0 requests nuevos) y confirmando el status final on-finish. **Valor:** el feed tiene contenido real desde el día 1 sin tocar archivos calientes ni agregar polling.

**Archivos:**
- NUEVO `frontend/src/services/runCapture.ts` (lógica pura del diff)
- NUEVO `frontend/src/services/__tests__/runCapture.test.ts`
- NUEVO `frontend/src/hooks/useRunActivityCapture.ts` (wiring react-query, sin lógica testeable-crítica)

**Símbolos EXACTOS:**
```ts
// runCapture.ts
export function diffFinishedIds(prev: Set<number> | null, current: Set<number>): number[];
// devuelve ids que estaban en prev y ya NO están en current (finalizaron/desaparecieron)

// useRunActivityCapture.ts
export function useRunActivityCapture(): void;  // hook sin retorno; se monta una vez en App
```

**Pseudocódigo `useRunActivityCapture` (replica el patrón de `useGlobalExecutionNotifier.ts:19-43`, SIN editar ese archivo):**
```ts
export function useRunActivityCapture() {
  const activeQ = useActiveRunsGlobal();               // MISMA query compartida ⇒ 0 requests nuevos
  const prev = useRef<Set<number> | null>(null);
  useEffect(() => {
    if (activeQ.data == null) return;                  // sin snapshot (carga/error): no comparar
    const current = new Set(activeQ.data.map(e => e.id));
    const finished = diffFinishedIds(prev.current, current);
    prev.current = current;                            // PRIMER snapshot: prev era null ⇒ diff = [] (no falsos positivos)
    for (const id of finished) {
      const key = `run:${id}`;
      // EVENTO DUPLICADO / doble-emisión con 134: si ya está en el store, NO re-consultamos byId
      if (getActivitySnapshot().events.some(e => e.key === key)) continue;
      void Executions.byId(id).then(row => {
        publishActivity({
          key, kind: "run",
          severity: severityFromRunStatus(String(row.status || "completed")),
          title: `Agente ${row.agent_type || "agente"} — ${row.status}`,
          body: buildNotificationBody(row),           // reuso notifierCore.ts:52
          ts: Date.now(),
          nav: { tab: "team", executionId: row.id },  // navegación NO destructiva
        });
      }).catch(() => { /* byId falló: se ignora, no se inventa evento */ });
    }
  }, [activeQ.data]);
}
```

**Casos borde cubiertos:** primer snapshot (`prev=null` ⇒ sin eventos), sin cambios (diff vacío), varios fines simultáneos (loop), evento duplicado (guard por key + store dedup), `byId` con error (catch silencioso, no inventa evento), cola llena (el store recorta).

**Tests puros (`runCapture.test.ts`):**
1. `diffFinishedIds(null, {1,2})` → `[]` (primer snapshot).
2. `diffFinishedIds({1,2}, {2})` → `[1]`.
3. `diffFinishedIds({1,2,3}, {}))` → `[1,2,3]`.
4. `diffFinishedIds({1}, {1,2})` → `[]` (aparecer no es finalizar).
5. `diffFinishedIds({1}, {1})` → `[]` (sin cambios).

**Comando:** `npx vitest run src/services/__tests__/runCapture.test.ts` — **criterio: exit 0.**
**Flag:** n/a (la captura corre siempre; el gating es de la UI, F4). **Runtime:** reusa el polling por intervalo de `activeRuns.ts` (no SSE) ⇒ idéntico en los 3 runtimes; **no hay dependencia de SSE que degradar**. **Trabajo del operador:** ninguno.

> **Nota de costo (declarada):** on-finish, `useRunActivityCapture` puede disparar un `Executions.byId` que `useGlobalExecutionNotifier` (134) también dispara. Es **1 request por run finalizado** (no un poll), acotado por el nº de runs concurrentes, y **solo** cuando `run:${id}` no está ya en el store. Se elige este costo mínimo para **no editar** el archivo caliente `useGlobalExecutionNotifier.ts`. Optimización futura (fuera de scope): que 134 publique al seam y F2 se apague — ver §8.

---

### F3 — Flag canónico `STACKY_NOTIFICATION_CENTER_ENABLED` (default ON)

**Objetivo:** registrar el flag por la vía canónica para que el operador pueda opt-out desde `HarnessFlagsPanel`, gateando la UI vía el endpoint EXISTENTE. **Valor:** control por UI sin endpoint nuevo.

**Archivos (config pura, único toque backend):**
- `backend/services/harness_flags.py`:
  - Agregar `FlagSpec` a `FLAG_REGISTRY` (tupla en `harness_flags.py:295`), tipo `bool`, `default=True`, `env_only=False`, con `label`/`description`/`plain_help` (`what/on_effect/off_effect/example`).
  - Agregar la key `"STACKY_NOTIFICATION_CENTER_ENABLED"` a `_CATEGORY_KEYS` (`harness_flags.py:114`) bajo la categoría **`capacidades_optin`** (features opt-in; verificar el id exacto por grep — si no fuera `capacidades_optin`, usar la categoría de experiencia/UI existente más cercana). *(Sin esto rompe `test_every_registry_flag_is_categorized`, ver `harness_flags.py:293-295`.)*
- `backend/tests/test_harness_flags.py`:
  - Agregar la key a `_CURATED_DEFAULTS_ON` (set en `test_harness_flags.py:467`). *(Sin esto rompe `test_default_known_only_for_curated`; gotcha: `default=True` fuera de la curada rompe el ratchet.)*
- `backend/config.py`:
  - Alta del default efectivo `"true"` (env_only=False exige alta en `config.py`; el default runtime vive acá, no solo en `FlagSpec`).
- **NO** regenerar `deployment/.../harness_defaults.env` (política §3.11 del plan 127; drift preexistente conocido, no se toca).

**Gating en el frontend (parte de F4, se describe acá por dependencia):** en `App.tsx`, junto al patrón `dbCompareEnabled` (`App.tsx:104-107`), leer el valor efectivo vía el endpoint existente:
```ts
const [notifEnabled, setNotifEnabled] = useState(true);   // FAIL-OPEN: default ON aunque el flag no esté en la respuesta
useEffect(() => {
  HarnessFlags.list()
    .then(r => {
      const f = r.flags.find(x => x.key === "STACKY_NOTIFICATION_CENTER_ENABLED");
      setNotifEnabled(f ? f.value === true : true);        // ausente ⇒ true (aditivo)
    })
    .catch(() => setNotifEnabled(true));                   // error ⇒ true (no romper UI aditiva)
}, []);
```

**Tests:** `python -m pytest "backend/tests/test_harness_flags.py" -q` (venv del repo, por archivo).
**Comando/criterio binario:** exit 0 (en particular `test_default_known_only_for_curated` y `test_every_registry_flag_is_categorized`).
**Flag:** este ES el flag, default **ON**. **Runtime:** el flag se lee igual en los 3 runtimes (config backend + endpoint compartido). **Trabajo del operador:** ninguno (default ON; opt-out opcional desde el panel de flags).

---

### F4 — Campana + panel + wiring (UI)

**Objetivo:** la campana con contador de no-leídos en la TopBar y el panel-feed desplegable con estados vacío/carga (140), micro-interacciones (143) y navegación no destructiva. **Valor:** la superficie visible del centro.

**Archivos NUEVOS:**
- `frontend/src/components/NotificationBell.tsx` + `NotificationBell.module.css`
- `frontend/src/components/NotificationPanel.tsx` + `NotificationPanel.module.css`
- NUEVO `frontend/src/hooks/useActivityCenter.ts`

**Archivos CALIENTES editados (aditivo, anclado por texto normativo; pre-flight `git status` OBLIGATORIO):**
- `frontend/src/App.tsx`:
  - Junto a `useGlobalExecutionNotifier();` (`App.tsx:70`) agregar `useRunActivityCapture();` y el gating `notifEnabled` (F3).
  - En `<TopBar onGoToTeam={...} />` (`App.tsx:158`) pasar props aditivas: `notificationsEnabled={notifEnabled}` y `onActivityNavigate={(nav) => selectTab(nav.tab)}`.
- `frontend/src/components/TopBar.tsx`:
  - Firma: agregar props opcionales `notificationsEnabled?: boolean` y `onActivityNavigate?: (nav: { tab: string; executionId?: number }) => void` a `TopBarProps` (`TopBar.tsx:13`).
  - Render: dentro de `<div className={styles.actions}>` (`TopBar.tsx:201`), **antes** de `<CostCapIndicator/>` (`:210`), insertar:
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

**`NotificationBell.tsx`:**
- Icono `Bell` de `lucide-react` (sin dep nueva). **NO** depende de la primitiva `IconButton` (139): usa un `<button>` propio token-only para no acoplarse a un plan en papel (degrade honesto).
- Badge de no-leídos: muestra `unread` (o `"9+"` si `unread > 9`); oculto si `unread === 0`.
- Click → toggle del panel; **al ABRIR** llama `markRead()`.
- `aria-label="Notificaciones"`, `aria-expanded`, foco visible (reusa `--focus-ring` de 141 si existe).

**`NotificationPanel.tsx`:**
- Lista `groups` en orden `run` → `error` → `cost` → (otros). Cada sección solo si tiene eventos (§4.5).
- **VACÍO** (0 eventos totales): `<EmptyState variant="history" .../>` (componente EXISTE, `EmptyState.tsx`). Regla vacío-vs-error de 140: EmptyState solo cuando no hay error de fuente base.
- **CARGA** (primer snapshot de runs pendiente y 0 eventos): placeholder token-only (o `Skeleton` de 138 **si existe**; si no, un `<div>` con `--space-*`). No agrega requests/timers.
- **Micro-interacciones (143):** panel y ítems con `transition: var(--transition-opacity), var(--transition-transform);` (entrada/salida). Si los tokens no existen (143 no aterrizó), la propiedad no anima — degrade instantáneo, **sin branch**. **152 NUNCA escribe `@media (prefers-reduced-motion)`** (dueño único: 141 F5).
- Cada ítem: `title`, `body`, hora relativa, color/icono por `severity`, y botón **"Ver"** → `onNavigate(item.nav)`. **Solo navegación**; prohibido cualquier acción destructiva/de escritura.
- (Opcional) engranaje → mute por `kind` (`setActivityMuted`), persistido; es config por UI, no requerida.

**Tests:** los componentes React **no** son testeables sin `@testing-library/react`/jsdom (ausentes en `package.json` — gap estructural verificado). Por lo tanto:
- **Criterio binario de F4:** `npx tsc --noEmit` (desde `frontend/`) → **exit 0**.
- **Verificación conductual:** smoke manual documentado (§9.2), no bloqueante para el gate binario pero requerido para DoD.

**Comando:** `npx tsc --noEmit` — **criterio: exit 0.**
**Flag:** gateado por `notificationsEnabled` (F3); OFF ⇒ TopBar idéntica a hoy. **Runtime:** 100% presentación, idéntico en los 3. **Trabajo del operador:** ninguno.

---

### F5 — Seam para fuentes 135/142 + degradación testeada + mute

**Objetivo:** dejar documentado y testeado el contrato pub/sub para que 135 (errores) y 142 (costos) se enchufen con UNA línea cuando aterricen, sin que 152 dependa de ellos. **Valor:** el centro crece solo, sin re-tocar 152.

**Archivos:**
- (Doc/contrato) esta sección + comentario JSDoc en `activityCenter.ts:publishActivity`.
- Extensión de tests en `activityCenter.test.ts` (ya listada en F1 casos 7-8): degradación (solo `run` ⇒ sin `error`/`cost`) y mute.

**Contrato para 135 (cuando implemente su Toast/ErrorBoundary, F5 de 135):** agregar en el punto donde hoy mostraría el toast de error:
```ts
publishActivity({ key: `error:${Date.now()}:${slug}`, kind: "error", severity: "error",
                  title: "Error en la UI", body: message, ts: Date.now(),
                  nav: surface ? { tab: surface } : undefined });
```
**Contrato para 142 (cuando implemente KPIs, al cruzar umbral/cap):**
```ts
publishActivity({ key: `cost:${projectName}:${bucket}`, kind: "cost", severity: "attention",
                  title: "Costo cruzó umbral", body: `${projectName}: ${usd} USD`, ts: Date.now(),
                  nav: { tab: "costs" } });
```
**Degradación (ya en §4.5):** sin esas líneas, no hay eventos `error`/`cost`, y el panel no muestra esas secciones. **Nada que importar, nada que romper.**

**Tests:** cubiertos por `activityCenter.test.ts` (casos 7-8). **Comando:** `npx vitest run src/services/__tests__/activityCenter.test.ts` — **criterio: exit 0.**
**Flag:** heredado de F3. **Runtime:** idéntico. **Trabajo del operador:** mute opcional por UI; nada requerido.

---

## 7. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | **Acoplamiento con services que la sesión 134 edita AHORA** (`useGlobalExecutionNotifier.ts`, `activeRuns.ts` untracked/modified). | 152 **no edita** esos archivos: reusa por import (`useActiveRunsGlobal`, `buildNotificationBody`) y replica el diff en `runCapture.ts`. Consumo por NOMBRE; si un export faltara, tsc falla ruidoso (contrato defensivo). |
| R2 | **Doble `byId` / doble evento** con el notificador de 134. | Dedup por `key=run:${id}` en el store + guard "si ya está en el store, no consultar byId". Doble emisión es **inofensiva** (dedup) y el byS extra es acotado (§F2 nota de costo). |
| R3 | **Ediciones a `App.tsx`/`TopBar.tsx` chocan con 134/135/139.** | Ediciones **aditivas de una línea** ancladas a texto normativo estable (`useGlobalExecutionNotifier();`, `<div className={styles.actions}>`). Pre-flight `git status` por archivo; WIP ajeno ⇒ STOP. |
| R4 | **135/142 no implementados al aterrizar 152.** | Degradación honesta §4.5: pub/sub data-driven, secciones ausentes sin import ni error; testeado (KPI-2 caso 7). |
| R5 | **`Skeleton`/`IconButton` (138/139) o tokens `--transition-*` (143) no existen aún.** | La campana usa `<button>` propio (no `IconButton`); la carga usa placeholder token-only (no `Skeleton` duro); los `var(--transition-*)` degradan a sin-animación. `EmptyState` sí existe hoy (verificado) y se usa. |
| R6 | **`useSyncExternalStore` re-render infinito** por snapshot inestable. | `getActivitySnapshot` devuelve **referencia estable** entre cambios (test KPI-2 caso 3). |
| R7 | **Crecimiento sin límite / localStorage lleno.** | Tope duro `ACTIVITY_CAP=50` (testeado); `safeStorage` con try/catch tolerante a cuota. |
| R8 | **`localStorage` corrupto** rompe el arranque. | `hydrateState` tolerante (JSON inválido → `emptyState()`, testeado). |
| R9 | **Colisión de numeración** (propuesto como 146; franja 144–149 ocupada por una serie concurrente ajena). | RESUELTO: el orquestador renumeró este plan a **152** (hermanos UX/UI a 150/151), sin tocar la serie ajena 144–149. Referencias internas actualizadas. |

---

## 8. Fuera de scope

- **NO es un log auditable.** Es un feed efímero de conveniencia, local al navegador, acotado a 50 eventos. La telemetría/auditoría real es backend (métricas/costos), fuera de este plan.
- **NO agrega backend** (endpoint, ruta, streaming, tabla, persistencia server-side). Único toque backend: registro del flag (config pura).
- **NO ejecuta acciones.** Solo navegación no destructiva. Nada de publicar, crear tickets, cancelar runs, etc. desde el centro.
- **NO reimplementa** streaming/polling: reusa `useActiveRunsGlobal`. **NO** crea intervalos/EventSource/fetch de polling (KPI-6).
- **NO redefine** `prefers-reduced-motion` ni el focus ring (dueño: 141). **NO** crea un Toast en `components/ui/` (contrato externo de 135).
- **Optimización futura (no acá):** que 134 publique fines de run directamente al seam para apagar el `byId` extra de F2.
- **NO** implementa las fuentes 135/142; solo deja el seam para que se enchufen.

---

## 9. Orden de implementación + DoD

### 9.1 Orden (por dependencia)
`F0 (reducer puro)` → `F1 (store + pub/sub)` → `F2 (captura runs)` → `F3 (flag canónico)` → `F4 (campana + panel + wiring)` → `F5 (seam 135/142 + degradación testeada)`.

- F0/F1/F2 son puros/backend-agnósticos y no tocan archivos calientes → se pueden hacer primero sin coordinar.
- F3 es backend-config aislado.
- **F4 es la única fase que edita archivos calientes** (`App.tsx`, `TopBar.tsx`): hacerla al final, con pre-flight `git status` por archivo y coordinación si hay WIP ajeno.

### 9.2 Smoke manual (DoD conductual de F4, documentado)
1. Con flag ON: la campana aparece en la TopBar (junto al indicador de costo). Sin runs, el panel muestra `EmptyState`.
2. Lanzar un agente; al finalizar, aparece 1 evento `run` con severidad correcta y badge de no-leídos = 1.
3. Abrir el panel → badge vuelve a 0 (marcado leído). "Ver" navega a la superficie de runs.
4. Flag OFF (desde `HarnessFlagsPanel`): la campana desaparece; TopBar idéntica a hoy; sin errores en consola.
5. Recargar la página: los eventos recientes (≤50) y el estado leído persisten.

### 9.3 Definition of Done
- KPI-1..KPI-6 en verde (comandos §2), con el **output real** leído por el implementador (cero falsos verdes).
- Smoke §9.2 ejecutado y OK.
- Pre-flight `git status` sin WIP ajeno pisado; staging quirúrgico por paths explícitos.
- Grep de degradación: publicar solo `run` no genera secciones `error`/`cost` (KPI-2 caso 7 verde).
- Sin regenerar `harness_defaults.env`.

---

### Resumen ejecutivo
152 crea el **Centro de Actividad**: una campana en la TopBar con contador de no-leídos y un feed desplegable que **agrega** runs (134), errores (135) y costos (142) en un solo lugar, **reusando** la query compartida `useActiveRunsGlobal` (0 requests nuevos) y un **pub/sub data-driven** que hace que las fuentes aún no implementadas simplemente **no aparezcan** (degradación honesta, testeada). Es 100% frontend (idéntico en los 3 runtimes), aditivo y opt-out (default ON), **informativo y solo-navegación** (human-in-the-loop), con la lógica crítica en **helpers puros testeables sin DOM**.
