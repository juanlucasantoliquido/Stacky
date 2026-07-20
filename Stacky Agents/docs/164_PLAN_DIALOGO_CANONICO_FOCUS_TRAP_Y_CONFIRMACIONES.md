# Plan 164 — Un diálogo para gobernarlos a todos: primitiva canónica, focus-trap y confirmaciones de marca

## Versión: v1 -> v2 (crítica adversarial aplicada)

**CHANGELOG v1 -> v2:**
- **C1 (BLOQUEANTE — motivo del RECHAZO del v1) Settlement del host sin especificar:** el v1 no decía qué pasa con la promesa de `useConfirm`/`useAlert` al cerrar por Escape/backdrop/X ni al desmontarse el consumidor → promesa colgada = `await` colgado = acción colgada. v2 fija la REGLA DURA "toda vía de cierre RESUELVE" (dismiss ⇒ valor neutro por kind, helper puro `dismissValueFor`), settle idempotente, 3 tests nuevos del reducer y semántica de desmonte del consumidor (F1 Paso 3, §3.12, §7 R10/R11).
- **C2 (IMPORTANTE) Tooling irreal:** el KPI-3 del v1 dependía de `tsx` (NO está en `devDependencies` — `npx tsx` intentaría bajarlo de la red) y de `rg` (no garantizado en PATH, verificado 2026-07-18). v2 elimina `scripts/count_native_dialogs.ts`, hace canónico un `grep -P` y documenta que `grep -c` sale exit 1 al imprimir `0` (gates se juzgan por stdout).
- **C3 (IMPORTANTE) Drift del plan 162 (implementado DESPUÉS del v1):** el barrel `ui/` exporta hoy **13** primitivas, no 8. v2 corrige §1/§2.1/§2.4, obliga a reusar `Field`+`Input` del 162 en los diálogos de entrada (PROHIBIDO `<input>` crudo) y declara la compatibilidad focus-trap ↔ foco-al-primer-error (`firstErrorFieldId`) del 162.
- **C4 (IMPORTANTE) Human-in-the-loop sin criterio binario:** el contador en 0 se podía alcanzar BORRANDO confirmaciones (el grep no distingue migrar de eliminar). v2 agrega la tabla de conservación congelada en F0 (32 filas clasificadas) + KPI-8: 32/32 MIGRADA con reemplazo `archivo:símbolo`; prohibido eliminar sin reemplazo.
- **C5 (IMPORTANTE) Coherencia con 156-F6:** la letra del 156 excluye solo `__tests__/` del scan del ratchet, pero hoy existe `src/incidents/incidentModel.test.ts:172` (plan 166) con un fixture de test que matchea el regex FUERA de `__tests__/` ⇒ el "0 por archivo" sería inalcanzable. v2 alinea la exclusión (`*.test.*` además) y define el fallback si este plan corre antes que 156-F6 (F2 pre-check).
- **C6 (IMPORTANTE) Bordes DOM ausentes:** los eventos React burbujean a través de portales por el árbol de React (Escape en un diálogo anidado cerraría AMBOS sin `stopPropagation`); faltaban scroll-lock del body, token de z-index vs drawers/paleta, `inert`/aria-hidden del fondo y restore-focus a nodo presente-pero-desprendido. v2 los especifica (F1 Paso 2).
- **C7 (IMPORTANTE) Heurística del adhocModalRatchet diferida** ("se congela en el test" = el implementador decide): v2 congela el detector EN EL PLAN (regex exactos + exclusiones + allowlist `{file, reason}`).
- **C8 (MENOR) F0 contradictoria** ("Archivos: ninguno" pero pedía escribir un docstring): v2 aclara que F0 entrega bloques de texto en el resumen; el docstring se materializa en F1 y el comentario-inventario en F3.
- **C9 (MENOR) Ambigüedad "o" en las entradas nativas** (¿ConfirmDialog+input o diálogo de entrada?): v2 la elimina con A2 (`PromptDialog`/`useTextPrompt`, contrato único).
- **C10 (MENOR) Borde `beforeunload`:** 0 usos hoy en `src` (verificado); §8 lo declara N/A explícito. También: la tabla de §2.4 decía "Rol en 157" (resto de la renumeración) → corregido a 164.
- **[ADICIÓN ARQUITECTO A1] `forcedZero` para `nativeDialogByFile`:** tras F2, la dimensión entra a la lista `forcedZero` del `uiDebtRatchet` (mecanismo YA existente, `uiDebtRatchet.test.ts:80-82`): el 0 queda ABSOLUTO — ni un regen futuro puede resubirlo. KPI-3/KPI-7 se apoyan en esto.
- **[ADICIÓN ARQUITECTO A2] `PromptDialog` + `useTextPrompt()`:** primitiva única para las 2 entradas nativas, sobre `Dialog`, reusando `Field`+`Input` del plan 162; `requiredText` da el type-to-confirm del rollback 1:1.
- **[ADICIÓN ARQUITECTO A3] Motion accesible autocontenido:** overlay/panel con transición breve y `@media (prefers-reduced-motion: reduce)` que la desactiva (en `Dialog.module.css`; sin dependencia de tokens de motion).

> **Estado:** CRITICADO v2 (2026-07-18) — v1 RECHAZADO (C1 bloqueante) → v2 aplica C1..C10 + A1..A3; listo para implementar · **Autor:** StackyArchitectaUltraEficientCode · **Juez:** StackyArchitectaUltraEficientCode (Fable 5, perfil normal)
> **Origen:** debate adversarial 2026-07-16 con auditoría empírica del árbol de frontend. El gap viene verificado del debate; toda la evidencia archivo:línea de este doc fue **re-verificada y RECONTADA en frío contra el worktree** y se corrigió el drift encontrado (ver §2 y los bloques "DRIFT CORREGIDO"). Los números de línea son referencia de ese día — **toda edición se ancla por TEXTO/símbolo citado, no por número de línea**.
> **Orden en el roadmap:** **ÚLTIMO de la serie de UX** — se implementa **después** del plan del ledger de publicación transaccional, el del arnés veraz, el del latido único y el de la identidad de build. Motivo: es el más transversal de todos (toca ~17 superficies de UI), así que se hace al final para no chocar con el resto mientras avanzan. Un contador only-decrease que protege a los demás planes mientras este espera lo **adelanta el plan del latido único** (una fase suya); este plan lo lleva a 0 y lo deja clavado (§5, F2).
> **Runtimes:** este plan es **UI pura del panel Stacky**, 100% **agnóstica del runtime de agentes** (Codex CLI, Claude Code CLI, GitHub Copilot Pro). Ninguna fase toca el camino de ejecución de agentes, ni el de publicación, ni ningún endpoint del backend. Solo cambia la **presentación** (cómo se ven y se comportan los diálogos) de flujos que ya existen. La paridad de runtimes es automática por vacuidad. Se declara igual por fase.
> **Flags nuevas:** **NINGUNA.** Es UI pura sin flag: una primitiva de componente nueva + migración de superficies existentes. NO se toca `FLAG_REGISTRY`, NO se toca `_CURATED_DEFAULTS_ON`, NO hay panel nuevo, NO hay config nueva del operador. Precedente directo: los planes de estados universales, tema claro/oscuro y sistema de movimiento se implementaron sin flag.
> **Human-in-the-loop:** los diálogos de confirmación **SON** exactamente el human-in-the-loop — el operador confirma cada acción destructiva. Este plan **mejora ese lazo** (mejor foco, mejor tema, mejor accesibilidad), **nunca lo bypasea**: ninguna confirmación desaparece, ninguna acción destructiva pasa a ser automática. Al contrario: hoy varias confirmaciones viven en diálogos nativos del navegador que rompen el tema y bloquean el hilo; este plan las convierte en confirmaciones de marca que respetan el sistema de diseño.

---

## 1. Objetivo + KPI / impacto esperado

**Objetivo (1 párrafo):** un producto tiene UNA puerta y todos entran por ella; un prototipo tiene catorce agujeros distintos en la pared. Hoy Stacky es lo segundo: **no existe primitiva `Dialog`/`Modal`** en `frontend/src/components/ui/` (el barrel exporta **13** primitivas — las 8 del plan de sistema de diseño: Button, IconButton, StatusChip, Card, SectionHeader, Tabs, Skeleton, Spinner, más las 5 de formularios del plan 162 IMPLEMENTADO: Field, Input, Select, Textarea, Checkbox — y ninguna es un diálogo). Como no hay puerta canónica, **cada superficie inventó su propio modal** (15 archivos `*Modal*.tsx` + 2 modales inline dentro de páginas) y **ninguno tiene focus-trap** (0 en TODO el frontend), **ninguno de esos modales cierra con Escape** (el único manejo de Escape del codebase vive en la paleta de comandos, drawers y páginas, jamás en un modal), y **6 superficies ni siquiera declaran `role="dialog"`**. En paralelo, **32 acciones destructivas y errores caen a diálogos nativos del navegador** (confirmación/aviso/entrada bloqueantes), repartidas en 16 archivos: rompen el tema claro/oscuro del plan de tema+A11y, **bloquean el hilo del navegador**, e ignoran los canales de marca que Stacky ya tiene (`ConfirmButton` del plan de protección de trabajo y `Toast` del plan de cero-errores-mudos). Y el flujo core "lanzar agente" está **implementado dos veces** (un modal ad-hoc de ~137 líneas dentro del tablero de tickets vs. el modal canónico de 457 líneas). Este plan crea la **primitiva canónica `Dialog`** (portal + `role="dialog"` + `aria-modal` + Escape + focus-trap sin librerías + restauración de foco + `closeGuard` que integra el contrato de guarda ya existente) más los hooks `useConfirm()`/`useAlert()`/`useTextPrompt()` promise-based (settlement garantizado: ninguna promesa queda colgada — C1), y **migra todo hacia ella**. Resultado: Stacky se **siente producto**, no prototipo — y sin agregarle ni un clic de trabajo al operador.

**KPIs binarios (comandos exactos; TODO frontend). Correr desde el checkout real `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend` (el `node_modules` del worktree puede estar roto — junction conocida). Equivalente POSIX: `cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"`. vitest SIEMPRE por archivo (cross-file pollution conocida):**

- **KPI-1 — Lógica de teclado/foco de la primitiva verde:** `npx vitest run src/components/ui/__tests__/dialogKeyboard.test.ts` → exit 0 (Escape → cerrar; Tab en el último foco → volver al primero; Shift+Tab en el primero → ir al último; `closeGuard` bloquea cuando dirty/busy).
- **KPI-2 — Reducer del host de diálogos verde:** `npx vitest run src/components/ui/__tests__/dialogHostReducer.test.ts` → exit 0 (encolar/abrir/resolver una petición promise-based; resolución con `true`/`false`; cola FIFO).
- **KPI-3 — Cero diálogos nativos del navegador en `src`:** el comando de conteo de §5 F2 imprime `0`. **C2: NO existe `scripts/count_native_dialogs.ts` ni se usa `npx tsx`** (`tsx` NO está en `devDependencies`; `npx` intentaría bajarlo de la red). El scan cubre `.ts` y `.tsx` bajo `src/`, excluye `**/__tests__/**` **y** `*.test.*`. Refuerzo estructural: KPI-7 con `forcedZero` (A1).
- **KPI-4 — Ratchet de modales ad-hoc verde y allowlist decreciente:** `npx vitest run src/__tests__/adhocModalRatchet.test.ts` → exit 0; y la allowlist congelada tiene **estrictamente menos** entradas que en el commit anterior (only-decrease).
- **KPI-5 — Un solo punto de lanzamiento de agente (F4, recortable):** `grep -c "function RunModal" src/pages/TicketBoard.tsx` → `0` (el modal ad-hoc de lanzamiento desapareció; queda el diálogo compartido).
- **KPI-6 — Tipos verdes:** `npx tsc --noEmit` → exit 0.
- **KPI-7 — El contador de diálogos nativos del plan del latido único quedó en 0 y sigue mordiendo:** `npx vitest run src/__tests__/uiDebtRatchet.test.ts` → exit 0, con la dimensión `nativeDialogByFile` en **0 por archivo** tras F2 **y movida a la lista `forcedZero` del test (A1: el 0 es absoluto — ni un regen futuro puede resubirlo)**.
- **KPI-8 — Conservación 1:1 del human-in-the-loop (C4):** la tabla congelada de F0 (las 32 llamadas clasificadas) figura **32/32 como MIGRADA** con su reemplazo `archivo:símbolo` en el resumen de implementación; **ninguna** fila queda ELIMINADA-SIN-REEMPLAZO. Binario: la tabla está completa o no lo está.

