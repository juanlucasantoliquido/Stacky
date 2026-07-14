# Plan 136 — Protección de trabajo y acciones seguras en la UI: ni pérdida de lo tipeado, ni acciones destructivas accidentales, ni estado stale peligroso

**Estado:** PROPUESTO v1 (2026-07-13)
**Origen:** auditoría UX multi-lente 2026-07-13, pedido del operador de mejorar UX sin romper nada.
**Alcance:** 100% frontend. Cero backend nuevo, cero endpoint nuevo, cero flag de harness.
**Flag:** NO lleva flag (decisión justificada en §3.1, precedente plan 132 §3.1).
**Ortogonal a:** planes 132 (consola a demanda desde ActiveRunsPanel), 134 (awareness de runs) y 135 (cero errores mudos) — ver §3.2, staging quirúrgico obligatorio.

> Este documento está redactado para que un MODELO MENOR (Haiku, Codex CLI o GitHub
> Copilot Pro) lo implemente SIN inferir nada. Rutas, símbolos y comandos son LITERALES.
> Prohibido desviarse de los nombres exactos, prohibido "mejorar" el alcance.
> Todo lo ambiguo ya fue decidido acá.

---

## 1. Objetivo + KPIs binarios

Hoy la UI de Stacky puede: lanzar DOS runs (y DOS épicas auto-publicadas en ADO) por un
doble click; descartar un brief largo por un click en el backdrop; borrar adjuntos y
desactivar webhooks sin confirmación; dejar ticket/bloques/caches del proyecto ANTERIOR
al cambiar de proyecto; perder la consola en vivo con un F5; y desincronizar tab↔URL con
Ctrl+/. Este plan cierra los 7 gaps con protecciones **invisibles** (cero configuración,
cero fricción en flujos felices) reusando patrones que ya existen en la casa.

**KPIs (todos binarios):**

- **KPI-1 (un click = un run):** con el POST de `runBrief` en vuelo, un segundo click en
  "Generar épica" o "Arrancar así" NO dispara un segundo POST. Verificación: test puro
  `canGenerateEpic({isLaunching:true,...}) === false` (F0, ejecutable hoy) + guard
  `if (isLaunching) return` visible en el diff de F1 + smoke F8 paso 1 (pestaña Network:
  exactamente 1 POST tras doble click).
- **KPI-2 (backdrop nunca destruye tipeo):** click en backdrop con contenido tipeado /
  cambios sin guardar / mutación en vuelo NO cierra el modal; con el modal pristine SÍ
  cierra (comportamiento actual intacto). Verificación: tests puros de
  `shouldCloseOnBackdrop` (F0) + smoke F8 paso 2. Los botones Cancelar/✕ cierran SIEMPRE
  igual que hoy.
- **KPI-3 (el brief sobrevive):** cerrar y reabrir "Nueva Épica desde Brief" en la misma
  pestaña re-hidrata el brief tipeado; publicar la épica OK lo limpia. Verificación:
  tests puros de `briefDraft` (F0) + smoke F8 paso 3.
- **KPI-4 (destructivo = 2 clicks):** "Desactivar" webhook y "Borrar (N)" adjuntos
  exigen segundo click de confirmación dentro de 4 s; un click aislado NUNCA ejecuta.
  Verificación: tests puros de `nextConfirmState` (F0) + smoke F8 paso 4.
- **KPI-5 (editar adjunto nunca destruye el original):** en `handleSave` de
  `AgentHistoryPage`, `uploadAttachment` precede a `deleteAttachments` en el código; si
  el upload falla, no se ejecuta ningún delete. Verificación: lectura del diff F4 (orden
  de líneas) + mensaje de error diferenciado.
- **KPI-6 (cambiar de proyecto limpia el workbench):** tras `setActiveProject` con nombre
  distinto, `activeTicketId === null`, `blocks.length === 0`,
  `chatDrawerTicketId === null`, `chatDrawerOpen === false`. Verificación: test puro
  `projectChangeReset` (F0, ejecutable hoy) + smoke F8 paso 5. Las queries `pm.*`
  refetchean solas por cambio de queryKey.
- **KPI-7 (la consola sobrevive al F5):** F5 con run vivo → el dock reaparece con el
  mismo run y estado minimizado; F5 con run terminado → el dock queda cerrado en
  silencio. Verificación: test puro `restoreConsoleDecision` (F0) + tests de
  `migrateWorkbenchPersist` (F0) + smoke F8 paso 6.
- **KPI-8 (Ctrl+/ consistente):** dos Ctrl+/ seguidos + F5 dejan tab y URL coincidentes.
  Verificación: test puro `toggleNavTab` (F0) + lectura del diff F7 (el path se calcula
  desde el valor actual, no desde el closure) + smoke F8 paso 7.
- **KPI-9 (no degradar):** `npx tsc --noEmit` = 0 errores; ningún flujo feliz gana
  clicks, diálogos nativos ni pasos nuevos.

## 2. Por qué ahora / gaps verificados (evidencia en HEAD, re-verificada 2026-07-13)

Todas las anclas siguientes fueron re-leídas en el checkout antes de citarse.

**GAP 1 — Doble-submit en brief→épica (el más caro: duplica épicas EN ADO).**
- `frontend/src/components/EpicFromBriefModal.tsx:283-333` — `handleGenerate` hace
  `await Agents.runBrief(...)` (:290) sin setear ningún estado busy antes; `setStep("running")`
  recién en :322, DESPUÉS de resolver el await → mientras el POST está en vuelo,
  `step === "brief"`.
- `:425-426` — `canGenerate = brief.trim().length > 0 && step === "brief" && ...` → sigue
  true con el POST en vuelo.
- `:539-550` — el botón solo tiene `disabled={!canGenerate}` → doble click = dos POST =
  dos runs.
- `:336-372` — `handleApproveIntent` sí setea `setStep("running")` (:339) pero
  `setShowPreflightModal(false)` recién en :361 tras el await → el modal de preflight
  sigue abierto y clickeable durante el POST.
- `frontend/src/components/IntentPreflightModal.tsx:158-164` — botón "Arrancar así" SIN
  `disabled`; `:165-173` — "Corregir y arrancar" solo se deshabilita por corrections
  vacío. `onApprove` async disparable N veces.
- `EpicFromBriefModal.tsx:398-399` — comentario verificado: "Auto-publicación: al
  terminar la run, la épica se crea en ADO directamente, sin paso de aprobación manual"
  (la excepción documentada al human-in-the-loop) → el duplicado LLEGA al tracker.
- Contraste (el patrón ya existe en la casa): `frontend/src/components/AgentLaunchModal.tsx:407`
  — `disabled={!selected || loading || success || ...}` y `handleLaunch` setea
  `setLoading(true)` al entrar (:218-220) con `finally { setLoading(false) }` (:265-267).

**GAP 2 — Ningún modal protege lo tipeado: el backdrop descarta todo sin aviso.**
- `EpicFromBriefModal.tsx:421-423` — `handleBackdrop` → `onClose()` incondicional; `:526`
  — placeholder "Pegá la transcripción, notas de reunión o brief del cliente…": input
  largo NO regenerable.
- `AgentLaunchModal.tsx:271-273` — backdrop cierra sin guard (pierde `message` :68 y
  `selected`).
- `frontend/src/components/EditProjectModal.tsx:289` — backdrop inline cierra sin guard
  (pierde todo el form :14-41, incl. PAT/tokens tipeados). Estado `saving` en :42; los
  edits del operador pasan por `patch()` (:175-177) y `patchDocsPath()` (:183+).
- `frontend/src/components/AgentConfigModal.tsx:100-102` — overlay descarta el estado
  `dirty` (:38-40) sin aviso; `saving` en :37.
- `frontend/src/components/FinishWorkButton.tsx:124` — overlay `onClick={handleClose}`
  SIN guard de `isBusy` (:106), mientras el botón ✕ (:128) SÍ tiene
  `disabled={isBusy}`; `handleClose` (:94-102) resetea `reason` y todo el form.
- `IntentPreflightModal.tsx:54-56` — backdrop llama `onCancel` incondicional (pierde
  `corrections` :39).

**GAP 3 — Editar un adjunto es borrar-y-resubir sin atomicidad.**
- `frontend/src/components/AgentHistoryPage.tsx:147-163` — `handleSave`: `await
  Tickets.deleteAttachments(...)` PRIMERO (:151), `uploadAttachment` después (:152); si
  el upload falla, solo `setError` (:153-155): no hay rollback, el original ya no existe.
- `frontend/src/api/endpoints.ts:312-316` — `deleteAttachments` es `api.delete` contra
  `/api/tickets/<id>/attachments`: borrado real en el tracker; `:317-318` —
  `uploadAttachment` es `api.post` al mismo path.
- **Hallazgo verificado (honestidad del grounding):** en HEAD el backend solo expone el
  GET de listado (`backend/api/tickets.py:1032-1056`); las rutas POST/DELETE y el GET
  `/attachments/content` NO existen (grep exhaustivo sobre `backend/` sin hits) →
  hoy esas llamadas devuelven 405/404. Además `AgentHistoryPage` y `FileManagerModal`
  son componentes huérfanos portados de WS2 (`AgentHistoryPage.tsx:13`; grep: ningún
  call site los monta). El fix de orden es blindaje correcto-por-construcción: el día
  que se monten/implementen las rutas, quien lo haga NO va a re-auditar este handler, y
  el orden actual destruiría el original en ADO ante un upload fallido.
- **Colisión de nombres (pregunta cerrada con evidencia):** `backend/services/ado_client.py:667-699`
  — `upload_attachment` hace `POST _apis/wit/attachments?fileName=...`: en ADO cada POST
  crea un blob NUEVO con UUID y URL propios (no pisa por nombre; el link al work item es
  una relación aparte, `:716`). Subir antes de borrar NO colisiona: el peor caso pasa de
  "archivo destruido" a "nombre duplicado un rato".
