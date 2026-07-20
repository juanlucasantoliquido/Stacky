# Plan 185 — Undo universal: acciones optimistas, gracia de deshacer y confirmaciones mínimas

- **Estado:** CRITICADO v2 (v1 → v2 aplicada; veredicto v1: RECHAZADO por C1)
- **Fecha:** 2026-07-18 (v1 y v2 el mismo día)
- **Autor:** Pipeline proponer-plan-stacky + criticar-y-mejorar-plan (ambos inline en la sesión principal: subagente arquitecto no disponible por límite de cuota)
- **Serie:** UX/UI (continúa 150/161/162/164/165/172/173/174/175 sin duplicarlos)

## CHANGELOG v1 → v2 (crítica C1..C9)

- **C1 (BLOQUEANTE, resuelto):** F2 decía "si el flag está OFF" sin especificar CÓMO resolverlo en la respuesta de `HarnessFlags.list()`. Ahora el lookup es literal con los campos REALES de `HarnessFlagView` (`key`, `value` — verificados en `frontend/src/api/endpoints.ts:703-711`).
- **C2 (IMPORTANTE, resuelto):** contradicción de accesibilidad — el host pedía `aria-live="polite"` conteniendo `Toast`s que ya son `role="alert"` + `aria-live="assertive"` (Toast.tsx:30-31). v2: la accesibilidad la aporta `Toast`; el host NO declara live-region; diff EXACTO de `Toast.tsx` incluido; `variant: "success"` literal; gate K4 re-apuntado.
- **C3 (IMPORTANTE, resuelto):** carrera de commits — `replaced`/`flushAll` podían despachar dos commits del mismo id fuera de orden. v2: serialización por id con cadena de promesas + test 10.
- **C4 (IMPORTANTE, resuelto):** `visibleToasts` FIFO ocultaba la acción MÁS reciente (la que el operador más quiere deshacer). v2: newest-first (LIFO), cap 4.
- **C5 (IMPORTANTE, resuelto):** F0 no decía cómo accede el test al registry de flags (gotcha `config` módulo vs `config.config`). v2: espejar el test vecino existente `backend/tests/test_harness_flags_requires.py`.
- **C6 (MENOR, resuelto):** staleness del flag documentada (se lee al montar; toggle aplica al próximo reload).
- **C7 (MENOR, resuelto):** key del baseline renombrada a `confirmCallCount` con definición exacta de la suma (dos patrones disjuntos, sin doble conteo).
- **C8 (MENOR, resuelto):** shell declarado por comando (PowerShell para pytest; Git Bash para gates grep).
- **C9 (MENOR, resuelto):** nota StrictMode/double-mount en F4 (unmount fantasma con cero pendientes = inocuo).
- **[ADICIÓN ARQUITECTO]:** atajo global **Ctrl+Z** que deshace el pendiente más reciente mientras su toast está visible (guard de foco; helper puro `shouldHandleUndoKey` testeable; sin dependencia del plan 172 no implementado, con nota de migración a su registry cuando exista) + API `undoLatest()` en el manager.

## 1. Objetivo y KPI

El dashboard hoy interrumpe al operador con confirmaciones (`confirm(` nativo o flujos two-step) incluso para acciones **reversibles**, y ejecuta las acciones de forma bloqueante. Este plan introduce el patrón **undo universal**: la acción reversible se aplica de forma **optimista e inmediata en la UI**, el efecto real (llamada API / mutación) se **difiere una gracia corta** (default 6 s) y un **toast con botón "Deshacer"** permite cancelarla en un click (o con **Ctrl+Z**). Si la gracia expira o el operador navega/cierra, el efecto se **commitea garantizado** (cero pérdidas). Las confirmaciones quedan reservadas para lo **irreversible** (regla de decisión explícita con el diálogo canónico del plan 164). Onboarding: **nulo** — el operador no aprende nada nuevo; solo deja de ver confirmaciones molestas y gana un botón Deshacer.