> **Nota de exit codes (C2):** `grep -c` devuelve **exit 1** cuando imprime `0` — todos los gates "→ 0" de este plan se juzgan por el NÚMERO en stdout, no por el exit code (en shells con `set -e`, sufijar `|| true`).

**KPIs de impacto (proyectados, verificables por observación manual):**

| Métrica | Hoy (recuento en frío) | Con el plan |
|---|---|---|
| Modales con `role="dialog"` **+ Escape + focus-trap** | **0** (21 archivos tienen `role="dialog"`, pero **0** modales tienen focus-trap y **0** cierran con Escape) | **15+** (todos los migrados, vía la primitiva) |
| Superficies modales sin `role="dialog"` | **6** (EditProjectModal, FileManagerModal, NewProjectModal, CommitPipelineModal, + los 2 inline RunModal/DetailModal) | **0** |
| Diálogos nativos del navegador en `src` | **32** llamadas en **16** archivos | **0** |
| Implementaciones del flujo "lanzar agente" | **2** (RunModal inline + AgentLaunchModal) | **1** (diálogo compartido) |
| Primitiva `Dialog` en `components/ui/` | **no existe** | **existe** y es el contrato canónico |

**Impacto esperado:** cada diálogo de Stacky cierra con Escape, atrapa el foco mientras está abierto y lo devuelve al disparador al cerrar, respeta el tema claro/oscuro, y no bloquea el hilo del navegador. Las confirmaciones destructivas siguen estando (human-in-the-loop intacto) pero ahora son de marca. Un cambio de estilo o de comportamiento en los diálogos se hace **una vez** en la primitiva, no catorce veces. Y el flujo de lanzar agente deja de tener dos copias que hay que arreglar por separado.

---

## 2. Por qué ahora / gap que cierra (evidencia RECONTADA en frío)

> **TESIS del debate ("un diálogo para gobernarlos a todos"):** los 3 gaps (U1 modales inconsistentes, U3 diálogos nativos, U6 lanzamiento duplicado) comparten **UNA causa raíz**: no existe primitiva `Dialog` canónica. Sin puerta común, cada superficie improvisó. La cura es crear la puerta y migrar todo.

### 2.1 U1 — No existe primitiva `Dialog`; cada modal se inventó solo

- **No hay `Dialog` en `components/ui/`.** El barrel `frontend/src/components/ui/index.ts` (contrato congelado del plan de sistema de diseño) exporta hoy **13** primitivas: `Button`, `IconButton`, `StatusChip`, `Card`, `SectionHeader`, `Tabs`, `Skeleton`, `Spinner` + `Field`, `Input`, `Select`, `Textarea`, `Checkbox` (aditivo del plan 162 de formularios, IMPLEMENTADO — **DRIFT CORREGIDO en v2 (C3):** el v1 decía 8 porque el 162 aún no estaba en main). **Ninguna es un diálogo/modal.** Verificado: `ls frontend/src/components/ui/Dialog.tsx` → no existe.
- **focus-trap = 0 en TODO el frontend.** `grep -rE "focus-trap|focusTrap|trapFocus|useFocusTrap" frontend/src` → **0 coincidencias**. Ningún modal atrapa el foco: con Tab, el foco se escapa detrás del overlay hacia el contenido de fondo.
- **Ningún modal cierra con Escape.** `grep -rn '"Escape"' frontend/src --include=*.ts --include=*.tsx` → **5 archivos**, y **NINGUNO es un modal**: son `components/CommandPalette.tsx`, `components/TeamManageDrawer.tsx`, `components/dbcompare/ObjectDrilldown.tsx`, `pages/PlansBoardPage.tsx`, `hooks/useKeyboardShortcuts.ts` (paleta, drawers, drilldown, página, hook global). **DRIFT CORREGIDO:** el debate citó "solo 3 archivos manejan Escape"; el recuento en frío da **5** — pero el punto que importa es más fuerte: **de esos 5, cero son diálogos modales**, así que los 15 modales tienen exactamente **0** manejo de Escape.
- **6 superficies modales sin `role="dialog"`.** `grep -rlE 'role="dialog"|aria-modal' frontend/src` → **21 archivos** tienen semántica de diálogo (**DRIFT CORREGIDO:** el debate dijo "algunos sin role"; en realidad **muchos SÍ lo tienen**). De los **15** archivos `*Modal*.tsx`, tienen `role="dialog"`: `AgentConfigModal`, `AgentHistoryModal`, `AgentLaunchModal`, `ClaudeCliConfigModal`, `DailyStandupModal`, `DataReadinessModal`, `EpicFromBriefModal`, `FileSelectorModal`, `IncidentResolverModal`, `IntentPreflightModal`, `QaBrowserRunModal` (11). **NO** lo tienen: `EditProjectModal`, `FileManagerModal`, `NewProjectModal`, `devops/CommitPipelineModal` (4), más los **2 modales inline** `RunModal` (dentro de `pages/TicketBoard.tsx`) y `DetailModal` (dentro de `pages/SystemLogsPage.tsx`). Total sin semántica de diálogo: **6 superficies**.
- **Inventario de superficies modales (RECONTADO — 15 archivos `*Modal*.tsx` + 2 inline):**

| # | Archivo / símbolo | `role="dialog"` | Escape | focus-trap | `shouldCloseOnBackdrop` |
|---|---|---|---|---|---|
| 1 | `components/AgentConfigModal.tsx` | sí | no | no | sí (`:110`) |
| 2 | `components/AgentHistoryModal.tsx` | sí | no | no | no |
| 3 | `components/AgentLaunchModal.tsx` (canónico, 457 líneas) | sí (`:294`) | no | no | sí (`:287`) |
| 4 | `components/ClaudeCliConfigModal.tsx` | sí | no | no | no |
| 5 | `components/DailyStandupModal.tsx` | sí | no | no | no |
| 6 | `components/DataReadinessModal.tsx` | sí | no | no | no |
| 7 | `components/EditProjectModal.tsx` | **no** | no | no | sí (`:304`) |
| 8 | `components/EpicFromBriefModal.tsx` | sí | no | no | sí (`:448`) |
| 9 | `components/FileManagerModal.tsx` | **no** | no | no | sí (`:102`) |
| 10 | `components/FileSelectorModal.tsx` | sí | no | no | no |
| 11 | `components/IncidentResolverModal.tsx` | sí | no | no | no |
| 12 | `components/IntentPreflightModal.tsx` | sí | no | no | sí (`:59`) |
| 13 | `components/NewProjectModal.tsx` | **no** | no | no | no |
| 14 | `components/QaBrowserRunModal.tsx` | sí | no | no | no |
| 15 | `components/devops/CommitPipelineModal.tsx` | **no** | no | no | no |
| 16 | inline `RunModal` en `pages/TicketBoard.tsx:94-231` | **no** | no | no | no |
| 17 | inline `DetailModal` en `pages/SystemLogsPage.tsx:38-...` (render `:375`) | **no** | no | no | no |

- **DRIFT CORREGIDO (inventario):** el prompt del debate citó 13 modales + `DetailModal` = 14. El recuento en frío encuentra **15 archivos `*Modal*.tsx`** (los 2 extra no citados: `devops/CommitPipelineModal.tsx` e `IncidentResolverModal.tsx`) **+ 2 inline** = **17 superficies**. La migración de F3 usa el número REAL del día, no el 14.

### 2.2 U3 — 32 acciones destructivas y errores caen a diálogos nativos del navegador

- **DRIFT CORREGIDO (recuento):** el debate estimó "~20-35 en 12-17 archivos". El scan en frío (regex de familia de diálogos nativos, `.ts` + `.tsx`, excluyendo tests) da **32 llamadas en 16 archivos**. Distribución real:

| Archivo | Llamadas |
|---|---|
| `components/AgentHistoryPage.tsx` | 8 |
| `components/devops/PipelineBuilderSection.tsx` | 5 |
| `components/TopBar.tsx` | 2 |
| `components/devops/ServersSection.tsx` | 2 |
| `components/devops/ProductionFlow.tsx` | 2 |
| `components/devops/VariablesSection.tsx` | 2 |
| `pages/TicketBoard.tsx` | 2 |
| `components/ActiveRunsPanel.tsx` | 1 |
| `components/ClientProfileEditor.tsx` | 1 |
| `components/EpicChildrenPanel.tsx` | 1 |
| `components/EpicFromBriefModal.tsx` | 1 |
| `components/dbcompare/EnvironmentsPanel.tsx` | 1 |
| `pages/FlowConfigPage.tsx` | 1 |
| `components/devops/DeploymentsSection.tsx` | 1 (entrada nativa / prompt de rollback) |
| `components/devops/RemoteConsoleSection.tsx` | 1 |
| `hooks/useAgentRun.ts` | 1 **(nótese: es `.ts`, no `.tsx` — el scan DEBE incluir `.ts`)** |

- **OJO exclusiones (C5, verificado 2026-07-18):** `src/incidents/incidentModel.test.ts:172` (plan 166) contiene un fixture XSS cuyo string matchea el regex (el identificador de aviso nativo seguido de paréntesis, dentro de un literal de test). Ese archivo está FUERA de `__tests__/`, así que un scan que excluya solo `__tests__/` (la letra del contrato 156-F6) lo contaría y el "0 por archivo" sería INALCANZABLE. Regla de este plan: TODO scan de la familia (el conteo de F2 Y la dimensión `nativeDialogByFile` del ratchet) excluye `**/__tests__/**` **y** `*.test.*` (ver pre-check de F2).
- **Ejemplos ancla (verificados):** borrar todo el historial de un ticket en `components/AgentHistoryPage.tsx:603`; eliminar un proyecto en `components/TopBar.tsx:133` (y su aviso de error en `:138`); cancelar un run en `pages/TicketBoard.tsx:333` (y su aviso de error en `:343`); entrada nativa (prompt) para tipear el nombre y confirmar un rollback en `components/devops/DeploymentsSection.tsx:136`.
- **Por qué duele:** (a) el diálogo nativo del navegador **ignora el tema** claro/oscuro del plan de tema+A11y (se ve como una alerta de sistema operativo, no como Stacky); (b) **bloquea el hilo** del navegador (nada más responde mientras está abierto); (c) **ignora los canales de marca que ya existen**: `ConfirmButton` (patrón "confirmar en el propio botón" del plan de protección de trabajo, en `components/ConfirmButton.tsx`, máquina de estados en `services/uiGuards.ts:nextConfirmState`) y `Toast` (canal de errores del plan de cero-errores-mudos, en `components/Toast.tsx`).
- **`Toast` es component-local (dato para el implementador):** `components/Toast.tsx` exporta `default Toast` + `type ToastState` + `type ToastVariant = "success" | "warning" | "error"`. **No hay provider global ni hook `useToast`**: cada consumidor tiene su propio `const [toast, setToast] = useState<ToastState | null>(null)` y renderiza `<Toast .../>` (ver `components/RecoverExecutionButton.tsx:87,120`). El barrel `ui/index.ts` prohíbe explícitamente re-crear Toast ("El Toast unificado es contrato del plan 135 F5 — PROHIBIDO crearlo acá"). **Consecuencia para F2:** un error que hoy usa el aviso nativo se migra al canal `Toast` (sembrando `ToastState` local + render `<Toast>`), NO a un aviso de marca. Ver §5 F2, "Regla de destino".