- Contraste: `AgentHistoryPage.tsx:252-264` — el borrado directo del padre SÍ confirma
  (`if (!confirm(...)) return;` en :253).

**GAP 4 — Destructivos con CERO confirmación + patrón two-step listo para extraer.**
- `frontend/src/components/FileManagerModal.tsx:62-92` — `handleDelete` borra los
  adjuntos seleccionados sin confirmación; `:113-127` — "Seleccionar todo" + "Borrar (N)":
  todos los adjuntos del ticket destruibles en 2 clicks. (Componente hoy huérfano —
  disclosed arriba — se blinda igual: costo mínimo, nace protegido cuando se monte.)
- `frontend/src/pages/SettingsPage.tsx:269-271` — "Desactivar" llama `deactivate(row.id)`
  directo (`endpoints.ts:1135`: `api.delete` real a `/api/webhooks/<id>`); `:193-209` —
  `create` sin estado busy y botón "Crear" (:256) sin `disabled`: doble-submit posible.
  `WebhooksPanel` SÍ está montado (`SettingsPage.tsx:152`).
- `frontend/src/components/FinishWorkButton.tsx:287-310` — patrón two-step in-app YA
  implementado y validado (botón cambia a "⚠ Confirmar cierre" vía estado `confirming`,
  disabled durante pending): base a extraer, sumándole timeout de desarme.

**GAP 5 — Cambiar de proyecto deja estado del proyecto ANTERIOR.**
- `frontend/src/components/TopBar.tsx:101-118` — `handleProjectChange` limpia 7 caches
  react-query pero NUNCA resetea `activeTicketId`/`blocks`/`chatDrawerTicketId` del
  workbench. `frontend/src/store/workbench.ts:119` — `setActiveProject` solo setea
  `activeProject`. Riesgo real: lanzar un agente contra un ticket de otro proyecto.
- `frontend/src/hooks/useAutoFillBlocks.ts:20-24` — `Tickets.byId(activeTicketId)` sin
  scoping por proyecto: el ticket ajeno carga normal.
- `frontend/src/pages/PMCommandCenter.tsx:857-858` — `queryKey: ["pm.sprint.current"]` y
  `:872-873` — `queryKey: ["pm.risks", severityFilter, showAcked]` SIN proyecto; TopBar
  (:108-114) no las limpia → parado en PM al cambiar de proyecto, los datos del anterior
  quedan indefinidamente. `PMCommandCenter.tsx` NO importa `useWorkbench` hoy (grep).
- Contraejemplo (el patrón correcto existe): `frontend/src/pages/DocsPage.tsx:76-82` —
  DocsPage resetea su estado al cambiar `projectName` y sus queryKeys incluyen el
  proyecto (`:90`).
- **Decisión cerrada:** scoping de las queryKeys `pm.*` con el proyecto (opción A) — es
  el idiom react-query, calca DocsPage:90 y EVITA tocar `TopBar.tsx` (archivo compartido
  con el plan 134 → ortogonalidad). Las invalidaciones existentes (:888-889, :899,
  :1032-1033) usan prefijo y siguen matcheando sin cambios (react-query hace partial
  matching por prefijo).

**GAP 6 — Un F5 durante un run CLI vivo hace desaparecer la consola flotante.**
- `frontend/src/store/workbench.ts:134-137` — `partialize` persiste SOLO `agentRuntime`
  (comentario: el resto es "efímero por sesión"); `:138-155` — el patrón
  `version`+`migrate` del persist YA existe (v2, Plan 37).
- `frontend/src/components/CodexConsoleDock.tsx:50-53` — el dock lee
  `codexConsoleExecutionId` del store; `:96` — `if (executionId == null) return null;`
  → tras rehidratar es null y el dock no existe, aunque el run siga corriendo.
- `:62-67` — el dock YA consulta `Executions.byId(executionId)` con polling 5 s
  (`endpoints.ts:1221` — `GET /api/executions/<id>`): mecanismo existente para validar
  la restauración, cero endpoint nuevo.
- **Ortogonalidad con plan 132 (declarada):** 132 agrega un botón manual "Ver consola"
  en ActiveRunsPanel (abrir A DEMANDA); esto restaura LO QUE YA ESTABA ABIERTO tras un
  reload. No se duplican: ni un archivo en común en las fases de 132 (ActiveRunsPanel.*)
  vs. las de acá (workbench.ts, CodexConsoleDock.tsx).

**GAP 7 — Ctrl+/ desincroniza URL de vista por closure stale.**
- `frontend/src/App.tsx:112` — `isToggleNav`; `:119-124` — el branch usa `setTab`
  funcional (:121) pero la :122 computa el path con la variable `tab` del closure del
  `useEffect` registrado con deps `[]` (:128) → congelada en el valor de montaje.
- `:55` — el tab inicial se deriva del pathname (`tabFromPath`): tras el desync, un F5
  restaura el tab EQUIVOCADO. `:32-46` — el mapa se llama literalmente `TAB_PATHS`.
- **Verificación adicional que cambia el diseño del fix:** `frontend/src/main.tsx:13` —
  la app monta en `<React.StrictMode>`. En dev, StrictMode invoca DOS VECES los updaters
  de estado → PROHIBIDO poner `window.history.pushState` adentro del callback de
  `setTab` (duplicaría entradas de historial). El fix usa un ref espejo + reusa
  `selectTab` (:66-72), que ya hace pushState con guard `pathname !== path`.

## 3. Principios y guardarraíles (no negociables)

1. **Paridad 3 runtimes** (Codex CLI, Claude Code CLI, GitHub Copilot Pro): TODO el plan
   es UI/estado local del frontend, runtime-agnóstico. Cada fase lo declara. La consola
   restaurada (F6) aplica a los runtimes interactivos `codex_cli`/`claude_code_cli` con
   stdin y al resto en modo solo-logs, IGUAL que hoy: verificado en
   `CodexConsoleDock.tsx:76` (`isInteractiveRun = codex_cli || claude_code_cli`; el panel
   de logs se renderiza para cualquier runtime, solo el stdin se gatea). Ver tabla §5.
2. **Cero trabajo extra del operador:** protecciones invisibles; nada que configurar,
   activar ni aprender. Ninguna fase agrega pasos a un flujo feliz.
3. **Human-in-the-loop:** las protecciones AGREGAN fricción solo ante gestos destructivos
   accidentales (backdrop con tipeo, primer click destructivo); JAMÁS quitan control:
   los botones Cancelar/✕ siguen cerrando SIEMPRE, cancelar runs sigue igual, y ninguna
   protección toma decisiones por el operador.
4. **Mono-operador sin auth real:** cero RBAC, cero chequeo de permisos.
5. **No degradar:** flujos felices byte-idénticos (mismo número de clicks, misma
   apariencia); PROHIBIDO agregar `window.confirm`/`alert` nuevos (los two-step son
   in-app); prohibido tocar la lógica interna de `useExecutionStream`, polling, o
   cualquier backend.
6. **Reusar, no reinventar:** two-step de `FinishWorkButton.tsx:287-310`; patrón
   `version`+`migrate` del persist de `workbench.ts:138-155`; patrón de reset por
   proyecto de `DocsPage.tsx:76-82`; patrón busy de `AgentLaunchModal.tsx:407`.

### 3.1 Decisión de diseño: SIN flag de harness (justificación explícita)

Precedente directo: plan 132 §3.1 — protecciones de UI puramente aditivas pueden ir sin
flag. Cada fase de este plan cumple los tres criterios del precedente:
- **Puramente aditivas:** ningún comportamiento existente cambia en el flujo feliz
  (backdrop pristine sigue cerrando; un solo click sigue lanzando; los borrados siguen
  disponibles a 2 clicks).
- **Reversibles con un gesto:** todo se deshace con el gesto opuesto (segundo click,
  botón Cancelar, reabrir consola desde el panel del plan 132).
- **Cero backend / cero datos remotos:** solo estado de UI local (`useState`,
  `sessionStorage`, `localStorage` del persist ya existente).

Un flag agregaría trabajo al operador (activarlo) y superficie de test/config sin
mitigar ningún riesgo real — violaría el principio 2. Aplica a las 9 fases; cada una
lo repite en una línea.

### 3.2 Ortogonalidad con los planes hermanos 134/135 (staging quirúrgico obligatorio)

Este plan se escribe EN PARALELO con 134 (awareness de runs) y 135 (cero errores mudos).
Archivos editados compartidos y cómo NO pisarse a nivel de líneas:

| Archivo | Compartido con | Zona que toca ESTE plan (única) |
|---|---|---|
| `App.tsx` | 134 y 135 | SOLO el efecto keydown (:103-128, branch `isToggleNav`), el import de react (:1) y 2 líneas de ref junto a :55. Nada más. |
| `SettingsPage.tsx` | 134 | SOLO el componente `WebhooksPanel` (:171-277) + 1 import arriba. |
| `TopBar.tsx` | 134 | **NO SE TOCA** (decisión GAP 5, opción A: la higiene vive en `workbench.ts` y el scoping en `PMCommandCenter.tsx`). |
| `EditProjectModal.tsx` | 135 | SOLO la línea del backdrop (:289), `patch`/`patchDocsPath` (:175-190) y 1 estado nuevo tras :43. |
| `CodexConsoleDock.tsx` | 135 | SOLO 1 import + 1 bloque aditivo (ref + efecto) inmediatamente después de :67. Cero cambios en JSX/render. |

Reglas duras: (a) commits SOLO con pathspec explícito de los archivos de cada fase —
PROHIBIDO `git add -A`/`git add .`; (b) si al implementar una zona listada arriba ya fue
modificada por 134/135, integrar por edición mínima manual, nunca revert/checkout.

### 3.3 Estrategia de tests (fijada; patrón plan 132 §4)

