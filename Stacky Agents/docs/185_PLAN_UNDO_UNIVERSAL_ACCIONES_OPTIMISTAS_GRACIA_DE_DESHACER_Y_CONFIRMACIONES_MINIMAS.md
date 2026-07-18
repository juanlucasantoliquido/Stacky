# Plan 185 — Undo universal: acciones optimistas, gracia de deshacer y confirmaciones mínimas

- **Estado:** PROPUESTO v1
- **Fecha:** 2026-07-18
- **Autor:** Pipeline proponer-plan-stacky (arquitecto fallback en sesión principal por límite de cuota del subagente)
- **Serie:** UX/UI (continúa 150/161/162/164/165/172/173/174/175 sin duplicarlos)

## 1. Objetivo y KPI

El dashboard hoy interrumpe al operador con confirmaciones (`confirm(` nativo o flujos two-step) incluso para acciones **reversibles**, y ejecuta las acciones de forma bloqueante. Este plan introduce el patrón **undo universal**: la acción reversible se aplica de forma **optimista e inmediata en la UI**, el efecto real (llamada API / mutación) se **difiere una gracia corta** (default 6 s) y un **toast accesible con botón "Deshacer"** permite cancelarla en un click. Si la gracia expira o el operador navega/cierra, el efecto se **commitea garantizado** (cero pérdidas). Las confirmaciones quedan reservadas para lo **irreversible** (regla de decisión explícita con el diálogo canónico del plan 164). Onboarding: **nulo** — el operador no aprende nada nuevo; solo deja de ver confirmaciones molestas y gana un botón Deshacer.

**KPI / impacto esperado (binarios al cierre):**
- K1: ≥ 2 flujos reales convertidos de confirmación → undo con gracia (F3), verificable por grep.
- K2: 0 acciones perdidas: todo `scheduleUndoable` termina en exactamente uno de {commit, undo}, incluso ante `pagehide` — probado con fake timers y test de flush (F1/F4).
- K3: Ratchet activo: el conteo de `window.confirm(` en `frontend/src` no puede crecer respecto del baseline congelado (F5).
- K4: Toast de undo accesible: `aria-live="polite"`, botón real `<button>`, countdown visible — verificado por greps de F2.

## 2. Por qué ahora / gap que cierra

- El plan **164** (diálogo canónico + confirmaciones) estandariza el CONFIRMAR; no cubre el patrón inverso (deshacer). El plan **175** (acciones rápidas inline) usa two-step confirm para destructivas ("Esta acción no se puede deshacer") y explícitamente NO implementa undo. El plan **174** acelera lecturas (virtualización/prefetch); nadie acelera las **escrituras percibidas**.
- Hay ~15 archivos reales con `confirm(` en `Stacky Agents/frontend/src` (inventario en F3): cada uno es una interrupción evitable cuando la acción tiene inversa.
- Es el eslabón UX que falta entre 162 (formularios), 164 (confirmar irreversible) y 175 (acción rápida): **acción reversible sin fricción, con red de seguridad**.
- Infra ya existente que se reutiliza (no se reinventa): `Toast.tsx` (componente y estado), arnés de flags (`backend/api/harness_flags.py` + `HarnessFlags.list()` en `frontend/src/api/endpoints.ts:909`), patrón baseline/ratchet (`frontend/src/__tests__/uiDebtBaseline.json`).

## 3. Principios y guardarraíles (no negociables)