**KPI / impacto esperado (binarios al cierre):**
- K1: ≥ 2 flujos reales convertidos de confirmación → undo con gracia (F3), verificable por grep.
- K2: 0 acciones perdidas y 0 commits duplicados o fuera de orden por id: todo `scheduleUndoable` termina en exactamente uno de {commit, undo}, los commits del mismo id se serializan, incluso ante `pagehide` — probado con fake timers (F1/F4).
- K3: Ratchet activo: el conteo de llamadas confirm nativas en `frontend/src` no puede crecer respecto del baseline congelado (F5).
- K4: Toast de undo accesible vía el `Toast` de la casa (`role="alert"`, Toast.tsx:30) + botón real `<button>` de acción + countdown visible — verificado por los greps de F2.
- K5: Ctrl+Z deshace el pendiente más reciente con guard de foco — helper puro con tests (F2).

## 2. Por qué ahora / gap que cierra

- El plan **164** (diálogo canónico + confirmaciones) estandariza el CONFIRMAR; no cubre el patrón inverso (deshacer). El plan **175** (acciones rápidas inline) usa two-step confirm para destructivas ("Esta acción no se puede deshacer") y explícitamente NO implementa undo. El plan **174** acelera lecturas (virtualización/prefetch); nadie acelera las **escrituras percibidas**.
- Hay ~15 archivos reales con `confirm(` en `Stacky Agents/frontend/src` (inventario en F3): cada uno es una interrupción evitable cuando la acción tiene inversa.
- Es el eslabón UX que falta entre 162 (formularios), 164 (confirmar irreversible) y 175 (acción rápida): **acción reversible sin fricción, con red de seguridad**.
- Infra ya existente que se reutiliza (no se reinventa): `Toast.tsx` (canal de la casa para resultados de ACCIONES, plan 135 F5, controlado por el caller — no singleton), arnés de flags (`backend/api/harness_flags.py` + `HarnessFlags.list()` en `frontend/src/api/endpoints.ts:909`), patrón baseline/ratchet (`frontend/src/__tests__/uiDebtBaseline.json`).

## 3. Principios y guardarraíles (no negociables)

1. **Human-in-the-loop reforzado:** la gracia NO quita al operador del lazo: la acción la inició él, y el undo le da MÁS control (puede arrepentirse). Nada se auto-inicia; el manager solo difiere lo que el operador ya pidió. Prohibida cualquier autonomía proactiva.
2. **Regla de decisión confirmar-vs-deshacer (codificada en F3):** irreversible o de efecto externo no compensable (borrar ejecución, cancelar run en curso, side-effects remotos en ADO sin inversa) → **diálogo canónico 164 / two-step 175, se mantiene**. Reversible con inversa natural (estado local, toggle, endpoint inverso existente) → **undo con gracia, sin confirmación previa**.
3. **3 runtimes (Codex CLI / Claude Code CLI / Copilot):** N/A-por-diseño — este plan es 100 % frontend + 1 flag de arnés backend; no toca ejecución de agentes ni difiere entre runtimes. Cada fase lo declara igualmente.
4. **Cero trabajo del operador:** flag default **ON** (`STACKY_UNDO_UNIVERSAL_ENABLED`); ninguna de las 4 excepciones duras aplica (no bypasea revisión humana — la acción es iniciada por el operador y cancelable; no es destructiva — al contrario, protege; sin prerequisitos externos; no reduce seguridad). OFF por el panel de flags = comportamiento previo intacto (commit inmediato, sin toast).
5. **Backward-compatible:** `Toast.tsx` se extiende con prop **opcional** (diff exacto en F2); ningún caller existente cambia. Con flag OFF el sistema es un no-op transparente.
6. **Shells de los comandos (C8):** los comandos `pytest` se corren en **PowerShell** desde `Stacky Agents/backend` con `venv\Scripts\python.exe`; los comandos `npx` en PowerShell o Git Bash desde `Stacky Agents/frontend`; los gates con `grep`/`wc` se corren en **Git Bash** desde `Stacky Agents/frontend`.
7. **Gotchas del repo que TODA fase respeta:**
   - `uiDebtRatchet` (plan 138): los `.tsx` NUEVOS tienen presupuesto CERO de estilo inline — prohibido `style={{...}}`; todo estilo va a `*.module.css`; los valores dinámicos (countdown) van por `ref` + `el.style.setProperty(...)` en `useEffect` (patrón ref+effect permitido).
   - El frontend NO tiene `@testing-library/react` ni jsdom (gap estructural preexistente): los tests nuevos son **vitest de módulos puros** (`.ts`), nunca de render de componentes. Por eso la lógica vive en `services/` y los componentes quedan finos.
   - vitest se corre **por archivo**: `npx vitest run <ruta>` desde `Stacky Agents/frontend/` (contaminación de orden cross-file conocida).
   - Tests backend nuevos (`test_*.py`) se registran en `HARNESS_TEST_FILES` (en `Stacky Agents/backend/tests/test_harness.py`) o el meta-test se pone rojo.
   - FlagSpec bool con default ON exige entrada en `_CURATED_DEFAULTS_ON` (en `Stacky Agents/backend/config.py`) o rompe `test_default_known_only_for_curated`.
   - En `backend/api/tickets.py`, `config` es el módulo; la instancia de flags es `config.config` (por eso F0 espeja el acceso del test vecino, C5).
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
  - Flag: `STACKY_UNDO_UNIVERSAL_ENABLED` (bool, default `True`), registrada con el MISMO patrón `FlagSpec` que las flags UI vecinas en `config.py` (abrir el bloque de flags de categoría UI/frontend y replicar estructura exacta: key, description en español, category igual a la de las flags de UI existentes, `requires=None`).
  - Entrada literal `"STACKY_UNDO_UNIVERSAL_ENABLED"` en `_CURATED_DEFAULTS_ON`.
