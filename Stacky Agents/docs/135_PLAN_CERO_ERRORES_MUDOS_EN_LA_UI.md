# Plan 135 — Cero errores mudos en la UI: distinguir error de vacío, contener crashes y un canal único de feedback

**Estado:** PROPUESTO v1 (2026-07-13)
**Origen:** auditoría UX multi-lente 2026-07-13, pedido del operador de mejorar UX sin romper nada; precedente real: el 500 mudo del revisor de PRs (2026-07-11) que costó una sesión de debugging.
**Alcance:** 100% frontend. Cero backend nuevo, cero endpoint nuevo, cero store nuevo, cero migración.
**Flag:** NO lleva flag (decisión de diseño justificada en §3.1, por fase).
**Ortogonal a:** Planes 132/134/136, que se escriben/implementan EN PARALELO y comparten archivos editados (§3.2 declara las zonas exactas de líneas para que no se pisen; staging quirúrgico obligatorio).

> Este documento está redactado para que un MODELO MENOR (Haiku, Codex CLI o GitHub
> Copilot Pro) lo implemente SIN inferir nada. Rutas, símbolos, copys y comandos son
> LITERALES. Prohibido desviarse de los nombres exactos, prohibido "mejorar" el alcance,
> prohibido tocar archivos no listados. Todo lo ambiguo ya fue decidido acá.
> Todas las rutas de código son relativas a `Stacky Agents/` salvo indicación contraria.

---

## 1. Objetivo + KPIs binarios

Hoy, cuando algo falla en el frontend de Stacky, el operador ve **lo mismo que si no hubiera datos**: listas vacías, selectores vacíos, paneles que desaparecen, tabs que se esfuman, "guardados" que no guardaron. La auditoría 2026-07-13 cuantificó el patrón: de ~60 handlers `.catch()` en `frontend/src/`, **~19 tragan el error por completo** (`.catch(() => {})`) y **~20 lo disfrazan de "no hay datos"** (`.catch(() => setX([]))`). El precedente que motivó este plan es real y costó una sesión entera: el 500 mudo del revisor de PRs (2026-07-11, bug `ado_client` con nombre de proyecto — el catch convertía el 500 en "no hay acciones").

Este plan convierte cada error mudo en una señal **visible, accionable y con reintento de 1 click**, en 6 frentes (GAP 1..6), sin cambiar ningún flujo feliz.

**KPI / impacto esperado (binarios):**

- **KPI-1 (error ≠ vacío):** con el backend devolviendo 500 en `/api/tickets/hierarchy` (o caído), el board en vista árbol muestra `LoadErrorState` con botón **Reintentar** y **NO** el copy "No hay tickets. Hacé clic en «Sincronizar ADO»". Verificación manual F1 paso a paso + criterio binario.
- **KPI-2 (cancelar nunca falla en silencio):** con `Executions.cancel` rechazando, el panel de ejecuciones activas muestra inline "No se pudo cancelar #<id>: <msg>" con **Reintentar**, y el panel NO desaparece. Test F3 (written-ready) + verificación manual.
- **KPI-3 (cero pantalla blanca):** un `throw` en el render de cualquiera de las 13 páginas muestra "Esta pestaña falló al renderizar" + mensaje + **Reintentar**, con TopBar/nav/HealthBanner/CodexConsoleDock/ActiveRunsPanel vivos; cambiar de tab recupera. Test F4 (written-ready) + verificación manual con throw inyectado temporal.
- **KPI-4 (éxito nunca por el canal de error):** "Guardado. Requiere reiniciar…" deja de renderizarse en rojo como error: en `HarnessFlagsPanel` sale como Toast `warning` y en `FlagGateBanner` como aviso warning separado del canal de error. Tests puros F0 de `classifyFlagUpdateOutcome` (ejecutables hoy) + inspección binaria.
- **KPI-5 (tabs no desaparecen por un parpadeo de red):** un fallo transitorio del health-check al arrancar NO oculta Migrador/DevOps si un retry (≤2, con backoff) llega a JSON válido con `flag_enabled=true`; y un JSON válido con `flag_enabled=false` los sigue ocultando (la desactivación real de la flag funciona igual). Tests puros F0 de `probeFlagHealth`/`nextEnabledState` (ejecutables hoy).
- **KPI-6 (gate global):** `npx tsc --noEmit` exit 0 y los 3 archivos de tests puros nuevos (F0) verdes **ejecutables hoy** con `npx vitest run <archivo>`.

## 2. Por qué ahora / gap que cierra (evidencia verificada en HEAD, 2026-07-13)

Los 6 gaps, con anclas re-verificadas archivo por archivo:

**GAP 1 — Errores de carga disfrazados de "no hay datos" (el central; el 500 mudo es sistémico):**
- `frontend/src/pages/TicketBoard.tsx:741-747` — la query principal de tickets no destructura `isError`/`error`; si falla, `data` queda `undefined`. `:749-755` — ídem la query de jerarquía. `:1011-1015` — el MISMO render `(!isHierarchyLoading && filteredEpics.length === 0 && filteredOrphans.length === 0)` → "No hay tickets. Hacé clic en «Sincronizar ADO»" se muestra para vacío real Y para query fallida → el operador sincroniza en loop.
- `frontend/src/components/CommandPalette.tsx:65` — `.catch(() => setTickets([]))`; ídem `:71` agents, `:74` packs, `:80` projects.
- `frontend/src/components/AgentLaunchModal.tsx:113` — `Tickets.list(...).catch(() => {})`: selector de tickets vacío sin explicación.
- `frontend/src/components/ChatDrawer.tsx:175` — `.catch(() => {})` en la carga de tickets del chat.
- `frontend/src/components/devops/PrReviewerSection.tsx:116` — `.catch(() => setActions([]))`: exactamente la superficie donde YA hubo un 500 mudo real (2026-07-11). Nota: la carga de la LISTA de PRs ya muestra error (`:203` "No se pudieron cargar las PRs…") — el patrón correcto convive con el mudo en el mismo archivo.
- `frontend/src/components/ReplayPlayer.tsx:42` — `.catch(() => setEvents([]))` → "Esta ejecución no tiene timeline de eventos registrado" (`:124-126`) también para un 500.
- Patrón de la casa a seguir: `frontend/src/components/EmptyState.tsx` (presets + title/message/action, `:21-61` y `:63-90`).

**GAP 2 — Cancelar una ejecución puede fallar en silencio y dejar un run zombie sin señal:**
- `frontend/src/components/ActiveRunsPanel.tsx:69-77` — `cancelMutation` solo define `onSettled`; sin `onError` ni render de error. `:63-67` — la query `active-global` tampoco destructura error; `:79-80` — `runs = data ?? []` y `if (runs.length === 0) return null`: si la PRIMERA carga falla, el panel no aparece aunque haya runs reales. `:31-36` — el comentario del propio panel dice que existe para cancelar runs colgados: su única acción no reporta fallos.
- `frontend/src/components/CodexConsoleDock.tsx:179` — `void Executions.cancel(executionId).catch(() => {})` seguido de `setExecution(null)` en `:181`: cierra la consola aunque el cancel haya fallado (precedente real: sesiones CLI zombie de 1800s).
- Precisión técnica verificada (corrige la hipótesis inicial de la auditoría): con react-query v5 (`package.json:13`, `@tanstack/react-query ^5.59.0`), un error de **refetch** NO borra `data` — se conserva el último resultado exitoso. O sea: el panel solo "desaparece" si la carga INICIAL falla; ante fallos posteriores muestra datos stale **sin ninguna señal**. Ambas cosas se resuelven en F3 sin `placeholderData` (que en v5 aplica a cambios de queryKey, no a errores).

**GAP 3 — Cero ErrorBoundary a nivel página: un throw en render de cualquiera de los 13 tabs = pantalla blanca total:**
- `frontend/src/main.tsx:12` — `render(<App/>)` sin boundary. `frontend/src/App.tsx:241-253` — las 13 páginas se montan crudas.
- `frontend/src/components/TicketGraphView.jsx:244` — `NodeErrorBoundary` existe (clase, `getDerivedStateFromError` + fallback con mensaje, `:244-282`) pero solo envuelve nodos del grafo: el patrón de la casa ya existe, se copia a nivel página.

**GAP 4 — 3 toasts caseros duplicados y "Guardado OK" viajando por el canal visual de ERROR:**
- `frontend/src/components/RecoverExecutionButton.tsx:50-67` — `function Toast` local completa con variantes `success/warning/error` (tipos `:41-48`; CSS `:159-226` de `RecoverExecutionButton.module.css`, `position: fixed; bottom: 24px; right: 24px`). Es el patrón EJEMPLAR: se extrae.
- `frontend/src/components/CreateChildTaskButton.tsx:63` — segundo toast local `{ ok, message }` (render `:365-374`). `frontend/src/components/PipelineTriggerCard.tsx:63-66` — tercero (`showToast`), con colores inline `:151-159`.
- `frontend/src/components/HarnessFlagsPanel.tsx:512` — `setApiError("Guardado. Requiere reiniciar el backend: …")`: un ÉXITO renderizado por el canal de error (`:682`, `styles.errorText`). `frontend/src/components/devops/FlagGateBanner.tsx:41-43` — mismo antipatrón; con `ok` + `restart_required_keys` dispara `onEnabled()` en `:36` Y muestra "error" a la vez.
- Nota: en `EpicFromBriefModal.tsx` y otros hay WIP ajeno sin commitear — NO se tocan (fuera de las superficies listadas).

**GAP 5 — Los tabs Migrador y DevOps desaparecen en silencio si su health-check falla UNA vez:**
- `frontend/src/App.tsx:86-89` — `fetch('/api/migrator/health').then(r=>r.json())….catch(()=>setMigradorEnabled(false))`; `:91-94` — ídem DevOps. `:137-138` — `else if (tab==='migrador' && !migradorEnabled) selectTab('team')` / ídem devops: expulsión sin mensaje. `:82-95` — corre UNA vez (`[]` deps), sin retry: un backend que tarda en levantar o un parpadeo de red = tab invisible toda la sesión.

**GAP 6 — Guardados que fallan en silencio: el operador cree que guardó y no guardó:**
- `frontend/src/components/AgentConfigModal.tsx:88-90` — `catch { // ignore -- changes still applied locally }` (engañoso: al reabrir, el `useEffect` de `:43-51` recarga del server y los cambios desaparecen). Nota: el error de CARGA sí está manejado (`fetchError`, `:36` y `:46-49`) — el mudo es solo el de guardado.
- `frontend/src/components/EditProjectModal.tsx:118-126` — `saveWorkflow` con `catch { /* ignore */ }` (`:124`).
- Contraste (patrón a copiar): `frontend/src/components/ClientProfileEditor.tsx:602-630` — `onSave` con `setSaveError` visible (`:617`, `:626`) y `setSaveNotice` para éxito (`:619`).