1. **Human-in-the-loop reforzado:** la gracia NO quita al operador del lazo: la acción la inició él, y el undo le da MÁS control (puede arrepentirse). Nada se auto-inicia; el manager solo difiere lo que el operador ya pidió. Prohibida cualquier autonomía proactiva.
2. **Regla de decisión confirmar-vs-deshacer (codificada en F3):** irreversible o de efecto externo no compensable (borrar ejecución, cancelar run en curso, side-effects remotos en ADO sin inversa) → **diálogo canónico 164 / two-step 175, se mantiene**. Reversible con inversa natural (estado local, toggle, endpoint inverso existente) → **undo con gracia, sin confirmación previa**.
3. **3 runtimes (Codex CLI / Claude Code CLI / Copilot):** N/A-por-diseño — este plan es 100 % frontend + 1 flag de arnés backend; no toca ejecución de agentes ni difiere entre runtimes. Cada fase lo declara igualmente.
4. **Cero trabajo del operador:** flag default **ON** (`STACKY_UNDO_UNIVERSAL_ENABLED`); ninguna de las 4 excepciones duras aplica (no bypasea revisión humana — la acción es iniciada por el operador y cancelable; no es destructiva — al contrario, protege; sin prerequisitos externos; no reduce seguridad). OFF por el panel de flags = comportamiento previo intacto (commit inmediato, sin toast).
5. **Backward-compatible:** `Toast.tsx` se extiende con prop **opcional**; ningún caller existente cambia. Con flag OFF el sistema es un no-op transparente.
6. **Gotchas del repo que TODA fase respeta:**
   - `uiDebtRatchet` (plan 138): los `.tsx` NUEVOS tienen presupuesto CERO de estilo inline — prohibido `style={{...}}`; todo estilo va a `*.module.css` (o ref+effect imperativo si fuera imprescindible).
   - El frontend NO tiene `@testing-library/react` ni jsdom (gap estructural preexistente): los tests nuevos son **vitest de módulos puros** (`.ts`), nunca de render de componentes. Por eso la lógica vive en `services/undoManager.ts` y los componentes quedan finos.
   - vitest se corre **por archivo**: `npx vitest run <ruta>` desde `Stacky Agents/frontend/` (contaminación de orden cross-file conocida).
   - Tests backend nuevos (`test_*.py`) se registran en `HARNESS_TEST_FILES` (en `Stacky Agents/backend/tests/test_harness.py`) o el meta-test se pone rojo.
   - FlagSpec bool con default ON exige entrada en `_CURATED_DEFAULTS_ON` (en `Stacky Agents/backend/config.py`) o rompe `test_default_known_only_for_curated`.
   - En `backend/api/tickets.py`, `config` es el módulo; la instancia de flags es `config.config`.
   - Toda config del operador va por UI (el flag aparece solo en el panel de flags existente; nada env-only).

## 4. Fases

### F0 — Flag de arnés `STACKY_UNDO_UNIVERSAL_ENABLED` (kill-switch, default ON)

- **Objetivo:** dar al sistema un interruptor visible en el panel de flags existente, default ON, sin trabajo del operador.
- **Archivos a editar:**
  - `Stacky Agents/backend/config.py` — agregar el `FlagSpec` y su entrada en `_CURATED_DEFAULTS_ON`.
  - `Stacky Agents/backend/tests/test_harness.py` — registrar el archivo de test nuevo en `HARNESS_TEST_FILES`.
- **Archivos a crear:**
  - `Stacky Agents/backend/tests/test_harness_flags_undo.py`
- **Símbolos exactos:**
  - Flag: `STACKY_UNDO_UNIVERSAL_ENABLED` (bool, default `True`), registrada con el MISMO patrón `FlagSpec` que las flags UI vecinas en `config.py` (buscar el bloque de flags de categoría UI/frontend y replicar estructura exacta: key, description en español, category igual a la de las flags de UI existentes, `requires=None`).
  - Entrada literal `"STACKY_UNDO_UNIVERSAL_ENABLED"` en `_CURATED_DEFAULTS_ON`.
- **Test primero (TDD)** — `test_harness_flags_undo.py`:
  1. `test_undo_flag_exists_default_on`: el registry de flags contiene `STACKY_UNDO_UNIVERSAL_ENABLED` con default `True`.
  2. `test_undo_flag_in_curated_defaults_on`: la key está en `_CURATED_DEFAULTS_ON`.
  3. `test_undo_flag_no_requires`: `requires` es `None` (no depende de otra flag).
- **Comando de verificación (binario):**
  ```
  cd "Stacky Agents/backend" && venv\Scripts\python.exe -m pytest tests/test_harness_flags_undo.py -q
  ```
  Pasa = verde 3/3. Además `venv\Scripts\python.exe -m pytest tests/test_harness.py -q` sigue verde (registro en `HARNESS_TEST_FILES` hecho).