- **Cómo accede el test al registry (C5, sin inferencia):** abrir `Stacky Agents/backend/tests/test_harness_flags_requires.py` (existe) y REPLICAR su forma exacta de importar y consultar flags/specs (mismo import, misma función de acceso). No usar `getattr(config, FLAG)` sobre el módulo (gotcha conocido: devuelve siempre el default).
- **Test primero (TDD)** — `test_harness_flags_undo.py`:
  1. `test_undo_flag_exists_default_on`: el registry contiene `STACKY_UNDO_UNIVERSAL_ENABLED` con default `True`.
  2. `test_undo_flag_in_curated_defaults_on`: la key está en `_CURATED_DEFAULTS_ON`.
  3. `test_undo_flag_no_requires`: `requires` es `None`.
- **Comando de verificación (binario, PowerShell desde `Stacky Agents/backend`):**
  ```
  venv\Scripts\python.exe -m pytest tests/test_harness_flags_undo.py -q
  venv\Scripts\python.exe -m pytest tests/test_harness.py -q
  ```
  Pasa = ambos verdes (el segundo prueba el registro en `HARNESS_TEST_FILES`).
- **Flag:** ella misma; default ON (ninguna excepción dura aplica).
- **Runtimes:** N/A-por-diseño (flag de arnés backend consumida por el dashboard común a los 3 runtimes; no altera ejecución de agentes).
- **Trabajo del operador:** ninguno.

### F1 — Núcleo puro `undoManager.ts` (commit diferido con gracia, exactamente-una-vez, serializado por id)

- **Objetivo:** un módulo TS puro, sin React, que agenda acciones con gracia, garantiza commit-o-undo exactamente-una-vez, serializa commits por id (C3) y notifica a la UI.
- **Archivo a crear:** `Stacky Agents/frontend/src/services/undoManager.ts`
- **Archivo de test a crear:** `Stacky Agents/frontend/src/services/__tests__/undoManager.test.ts`
- **API exacta del módulo (exports nombrados):**
  ```ts
  export const DEFAULT_GRACE_MS = 6000;           // clamp duro [2000, 15000]
  export type FlushReason = "expired" | "pagehide" | "replaced" | "manual";
  export interface UndoableSpec {
    id: string;                                   // único por acción lógica, formato "<dominio>:<id-entidad>"
    label: string;                                // texto humano del toast, ej: "Ticket archivado"
    graceMs?: number;                             // default DEFAULT_GRACE_MS, clampeado
    commit: () => void | Promise<void>;           // efecto real (llamada API)
    onUndo?: () => void;                          // revertir la mutación optimista de UI
    onCommitted?: () => void;
    onError?: (e: unknown) => void;               // commit rechazado/lanzó
  }
  export interface PendingUndoable { id: string; label: string; createdAt: number; expiresAt: number; }
  export function scheduleUndoable(spec: UndoableSpec): void;
  export function undo(id: string): boolean;      // true si estaba pendiente y se canceló
  export function undoLatest(): boolean;          // [ADICIÓN ARQUITECTO] deshace el pendiente MÁS reciente; false si no hay
  export function flushAll(reason: FlushReason): void;  // commitea TODO lo pendiente ya
  export function pending(): PendingUndoable[];   // orden de creación ascendente (el host reordena)
  export function subscribe(listener: () => void): () => void;  // devuelve unsubscribe
  export function setBypass(bypass: boolean): void;  // true = flag OFF: commit inmediato, sin toast
  export function _resetForTests(): void;         // limpia estado interno y cadenas por id (solo tests)
  ```