**Entorno:** los tests de componente `@testing-library/react` + jsdom NO corren en este
checkout (gap preexistente documentado en
`frontend/src/components/__tests__/ActiveRunsPanel.test.tsx:12-17` — NO resolverlo, no es
parte de este plan). La lógica pura SÍ corre: `npx vitest run <archivo>` desde
`Stacky Agents/frontend` (precedente: `src/devops/*.test.ts`, `src/docs/*.test.ts`,
todos co-locados y verdes).

**Diseño para testeabilidad (obligatorio):** todo lo no trivial se extrae a funciones
puras en módulos SIN imports de React/zustand/endpoints, testeables HOY con vitest:
`shouldCloseOnBackdrop`, `canGenerateEpic`, `nextConfirmState`, `restoreConsoleDecision`,
`toggleNavTab` (en `services/uiGuards.ts`), `projectChangeReset` y
`migrateWorkbenchPersist` (en `store/workbenchPure.ts`), y el borrador del brief con
Storage inyectado (`services/briefDraft.ts`). No hay hoy tests de store en
`src/store/` (verificado): estos son los primeros y por eso NO importan `workbench.ts`
(que crea el store zustand con `localStorage`), solo el módulo puro.

**Gate binario global:** `npx tsc --noEmit` desde `Stacky Agents/frontend` = 0 errores.
Los tests de componente que este plan pide (solo `ConfirmButton.test.tsx`, chico y
autocontenido) se escriben "listos para correr" con la misma nota de entorno del
precedente. Para los 6 modales NO se escriben tests de componente: la regla está cubierta
por los tests puros + tsc + smoke F8 (decisión explícita para no multiplicar el gap RTL).

## 4. Fases

Dependencias: F1..F7 dependen SOLO de F0. Entre sí son independientes y commiteables por
separado (pathspec explícito por fase). F8 cierra.

---

### F0 — Módulos puros + tests PRIMERO (ejecutables HOY)

**Objetivo (1 frase):** crear las 3 unidades de lógica pura que gobiernan todas las
protecciones, con sus tests vitest escritos ANTES y corriendo en verde hoy mismo —
el corazón testeable del plan.

**Archivos a CREAR (6, ninguno existe hoy):**
1. `Stacky Agents/frontend/src/services/uiGuards.ts`
2. `Stacky Agents/frontend/src/services/uiGuards.test.ts`
3. `Stacky Agents/frontend/src/services/briefDraft.ts`
4. `Stacky Agents/frontend/src/services/briefDraft.test.ts`
5. `Stacky Agents/frontend/src/store/workbenchPure.ts`
6. `Stacky Agents/frontend/src/store/workbenchPure.test.ts`

Regla dura: estos módulos NO importan React, zustand, ni `../api/endpoints`. Solo
`import type` de `../types` está permitido (se borra al compilar).

**Contenido EXACTO de `uiGuards.ts`:**

```ts
/**
 * Plan 136 — Guards puros de UI: protección de trabajo y acciones seguras.
 * Módulo SIN dependencias (ni React, ni zustand, ni endpoints) para ser
 * testeable con vitest puro, sin jsdom. Cada función es determinista.
 */

export interface BackdropGuardInput {
  /** Hay contenido tipeado / cambios sin guardar en el modal. */
  dirty: boolean;
  /** Hay una mutación o lanzamiento en vuelo. */
  busy: boolean;
}

/** Regla compartida F2: el click en backdrop solo cierra un modal pristine y ocioso.
 *  Los botones Cancelar/✕ NO pasan por acá: cierran siempre. */
export function shouldCloseOnBackdrop(input: BackdropGuardInput): boolean {
  return !input.dirty && !input.busy;
}

export interface CanGenerateEpicInput {
  step: string;               // Step del modal ("brief" | "running" | ...)
  briefEmpty: boolean;        // brief.trim().length === 0
  isLaunching: boolean;       // POST runBrief en vuelo (F1)
  claudeGateBlocked: boolean; // runtime claude_code_cli && !claudeReady
}

/** F1: habilitación del botón "Generar épica". */
export function canGenerateEpic(i: CanGenerateEpicInput): boolean {
  return i.step === "brief" && !i.briefEmpty && !i.isLaunching && !i.claudeGateBlocked;
}

export type ConfirmState = "idle" | "armed";
export type ConfirmEvent = "click" | "timeout" | "disable";

/** F3: máquina de estados del ConfirmButton (two-step).
 *  fire=true SOLO en armed+click (el segundo click). */
export function nextConfirmState(
  state: ConfirmState,
  event: ConfirmEvent,
): { state: ConfirmState; fire: boolean } {
  if (event === "timeout" || event === "disable") return { state: "idle", fire: false };
  if (state === "idle") return { state: "armed", fire: false };
  return { state: "idle", fire: true };
}

/** Estados de ejecución considerados vivos (mismos que usa ActiveRunsPanel). */
export const ACTIVE_RUN_STATUSES = ["running", "preparing", "queued"] as const;

/** F6: decisión de restauración de la consola tras un reload.
 *  "keep" solo si la API confirmó que el run sigue vivo; ante error o estado
 *  desconocido, "clear" (limpiar en silencio). */
export function restoreConsoleDecision(
  status: string | undefined,
  isError: boolean,
): "keep" | "clear" {
  if (isError || !status) return "clear";
  return (ACTIVE_RUN_STATUSES as readonly string[]).includes(status) ? "keep" : "clear";
}

/** F7: toggle de navegación Ctrl+/ (espejo puro del comportamiento). */
export function toggleNavTab(current: string): "team" | "tickets" {
  return current === "team" ? "tickets" : "team";
}
```

**Contenido EXACTO de `briefDraft.ts`:**

```ts
/**
 * Plan 136 F2 — Borrador del brief de EpicFromBriefModal en sessionStorage.
 * Storage inyectable para tests puros. NUNCA lanza: cualquier fallo de storage
 * (cuota llena, storage deshabilitado) degrada a no-op — jamás rompe el tipeo.
 * sessionStorage muere con la pestaña: el draft no persiste entre sesiones.
 */
export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

const PREFIX = "stacky.epicBriefDraft.v1:";

export function briefDraftKey(project: string | null): string {
  return `${PREFIX}${project ?? "_global"}`;
}

export function readBriefDraft(storage: StorageLike | null, project: string | null): string {
  if (!storage) return "";
  try {
    return storage.getItem(briefDraftKey(project)) ?? "";
  } catch {
    return "";
  }
}

export function writeBriefDraft(
  storage: StorageLike | null,
  project: string | null,
  brief: string,
): void {
  if (!storage) return;
  try {
    if (brief.trim().length === 0) storage.removeItem(briefDraftKey(project));
    else storage.setItem(briefDraftKey(project), brief);
  } catch {
    /* no-op: nunca romper el tipeo por un fallo de storage */
  }
}

export function clearBriefDraft(storage: StorageLike | null, project: string | null): void {
  if (!storage) return;
  try {
    storage.removeItem(briefDraftKey(project));
  } catch {
    /* no-op */
  }
}
```

**Contenido EXACTO de `workbenchPure.ts`:**

```ts
/**
 * Plan 136 — Lógica pura del store workbench (higiene de proyecto F5 y
 * migración del persist F6), extraída para tests vitest sin zustand/jsdom.
 */
import type { AgentRuntime, ContextBlock } from "../types";

export const WORKBENCH_PERSIST_VERSION = 3;

export interface WorkbenchPersistV3 {
  agentRuntime: AgentRuntime;
  codexConsoleExecutionId: number | null;
  codexConsoleMinimized: boolean;
}

const VALID_RUNTIMES: AgentRuntime[] = ["github_copilot", "codex_cli", "claude_code_cli"];

/** Migración v1/v2 → v3. Preserva EXACTAMENTE el remapeo del Plan 37
 *  (copilot heredado → claude_code_cli cuando fromVersion < 2, ver
 *  workbench.ts:139-155 actual) y agrega los campos de consola con defaults
 *  inertes (null/false) para todo lo anterior a v3. */
export function migrateWorkbenchPersist(
  persisted: unknown,
  fromVersion: number,
): WorkbenchPersistV3 {
  const prev = (persisted ?? {}) as {
    agentRuntime?: unknown;
    codexConsoleExecutionId?: unknown;
    codexConsoleMinimized?: unknown;
  };
  let rt: AgentRuntime =
    typeof prev.agentRuntime === "string" &&
    VALID_RUNTIMES.includes(prev.agentRuntime as AgentRuntime)
      ? (prev.agentRuntime as AgentRuntime)
      : "claude_code_cli";
  if (fromVersion < 2 && rt === "github_copilot") rt = "claude_code_cli";
  const execId =
    fromVersion >= 3 && typeof prev.codexConsoleExecutionId === "number"
      ? prev.codexConsoleExecutionId
      : null;
  const minimized = fromVersion >= 3 && prev.codexConsoleMinimized === true;
  return { agentRuntime: rt, codexConsoleExecutionId: execId, codexConsoleMinimized: minimized };
}

export interface ProjectChangeReset {
  activeTicketId: null;
  activeExecutionId: null;
  blocks: ContextBlock[];
  chatDrawerTicketId: null;
  chatDrawerOpen: false;
}

/** F5: higiene al cambiar de proyecto. Devuelve null cuando NO hay que resetear
 *  (primera asignación al bootear, o mismo nombre de proyecto). Incluye
 *  activeExecutionId por consistencia con setActiveTicket (workbench.ts:86-87). */
export function projectChangeReset(
  prevName: string | null,
  nextName: string | null,
): ProjectChangeReset | null {
  if (prevName === null) return null; // boot: primera asignación, nada que limpiar
  if (prevName === nextName) return null; // mismo proyecto: no-op
  return {
    activeTicketId: null,
    activeExecutionId: null,
    blocks: [],
    chatDrawerTicketId: null,
    chatDrawerOpen: false,
  };
}
```