- **Flag:** ella misma; default ON (ninguna excepción dura aplica).
- **Runtimes:** N/A-por-diseño (flag de arnés backend consumida por el dashboard común a los 3 runtimes; no altera ejecución de agentes).
- **Trabajo del operador:** ninguno.

### F1 — Núcleo puro `undoManager.ts` (commit diferido con gracia)

- **Objetivo:** un módulo TS puro, sin React, que agenda acciones con gracia, garantiza commit-o-undo exactamente-una-vez y notifica a la UI.
- **Archivo a crear:** `Stacky Agents/frontend/src/services/undoManager.ts`
- **Archivo de test a crear:** `Stacky Agents/frontend/src/services/__tests__/undoManager.test.ts`
- **API exacta del módulo (exports nombrados):**
  ```ts
  export const DEFAULT_GRACE_MS = 6000;           // clamp duro [2000, 15000]
  export type FlushReason = "expired" | "pagehide" | "replaced" | "manual";
  export interface UndoableSpec {
    id: string;                                   // único por acción lógica
    label: string;                                // texto humano del toast, ej: "Ticket archivado"
    graceMs?: number;                             // default DEFAULT_GRACE_MS, clampeado
    commit: () => void | Promise<void>;           // efecto real (llamada API)
    onUndo?: () => void;                          // revertir la mutación optimista de UI
    onCommitted?: () => void;
    onError?: (e: unknown) => void;               // commit rechazado/lanzó
  }
  export interface PendingUndoable { id: string; label: string; expiresAt: number; }
  export function scheduleUndoable(spec: UndoableSpec): void;
  export function undo(id: string): boolean;      // true si estaba pendiente y se canceló
  export function flushAll(reason: FlushReason): void;  // commitea TODO lo pendiente ya
  export function pending(): PendingUndoable[];   // para el host UI, orden FIFO
  export function subscribe(listener: () => void): () => void;  // devuelve unsubscribe
  export function setBypass(bypass: boolean): void;  // true = flag OFF: commit inmediato, sin toast
  export function _resetForTests(): void;         // limpia estado interno (solo tests)
  ```
- **Semántica exacta (casos borde):**
  1. `scheduleUndoable` con `id` ya pendiente → primero flush del anterior con reason `"replaced"`, después agenda el nuevo.
  2. `undo(id)` después del commit (gracia vencida) → `false`, no llama `onUndo`.
  3. `undo(id)` dos veces → segunda vez `false`.
  4. `commit` que lanza (sync) o rechaza (async) → se invoca `onError(e)`; el manager NO reintenta (el caller decide); la entrada sale de pendientes igual.
  5. `setBypass(true)` → `scheduleUndoable` ejecuta `commit()` inmediato, no agenda, no notifica listeners (comportamiento pre-plan).
  6. `graceMs` fuera de [2000, 15000] → se clampea a ese rango.
  7. Timers con `setTimeout`; `expiresAt = Date.now() + graceMs` (para countdown UI).
  8. `flushAll` es idempotente y sincrónica en su disparo (lanza los `commit()` sin await; los callbacks async siguen su curso).
- **Tests (con `vi.useFakeTimers()` + `_resetForTests()` en `beforeEach`):**
  1. `commit_dispara_al_vencer_gracia` — avanza 6000 ms → `commit` llamado 1 vez, `onCommitted` llamado.
  2. `undo_dentro_de_gracia_cancela` — `undo(id)` a los 3000 ms → `commit` 0 veces, `onUndo` 1 vez, devuelve `true`.
  3. `undo_tarde_devuelve_false` — tras vencer → `false`, `onUndo` 0 veces.
  4. `replaced_flushea_anterior` — mismo `id` dos veces → primer `commit` llamado ya (reason replaced), segundo agendado.
  5. `flushAll_commitea_todo_ya` — 3 pendientes, `flushAll("pagehide")` → 3 commits sin avanzar timers.
  6. `bypass_commit_inmediato` — `setBypass(true)` → commit sincrónico, `pending()` vacío.
  7. `commit_que_lanza_invoca_onError`.
  8. `clamp_de_gracia` — `graceMs: 100` → vence recién a los 2000 ms.
  9. `subscribe_notifica_en_alta_y_baja` — contador de notificaciones ≥ 2.