- **Semántica exacta (casos borde):**
  1. `scheduleUndoable` con `id` ya pendiente → primero flush del anterior con reason `"replaced"`, después agenda el nuevo.
  2. **Serialización por id (C3):** el manager mantiene `Map<string, Promise<void>>` (`commitChains`); TODO despacho de `commit` para un id se encadena: `const prev = chains.get(id) ?? Promise.resolve(); const next = prev.then(() => spec.commit()).then(() => spec.onCommitted?.(), (e) => spec.onError?.(e)); chains.set(id, next.then(() => {}, () => {}));`. Commits de ids distintos corren en paralelo; del mismo id, en orden de despacho.
  3. `undo(id)` después del commit (gracia vencida) → `false`, no llama `onUndo`.
  4. `undo(id)` dos veces → segunda vez `false`.
  5. `undoLatest()` → aplica `undo` sobre el pendiente de `createdAt` más alto; `false` si `pending()` está vacío.
  6. `commit` que lanza (sync) o rechaza (async) → se invoca `onError(e)`; el manager NO reintenta (el caller decide); la entrada sale de pendientes igual.
  7. `setBypass(true)` → `scheduleUndoable` despacha el commit por la MISMA cadena por id (la serialización se conserva), no agenda, no notifica listeners.
  8. `graceMs` fuera de [2000, 15000] → se clampea a ese rango.
  9. Timers con `setTimeout`; `createdAt = Date.now()`, `expiresAt = createdAt + graceMs` (para countdown UI).
  10. `flushAll` es idempotente; despacha por las cadenas por id sin await global.
- **Tests (con `vi.useFakeTimers()` + `_resetForTests()` en `beforeEach`):**
  1. `commit_dispara_al_vencer_gracia` — avanza 6000 ms → `commit` 1 vez, `onCommitted` llamado.
  2. `undo_dentro_de_gracia_cancela` — `undo(id)` a los 3000 ms → `commit` 0 veces, `onUndo` 1 vez, devuelve `true`.
  3. `undo_tarde_devuelve_false` — tras vencer → `false`, `onUndo` 0 veces.
  4. `replaced_flushea_anterior` — mismo `id` dos veces → primer `commit` despachado (reason replaced), segundo agendado.
  5. `flushAll_commitea_todo_ya` — 3 pendientes, `flushAll("pagehide")` → 3 commits sin avanzar timers.
  6. `bypass_commit_inmediato` — `setBypass(true)` → commit despachado, `pending()` vacío, listeners 0 notificaciones.
  7. `commit_que_lanza_invoca_onError`.
  8. `clamp_de_gracia` — `graceMs: 100` → vence recién a los 2000 ms.
  9. `subscribe_notifica_en_alta_y_baja` — contador ≥ 2.
  10. `replaced_serializa_commits_mismo_id` (C3) — commit A devuelve promesa que resuelve tarde; se agenda B (mismo id) y se flushea; ORDEN observado en un array: A resuelve ANTES de que B ejecute.
  11. `undoLatest_deshace_el_mas_reciente` — 2 pendientes → `undoLatest()` cancela el segundo; el primero sigue pendiente.
- **Comando de verificación (binario, desde `Stacky Agents/frontend`):**
  ```
  npx vitest run src/services/__tests__/undoManager.test.ts
  ```
- **Flag:** consumida vía `setBypass` (cableado en F2); el módulo en sí es inerte hasta que alguien lo llame.
- **Runtimes:** N/A-por-diseño (módulo puro del dashboard).
- **Trabajo del operador:** ninguno.

### F2 — UI: `Toast.tsx` con acción opcional + `UndoToastHost.tsx` + Ctrl+Z (cero inline-style)