**Tests (escribirlos PRIMERO; deben fallar por módulo inexistente, luego pasar):**

`uiGuards.test.ts` — casos obligatorios (`describe`/`it` en español):
- `shouldCloseOnBackdrop`: (1) pristine+ocioso → true; (2) dirty → false; (3) busy →
  false; (4) dirty+busy → false.
- `canGenerateEpic`: (5) caso feliz (step "brief", no vacío, no launching, gate libre) →
  true; (6) `isLaunching:true` → false [KPI-1]; (7) `briefEmpty:true` → false; (8)
  `step:"running"` → false; (9) `claudeGateBlocked:true` → false.
- `nextConfirmState`: (10) idle+click → {armed, fire:false}; (11) armed+click →
  {idle, fire:true}; (12) armed+timeout → {idle, fire:false}; (13) idle+timeout →
  {idle, fire:false}; (14) armed+disable → {idle, fire:false}.
- `restoreConsoleDecision`: (15) "running"/false → keep; (16) "preparing"/false → keep;
  (17) "queued"/false → keep; (18) "completed"/false → clear; (19) "failed"/false →
  clear; (20) undefined/false → clear; (21) "running"/true (isError) → clear.
- `toggleNavTab`: (22) "team" → "tickets"; (23) "tickets" → "team"; (24) "docs" → "team".

`briefDraft.test.ts` — usar un FakeStorage in-memory (`Map` envuelta en `StorageLike`)
definido en el propio test. Casos: (1) write+read roundtrip; (2) claves distintas por
proyecto (escribir en "A" no pisa "B"); (3) project null usa la clave `_global`; (4)
write con string vacío o solo whitespace hace removeItem (read posterior → ""); (5)
clear → read ""; (6) storage null → read devuelve "" y write/clear no lanzan; (7)
storage cuyo setItem lanza → write no propaga la excepción.

`workbenchPure.test.ts` — casos: (1) migrate v2 `{agentRuntime:"codex_cli"}` → codex
preservado + `codexConsoleExecutionId:null` + `codexConsoleMinimized:false`; (2) migrate
v1 `{agentRuntime:"github_copilot"}` → `"claude_code_cli"` (remapeo Plan 37 intacto);
(3) migrate v3 completo `{agentRuntime:"claude_code_cli", codexConsoleExecutionId:42,
codexConsoleMinimized:true}` → passthrough; (4) migrate basura (null y {}) → defaults
`{"claude_code_cli", null, false}`; (5) migrate v3 con execId no numérico → null; (6)
`projectChangeReset(null,"A")` → null (boot); (7) `projectChangeReset("A","A")` → null;
(8) `projectChangeReset("A","B")` → objeto con los 5 campos exactos (assert campo por
campo); (9) `projectChangeReset("A",null)` → objeto reset (proyecto desactivado).

**Comandos exactos** (desde `Stacky Agents/frontend/`):
```
npx vitest run src/services/uiGuards.test.ts
npx vitest run src/services/briefDraft.test.ts
npx vitest run src/store/workbenchPure.test.ts
```
- **Criterio de aceptación (binario):** los 3 archivos de test corren EN VERDE hoy
  (24 + 7 + 9 = 40 casos mínimos) y `npx tsc --noEmit` = 0 errores.
- **Flag:** no aplica (§3.1). **Paridad runtimes:** módulos puros, sin contacto con
  runtimes. **Trabajo del operador: ninguno.**

---

### F1 — GAP 1: anti doble-submit en brief→épica (KPI-1)

**Objetivo (1 frase):** que con el POST de `runBrief` en vuelo sea IMPOSIBLE disparar un
segundo run (y por lo tanto una segunda épica auto-publicada en ADO).

**Archivo 1: `Stacky Agents/frontend/src/components/EpicFromBriefModal.tsx`** (7 ediciones)

1. Agregar import (junto al bloque de imports :8-20):
```ts
import { canGenerateEpic } from "../services/uiGuards";
```
2. Agregar estado, inmediatamente después de `const [isCancelling, setIsCancelling] = useState(false);` (:106):
```ts
  // Plan 136 F1 — true mientras el POST de runBrief está en vuelo (ambos caminos:
  // handleGenerate y handleApproveIntent). Bloquea el doble-submit que duplicaba
  // runs y épicas auto-publicadas en ADO.
  const [isLaunching, setIsLaunching] = useState(false);
```
3. `handleGenerate` (:283): agregar guard + set + finally. Queda así (el cuerpo del
   `try` actual :287-327 y el `catch` :328-332 NO cambian):
```ts
  async function handleGenerate() {
    if (!brief.trim() || isLaunching) return;
    setIsLaunching(true);
    setErrorMsg(null);
    setRunningExecutionId(null);
    try {
      // ... cuerpo actual sin cambios ...
    } catch (e) {
      // ... catch actual sin cambios ...
    } finally {
      setIsLaunching(false);
    }
  }
```
4. `handleApproveIntent` (:336): mismo patrón exacto — guard
   `if (!brief.trim() || isLaunching) return;` + `setIsLaunching(true);` como primeras
   líneas, y `finally { setIsLaunching(false); }` cerrando el try/catch actual
   (:341-371).
5. `canGenerate` (:425-426): reemplazar por la función pura (misma semántica + launching):
```ts
  const canGenerate = canGenerateEpic({
    step,
    briefEmpty: brief.trim().length === 0,
    isLaunching,
    claudeGateBlocked: agentRuntime === "claude_code_cli" && !claudeReady,
  });
```
6. Botón (:539-550): `disabled={!canGenerate}` queda IGUAL (ya cubre isLaunching vía
   canGenerate). Cambiar SOLO el label:
```tsx
              {isLaunching ? "Lanzando…" : "▶ Generar épica con Agente de Negocio"}
```
7. Render del preflight (:662-674): agregar la prop `busy={isLaunching}` al
   `<IntentPreflightModal ...>` existente. Nada más cambia ahí.

**Archivo 2: `Stacky Agents/frontend/src/components/IntentPreflightModal.tsx`** (3 ediciones)

1. Props (:22-26): agregar `busy?: boolean;` a `IntentPreflightModalProps` y
   desestructurarla en la firma (:34-38): `({ intent, onApprove, onCancel, busy })`.
2. Botón "Arrancar así" (:158-164): agregar `disabled={busy}` y label
   `{busy ? "Lanzando…" : "Arrancar así"}`.
3. Botón "Corregir y arrancar" (:165-173): `disabled={busy || !corrections.trim()}`.
   El botón "Cancelar" (:155-157) queda SIN disabled (human-in-the-loop: el operador
   nunca pierde la salida).

- **Prohibido en esta fase:** tocar el backdrop de ninguno de los dos modales (eso es
  F2), tocar `Agents.runBrief`, el polling o el backend.
- **Tests:** cubiertos por F0 casos 5-9 (puros, verdes hoy). No se agrega test de
  componente (decisión §3.3).
- **Criterio de aceptación (binario):** `npx tsc --noEmit` = 0 errores; en el diff, el
  guard `|| isLaunching` aparece en `handleGenerate` Y en `handleApproveIntent`, y ambos
  tienen `finally { setIsLaunching(false) }`.
- **Flag:** no aplica (§3.1: protección aditiva; resuelto el POST, el botón se
  re-habilita solo). **Paridad runtimes:** el guard aplica ANTES de elegir runtime —
  idéntico para los 3. **Trabajo del operador: ninguno.**

---

### F2 — GAP 2: backdrop solo cierra modales pristine + borrador del brief (KPI-2, KPI-3)

**Objetivo (1 frase):** que un click accidental en el backdrop nunca destruya contenido
tipeado/cambios sin guardar, y que el brief de EpicFromBriefModal sobreviva a un cierre
accidental vía borrador en sessionStorage.

**Regla compartida (una sola, sin excepciones):** cada backdrop pasa a evaluar
`shouldCloseOnBackdrop({ dirty, busy })` (F0). Con contenido o mutación en vuelo el click
en backdrop SE IGNORA (sin diálogo, sin toast — silencio). Los botones Cancelar/✕ de cada
modal NO SE TOCAN: cierran siempre, exactamente como hoy (principio 3).

**Edición 1 — `EpicFromBriefModal.tsx`** (mismo archivo que F1; zonas distintas):
1. Import (sumar a la línea de F1): `import { canGenerateEpic, shouldCloseOnBackdrop } from "../services/uiGuards";`
   y nueva línea `import { clearBriefDraft, readBriefDraft, writeBriefDraft } from "../services/briefDraft";`
2. Init del brief (:93) — ANTES: `const [brief, setBrief] = useState("");` / DESPUÉS:
```ts
  // Plan 136 F2 — re-hidratar el borrador de la sesión (clave por proyecto).
  const [brief, setBrief] = useState<string>(() =>
    readBriefDraft(window.sessionStorage, activeProjectName)
  );
```
   (`activeProjectName` ya está declarado ANTES, en :90 — el orden de hooks lo permite.)
3. Write-through del borrador — agregar después del `useEffect(() => () => stopPolling(), []);` (:281):
```ts
  // Plan 136 F2 — borrador write-through: cada tecla persiste; vacío ⇒ se borra la clave.
  useEffect(() => {
    writeBriefDraft(window.sessionStorage, activeProjectName, brief);
  }, [brief, activeProjectName]);
```
4. Limpieza al publicar OK — en `publishEpic` (:400-419), inmediatamente después de
   `setCreatedAdoId(res.ado_id);` (:411) agregar:
   `clearBriefDraft(window.sessionStorage, activeProjectName);`
   Momentos EXACTOS del ciclo de vida del draft: WRITE en cada cambio de `brief`;
   CLEAR solo al publicar OK; en cancelar/cerrar NO se limpia (eso ES la protección);
   la pestaña cerrada lo elimina sola (sessionStorage).