### 2.3 U6 — El flujo "lanzar agente" está implementado dos veces

- **RunModal ad-hoc (dentro del tablero):** `pages/TicketBoard.tsx:94-231` — `interface RunModalProps` (`:96`), `function RunModal({...})` (`:108`), render vía `createPortal(modalContent, document.body)` (`:230`), montado en `:549`. **~137 líneas** de modal a mano: overlay `styles.modalOverlay` con `onClick={onClose}`, inner con `stopPropagation`, sin Escape, sin `role="dialog"`, sin focus-trap. Tiene selector de runtime + nota + modo sugerido/personalizado, todo scopeado a un ticket.
- **AgentLaunchModal canónico:** `components/AgentLaunchModal.tsx` (**457 líneas**, `export default function AgentLaunchModal({ agent, avatarValue, onClose })` en `:61`). Tiene `role="dialog" aria-modal="true"` (`:294`), usa `shouldCloseOnBackdrop` (`:287`), pero **tampoco** tiene Escape ni focus-trap.
- **DRIFT CORREGIDO (consumidores):** el debate dijo que AgentLaunchModal lo usan "EmployeeCard, ChatDrawer, docs/DocumenterButton". Recuento en frío: **solo `components/EmployeeCard.tsx` lo importa y lo renderiza** (`:14` import, `:133` render). `ChatDrawer.tsx:174` y `docs/DocumenterButton.tsx:39` **solo lo MENCIONAN en comentarios** (no lo renderizan). O sea: el flujo de lanzar agente tiene hoy **dos puntos de entrada de UI reales** — el RunModal del tablero y el AgentLaunchModal de la tarjeta de empleado — con distinto código para lo mismo. Cualquier arreglo (Escape, focus-trap, tema) hay que aplicarlo **dos veces**.

### 2.4 Sustrato existente que la primitiva DEBE integrar y reusar (leído, no supuesto)

| Símbolo | Archivo:línea (recontado) | Rol en 164 |
|---|---|---|
| `shouldCloseOnBackdrop({dirty,busy})` | `services/uiGuards.ts:16` (test `services/uiGuards.test.ts`) | F1: el `Dialog` acepta un `closeGuard` que lo llama para decidir Escape/backdrop. Ya lo usan **6 modales + FinishWorkButton** (`AgentConfigModal:110`, `AgentLaunchModal:287`, `EditProjectModal:304`, `EpicFromBriefModal:448`, `FileManagerModal:102`, `IntentPreflightModal:59`, `FinishWorkButton:128`) — **DRIFT CORREGIDO:** el debate citó solo 2. |
| `ConfirmButton` + `nextConfirmState` | `components/ConfirmButton.tsx`, `services/uiGuards.ts` | Patrón "confirmar en el botón". Para confirmaciones **inline** que ya son botones, `ConfirmButton` sigue siendo válido; `useConfirm()` es para las que hoy son diálogos nativos bloqueantes. §8 aclara el límite. |
| `Toast` + `ToastState` + `ToastVariant` | `components/Toast.tsx:9,11,19` | F2: destino de los errores hoy en avisos nativos. Component-local (§2.2). |
| `createPortal` | patrón ya usado en `pages/TicketBoard.tsx:230` | F1: el `Dialog` monta su overlay en `document.body` con el mismo mecanismo. |
| barrel `ui/index.ts` | `components/ui/index.ts` | F1 agrega los exports de `Dialog`, `ConfirmDialog`, `AlertDialog`, `PromptDialog`, `useConfirm`, `useAlert`, `useTextPrompt` (aditivo; las 13 primitivas existentes no se tocan). |
| `Field`, `Input`, `firstErrorFieldId` | `components/ui/Field.tsx`, `components/ui/Input.tsx` (plan 162, IMPLEMENTADO) | C3/A2: `PromptDialog` y el type-to-confirm usan `Field`+`Input` (PROHIBIDO `<input>` crudo). El focus-trap NO interfiere con el foco-al-primer-error del 162: el trap solo intercepta Tab/Escape y fija el foco inicial; el foco programático del 162 dentro del panel sigue funcionando igual. |
| montaje root | `main.tsx:17-21` (`<QueryClientProvider><App/></QueryClientProvider>`) | F1 envuelve `<App/>` con `<DialogHost>` (un único montaje global). |
| `uiDebtRatchet` + baseline + dimensión `nativeDialogByFile` | `src/__tests__/uiDebtRatchet.test.ts` + `src/__tests__/uiDebtBaseline.json` | La dimensión `nativeDialogByFile` la **crea el plan del latido único** (only-decrease). F2 la lleva a **0 por archivo**; F6 de aquel plan queda satisfecho. |
| `AgentRuntimeSelector`, `runtimeRequiresVsCodeAgent`, `runtimeDisplayLabel`, `launchInProgressLabel` | usados en `pages/TicketBoard.tsx:179-223` y en `AgentLaunchModal` | F4: el diálogo compartido de lanzamiento reusa estos helpers tal cual (no se reescriben). |
| `services/agentLaunch.ts` | `services/agentLaunch.ts:47` (comentario: contrato de lanzamiento común a epic y AgentLaunchModal) | F4: es el lugar natural para el helper de lanzamiento compartido; el diálogo unificado lo consume. |

---

## 3. Principios y guardarraíles

1. **Una puerta, catorce entradas.** La primitiva `Dialog` es la única forma canónica de abrir un modal. Todo lo demás se migra hacia ella; nada nuevo se construye a mano.
2. **Backward-compatible en semántica, mejora en presentación.** Ningún flujo cambia lo que hace: las mismas confirmaciones, los mismos textos, las mismas acciones. Solo cambia **cómo se ve y se comporta** (tema, foco, teclado). El operador no aprende nada nuevo.
3. **El focus-trap y `aria-modal` MEJORAN la accesibilidad; nada se vuelve más lento.** Atrapar el foco, restaurarlo al cerrar y declarar `role="dialog"`/`aria-modal` son ganancias netas de A11y sin costo perceptible.
4. **Las confirmaciones SON el human-in-the-loop.** `useConfirm()` no elimina ninguna confirmación: la mejora. Ninguna acción destructiva pasa a ser automática. El operador sigue decidiendo, ahora en un diálogo de marca.
5. **Reusar el sustrato, no reinventar.** El `Dialog` integra `shouldCloseOnBackdrop` (guarda ya testeada); los errores van al `Toast` ya existente; el portal usa el mismo `createPortal` que ya se usa. No se crea infraestructura paralela.
6. **Lógica pura, no `render()`.** `@testing-library/react` y `jsdom` NO están en `frontend/package.json` (gap estructural conocido). Toda la lógica testeable de la primitiva (decisión de teclado, cálculo del próximo foco, guarda de cierre, reducer del host) vive en **módulos puros** sin DOM; los tests los cubren sin `render()`. El comportamiento real de DOM (foco que se mueve, foco que se restaura, portal que monta) se valida por **smoke MANUAL** del operador. El gate de UI real = `tsc --noEmit` + los tests puros + smoke manual.
7. **Migrar por lotes, con trinquete.** F3 migra los 15 modales en lotes; un ratchet only-decrease de "modales ad-hoc fuera de la primitiva" con **allowlist congelada** garantiza que la deuda solo baje, nunca suba, aunque el plan se implemente en varias sesiones.
8. **Stress-test ANTES de comprometerse.** F1 prueba el contrato de la primitiva contra los 3 modales de mayor riesgo/tráfico (FileManagerModal, IntentPreflightModal, AgentLaunchModal). Si el contrato no cubre alguno (p. ej. un modal que en realidad es drawer con foco custom), se sabe en F1, no en F4.
9. **Anti-gamear gates (CRÍTICO en este plan).** Los gates de F2/F3 grepan la llamada literal de diálogo nativo en `src`. Por eso **ni la prosa de este doc, ni los comentarios del código, ni los mensajes de test** pueden contener esa cadena literal (identificador de familia nativo seguido de paréntesis). Se nombra **siempre perifrásticamente** ("el diálogo de confirmación nativo del navegador", "el aviso nativo bloqueante", "la entrada nativa del navegador"). El gate siempre gana; jamás se relaja. Gotcha con múltiples recurrencias históricas.
10. **Mono-operador sin auth.** Nada de RBAC; ningún diálogo valida `current_user`. No aplica.
11. **No degradar.** La primitiva REDUCE código duplicado, MEJORA A11y y unifica el tema. El `closeGuard` PROTEGE el trabajo sin terminar. Ningún eje empeora.
12. **Toda promesa del host SE RESUELVE, siempre (C1).** Cerrar un diálogo del host por CUALQUIER vía (botón primario, Cancelar, X, Escape, backdrop) resuelve su promesa; el dismiss settlea con el valor neutro del kind (`false`/`undefined`/`null`). Un `await` sobre el host JAMÁS queda colgado; el settle es idempotente (la primera resolución gana).

---

## 4. Glosario (para un modelo menor que no conoce Stacky)