## 3. Principios y guardarraíles (no negociables)

1. **Paridad 3 runtimes** (Codex CLI, Claude Code CLI, GitHub Copilot Pro): TODO este plan es UI sobre las APIs existentes de `Executions`/tickets/config, runtime-agnóstica. Ninguna fase mira el runtime, con una única excepción documentada: el guard de cierre del dock (F3) aplica solo al camino que HOY ya es exclusivo de runtimes interactivos (`isInteractiveRun`, `CodexConsoleDock.tsx:76,178`); para `github_copilot`/`mock` el cierre queda byte-idéntico. Ver §5.
2. **Cero trabajo extra del operador:** todo es invisible/automático; cero config nueva, cero flag que activar, cero paso manual.
3. **Human-in-the-loop:** este plan solo AGREGA superficie de errores. Nada se auto-reintenta sin click: **el retry SIEMPRE es un botón** (el retry interno del health-check F6 no es una acción de negocio — es la misma carga de arranque que hoy ya ocurre, con 2 intentos más ante fallo de red; no ejecuta nada en nombre del operador).
4. **Mono-operador sin auth real:** sin RBAC, sin permisos.
5. **No degradar:** no cambiar flujos felices, no tocar lógica de negocio; los estados de éxito existentes quedan **byte-idénticos** (única excepción declarada y pedida: el canal visual de los 2 "Guardado-como-error" del GAP 4, y la posición/estética unificada de los 3 toasts, ver F5).
6. **Reusar, no reinventar:** `EmptyState` (patrón de layout), `NodeErrorBoundary` (patrón de boundary), el Toast de `RecoverExecutionButton` (patrón de toast), `ClientProfileEditor` (patrón de save-error), `errMsg` de `PrReviewerSection` (canal de error ya existente). Prohibido agregar librerías: `package.json` no se toca (nada de react-toastify ni react-error-boundary ni ninguna otra dependencia nueva).

### 3.1 Decisión de diseño: SIN flag de harness (justificación explícita, precedente plan 132 §3.1)

Ninguna fase lleva flag `STACKY_*`. Cada fase cumple los tres criterios del precedente:
- **Puramente aditiva/correctiva:** solo agrega renders de error donde hoy hay silencio, o corrige el canal visual de un éxito mal rotulado. Ningún flujo feliz cambia.
- **Reversible con revert:** cero estado persistido, cero backend, cero datos; el kill-switch es `git revert` del commit de la fase.
- **Cero backend / cero datos:** no escribe nada, no llama endpoints nuevos.

Un flag acá agregaría trabajo al operador (activarlo) y superficie de test/config sin mitigar ningún riesgo real — violaría el principio 2. Caso a caso está declarado en la línea "Flag" de cada fase. El único cambio de COMPORTAMIENTO (no solo de render) es F6 (retry+sticky del health-check), y su fallback ante backend sano es byte-idéntico al actual (1 fetch, mismo veredicto), por lo que tampoco amerita flag.

### 3.2 Ortogonalidad con planes 132/134/136 (staging quirúrgico obligatorio)

Este plan comparte ARCHIVOS EDITADOS con planes hermanos paralelos. Las zonas de líneas están diseñadas para NO pisarse:

| Archivo | Zona de ESTE plan (135) | Zona del plan hermano |
|---|---|---|
| `ActiveRunsPanel.tsx` | destructure de la query (`:63`), bloque nuevo DESPUÉS de `</ul>` (`:159`), 1 import | 132: botón "Ver consola" DENTRO del map (`:137-138`) + import lucide `:2` + hook tras `:49`; 134: rotulado de las filas |
| `ActiveRunsPanel.module.css` | append de `.staleNotice`/`.cancelError*` al FINAL | 132: cambia grid `:116` + append `.consoleBtn` al final (merge trivial de dos appends) |
| `ActiveRunsPanel.test.tsx` | tests nuevos AGREGADOS AL FINAL del `describe`; NO editar `beforeEach` ni tests existentes | 132: mock del store + 3 tests propios |
| `App.tsx` | efecto `:82-95` (F6) + wrap del bloque `:241-253` (F4) + 2 imports | 134: notificaciones/título/badges (otras zonas); 136: guards de UI |
| `EditProjectModal.tsx` | estado junto a `:57`, cuerpo de `saveWorkflow` `:118-126`, render junto a `:706-709`, append CSS | 136: higiene de cambio de proyecto / otros guards |

Reglas duras para el implementador: (a) commitear con **pathspec explícito** (`git commit -- <archivos>`), NUNCA `git add -A` (working tree con WIP ajeno); (b) si al editar una zona el contenido no coincide porque un plan hermano ya aterrizó, re-anclar por el TEXTO citado (no por número de línea) y NO tocar las líneas del hermano; (c) los archivos NUEVOS de este plan no colisionan con nadie (nombres propios: `LoadErrorState`, `PageErrorBoundary`, `Toast`, `utils/loadError`, `utils/flagHealth`, `utils/flagUpdateOutcome`).

### 3.3 Léxico de canales (decisión congelada — un canal por tipo de feedback)

- **Carga fallida** (GET que alimenta una vista/lista/selector): `LoadErrorState` (F1), hermano de `EmptyState`.
- **Acción puntual fallida o con aviso** (POST/PUT disparado por un click): `Toast` compartido (F5) o banner inline si el toast no sobrevive al unmount (casos declarados).
- **Guardado de formulario fallido:** banner inline junto al botón Guardar, conservando lo tipeado (F7, patrón `ClientProfileEditor`).
- **Crash de render:** `PageErrorBoundary` (F4).
- **Éxito con condición** (p. ej. requiere reinicio): variante `warning`, NUNCA el canal de error (F5).

## 4. Fases

> **Entorno de tests frontend (leer antes de empezar — patrón plan 132 §4):** los tests de
> componente con `@testing-library/react` + jsdom **no pueden ejecutarse en este checkout**
> (gap preexistente, documentado en `frontend/src/components/__tests__/ActiveRunsPanel.test.tsx:12-17`
> — NO lo resuelvas, no es parte de este plan). Esos tests se escriben igual, con la misma
> NOTA DE ENTORNO en el encabezado, y "quedan listos para correr". La **lógica pura SÍ corre**:
> `npx vitest run <archivo>` desde `Stacky Agents/frontend` (entorno node, sin DOM — igual que
> los tests puros ya verdes del repo). Por eso F0 extrae TODO lo no trivial a funciones puras:
> este plan tiene verdes ejecutables reales, no solo `tsc`. Gate binario global:
> `npx tsc --noEmit` desde `Stacky Agents/frontend`.

---

### F0 — Fundaciones puras + tests (TDD, ejecutables HOY)

**Objetivo (1 frase):** extraer a funciones puras las tres decisiones no triviales del plan (formateo de mensaje de error, veredicto del health-check con retry, clasificación del resultado de guardar flags) y dejarlas verdes con vitest antes de tocar ningún componente.

**Archivos a CREAR (6):**

1. `frontend/src/utils/loadError.ts` — contenido exacto:

```ts
/**
 * Convierte cualquier error atrapado en un mensaje corto y legible para la UI.
 * Los errores de `api/client.ts` (request, :76-78) tienen message =
 * "<status> <statusText>: <body crudo>" — acá se colapsa whitespace y se
 * trunca para que un body HTML/JSON largo no rompa el layout.
 */
export function formatLoadErrorMessage(error: unknown, maxLen = 140): string {
  let msg: string;
  if (error instanceof Error) msg = error.message;
  else if (typeof error === "string") msg = error;
  else msg = "";
  msg = msg.replace(/\s+/g, " ").trim();
  if (!msg) return "error desconocido";
  if (msg.length > maxLen) return msg.slice(0, maxLen - 1) + "…";
  return msg;
}
```

2. `frontend/src/utils/__tests__/loadError.test.ts` — casos (nombres exactos):
   - `"devuelve el message de un Error"` — `new Error("500 INTERNAL SERVER ERROR: boom")` → contiene `"500 INTERNAL SERVER ERROR: boom"`.
   - `"trunca mensajes largos a maxLen con elipsis"` — Error con message de 500 chars → `length === 140` y termina en `"…"`.
   - `"colapsa saltos de línea y espacios múltiples"` — `new Error("a\n\n  b\tc")` → `"a b c"`.
   - `"acepta strings crudos"` — `formatLoadErrorMessage("timeout")` → `"timeout"`.
   - `"cae a 'error desconocido' ante null/undefined/objeto raro"` — `null`, `undefined`, `{}` → `"error desconocido"`.

3. `frontend/src/utils/flagHealth.ts` — contenido exacto:

```ts
/**
 * Veredicto del health-check de tabs opcionales (Migrador/DevOps).
 * Regla congelada (plan 135 F6): SOLO una respuesta JSON válida con
 * flag_enabled === true|false es veredicto. Cualquier otra cosa (red caída,
 * body no-JSON, JSON sin el campo) es "unknown" y NO cambia el estado previo.
 */
export type FlagHealthVerdict = "enabled" | "disabled" | "unknown";

export function interpretFlagHealthResponse(body: unknown): FlagHealthVerdict {
  if (typeof body === "object" && body !== null && "flag_enabled" in body) {
    const v = (body as { flag_enabled?: unknown }).flag_enabled;
    if (v === true) return "enabled";
    if (v === false) return "disabled";
  }
  return "unknown";
}

/** unknown conserva el último estado conocido (sticky). */
export function nextEnabledState(prev: boolean, verdict: FlagHealthVerdict): boolean {
  if (verdict === "enabled") return true;
  if (verdict === "disabled") return false;
  return prev;
}

export interface ProbeOptions {
  fetchImpl?: (path: string) => Promise<{ json(): Promise<unknown> }>;
  /** Reintentos ADICIONALES ante fallo de red/parseo/"unknown". Default 2. */
  retries?: number;
  /** Espera antes del primer reintento; se duplica en cada uno. Default 400. */
  backoffMs?: number;
  sleepImpl?: (ms: number) => Promise<void>;
}

export async function probeFlagHealth(
  path: string,
  opts: ProbeOptions = {}
): Promise<FlagHealthVerdict> {
  // fetch se invoca vía lambda para no perder el binding a window.
  const fetchImpl = opts.fetchImpl ?? ((p: string) => fetch(p));
  const retries = opts.retries ?? 2;
  const backoffMs = opts.backoffMs ?? 400;
  const sleep =
    opts.sleepImpl ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  let wait = backoffMs;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const res = await fetchImpl(path);
      const verdict = interpretFlagHealthResponse(await res.json());
      if (verdict !== "unknown") return verdict; // JSON válido = veredicto final
    } catch {
      // red caída o body no-JSON: cae al retry
    }
    if (attempt < retries) {
      await sleep(wait);
      wait *= 2;
    }
  }
  return "unknown";
}
```