5. `handleBackdrop` (:421-423) — reemplazar por:
```ts
  function handleBackdrop(e: React.MouseEvent) {
    if (e.target !== e.currentTarget) return;
    // dirty: hay brief tipeado o el flujo ya avanzó (running/creating/error).
    // En "done" no hay nada que perder: el backdrop vuelve a cerrar.
    const dirty = step !== "done" && (brief.trim().length > 0 || step !== "brief");
    const busy = isLaunching || step === "running" || step === "creating";
    if (shouldCloseOnBackdrop({ dirty, busy })) onClose();
  }
```
   Nota: aunque el backdrop ignore el click, el brief queda además protegido por el
   borrador (doble red). El modal se monta condicionalmente en `TicketBoard.tsx:944`,
   así que al reabrir se re-ejecuta el initializer del paso 2 y re-hidrata.

**Edición 2 — `AgentLaunchModal.tsx` (:271-273)** — reemplazar `handleBackdrop`:
```ts
  function handleBackdrop(e: React.MouseEvent) {
    if (e.target !== e.currentTarget) return;
    const dirty = selected != null || message.trim().length > 0;
    if (shouldCloseOnBackdrop({ dirty, busy: loading })) onClose();
  }
```
   + import de `shouldCloseOnBackdrop`. (`message` es el estado :68; `selected` y
   `loading` ya existen. El auto-close post-éxito :251 no cambia.)

**Edición 3 — `EditProjectModal.tsx`** (compartido con plan 135 — tocar SOLO esto):
1. Import de `shouldCloseOnBackdrop` (ruta desde components: `../services/uiGuards`).
2. Después de `const [error, setError] = useState<string | null>(null);` (:43):
   `const [dirty, setDirty] = useState(false);`
3. En `patch` (:175-177) y en `patchDocsPath` (:183-190): agregar `setDirty(true);` como
   última línea del cuerpo. IMPORTANTE: los `setForm` de los efectos de credenciales
   (:66-73) NO se tocan — no son tipeo del operador y no deben marcar dirty.
4. Backdrop (:289) — reemplazar el onClick por:
   `onClick={(e) => { if (e.target === e.currentTarget && shouldCloseOnBackdrop({ dirty, busy: saving })) onClose(); }}`

**Edición 4 — `AgentConfigModal.tsx` (:100-102)** — reemplazar el onClick del overlay por:
   `onClick={(e) => { if (e.target === e.currentTarget && shouldCloseOnBackdrop({ dirty: Object.keys(dirty).length > 0, busy: saving })) onClose(); }}`
   + import. (`dirty` :38 y `saving` :37 ya existen.)

**Edición 5 — `FinishWorkButton.tsx` (:124)** — reemplazar el onClick del overlay:
   ANTES: `<div className={styles.overlay} onClick={handleClose}>`
   DESPUÉS: `<div className={styles.overlay} onClick={() => { if (shouldCloseOnBackdrop({ dirty: reason.trim().length > 0, busy: isBusy })) handleClose(); }}>`
   + import. El `stopPropagation` del modal (:125), el ✕ (:128) y "Cerrar" (:280-285)
   quedan idénticos (ya tienen `disabled={isBusy}`).

**Edición 6 — `IntentPreflightModal.tsx` (:54-56)** — reemplazar el onClick del backdrop:
   `onClick={(e) => { if (e.target === e.currentTarget && shouldCloseOnBackdrop({ dirty: corrections.trim().length > 0, busy: busy === true })) onCancel(); }}`
   + import. (Usa la prop `busy` agregada en F1 — F2 requiere F1 en este archivo.)

- **NO tocar en esta fase:** `FileManagerModal.tsx` (su backdrop se protege en F3, junto
  con su ConfirmButton, para que ese archivo viva en UNA sola fase).
- **Tests:** F0 casos 1-4 (regla) + 1-7 de briefDraft (borrador). Sin tests de
  componente (§3.3).
- **Criterio de aceptación (binario):** `npx tsc --noEmit` = 0 errores; grep
  `shouldCloseOnBackdrop` devuelve EXACTAMENTE 7 hits en `src/` (1 definición + 6 usos);
  smoke F8 pasos 2 y 3.
- **Flag:** no aplica (§3.1: con el modal pristine el comportamiento es byte-idéntico al
  actual). **Paridad runtimes:** los 6 modales son UI pura previa/ajena al runtime.
  **Trabajo del operador: ninguno.**

---

### F3 — GAP 4: ConfirmButton two-step + webhooks seguros + FileManagerModal blindado (KPI-4)

**Objetivo (1 frase):** extraer el patrón two-step ya validado de FinishWorkButton a un
componente reusable y aplicarlo a los dos destructivos sin confirmación, más busy en
"Crear" webhook.

**Archivo a CREAR: `Stacky Agents/frontend/src/components/ConfirmButton.tsx`**
```tsx
/**
 * Plan 136 F3 — Botón destructivo two-step (sin window.confirm).
 * Primer click ARMA (label de confirmación); segundo click dentro de timeoutMs
 * EJECUTA; expirado el timeout se desarma solo. Extraído del patrón validado de
 * FinishWorkButton.tsx:287-310, sumándole el desarme automático.
 * La máquina de estados vive en services/uiGuards.ts (nextConfirmState, testeada).
 */
import { useEffect, useRef, useState } from "react";
import { nextConfirmState, type ConfirmState } from "../services/uiGuards";
import styles from "./ConfirmButton.module.css";

interface ConfirmButtonProps {
  label: React.ReactNode;
  confirmLabel?: React.ReactNode; // default "⚠ Confirmar"
  onConfirm: () => void;
  disabled?: boolean;
  busy?: boolean;      // deshabilita y desarma mientras la acción corre
  className?: string;  // clase del estado idle (hereda el estilo local del caller)
  title?: string;
  timeoutMs?: number;  // default 4000
}

export default function ConfirmButton({
  label,
  confirmLabel = "⚠ Confirmar",
  onConfirm,
  disabled,
  busy,
  className,
  title,
  timeoutMs = 4000,
}: ConfirmButtonProps) {
  const [state, setState] = useState<ConfirmState>("idle");
  const timerRef = useRef<number | null>(null);

  function clearTimer() {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }

  useEffect(() => () => clearTimer(), []);

  // disabled/busy externos desarman (evento "disable" de la máquina).
  useEffect(() => {
    if ((disabled || busy) && state === "armed") {
      clearTimer();
      setState(nextConfirmState(state, "disable").state);
    }
  }, [disabled, busy, state]);

  function handleClick() {
    const next = nextConfirmState(state, "click");
    clearTimer();
    setState(next.state);
    if (next.fire) {
      onConfirm();
      return;
    }
    timerRef.current = window.setTimeout(() => {
      setState((s) => nextConfirmState(s, "timeout").state);
      timerRef.current = null;
    }, timeoutMs);
  }

  return (
    <button
      type="button"
      className={state === "armed" ? styles.armed : className}
      onClick={handleClick}
      disabled={disabled || busy}
      title={state === "armed" ? "Click de nuevo para confirmar (se desarma solo en unos segundos)" : title}
      aria-pressed={state === "armed"}
    >
      {state === "armed" ? confirmLabel : label}
    </button>
  );
}
```

**Archivo a CREAR: `Stacky Agents/frontend/src/components/ConfirmButton.module.css`**
— UNA clase `.armed`. NO inventar paleta: copiar las declaraciones de color/fondo/borde
EXACTAS de la clase `.dangerConfirm` de
`Stacky Agents/frontend/src/components/FinishWorkButton.module.css` (misma semántica
visual "estás por ejecutar algo destructivo") y agregar `cursor: pointer;`.

**Archivo a CREAR: `Stacky Agents/frontend/src/components/__tests__/ConfirmButton.test.tsx`**
— tests de componente listos-para-correr (gap jsdom §3.3; encabezarlo con la MISMA nota
de entorno de `ActiveRunsPanel.test.tsx:12-17`). Casos: (1) render inicial muestra
`label`; (2) primer click NO llama onConfirm y muestra `confirmLabel`; (3) segundo click
llama onConfirm exactamente 1 vez; (4) con `vi.useFakeTimers`, avanzar 4001 ms tras el
primer click desarma (vuelve `label`) y un click posterior NO ejecuta; (5)
`busy: true` deshabilita el botón.

**Edición 1 — `SettingsPage.tsx`** (compartido con plan 134 — tocar SOLO `WebhooksPanel`
:171-277 + 1 import arriba del archivo):
1. Import: `import ConfirmButton from "../components/ConfirmButton";`
2. En `WebhooksPanel`, después de `const [secret, setSecret] = useState("");` (:178):
   `const [creating, setCreating] = useState(false);`
3. `create` (:193-209) — agregar guard y finally:
```ts
  const create = async () => {
    if (!url.trim() || creating) return;
    setCreating(true);
    setError(null);
    try {
      await Webhooks.create({ url: url.trim(), event, format, secret: secret.trim() || undefined });
      setUrl("");
      setSecret("");
      load();
    } catch (e) {
      setError(String((e as Error)?.message ?? e));
    } finally {
      setCreating(false);
    }
  };
```
4. Botón "Crear" (:256): `<button className={styles.subTab} onClick={create} disabled={creating || !url.trim()}>{creating ? "Creando…" : "Crear"}</button>`
5. Botón "Desactivar" (:269-271) — reemplazar por:
```tsx
          <ConfirmButton
            className={styles.subTab}
            label="Desactivar"
            confirmLabel="⚠ Confirmar"
            onConfirm={() => deactivate(row.id)}
          />
```