| Término | Definición |
|---|---|
| **primitiva / design-system** | Un componente base, reusable y con contrato fijo, del sistema de diseño (viven en `components/ui/`). "Crear la primitiva `Dialog`" = escribir el componente canónico del que todos los modales derivarán. |
| **portal** | Un mecanismo de React (`createPortal`) que renderiza un componente en un nodo del DOM **fuera** del árbol del padre (acá, `document.body`), para que el overlay del modal quede por encima de todo sin problemas de `z-index`/`overflow` del contenedor. |
| **focus-trap** | Mantener el foco del teclado **atrapado dentro** del modal mientras está abierto: al llegar con Tab al último elemento enfocable, el foco vuelve al primero (y con Shift+Tab, del primero al último), en vez de escaparse al contenido de fondo. Requisito de accesibilidad de un diálogo modal. |
| **aria-modal** | Atributo ARIA (`aria-modal="true"`) que le dice a las tecnologías de asistencia que el contenido de fondo está inerte mientras el diálogo está abierto. Va junto con `role="dialog"`. |
| **restore-focus** | Al cerrar el modal, devolver el foco al elemento que lo abrió (el "trigger"), para que el usuario de teclado no quede perdido. El `Dialog` guarda `document.activeElement` al montar y lo re-enfoca al desmontar. |
| **closeGuard** | Una función que el `Dialog` consulta antes de cerrar por Escape o por clic en el backdrop: si el modal está "sucio" (`dirty`: hay cambios sin guardar) o "ocupado" (`busy`: hay una operación en curso), NO cierra. Integra el contrato ya existente `shouldCloseOnBackdrop({dirty,busy})`. |
| **promise-based hook** | Un hook (`useConfirm`/`useAlert`) que devuelve una función `async` que se puede `await`-ear: `const ask = useConfirm(); if (await ask({...})) { ...borrar... }`. En vez de renderizar un modal a mano y manejar callbacks, el código pide una confirmación y espera la respuesta como si fuera una promesa. **El resultado NUNCA se llama `confirm`/`alert`/`prompt`** (ver §9: esos nombres colisionan con el gate). |
| **ratchet only-decrease / trinquete** | Un contador congelado en un baseline que **falla el test si sube**. Bajar (limpiar deuda) está permitido y requiere regenerar el baseline. Acá: la cantidad de modales ad-hoc fuera de la primitiva solo puede decrecer. |
| **uiDebtRatchet** | Test de vitest (del plan de sistema de diseño) que congela, POR ARCHIVO, contadores de deuda visual (`style={{` inline en `.tsx`, colores hex en `.module.css`, y — agregado por el plan del latido único — `nativeDialogByFile`). |
| **allowlist congelada** | La lista explícita de archivos que TODAVÍA tienen un modal ad-hoc (fuera de la primitiva), guardada en un JSON. El test verifica que ningún archivo fuera de la allowlist tenga un modal ad-hoc y que la allowlist no crezca. |
| **diálogo nativo del navegador** | Las funciones de bloqueo modal que el navegador provee de fábrica (confirmación/aviso/entrada). Bloquean el hilo, ignoran el tema de la app y no son accesibles con el diseño de Stacky. Son el antipatrón que este plan elimina. |
| **DialogHost** | El provider global (montado una sola vez alrededor de `<App/>`) que renderiza los diálogos pedidos por `useConfirm`/`useAlert`/`useTextPrompt` y resuelve sus promesas. |
| **settle / dismiss** | "Settle" = resolver la promesa de una petición del host, UNA sola vez (idempotente). "Dismiss" = cierre sin decisión explícita (Escape/backdrop/X/Cancelar): settlea con el valor neutro del kind — confirm→`false`, alert→`undefined`, prompt→`null` (helper puro `dismissValueFor`). No existe camino de cierre que no resuelva (C1). |
| **PromptDialog / useTextPrompt** | (A2) La entrada de texto de marca que reemplaza la entrada nativa del navegador: un `Dialog` con `Field`+`Input` del plan 162. `requiredText` activa el modo type-to-confirm (confirmar se habilita solo si el texto coincide exactamente). Devuelve `Promise<string \| null>` (`null` = dismiss/cancelar). |

---

## 5. Fases

> **Pre-flight OBLIGATORIO por fase que toque archivo caliente** (`components/ui/index.ts`, `main.tsx`, `src/__tests__/uiDebtRatchet.test.ts`, `src/__tests__/uiDebtBaseline.json`, y cada archivo migrado en F2/F3/F4): `git status -- "<ruta>"`. Si hay WIP ajeno, STOP y avisar al orquestador (sesiones paralelas en el mismo árbol son un escenario real conocido). Staging quirúrgico por path explícito. **El implementador NO commitea** (lo hace el orquestador).
>
> **Comandos:** todo es frontend, desde el checkout real `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend` (POSIX: `cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"`). Tests: `npx vitest run src/<archivo>` — **SIEMPRE por archivo** (cross-file pollution conocida). Tipos: `npx tsc --noEmit`. Correr `tsc` al terminar cada fase.
>
> **Orden de implementación:** F0 → F1 → F2 → F3 → F4. F1 crea la primitiva (todo depende de ella). F2 elimina los diálogos nativos (independiente de F3/F4 pero conviene antes para dejar el contador en 0 temprano). F3 migra los modales por lotes (el lote 1 = el trío del stress-test de F1). F4 (recortable) unifica el lanzamiento de agente. El ratchet de F3 se congela DESPUÉS de que el lote 1 migre, y se re-baja en cada lote.

---

### F0 — Inventario congelado y contrato de la primitiva (solo lectura)

**Objetivo (1 frase):** dejar escrito, dentro del propio plan y como comentario del test del ratchet de F3, el inventario EXACTO de las 17 superficies modales y las 32 llamadas a diálogos nativos que hay HOY, para que F1..F4 no inventen ni omitan ninguna. **Valor:** la migración parte de una lista verificada, no de una estimación.

**Archivos:** ninguno se modifica (fase de solo lectura — **C8:** el inventario y la tabla de conservación se entregan como BLOQUE DE TEXTO en el resumen de implementación; el docstring del contrato se escribe recién en F1 y el comentario-inventario del ratchet recién en F3).

**Procedimiento EXACTO:**
1. Recontar las superficies modales: `find src -name "*Modal*.tsx" | grep -v __tests__` (debería dar 15) + los 2 inline (`RunModal` en `pages/TicketBoard.tsx`, `DetailModal` en `pages/SystemLogsPage.tsx`). Confirmar contra la tabla de §2.1. Si aparece un `*Modal*.tsx` nuevo (otra sesión pudo agregarlo), incluirlo.
2. Recontar las llamadas a diálogos nativos con el comando de F2 (abajo). Confirmar el total (~32) y la distribución por archivo de §2.2. **Usar el número REAL del día**, no el 32.
3. Redactar el **contrato de la primitiva** (props del `Dialog`, firma de `useConfirm`/`useAlert`/`useTextPrompt` y la semántica settle/dismiss de C1) para el resumen de implementación (**C8:** en F0 NO se escribe ningún archivo; el docstring se materializa en F1).
4. **Tabla de conservación (C4):** construir la tabla de las 32 llamadas — una fila por llamada: `archivo`, `qué protege`, clasificación {confirmación-destructiva | error | info | entrada}, destino {useConfirm | Toast | useAlert | useTextPrompt}. Esta tabla es el contrato del KPI-8: en F2 cada fila DEBE terminar MIGRADA con su reemplazo `archivo:símbolo`.

**Contrato acordado de la primitiva** (materializar en F1):

```ts
// Dialog.tsx
interface DialogProps {
  open: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  children: React.ReactNode;
  /** Guarda de cierre: si devuelve false, Escape y backdrop NO cierran. */
  closeGuard?: { dirty: boolean; busy: boolean };
  /** aria-label si no hay title textual. */
  ariaLabel?: string;
  /** Ancho/variante visual opcional (clase de módulo, no inline-style). */
  size?: "sm" | "md" | "lg";
  /** El foco inicial: por defecto el primer enfocable; se puede forzar por ref. */
  initialFocusRef?: React.RefObject<HTMLElement>;
}

// DialogHost.tsx (provider + hooks promise-based)
// REGLA DURA (C1): TODA via de cierre resuelve la promesa (settle idempotente).
// Dismiss (Escape con guard OK / backdrop / X / Cancelar) settlea con el valor
// neutro del kind: confirm -> false; alert -> undefined; prompt -> null
// (helper puro dismissValueFor, testeado).
function useConfirm(): (opts: {
  title?: React.ReactNode; message: React.ReactNode;
  confirmLabel?: string; cancelLabel?: string; tone?: "default" | "danger";
}) => Promise<boolean>;

function useAlert(): (opts: {
  title?: React.ReactNode; message: React.ReactNode; okLabel?: string;
}) => Promise<void>;

// A2 — entrada de texto de marca (reusa Field+Input del plan 162):
function useTextPrompt(): (opts: {
  title?: React.ReactNode; message: React.ReactNode;
  label?: string; initialValue?: string;
  /** type-to-confirm: confirmar se habilita solo si el texto coincide exacto. */
  requiredText?: string;
  confirmLabel?: string; cancelLabel?: string; tone?: "default" | "danger";
}) => Promise<string | null>;
```

**Criterio de aceptación BINARIO:** el inventario de superficies, el conteo de diálogos nativos y la **tabla de conservación de 32 filas (C4)** están escritos en el resumen; el contrato de props/hooks (incluida la semántica settle/dismiss de C1 y `useTextPrompt` de A2) está fijado. No hay superficie ni llamada sin clasificar.

**Flag:** N/A. **Runtimes:** N/A (solo lectura). **Trabajo del operador: ninguno.**

---

### F1 — Primitiva `Dialog` + hooks `useConfirm`/`useAlert` + STRESS-TEST del contrato

**Objetivo (1 frase):** crear la primitiva canónica (`components/ui/Dialog.tsx`: portal + overlay + `role="dialog"` + `aria-modal` + Escape + focus-trap sin librerías + restore-focus + `closeGuard`), sus derivados de marca `ConfirmDialog`/`AlertDialog`/`PromptDialog` (A2), y los hooks promise-based `useConfirm()`/`useAlert()`/`useTextPrompt()` vía un `DialogHost` global — y **probar el contrato contra los 3 modales de mayor riesgo/tráfico** (FileManagerModal, IntentPreflightModal, AgentLaunchModal) para saber ACÁ, no en F4, si algo no encaja. **Valor:** la puerta canónica existe y se demostró que sirve para los casos difíciles antes de migrar los 15.

**Archivos:**
- NUEVO `frontend/src/components/ui/dialogKeyboard.ts` (helpers PUROS: decisión de teclado, próximo foco, resolución de cierre)
- NUEVO `frontend/src/components/ui/Dialog.tsx` (la primitiva; consume los helpers puros)
- NUEVO `frontend/src/components/ui/Dialog.module.css` (overlay/panel con tokens de `theme.css`; sin inline-style; **A3:** transición breve de entrada del panel + `@media (prefers-reduced-motion: reduce)` que la desactiva — autocontenido, sin depender de tokens de motion)
- NUEVO `frontend/src/components/ui/ConfirmDialog.tsx` y `frontend/src/components/ui/AlertDialog.tsx` (de marca, construidos sobre `Dialog`)
- NUEVO `frontend/src/components/ui/PromptDialog.tsx` (A2: entrada de texto de marca sobre `Dialog`, con `Field`+`Input` del plan 162)
- NUEVO `frontend/src/components/ui/DialogHost.tsx` (provider + `useConfirm`/`useAlert`; reducer PURO extraído)
- NUEVO `frontend/src/components/ui/dialogHostReducer.ts` (reducer PURO de la cola de peticiones)
- NUEVO `frontend/src/components/ui/__tests__/dialogKeyboard.test.ts` y `frontend/src/components/ui/__tests__/dialogHostReducer.test.ts`
- MODIFICADO `frontend/src/components/ui/index.ts` (exports nuevos: `Dialog`, `ConfirmDialog`, `AlertDialog`, `PromptDialog`, `useConfirm`, `useAlert`, `useTextPrompt` — aditivo; las 13 primitivas existentes no se tocan)
- MODIFICADO `frontend/src/main.tsx` (envolver `<App/>` con `<DialogHost>`)
- MODIFICADO `frontend/src/components/FileManagerModal.tsx`, `frontend/src/components/IntentPreflightModal.tsx`, `frontend/src/components/AgentLaunchModal.tsx` (stress-test: migrar los 3 a la primitiva)

**Paso 1 — Helpers PUROS `dialogKeyboard.ts`** (nada de DOM; 100% testeable):

```ts
import { shouldCloseOnBackdrop } from "../../services/uiGuards";

export type DialogKeyAction = "close" | "focus-first" | "focus-last" | null;

/** Decide la accion de teclado de un dialogo modal.
 *  atFirst/atLast: si el foco esta en el primer/ultimo enfocable. */
export function dialogKeydownAction(
  key: string,
  shiftKey: boolean,
  pos: { atFirst: boolean; atLast: boolean },
): DialogKeyAction {
  if (key === "Escape") return "close";
  if (key === "Tab" && !shiftKey && pos.atLast) return "focus-first"; // wrap hacia adelante
  if (key === "Tab" && shiftKey && pos.atFirst) return "focus-last";  // wrap hacia atras
  return null;
}

/** Indice del proximo enfocable con wraparound (para el focus-trap). */
export function nextFocusableIndex(count: number, current: number, shiftKey: boolean): number {
  if (count <= 0) return -1;
  const delta = shiftKey ? -1 : 1;
  return (current + delta + count) % count;
}

/** El dialogo puede cerrar por Escape/backdrop? Reusa la guarda ya testeada.
 *  El cierre por boton explicito (X/Cancelar) NO pasa por aca: es intencion directa. */
export function canCloseByGuard(guard?: { dirty: boolean; busy: boolean }): boolean {
  if (!guard) return true;
  return shouldCloseOnBackdrop(guard);
}
```