4. `frontend/src/utils/__tests__/flagHealth.test.ts` — casos (nombres exactos; `fetchImpl`/`sleepImpl` inyectados con `vi.fn()`, sin DOM ni timers reales):
   - `"interpreta flag_enabled true/false y todo lo demás como unknown"` — tabla: `{flag_enabled:true}`→enabled, `{flag_enabled:false}`→disabled, `{}`→unknown, `null`→unknown, `"x"`→unknown, `{flag_enabled:"true"}`→unknown.
   - `"nextEnabledState es sticky ante unknown"` — tabla de 6 combinaciones: (prev true, enabled)→true, (true, disabled)→false, (true, unknown)→true, (false, enabled)→true, (false, disabled)→false, (false, unknown)→false.
   - `"devuelve enabled al primer intento sin dormir"` — fetchImpl resuelve `{json: async () => ({flag_enabled: true})}` → `"enabled"`, fetchImpl llamado 1 vez, sleepImpl 0 veces.
   - `"reintenta ante rechazo de red y acepta el veredicto tardío"` — fetchImpl rechaza 2 veces y a la 3ª devuelve `{flag_enabled:false}` → `"disabled"`, fetchImpl 3 llamadas, sleepImpl llamado con `[400, 800]`.
   - `"agota los reintentos y devuelve unknown"` — fetchImpl siempre rechaza, `retries: 2` → `"unknown"`, 3 llamadas.
   - `"JSON válido sin flag_enabled también se reintenta"` — fetchImpl devuelve `{}` siempre → `"unknown"`, 3 llamadas (un body sin el campo NO es veredicto).

5. `frontend/src/utils/flagUpdateOutcome.ts` — contenido exacto:

```ts
/**
 * Clasifica el resultado de HarnessFlags.update para que ÉXITO-con-condición
 * (requiere reinicio) nunca viaje por el canal visual de error (plan 135 F5).
 */
export interface FlagUpdateResultLike {
  ok: boolean;
  error?: string | null;
  restart_required_keys?: string[] | null;
}

export interface FlagUpdateView {
  kind: "error" | "warning" | "ok";
  message: string | null;
}

export function classifyFlagUpdateOutcome(result: FlagUpdateResultLike): FlagUpdateView {
  if (!result.ok) {
    return { kind: "error", message: result.error || "Error al guardar la flag" };
  }
  const keys = result.restart_required_keys ?? [];
  if (keys.length > 0) {
    return {
      kind: "warning",
      message: `Guardado. Requiere reiniciar el backend: ${keys.join(", ")}`,
    };
  }
  return { kind: "ok", message: null };
}
```

6. `frontend/src/utils/__tests__/flagUpdateOutcome.test.ts` — casos (nombres exactos):
   - `"ok sin restart es ok silencioso"` — `{ok:true}` → `{kind:"ok", message:null}`.
   - `"ok con restart_required_keys es warning con las keys"` — `{ok:true, restart_required_keys:["STACKY_X","STACKY_Y"]}` → kind `"warning"`, message `"Guardado. Requiere reiniciar el backend: STACKY_X, STACKY_Y"`.
   - `"no-ok es error con el mensaje del backend"` — `{ok:false, error:"boom"}` → `{kind:"error", message:"boom"}`.
   - `"no-ok sin mensaje cae al copy default"` — `{ok:false}` → message `"Error al guardar la flag"`.

- **Comandos exactos** (desde `Stacky Agents/frontend/`, uno por archivo — regla del repo):
  1. `npx vitest run src/utils/__tests__/loadError.test.ts`
  2. `npx vitest run src/utils/__tests__/flagHealth.test.ts`
  3. `npx vitest run src/utils/__tests__/flagUpdateOutcome.test.ts`
- **Criterio de aceptación (binario):** los 3 comandos terminan verdes (exit 0) HOY, antes de tocar cualquier componente; `npx tsc --noEmit` exit 0.
- **Flag:** no aplica (§3.1: helpers puros sin efecto hasta que un componente los use). **Impacto por runtime:** ninguno (código puro). **Trabajo del operador: ninguno.**

---

### F1 — `LoadErrorState` + adopción en TicketBoard (KPI-1, el caso central)

**Objetivo (1 frase):** crear el componente hermano de `EmptyState` que distingue "falló la carga" de "no hay datos", y estrenarlo en la superficie donde el disfraz es más caro: el board de tickets.

**Archivo a CREAR 1:** `frontend/src/components/LoadErrorState.tsx` — contenido exacto:

```tsx
import { formatLoadErrorMessage } from "../utils/loadError";
import styles from "./LoadErrorState.module.css";

/**
 * Hermano de EmptyState (plan 135 F1): se usa cuando una CARGA FALLÓ, para no
 * disfrazar un 500 de "no hay datos" (precedente: 500 mudo del revisor de PRs,
 * 2026-07-11). El botón Reintentar re-dispara LA MISMA carga que falló.
 */
interface Props {
  /** Qué se intentó cargar, en plural y con artículo: "los tickets", "las PRs". */
  what: string;
  /** El error atrapado (Error, string o cualquier cosa); se formatea y trunca. */
  error?: unknown;
  /** Re-dispara la misma carga. Si falta, no se muestra botón. */
  onRetry?: () => void;
  /** Variante de una sola línea para paletas/selectores/listas embebidas. */
  compact?: boolean;
}

export default function LoadErrorState({ what, error, onRetry, compact = false }: Props) {
  const detail = error === undefined || error === null ? null : formatLoadErrorMessage(error);
  if (compact) {
    return (
      <div className={styles.compact} role="alert">
        <span aria-hidden="true">⚠️</span>
        <span className={styles.compactText}>
          No se pudieron cargar {what}
          {detail ? `: ${detail}` : ""}
        </span>
        {onRetry && (
          <button type="button" className={styles.retryCompact} onClick={onRetry}>
            Reintentar
          </button>
        )}
      </div>
    );
  }
  return (
    <div className={styles.root} role="alert">
      <div className={styles.icon} aria-hidden="true">⚠️</div>
      <h3 className={styles.title}>No se pudieron cargar {what}</h3>
      {detail && <p className={styles.message}>{detail}</p>}
      {onRetry && (
        <button type="button" className={styles.action} onClick={onRetry}>
          ↻ Reintentar
        </button>
      )}
    </div>
  );
}
```

**Archivo a CREAR 2:** `frontend/src/components/LoadErrorState.module.css` — contenido exacto (paleta de error de la casa: mismos `rgba(239,68,68,…)`/`#fecaca` que el fallback de `TicketGraphView.jsx:263-272`):

```css
/* LoadErrorState — hermano de EmptyState para cargas fallidas (plan 135). */
.root {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 32px 16px;
  text-align: center;
}
.icon { font-size: 28px; }
.title { margin: 0; font-size: 15px; font-weight: 600; color: #fca5a5; }
.message {
  margin: 0;
  font-size: 12.5px;
  color: rgba(255, 255, 255, 0.65);
  max-width: 420px;
  overflow-wrap: anywhere;
}
.action {
  margin-top: 4px;
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid rgba(239, 68, 68, 0.45);
  background: rgba(239, 68, 68, 0.12);
  color: #fecaca;
  cursor: pointer;
  font-size: 12.5px;
}
.action:hover { background: rgba(239, 68, 68, 0.2); }

/* Variante compacta: una línea, para listas/paletas/selectores. */
.compact {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid rgba(239, 68, 68, 0.45);
  background: rgba(239, 68, 68, 0.12);
  border-radius: 6px;
  font-size: 12px;
  color: #fecaca;
}
.compactText { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.retryCompact {
  flex-shrink: 0;
  background: transparent;
  border: 1px solid rgba(239, 68, 68, 0.45);
  border-radius: 4px;
  color: #fecaca;
  padding: 2px 8px;
  cursor: pointer;
  font-size: 11.5px;
}
.retryCompact:hover { background: rgba(239, 68, 68, 0.2); }
```

**Archivo a CREAR 3 (test primero):** `frontend/src/components/__tests__/LoadErrorState.test.tsx` — RTL written-ready (encabezado con la misma NOTA DE ENTORNO literal de `ActiveRunsPanel.test.tsx:12-17`). Tests con estos nombres exactos:
- `"muestra el copy de error con el sujeto"` — render con `what="los tickets"` → texto `/No se pudieron cargar los tickets/`.
- `"muestra el detalle formateado del error"` — `error={new Error("500 X: boom")}` → texto que contiene `"boom"`.
- `"el botón Reintentar dispara onRetry"` — `fireEvent.click` sobre `getByRole("button", { name: /reintentar/i })` → spy llamado 1 vez.
- `"sin onRetry no renderiza botón"` — `queryByRole("button")` es `null`.
- `"la variante compact renderiza en una línea con role alert"` — `compact` → `getByRole("alert")` existe y contiene el copy.

**Archivo a EDITAR:** `frontend/src/pages/TicketBoard.tsx` (4 ediciones):

1. Import (junto a los imports de componentes existentes, al tope del archivo):
```tsx
import LoadErrorState from "../components/LoadErrorState";
```

2. Query de tickets (`:741-747`) — ampliar el destructure, resto idéntico:
```tsx
// ANTES
const { data: tickets, isLoading } = useQuery<Ticket[]>({
// DESPUÉS
const { data: tickets, isLoading, isError: isTicketsError, error: ticketsError, refetch: refetchTickets } = useQuery<Ticket[]>({
```

3. Query de jerarquía (`:749-755`) — ídem:
```tsx
// ANTES
const { data: hierarchy, isLoading: isHierarchyLoading } = useQuery<TicketHierarchy>({
// DESPUÉS
const { data: hierarchy, isLoading: isHierarchyLoading, isError: isHierarchyError, error: hierarchyError, refetch: refetchHierarchy } = useQuery<TicketHierarchy>({
```