- **Comando de verificación (binario):**
  ```
  cd "Stacky Agents/frontend" && npx vitest run src/services/__tests__/undoManager.test.ts
  ```
- **Flag:** consumida vía `setBypass` (cableado en F2); el módulo en sí es inerte hasta que alguien lo llame.
- **Runtimes:** N/A-por-diseño (módulo puro del dashboard).
- **Trabajo del operador:** ninguno.

### F2 — UI: `Toast.tsx` con acción opcional + `UndoToastHost.tsx` (accesible, cero inline-style)

- **Objetivo:** mostrar los pendientes como toasts con botón "Deshacer" y countdown, reusando el componente `Toast` existente sin romper callers.
- **Archivos a editar:**
  - `Stacky Agents/frontend/src/components/Toast.tsx` — extender `ToastState` con campo **opcional** `action?: { label: string; onAction: () => void }`; render del botón solo si `action` está presente. Cero cambios a callers existentes (prop opcional).
  - `Stacky Agents/frontend/src/components/Toast.module.css` — clase nueva `.actionButton` (estilo del botón) y `.countdownBar` con `@keyframes undoCountdown` (barra que se vacía en `var(--undo-grace-ms)` vía `animation-duration`).
  - `Stacky Agents/frontend/src/App.tsx` — montar `<UndoToastHost />` una sola vez (junto al resto de hosts globales ya montados en App).
- **Archivos a crear:**
  - `Stacky Agents/frontend/src/components/UndoToastHost.tsx` — se suscribe a `subscribe()` del manager, lee `pending()` y renderiza hasta **3** toasts (FIFO; el resto espera su turno visual pero su gracia corre igual). Contenedor con `aria-live="polite"` y `role="status"`. Cada toast: texto `label`, botón `<button>` "Deshacer" → `undo(id)`, countdown bar. Al montar, hace **una** llamada `HarnessFlags.list()` (símbolo real en `frontend/src/api/endpoints.ts:909`, GET `/api/harness-flags`) y si `STACKY_UNDO_UNIVERSAL_ENABLED` está OFF → `setBypass(true)`; si la llamada falla → default ON (no bloquear UX por red).
  - `Stacky Agents/frontend/src/components/UndoToastHost.module.css` — TODO el estilo del host (posición fija esquina inferior, stack vertical, ancho máx). **Prohibido `style={{}}`** (uiDebtRatchet: presupuesto cero para .tsx nuevos). La duración del countdown se pasa con `ref` + `element.style.setProperty("--undo-grace-ms", ...)` en un `useEffect` (patrón ref+effect permitido), NUNCA con atributo `style` JSX.
  - `Stacky Agents/frontend/src/services/undoToastModel.ts` — lógica pura extraída para test: `export function visibleToasts(pending: PendingUndoable[], max?: number): PendingUndoable[]` (default max 3, FIFO) y `export function remainingRatio(p: PendingUndoable, now: number): number` (0..1, clamp).
- **Test a crear:** `Stacky Agents/frontend/src/services/__tests__/undoToastModel.test.ts`
  1. `visibleToasts_limita_a_3_fifo` — 5 pendientes → devuelve los 3 más antiguos en orden.
  2. `visibleToasts_max_custom`.
  3. `remainingRatio_clamp_0_1` — antes/después de expirar.
- **Comandos de verificación (binarios):**
  ```
  cd "Stacky Agents/frontend" && npx vitest run src/services/__tests__/undoToastModel.test.ts
  cd "Stacky Agents/frontend" && npx tsc --noEmit
  grep -n "aria-live" src/components/UndoToastHost.tsx        (≥1 hit)
  grep -n "style={{" src/components/UndoToastHost.tsx          (0 hits)
  grep -rn "action?" src/components/Toast.tsx                  (≥1 hit, prop opcional)
  ```
- **Flag:** `STACKY_UNDO_UNIVERSAL_ENABLED` (OFF ⇒ bypass total; la UI no muestra nada y todo commitea inmediato).
- **Runtimes:** N/A-por-diseño (UI del dashboard común).
- **Trabajo del operador:** ninguno.