**Paso 2 — `Dialog.tsx`** (consume los helpers; el ÚNICO lugar con efectos de DOM):
- Si `!open`, devuelve `null`.
- `createPortal(panel, document.body)` (mismo patrón que `TicketBoard.tsx:230`).
- Al montar: guardar `const trigger = document.activeElement as HTMLElement | null` (para restore-focus); enfocar `initialFocusRef?.current` o el primer enfocable del panel. Al desmontar (cleanup del `useEffect`): `trigger?.focus()`.
- `onKeyDown` del panel: calcular `atFirst/atLast` sobre la lista de enfocables (`panel.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])')`), llamar `dialogKeydownAction(e.key, e.shiftKey, {atFirst, atLast})`; si `"close"` y `canCloseByGuard(closeGuard)` → `e.preventDefault(); onClose()`; si `"focus-first"/"focus-last"` → `e.preventDefault()` + enfocar el extremo correspondiente (el focus-trap real). **Estilos dinámicos por `ref`+efecto imperativo si hicieran falta, JAMÁS `style={{}}`** (gotcha uiDebtRatchet: archivos `.tsx` nuevos nacen con alcance CERO a inline-style).
- **Burbujeo por portales (C6a):** tras manejar una tecla (`"close"`/`"focus-first"`/`"focus-last"`), llamar `e.stopPropagation()` además de `preventDefault()`. Los eventos de React burbujean por el árbol de REACT a través de los portales: sin esto, Escape en un diálogo anidado cerraría también el de abajo.
- **Scroll-lock + fondo inerte (C6b):** efecto imperativo con contador de diálogos abiertos a nivel módulo (`let openDialogCount = 0`): al montar el PRIMERO, `document.body.classList.add("dialogScrollLock")` y setear el atributo `inert` en `#root`; al desmontar el ÚLTIMO, quitar ambos ANTES de restaurar el foco. La clase se define en `Dialog.module.css` vía `:global(body.dialogScrollLock) { overflow: hidden; }`. JAMÁS estilos inline. Si `inert` diera problemas en el smoke, degradar a `aria-hidden="true"` en `#root` y documentarlo en el resumen. (El panel vive en un portal a `document.body`, hermano de `#root`, así que `inert` en `#root` no lo afecta.)
- **z-index (C6c):** el overlay usa `z-index: var(--z-dialog, 1000)` en la clase del módulo. Antes de fijar el valor, grep del mayor `z-index` existente en `src/**/*.module.css` y `theme.css`; `--z-dialog` DEBE quedar por encima de drawers y paleta de comandos (si `theme.css` no define el token, agregarlo ahí).
- **StrictMode (nota):** `main.tsx` monta bajo `React.StrictMode` — en dev los efectos corren doble. El contador de scroll-lock y el settle idempotente (Paso 3) hacen los efectos re-entrantes; no escribir lógica de foco que dependa de "correr exactamente una vez".
- Overlay: `<div className={styles.overlay} onClick={(e) => { if (e.target === e.currentTarget && canCloseByGuard(closeGuard)) onClose(); }}>` con el panel `<div className={styles.panel} role="dialog" aria-modal="true" aria-label={ariaLabel} aria-labelledby={...}>`.
- **Casos borde a cubrir explícitamente:** (a) **foco inicial** — si no hay `initialFocusRef` ni enfocables, enfocar el panel mismo (`tabIndex={-1}`); (b) **cierre por Escape** — solo si `canCloseByGuard`, y con `stopPropagation` (C6a); (c) **Tab-cycle** — wrap en ambos sentidos; (d) **restore-focus robusto (C6d)** — al desmontar, `if (trigger && document.contains(trigger)) trigger.focus();`: si el trigger ya no está en el DOM, NO llamar `focus()` sobre un nodo desprendido (sería un no-op silencioso que deja el foco perdido en `body`; el caso queda documentado, sin fallback obligatorio); (e) **doble apertura** — el host garantiza uno a la vez (Paso 4).

**Paso 3 — `dialogHostReducer.ts` (PURO) + `DialogHost.tsx`:**
- `dialogHostReducer.ts`: estado = `{ queue: DialogRequest[]; current: DialogRequest | null }`. Acciones puras: `enqueue(req)`, `resolveCurrent(value)` (saca el actual, avanza al siguiente de la cola). `DialogRequest` lleva `{ id, kind: "confirm"|"alert", opts, resolve }` — pero para el test PURO del reducer, `resolve` se modela como un id y el test verifica solo las transiciones de `queue`/`current` (FIFO, avanzar al resolver). Esto es lo testeable sin DOM.
- `dialogHostReducer.ts` exporta además 2 helpers PUROS: `dismissValueFor(kind)` (confirm→`false`, alert→`undefined`, prompt→`null`) y `textPromptCanConfirm(value: string, requiredText?: string)` (para el type-to-confirm de A2: `true` si no hay `requiredText` o si el texto coincide exacto).
- `DialogHost.tsx`: provider que usa el reducer; expone por contexto `requestConfirm(opts): Promise<boolean>`, `requestAlert(opts): Promise<void>` y `requestTextPrompt(opts): Promise<string | null>` (crean la promesa, guardan su `resolve`, encolan). Renderiza `<ConfirmDialog>`/`<AlertDialog>`/`<PromptDialog>` para `current`. `useConfirm()`/`useAlert()`/`useTextPrompt()` leen del contexto y devuelven la función async.
- **Settlement (C1, REGLA DURA):** el host settlea `current` por CUALQUIER vía de cierre: botón primario → `resolve(valor)`; Cancelar/X/Escape/backdrop → `resolve(dismissValueFor(kind))`. El `onClose` que el host pasa a `ConfirmDialog`/`AlertDialog`/`PromptDialog` ES `() => settle(dismissValueFor(kind))` — **no existe camino de cierre que no resuelva**. `settle` es idempotente: la primera resolución gana; el reducer trata `resolveCurrent` sobre un id que ya no es `current` como no-op.
- **Desmonte del consumidor (C1/R11):** si el componente que pidió la confirmación se desmonta (refetch de react-query, navegación) mientras su petición espera, la petición NO se cancela: el operador la ve y la promesa se resuelve igual al actuar (nunca cuelga). Regla para el código migrado: el continuation tras `await ask(...)` opera con los IDs capturados ANTES del await (no con objetos vivos que pudieron refrescarse); los borrados por id ya son idempotentes en el backend.

**Paso 4 — `ConfirmDialog.tsx` / `AlertDialog.tsx` / `PromptDialog.tsx`:** construidos sobre `Dialog`; `ConfirmDialog` con dos botones (usa `tone: "danger"` para acciones destructivas, clase de módulo con tokens); `AlertDialog` con un botón OK. **`PromptDialog` (A2):** con `Field`+`Input` del plan 162 (C3: PROHIBIDO `<input>` crudo), estado local del texto, `requiredText` opcional (el botón confirmar queda `disabled` mientras `textPromptCanConfirm` sea `false`; Enter en el input confirma solo si está habilitado), resuelve el `string` al confirmar y `null` al dismiss; foco inicial en el input (`initialFocusRef`). Sin inline-style; foco inicial en el botón primario (o en Cancelar para `tone: "danger"`, para no confirmar por Enter accidental).

**Paso 5 — Montaje global (`main.tsx`):** envolver `<App/>`:
```tsx
<QueryClientProvider client={queryClient}>
  <DialogHost>
    <App />
  </DialogHost>
</QueryClientProvider>
```

**Paso 6 — STRESS-TEST (migrar los 3 modales de mayor riesgo/tráfico):**
- `FileManagerModal.tsx`, `IntentPreflightModal.tsx`, `AgentLaunchModal.tsx` pasan a envolver su contenido en `<Dialog open onClose={...} closeGuard={{dirty, busy}} .../>`, reusando su MISMO `shouldCloseOnBackdrop({dirty,busy})` como `closeGuard` (los tres ya calculan `dirty`/`busy`: `FileManagerModal` → `{dirty: selected.size>0, busy: deleting}`; `IntentPreflightModal` → `{dirty: corrections.trim().length>0, busy: busy===true}`; `AgentLaunchModal` → `{dirty: selected!=null || message.trim().length>0, busy: loading}`).
- **Regla dura:** el contenido interno de cada modal (formularios, textos, lógica) NO cambia — solo se reemplaza el andamiaje de overlay/panel por el `Dialog`. Si alguno NO encaja en el contrato (p. ej. resulta ser un drawer con foco custom), **DOCUMENTARLO en el resumen y ajustar el contrato de `Dialog` ACÁ** (esa es la razón del stress-test), no en F4.

**Paso 7 — Tests PUROS:**

`src/components/ui/__tests__/dialogKeyboard.test.ts`:

| Test | Qué afirma |
|---|---|
| `test_escape_cierra` | `dialogKeydownAction("Escape", false, {atFirst:false,atLast:false})` → `"close"`. |
| `test_tab_wrap_adelante` | `dialogKeydownAction("Tab", false, {atFirst:false,atLast:true})` → `"focus-first"`. |
| `test_shift_tab_wrap_atras` | `dialogKeydownAction("Tab", true, {atFirst:true,atLast:false})` → `"focus-last"`. |
| `test_tab_intermedio_no_actua` | `dialogKeydownAction("Tab", false, {atFirst:false,atLast:false})` → `null`. |
| `test_next_index_wrap` | `nextFocusableIndex(3, 2, false)` → `0`; `nextFocusableIndex(3, 0, true)` → `2`; `nextFocusableIndex(0, 0, false)` → `-1`. |
| `test_closeGuard_bloquea` | `canCloseByGuard({dirty:true,busy:false})` → `false`; `canCloseByGuard({dirty:false,busy:true})` → `false`; `canCloseByGuard({dirty:false,busy:false})` → `true`; `canCloseByGuard(undefined)` → `true`. |

`src/components/ui/__tests__/dialogHostReducer.test.ts`:

| Test | Qué afirma |
|---|---|
| `test_enqueue_abre_primero` | Tras `enqueue(A)` sobre estado vacío, `current === A`, `queue` vacía. |
| `test_fifo` | `enqueue(A)`, `enqueue(B)` → `current === A`, `queue === [B]`. |
| `test_resolve_avanza` | Con `current=A, queue=[B]`, `resolveCurrent()` → `current === B`, `queue` vacía. |
| `test_resolve_ultimo_deja_vacio` | Con `current=A, queue=[]`, `resolveCurrent()` → `current === null`. |
| `test_settle_idempotente` (C1) | `resolveCurrent()` sobre `current === null` (o con un id que ya no es `current`) → devuelve el MISMO estado (no-op); resolver dos veces no re-avanza la cola. |
| `test_dismiss_value_por_kind` (C1) | `dismissValueFor("confirm")` → `false`; `dismissValueFor("alert")` → `undefined`; `dismissValueFor("prompt")` → `null`. |
| `test_type_to_confirm` (A2) | `textPromptCanConfirm("x", undefined)` → `true`; `textPromptCanConfirm("ab", "abc")` → `false`; `textPromptCanConfirm("abc", "abc")` → `true`. |