Inmediatamente DESPUÉS del bloque de la query de jerarquía (tras su `});` de cierre, `:755`), agregar:
```tsx
  // Plan 135: error de PRIMERA carga (sin datos previos). react-query v5
  // conserva `data` del último fetch exitoso ante errores de refetch, así que
  // si hay data seguimos mostrando el board (stale) y NO lo tapamos con error.
  const ticketsUnavailable = isTicketsError && tickets === undefined;
  const hierarchyUnavailable = isHierarchyError && hierarchy === undefined;
```

4. Render — dos inserciones:

4a. Inmediatamente DESPUÉS de `<main className={styles.main}>` (`:1006`), agregar (cubre vista plana y grafo, que se alimentan de la query de tickets):
```tsx
        {ticketsUnavailable && (
          <LoadErrorState
            what="los tickets"
            error={ticketsError}
            onRetry={() => { void refetchTickets(); }}
          />
        )}
```

4b. En el bloque de vista árbol (`:1008-1015`), reemplazar EXACTAMENTE:
```tsx
// ANTES
            {isHierarchyLoading && <div className={styles.loading}>Cargando jerarquía…</div>}
            {!isHierarchyLoading && filteredEpics.length === 0 && filteredOrphans.length === 0 && (
              <div className={styles.empty}>
                No hay tickets. Hacé clic en «Sincronizar ADO».
              </div>
            )}
// DESPUÉS
            {isHierarchyLoading && <div className={styles.loading}>Cargando jerarquía…</div>}
            {!isHierarchyLoading && hierarchyUnavailable && (
              <LoadErrorState
                what="la jerarquía de tickets"
                error={hierarchyError}
                onRetry={() => { void refetchHierarchy(); }}
              />
            )}
            {!isHierarchyLoading && !hierarchyUnavailable && filteredEpics.length === 0 && filteredOrphans.length === 0 && (
              <div className={styles.empty}>
                No hay tickets. Hacé clic en «Sincronizar ADO».
              </div>
            )}
```

**Casos borde congelados:** (a) refetch periódico (45 s) falla con datos ya cargados → el board sigue mostrando los datos (stale) sin banner — decisión deliberada para no parpadear; (b) `enabled: viewMode === "tree" || viewMode === "graph"` en la query de jerarquía se mantiene intacto; (c) el botón Reintentar llama `refetch()` de la MISMA query — cero mecanismos nuevos.

- **Comando exacto:** `npx tsc --noEmit` (desde `Stacky Agents/frontend/`) + `npx vitest run src/components/__tests__/LoadErrorState.test.tsx` (rojo SOLO por el gap RTL preexistente = no bloquea).
- **Criterio de aceptación (binario, = KPI-1):** con el backend detenido, abrir el board en vista árbol muestra `LoadErrorState` con "Reintentar" y NO el copy "No hay tickets…"; levantar el backend y clickear Reintentar recupera el árbol SIN F5. Con backend sano, el board es byte-idéntico a hoy.
- **Flag:** no aplica (§3.1). **Impacto por runtime:** ninguno (query de tickets, agnóstica). **Trabajo del operador: ninguno.**

---

### F2 — Adopción de `LoadErrorState` en las 5 superficies restantes del GAP 1

**Objetivo (1 frase):** que ninguna carga fallida quede disfrazada de vacío en la paleta, el modal de lanzamiento, el chat, el revisor de PRs ni el replay.

Todas las ediciones importan lo que usan: `import LoadErrorState from "./LoadErrorState";` (misma carpeta `components/`) o `"../LoadErrorState"` según ubicación, y `import { formatLoadErrorMessage } from "../utils/loadError";` (ajustar `../` a la profundidad del archivo; para `devops/` es `"../../utils/loadError"`). No se escribe ningún test RTL nuevo en esta fase (gap de entorno; la lógica de formateo ya quedó verde en F0): el gate es `tsc` + el checklist manual del final de la fase.

**2.1 — `frontend/src/components/CommandPalette.tsx`**
- Junto a los `useState` existentes (`:43-48`), agregar:
```tsx
  const [loadFailed, setLoadFailed] = useState<string[]>([]);
  const [reloadKey, setReloadKey] = useState(0);
```
- En el `useEffect` de carga (`:51-81`): (a) tras `setSelectedIdx(0);` (`:54`) agregar `setLoadFailed([]);`; (b) reemplazar los 4 catch:
```tsx
      .catch(() => { setTickets([]); setLoadFailed((p) => [...p, "tickets"]); });
      .catch(() => { setAgents([]); setLoadFailed((p) => [...p, "agentes"]); });
      .catch(() => { setPacks([]); setLoadFailed((p) => [...p, "packs"]); });
      .catch(() => { setProjects([]); setLoadFailed((p) => [...p, "proyectos"]); });
```
  (respetando el cuerpo `.then` existente de cada uno, `:57-80`); (c) deps `:81`: `}, [open]);` → `}, [open, reloadKey]);`.
- Render: inmediatamente ANTES de `<ul className={styles.list} role="listbox">` (`:229`), agregar:
```tsx
        {loadFailed.length > 0 && (
          <LoadErrorState
            compact
            what={loadFailed.join(", ")}
            onRetry={() => setReloadKey((k) => k + 1)}
          />
        )}
```
- Caso borde: fallos parciales (p. ej. solo packs) muestran la línea con solo esa fuente; la paleta sigue operable con lo que sí cargó.

**2.2 — `frontend/src/components/AgentLaunchModal.tsx`**
- Junto a `const [filtered, setFiltered] = useState<Ticket[]>([]);` (`:64`), agregar:
```tsx
  const [ticketsLoadError, setTicketsLoadError] = useState<string | null>(null);
  const [ticketsReloadKey, setTicketsReloadKey] = useState(0);
```
- En el `useEffect` de carga (`:109-130`): (a) primera línea del cuerpo: `setTicketsLoadError(null);`; (b) `:113` `.catch(() => {})` → `.catch((e) => setTicketsLoadError(formatLoadErrorMessage(e)));`; (c) agregar `ticketsReloadKey` al array de dependencias del efecto (el array que cierra el efecto en `:130`, debajo del `eslint-disable` de `:129`).
- Render (`:353-357`): reemplazar el ternario del bloque `{/* Ticket list */}`:
```tsx
// ANTES
          {filtered.length === 0 ? (
            <div className={styles.empty}>No se encontraron tickets</div>
          ) : (
// DESPUÉS
          {ticketsLoadError ? (
            <LoadErrorState
              compact
              what="los tickets"
              error={ticketsLoadError}
              onRetry={() => setTicketsReloadKey((k) => k + 1)}
            />
          ) : filtered.length === 0 ? (
            <div className={styles.empty}>No se encontraron tickets</div>
          ) : (
```

**2.3 — `frontend/src/components/ChatDrawer.tsx`**
- Junto a los `useState` del componente, agregar `ticketsLoadError`/`ticketsReloadKey` (idéntico a 2.2).
- En el `useEffect` (`:162-176`): (a) tras el guard de `:163`, agregar `setTicketsLoadError(null);`; (b) `:175` `.catch(() => {})` → `.catch((e) => setTicketsLoadError(formatLoadErrorMessage(e)));`; (c) deps `:176`: agregar `ticketsReloadKey`.
- Render: inmediatamente ANTES de `{filteredTickets.length > 0 && (` (`:524`), agregar:
```tsx
                {ticketsLoadError && (
                  <LoadErrorState
                    compact
                    what="los tickets"
                    error={ticketsLoadError}
                    onRetry={() => setTicketsReloadKey((k) => k + 1)}
                  />
                )}
```

**2.4 — `frontend/src/components/devops/PrReviewerSection.tsx`** (la superficie del 500 mudo real)
- Diff de 1 línea en `resetForPr` (`:114-116`) — reusar el canal `error` YA renderizado en `:199` y el helper `errMsg` (`:35`):
```tsx
// ANTES
    PrReview.actions(activeProject)
      .then((r) => setActions(r.actions))
      .catch(() => setActions([]));
// DESPUÉS
    PrReview.actions(activeProject)
      .then((r) => setActions(r.actions))
      .catch((e) => { setActions([]); setError(errMsg(e)); });
```
- Reintento (decidido): re-seleccionar la PR en la lista re-dispara `resetForPr` (mecanismo existente de 1 click); no se agrega botón propio acá porque el banner `:199` es genérico de la sección. NO usar `LoadErrorState` en esta superficie: el canal correcto ya existe.

**2.5 — `frontend/src/components/ReplayPlayer.tsx`**
- Junto a `const [events, setEvents] = useState<Event[]>([]);` (`:28`), agregar `loadError`/`reloadKey` (mismo par de estados que 2.2, nombres `loadError` y `reloadKey`).
- En el `useEffect` (`:35-43`): (a) tras `setPlaying(false);` (`:38`) agregar `setLoadError(null);`; (b) `:42` → `.catch((err) => { setEvents([]); setLoadError(formatLoadErrorMessage(err)); });`; (c) deps `:43`: `[open, executionId]` → `[open, executionId, reloadKey]`.
- Render (`:123-127`): reemplazar el ternario del `<ul className={styles.log}>`:
```tsx
// ANTES
          {events.length === 0 ? (
            <li className={styles.empty}>
              Esta ejecución no tiene timeline de eventos registrado.
            </li>
          ) : (
// DESPUÉS
          {loadError ? (
            <li className={styles.empty}>
              <LoadErrorState
                compact
                what="los eventos de la grabación"
                error={loadError}
                onRetry={() => setReloadKey((k) => k + 1)}
              />
            </li>
          ) : events.length === 0 ? (
            <li className={styles.empty}>
              Esta ejecución no tiene timeline de eventos registrado.
            </li>
          ) : (
```

- **Comando exacto:** `npx tsc --noEmit` → exit 0.
- **Criterio de aceptación (binario):** checklist manual con el backend DETENIDO (o DevTools → Network → Offline): (1) Ctrl+K → la paleta muestra la línea compacta "No se pudieron cargar tickets, agentes, packs, proyectos" con Reintentar; (2) abrir AgentLaunchModal → línea compacta en el selector de tickets, no "No se encontraron tickets"; (3) abrir ChatDrawer con un agente → ídem; (4) en DevOps → Revisor de PRs, seleccionar una PR con `/pr-review/actions` devolviendo 500 → banner de error de la sección, no silencio; (5) abrir un ReplayPlayer → línea compacta, no "no tiene timeline". Con backend sano: los 5 renders son byte-idénticos a hoy.
- **Flag:** no aplica (§3.1). **Impacto por runtime:** ninguno (todas son cargas de datos agnósticas). **Trabajo del operador: ninguno.**

---

### F3 — GAP 2: cancelaciones nunca más en silencio (panel + dock)