### F3 — Adopción piloto: convertir confirmaciones reversibles reales (≥ 2 flujos)

- **Objetivo:** materializar el valor: menos interrupciones en flujos reales, con la regla confirmar-vs-deshacer aplicada.
- **Inventario REAL (grep `confirm(` en `Stacky Agents/frontend/src`, 2026-07-18) — tabla de trabajo:**
  | Archivo | Acción esperable |
  |---|---|
  | `pages/TicketBoard.tsx` | acciones de tablero sobre tickets locales |
  | `components/EpicChildrenPanel.tsx` | quitar/vincular hijos de épica |
  | `components/ActiveRunsPanel.tsx` | stop/cancel de runs (IRREVERSIBLE → queda con confirm) |
  | `components/AgentHistoryPage.tsx` | limpieza de historial |
  | `components/ConfirmButton.tsx` | primitiva two-step (se conserva para irreversibles) |
  | `components/TopBar.tsx` | acciones globales |
  | `components/EpicFromBriefModal.tsx` | publicación (externa → queda con confirm) |
  | `components/ClientProfileEditor.tsx` | edición de perfil |
  | `pages/FlowConfigPage.tsx` | config de flujo |
  | `components/devops/PipelineBuilderSection.tsx`, `devops/ServersSection.tsx`, `devops/RemoteConsoleSection.tsx`, `devops/ProductionFlow.tsx`, `devops/VariablesSection.tsx` | operaciones DevOps (remotas → quedan con confirm salvo inversa local obvia) |
  | `components/dbcompare/EnvironmentsPanel.tsx` | entornos DB Compare |
- **Procedimiento EXACTO para el implementador (sin inferencia):**
  1. Abrí `pages/TicketBoard.tsx` y `components/EpicChildrenPanel.tsx` (los 2 pilotos obligatorios). Localizá cada llamada `confirm(`.
  2. Aplicá el **criterio binario de reversibilidad**: la acción es convertible ⇔ (a) muta solo estado local/DB local del dashboard, y (b) existe operación inversa ya implementada (re-abrir, re-vincular, toggle) invocable con los mismos datos que ya tiene el componente. Si no cumple ambas, NO la convierta (déjala con confirm/askConfirm).
  3. Por cada acción convertible: eliminá el `confirm(...)`; aplicá la mutación optimista de UI que ya hace el happy-path; envolvé la llamada API en `scheduleUndoable({ id: "<dominio>:<id-entidad>", label: "<pasado humano, ej. 'Hijo desvinculado'>", commit: <llamada API existente>, onUndo: <revertir estado local> })`.
  4. Si en un piloto NINGUNA acción cumple el criterio (posible: son todas remotas/irreversibles), registralo como comentario en el mensaje de commit y tomá el siguiente archivo de la tabla que sí tenga una acción reversible, hasta lograr **≥ 2 conversiones totales**.
  5. PROHIBIDO convertir: cancelar/stop de runs, borrados remotos (ADO/GitLab), publicaciones externas, cualquier acción marcada "no se puede deshacer".
- **Criterio de aceptación (binario):**
  ```
  cd "Stacky Agents/frontend" && grep -rn "scheduleUndoable" src --include=*.tsx | wc -l   (≥ 2)
  cd "Stacky Agents/frontend" && npx tsc --noEmit                                          (verde)
  ```
- **Flag:** `STACKY_UNDO_UNIVERSAL_ENABLED` (OFF ⇒ bypass: la acción commitea inmediata, indistinguible del pre-plan salvo la ausencia del confirm eliminado; esto es aceptado y documentado: el confirm removido era fricción, no seguridad, por definición del criterio de reversibilidad).
- **Runtimes:** N/A-por-diseño.
- **Trabajo del operador:** ninguno.

### F4 — Garantía de no-pérdida: flush en `pagehide`/`visibilitychange` y unmount