**Verificación manual (documentada en el DoD, por el operador):** abrir FileManagerModal / IntentPreflightModal / AgentLaunchModal → Escape cierra (si no está dirty/busy); Tab no se escapa del modal y cicla; al cerrar, el foco vuelve al botón que lo abrió; se ve con el tema activo (claro y oscuro).

**Criterio de aceptación BINARIO:** `npx vitest run src/components/ui/__tests__/dialogKeyboard.test.ts` → exit 0; `npx vitest run src/components/ui/__tests__/dialogHostReducer.test.ts` → exit 0 (incluye dismiss/idempotencia/type-to-confirm — C1/A2); `npx tsc --noEmit` → exit 0; `grep -c "role=\"dialog\"" src/components/ui/Dialog.tsx` → `1`; `grep -c "useTextPrompt" src/components/ui/index.ts` → `1` (el barrel exporta los símbolos nuevos).

**Flag:** ninguna. **Runtimes:** UI pura del panel Stacky, agnóstica del runtime de agentes. **Trabajo del operador: ninguno (mejora invisible).**

---

### F2 — Migrar las 32 llamadas a diálogos nativos → `useConfirm` / `Toast` / entrada de marca

**Objetivo (1 frase):** reemplazar cada uno de los diálogos nativos del navegador (confirmación/aviso/entrada) por el canal de marca correcto, dejando el contador de diálogos nativos en `src` en **0**. **Valor:** desaparecen las alertas de sistema operativo que rompen el tema y bloquean el hilo; las confirmaciones destructivas se vuelven de marca sin dejar de ser el human-in-the-loop.

**Regla de destino (por tipo de llamada):**
- **Confirmación destructiva** (borrar historial, eliminar proyecto, cancelar run, quitar credencial, borrar variable/borrador, etc.) → `const ask = useConfirm();` + `if (await ask({ title, message, tone: "danger", confirmLabel: "Eliminar" })) { ...acción... }`. **El resultado se llama `ask` (o `confirmDelete`, etc.), NUNCA `confirm`** (ver el GOTCHA de nombres abajo).
- **Aviso de ERROR** (los que hoy avisan un fallo tras un catch, p. ej. `TopBar:138`, `AgentHistoryPage:272/285/288/414/613`, `TicketBoard:343`, `useAgentRun.ts:60`) → **canal `Toast`** del plan de cero-errores-mudos: sembrar `const [toast, setToast] = useState<ToastState | null>(null)` + render `<Toast state={toast} .../>` + reemplazar el aviso nativo por `setToast({ variant: "error", message })`. **NO** usar un aviso de marca para errores (§2.2). Si un archivo ya tiene un `Toast`, reusarlo.
- **Aviso INFORMATIVO/validación** (no-error) → `const notify = useAlert();` + `await notify({ message })`. **El resultado se llama `notify`, NUNCA `alert`.**
- **Entrada nativa** (la de `DeploymentsSection:136` que pide tipear el nombre para confirmar un rollback; y la de `PipelineBuilderSection:207` que pide el nombre de un borrador) → `const askText = useTextPrompt();` (**A2, sin ambigüedad — C9**): el rollback usa `requiredText` (type-to-confirm: tipear el id exacto, igual que hoy); el nombre de borrador usa entrada libre con `initialValue`. El resultado se llama `askText`, JAMÁS el identificador nativo. El comportamiento de confirmación se preserva 1:1.

**Conservación 1:1 (C4 — criterio BINARIO de human-in-the-loop):** la tabla de F0 se actualiza acá: cada una de las 32 filas termina MIGRADA con su reemplazo `archivo:símbolo`. **PROHIBIDO eliminar una llamada nativa sin reemplazo equivalente**; si era confirmación destructiva, el flujo migrado DEBE seguir exigiendo la confirmación explícita ANTES de ejecutar la acción (el gate de 0 nativos NO distingue migrar de borrar — la tabla sí). El resumen pega la tabla 32/32 (KPI-8) y el smoke del DoD ejercita al menos 3 confirmaciones destructivas migradas.

**Archivos (los 16 de §2.2):** `AgentHistoryPage.tsx`, `devops/PipelineBuilderSection.tsx`, `TopBar.tsx`, `devops/ServersSection.tsx`, `devops/ProductionFlow.tsx`, `devops/VariablesSection.tsx`, `pages/TicketBoard.tsx`, `ActiveRunsPanel.tsx`, `ClientProfileEditor.tsx`, `EpicChildrenPanel.tsx`, `EpicFromBriefModal.tsx`, `dbcompare/EnvironmentsPanel.tsx`, `pages/FlowConfigPage.tsx`, `devops/DeploymentsSection.tsx`, `devops/RemoteConsoleSection.tsx`, `hooks/useAgentRun.ts`.

**Nota sobre `useAgentRun.ts` (`.ts`, no `.tsx`):** un hook no puede renderizar `<Toast>`. Migrar su aviso de error a: (a) devolver/propagar el error para que el componente consumidor lo muestre con `Toast`, o (b) usar `useAlert()` (que sí funciona desde un hook porque solo pide, no renderiza). Preferir (a) si el consumidor ya tiene canal de error; si no, (b).

**Procedimiento por archivo:** (1) `git status -- "<ruta>"` (pre-flight); (2) localizar cada llamada nativa; (3) aplicar la Regla de destino; (4) `npx tsc --noEmit`; (5) verificación manual del flujo migrado (la confirmación sigue apareciendo y la acción destructiva sigue requiriéndola).

**GOTCHA CRÍTICO 1 (anti-gamear, comentarios):** el gate de esta fase es un grep de la llamada literal en `src`. Por eso, en el código migrado, **ningún comentario** puede contener la cadena literal del diálogo nativo (identificador de familia + paréntesis). Nombrarla perifrásticamente en cualquier comentario ("se reemplaza el diálogo de confirmación nativo por useConfirm"). El gate gana.

**GOTCHA CRÍTICO 2 (colisión de NOMBRES con el gate — no obvio, se pisa fácil):** el regex del gate caza el identificador de familia (minúsculas) seguido de paréntesis, con un lookbehind que solo excluye el punto y los caracteres de palabra (`(?<![.\w])`). Por lo tanto, si el resultado del hook se guarda en una variable llamada `confirm`/`alert`/`prompt` y luego se invoca (`await <esa-variable>({...})`), **el gate la contará como si fuera una llamada nativa** y el contador NUNCA llegará a 0. **Regla dura:** el resultado de `useConfirm()`/`useAlert()` se nombra `ask`/`notify` (o `confirmDelete`, `showError`, etc.), **jamás** `confirm`/`alert`/`prompt`. Nota: `useConfirm(`/`useAlert(`/`ConfirmDialog`/`requestConfirm(` NO colisionan (preceden con carácter de palabra o mayúscula), solo el identificador de familia en minúsculas al inicio de token.

**Test / gate:** no hay test unitario por archivo (son integraciones de UI, no lógica pura). El gate es el **grep 0-hits** + `tsc`:

```bash
# Comando CANONICO de conteo (PCRE; excluye tests; cubre .ts y .tsx). Debe imprimir 0.
# Juzgar el NUMERO en stdout, no el exit code (C2).
grep -PRc --include='*.ts' --include='*.tsx' --exclude-dir='__tests__' \
  '(?<![.\w])(?:window\.)?(?:confirm|alert|prompt)\s*\(' src \
  | grep -v '\.test\.' | awk -F: '{s+=$NF} END{print s+0}'
```

Equivalente con ripgrep (si está en PATH): `rg -P -c` con globs `'src/**/*.{ts,tsx}'`, `'!**/__tests__/**'`, `'!**/*.test.*'` y el mismo patrón, sumado con el mismo `awk`. **C2 (tooling real, verificado 2026-07-18):** `rg` NO está garantizado en el PATH del entorno y `tsx` NO está en `devDependencies` — **queda ELIMINADO el helper `scripts/count_native_dialogs.ts` del v1** (un `npx tsx` intentaría bajar el paquete de la red). Si tampoco hubiera `grep -P`, usar `grep -rEn` sin el lookbehind y descartar a mano las invocaciones de método precedidas por punto (hoy: ninguna en `src`).

**Pre-check de la dimensión del ratchet (C5):** antes de migrar, `grep -c "nativeDialogByFile" src/__tests__/uiDebtRatchet.test.ts`:
- Si da `0` (el 156-F6 aún no se implementó): crear la dimensión ACÁ con EXACTAMENTE la spec del 156-F6 (mismo regex, `Record<string, number>`, `check` robusto a clave ausente) y declarar en el resumen que 156-F6 queda satisfecho por adelantado.
- En AMBOS casos, la exclusión del scan de la dimensión DEBE ser `**/__tests__/**` **y** `*.test.*`: la letra del 156-F6 excluía solo `__tests__/`, pero hoy `src/incidents/incidentModel.test.ts:172` (plan 166) contiene un fixture de test que matchea el regex y haría INALCANZABLE el 0 por archivo. Es un ajuste de coherencia del contrato 156-F6 — documentarlo en el comentario del test citando este plan.

**Coordinación con el plan del latido único:** ese plan crea la dimensión `nativeDialogByFile` en el `uiDebtRatchet` (only-decrease) para proteger a los demás planes mientras este espera. F2 la lleva a **0 por archivo**: tras migrar, regenerar el baseline (`UI_DEBT_REGEN=1 npx vitest run src/__tests__/uiDebtRatchet.test.ts`) para clavar el 0, y **mover la dimensión a la lista `forcedZero` del test (A1)** — el mecanismo YA existe (`uiDebtRatchet.test.ts:80-82`: `const forcedZero = ...` / `const allowed = forcedZero ? 0 : allowedBase`). Con `forcedZero` el 0 es ABSOLUTO: ni un `UI_DEBT_REGEN=1` futuro puede resubirlo (el baseline deja de ser el techo). El 156-F6 la creó "sin forcedZero" porque la deuda era heredada y distribuida; al llegar a 0, clavarla es la continuación natural de ese contrato. A partir de ahí, cualquier reintroducción de un diálogo nativo rompe ese test.

**Criterio de aceptación BINARIO:** el conteo del comando de arriba → `0`; `npx tsc --noEmit` → exit 0; `npx vitest run src/__tests__/uiDebtRatchet.test.ts` → exit 0 con `nativeDialogByFile` en 0 por archivo Y movida a `forcedZero` (A1); tabla de conservación **32/32 MIGRADA** en el resumen (C4/KPI-8).

**Flag:** ninguna. **Runtimes:** UI pura del panel Stacky, agnóstica del runtime de agentes; las confirmaciones migradas son presentación, no tocan el camino de ejecución. **Trabajo del operador: ninguno (mejora invisible; las confirmaciones siguen exactamente donde estaban).**

---

### F3 — Migrar los 15 modales a la primitiva, por lotes, con ratchet de modales ad-hoc

**Objetivo (1 frase):** migrar cada uno de los 15 archivos `*Modal*.tsx` (+ el `DetailModal` inline) a la primitiva `Dialog` en lotes verificables, y congelar un ratchet only-decrease que impida que queden (o vuelvan a aparecer) modales ad-hoc fuera de la primitiva. **Valor:** todos los modales de Stacky ganan Escape, focus-trap, restore-focus y tema consistente de una vez, y la deuda queda estructuralmente acotada a la baja.