**Objetivo (1 frase):** que cancelar un run que falla lo diga y ofrezca reintentar, y que cerrar la consola de una sesión interactiva viva no desmonte la UI si el cancel falló (anti-zombie de 1800 s).

**3.1 — Test primero (written-ready):** EDITAR `frontend/src/components/__tests__/ActiveRunsPanel.test.tsx` agregando AL FINAL del `describe("ActiveRunsPanel", ...)` (después del último test existente; NO tocar `beforeEach` ni mocks existentes — regla §3.2; si el plan 132 ya aterrizó sus tests, agregar después de los suyos) exactamente estos 2 tests:

```tsx
  it("muestra un aviso inline cuando cancelar falla, sin ocultar el panel", async () => {
    mockRuns([RUN]);
    mockCancel.mockRejectedValueOnce(new Error("500 INTERNAL SERVER ERROR: boom"));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    wrap(<ActiveRunsPanel />);

    await waitFor(() => expect(screen.getByText("#42")).toBeDefined());
    fireEvent.click(screen.getByRole("button", { name: /cancelar/i }));

    await waitFor(() =>
      expect(screen.getByText(/No se pudo cancelar #42/i)).toBeDefined(),
    );
    // El panel sigue visible con el run listado.
    expect(screen.getByText("#42")).toBeDefined();
  });

  it("el botón Reintentar del aviso re-dispara la cancelación sin nuevo confirm", async () => {
    mockRuns([RUN]);
    mockCancel.mockRejectedValueOnce(new Error("timeout"));
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    wrap(<ActiveRunsPanel />);

    await waitFor(() => expect(screen.getByText("#42")).toBeDefined());
    fireEvent.click(screen.getByRole("button", { name: /cancelar/i }));
    await waitFor(() =>
      expect(screen.getByText(/No se pudo cancelar #42/i)).toBeDefined(),
    );

    confirmSpy.mockClear();
    fireEvent.click(screen.getByRole("button", { name: /^reintentar$/i }));

    expect(confirmSpy).not.toHaveBeenCalled();
    await waitFor(() => expect(mockCancel).toHaveBeenCalledTimes(2));
  });
```

**3.2 — EDITAR `frontend/src/components/ActiveRunsPanel.tsx`** (3 ediciones; NO tocar el interior del `runs.map` `:128-158` — zona del plan 132/134):

1. Import: agregar junto a los imports existentes:
```tsx
import { formatLoadErrorMessage } from "../utils/loadError";
```
2. Query (`:63`) — destructurar el error de fetch:
```tsx
// ANTES
  const { data } = useQuery({
// DESPUÉS
  const { data, isError: fetchFailed } = useQuery({
```
   `cancelMutation` (`:69-77`) NO se toca: el estado de error se lee de la propia mutation (react-query v5 expone `isError`/`error`/`variables`/`reset`), sin `onError` nuevo.
3. Render: inmediatamente DESPUÉS de `</ul>` (`:159`) y ANTES del `</div>` de cierre (`:160`), agregar:
```tsx
      {fetchFailed && (
        <div className={styles.staleNotice} role="status">
          Sin conexión con el backend — mostrando el último estado conocido.
        </div>
      )}
      {cancelMutation.isError && (
        <div className={styles.cancelError} role="alert">
          <span className={styles.cancelErrorText}>
            No se pudo cancelar #{cancelMutation.variables}:{" "}
            {formatLoadErrorMessage(cancelMutation.error)}
          </span>
          <button
            type="button"
            className={styles.cancelRetry}
            onClick={() => cancelMutation.mutate(cancelMutation.variables as number)}
          >
            Reintentar
          </button>
          <button
            type="button"
            className={styles.cancelDismiss}
            aria-label="Descartar aviso de cancelación"
            onClick={() => cancelMutation.reset()}
          >
            ✕
          </button>
        </div>
      )}
```
   Decisiones congeladas: (a) el Reintentar NO re-pide `window.confirm` — el operador ya confirmó esa cancelación (HITL intacto: sigue siendo un click explícito); (b) si la PRIMERA carga de la query falla (`data === undefined`), el panel sigue devolviendo `null` como hoy — la señal global de backend caído ya la da `HealthBanner` (`App.tsx:145`) y un panel flotante de error duplicaría ese canal; el aviso `staleNotice` solo aparece cuando el panel está visible con datos previos.

**3.3 — EDITAR `frontend/src/components/ActiveRunsPanel.module.css`** — append AL FINAL del archivo (si el plan 132 ya agregó `.consoleBtn` al final, agregar después):
```css
/* Plan 135 F3 — feedback de cancelación y datos stale. */
.staleNotice {
  margin: 6px 8px 8px;
  padding: 4px 8px;
  color: #fcd34d;
  font-size: 11px;
  opacity: 0.9;
}
.cancelError {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 6px 8px 8px;
  padding: 6px 8px;
  border: 1px solid rgba(239, 68, 68, 0.45);
  background: rgba(239, 68, 68, 0.12);
  border-radius: 4px;
  color: #fecaca;
  font-size: 11.5px;
}
.cancelErrorText { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.cancelRetry,
.cancelDismiss {
  flex-shrink: 0;
  background: transparent;
  border: 1px solid rgba(239, 68, 68, 0.45);
  border-radius: 4px;
  color: #fecaca;
  padding: 2px 8px;
  cursor: pointer;
  font-size: 11px;
}
.cancelRetry:hover,
.cancelDismiss:hover { background: rgba(239, 68, 68, 0.2); }
```

**3.4 — EDITAR `frontend/src/components/CodexConsoleDock.tsx`** (4 ediciones):

1. Import: agregar `import { formatLoadErrorMessage } from "../utils/loadError";`.
2. Estado: junto a `const [detailOpen, setDetailOpen] = useState(false);` (`:55`), agregar:
```tsx
  const [closeState, setCloseState] = useState<{ closing: boolean; error: string | null }>({
    closing: false,
    error: null,
  });
```
3. Handler: inmediatamente DESPUÉS de `handleScroll` (`:121-126`), agregar:
```tsx
  // Plan 135 F3: cerrar una sesión interactiva VIVA implica cancelarla en el
  // backend. Si el cancel falla, NO desmontamos la consola (antes: catch mudo
  // + setExecution(null) → run zombie invisible, precedente 1800s). El
  // operador ve el error y reintenta con otro click.
  const handleClose = async () => {
    if (closeState.closing) return;
    if (isInteractiveRun && status === "running" && !stream.done) {
      setCloseState({ closing: true, error: null });
      try {
        await Executions.cancel(executionId);
      } catch (e) {
        setCloseState({ closing: false, error: formatLoadErrorMessage(e) });
        return; // la consola sigue abierta y viva
      }
    }
    setCloseState({ closing: false, error: null });
    setExecution(null);
  };
```
4. Botón de cierre (`:171-186`): reemplazar el `onClick` inline (`:174-182`) por `onClick={() => { void handleClose(); }}`, y agregar al botón `disabled={closeState.closing}`. El comentario existente del cuerpo (`:175-177`) se traslada al handler (ya cubierto por el comentario nuevo — eliminarlo del JSX). Título del botón sin cambios.
5. Render del error: inmediatamente DESPUÉS de `</header>` (`:188`), agregar:
```tsx
      {closeState.error && (
        <div className={styles.closeError} role="alert">
          No se pudo finalizar la sesión: {closeState.error} — la consola sigue abierta.
          <button type="button" onClick={() => { void handleClose(); }}>
            Reintentar
          </button>
        </div>
      )}
```

**3.5 — EDITAR `frontend/src/components/CodexConsoleDock.module.css`** — append al final:
```css
/* Plan 135 F3 — el cierre de una sesión interactiva viva falló. */
.closeError {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-bottom: 1px solid rgba(239, 68, 68, 0.45);
  background: rgba(239, 68, 68, 0.12);
  color: #fecaca;
  font-size: 12px;
}
.closeError button {
  flex-shrink: 0;
  background: transparent;
  border: 1px solid rgba(239, 68, 68, 0.45);
  border-radius: 4px;
  color: #fecaca;
  padding: 2px 8px;
  cursor: pointer;
  font-size: 11px;
}
.closeError button:hover { background: rgba(239, 68, 68, 0.2); }
```

**Casos borde congelados:** (a) run NO interactivo o ya terminado → `handleClose` cierra directo, byte-idéntico a hoy; (b) el cancel falla porque el run terminó justo entre medio → el error se muestra, `executionQ` refresca `status` a los ≤5 s (`:66`), el segundo click ya no intenta cancelar y cierra; (c) minimizar sigue intacto como vía de "ocultar sin matar". No se escribe test RTL para el dock (superficie de mocks alta: `useExecutionStream` + store + endpoints; gap de entorno lo haría doblemente no-ejecutable): gate = `tsc` + smoke manual.

- **Comandos exactos:** `npx tsc --noEmit`; `npx vitest run src/components/__tests__/ActiveRunsPanel.test.tsx` (verde, o rojo SOLO por el gap RTL preexistente).
- **Criterio de aceptación (binario, = KPI-2):** con el backend devolviendo error en `POST /api/executions/<id>/cancel` (p. ej. deteniéndolo tras cargar el panel): (1) "✕ Cancelar" en el panel muestra el aviso inline con Reintentar y el panel NO desaparece; (2) la X del dock sobre una sesión interactiva viva muestra "No se pudo finalizar la sesión…" y la consola SIGUE montada. Con backend sano, ambos flujos son byte-idénticos a hoy.
- **Flag:** no aplica (§3.1). **Impacto por runtime:** panel idéntico para los 3; guard del dock solo en el camino ya-interactivo (§5). **Trabajo del operador: ninguno.**

---

### F4 — GAP 3: `PageErrorBoundary` — cero pantalla blanca

**Objetivo (1 frase):** contener cualquier throw de render de las 13 páginas en un fallback con Reintentar, manteniendo vivos TopBar/nav/HealthBanner/CodexConsoleDock/ActiveRunsPanel.

**Archivo a CREAR 1 (test primero, written-ready):** `frontend/src/components/__tests__/PageErrorBoundary.test.tsx` — RTL con la NOTA DE ENTORNO literal. Tests (nombres exactos), usando un componente local `function Bomb(): never { throw new Error("boom de render"); }`:
- `"renderiza el fallback con el mensaje cuando un hijo lanza"` — render `<PageErrorBoundary resetKey="a"><Bomb/></PageErrorBoundary>` → `getByRole("alert")` contiene `/Esta pestaña falló al renderizar/` y `/boom de render/`.
- `"Reintentar resetea el boundary y re-renderiza los hijos"` — estado compartido que deja de lanzar tras el primer render; click en `/reintentar/i` → hijos visibles, sin fallback.
- `"cambiar resetKey resetea el boundary"` — rerender con `resetKey="b"` y un hijo sano → hijos visibles.
- `"sin error renderiza los hijos tal cual"` — hijo de texto → visible, sin `role="alert"`.