- **Objetivo:** que ninguna acción diferida se pierda al cerrar pestaña, recargar o cambiar de app.
- **Archivo a editar:** `Stacky Agents/frontend/src/components/UndoToastHost.tsx`
- **Cambio exacto:** en un `useEffect` del host registrar:
  ```ts
  const flush = () => flushAll("pagehide");
  window.addEventListener("pagehide", flush);
  const onVis = () => { if (document.visibilityState === "hidden") flushAll("pagehide"); };
  document.addEventListener("visibilitychange", onVis);
  return () => { window.removeEventListener("pagehide", flush);
                 document.removeEventListener("visibilitychange", onVis);
                 flushAll("manual"); };  // unmount del host también commitea
  ```
- **Nota de límite (honesta, va como comentario en el código):** commits async lanzados durante `pagehide` pueden no completarse si el browser mata el proceso; mitigación real = los callers usan el api-client existente (fetch) y la gracia es corta. `keepalive`/`sendBeacon` queda FUERA de scope (ver §6).
- **Test:** ya cubierto por `flushAll_commitea_todo_ya` en F1 (la lógica es del manager); para el wiring, criterio por grep:
  ```
  grep -n "pagehide" src/components/UndoToastHost.tsx          (≥2 hits: add+remove)
  grep -n "visibilitychange" src/components/UndoToastHost.tsx  (≥2 hits)
  ```
- **Flag / Runtimes / Operador:** igual que F2 (misma flag; N/A; ninguno).

### F5 — Ratchet anti-regresión de confirmaciones

- **Objetivo:** impedir que vuelvan a crecer los `confirm(` nativos (la deuda solo baja), con el patrón baseline ya usado por el repo (`uiDebtBaseline.json`, `motionDebtBaseline.json`).
- **Archivos a crear:**
  - `Stacky Agents/frontend/src/__tests__/undoConfirmBaseline.json` — `{ "windowConfirmCalls": <N> }` donde `<N>` es el conteo real medido AL IMPLEMENTAR esta fase (después de F3, por eso F5 va última). No inventar el número: medirlo con el mismo scanner del test y congelarlo.
  - `Stacky Agents/frontend/src/__tests__/undoConfirmRatchet.test.ts` — test vitest puro que:
    1. Recorre recursivamente `src/**/*.{ts,tsx}` con `fs` de Node (mismo estilo que el test de uiDebt existente; leerlo y replicar su walker).
    2. Cuenta ocurrencias de la subcadena `window.confirm(` y del patrón regex `[^.\w]confirm\(` (confirm global sin receptor).
    3. Excluye: el propio archivo de test, `undoConfirmBaseline.json`, y cualquier identificador `askConfirm` (patrón del plan 164/175 — NO es deuda).
    4. Falla si `conteo > baseline.windowConfirmCalls`; si `conteo < baseline`, falla con mensaje "bajá el baseline a <conteo>" (ratchet de una vía, mismo contrato que uiDebt).
- **Cuidado gotcha conocido (prosa-vs-gate):** el scanner mira SOLO `frontend/src`; este documento vive en `docs/` y no colisiona. El test se auto-excluye por ruta exacta.
- **Comando de verificación (binario):**
  ```
  cd "Stacky Agents/frontend" && npx vitest run src/__tests__/undoConfirmRatchet.test.ts
  ```
- **Flag:** ninguna (es un test estático; no hay comportamiento runtime que apagar). Default N/A.
- **Runtimes:** N/A-por-diseño (test de repo).
- **Trabajo del operador:** ninguno.

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Doble ejecución del efecto (commit corre dos veces) | contrato exactamente-una-vez del manager + tests 1/4/5 de F1 (replaced/flush no re-commitean lo ya commiteado) |
| Pérdida de acción al cerrar la pestaña | F4 `pagehide`+`visibilitychange`+unmount → `flushAll`; gracia corta (≤15 s) acota la ventana |
| Convertir por error una acción irreversible | criterio binario de reversibilidad en F3 + lista PROHIBIDO explícita + ratchet F5 no fuerza conversiones |
| Romper callers existentes de `Toast` | prop `action` **opcional**; tsc --noEmit como gate en F2/F3 |
| Ratchet propio mal calibrado (rojo perpetuo) | baseline se MIDE con el mismo scanner al implementar F5 (no se estima); contrato de una vía igual a uiDebt ya probado en el repo |
| Flag OFF deja flujos convertidos sin confirm ni gracia | aceptado y documentado en F3: solo se convierten acciones cuyo confirm era fricción (reversibles por criterio); OFF = pre-plan menos ese confirm |
| Sesión paralela activa en el repo | este plan es un doc nuevo standalone; la implementación crea archivos nuevos + ediciones acotadas (Toast/App/2 pilotos); commit con pathspec explícito |