- **Objetivo:** mostrar los pendientes como toasts de la casa con botón "Deshacer", countdown y atajo Ctrl+Z, sin romper ningún caller existente.
- **Diff EXACTO de `Stacky Agents/frontend/src/components/Toast.tsx` (C2 — prop opcional, backward-compatible):**
  ```ts
  export interface ToastState {
    variant: ToastVariant;
    title?: string;
    body: string;
    correlationId?: string;
    action?: { label: string; onAction: () => void };   // NUEVO, opcional
  }
  ```
  y en el JSX, inmediatamente DESPUÉS de `<p className={styles.toastBody}>{toast.body}</p>` (Toast.tsx:47):
  ```tsx
  {toast.action ? (
    <button className={styles.toastAction} onClick={toast.action.onAction}>
      {toast.action.label}
    </button>
  ) : null}
  ```
  `Toast` ya trae `role="alert"` + `aria-live="assertive"` (Toast.tsx:30-31): NO agregar live-region en ningún otro lado (C2).
- **Archivos a editar además:**
  - `Stacky Agents/frontend/src/components/Toast.module.css` — clase nueva `.toastAction` (botón, estilo alineado a `.toastClose` existente).
  - `Stacky Agents/frontend/src/App.tsx` — montar `<UndoToastHost />` una sola vez, junto a los hosts globales ya montados.
- **Archivos a crear:**
  - `Stacky Agents/frontend/src/components/UndoToastHost.tsx` — comportamiento EXACTO:
    1. Se suscribe con `subscribe()` y lee `pending()`; calcula visibles con `visibleToasts(...)` (newest-first, cap 4 — C4).
    2. Renderiza cada visible como `<Toast toast={{ variant: "success", body: p.label, action: { label: "Deshacer", onAction: () => undo(p.id) } }} onClose={() => dismiss(p.id)} />` donde `dismiss` solo OCULTA el toast localmente (estado `dismissed: Set<string>` del host); la gracia sigue corriendo hasta su commit normal (cerrar ≠ deshacer; cero API nueva, cero pérdida).
    3. Envuelve cada `Toast` en `<div className={styles.item}>` con una barra `<div className={styles.countdownBar} ref={...} />`; la duración se setea con `el.style.setProperty("--undo-grace-ms", String(p.expiresAt - p.createdAt) + "ms")` en `useEffect` (ratchet: prohibido `style={{}}`).
    4. Al montar, llama `HarnessFlags.list()` (símbolo real, `frontend/src/api/endpoints.ts:909`, GET `/api/harness-flags`) UNA vez y resuelve el flag ASÍ (C1, literal):
       ```ts
       const res = await HarnessFlags.list();
       const flag = res.flags.find(f => f.key === "STACKY_UNDO_UNIVERSAL_ENABLED");
       if (flag && flag.value === false) setBypass(true);   // ausente o error de red ⇒ queda ON
       ```
    5. **Staleness aceptada (C6):** el flag se lee solo al montar; un toggle del operador aplica al próximo reload del dashboard (mismo contrato que las flags `restart_required` del arnés). Documentarlo en comentario del host.
    6. **[ADICIÓN ARQUITECTO] Ctrl+Z global:** `useEffect` que registra `window.addEventListener("keydown", handler)`; `handler` llama al helper puro `shouldHandleUndoKey(ev, document.activeElement ...)` y, si devuelve `true`, hace `ev.preventDefault(); undoLatest();`. Cuando el plan 172 (registry de atajos) se implemente, este listener migra a ese registry — nota en comentario; hasta entonces es un listener directo sin dependencias.
  - `Stacky Agents/frontend/src/components/UndoToastHost.module.css` — posición fija esquina inferior derecha, stack vertical, ancho máx 360px, clases `.host`, `.item`, `.countdownBar` con `@keyframes undoCountdown` (`animation-duration: var(--undo-grace-ms)`), sin tocar estilos globales.
  - `Stacky Agents/frontend/src/services/undoToastModel.ts` — lógica pura:
    ```ts
    export function visibleToasts(pending: PendingUndoable[], max = 4): PendingUndoable[];
    // newest-first por createdAt DESC, cap max (C4)
    export function remainingRatio(p: PendingUndoable, now: number): number; // 0..1 clamp
    export function shouldHandleUndoKey(
      ev: { key: string; ctrlKey: boolean; metaKey: boolean; altKey: boolean; shiftKey: boolean },
      active: { tagName: string; isContentEditable: boolean } | null
    ): boolean;
    // true ⇔ (ctrlKey || metaKey) && !altKey && !shiftKey && key.toLowerCase()==="z"
    //        && active no es INPUT/TEXTAREA/SELECT ni isContentEditable
    ```