**Edición 2 — `FileManagerModal.tsx`** (única fase que toca este archivo; componente hoy
huérfano — ver §2 GAP 3 — se blinda igual para que nazca protegido cuando se monte):
1. Imports: `ConfirmButton` y `shouldCloseOnBackdrop`.
2. Botón "Borrar (N)" (:121-127) — reemplazar por:
```tsx
                <ConfirmButton
                  className={styles.deleteBtn}
                  label={deleting ? "Borrando..." : `Borrar (${selected.size})`}
                  confirmLabel={`⚠ Confirmar borrado (${selected.size})`}
                  disabled={selected.size === 0}
                  busy={deleting}
                  onConfirm={handleDelete}
                />
```
3. Backdrop (:97) — reemplazar el onClick por:
   `onClick={(e) => { if (e.target === e.currentTarget && shouldCloseOnBackdrop({ dirty: selected.size > 0, busy: deleting })) onClose(); }}`
   (la selección de N adjuntos también es trabajo del operador). El ✕ (:104) queda igual.

- **Fuera de esta fase:** los ~21 `window.confirm` existentes NO se migran (fuera de
  scope §7); `AgentHistoryPage.tsx:253` conserva su confirm actual.
- **Tests:** F0 casos 10-14 (máquina, verdes hoy) + `ConfirmButton.test.tsx` (listo para
  correr). Comando: `npx vitest run src/components/__tests__/ConfirmButton.test.tsx`
  (hoy falla SOLO por el gap RTL documentado; cualquier otro error bloquea).
- **Criterio de aceptación (binario):** `npx tsc --noEmit` = 0 errores; en `src/` hay
  EXACTAMENTE 2 call sites de `<ConfirmButton` (SettingsPage y FileManagerModal); un
  click aislado en "Desactivar"/"Borrar (N)" no ejecuta nada (smoke F8 paso 4).
- **Flag:** no aplica (§3.1: fricción SOLO en el gesto destructivo; el resto del panel
  es byte-idéntico). **Paridad runtimes:** webhooks y adjuntos son UI/API del tracker,
  ajenos al runtime. **Trabajo del operador: ninguno.**

---

### F4 — GAP 3: guardado de adjunto atómico (upload ANTES de delete) (KPI-5)

**Objetivo (1 frase):** invertir el orden borrar→subir de `handleSave` para que el peor
caso ante un fallo pase de "archivo destruido en el tracker" a "nombre duplicado un rato".

**Único archivo: `Stacky Agents/frontend/src/components/AgentHistoryPage.tsx`**

Reemplazar `handleSave` (:147-163) COMPLETO por:
```ts
  const handleSave = useCallback(async () => {
    setSaving(true);
    setError(null);
    try {
      // Plan 136 F4 — orden atómico: subir la versión NUEVA antes de borrar la
      // vieja. En ADO upload_attachment SIEMPRE crea un blob nuevo con UUID
      // propio (no pisa por nombre — backend/services/ado_client.py:667-699),
      // así que el peor caso es un nombre duplicado transitorio, nunca pérdida.
      const res = await Tickets.uploadAttachment(ticketId, att.name, editContent);
      if (!res.ok) {
        setError(res.error ?? "Error al guardar (el adjunto original quedó intacto)");
        return;
      }
      try {
        await Tickets.deleteAttachments(ticketId, [{ id: att.id, url: att.url, name: att.name }]);
      } catch {
        setError(
          "La versión nueva se subió, pero no se pudo borrar la anterior: " +
          "quedó una versión duplicada con el mismo nombre. Borrala a mano desde la lista."
        );
        return; // no cerrar: que el operador vea el aviso
      }
      onClose();
    } catch (e) {
      setError(`${String(e)} (el adjunto original quedó intacto)`);
    } finally {
      setSaving(false);
    }
  }, [ticketId, att, editContent, onClose]);
```

Casos borde (todos cubiertos por el código de arriba, verificar por lectura del diff):
- upload falla (res.ok false o excepción) → NINGÚN delete se ejecuta, original intacto,
  error visible.
- upload OK + delete falla → aviso explícito de duplicado, modal abierto, sin rollback
  destructivo.
- upload OK + delete OK → idéntico resultado neto al actual, cero cambio visible.

**Contexto verificado (no accionable en esta fase):** en HEAD las rutas backend
POST/DELETE de `/api/tickets/<id>/attachments` no existen (§2 GAP 3) y el componente es
huérfano; este fix es blindaje correcto-por-construcción para el día que se monten.
PROHIBIDO implementar esas rutas backend en este plan (fuera de scope §7).

- **Tests:** sin test ejecutable posible (componente + gap RTL + backend inexistente);
  el criterio es estructural sobre el diff. Justificación de 1 línea (TDD no viable):
  no hay seam puro que extraer sin inventar abstracción prematura sobre un componente
  huérfano — la validación más cercana es la revisión de orden en el diff + tsc.
- **Criterio de aceptación (binario):** `npx tsc --noEmit` = 0 errores; en el archivo,
  la línea con `uploadAttachment` tiene número MENOR que toda línea con
  `deleteAttachments` dentro de `handleSave`; `handleDelete` (:252-264) queda intacto.
- **Flag:** no aplica (§3.1: mismo resultado neto en el camino feliz). **Paridad
  runtimes:** adjuntos del tracker, ajeno al runtime. **Trabajo del operador: ninguno.**

---

### F5 — GAP 5: higiene de cambio de proyecto (workbench + queries pm.*) (KPI-6)

**Objetivo (1 frase):** que cambiar de proyecto nunca deje ticket activo, bloques,
ChatDrawer ni datos PM del proyecto anterior — centralizado en el store, sin tocar
TopBar.

**Decisión fijada (§2 GAP 5):** higiene en `setActiveProject` (opción store) + scoping
de queryKeys `pm.*` con el proyecto (opción A, patrón DocsPage:90). `TopBar.tsx` NO se
edita (ortogonalidad con plan 134); su `removeQueries` actual (:108-114) queda como está.

**Edición 1 — `Stacky Agents/frontend/src/store/workbench.ts`** (2 cambios):
1. Import arriba: `import { projectChangeReset } from "./workbenchPure";`
2. `setActiveProject` (:119) — ANTES: `setActiveProject: (p) => set({ activeProject: p }),`
   DESPUÉS:
```ts
  setActiveProject: (p) =>
    set((s) => {
      // Plan 136 F5 — higiene: al cambiar de proyecto, el ticket activo, los
      // bloques y el ChatDrawer del proyecto anterior dejan de tener sentido
      // (riesgo real: lanzar un agente contra un ticket ajeno). La primera
      // asignación (boot, TopBar.tsx:85) y el re-set del mismo proyecto no
      // resetean nada. Lógica pura y testeada en workbenchPure.ts.
      const reset = projectChangeReset(s.activeProject?.name ?? null, p?.name ?? null);
      return reset ? { activeProject: p, ...reset } : { activeProject: p };
    }),
```
   Efecto en cascada verificado: `activeTicketId=null` hace que `useAutoFillBlocks`
   (:47-50) haga `setBlocks([])` y que sus queries queden `enabled:false` — el ticket
   ajeno deja de cargar.

**Edición 2 — `Stacky Agents/frontend/src/pages/PMCommandCenter.tsx`** (3 cambios):
1. Import arriba: `import { useWorkbench } from "../store/workbench";` (verificado: hoy
   NO lo importa).
2. Dentro del mismo componente que define `sprintQuery` (:857), antes de esa línea:
   `const pmProject = useWorkbench((s) => s.activeProject?.name ?? null);`
3. Cambiar SOLO estas dos queryKeys:
   - `:858` → `queryKey: ["pm.sprint.current", pmProject],`
   - `:873` → `queryKey: ["pm.risks", pmProject, severityFilter, showAcked],`
   Las invalidaciones existentes (:888-889, :899, :1032-1033) NO se tocan: usan prefijo
   (`["pm.sprint.current"]`, `["pm.risks"]`) y react-query hace partial matching por
   prefijo, así que siguen invalidando todas las variantes. Las demás keys `pm.*`
   (`pm.ai.models`, `pm.ai.usage`, `pm.recommendations`, `pm.comments`) NO se tocan en
   este plan (no hay evidencia de staleness por proyecto; ampliar scope está prohibido).

- **Tests:** F0 casos 6-9 de workbenchPure (puros, verdes hoy). El cambio de key hace el
  refetch automático (mecánica de react-query, no se testea acá).
- **Criterio de aceptación (binario):** `npx tsc --noEmit` = 0 errores;
  `npx vitest run src/store/workbenchPure.test.ts` verde; smoke F8 paso 5 (cambiar de
  proyecto con ticket activo y PM abierto: el ticket se des-selecciona y el sprint/risks
  del proyecto anterior desaparecen).
- **Flag:** no aplica (§3.1: sin cambio de proyecto, comportamiento byte-idéntico).
- **Paridad runtimes:** estado de UI previo al lanzamiento; idéntico para los 3.
  **Trabajo del operador: ninguno.**

---

### F6 — GAP 6: la consola sobrevive al F5 (persist + validación de restauración) (KPI-7)

**Objetivo (1 frase):** persistir `codexConsoleExecutionId`/`codexConsoleMinimized` en el
persist del workbench y, al rehidratar, validar contra la API que el run siga vivo:
si sí, el dock reaparece como estaba; si no, se limpia en silencio.

**Ortogonalidad declarada:** el plan 132 agrega un botón "Ver consola" en
ActiveRunsPanel (abrir A DEMANDA un run activo); esta fase restaura LO QUE YA ESTABA
ABIERTO tras un reload. Complementarios, sin archivos en común (132: ActiveRunsPanel.*;
acá: workbench.ts + CodexConsoleDock.tsx). No duplican mecanismo: ambos convergen en el
mismo `setCodexConsoleExecution`/estado ya existente.