**Archivos (por lote):**
- **Lote 1 (ya hecho en F1 — el trío del stress-test):** `FileManagerModal.tsx`, `IntentPreflightModal.tsx`, `AgentLaunchModal.tsx`. Este lote **valida el contrato**; F3 arranca congelando el ratchet con estos 3 ya migrados.
- **Lote 2 (los que ya tienen `role="dialog"` — migración mecánica):** `AgentConfigModal`, `AgentHistoryModal`, `ClaudeCliConfigModal`, `DailyStandupModal`, `DataReadinessModal`, `EpicFromBriefModal`, `FileSelectorModal`, `IncidentResolverModal`, `QaBrowserRunModal`.
- **Lote 3 (los que NO tienen `role="dialog"` — ganan semántica al migrar):** `EditProjectModal`, `NewProjectModal`, `devops/CommitPipelineModal`, + el `DetailModal` inline de `pages/SystemLogsPage.tsx`.
- NUEVO `frontend/src/__tests__/adhocModalRatchet.test.ts` + `frontend/src/__tests__/adhocModalAllowlist.json` (allowlist congelada, only-decrease).

**Cómo migrar un modal (patrón mecánico):** reemplazar el andamiaje `<div overlay onClick><div panel role="dialog"?>...</div></div>` por `<Dialog open onClose={onClose} closeGuard={{dirty, busy}} title={...} size={...}>...contenido idéntico...</Dialog>`. El `closeGuard`:
- Si el modal ya usa `shouldCloseOnBackdrop({dirty,busy})`, pasar EXACTAMENTE ese `{dirty,busy}` como `closeGuard`.
- Si no lo usa (modales del lote 3), derivar `dirty`/`busy` de su estado (campos de formulario tocados / operación en curso) o pasar `{dirty:false,busy:false}` si no hay nada que proteger. **No cambiar la lógica de negocio.**

**Ratchet de modales ad-hoc (`adhocModalRatchet.test.ts`):**
- **Detector CONGELADO EN EL PLAN (C7 — nada se difiere al test):** un archivo cuenta como "modal ad-hoc" si y solo si:
  - (a) está bajo `src/**/*.tsx`, NO bajo `src/components/ui/`, NO bajo `**/__tests__/**` y NO matchea `*.test.*`; y
  - (b) su contenido matchea al menos uno de: `role="dialog"` | `aria-modal` | `createPortal(`; y
  - (c) NO matchea el regex de import de la primitiva: `/import\s+\{[^}]*\bDialog\b[^}]*\}\s+from\s+["'][^"']*ui["']/` (import nombrado `Dialog` desde el barrel `ui`).
  El test implementa EXACTAMENTE esto (fs + regex, sin AST). Falsos positivos conocidos y ACEPTADOS vía allowlist: drawers/paleta/popovers con `aria-modal` o `createPortal` propios quedan como **entradas permanentes documentadas** (no se migran — §8).
- `adhocModalAllowlist.json`: array de objetos `{ "file": "<ruta relativa src/...>", "reason": "<por qué sigue ad-hoc o es excepción permanente>" }`. El test afirma: (a) todo archivo detectado está en la allowlist; (b) ningún archivo de la allowlist dejó de ser detectado (obliga a sacarlo al migrar); (c) **only-decrease:** la allowlist nunca crece (comparación contra el JSON congelado en el repo).
- Al terminar F3 (los 3 lotes), la allowlist queda **vacía** (o con las excepciones justificadas por escrito — p. ej. si un "modal" resultó ser un drawer y se decide dejarlo fuera de scope, se documenta en §8 y se deja en la allowlist con un comentario).

**Test / gate por lote:**

| Momento | Gate |
|---|---|
| Tras lote 1 | `adhocModalRatchet.test.ts` verde con allowlist = {todos menos el trío}; `tsc` verde; smoke manual del trío. |
| Tras lote 2 | allowlist recortada en 9; `tsc` verde; smoke manual de 2-3 del lote. |
| Tras lote 3 | allowlist vacía (o excepciones documentadas); `tsc` verde; smoke manual de EditProject/NewProject/DetailModal. |

**Casos borde a vigilar:** (a) un modal con foco inicial específico (p. ej. un input de búsqueda) → usar `initialFocusRef`; (b) un modal que hace su propio `stopPropagation` en el panel → el `Dialog` ya lo maneja, quitar el duplicado; (c) un modal anidado (uno abre otro) → el `DialogHost` procesa uno por vez; si hay anidación real, el `Dialog` directo (no el host) permite superponer — validar en smoke.

**Criterio de aceptación BINARIO:** `npx vitest run src/__tests__/adhocModalRatchet.test.ts` → exit 0; la allowlist tiene **estrictamente menos** entradas que en el estado inicial (idealmente 0); `npx tsc --noEmit` → exit 0; `grep -rlE 'role="dialog"' src/components src/pages --include=*.tsx | xargs grep -L "ui" ` no lista modales migrados (todos importan la primitiva).

**Flag:** ninguna. **Runtimes:** UI pura del panel Stacky, agnóstica del runtime de agentes. **Trabajo del operador: ninguno (mejora invisible; los modales se ven y se comportan mejor).**

---

### F4 (RECORTABLE) — Un solo punto de lanzamiento de agente: `LaunchAgentDialog` compartido

**Objetivo (1 frase):** unificar el `RunModal` ad-hoc del tablero (`pages/TicketBoard.tsx:94-231`) con el `AgentLaunchModal` canónico en un único `LaunchAgentDialog` (sobre la primitiva `Dialog`) que reciba el contexto opcional de ticket, de modo que el flujo de lanzar agente exista una sola vez. **Valor:** los arreglos al lanzamiento (Escape, focus-trap, runtime selector, tema) se hacen una vez, no dos.

**Por qué es recortable:** si el tiempo aprieta, con F1-F3 el `RunModal` del tablero YA está sobre la primitiva `Dialog` (F3 lote correspondiente) y `AgentLaunchModal` también (F1). La duplicación de LÓGICA sigue, pero ambos ya son accesibles y con tema. F4 elimina la duplicación de código; no es requisito para que Stacky "se sienta producto".

**Archivos:**
- NUEVO `frontend/src/components/LaunchAgentDialog.tsx` (diálogo compartido sobre `Dialog`, con props de contexto)
- MODIFICADO `frontend/src/pages/TicketBoard.tsx` (borrar `RunModal`; usar `LaunchAgentDialog` con contexto de ticket)
- MODIFICADO `frontend/src/components/EmployeeCard.tsx` (usar `LaunchAgentDialog` en vez de `AgentLaunchModal`)
- (posible) ELIMINADO/ADELGAZADO `frontend/src/components/AgentLaunchModal.tsx` (su cuerpo se absorbe en `LaunchAgentDialog`; si otros lo referencian, dejar un re-export delgado)
- MODIFICADO `frontend/src/services/agentLaunch.ts` (helper de lanzamiento compartido, si hace falta)

**Diseño del contrato del diálogo compartido:**
```ts
interface LaunchAgentDialogProps {
  open: boolean;
  onClose: () => void;
  /** Contexto opcional: si viene, el diálogo arranca scopeado a ese ticket
   *  (modo del tablero); si no, arranca en modo "elegí ticket" (modo tarjeta). */
  ticketContext?: { ticket: Ticket; mode: "suggested" | "custom";
                    suggestedLabel: string | null; suggestedFilename: string | null };
  agent?: AgentSummary;          // modo tarjeta de empleado
  avatarValue?: string;
  onConfirm: (note: string, filename: string | null) => void;
}
```
Reusa `AgentRuntimeSelector`, `runtimeRequiresVsCodeAgent`, `runtimeDisplayLabel`, `launchInProgressLabel` (ya usados por ambos). Todo sobre `Dialog` (Escape/focus-trap/restore-focus/tema gratis). **Sin inline-style** (archivo `.tsx` nuevo → alcance CERO del uiDebtRatchet: estilos por clase de módulo).

**Test / gate:** no hay lógica pura nueva significativa (el diálogo es composición). El gate es el grep + `tsc` + smoke:
- `grep -c "function RunModal" src/pages/TicketBoard.tsx` → `0`.
- `grep -c "createPortal" src/pages/TicketBoard.tsx` → `0` (el portal ahora vive en `Dialog`).
- Smoke manual: lanzar un run desde el tablero (modo sugerido y personalizado) y desde la tarjeta de empleado → mismo diálogo, mismo comportamiento que antes.

**Criterio de aceptación BINARIO:** `grep -c "function RunModal" src/pages/TicketBoard.tsx` → `0`; `npx tsc --noEmit` → exit 0; `npx vitest run src/__tests__/adhocModalRatchet.test.ts` → exit 0 (el RunModal ya no cuenta como ad-hoc).

**Flag:** ninguna. **Runtimes:** el diálogo de lanzamiento es UI; el runtime real (Codex/Claude/Copilot) lo elige `AgentRuntimeSelector` como hoy — paridad idéntica, sin cambios de comportamiento por runtime. **Trabajo del operador: ninguno (mejora invisible; el flujo de lanzar es el mismo).**

---

## 6. Orden de implementación (numerado)

1. **F0** — recontar el inventario en frío (superficies modales + llamadas nativas) y fijar el contrato de la primitiva. Solo lectura.
2. **F1** — crear `dialogKeyboard.ts` (puro) + `Dialog.tsx` + `Dialog.module.css` + `ConfirmDialog`/`AlertDialog` + `dialogHostReducer.ts` (puro) + `DialogHost.tsx`; exportar en `ui/index.ts`; montar `<DialogHost>` en `main.tsx`; **stress-test** migrando FileManagerModal/IntentPreflightModal/AgentLaunchModal; tests puros verdes. Ajustar el contrato si el stress-test lo exige.
3. **F2** — pre-check de la dimensión del ratchet (C5); migrar las ~32 llamadas nativas por la Regla de destino (confirmaciones → `useConfirm`; errores → `Toast`; info → `useAlert`; entradas → `useTextPrompt`); tabla de conservación 32/32 (C4); dejar el contador en 0, regenerar el baseline del `uiDebtRatchet` y mover la dimensión a `forcedZero` (A1).
4. **F3** — migrar los 15 modales por lotes (lote 1 = trío de F1); crear y congelar el `adhocModalRatchet`; bajarlo en cada lote hasta vaciarlo.
5. **F4 (recortable)** — unificar `RunModal` + `AgentLaunchModal` en `LaunchAgentDialog`; grep del RunModal ad-hoc = 0.

Correr `npx tsc --noEmit` al terminar cada fase. Cada test SIEMPRE por archivo. Pre-flight `git status` por archivo caliente antes de tocarlo.

---