- **Test a crear:** `Stacky Agents/frontend/src/services/__tests__/undoToastModel.test.ts`
  1. `visibleToasts_newest_first_cap_4` — 6 pendientes → devuelve los 4 de `createdAt` más alto, descendente (C4).
  2. `visibleToasts_max_custom`.
  3. `remainingRatio_clamp_0_1` — antes/después de expirar.
  4. `shouldHandleUndoKey_true_ctrl_z_fuera_de_inputs`.
  5. `shouldHandleUndoKey_false_en_input_textarea_select_contenteditable`.
  6. `shouldHandleUndoKey_false_con_shift_o_alt` (no captura Ctrl+Shift+Z/redo ni combos ajenos).
- **Comandos de verificación (binarios):**
  ```
  npx vitest run src/services/__tests__/undoToastModel.test.ts     (desde Stacky Agents/frontend)
  npx tsc --noEmit                                                  (desde Stacky Agents/frontend)
  ```
  y en Git Bash desde `Stacky Agents/frontend`:
  ```
  grep -n "toastAction" src/components/Toast.tsx                    (≥1 hit — botón de acción presente)
  grep -n "aria-live" src/components/UndoToastHost.tsx              (0 hits — C2: la live-region la da Toast)
  grep -n "style={{" src/components/UndoToastHost.tsx               (0 hits — ratchet)
  grep -n "shouldHandleUndoKey" src/components/UndoToastHost.tsx    (≥1 hit — Ctrl+Z cableado)
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
  2. Aplicá el **criterio binario de reversibilidad**: la acción es convertible ⇔ (a) muta solo estado local/DB local del dashboard, y (b) existe operación inversa ya implementada (re-abrir, re-vincular, toggle) invocable con los mismos datos que ya tiene el componente. Si no cumple ambas, NO la conviertas (dejala con confirm/askConfirm).
  3. Por cada acción convertible: eliminá el `confirm(...)`; aplicá la mutación optimista de UI que ya hace el happy-path; envolvé la llamada API en `scheduleUndoable({ id: "<dominio>:<id-entidad>", label: "<pasado humano, ej. 'Hijo desvinculado'>", commit: <llamada API existente>, onUndo: <revertir estado local> })`.
  4. Si en un piloto NINGUNA acción cumple el criterio (posible: son todas remotas/irreversibles), registralo como comentario en el mensaje de commit y tomá el siguiente archivo de la tabla que sí tenga una acción reversible, hasta lograr **≥ 2 conversiones totales**.
  5. PROHIBIDO convertir: cancelar/stop de runs, borrados remotos (ADO/GitLab), publicaciones externas, cualquier acción marcada "no se puede deshacer".
- **Criterio de aceptación (binario, Git Bash desde `Stacky Agents/frontend`):**
  ```
  grep -rn "scheduleUndoable" src --include=*.tsx | wc -l   (≥ 2)
  npx tsc --noEmit                                          (verde)
  ```
- **Flag:** `STACKY_UNDO_UNIVERSAL_ENABLED` (OFF ⇒ bypass: la acción commitea inmediata, indistinguible del pre-plan salvo la ausencia del confirm eliminado; aceptado y documentado: el confirm removido era fricción, no seguridad, por definición del criterio de reversibilidad).
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
- **Nota StrictMode (C9, va como comentario en el código):** en dev, React StrictMode monta-desmonta-monta el host al inicio; ese unmount fantasma dispara `flushAll("manual")` con CERO pendientes (no hay acciones aún), así que es inocuo. No agregar guards extra.
- **Nota de límite (honesta, va como comentario en el código):** commits async lanzados durante `pagehide` pueden no completarse si el browser mata el proceso; mitigación real = gracia corta (≤15 s) + api-client existente. `keepalive`/`sendBeacon` queda FUERA de scope (§6).
- **Test:** la lógica es del manager (test 5 de F1); el wiring se verifica por grep (Git Bash desde `Stacky Agents/frontend`):
  ```
  grep -n "pagehide" src/components/UndoToastHost.tsx          (≥2 hits: add+remove)
  grep -n "visibilitychange" src/components/UndoToastHost.tsx  (≥2 hits)
  ```
- **Flag / Runtimes / Operador:** igual que F2 (misma flag; N/A; ninguno).

### F5 — Ratchet anti-regresión de confirmaciones

- **Objetivo:** impedir que vuelvan a crecer los `confirm(` nativos (la deuda solo baja), con el patrón baseline ya usado por el repo (`uiDebtBaseline.json`, `motionDebtBaseline.json`).
- **Archivos a crear:**
  - `Stacky Agents/frontend/src/__tests__/undoConfirmBaseline.json` — `{ "confirmCallCount": <N> }` (C7) donde `<N>` es el conteo real medido AL IMPLEMENTAR esta fase (después de F3, por eso F5 va última). No inventar el número: medirlo con el mismo scanner del test y congelarlo.
  - `Stacky Agents/frontend/src/__tests__/undoConfirmRatchet.test.ts` — test vitest puro que:
    1. Recorre recursivamente `src/**/*.{ts,tsx}` con `fs` de Node (leer el walker del test de uiDebt existente en `src/__tests__/` y replicarlo).
    2. **Definición exacta del conteo (C7):** `confirmCallCount` = (ocurrencias de la subcadena `window.confirm(`) + (matches del regex `/[^.\w]confirm\(/g`). Los dos conjuntos son disjuntos por construcción (el regex exige un no-`.`/no-word antes de `confirm`, y `window.confirm(` tiene `.`), así que la suma no cuenta doble. `askConfirm(` no matchea ninguno (la `k` es word-char).
    3. Excluye por ruta exacta: el propio `undoConfirmRatchet.test.ts` y `undoConfirmBaseline.json`.
    4. Falla si `conteo > baseline.confirmCallCount`; si `conteo < baseline`, falla con mensaje `bajá el baseline a <conteo>` (ratchet de una vía, mismo contrato que uiDebt).
- **Cuidado gotcha conocido (prosa-vs-gate):** el scanner mira SOLO `frontend/src`; este documento vive en `docs/` y no colisiona. El test se auto-excluye por ruta exacta.
- **Comando de verificación (binario, desde `Stacky Agents/frontend`):**
  ```
  npx vitest run src/__tests__/undoConfirmRatchet.test.ts
  ```
- **Flag:** ninguna (es un test estático; no hay comportamiento runtime que apagar). Default N/A.
- **Runtimes:** N/A-por-diseño (test de repo).
- **Trabajo del operador:** ninguno.

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Doble ejecución o commits fuera de orden del mismo id | contrato exactamente-una-vez + serialización por id con cadena de promesas (F1 semántica 2, tests 4/5/10) |
| Pérdida de acción al cerrar la pestaña | F4 `pagehide`+`visibilitychange`+unmount → `flushAll`; gracia corta (≤15 s) acota la ventana |
| Convertir por error una acción irreversible | criterio binario de reversibilidad en F3 + lista PROHIBIDO explícita + ratchet F5 no fuerza conversiones |
| Romper callers existentes de `Toast` | prop `action` **opcional** con diff exacto (F2); `tsc --noEmit` como gate en F2/F3 |
| Ctrl+Z roba el atajo dentro de campos de texto | guard `shouldHandleUndoKey` excluye INPUT/TEXTAREA/SELECT/contentEditable y combos con Shift/Alt (tests 4-6 de F2) |
| Ratchet propio mal calibrado (rojo perpetuo) | baseline se MIDE con el mismo scanner al implementar F5 (no se estima); contrato de una vía igual a uiDebt |
| Flag OFF deja flujos convertidos sin confirm ni gracia | aceptado y documentado en F3: solo se convierten acciones cuyo confirm era fricción (reversibles por criterio); OFF = pre-plan menos ese confirm |
| Sesión paralela activa en el repo | doc standalone; la implementación crea archivos nuevos + ediciones acotadas (Toast/App/2 pilotos); commit con pathspec explícito |

## 6. Fuera de scope (explícito)

- Undo multi-nivel / historial de undo (stack): solo gracia simple por acción; Ctrl+Z repetido deshace pendientes restantes, nunca acciones ya commiteadas.
- Undo server-side con ledger/compensaciones (transaccionalidad ADO es del plan 153).
- `navigator.sendBeacon` / `fetch keepalive` en pagehide.
- Conversión masiva de TODOS los confirms (solo pilotos ≥2 + ratchet; el resto migra orgánicamente en planes futuros).
- Cola offline/retry de commits fallidos (el caller maneja `onError` como ya maneja errores de esa API).
- Telemetría de undo-rate (encaja en el plan 171 cuando se implemente).
- Integración con el registry de atajos del plan 172 (no implementado): el listener directo de Ctrl+Z migra ahí cuando exista.

## 7. Glosario (para el modelo implementador)

- **Arnés / FlagSpec:** registro central de feature-flags del backend (`backend/config.py`); se exponen por `GET /api/harness-flags` y se administran SOLO por UI (`HarnessFlagsPanel.tsx`).
- **`_CURATED_DEFAULTS_ON`:** allowlist en `config.py`; toda flag bool con default `True` DEBE estar ahí o `test_default_known_only_for_curated` falla.
- **`HARNESS_TEST_FILES`:** lista en `backend/tests/test_harness.py`; todo `test_*.py` nuevo del backend debe registrarse ahí.
- **`HarnessFlagView`:** shape de cada flag en la respuesta de `GET /api/harness-flags` (`frontend/src/api/endpoints.ts:703`); los campos que usa este plan son `key` (string) y `value` (boolean para flags bool).
- **uiDebtRatchet:** test existente que congela deuda de estilo inline; los `.tsx` nuevos tienen presupuesto 0 (`style={{}}` prohibido; dinámicos por ref+`setProperty`).
- **askConfirm:** API de confirmación del diálogo canónico (plan 164, usada por 175). NO es deuda; el ratchet F5 no la cuenta.
- **Acción optimista:** la UI refleja el resultado ANTES de que el efecto real corra; si el operador deshace, la UI se revierte con `onUndo`.
- **Gracia:** ventana (default 6 s) entre la acción del operador y el commit real, durante la cual el toast ofrece "Deshacer" (y Ctrl+Z).
- **Serialización por id:** los commits de una misma entidad se despachan encadenados en orden; entidades distintas en paralelo.
- **Bypass:** modo del manager cuando la flag está OFF: commit inmediato por la misma cadena, cero toasts, comportamiento pre-plan.

## 8. Orden de implementación

1. F0 — flag + tests backend (registro en `HARNESS_TEST_FILES` incluido).
2. F1 — `undoManager.ts` con sus 11 tests (TDD: tests primero).
3. F2 — `undoToastModel.ts` + 6 tests; diff de `Toast.tsx`; `UndoToastHost.tsx` + css; montaje en `App.tsx`; wiring de flag; Ctrl+Z.
4. F3 — pilotos de conversión (≥2) con criterio de reversibilidad.
5. F4 — flush `pagehide`/`visibilitychange`/unmount.
6. F5 — baseline medido + `undoConfirmRatchet.test.ts`.

## 9. Definición de Hecho (DoD) global

- [ ] `venv\Scripts\python.exe -m pytest tests/test_harness_flags_undo.py -q` y `... tests/test_harness.py -q` verdes (PowerShell, `Stacky Agents/backend`).
- [ ] `npx vitest run src/services/__tests__/undoManager.test.ts` verde (11/11).
- [ ] `npx vitest run src/services/__tests__/undoToastModel.test.ts` verde (6/6).
- [ ] `npx vitest run src/__tests__/undoConfirmRatchet.test.ts` verde con baseline medido.
- [ ] `npx tsc --noEmit` verde en `Stacky Agents/frontend`.
- [ ] `grep -rn "scheduleUndoable" src --include=*.tsx | wc -l` ≥ 2 (Git Bash).
- [ ] `grep -n "style={{" src/components/UndoToastHost.tsx` = 0 hits y `grep -n "aria-live" src/components/UndoToastHost.tsx` = 0 hits (C2).
- [ ] `grep -n "toastAction" src/components/Toast.tsx` ≥ 1 y `grep -n "shouldHandleUndoKey" src/components/UndoToastHost.tsx` ≥ 1.
- [ ] Flag `STACKY_UNDO_UNIVERSAL_ENABLED` visible en el panel de flags, default ON; con OFF el dashboard se comporta como pre-plan (verificación manual de 1 minuto del operador, opcional, no bloqueante).
- [ ] Ningún confirm de acción irreversible fue removido (revisión del diff de F3 contra la lista PROHIBIDO).