## 6. Fuera de scope (explícito)

- Undo multi-nivel / historial de undo (stack): solo gracia simple por acción.
- Undo server-side con ledger/compensaciones (transaccionalidad ADO es del plan 153).
- `navigator.sendBeacon` / `fetch keepalive` en pagehide.
- Conversión masiva de TODOS los confirms (solo pilotos ≥2 + ratchet; el resto migra orgánicamente en planes futuros).
- Cola offline/retry de commits fallidos (el caller maneja `onError` como ya maneja errores de esa API).
- Telemetría de undo-rate (encaja en el plan 171 cuando se implemente).

## 7. Glosario (para el modelo implementador)

- **Arnés / FlagSpec:** registro central de feature-flags del backend (`backend/config.py`); se exponen por `GET /api/harness-flags` y se administran SOLO por UI (`HarnessFlagsPanel.tsx`).
- **`_CURATED_DEFAULTS_ON`:** allowlist en `config.py`; toda flag bool con default `True` DEBE estar ahí o `test_default_known_only_for_curated` falla.
- **`HARNESS_TEST_FILES`:** lista en `backend/tests/test_harness.py`; todo `test_*.py` nuevo del backend debe registrarse ahí.
- **uiDebtRatchet:** test existente que congela deuda de estilo inline; los `.tsx` nuevos tienen presupuesto 0 (`style={{}}` prohibido).
- **askConfirm:** API de confirmación del diálogo canónico (plan 164, usada por 175). NO es deuda; el ratchet F5 la excluye.
- **Acción optimista:** la UI refleja el resultado ANTES de que el efecto real corra; si el operador deshace, la UI se revierte con `onUndo`.
- **Gracia:** ventana (default 6 s) entre la acción del operador y el commit real, durante la cual el toast ofrece "Deshacer".
- **Bypass:** modo del manager cuando la flag está OFF: commit inmediato, cero toasts, comportamiento pre-plan.

## 8. Orden de implementación

1. F0 — flag + tests backend (registro en `HARNESS_TEST_FILES` incluido).
2. F1 — `undoManager.ts` con sus 9 tests (TDD: tests primero).
3. F2 — `undoToastModel.ts` + tests; extensión `Toast.tsx`; `UndoToastHost.tsx` + css; montaje en `App.tsx`; wiring de flag.
4. F3 — pilotos de conversión (≥2) con criterio de reversibilidad.
5. F4 — flush `pagehide`/`visibilitychange`/unmount.
6. F5 — baseline medido + `undoConfirmRatchet.test.ts`.

## 9. Definición de Hecho (DoD) global

- [ ] `pytest tests/test_harness_flags_undo.py` y `pytest tests/test_harness.py` verdes (venv del backend).
- [ ] `npx vitest run src/services/__tests__/undoManager.test.ts` verde (9/9).
- [ ] `npx vitest run src/services/__tests__/undoToastModel.test.ts` verde (3/3).
- [ ] `npx vitest run src/__tests__/undoConfirmRatchet.test.ts` verde con baseline medido.
- [ ] `npx tsc --noEmit` verde en `Stacky Agents/frontend`.
- [ ] `grep -rn "scheduleUndoable" src --include=*.tsx | wc -l` ≥ 2.
- [ ] `grep -n "style={{" src/components/UndoToastHost.tsx` = 0 hits.
- [ ] Flag `STACKY_UNDO_UNIVERSAL_ENABLED` visible en el panel de flags, default ON; con OFF el dashboard se comporta como pre-plan (verificación manual de 1 minuto del operador, opcional, no bloqueante).
- [ ] Ningún confirm de acción irreversible fue removido (revisión del diff de F3 contra la lista PROHIBIDO).