## 7. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | El contrato de la primitiva no cubre algún modal (p. ej. resulta ser un drawer con foco custom). | Por eso el **stress-test de F1 es PREVIO** a comprometer los 15: se prueba contra los 3 de mayor riesgo/tráfico; si algo no encaja, se ajusta el contrato ACÁ. Los que resulten drawers/popovers salen a §8 (fuera de scope) y quedan documentados en la allowlist del ratchet. |
| R2 | No se puede testear focus-trap/restore-focus sin `jsdom`. | La **lógica** (decisión de teclado, próximo foco, guarda de cierre, reducer) vive en módulos puros y se testea 100%; el comportamiento de DOM real se valida por **smoke manual** (declarado en el DoD). Es el gate honesto de este repo. |
| R3 | Migrar un error a `Toast` requiere wiring (state + render) que no todos los archivos tienen. | La Regla de destino de F2 da el patrón exacto (sembrar `ToastState` local + render `<Toast>`); para hooks `.ts` (`useAgentRun.ts`) se propaga el error al consumidor o se usa `useAlert()`. No se crea un Toast nuevo (prohibido por el barrel). |
| R4 | El grep de F2 caza un comentario/prosa con la llamada literal y nunca llega a 0. | **Gotcha crítico codificado en §3.9 y §9:** ni la prosa del doc ni los comentarios del código contienen la cadena literal; se nombra perifrásticamente. El gate gana. |
| R5 | Un `.tsx` nuevo (Dialog, ConfirmDialog, LaunchAgentDialog) introduce inline-style y rompe el uiDebtRatchet. | Archivos `.tsx` nuevos nacen con alcance CERO a `style={{`; estilos por clase de `*.module.css` con tokens de `theme.css`; estilos dinámicos por `ref`+efecto imperativo. Gotcha conocido. |
| R6 | La migración de un modal cambia sutilmente su comportamiento (cierra cuando no debía, pierde foco inicial). | El `closeGuard` reusa el MISMO `{dirty,busy}` que el modal ya calculaba; `initialFocusRef` preserva el foco inicial; el contenido interno NO se toca. Smoke por lote. |
| R7 | El plan se implementa en varias sesiones y un modal migrado "regresa" a ad-hoc. | El `adhocModalRatchet` only-decrease lo impide: la allowlist congelada solo baja; un ad-hoc nuevo fuera de la lista rompe el test. |
| R8 | El `DialogHost` global rompe modales anidados (uno abre otro). | El host procesa una petición promise-based por vez (FIFO); para modales que se superponen de verdad, se usa el `Dialog` directo (no el host), que permite anidar. Validado en smoke de F3 (caso borde c). |
| R9 | Sesión concurrente en el mismo árbol pisa un archivo caliente. | `git status -- "<ruta>"` antes de cada archivo; staging quirúrgico por path; el implementador NO commitea. |
| R10 | Una promesa del host queda sin resolver (dismiss no mapeado) y un `await` cuelga la acción. | **Diseño C1:** toda vía de cierre resuelve (`onClose` del host ES `settle(dismissValueFor(kind))`; helper puro testeado); el reducer ignora resoluciones duplicadas (idempotente). No existe camino de cierre que no resuelva. |
| R11 | El consumidor se desmonta (refetch de react-query, navegación) mientras su petición espera → confirmación huérfana / closure con datos viejos. | La promesa SIEMPRE se resuelve al actuar el operador (C1: nunca cuelga). El continuation opera con IDs capturados antes del `await` (no objetos vivos); los borrados por id son idempotentes en el backend. Cola corta (mono-operador). Documentado en F1 Paso 3. |

---

## 8. Fuera de scope (explícito)

- **Drawers y popovers que NO son modales.** `TeamManageDrawer`, `ChatDrawer`, `CodexConsoleDock`, `ProvenanceDrawer`, `ExecutionDetailDrawer`, la paleta de comandos, etc. tienen foco/teclado propios y NO son diálogos modales; **no se migran** salvo que el stress-test de F1 demuestre que uno debería serlo. Si un "modal" resulta ser drawer, queda documentado aquí y en la allowlist.
- **Rediseño visual de los modales más allá de meterlos en la primitiva.** No se rediseñan formularios, ni se reordenan campos, ni se cambian textos. Solo cambia el andamiaje (overlay/panel/teclado/foco/tema).
- **Cualquier cambio de lógica de negocio de los flujos migrados.** Las mismas confirmaciones, los mismos endpoints, las mismas acciones. Si borraba, sigue borrando; si pedía tipear el id, sigue pidiéndolo.
- **`ConfirmButton` inline no se toca.** El patrón "confirmar en el propio botón" (plan de protección de trabajo) sigue siendo válido para confirmaciones que ya son botones inline; `useConfirm()` es solo para las que hoy son diálogos nativos bloqueantes. No se convierten `ConfirmButton` existentes en `useConfirm`.
- **Crear un Toast nuevo.** Prohibido por el barrel `ui/index.ts`; se reusa el `components/Toast.tsx` existente.
- **Tests de render (`render()`/RTL).** Imposibles en este repo (sin `@testing-library/react` ni `jsdom`); todo test es de lógica pura; el DOM real es smoke manual.
- **Flags / config nueva.** UI pura sin flag (precedente: estados/tema/motion).
- **`beforeunload` / confirmación de cierre de pestaña (C10):** HOY hay **0** usos en `src` (verificado 2026-07-18). Es otra familia (evento del navegador, no diálogo modal): NO entra en el gate ni en la migración. Si un plan futuro lo agrega, no rompe nada de este plan.

---

## 9. Advertencias para el implementador (leer antes de tocar nada)

- **RTL/jsdom NO están en `frontend/package.json`** (gap estructural conocido). Prohibido `render()`/`renderHook`. Tests = funciones/reducers puros + `tsc --noEmit`. El gate de UI real es tsc + los tests puros + **smoke MANUAL del operador** (declarado en el DoD).
- **vitest SIEMPRE por archivo** (`npx vitest run src/<archivo>`): la corrida completa contamina cross-file (conocido y documentado en este repo).
- **Correr desde el checkout real** `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend` (el `node_modules` del worktree puede estar roto — junction conocida).
- **GOTCHA comentario-choca-con-gate (CRÍTICO en este plan, múltiples recurrencias históricas):** los gates de F2/F3 grepan la llamada literal de diálogo nativo (identificador de familia — confirmación/aviso/entrada — seguido de paréntesis) en `src`. **Ni la prosa de este doc, ni los comentarios del código, ni los mensajes de test** pueden contener esa cadena literal. Nombrarla SIEMPRE perifrásticamente ("el diálogo de confirmación nativo del navegador"). El gate gana; jamás se relaja.
- **GOTCHA colisión de NOMBRES con el gate (no obvio):** NO nombrar con un identificador de familia nativo (en minúsculas) a la variable que recibe `useConfirm()`/`useAlert()`. Si se hace, invocar esa variable (`await <variable>({...})`) es indistinguible para el regex del gate de una llamada nativa y el contador nunca llega a 0. Usar `ask`/`notify`/`confirmDelete`/`showError`. (`useConfirm(`/`ConfirmDialog`/`requestConfirm(` son seguros: preceden con carácter de palabra o mayúscula.)
- **Archivos `.tsx` nuevos y el uiDebtRatchet:** el ratchet le da alcance CERO a `style={{` en `.tsx` nuevos; para estilos dinámicos usar `ref`+`useEffect` imperativo, JAMÁS `style={{}}`. Usar clases de `*.module.css` con tokens de `theme.css`.
- **El scan de diálogos nativos DEBE incluir `.ts`, no solo `.tsx`:** hay al menos una llamada en un hook `.ts` (`hooks/useAgentRun.ts`). Un scan solo-`.tsx` la dejaría viva y el contador nunca llegaría a 0.
- **El scan DEBE excluir `*.test.*` además de `__tests__/` (C5):** `src/incidents/incidentModel.test.ts:172` tiene un fixture de test que matchea el regex; con la exclusión solo-`__tests__/` (letra del 156-F6), el 0 por archivo es inalcanzable.
- **`tsx` NO está instalado (C2):** no figura en `devDependencies`; PROHIBIDO `npx tsx` (bajaría el paquete de la red). El conteo es grep/rg con PCRE; los tests, `npx vitest run` por archivo.
- **Exit codes de grep (C2):** `grep -c` sale con exit 1 cuando imprime `0`; los gates "→ 0" se juzgan por stdout (`|| true` si el shell corre con `set -e`).
- **Settlement (C1):** toda vía de cierre de un diálogo del host RESUELVE su promesa (`dismissValueFor`); JAMÁS dejar un `await` colgado. En el panel, `e.stopPropagation()` tras manejar una tecla (los portales burbujean por el árbol de React — C6a).
- **StrictMode:** los efectos corren doble en dev; el contador de scroll-lock y el settle idempotente lo absorben — no escribir efectos de foco "de una sola vez".
- **`Toast` es component-local** (sin provider global): migrar un error a Toast = sembrar `ToastState` local + render `<Toast>`; desde un hook `.ts`, propagar el error o usar `useAlert()`.
- **Algún "modal" puede ser en realidad drawer/popover con foco custom:** por eso el stress-test de F1 es previo. Si uno no encaja, documentarlo (§8) y dejarlo en la allowlist del ratchet, no forzarlo.
- **`shouldCloseOnBackdrop` ya lo usan 6 modales + FinishWorkButton:** el `closeGuard` de la primitiva DEBE integrar ese contrato tal cual; al migrar, pasar el MISMO `{dirty,busy}` que el modal ya calculaba.
- **Sesión concurrente en el mismo árbol:** `git status -- "<ruta>"` antes de cada archivo caliente; staging quirúrgico por path; el implementador NO commitea (lo hace el orquestador).

---

## 10. Definition of Done (global)

- [ ] KPI-1..KPI-8 en verde con los comandos exactos de §1, cada test corrido por archivo, con su salida pegada en el resumen (gates "→ 0" juzgados por stdout — C2).
- [ ] Existe `components/ui/Dialog.tsx` con portal + `role="dialog"` + `aria-modal` + Escape + focus-trap (sin librerías) + restore-focus + `closeGuard` que integra `shouldCloseOnBackdrop`; exportada en `ui/index.ts`.
- [ ] Existen `useConfirm()`, `useAlert()` y `useTextPrompt()` (A2) promise-based vía `DialogHost`, montado una sola vez alrededor de `<App/>` en `main.tsx`; reducer del host testeado puro, INCLUIDOS dismiss (`dismissValueFor`), idempotencia del settle (C1) y `textPromptCanConfirm` (A2).
- [ ] Stress-test de F1 hecho: FileManagerModal, IntentPreflightModal y AgentLaunchModal migrados y verificados; cualquier ajuste de contrato documentado.
- [ ] Diálogos nativos del navegador en `src` = **0** (comando de conteo de F2), incluyendo `.ts`, con exclusión `*.test.*` alineada (C5); el `uiDebtRatchet.nativeDialogByFile` en 0 por archivo tras regenerar el baseline **y movido a `forcedZero` (A1)**. Tabla de conservación **32/32 MIGRADA** (C4/KPI-8): ninguna confirmación destructiva desapareció ni se volvió automática.
- [ ] Los 15 modales `*Modal*.tsx` (+ `DetailModal` inline) migrados a la primitiva; `adhocModalRatchet` verde con allowlist vacía (o excepciones documentadas en §8); la allowlist solo bajó.
- [ ] (F4, si no se recortó) `RunModal` ad-hoc eliminado (`grep -c "function RunModal" TicketBoard.tsx` → 0); un único `LaunchAgentDialog` compartido para tablero y tarjeta de empleado.
- [ ] `npx tsc --noEmit` verde.
- [ ] **Smoke MANUAL del operador (criterio de DoD, por el gap RTL/jsdom):** en al menos FileManagerModal, IntentPreflightModal, AgentLaunchModal, una confirmación destructiva migrada (p. ej. eliminar proyecto) y un modal del lote 3 — verificar: Escape cierra (si no dirty/busy), Tab no se escapa y cicla, el foco vuelve al disparador al cerrar, se ve correcto en tema claro Y oscuro, y ninguna confirmación destructiva desapareció (human-in-the-loop intacto). Además (C6/A2): el scroll del fondo queda bloqueado con un diálogo abierto; Escape en un diálogo anidado cierra SOLO el de arriba; las 2 entradas migradas (`useTextPrompt`) preservan su comportamiento, incluido el type-to-confirm del rollback.
- [ ] Pre-flight `git status` por archivo caliente hecho; sin WIP ajeno arrastrado; el implementador NO commiteó.
- [ ] "Trabajo del operador: ninguno" se cumple: sin config nueva, sin flags, backward-compatible en semántica; solo mejora de presentación y comportamiento.