**Archivo a CREAR 2:** `frontend/src/components/PageErrorBoundary.tsx` — contenido exacto:

```tsx
import React, { type ReactNode } from "react";
import styles from "./PageErrorBoundary.module.css";

/**
 * Boundary a nivel PÁGINA (plan 135 F4). Patrón de la casa: copia de
 * NodeErrorBoundary (TicketGraphView.jsx:244) elevada a las 13 páginas de
 * App.tsx. Un throw en el render de un tab ya no blanquea toda la app:
 * TopBar/nav/HealthBanner/CodexConsoleDock/ActiveRunsPanel siguen vivos.
 * Se resetea con el botón Reintentar o al cambiar de tab (resetKey).
 */
interface Props {
  /** Cambiarla (p. ej. el tab activo) resetea el boundary automáticamente. */
  resetKey: string;
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class PageErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error("[PageErrorBoundary] render error:", error, info);
  }

  componentDidUpdate(prevProps: Props): void {
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false, error: null });
    }
  }

  handleRetry = (): void => {
    this.setState({ hasError: false, error: null });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className={styles.root} role="alert">
          <div className={styles.icon} aria-hidden="true">💥</div>
          <h2 className={styles.title}>Esta pestaña falló al renderizar</h2>
          <p className={styles.message}>
            {this.state.error?.message || "Error inesperado"}
          </p>
          <p className={styles.hint}>
            El resto de la aplicación sigue funcionando. Podés reintentar o cambiar de pestaña.
          </p>
          <button type="button" className={styles.action} onClick={this.handleRetry}>
            ↻ Reintentar
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
```

**Archivo a CREAR 3:** `frontend/src/components/PageErrorBoundary.module.css`:
```css
/* PageErrorBoundary — fallback de página (plan 135 F4). */
.root {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 64px 24px;
  text-align: center;
}
.icon { font-size: 32px; }
.title { margin: 0; font-size: 17px; font-weight: 600; color: #fca5a5; }
.message {
  margin: 0;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.7);
  max-width: 520px;
  overflow-wrap: anywhere;
}
.hint { margin: 0; font-size: 12px; color: rgba(255, 255, 255, 0.45); }
.action {
  margin-top: 8px;
  padding: 8px 18px;
  border-radius: 6px;
  border: 1px solid rgba(239, 68, 68, 0.45);
  background: rgba(239, 68, 68, 0.12);
  color: #fecaca;
  cursor: pointer;
  font-size: 13px;
}
.action:hover { background: rgba(239, 68, 68, 0.2); }
```

**Archivo a EDITAR:** `frontend/src/App.tsx` (2 ediciones):
1. Import junto a los imports de componentes: `import PageErrorBoundary from "./components/PageErrorBoundary";`
2. Envolver EXACTAMENTE el bloque de páginas (`:241-253`), sin tocar su interior (zona compartida §3.2 — el wrap agrega 1 línea antes y 1 después):
```tsx
      <PageErrorBoundary resetKey={tab}>
        {tab === "team"     && <TeamScreen />}
        {/* … las 13 líneas existentes idénticas … */}
        {tab === "devops"      && devopsEnabled && <DevOpsPage />} {/* Plan 87 */}
      </PageErrorBoundary>
```
   `CommandPalette`, `ShortcutsCheatsheet`, `DailyStandupModal`, `OnboardingTour`, `CodexConsoleDock` y `ActiveRunsPanel` (`:255-274`) quedan FUERA del boundary (siguen vivos ante un crash de página).

**Casos borde congelados:** (a) cambiar de tab con el fallback visible → `resetKey` cambia → boundary se resetea y monta la página nueva; (b) si el error es determinista, Reintentar vuelve a mostrar el fallback (correcto: señal persistente, no loop — React no re-lanza infinito porque el throw ocurre solo al re-render solicitado); (c) errores de EVENTOS/promesas no pasan por boundaries de React — fuera de alcance declarado (los cubren F1-F3/F5-F7).

- **Comandos exactos:** `npx tsc --noEmit`; `npx vitest run src/components/__tests__/PageErrorBoundary.test.tsx` (verde, o rojo SOLO por gap RTL).
- **Criterio de aceptación (binario, = KPI-3):** agregar temporalmente `throw new Error("prueba 135")` al inicio del render de `DiagnosticsPage`, abrir el tab Diagnóstico → fallback con el mensaje y Reintentar, con TopBar/nav/paneles globales operativos; cambiar a otro tab funciona; revertir el throw. Con páginas sanas, render byte-idéntico.
- **Flag:** no aplica (§3.1). **Impacto por runtime:** ninguno (contención de render, agnóstica). **Trabajo del operador: ninguno.**

---

### F5 — GAP 4: Toast compartido + los 2 "Guardado-como-error" al canal correcto

**Objetivo (1 frase):** un solo componente Toast (extraído del ejemplar de `RecoverExecutionButton`) para los 3 toasts caseros, y que "Guardado. Requiere reiniciar…" viaje como `warning`, nunca como error.

**Decisión congelada de unificación:** el look canónico es el del Toast de `RecoverExecutionButton` (fixed bottom-right, `RecoverExecutionButton.module.css:161-171`). Los 3 adoptantes pasan a ese look/posición — esa ES la unificación buscada. Contenido de los mensajes, disparadores y timings quedan idénticos (el auto-dismiss de 5 s de `PipelineTriggerCard` se conserva). Prohibido migrar cualquier otra superficie (en particular los `window.confirm` — plan 136) o cambiar copys, salvo los 2 casos rotos declarados.

**5.1 — Test primero (written-ready):** CREAR `frontend/src/components/__tests__/Toast.test.tsx` — RTL con NOTA DE ENTORNO. Tests: `"renderiza title y body con role alert"`, `"sin title no renderiza el header title"`, `"aplica la clase de la variante"` (un caso por variante: `variant="success"` → `className` contiene `success`, `variant="warning"` → contiene `warning`, `variant="error"` → contiene `error`), `"el botón cerrar dispara onClose"`.

**5.2 — CREAR `frontend/src/components/Toast.tsx`** — contenido exacto (copia del ejemplar `:50-67` con `title` ahora opcional):

```tsx
import styles from "./Toast.module.css";

/**
 * Toast compartido de la casa (plan 135 F5). Extraído del patrón ejemplar de
 * RecoverExecutionButton. Canal para resultados de ACCIONES (no de cargas:
 * eso es LoadErrorState). Variante warning = éxito con condición (p. ej.
 * requiere reinicio): NUNCA usar variante error para un éxito.
 */
export type ToastVariant = "success" | "warning" | "error";

export interface ToastState {
  variant: ToastVariant;
  /** Opcional: si falta, se renderiza solo el body + botón cerrar. */
  title?: string;
  body: string;
  correlationId?: string;
}

export default function Toast({
  toast,
  onClose,
}: {
  toast: ToastState;
  onClose: () => void;
}) {
  return (
    <div
      className={`${styles.toast} ${styles[`toast_${toast.variant}`]}`}
      data-correlation-id={toast.correlationId ?? undefined}
      role="alert"
      aria-live="assertive"
    >
      <div className={styles.toastHeader}>
        {toast.title ? (
          <strong className={styles.toastTitle}>{toast.title}</strong>
        ) : (
          <span />
        )}
        <button
          className={styles.toastClose}
          onClick={onClose}
          aria-label="Cerrar notificación"
        >
          ✕
        </button>
      </div>
      <p className={styles.toastBody}>{toast.body}</p>
    </div>
  );
}
```

**5.3 — CREAR `frontend/src/components/Toast.module.css`:** copia LITERAL del bloque `/* ─── Toast ─── */` de `RecoverExecutionButton.module.css:159-226` (clases `.toast`, `@keyframes toastIn`, `.toast_success`, `.toast_warning`, `.toast_error`, `.toastHeader`, `.toastTitle`, sus 3 overrides de color, `.toastBody`, `.toastClose`, `.toastClose:hover`).

**5.4 — EDITAR `frontend/src/components/RecoverExecutionButton.tsx`:** eliminar los tipos y el componente locales (`:41-48` y `:50-67`) y agregar `import Toast, { type ToastState } from "./Toast";`. El resto del archivo queda byte-idéntico (los call sites ya usan `ToastState` y `<Toast toast=… onClose=…/>`). EDITAR `RecoverExecutionButton.module.css`: eliminar el bloque `:159-226` (queda en `Toast.module.css`; dejarlo duplicado = drift futuro).

**5.5 — EDITAR `frontend/src/components/CreateChildTaskButton.tsx`** (adopción, comportamiento idéntico):
- Import: `import Toast, { type ToastState } from "./Toast";`
- Estado (`:63`): `useState<{ ok: boolean; message: string } | null>(null)` → `useState<ToastState | null>(null)`.
- Call sites: `:87` (`setToast(null)`) queda igual; `:166` → `setToast({ variant: "success", body: \`${createdCount} Task(s) creada(s) en ADO exitosamente.\` });`; `:169-172` → `setToast({ variant: "error", body: \`${createdCount} ok, ${errorCount} con error. Revisar resultados.\` });` (mensajes byte-idénticos).
- Render (`:365-374`): reemplazar el `<div role="alert" …>` completo por `{toast && <Toast toast={toast} onClose={() => setToast(null)} />}`.

**5.6 — EDITAR `frontend/src/components/PipelineTriggerCard.tsx`** (adopción, comportamiento idéntico):
- Import: `import Toast, { type ToastState } from "./Toast";`
- Estado: cambiar el tipo del `useState` de `toast` (buscar `useState<{ msg: string; kind` en el archivo) a `useState<ToastState | null>(null)`.
- `showToast` (`:63-66`): cuerpo →
```tsx
  const showToast = (msg: string, kind: "info" | "error" = "info") => {
    setToast({ variant: kind === "error" ? "error" : "success", body: msg });
    setTimeout(() => { if (mountedRef.current) setToast(null); }, 5000);
  };
```
  (firma intacta: los callers no se tocan; timing 5 s intacto; `info` ya se renderizaba en verde `#e8f5e9` → `success` es el mismo canal visual).
- Render (`:151-159`): reemplazar el `<div style={{…}}>` completo por `{toast && <Toast toast={toast} onClose={() => setToast(null)} />}`.