**Edición 1 — `Stacky Agents/frontend/src/store/workbench.ts`** (config del persist,
:131-156):
1. Ampliar el import de F5: `import { migrateWorkbenchPersist, projectChangeReset, WORKBENCH_PERSIST_VERSION } from "./workbenchPure";`
2. `partialize` (:134-137) — reemplazar (incluido el comentario actual) por:
```ts
      // Persistimos la preferencia de runtime y la consola abierta (Plan 136 F6:
      // sobrevive al F5; CodexConsoleDock valida al rehidratar que el run siga
      // vivo y la limpia en silencio si no). El resto del estado (ticket activo,
      // ejecuciones, bloques) sigue siendo efímero por sesión.
      partialize: (state) => ({
        agentRuntime: state.agentRuntime,
        codexConsoleExecutionId: state.codexConsoleExecutionId,
        codexConsoleMinimized: state.codexConsoleMinimized,
      }),
```
3. `version: 2,` (:138) → `version: WORKBENCH_PERSIST_VERSION,`
4. `migrate` (:139-155) — reemplazar TODO el cuerpo por la función pura (que preserva
   el remapeo Plan 37, testeado en F0):
```ts
      migrate: (persisted: unknown, fromVersion: number) =>
        migrateWorkbenchPersist(persisted, fromVersion),
```

**Edición 2 — `Stacky Agents/frontend/src/components/CodexConsoleDock.tsx`**
(compartido con plan 135 — SOLO 1 import + 1 bloque aditivo; CERO cambios en JSX):
1. Import: `import { restoreConsoleDecision } from "../services/uiGuards";` (y sumar
   `useRef` al import de react si no está — verificado: SÍ está, :el archivo ya usa
   `useRef` para `bodyRef`).
2. Insertar inmediatamente DESPUÉS de la declaración de `executionQ` (:62-67) y ANTES de
   `const sendInput = useMutation(...)` (:68):
```ts
  // Plan 136 F6 — validación de la consola RESTAURADA tras un reload.
  // Determinismo del origen: en el PRIMER render tras montar (el dock se monta
  // una sola vez, globalmente, en App.tsx), executionId solo puede ser != null
  // si vino de la rehidratación del persist — el operador aún no pudo clickear
  // nada. Capturamos ese valor inicial en un ref y lo validamos UNA vez con la
  // query que este dock ya hace (Executions.byId): si el run no está vivo
  // (running/preparing/queued), limpiamos en silencio. Si el operador abre otra
  // consola antes de resolver, la validación se descarta.
  const restoredIdRef = useRef<number | null>(executionId);
  useEffect(() => {
    const restoredId = restoredIdRef.current;
    if (restoredId == null) return;
    if (executionId !== restoredId) {
      restoredIdRef.current = null; // el operador ya cambió de consola: no validar
      return;
    }
    if (!executionQ.isSuccess && !executionQ.isError) return; // sin veredicto aún
    restoredIdRef.current = null; // validar una sola vez
    if (restoreConsoleDecision(executionQ.data?.status, executionQ.isError) === "clear") {
      setExecution(null); // run terminado/inexistente: cerrar en silencio
    }
  }, [executionId, executionQ.isSuccess, executionQ.isError, executionQ.data, setExecution]);
```
   Notas de corrección verificadas: (a) los hooks corren aunque el dock devuelva null
   después (:96 `if (executionId == null) return null;` está DESPUÉS de los hooks); (b)
   `executionQ` ya existe con `enabled: executionId != null` y usa `Executions.byId`
   (`endpoints.ts:1221`, `GET /api/executions/<id>`) — cero endpoint/fetch nuevo; (c)
   error de red o 404 ⇒ `isError` ⇒ decisión "clear" (no se deja un dock zombie); (d)
   StrictMode (main.tsx:13) re-monta en dev: la re-validación es idempotente.

**Comportamiento resultante (binario):**
- F5 con run vivo → dock reaparece con el MISMO `executionId` y el MISMO estado
  minimizado; el streaming rearranca solo (`useExecutionStream` ya depende de
  `executionId`).
- F5 con run terminado/cancelado/inexistente/API caída → dock cerrado, cero mensajes.
- Abrir consola manualmente (cualquier call site existente o el botón del plan 132) →
  la validación NO interfiere (ref ya consumido o distinto id).

- **Tests:** F0 casos 15-21 (decisión) + 1-5 de migrate (puros, verdes hoy). Sin test de
  componente (§3.3).
- **Criterio de aceptación (binario):** `npx tsc --noEmit` = 0 errores;
  `npx vitest run src/store/workbenchPure.test.ts` y
  `npx vitest run src/services/uiGuards.test.ts` verdes; smoke F8 paso 6 (las dos ramas:
  run vivo y run terminado).
- **Flag:** no aplica (§3.1; precedente directo: `agentRuntime` ya se persiste sin flag
  en el mismo `partialize`). **Paridad runtimes:** tabla §5 — la consola restaurada es
  interactiva (stdin) para `codex_cli`/`claude_code_cli` y solo-logs para el resto,
  EXACTAMENTE igual que una consola abierta a mano (gate `isInteractiveRun`,
  CodexConsoleDock.tsx:76, sin cambios). **Trabajo del operador: ninguno.**

---

### F7 — GAP 7: fix Ctrl+/ (closure stale desincroniza tab↔URL) (KPI-8)

**Objetivo (1 frase):** que Ctrl+/ compute el path desde el tab ACTUAL (no el del
closure congelado del montaje), manteniendo URL y vista siempre consistentes.

**Único archivo: `Stacky Agents/frontend/src/App.tsx`** (compartido con 134/135 — tocar
SOLO estas 3 zonas):

1. Import (:1) — ANTES: `import { useEffect, useState } from "react";` / DESPUÉS:
   `import { useEffect, useRef, useState } from "react";`
2. Ref espejo — inmediatamente después de la línea :55
   (`const [tab, setTab] = useState<Tab>(...)`):
```ts
  // Plan 136 F7 — espejo del tab para handlers registrados con deps [] (el
  // closure del keydown quedaba congelado en el valor de montaje).
  const tabRef = useRef(tab);
  useEffect(() => { tabRef.current = tab; }, [tab]);
```
3. Branch `isToggleNav` (:119-124) — reemplazar por:
```ts
      } else if (isToggleNav) {
        ev.preventDefault();
        // Plan 136 F7 — usar el tab ACTUAL (tabRef) y reusar selectTab, que ya
        // hace pushState con guard de pathname. PROHIBIDO meter pushState dentro
        // del updater de setTab: la app monta en <React.StrictMode> (main.tsx:13)
        // y en dev los updaters se invocan DOS veces (duplicaría el historial).
        selectTab(toggleNavTab(tabRef.current) as Tab);
      }
```
4. Import de la función pura: `import { toggleNavTab } from "./services/uiGuards";`

Justificación del desvío respecto del fix "pushState adentro del setTab funcional"
considerado en la auditoría: es incorrecto bajo StrictMode (side effect en updater,
verificado main.tsx:13); `selectTab` (:66-72) ya existe, no lee estado (solo `setTab`
estable y la constante `TAB_PATHS` :32-46), así que capturarlo en el closure del efecto
deps [] es seguro; y su guard `window.location.pathname !== path` evita entradas de
historial duplicadas. El mapa se llama literalmente `TAB_PATHS` (verificado :32).

Comportamiento intacto verificado: popstate (:97-101) sigue re-derivando el tab; el
fallback de tabs ocultos (:132-139) sigue usando `selectTab`; `tabFromPath` (:48-52)
hace que un F5 posterior restaure el tab CORRECTO — que es el bug reportado.

- **Tests:** F0 casos 22-24 (`toggleNavTab`, puros, verdes hoy).
- **Criterio de aceptación (binario):** `npx tsc --noEmit` = 0 errores; smoke F8 paso 7
  (Ctrl+/ ×2 + F5: la URL y el tab coinciden en cada paso).
- **Flag:** no aplica (§3.1: bugfix de 3 zonas, sin comportamiento nuevo). **Paridad
  runtimes:** navegación de UI, ajena al runtime. **Trabajo del operador: ninguno.**

---

### F8 — Gate final: verificación estática + smoke manual

**Objetivo (1 frase):** demostrar con comandos y 7 pasos manuales binarios que las 7
protecciones funcionan y que ningún flujo feliz cambió.

**Comandos exactos** (desde `Stacky Agents/frontend/`), en este orden:
1. `npx tsc --noEmit` → **exit 0, 0 errores** (gate duro).
2. `npx vitest run src/services/uiGuards.test.ts` → verde.
3. `npx vitest run src/services/briefDraft.test.ts` → verde.
4. `npx vitest run src/store/workbenchPure.test.ts` → verde.
5. `npx vitest run src/components/__tests__/ConfirmButton.test.tsx` → verde, o rojo SOLO
   por `Cannot find module '@testing-library/react'`/jsdom (gap preexistente §3.3);
   cualquier otro error BLOQUEA.
6. NO correr la suite vitest completa (regla del repo: tests por archivo).

**Smoke manual (7 pasos, todos binarios; app levantada como siempre):**
1. **[KPI-1]** Abrir "Nueva Épica desde Brief", pegar un brief, abrir la pestaña Network
   y hacer doble click rápido en "Generar épica" → EXACTAMENTE 1 POST a
   `/api/agents/run-brief`; el botón muestra "Lanzando…" deshabilitado. Repetir con el
   preflight activo doble-clickeando "Arrancar así" → 1 solo POST.
2. **[KPI-2]** Con texto tipeado en el brief, click en el backdrop → el modal NO cierra;
   botones ✕ y "Cancelar" SÍ cierran. Con el modal recién abierto y vacío, click en el
   backdrop → cierra (igual que hoy). Repetir la variante "con contenido" en
   EditProjectModal (editar un campo) y FinishWorkButton (tipear un motivo).
3. **[KPI-3]** Tipear un brief, cerrar el modal con ✕, reabrirlo → el brief reaparece.
   Publicar una épica OK → reabrir: el textarea está vacío.