**5.7 — EDITAR `frontend/src/components/HarnessFlagsPanel.tsx`** (caso roto 1, = KPI-4):
- Imports: `import Toast, { type ToastState } from "./Toast";` y `import { classifyFlagUpdateOutcome } from "../utils/flagUpdateOutcome";`
- Estado: junto a `const [apiError, setApiError] = useState<string | null>(null);` (`:353`), agregar `const [saveNotice, setSaveNotice] = useState<ToastState | null>(null);`
- `handleUpdate` (`:506-516`): reemplazar el cuerpo del `onSuccess` (`:508-514`) por:
```tsx
      onSuccess: (data) => {
        // Plan 135 F5: "guardado + requiere reinicio" es un ÉXITO con
        // condición — canal warning, nunca el canal de error (antes: :512).
        const outcome = classifyFlagUpdateOutcome(data);
        if (outcome.kind === "warning") {
          setSaveNotice({ variant: "warning", title: "Guardado", body: outcome.message! });
        }
      },
```
- Render: junto a `{apiError && …}` (`:682`), agregar `{saveNotice && <Toast toast={saveNotice} onClose={() => setSaveNotice(null)} />}`. `apiError` queda reservado para errores REALES (sus otros writers no se tocan).

**5.8 — EDITAR `frontend/src/components/devops/FlagGateBanner.tsx`** (caso roto 2, = KPI-4):
- Import: `import { classifyFlagUpdateOutcome } from "../../utils/flagUpdateOutcome";`
- Estado: junto a `error` (`:28`), agregar `const [notice, setNotice] = useState<string | null>(null);`
- `handleActivate` (`:30-50`): reemplazar el cuerpo del `try` (`:34-43`) por:
```tsx
      const result = await HarnessFlags.update({ [flagKey]: true });
      const outcome = classifyFlagUpdateOutcome(result);
      if (outcome.kind === "error") {
        setError(outcome.message);
        return; // sin onEnabled: la flag NO quedó activa
      }
      if (outcome.kind === "warning") {
        setNotice("Flag activada. Requiere reiniciar el backend para aplicar.");
      }
      onEnabled();
```
  y agregar `setNotice(null);` junto al `setError(null);` de `:32`.
- Render: debajo del bloque `{error && …}` (`:67-71`), agregar:
```tsx
      {notice && (
        <div style={{ marginTop: '8px', fontSize: '0.9em', color: '#fcd34d' }} role="status">
          {notice}
        </div>
      )}
```
- Limitación declarada (aceptada): si el `onEnabled()` del padre desmonta el banner en el acto, el aviso no llega a verse — caso hoy teórico (el propio comentario `:40` dice que las flags DevOps no requieren reinicio) y NO se degrada el flujo demorando `onEnabled` (principio 5). Lo que este plan garantiza es que el ÉXITO nunca más se pinta de rojo.

- **Comandos exactos:** `npx tsc --noEmit`; `npx vitest run src/utils/__tests__/flagUpdateOutcome.test.ts` (verde ejecutable); `npx vitest run src/components/__tests__/Toast.test.tsx` (verde, o rojo SOLO por gap RTL).
- **Criterio de aceptación (binario, = KPI-4):** (1) en Ajustes → Arnés, cambiar una flag con `restart_required_keys` → aparece Toast AMARILLO "Guardado / Requiere reiniciar el backend: …", y NADA en el render rojo de `apiError`; (2) los toasts de RecoverExecution/CreateChildTask/PipelineTrigger se ven con el estilo canónico y mensajes/timings idénticos; (3) `grep -n "Guardado. Requiere reiniciar" frontend/src/components/HarnessFlagsPanel.tsx` ya no aparece dentro de `setApiError`.
- **Flag:** no aplica (§3.1). **Impacto por runtime:** ninguno (config UI, agnóstica). **Trabajo del operador: ninguno.**

---

### F6 — GAP 5: los tabs Migrador/DevOps no desaparecen por un parpadeo (usa F0)

**Objetivo (1 frase):** que el veredicto de visibilidad de los tabs opcionales salga SOLO de una respuesta JSON válida, con ≤2 reintentos con backoff ante fallo de red, y sin des-habilitar por un fallo posterior.

**Archivo a EDITAR:** `frontend/src/App.tsx` (2 ediciones):
1. Import: `import { probeFlagHealth, nextEnabledState } from "./utils/flagHealth";`
2. Reemplazar el cuerpo del `useEffect` de `:82-95` EXACTAMENTE por:
```tsx
  useEffect(() => {
    initPreferences();
    initUiSections();
    // Plan 135 F6: solo un JSON válido con flag_enabled===true|false es
    // veredicto. Fallo de red/parseo => retry (≤2, backoff) y, si persiste,
    // "unknown" que CONSERVA el estado previo (nextEnabledState) en vez de
    // ocultar el tab toda la sesión. La desactivación real de la flag
    // (JSON ok con flag_enabled=false) sigue ocultando el tab, igual que hoy.
    let alive = true;
    void probeFlagHealth("/api/migrator/health").then((v) => {
      if (alive) setMigradorEnabled((prev) => nextEnabledState(prev, v));
    });
    void probeFlagHealth("/api/devops/health").then((v) => {
      if (alive) setDevopsEnabled((prev) => nextEnabledState(prev, v));
    });
    return () => {
      alive = false;
    };
  }, []);
```
El efecto de expulsión de tab (`:132-139`) NO se toca: con el veredicto sticky ya no expulsa por fallos transitorios, y sigue expulsando cuando la flag está realmente OFF.

**Casos borde congelados:** (a) backend sano → 1 fetch por endpoint, mismo veredicto que hoy (comportamiento byte-equivalente); (b) backend tarda en levantar → hasta 3 intentos por endpoint (0 ms, 400 ms, 800 ms de espera previa) antes de rendirse; (c) `unknown` con estado inicial `false` → tab oculto (igual que hoy ante fallo), pero SIN falso `disabled` persistente si el operador recarga cuando el backend ya respondió; (d) este retry NO es una acción de negocio del operador (principio 3): es la misma carga de arranque, endurecida.

- **Comandos exactos:** `npx tsc --noEmit`; `npx vitest run src/utils/__tests__/flagHealth.test.ts` (ya verde desde F0 — acá se re-corre como regresión).
- **Criterio de aceptación (binario, = KPI-5):** (1) tests F0 verdes; (2) manual: con backend arriba y `STACKY_DEVOPS_AGENT_ENABLED=true`, cargar el frontend ANTES de que el backend termine de levantar (o simular primer fetch fallido con DevTools) → el tab DevOps aparece cuando el retry llega; (3) con la flag realmente OFF (JSON `flag_enabled:false`) el tab NO aparece.
- **Flag:** no aplica (§3.1: corrección de robustez sin cambio de semántica ante backend sano). **Impacto por runtime:** ninguno (visibilidad de tabs, agnóstica). **Trabajo del operador: ninguno.**

---

### F7 — GAP 6: guardados nunca más en silencio (patrón `ClientProfileEditor`)

**Objetivo (1 frase):** que un PUT de guardado fallido muestre un banner inline junto al botón Guardar, conservando lo tipeado para reintento de 1 click.

**7.1 — EDITAR `frontend/src/components/AgentConfigModal.tsx`** (4 ediciones):
1. Import: `import { formatLoadErrorMessage } from "../utils/loadError";`
2. Estado: junto a `const [saved, setSaved] = useState(false);` (`:41`), agregar `const [saveError, setSaveError] = useState<string | null>(null);`
3. `handleSave` (`:77-93`): agregar `setSaveError(null);` junto a `setSaving(true);` (`:82`), y reemplazar el catch (`:88-90`):
```tsx
// ANTES
    } catch {
      // ignore -- changes still applied locally
    } finally {
// DESPUÉS
    } catch (e) {
      // Plan 135 F7: el PUT falló — los cambios NO quedaron en el server (al
      // reabrir, el useEffect de carga los pisa). `dirty` se conserva (las
      // limpiezas están en el try, no corren ante throw) => reintento 1-click.
      setSaveError(formatLoadErrorMessage(e));
    } finally {
```
4. Render: inmediatamente ANTES del contenedor de los botones del footer (el bloque que contiene el botón `{saved ? "Guardado" : saving ? "Guardando..." : "Guardar"}`, `:192-201`), agregar:
```tsx
        {saveError && (
          <div role="alert" className={styles.saveError}>
            No se pudo guardar: {saveError}. Tus cambios siguen en el formulario — reintentá con «Guardar».
          </div>
        )}
```
5. EDITAR `frontend/src/components/AgentConfigModal.module.css` — append al final:
```css
/* Plan 135 F7 — guardado fallido visible, cambios conservados. */
.saveError {
  margin: 8px 0;
  padding: 8px 10px;
  border: 1px solid rgba(239, 68, 68, 0.45);
  background: rgba(239, 68, 68, 0.12);
  border-radius: 6px;
  color: #fecaca;
  font-size: 12px;
  overflow-wrap: anywhere;
}
```

**7.2 — EDITAR `frontend/src/components/EditProjectModal.tsx`** (4 ediciones; zona compartida con plan 136, §3.2):
1. Import: `import { formatLoadErrorMessage } from "../utils/loadError";`
2. Estado: junto a `const [savingWorkflow, setSavingWorkflow] = useState<string | null>(null);` (`:57`), agregar:
```tsx
  const [workflowSaveError, setWorkflowSaveError] =
    useState<{ filename: string; message: string } | null>(null);
```
3. `saveWorkflow` (`:118-126`): reemplazar la función completa por:
```tsx
  async function saveWorkflow(filename: string) {
    const wf = workflows[filename];
    if (!wf) return;
    setSavingWorkflow(filename);
    setWorkflowSaveError(null);
    try {
      await Projects.putAgentWorkflow(project.name, filename, wf);
    } catch (e) {
      // Plan 135 F7: antes catch { /* ignore */ } — el operador creía que
      // guardó. El estado local `workflows` se conserva => reintento 1-click.
      setWorkflowSaveError({ filename, message: formatLoadErrorMessage(e) });
    } finally {
      setSavingWorkflow(null);
    }
  }
```
4. Render: inmediatamente DESPUÉS del `</button>` del botón "💾 Guardar workflow" (`:706-709`, dentro de la fila del agente correspondiente), agregar:
```tsx
                      {workflowSaveError?.filename === filename && (
                        <div role="alert" className={styles.saveError}>
                          No se pudo guardar el workflow: {workflowSaveError.message}. Tus cambios siguen en el formulario — reintentá.
                        </div>
                      )}
```
5. EDITAR `frontend/src/components/NewProjectModal.module.css` (es el module que este componente importa, `EditProjectModal.tsx:4` — compartido con NewProjectModal; agregar una clase nueva es inocuo para el otro consumidor): append al final la MISMA regla `.saveError` de 7.1.5.

- **Comando exacto:** `npx tsc --noEmit` → exit 0.
- **Criterio de aceptación (binario):** con el backend devolviendo error en los PUT respectivos (p. ej. backend detenido tras abrir el modal): (1) Guardar en `AgentConfigModal` muestra el banner y al reintentar con backend sano guarda (los toggles NO se perdieron); (2) "💾 Guardar workflow" muestra el banner SOLO en la fila del agente afectado y el formulario conserva los valores. Con backend sano, ambos byte-idénticos a hoy.
- **Flag:** no aplica (§3.1). **Impacto por runtime:** ninguno (config de agentes/proyecto, agnóstica). **Trabajo del operador: ninguno.**

---

### F8 — Verificación global

**Objetivo (1 frase):** demostrar con comandos y un smoke que nada compilable ni ningún flujo feliz se rompió.

- **Comandos exactos** (desde `Stacky Agents/frontend/`), en este orden:
  1. `npx tsc --noEmit` → **binario: exit 0, 0 errores.**
  2. `npx vitest run src/utils/__tests__/loadError.test.ts` → verde.
  3. `npx vitest run src/utils/__tests__/flagHealth.test.ts` → verde.
  4. `npx vitest run src/utils/__tests__/flagUpdateOutcome.test.ts` → verde.
  5. `npx vitest run src/components/__tests__/ActiveRunsPanel.test.tsx` → verde, o rojo SOLO por `Cannot find module '@testing-library/react'`/jsdom (gap preexistente documentado; cualquier otro error SÍ bloquea). Ídem para `LoadErrorState.test.tsx`, `PageErrorBoundary.test.tsx`, `Toast.test.tsx`.
  6. **No correr la suite vitest completa** (regla del repo: tests por archivo).
- **Smoke manual de flujos FELICES (binario, 6 pasos):** con backend sano: (1) board carga y sincroniza igual; (2) Ctrl+K lista y navega igual; (3) lanzar un agente desde el modal y verlo en el panel/dock igual; (4) cancelar un run con backend sano funciona igual (confirm + desaparece); (5) guardar una flag sin restart no muestra nada nuevo; (6) guardar roles de agente y workflow funciona igual.
- **Git (para el implementador):** commits por fase con **pathspec explícito** (`git commit -- <archivos de la fase>`); PROHIBIDO `git add -A`/`git add .` (working tree con WIP ajeno de planes hermanos).
- **Trabajo del operador: ninguno.**

## 5. Paridad de runtimes (documentación explícita)

| Superficie | Codex CLI | Claude Code CLI | GitHub Copilot Pro (y `mock`) |
|---|---|---|---|
| LoadErrorState (F1/F2) | idéntico | idéntico | idéntico — errores de GET, sin noción de runtime |
| Cancel del panel (F3) | idéntico | idéntico | idéntico — `Executions.cancel` es por `execution_id`, agnóstico |
| Cierre del dock (F3) | guard nuevo (cancel esperado) | guard nuevo | **sin cambios**: para runtimes no interactivos `isInteractiveRun` es false (`CodexConsoleDock.tsx:76`) y el cierre nunca cancelaba — sigue byte-idéntico |
| PageErrorBoundary (F4) | idéntico | idéntico | idéntico — contención de render |
| Toast + flags (F5) | idéntico | idéntico | idéntico — config UI |
| Health tabs (F6) | idéntico | idéntico | idéntico — endpoints de health, sin runtime |
| Guardados (F7) | idéntico | idéntico | idéntico — PUT de config |

No hay fallback nuevo que implementar: ninguna fase bifurca por runtime.

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Colisión de líneas con planes 132/134/136 en `ActiveRunsPanel.tsx`/`App.tsx`/`EditProjectModal.tsx` | §3.2: zonas de líneas disjuntas por diseño; re-anclar por TEXTO citado si un hermano aterrizó primero; commits con pathspec explícito |
| `LoadErrorState` tapa datos stale útiles en el board | Predicado congelado `isError && data === undefined` (solo primera carga); ante refetch fallido con datos, el board sigue mostrando datos (F1, caso borde a) |
| El guard de cierre del dock "traba" el cierre si el backend no responde | El botón queda deshabilitado solo durante el intento; al fallar muestra error + Reintentar y Minimizar sigue disponible; el statu quo era peor (run zombie invisible). Caso "run ya terminó" se auto-resuelve con el refetch de 5 s (F3, casos borde) |
| Boundary oculta errores que antes "se veían" en consola | `componentDidCatch` sigue logueando a consola (patrón NodeErrorBoundary `:252-255`); el fallback ADEMÁS lo muestra al operador |
| Unificar toasts cambia posición del de `CreateChildTaskButton`/`PipelineTriggerCard` | Decisión declarada (F5): el look canónico fixed bottom-right ES la unificación pedida; mensajes/timings/disparadores byte-idénticos; los 2 tests de flujo feliz del smoke F8 lo cubren |
| Retry del health-check demora el arranque | Solo ante fallo (backend sano = 1 fetch, 0 esperas); peor caso +1.2 s por endpoint, en paralelo, sin bloquear el render (el efecto ya era async) |
| `restart_required_keys` con shape inesperado | `classifyFlagUpdateOutcome` es total (maneja `null`/`undefined`/lista vacía) y está testeada en F0 |
| Tests RTL no ejecutables hoy | Gap preexistente documentado (`ActiveRunsPanel.test.tsx:12-17`); gate real = `tsc` + 3 suites puras ejecutables + smokes manuales binarios por fase |

## 7. Fuera de scope (prohibido en este plan)

- **Plan 134:** notificaciones/título/badges de awareness de runs y rotulado de filas del `ActiveRunsPanel`.
- **Plan 136:** doble-submit, guards de backdrop, orden atómico de adjuntos, `ConfirmButton` two-step, higiene de cambio de proyecto. El Toast compartido de F5 **NO** migra ningún `window.confirm`.
- **Plan 132:** botón "Ver consola" en el panel.
- Resolver el gap de entorno `@testing-library/react`/jsdom.
- Migrar al Toast compartido cualquier superficie no listada en F5 (adopción incremental: NADIE más está obligado).
- Auto-retry sin click, telemetría de errores, error reporting remoto, cambios de backend, flags nuevas, endpoints nuevos.
- Tocar `EpicFromBriefModal.tsx`, `TicketBoard.tsx` fuera de las 4 ediciones de F1, o cualquier archivo con WIP ajeno no listado.

## 8. Glosario

- **Error mudo:** un `.catch()` que traga el error (`() => {}`) o lo disfraza de estado vacío (`() => setX([])`), dejando al operador sin señal ni acción.
- **`LoadErrorState`:** componente nuevo (F1), hermano de `EmptyState`, para cargas fallidas; siempre ofrece Reintentar cuando hay un mecanismo de recarga.
- **`PageErrorBoundary`:** class component (F4) que contiene throws de render de una página; patrón copiado de `NodeErrorBoundary` (`TicketGraphView.jsx:244`).
- **Toast canónico:** el de `RecoverExecutionButton` (fixed bottom-right, variantes success/warning/error), extraído a `components/Toast.tsx` (F5).
- **Veredicto de health:** resultado de `interpretFlagHealthResponse`: solo JSON válido con `flag_enabled === true|false` decide; todo lo demás es `unknown` y no cambia el estado (F6).
- **Primera carga vs refetch:** en react-query v5, un error de refetch conserva `data`; "carga fallida" para F1/F3 = `isError && data === undefined`.
- **Written-ready:** test RTL escrito y compilable que no puede ejecutarse por el gap de entorno preexistente; queda listo para cuando se resuelva.

## 9. Orden de implementación

1. **F0** — utils puros + 3 suites vitest verdes (fundación de todo).
2. **F1** — `LoadErrorState` + TicketBoard (KPI-1, el caso central).
3. **F2** — 5 superficies restantes del GAP 1.
4. **F3** — cancelaciones (panel + dock) (KPI-2).
5. **F4** — `PageErrorBoundary` (KPI-3).
6. **F5** — Toast compartido + 2 "Guardado-como-error" (KPI-4).
7. **F6** — health-check de tabs (KPI-5; solo depende de F0).
8. **F7** — guardados mudos.
9. **F8** — verificación global (KPI-6).

F3..F7 son independientes entre sí (solo F1/F2 dependen de F1, y F3/F6/F7 de F0): ante un imprevisto, cualquiera puede posponerse sin bloquear el resto. Commit por fase, pathspec explícito.

## 10. Definición de Hecho (DoD) global

- [ ] Los 6 archivos de F0 existen; las 3 suites puras corren VERDES hoy (`npx vitest run` por archivo).
- [ ] `LoadErrorState.tsx` + `.module.css` existen; el board distingue error de vacío (KPI-1 verificado manualmente con backend caído y recuperación con Reintentar sin F5).
- [ ] Las 5 superficies de F2 muestran error visible con backend caído y son byte-idénticas con backend sano (checklist de 5 pasos pasado).
- [ ] Cancelar con fallo muestra aviso inline + Reintentar en el panel; el dock no se desmonta si el cancel de una sesión interactiva viva falla (KPI-2).
- [ ] `PageErrorBoundary` envuelve las 13 páginas en `App.tsx`; el throw de prueba muestra el fallback con el resto de la app viva y se revierte (KPI-3).
- [ ] `Toast.tsx`/`Toast.module.css` existen; los 3 toasts caseros adoptados; "Guardado. Requiere reiniciar…" sale como warning en las 2 superficies (KPI-4); el Toast local y su CSS fueron eliminados de `RecoverExecutionButton`.
- [ ] Health-check de tabs con retry+sticky vía `probeFlagHealth`/`nextEnabledState`; flag realmente OFF sigue ocultando el tab (KPI-5).
- [ ] Los 2 guardados mudos (F7) muestran banner inline y conservan lo tipeado.
- [ ] `npx tsc --noEmit` = 0 errores; tests RTL nuevos verdes o rojos SOLO por el gap preexistente (KPI-6).
- [ ] Smoke de flujos felices F8 (6 pasos) pasado.
- [ ] Diff limitado a los archivos listados en este plan; ningún cambio en backend, flags, endpoints ni en zonas de los planes 132/134/136; commits con pathspec explícito.