4. **[KPI-4]** Settings → Webhooks: click en "Desactivar" → el botón cambia a
   "⚠ Confirmar" y NO borra; esperar >4 s → vuelve a "Desactivar"; dos clicks seguidos
   → desactiva. Doble click en "Crear" con URL válida → se crea UN solo webhook.
5. **[KPI-6]** Seleccionar un ticket, abrir el tab PM, cambiar de proyecto en el TopBar
   → el ticket queda des-seleccionado (sin bloques) y el PM muestra datos del proyecto
   nuevo (o vacío), nunca los del anterior.
6. **[KPI-7]** Lanzar un agente CLI (consola abierta), F5 → la consola reaparece con el
   mismo run y streaming vivo; minimizarla, F5 → reaparece minimizada. Esperar a que el
   run termine, F5 → la consola NO reaparece. Repetir el caso "run vivo" con runtime
   `github_copilot` → la consola restaurada es solo-logs (sin stdin), igual que hoy.
7. **[KPI-8]** Estando en "Equipo", Ctrl+/ → tab Tickets y URL `/tickets`; Ctrl+/ →
   Equipo y `/`; F5 → permanece el tab correcto según la URL.

- **Criterio de aceptación (binario):** los 6 comandos + 7 pasos pasan tal cual están
  escritos. **Trabajo del operador: ninguno** (verifica quien implementa).

## 5. Paridad de runtimes (documentación explícita, sin código nuevo por runtime)

| Fase | Codex CLI | Claude Code CLI | GitHub Copilot Pro |
|---|---|---|---|
| F1 doble-submit | guard idéntico (previo a elegir runtime) | ídem | ídem |
| F2 backdrop/draft | UI pura, idéntica | ídem | ídem |
| F3 ConfirmButton | UI pura, idéntica | ídem | ídem |
| F4 adjunto atómico | API del tracker, idéntica | ídem | ídem |
| F5 higiene proyecto | estado local, idéntico | ídem | ídem |
| F6 consola restaurada | logs en vivo + stdin (`isInteractiveRun`) | logs en vivo + stdin | logs en vivo solo-lectura (sin stdin) — mismo gate existente `CodexConsoleDock.tsx:76`, sin cambios |
| F7 Ctrl+/ | navegación, idéntica | ídem | ídem |

No hay fallback nuevo que implementar: la única asimetría (stdin de F6) ya está resuelta
por el componente existente y esta fase no la toca.

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Colisión de líneas con planes 134/135 en App.tsx / SettingsPage.tsx / EditProjectModal.tsx / CodexConsoleDock.tsx | Zonas disjuntas declaradas en §3.2; TopBar.tsx directamente NO se toca; commits con pathspec explícito por fase; si la zona ya cambió, integración por edición mínima manual (nunca revert). |
| `isLaunching` se queda trabado en true por una excepción | Imposible por construcción: `finally { setIsLaunching(false) }` en ambos handlers (F1, criterio binario del diff). |
| El backdrop "muerto" confunde al operador | El gesto explícito (✕ / Cancelar) sigue funcionando SIEMPRE y es el camino visible; la regla solo ignora el gesto ambiguo. Sin diálogos nuevos (principio 5). |
| Draft del brief con datos sensibles | El brief es contenido de negocio (no credenciales), va a `sessionStorage` (muere con la pestaña, no viaja a ningún lado) y se limpia al publicar OK. |
| Doble borrado accidental con ConfirmButton armado | El desarme automático a los 4 s + label "⚠ Confirmar…" + `aria-pressed` hacen el estado visible; `busy` desarma durante la ejecución (F0 caso 14). |
| Migración del persist v2→v3 rompe la preferencia de runtime | `migrateWorkbenchPersist` preserva el remapeo Plan 37 y tiene 5 tests puros (F0) que cubren v1/v2/v3/basura. |
| El dock restaurado apunta a un run de otro proyecto | Igual que el diseño existente (la consola streamea por `execution_id` global — precedente plan 132 §6): intencional, no mitigar. |
| StrictMode double-render re-valida la consola o duplica pushState | F6: validación idempotente (segunda pasada decide lo mismo); F7: PROHIBIDO pushState en updater + guard de pathname en `selectTab` (documentado en el código). |
| `pm.*` scoping rompe invalidaciones existentes | Las invalidaciones usan prefijo y react-query hace partial matching: verificado que `["pm.risks"]` matchea `["pm.risks", proyecto, ...]`. Solo cambian 2 keys. |
| AgentHistoryPage / FileManagerModal son huérfanos (¿trabajo muerto?) | Disclosed en §2: el blindaje es ~30 líneas, evita una pérdida de datos garantizada el día que se monten, y NO agrega rutas backend (fuera de scope). |
| Tests de componente no ejecutables hoy | Gap preexistente documentado (§3.3); el gate ejecutable son los 3 archivos de tests puros (40 casos) + tsc + smoke F8. |

## 7. Fuera de scope (prohibido en este plan)

- Notificaciones/título/badge de runs y rotulado del ActiveRunsPanel → **plan 134**.
- LoadErrorState/ErrorBoundary/toast unificado/errores de guardado silenciosos → **plan 135**.
- Migración masiva de los ~21 `window.confirm` existentes a ConfirmButton (este plan solo
  deja el ladrillo; la migración es una oportunidad futura).
- Persistencia de filtros de Docs/Historial entre tabs (oportunidad futura detectada en
  la auditoría).
- Implementar las rutas backend POST/DELETE/content de adjuntos, o montar
  AgentHistoryPage/FileManagerModal en alguna vista.
- Resolver el gap de entorno `@testing-library/react`/jsdom.
- Multi-consola, historial de consolas, restauración de más estado que
  `codexConsoleExecutionId`/`codexConsoleMinimized`.
- Cualquier flag de harness, endpoint, migración de datos o cambio de backend.

## 8. Glosario

- **Backdrop:** el overlay oscuro detrás de un modal; clickearlo hoy cierra el modal.
- **Pristine:** modal sin contenido tipeado, sin cambios sin guardar y sin mutación en
  vuelo (`shouldCloseOnBackdrop` → true).
- **Two-step / ConfirmButton:** botón destructivo que requiere dos clicks (armar →
  confirmar) con desarme automático; patrón origen: `FinishWorkButton.tsx:287-310`.
- **Draft del brief:** copia write-through del textarea de EpicFromBriefModal en
  `sessionStorage` bajo `stacky.epicBriefDraft.v1:<proyecto|_global>`.
- **Persist / partialize / migrate:** middleware zustand de `workbench.ts` que guarda un
  subconjunto del estado en localStorage con versionado (`stacky-workbench`).
- **Dock / consola:** `CodexConsoleDock`, montado globalmente; muestra logs en vivo por
  streaming y stdin para runtimes CLI interactivos.
- **Run vivo:** `AgentExecution` con status `running`, `preparing` o `queued`
  (`ACTIVE_RUN_STATUSES`).
- **Closure stale:** variable capturada por un handler registrado con deps `[]` que
  queda congelada en su valor de montaje (bug de F7).

## 9. Orden de implementación

1. **F0** — módulos puros + 3 archivos de tests (verdes antes de seguir).
2. **F1** — anti doble-submit (el gap más caro primero).
3. **F2** — backdrops + draft del brief (depende de F1 en los 2 archivos compartidos).
4. **F3** — ConfirmButton + webhooks + FileManagerModal.
5. **F4** — adjunto atómico.
6. **F5** — higiene de proyecto.
7. **F6** — consola tras F5 (reload).
8. **F7** — Ctrl+/.
9. **F8** — gate final (comandos + smoke).

Cada fase se commitea sola, con pathspec explícito de SUS archivos (§3.2). Si 134/135 ya
mergearon cambios en un archivo compartido, integrar a mano la zona propia.

## 10. Definición de Hecho (DoD global)

- [ ] Los 6 archivos nuevos de F0 existen y `npx vitest run` de los 3 tests puros está
  VERDE (40 casos mínimos).
- [ ] KPI-1: guard `|| isLaunching` + `finally` en ambos handlers; `busy` cableado al
  preflight; smoke paso 1 con 1 solo POST.
- [ ] KPI-2: los 6 backdrops (EpicFromBrief, AgentLaunch, EditProject, AgentConfig,
  FinishWork overlay, IntentPreflight) usan `shouldCloseOnBackdrop`; FileManagerModal
  también (vía F3). Cancelar/✕ intactos en todos.
- [ ] KPI-3: draft write-through + re-hidratación + clear al publicar OK, clave exacta
  `stacky.epicBriefDraft.v1:<proyecto|_global>`.
- [ ] KPI-4: `<ConfirmButton>` en "Desactivar" webhook y "Borrar (N)"; busy en "Crear";
  desarme a 4 s.
- [ ] KPI-5: en `handleSave`, upload precede a delete; mensajes de error diferenciados
  (original intacto / duplicado transitorio).
- [ ] KPI-6: `setActiveProject` aplica `projectChangeReset`; `pm.sprint.current` y
  `pm.risks` con proyecto en la key; TopBar.tsx SIN cambios.
- [ ] KPI-7: partialize v3 + `migrateWorkbenchPersist` + validación de restauración en
  el dock; ambas ramas del smoke paso 6 pasan (incl. copilot solo-logs).
- [ ] KPI-8: Ctrl+/ usa `tabRef` + `selectTab`; sin pushState dentro de updaters.
- [ ] KPI-9: `npx tsc --noEmit` = 0 errores; ningún flujo feliz ganó clicks ni diálogos.
- [ ] Diff limitado a: 6 archivos nuevos F0 + `ConfirmButton.tsx` + `.module.css` +
  `ConfirmButton.test.tsx` + los 12 archivos editados listados en las fases. Ningún
  cambio en backend, TopBar.tsx, flags, ni `harness_defaults.env`.
- [ ] Ortogonalidad §3.2 respetada: commits por fase con pathspec explícito.
