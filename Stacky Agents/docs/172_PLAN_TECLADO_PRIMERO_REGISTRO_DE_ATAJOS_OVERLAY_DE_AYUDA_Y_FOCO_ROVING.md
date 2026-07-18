# Plan 172 — Teclado primero: registro central de atajos, overlay de ayuda "?" y foco roving

Serie UX Cockpit del Operador (172-175) — plan 1/4 — **v2 CRITICADO** — 2026-07-18

> **Estado:** CRITICADO v1 → v2 (2026-07-18) · **Autor:** StackyArchitectaUltraEficientCode · **Juez:** StackyArchitectaUltraEficientCode (adversarial)
>
> ### Changelog v1 → v2 (veredicto: APROBADO-CON-CAMBIOS)
> - **C1 (IMPORTANTE):** F4 regla 1 usaba comillas SIMPLES alrededor de `'[data-roving-item="${next}"]'` → `${next}` NO se interpola en JS: el roving jamás movería el foco (tsc verde, tests puros verdes, solo lo cazaría el smoke). Corregido a backticks. Regla de literalidad para modelos menores restaurada.
> - **C2 (IMPORTANTE) [ADICIÓN ARQUITECTO]:** los 3 defs CORE vivían inline en `App.tsx` (F2) mientras el test de colisiones de F1 usaba una copia a mano ("CORE de F2 como specs estáticos") → `detectCollisions` NUNCA corría sobre el set real y un atajo colisionante futuro escapaba al CI (irónico en un plan cuya tesis es "una sola fuente de verdad": introducía una 2.ª copia oculta). Se exporta `CORE_SHORTCUT_DEFS` (sin handler) desde `shortcuts.ts`, consumida por App.tsx (adjunta handlers por id) Y por el test; + guardia de colisiones dev-only en runtime.
> - **C3 (IMPORTANTE):** el overlay `?` (F3, rama sin 164) roba el foco al montar pero NUNCA lo restaura al cerrar → un operador que estaba roving el historial, abre `?` y cierra con Escape, PIERDE su fila activa. Se agrega captura/restauración de `document.activeElement`.
> - **C4 (MENOR):** overlay con `role="dialog" aria-modal` pero sin `aria-labelledby` al `<h2>`. Se asocia por id (ambas ramas).
> - **C5 (MENOR):** drift de números de línea en la evidencia citada (keydown real en `App.tsx:210-235` no `:173-200`; fetch health `:148`; selector `[tabindex]:focus-visible` en `theme.css:362-365` no `:334-337`; `shell_v2_enabled` en `diag.py:415`). Los HECHOS se verificaron TODOS verdaderos en frío; se corrigen las refs más citadas. Ediciones siguen ancladas por TEXTO.
> - **C6 (MENOR):** `Ctrl+/` (nav.toggle-board, `allowInDialog:true`) dispara bajo un `Dialog` 164 abierto, cambiando el tab detrás del modal. Es paridad con HEAD (hoy no hay guard de diálogo), NO regresión; se deja nota para reconsiderar cuando 164 aterrice.
> - **C7 (MENOR):** plan tipo-fix (mata la clase "overlay que miente" + el bug matcher `?`/Shift); se registra huella en `error_fingerprints.json` (DoD).
>
> **Estado v1 original:** PROPUESTO v1 (2026-07-18) · **Autor:** StackyArchitectaUltraEficientCode
> **Serie:** hermanos 173 (vistas guardadas), 174 (rendimiento percibido), 175 (peek y acciones rápidas). Cada tema pertenece a UN solo plan: este plan NO define vistas guardadas (173), NI virtualización/prefetch (174), NI menú contextual/hover-cards (175). 175 CONSUME los atajos que este plan registra.
> **Runtimes:** feature 100% del dashboard (frontend + un campo aditivo en un endpoint de health del backend). **Agnóstica del runtime de agentes** (Codex CLI, Claude Code CLI, GitHub Copilot Pro): ninguna fase toca el camino de ejecución, publicación ni prompts. Paridad de los 3 runtimes automática por vacuidad — se declara igual fase por fase.
> **Flag:** `STACKY_UI_SHORTCUTS_ENABLED`, **default ON**, configurable desde la UI de Settings (panel de flags del arnés, plan 82/86). OFF = comportamiento de HOY, byte-compatible (los 3 atajos preexistentes siguen; lo nuevo se apaga).
> **Human-in-the-loop:** este plan NO ejecuta ninguna acción con efecto por teclado. `Enter` en una fila solo ABRE el detalle (lectura). Ninguna acción destructiva/publicación gana un atajo. Las acciones rápidas con efecto son del plan 175 y pasan por el diálogo canónico del plan 164.
> **Excepciones duras (evaluadas una por una):** ninguna aplica. (1) No hay bypass de revisión humana: no se automatiza ninguna decisión. (2) No hay acción destructiva/irreversible: los handlers de este plan solo abren/cierran/mueven foco. (3) No hay prerequisito no garantizado: todo el sustrato citado existe y fue verificado en frío. (4) No reduce seguridad: no toca auth (no existe), ni egress, ni datos.

---

## 1. Objetivo + KPI / impacto esperado

**Objetivo (1 párrafo):** hoy Stacky tiene TRES fuentes de verdad divergentes sobre sus atajos de teclado: (a) el handler ad-hoc de `App.tsx:210-235 (v2: era :173-200; drift confirmado en frío — anclar por el texto `const onKeyDown` + `isPaletteShortcut`)` que implementa los 3 atajos REALES (Ctrl+K paleta, `?` cheatsheet, Ctrl+/ alternar nav); (b) la lista hardcodeada `DEFAULT_SHORTCUTS` (`frontend/src/hooks/useKeyboardShortcuts.ts:48-57`) que la cheatsheet muestra al operador y que **miente**: 5 de sus 8 entradas (Ctrl+R, Ctrl+Shift+R, Enter, Shift+Enter, Esc global) no están implementadas en ningún lado; y (c) el hook `useKeyboardShortcuts` (`useKeyboardShortcuts.ts:26-46`) con **cero consumidores** (verificado por grep: solo la cheatsheet importa la constante, nadie usa el hook) y un bug latente en su matcher (`matches()` en `:10-24` chequea `wantShift` ANTES del caso especial `?`, así que `?` —que ES Shift+/ en casi todos los layouts— jamás matchearía). Este plan funde las tres en UNA: un **registro central tipado** de atajos en un módulo puro (`services/shortcuts.ts`), un **hook de suscripción** para componentes, el **overlay de ayuda `?` AUTOGENERADO del registro** (imposible que vuelva a mentir), **foco roving** (j/k/flechas + Enter + Escape) en el historial de ejecuciones y en la bandeja de revisión, y **hints de atajos** en tooltips y en la paleta del plan 129. El binding Ctrl+K existente migra AL registro sin cambiar un byte de comportamiento.

**KPIs binarios (comandos exactos). Frontend desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend` (POSIX: `cd "Stacky Agents/frontend"`); backend desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend`. vitest y pytest SIEMPRE por archivo (contaminación cross-file conocida en ambos):**

- **KPI-1 — Lógica pura del registro verde:** `npx vitest run src/services/shortcuts.test.ts` → exit 0 (matching de combos incl. `?`=Shift+/, supresión en editables, prioridad de scope, gate de flag, colisiones=0, datos del overlay).
- **KPI-2 — Lógica pura del roving verde:** `npx vitest run src/services/rovingFocus.test.ts` → exit 0 (mapa tecla→acción, aritmética de índice con clamp, modificadores ignorados).
- **KPI-3 — Cero keydown ad-hoc en App.tsx:** `grep -c 'addEventListener("keydown"' src/App.tsx` → `0` (el listener vive en el hook `useGlobalShortcutListener`, único punto de entrada).
- **KPI-4 — La fuente que mentía murió:** `grep -rn "DEFAULT_SHORTCUTS\|useKeyboardShortcuts" src --include=*.ts --include=*.tsx` → **0 hits** (archivo borrado, lógica absorbida); y `grep -rn "Re-ejecutar último agente" src` → **0 hits** (la entrada fantasma desapareció).
- **KPI-5 — Overlay autogenerado, no hardcodeado:** `grep -c "groupForOverlay" src/components/ShortcutsCheatsheet.tsx` → `≥1`.
- **KPI-6 — Tipos verdes:** `npx tsc --noEmit` → exit 0.
- **KPI-7 — Flag backend completa y testeada:** `venv/Scripts/python.exe -m pytest tests/test_plan172_shortcuts_flag.py -q` → verde; y `grep -c "test_plan172_shortcuts_flag" scripts/run_harness_tests.sh` → `1` (registrado en `HARNESS_TEST_FILES`).
- **KPI-8 — Cero requests nuevos:** la flag se lee del `fetch("/api/diag/health")` que `App.tsx:148` YA hace (campo aditivo). Verificable: `grep -c 'fetch("/api/diag/health")' src/App.tsx` → `1` (sigue habiendo UNO).
- **KPI-9 (C2) — Fuente única de los core, sin copia oculta:** `grep -c "CORE_SHORTCUT_DEFS" src/services/shortcuts.ts` → `≥1` (declarada) y `grep -c "CORE_SHORTCUT_DEFS" src/App.tsx` → `≥1` (importada, no re-declarada); y `grep -c 'combo: "Ctrl+K"' src/App.tsx` → `0` (los combos core NO se re-tipean inline). El test `test_collisions_zero_en_estaticos` corre sobre el array real.

**Nota de scripting (aplica a TODOS los KPIs y gates con `grep`):** el criterio se evalúa por la SALIDA impresa (el conteo o los hits), NUNCA por el exit code. Con 0 matches, `grep -c` imprime `0` pero retorna exit code 1; un script de DoD automatizado debe comparar el número impreso contra el esperado (`0`, `1`, `2`, `≥1`), no usar `grep && ...`.

**KPIs de impacto (proyectados, smoke manual §9):**

| Métrica | Hoy | Con el plan |
|---|---|---|
| Fuentes de verdad de atajos | 3 divergentes (App.tsx / DEFAULT_SHORTCUTS / hook muerto) | **1** (registro tipado) |
| Entradas del overlay `?` que mienten | 5 de 8 | **0** (autogenerado del registro) |
| Listas navegables por teclado (j/k + Enter) | 0 | **2** (historial, revisión) + 1 recortable (tablero tickets) |
| Requests HTTP nuevos por sesión | — | **0** |
| Trabajo nuevo del operador | — | **0** (invisible; default ON) |

---

## 2. Por qué ahora / gap que cierra (evidencia archivo:línea, verificada en frío 2026-07-18)

> Los números de línea son referencia del día; **toda edición se ancla por TEXTO/símbolo citado, no por número de línea** (hay sesiones paralelas conocidas en este repo).

### 2.1 Tres fuentes de verdad divergentes (el gap central)

1. **El handler real y ad-hoc:** `frontend/src/App.tsx:210-235 (v2: era :173-200; drift confirmado en frío — anclar por el texto `const onKeyDown` + `isPaletteShortcut`)` — un `useEffect` con `window.addEventListener("keydown", ...)` que implementa: Ctrl+K → `setPaletteOpen(v => !v)` (`:183-185`, funciona TAMBIÉN con foco en inputs), `?` → `setCheatsheetOpen(v => !v)` (`:186-188`, SOLO fuera de editables: guard `!editable && ev.key === "?" && !ev.ctrlKey && !ev.metaKey` en `:181`), y Ctrl+/ → `selectTab(toggleNavTab(tabRef.current))` (`:189-196`, con el espejo `tabRef` del plan 136 F7, `:74-75`, y la prohibición explícita de `pushState` dentro del updater por StrictMode).
2. **La lista que miente:** `frontend/src/hooks/useKeyboardShortcuts.ts:48-57` — `DEFAULT_SHORTCUTS` declara 8 atajos; solo `Ctrl+K`, `?` y `Ctrl+/` existen. `Ctrl+R "Re-ejecutar último agente"`, `Ctrl+Shift+R`, `Enter "Correr agente seleccionado"`, `Shift+Enter` y `Esc "Cerrar modal/drawer"` (global) **no tienen implementación en ninguna parte del árbol** (grep de consumidores del hook: 0). El overlay `ShortcutsCheatsheet.tsx:18-21` renderiza esa lista tal cual → **le miente al operador**.
3. **El hook muerto con bug:** `useKeyboardShortcuts()` (`useKeyboardShortcuts.ts:26-46`) no lo llama nadie. Su `matches()` (`:10-24`) además tiene el bug de orden: para el combo `"?"`, `wantShift=false` se compara contra `ev.shiftKey=true` en `:18` y devuelve `false` ANTES de llegar al caso especial de `:22`. El plan 164 §2.1 ya lo inventarió como uno de los 5 archivos que manejan Escape sin ser modal.

**Consecuencia:** el orquestador de la serie verificó "cero hits de useShortcut/useHotkey/registerShortcut" — correcto: no hay SISTEMA de atajos. Lo que hay es un embrión fragmentado en tres piezas que divergen. La cura no es crear una cuarta pieza: es fundir las tres en un registro único.

### 2.2 El overlay `?` existe pero está desconectado de la realidad

- `frontend/src/components/ShortcutsCheatsheet.tsx` (68 líneas) ya se monta en `App.tsx:414-417` y se abre con `?`. Tiene `role="dialog"` y backdrop-click para cerrar (`:24-31`), pero **ni Escape** (el plan 164 inventarió: 0 modales cierran con Escape) **ni contenido veraz** (§2.1.2). Este plan lo conserva como componente (mismo nombre, mismo punto de montaje) y le cambia la fuente: del registro, nunca más de una constante aparte.

### 2.3 Superficies elegidas para el foco roving (leídas, no supuestas)

| Superficie | Evidencia | Qué hace Enter hoy (mouse) | Roving propuesto |
|---|---|---|---|
| **Historial de ejecuciones** | `frontend/src/pages/ExecutionHistoryPage.tsx:183-227` — `<tbody>` con `items.map((item) => <tr onClick={() => setDetailId(item.id)} title="Click para ver detalle">` (`:187-188`); drawer de detalle `ExecutionDetailDrawer` en `:258-261` | click en la fila abre el drawer | j/k/↑↓ mueven foco entre filas, Enter = `setDetailId(items[i].id)`, Escape = `setDetailId(null)` |
| **Bandeja de revisión** | `frontend/src/pages/ReviewInboxPage.tsx:103-116` — `sortedRows.map((row) => <tr key={row.id}>` con botón "Ver detalle" → `setDetailExecutionId(row.id)` (`:111`) | botón "Ver detalle" | j/k/↑↓ + Enter = `setDetailExecutionId(sortedRows[i].id)`, Escape = `setDetailExecutionId(null)` |
| **Tablero de tickets (RECORTABLE)** | `frontend/src/pages/TicketBoard.tsx:249` `function TicketCard`, header expandible `styles.cardHeader` con `onClick={() => setExpanded(x => !x)}` (`:422`), renders en `:735` y `:1158` | click en el header expande/colapsa | j/k entre tarjetas, Enter = expandir/colapsar (F5, recortable: archivo caliente, lo toca el 164 F4) |

**Bonus verificado que abarata todo:** `frontend/src/theme.css:362-365 (selector `:where(…,[tabindex],…):focus-visible` con `box-shadow: var(--focus-ring)`; verificado en frío 2026-07-18)` ya aplica `box-shadow: var(--focus-ring)` a `:focus-visible` de **cualquier elemento con `[tabindex]`** (contrato del plan 138, re-apuntado por tema en 141 F2). Una `<tr tabIndex={0}>` gana el anillo de foco **gratis, en claro y oscuro, sin una línea de CSS nueva**.

### 2.4 Sustrato existente que se reusa (no se reinventa)

| Símbolo | Archivo:línea | Rol en 172 |
|---|---|---|
| Parser de combos `matches()` | `hooks/useKeyboardShortcuts.ts:10-24` | Se ABSORBE en `eventMatchesCombo()` de `services/shortcuts.ts` (con el bug de `?`/Shift corregido y testeado); el archivo original se borra en F3. |
| Guard de editables | `App.tsx:176-178` y `useKeyboardShortcuts.ts:29-31` (idénticos: `INPUT`/`TEXTAREA`/`isContentEditable`) | Se extrae a `isEditableTarget()` puro. Paridad exacta: combos con Ctrl/Cmd NO se suprimen en editables (así funciona Ctrl+K hoy), teclas sueltas SÍ. |
| `tabRef` espejo del tab | `App.tsx:74-75` (plan 136 F7) | El handler migrado de Ctrl+/ lo sigue usando tal cual, con su comentario normativo. |
| Paleta Ctrl+K | `components/CommandPalette.tsx` (`:83-132` `allCommands`, `:221` render de `hint`, `:226-230` footer) y `components/commandPaletteData.ts:59-73` `NAV_COMMANDS` | F6 agrega el comando "Ver atajos de teclado" y usa el campo `hint` ya existente. La navegación interna de la paleta (↑↓/Enter/Esc en `:179-193`) NO se toca: es scope local de un input, no colisiona con el registro. |
| Mecanismo de flags frontend | plan 139 §"Mecanismo EXACTO de lectura de la flag por el frontend" (`docs/139_...md:133-152`): campo ADITIVO en `GET /api/diag/health` (`backend/api/diag.py:410-411` ya expone `local_llm_enabled` y `shell_v2_enabled` con `getattr(_config.config, ...)`), leído en el effect de montaje de `App.tsx:154-161` | F0 agrega `ui_shortcuts_enabled` al MISMO dict y lo lee del MISMO fetch. Cero requests nuevos. |
| Panel de flags en Settings | `frontend/src/components/HarnessFlagsPanel.tsx` (montado desde `SettingsPage.tsx`; planes 82/86) | La flag nueva aparece AUTOMÁTICAMENTE en Settings al estar en `FLAG_REGISTRY` + categorizada. Regla dura del pipeline cumplida sin código nuevo. |
| Template de test de flag | `backend/tests/test_plan139_shell_flag.py` (completo) | F0 lo calca cambiando OFF→ON y `shell_v2`→`ui_shortcuts`. |
| Anillo de foco | `frontend/src/theme.css:362-365 (selector `:where(…,[tabindex],…):focus-visible` con `box-shadow: var(--focus-ring)`; verificado en frío 2026-07-18)` | F4/F5: foco visible gratis en filas con `tabindex`. |

### 2.5 Relación con el launcher de ayuda del plan 151 (decisión con evidencia)

El plan 151 (CRITICADO v2, **aún no implementado**) define `HelpLauncher.tsx`: un BOTÓN "?" en la TopBar que abre el **tour de onboarding** (`docs/151_...md` F3, KPI-6, snippet en `:480-494`). Son dos afordances DISTINTAS y compatibles:

- **Tecla `?`** (este plan) → overlay de **atajos de teclado** (referencia rápida, autogenerada). Ya existe hoy (`App.tsx:181,186-188`); este plan solo la hace veraz.
- **Botón "?" en TopBar** (plan 151) → **tour guiado** (onboarding narrativo re-abrible).

**Decisión: diferenciarse, no fusionarse.** Un overlay de referencia y un tour narrativo tienen propósitos distintos; fusionarlos rompería el contrato C2/invariante de `seen` del 151. Integración mínima si 151 aterriza después: el tour del 151 ya enseña "Ctrl+K es tu atajo" (paso `palette`, `docs/151:323-324`) — nada que cambiar acá. Integración si 172 aterriza primero: ninguna (el overlay no toca TopBar). **Dependencia blanda declarada:** ninguno de los dos planes requiere al otro; cero conflicto de archivos (151 toca `TopBar.tsx`, 172 no la toca). Además el listener del tour del 151 (C7/R8) ignora editables y no hace `preventDefault`, así que no colisiona con el listener del registro.

### 2.6 Relación con el diálogo canónico del plan 164 (dependencia blanda)

164 (PROPUESTO, no implementado) creará la primitiva `Dialog` con focus-trap y Escape. Este plan NO la espera:

- **Si 164 NO está** (caso base): el overlay conserva su patrón actual de backdrop (`ShortcutsCheatsheet.tsx:24-31`) y F3 le agrega cierre por Escape con un `onKeyDown` local en el contenedor (mejora puntual, sin focus-trap — ese es territorio del 164).
- **Si 164 YA está** al momento de implementar: F3 envuelve el contenido en `<Dialog>` en vez del backdrop manual (misma media hora de trabajo, y el overlay gana focus-trap gratis).
- El registro suprime atajos nuevos cuando hay un `role="dialog"` abierto (§5 F1, `allowInDialog`), así que cuando 164 migre los 15 modales, los atajos de página no van a dispararse detrás de un modal. Los 3 atajos core preservan su comportamiento actual (hoy funcionan con modales abiertos — paridad exacta).
- **C6 (v2) — nota a reconsiderar cuando 164 aterrice:** `nav.toggle-board` (Ctrl+/) tiene `allowInDialog:true`, así que dispara aun con un `Dialog` de confirmación abierto, cambiando el tab DETRÁS del modal. Esto es **paridad exacta con HEAD** (hoy el listener no tiene guard de diálogo), NO una regresión, por eso se conserva. Pero al integrar 164 conviene evaluar si un cambio de contexto bajo un diálogo destructivo debería inhibirse (bajar `allowInDialog` a `false` SOLO para `nav.toggle-board`); decisión diferida al plan que implemente la migración de modales, no se toca en 172.

---

## 3. Principios y guardarrailes (restricciones codificadas)

1. **Una sola fuente de verdad.** Todo atajo global vive en el registro. El overlay se AUTOGENERA del registro: es estructuralmente imposible que vuelva a mentir. Prohibido crear listas paralelas de atajos en cualquier archivo.
2. **Paridad byte-compatible de lo existente.** Ctrl+K, `?` y Ctrl+/ se comportan EXACTAMENTE igual que hoy (mismos guards de editable, mismo toggle, mismo `tabRef`). La migración al registro es refactor, no rediseño.
3. **Cero trabajo del operador.** Flag default ON, invisible, sin pasos manuales, sin config nueva obligatoria. OFF restaura el comportamiento de hoy. Backward-compatible al 100%.
4. **Human-in-the-loop innegociable.** Ningún atajo de este plan dispara acciones con efecto (crear/borrar/publicar/lanzar). Enter = abrir detalle (lectura). Las acciones con efecto son del 175 vía diálogo canónico del 164.
5. **3 runtimes, paridad por vacuidad.** Feature de dashboard, agnóstica del runtime de agentes. Se declara fase por fase igual.
6. **Mono-operador sin auth.** Nada de RBAC ni per-usuario; las preferencias de teclado no existen (no hay nada que persistir en 172 — persistencia de vistas es del 173).
7. **Lógica pura, no `render()`.** `@testing-library/react` y `jsdom` NO están en `frontend/package.json` (gap estructural conocido). TODA la lógica testeable vive en módulos `.ts` puros (`services/shortcuts.ts`, `services/rovingFocus.ts`) testeados sin DOM, como `commandPaletteData.test.ts` y `services/uiGuards.test.ts`. El comportamiento DOM real se valida con `tsc --noEmit` + smoke manual (§9).
8. **Ratchet de deuda UI (plan 138):** este plan NO crea archivos `.tsx` nuevos (solo `.ts` y hooks). En los `.tsx` que edita, PROHIBIDO `style={{}}`; cualquier estilo va por clases de módulo o el token global de `theme.css` ya citado. Los `.tsx` nuevos tendrían alcance CERO de inline-style — no aplica porque no hay ninguno.
9. **Flags por la vía canónica (reglas duras del repo):** `FlagSpec` en `backend/services/harness_flags.py` (`:21`), categorizada en `_CATEGORY_KEYS` (`:117`, categoría `interfaz_ui`, `:109-111`) o rompe el test de categorización; default ON ⇒ entrada en `_CURATED_DEFAULTS_ON` (`backend/tests/test_harness_flags.py:467`) o rompe `test_default_known_only_for_curated`; ayuda en llano en `services/harness_flags_help.py` (`PLAIN_HELP`) o rompe `test_harness_flags_help.py`; default EFECTIVO en `config.py` (el de `FlagSpec` es cosmético). PROHIBIDO tocar `harness_defaults.env` a mano (lo genera `export_harness_defaults.py`, plan 133 §3.6).
10. **Tests backend nuevos se registran** en `HARNESS_TEST_FILES` (`backend/scripts/run_harness_tests.sh:20`) o el meta-test del plan 49 rompe. pytest POR ARCHIVO con `venv/Scripts/python.exe`.
11. **Sesiones paralelas:** pre-flight `git status -- "<ruta>"` antes de editar CADA archivo caliente (`App.tsx`, `CommandPalette.tsx`, `TicketBoard.tsx`); WIP ajeno ⇒ STOP y avisar. Anclar ediciones por texto, no por línea. El implementador NO commitea (lo hace el orquestador).
12. **Formato humano y formularios:** este plan no formatea fechas/costos ni crea formularios; si una fase necesitara mostrar un valor formateado, usa los 11 exports de `frontend/src/utils/format.ts` (plan 161). No aplica hoy — se deja declarado.

---

## 4. Glosario (para un modelo menor que no conoce Stacky)

| Término | Definición |
|---|---|
| **registro de atajos** | Estructura central (Map por id) donde cada atajo se declara UNA vez con id, combo, scope, descripción y handler. Todo lo demás (dispatch, overlay, hints) deriva de ahí. |
| **combo** | La representación textual del atajo: `"Ctrl+K"`, `"?"`, `"Ctrl+/"`, `"J"`. Se parsea con reglas fijas (Ctrl≡Cmd en Mac vía `metaKey`). |
| **scope** | Dónde aplica el atajo: `global` (toda la app), `page` (solo con esa página montada; en 172 queda declarado en el tipo, sin consumidores), `dialog` (reservado para el 164). |
| **supresión en editables** | Regla: si el foco está en `INPUT`/`TEXTAREA`/`contenteditable`, los atajos de tecla suelta NO disparan (escribir "?" en un textarea no abre el overlay); los combos con Ctrl/Cmd SÍ (Ctrl+K funciona dentro de un input — paridad con hoy, `App.tsx:179-181`). |
| **atajo core** | Los 3 atajos preexistentes al plan (Ctrl+K, `?`, Ctrl+/). Están EXENTOS del gate de la flag: con la flag OFF siguen funcionando, porque apagarlos sería una regresión contra HEAD. |
| **display-only** | Entrada del registro sin handler global: existe solo para que el overlay la muestre (p.ej. "j/k navega la lista" — el handler real vive en el contenedor de la lista, no en `window`). |
| **overlay autogenerado** | El overlay `?` construye sus secciones LEYENDO el registro al abrirse. No existe ninguna lista estática paralela. |
| **foco roving (roving tabindex)** | Patrón W3C para listas: UN solo ítem tiene `tabIndex=0` (el activo), el resto `-1`. Tab entra a la lista por el activo; j/k/flechas mueven el activo y el foco DOM; Enter lo abre. El anillo de foco lo pinta `theme.css:362-365 (selector `:where(…,[tabindex],…):focus-visible` con `box-shadow: var(--focus-ring)`; verificado en frío 2026-07-18)` gratis. |
| **clamp** | Al navegar con j/k, el índice se detiene en los extremos (no da la vuelta). Decisión fija de este plan para no desorientar en tablas largas. |
| **paleta (plan 129)** | `CommandPalette.tsx`, se abre con Ctrl+K, busca tickets/agentes/packs/proyectos/navegación; flag `STACKY_PALETTE_DEEP_SEARCH_ENABLED` para búsqueda profunda. |
| **HITL** | Human-in-the-loop: el operador decide; ninguna acción con efecto se ejecuta sin su confirmación explícita. |

---

## 5. Fases

> **Pre-flight OBLIGATORIO por fase:** `git status -- "<ruta>"` de cada archivo a editar; WIP ajeno ⇒ STOP. Ediciones ancladas por texto citado. Staging quirúrgico por path explícito. El implementador NO commitea.
>
> **Comandos:** backend `cd "Stacky Agents/backend" && venv/Scripts/python.exe -m pytest tests/<archivo> -q` (POR ARCHIVO). Frontend `cd "Stacky Agents/frontend" && npx vitest run src/<ruta>` (POR ARCHIVO) y `npx tsc --noEmit` al cerrar cada fase que toque `.ts/.tsx`.

---

### F0 — Flag `STACKY_UI_SHORTCUTS_ENABLED` (default ON) end-to-end: registry + config + health + Settings + test registrado

**Objetivo (1 frase):** dejar la flag operativa por la vía canónica completa (backend registry→config→health aditivo→panel Settings) con su test registrado, ANTES de escribir una línea de frontend. **Valor:** el kill-switch existe desde el día cero y el frontend nace leyendo el mecanismo real del plan 139.

**Archivos EXACTOS:**
- EDITAR `Stacky Agents/backend/services/harness_flags.py` — agregar `FlagSpec` a `FLAG_REGISTRY` (ancla: el bloque de la flag `STACKY_UI_SHELL_V2_ENABLED`, para que queden juntas las de interfaz) y la key a `_CATEGORY_KEYS["interfaz_ui"]` (dict en `:117`; la categoría existe en `:109-111`).
- EDITAR `Stacky Agents/backend/services/harness_flags_help.py` — entrada en `PLAIN_HELP` (si falta, rompe `tests/test_harness_flags_help.py`).
- EDITAR `Stacky Agents/backend/config.py` — atributo con default `"true"` (ancla: el bloque de `STACKY_UI_SHELL_V2_ENABLED` en `:1300-1302`, mismo patrón con `"false"→"true"`).
- EDITAR `Stacky Agents/backend/api/diag.py` — campo aditivo en el dict de retorno de `health()`, inmediatamente después de la línea `"shell_v2_enabled": ...` (`:411`).
- EDITAR `Stacky Agents/backend/tests/test_harness_flags.py` — agregar `"STACKY_UI_SHORTCUTS_ENABLED"` al set `_CURATED_DEFAULTS_ON` (`:467`) con comentario `# Plan 172 — default ON (UX teclado, sin costo)`.
- NUEVO `Stacky Agents/backend/tests/test_plan172_shortcuts_flag.py`.
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh` — agregar `tests/test_plan172_shortcuts_flag.py` al final del array `HARNESS_TEST_FILES` (`:20`).
- PROHIBIDO tocar `backend/harness_defaults.env` a mano (generado; plan 133 §3.6).

**FlagSpec EXACTO (calcado del patrón del registry):**

```python
FlagSpec(
    key="STACKY_UI_SHORTCUTS_ENABLED",
    type="bool",
    label="Atajos de teclado y foco en listas",
    description="Registro central de atajos, overlay de ayuda '?' autogenerado y navegación j/k en listas del panel. OFF = solo los 3 atajos históricos (Ctrl+K, ?, Ctrl+/).",
    group="global",
    default=True,  # Plan 172 — default ON (curada en _CURATED_DEFAULTS_ON): UX pura del panel, cero costo, cero riesgo.
),
```

**config.py EXACTO:**

```python
# Plan 172 — Atajos de teclado del panel (registro central + overlay ? + roving).
# Default ON: es UX pura del dashboard, sin costo ni efectos sobre agentes.
# OFF restaura el comportamiento previo (solo Ctrl+K / ? / Ctrl+/ históricos).
STACKY_UI_SHORTCUTS_ENABLED: bool = os.getenv(
    "STACKY_UI_SHORTCUTS_ENABLED", "true"
).strip().lower() == "true"
```

**diag.py EXACTO (aditivo, tras la línea de `shell_v2_enabled`):**

```python
"ui_shortcuts_enabled": bool(getattr(_config.config, "STACKY_UI_SHORTCUTS_ENABLED", True)),  # Plan 172
```

**TDD — `tests/test_plan172_shortcuts_flag.py` PRIMERO** (calcar la estructura completa de `tests/test_plan139_shell_flag.py`, que es el template canónico: setdefault de `DATABASE_URL` sqlite memory + `LLM_BACKEND=mock` arriba del todo, fixture `client` con `create_app()` + `TESTING`):

| Test | Qué afirma |
|---|---|
| `test_flag_registered_and_categorized` | key en `FLAG_REGISTRY`; en `_CATEGORY_KEYS["interfaz_ui"]`; `categorize(key) == "interfaz_ui"`. |
| `test_flag_default_on_and_curated` | `declared_default(spec) is True` y `default_is_known(spec) is True` (curada — espejo INVERTIDO del test del 139). |
| `test_plain_help_present` | key en `PLAIN_HELP`. |
| `test_config_default_on` | `importlib.reload(config)`; `config.config.STACKY_UI_SHORTCUTS_ENABLED is True`. |
| `test_diag_health_exposes_flag_default_on` | `GET /api/diag/health` → 200 y `json["ui_shortcuts_enabled"] is True`. |
| `test_diag_health_reflects_flag_off` | `monkeypatch.setattr(config.config, "STACKY_UI_SHORTCUTS_ENABLED", False, raising=False)` → `json["ui_shortcuts_enabled"] is False`. |

**Comandos de verificación (correr en este orden, cada uno POR ARCHIVO):**
1. `venv/Scripts/python.exe -m pytest tests/test_plan172_shortcuts_flag.py -q` → verde (primero rojo, luego verde tras implementar — TDD).
2. `venv/Scripts/python.exe -m pytest tests/test_harness_flags.py -q` → verde (curado + categorización).
3. `venv/Scripts/python.exe -m pytest tests/test_harness_flags_help.py -q` → verde (ayuda en llano). NOTA: este archivo tiene historial de rojos por drift AJENO (gotcha conocido); si está rojo ANTES de tocar nada, documentarlo como preexistente y verificar solo que la entrada nueva no agregue fallos.

**Criterio de aceptación BINARIO:** los 3 comandos de arriba en verde + `grep -c "test_plan172_shortcuts_flag" scripts/run_harness_tests.sh` → `1`.

**Configurable desde UI (regla dura):** automático — al estar en `FLAG_REGISTRY` y categorizada, la flag aparece en el panel de flags del arnés en Settings (`HarnessFlagsPanel.tsx`, planes 82/86), categoría "Interfaz", tier simple. El cambio aplica al recargar la página (mismo modelo que el 139: la lee el effect de montaje de `App.tsx`). `restart_required=False`: `diag.py` la lee por request con `getattr`.

**Flag:** `STACKY_UI_SHORTCUTS_ENABLED` (la de este plan). **Runtimes:** campo read-only en un health; agnóstico de los 3 runtimes de agentes, cero impacto en ejecución. Fallback: si el health falla, el frontend queda con el default ON del módulo (ver F2). **Trabajo del operador: ninguno.**

---

### F1 — Módulo puro `services/shortcuts.ts`: registro tipado, matching, supresión, colisiones y datos del overlay

**Objetivo (1 frase):** crear el corazón del sistema como módulo 100% puro y testeable sin DOM: tipos, parser/matcher de combos (absorbiendo y corrigiendo `matches()` del hook muerto), reglas de supresión, resolución con prioridad y gate de flag, detector de colisiones y generador de datos del overlay. **Valor:** toda la semántica queda clavada por tests ANTES de tocar ningún componente.

**Archivos EXACTOS:**
- NUEVO `Stacky Agents/frontend/src/services/shortcuts.ts`
- NUEVO `Stacky Agents/frontend/src/services/shortcuts.test.ts` (co-locado, patrón `services/uiGuards.test.ts`)

**Contrato EXACTO del módulo (nombres normativos):**

```ts
// services/shortcuts.ts — Plan 172. PURO: cero imports de react/DOM.

export type ShortcutScope = "global" | "page" | "dialog"; // "dialog" reservado (plan 164), sin consumidor en 172
export type ShortcutCategory = "global" | "navegacion" | "listas";

export interface KeyEventLike {
  key: string; ctrlKey: boolean; metaKey: boolean; shiftKey: boolean; altKey: boolean;
}

export interface ShortcutDef {
  id: string;                 // único, con puntos: "palette.toggle"
  combo: string;              // "Ctrl+K" | "?" | "Ctrl+/" | "J" ...
  scope: ShortcutScope;
  category: ShortcutCategory; // sección del overlay
  description: string;        // español, para el overlay
  core?: boolean;             // true = preexistente al plan; EXENTO del gate de flag
  allowInDialog?: boolean;    // default false: con role="dialog" abierto no dispara
  displayOnly?: boolean;      // true = solo overlay; dispatch lo ignora
  handler?: () => void;       // requerido si !displayOnly
}

export interface DispatchCtx { editable: boolean; dialogOpen: boolean; enabled: boolean; }

// ── Funciones puras ──
export function parseCombo(combo: string): { ctrl: boolean; shift: boolean; alt: boolean; key: string };
export function eventMatchesCombo(ev: KeyEventLike, combo: string): boolean;
export function isEditableTarget(tagName: string, isContentEditable: boolean | undefined): boolean;
export function comboAllowedInEditable(combo: string): boolean; // true si lleva Ctrl/Cmd
export function resolveShortcut(defs: ShortcutDef[], ev: KeyEventLike, ctx: DispatchCtx): ShortcutDef | null;
export function detectCollisions(defs: ShortcutDef[]): string[][]; // grupos de ids con mismo combo+scope
export function visibleShortcuts(defs: ShortcutDef[], enabled: boolean): ShortcutDef[]; // OFF ⇒ solo core
export function groupForOverlay(defs: ShortcutDef[]): { category: ShortcutCategory; label: string; items: { comboLabel: string; description: string }[] }[];
export function comboLabel(combo: string): string; // "Ctrl+K" → "Ctrl+K", "?" → "?"
export function withShortcutHint(base: string, hint: string, enabled: boolean): string; // enabled ? `${base} · ${hint}` : base

// ── Entradas display-only (el handler vive en el contenedor de cada lista, F4) ──
export const LIST_NAV_DISPLAY_DEFS: ShortcutDef[]; // j/k/↑↓, Home/End, Enter, Escape — category "listas", displayOnly: true

// ── [ADICIÓN ARQUITECTO C2] Defs CORE como fuente única, SIN handler ──
// Los 3 atajos preexistentes se declaran UNA vez acá (id/combo/scope/category/
// description/core/allowInDialog). App.tsx (F2) mapea sobre este array y ADJUNTA
// el handler por id (ver CORE_HANDLERS en F2). El test de colisiones importa ESTE
// array, nunca una copia a mano: extiende la tesis "una sola fuente de verdad" a
// los core y cierra el punto ciego de CI (un atajo colisionante futuro rompe el test).
export type CoreShortcutSpec = Omit<ShortcutDef, "handler">;
export const CORE_SHORTCUT_DEFS: CoreShortcutSpec[]; // ["palette.toggle","help.shortcuts","nav.toggle-board"]

// ── [ADICIÓN ARQUITECTO C2] Guardia de colisiones en runtime (dev-only) ──
// Llamar UNA vez tras registrar todo (F2). En import.meta.env.DEV, si
// detectCollisions(getAll()) no es vacío ⇒ console.warn con los grupos. Cero costo
// en prod, cero acción del operador; delata regresiones que el grep no ve.
export function assertNoRuntimeCollisions(): void;

// ── Registro (estado de módulo, API mínima) ──
export const shortcutRegistry: {
  register(def: ShortcutDef): void;      // reemplaza por id (idempotente ⇒ StrictMode-safe)
  unregister(id: string): void;
  getAll(): ShortcutDef[];               // orden de inserción
  dispatch(ev: KeyEventLike, ctx: DispatchCtx): boolean; // true = matcheó y ejecutó handler
};

// ── Config de la flag (seteada por App.tsx al leer el health) ──
export function setUiShortcutsEnabled(v: boolean): void;  // default de módulo: true (paridad con default ON)
export function isUiShortcutsEnabled(): boolean;
```

**Semántica EXACTA (casos borde incluidos):**

1. `parseCombo`: split por `+`, lowercase; `ctrl` = contiene `ctrl` o `cmd`; la última parte es la tecla. (Absorbe `matches()` de `useKeyboardShortcuts.ts:10-15` con atribución en comentario.)
2. `eventMatchesCombo`:
   - Modificadores: `ctrl` matchea `ev.ctrlKey || ev.metaKey` (Mac); `alt` contra `ev.altKey`.
   - **Caso `?` (FIX del bug del hook muerto):** si la tecla del combo es `"?"`, se IGNORA el requisito de shift (en la mayoría de los layouts `?` se produce con Shift+/) y matchea `ev.key === "?" || (ev.shiftKey && ev.key === "/")`. El hook original chequeaba `wantShift` antes (`useKeyboardShortcuts.ts:18`) y por eso jamás habría matcheado — el comportamiento CORRECTO es el de `App.tsx:181`, que es el que se preserva.
   - Teclas: `enter`→`"Enter"`, `esc|escape`→`"Escape"`, resto case-insensitive contra `ev.key.toLowerCase()`.
3. `isEditableTarget(tagName, isContentEditable)`: `["INPUT","TEXTAREA"].includes(tagName) || isContentEditable === true`. Paridad EXACTA con `App.tsx:176-178` (no se agrega `SELECT`: hoy no está y agregarlo cambiaría comportamiento).
4. `resolveShortcut` — pipeline de filtros en este orden, luego primer match por orden de inserción:
   1. descartar `displayOnly`;
   2. si `!ctx.enabled` → conservar solo `core`;
   3. si `ctx.dialogOpen` → conservar solo `allowInDialog`;
   4. si `ctx.editable` → conservar solo los combos con `comboAllowedInEditable(combo) === true`;
   5. prioridad de scope ante múltiples matches: `dialog` > `page` > `global`;
   6. mismo combo+scope duplicado: gana el primero registrado (y `detectCollisions` lo delata en tests).
5. `dispatch`: `resolveShortcut`; si hay def con handler → `handler()` y `return true`; si no → `false`. El `preventDefault` lo hace el LISTENER cuando dispatch devuelve true (F2), nunca el módulo puro.
6. `visibleShortcuts(defs, false)` → solo `core` (el overlay con flag OFF muestra exactamente lo que funciona: veracidad).
7. `groupForOverlay`: agrupa por `category` en orden fijo `global` → `navegacion` → `listas`, con labels `"Global"`, `"Navegación"`, `"Listas"`; dedup por `id`.
8. `LIST_NAV_DISPLAY_DEFS` EXACTOS (todos `displayOnly: true, scope: "page", category: "listas"`): `list.next` (`"J"`, "Fila siguiente (también ↓)"), `list.prev` (`"K"`, "Fila anterior (también ↑)"), `list.first` (`"Home"`, "Primera fila"), `list.last` (`"End"`, "Última fila"), `list.open` (`"Enter"`, "Abrir el detalle de la fila"), `list.close` (`"Escape"`, "Cerrar el detalle abierto").

**TDD — `src/services/shortcuts.test.ts` PRIMERO (mínimo estos casos):**

| Test | Afirmación |
|---|---|
| `test_match_ctrl_k` | `eventMatchesCombo({key:"k",ctrlKey:true,metaKey:false,shiftKey:false,altKey:false}, "Ctrl+K")` → true; con `metaKey:true, ctrlKey:false` → true (Cmd≡Ctrl); sin modificador → false. |
| `test_match_question_shift_fix` | `eventMatchesCombo({key:"?",shiftKey:true,...}, "?")` → **true** (el bug del hook muerto queda clavado por test); `{key:"/",shiftKey:true}` → true; `{key:"/",shiftKey:false}` → false; `{key:"?",ctrlKey:true}` → false. |
| `test_editable_suppression` | `isEditableTarget("INPUT",undefined)` true; `("DIV",true)` true; `("DIV",false)` false. `comboAllowedInEditable("Ctrl+K")` true; `("?")` false; `("J")` false. |
| `test_resolve_gate_flag_off` | con `enabled:false`, un def no-core no resuelve; un def `core:true` sí. |
| `test_resolve_dialog_open` | con `dialogOpen:true`, def sin `allowInDialog` no resuelve; con `allowInDialog:true` sí. |
| `test_resolve_editable` | con `editable:true`, `"?"` no resuelve; `"Ctrl+K"` sí (paridad App.tsx). |
| `test_scope_priority` | dos defs con el mismo combo, scopes `page` y `global` → gana `page`. |
| `test_collisions_zero_en_estaticos` | **C2:** `detectCollisions([...CORE_SHORTCUT_DEFS, ...LIST_NAV_DISPLAY_DEFS])` → `[]` (importa el array REAL, no una copia; un core colisionante futuro rompe este test). |
| `test_core_defs_shape` | **C2:** `CORE_SHORTCUT_DEFS` tiene exactamente los 3 ids `palette.toggle`/`help.shortcuts`/`nav.toggle-board`, todos con `core:true` y `allowInDialog:true`, y NINGUNO trae `handler` (el handler lo adjunta App.tsx). |
| `test_registry_replace_by_id` | `register(a); register({...a, description:"x"})` → `getAll().length === 1` (StrictMode-safe). |
| `test_visible_off_solo_core` | `visibleShortcuts` con false filtra los no-core. |
| `test_group_for_overlay` | agrupa en orden global→navegacion→listas y dedup por id. |
| `test_with_shortcut_hint` | `withShortcutHint("a","b",true)` → `"a · b"`; con false → `"a"`. |

**Comando:** `npx vitest run src/services/shortcuts.test.ts` (rojo → implementar → verde) y `npx tsc --noEmit`.

**Criterio de aceptación BINARIO:** KPI-1 verde + `tsc` exit 0. Ningún import de `react` en `shortcuts.ts` (`grep -c "from \"react\"" src/services/shortcuts.ts` → 0).

**Flag:** el módulo respeta `enabled` vía `DispatchCtx`; los core quedan exentos (así OFF = hoy). **Runtimes:** N/A (módulo puro de frontend). **Trabajo del operador: ninguno.**

---

### F2 — Hooks de suscripción + migración del keydown de `App.tsx` al registro (paridad byte-compatible)

**Objetivo (1 frase):** crear `useShortcut` y `useGlobalShortcutListener`, migrar los 3 atajos reales de `App.tsx:210-235 (v2: era :173-200; drift confirmado en frío — anclar por el texto `const onKeyDown` + `isPaletteShortcut`)` al registro sin cambiar comportamiento, y leer la flag del health SIN requests nuevos. **Valor:** una sola puerta de entrada de teclado; el ad-hoc muere.

**Archivos EXACTOS:**
- NUEVO `Stacky Agents/frontend/src/hooks/useShortcut.ts`
- NUEVO `Stacky Agents/frontend/src/hooks/useGlobalShortcutListener.ts`
- EDITAR `Stacky Agents/frontend/src/App.tsx` (borrar el `useEffect` del keydown `:173-200`; registrar los 3 core; extender el `.then` del fetch de health `:154-161`)

**`useShortcut.ts` EXACTO (patrón ref para evitar closures stale):**

```ts
import { useEffect, useRef } from "react";
import { shortcutRegistry } from "../services/shortcuts";
import type { ShortcutDef } from "../services/shortcuts";

/** Registra un atajo mientras el componente esté montado. El handler se lee
 *  por ref en cada disparo (nunca queda stale). Re-registro por id es
 *  idempotente (StrictMode-safe: register→cleanup→register no duplica). */
export function useShortcut(def: ShortcutDef): void {
  const ref = useRef(def);
  ref.current = def;
  useEffect(() => {
    shortcutRegistry.register({ ...ref.current, handler: () => ref.current.handler?.() });
    return () => shortcutRegistry.unregister(ref.current.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [def.id]);
}
```

**`useGlobalShortcutListener.ts` EXACTO:**

```ts
import { useEffect } from "react";
import { shortcutRegistry, isEditableTarget, isUiShortcutsEnabled } from "../services/shortcuts";

/** ÚNICO listener global de teclado de la app (Plan 172). Montar UNA vez en App. */
export function useGlobalShortcutListener(): void {
  useEffect(() => {
    const onKeyDown = (ev: KeyboardEvent) => {
      const t = ev.target as HTMLElement | null;
      const handled = shortcutRegistry.dispatch(
        { key: ev.key, ctrlKey: ev.ctrlKey, metaKey: ev.metaKey, shiftKey: ev.shiftKey, altKey: ev.altKey },
        {
          editable: isEditableTarget(t?.tagName ?? "", t?.isContentEditable),
          dialogOpen: document.querySelector('[role="dialog"]') != null,
          enabled: isUiShortcutsEnabled(),
        },
      );
      if (handled) ev.preventDefault();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}
```

**Migración en `App.tsx` (anclas por texto):**

1. BORRAR el `useEffect` completo que empieza con `const onKeyDown = (ev: KeyboardEvent) => {` y contiene `isPaletteShortcut` (hoy `:173-200`). **Conservar intactos** `tabRef` (`:74-75`) y el comentario del plan 136 F7.
2. AGREGAR (junto a `useGlobalExecutionNotifier()`, ancla el call de ese hook). **C2 (v2): los defs CORE NO se re-declaran acá** — se importan de `CORE_SHORTCUT_DEFS` (fuente única, F1) y App.tsx SOLO adjunta el handler por id vía el mapa local `CORE_HANDLERS`. Así el test de colisiones y el runtime consumen el MISMO array:

```tsx
import { CORE_SHORTCUT_DEFS, assertNoRuntimeCollisions } from "./services/shortcuts";

// Mapa id → handler (los combos/scope/description viven en CORE_SHORTCUT_DEFS, F1).
const CORE_HANDLERS: Record<string, () => void> = {
  "palette.toggle": () => setPaletteOpen((v) => !v),
  "help.shortcuts": () => setCheatsheetOpen((v) => !v),
  // Plan 136 F7 — usar el tab ACTUAL (tabRef) y reusar selectTab (pushState con guard).
  // PROHIBIDO pushState dentro del updater de setTab (StrictMode lo invoca dos veces).
  "nav.toggle-board": () => selectTab(toggleNavTab(tabRef.current)),
};

useGlobalShortcutListener();
CORE_SHORTCUT_DEFS.forEach((spec) =>
  // useShortcut es un hook: el orden y la cantidad de CORE_SHORTCUT_DEFS es ESTÁTICO
  // (3 entradas constantes en módulo), así que el forEach cumple las reglas de hooks.
  useShortcut({ ...spec, handler: CORE_HANDLERS[spec.id] }),
);
useEffect(() => { assertNoRuntimeCollisions(); }, []); // dev-only warn (C2)
```

> **Nota de reglas-de-hooks (para el modelo menor):** `CORE_SHORTCUT_DEFS` es una constante de módulo de longitud fija (3). Iterarla con `.forEach` para llamar `useShortcut` es seguro porque el número de hooks NO varía entre renders. NO derivar este array de props/estado ni filtrarlo condicionalmente.

3. EXTENDER el `.then` del fetch de health existente (ancla: `d: { shell_v2_enabled?: boolean }` en `:156`): tipo pasa a `{ shell_v2_enabled?: boolean; ui_shortcuts_enabled?: boolean }` y se agrega `setUiShortcutsEnabled(d.ui_shortcuts_enabled !== false);` dentro del mismo `.then`. En el `.catch` NO se toca la flag (queda el default ON del módulo — una falla de red no debe degradar UX con default ON; simetría inversa al 139, cuyo default es OFF).

**Tabla de paridad OBLIGATORIA (verificar una por una en smoke §9):**

| Comportamiento HOY (`App.tsx:210-235 (v2: era :173-200; drift confirmado en frío — anclar por el texto `const onKeyDown` + `isPaletteShortcut`)`) | Tras F2 |
|---|---|
| Ctrl+K toggle paleta, TAMBIÉN con foco en input | idéntico (`comboAllowedInEditable("Ctrl+K")` = true; `allowInDialog` = true cubre paleta abierta) |
| `?` toggle cheatsheet SOLO fuera de editables, sin Ctrl/Meta | idéntico (supresión de tecla suelta + `eventMatchesCombo` exige sin Ctrl) |
| Ctrl+/ alterna team↔tickets vía `toggleNavTab(tabRef.current)` | idéntico (mismo handler, mismo `tabRef`) |
| `preventDefault` solo cuando un atajo matchea | idéntico (`if (handled) ev.preventDefault()`) |
| Los 3 funcionan con cualquier modal abierto (listener global sin guard de diálogo) | idéntico (`allowInDialog: true` en los 3) |

**TDD:** los tests de esta fase son los de F1 (la semántica ya quedó clavada ahí; los hooks son pegamento sin lógica). Gate: `npx tsc --noEmit` + KPI-3 (`grep -c 'addEventListener("keydown"' src/App.tsx` → 0) + smoke §9 pasos 1-4.

**Criterio de aceptación BINARIO:** KPI-3 → `0`; KPI-8 → `1`; `tsc` exit 0; smoke de paridad OK.

**Flag:** OFF ⇒ dispatch solo resuelve los 3 core = comportamiento de HOY exacto. **Runtimes:** agnóstico (UI del panel). **Trabajo del operador: ninguno.**

---

### F3 — Overlay `?` AUTOGENERADO del registro (y muerte de la lista que miente)

**Objetivo (1 frase):** reescribir el CONTENIDO de `ShortcutsCheatsheet.tsx` para que se autogenere del registro (+ `LIST_NAV_DISPLAY_DEFS` si la flag está ON), agregarle cierre por Escape, y borrar `hooks/useKeyboardShortcuts.ts`. **Valor:** el overlay no puede volver a mentir; la tercera fuente de verdad muere.

**Archivos EXACTOS:**
- EDITAR `Stacky Agents/frontend/src/components/ShortcutsCheatsheet.tsx` (mismo nombre, mismo montaje `App.tsx:414-417` — diff mínimo)
- BORRAR `Stacky Agents/frontend/src/hooks/useKeyboardShortcuts.ts` (cero consumidores tras esta fase; su `matches()` ya fue absorbido y corregido en F1)
- (SIN CAMBIOS) `ShortcutsCheatsheet.module.css` — se reusan las clases existentes (`backdrop`, `modal`, `header`, `section`, `table`, `kbd`, `plus`)

**Reescritura EXACTA del componente (estructura):**

```tsx
import { shortcutRegistry, groupForOverlay, visibleShortcuts, isUiShortcutsEnabled,
         LIST_NAV_DISPLAY_DEFS } from "../services/shortcuts";
import styles from "./ShortcutsCheatsheet.module.css";

export default function ShortcutsCheatsheet({ open, onClose }: Props) {
  if (!open) return null;
  const enabled = isUiShortcutsEnabled();
  const defs = visibleShortcuts(
    [...shortcutRegistry.getAll(), ...(enabled ? LIST_NAV_DISPLAY_DEFS : [])],
    enabled,
  );
  const groups = groupForOverlay(defs);
  // render: mismo markup de secciones/tabla/kbd que hoy, iterando groups.
  // C4 (v2): asociar el diálogo a su título → <h2 id="shortcuts-overlay-title">…</h2>
  //          y en el contenedor role="dialog" agregar aria-labelledby="shortcuts-overlay-title".
  // en el <div className={styles.backdrop}> agregar:
  //   onKeyDown={(e) => { if (e.key === "Escape") { e.preventDefault(); onClose(); } }}
  //   tabIndex={-1} y ref con focus() al montar (para que Escape funcione sin click previo)
}
```

**C3 (v2) — restauración de foco (rama SIN 164), OBLIGATORIA:** el overlay roba el foco al montar (para que Escape ande sin click). DEBE devolverlo al cerrar, o el operador que estaba roving el historial pierde su fila activa. Patrón EXACTO en el componente:

```tsx
const restoreRef = useRef<HTMLElement | null>(null);
const backdropRef = useRef<HTMLDivElement | null>(null);
useEffect(() => {
  if (!open) return;
  restoreRef.current = document.activeElement as HTMLElement | null; // guardar quién tenía foco
  backdropRef.current?.focus();
  return () => { restoreRef.current?.focus?.(); }; // restaurar al cerrar/desmontar
}, [open]);
```

(Si 164 YA está y se usa `<Dialog>`, NO agregar esto: `Dialog` del 164 ya restaura el foco al cerrar — verificado contra su contrato F1. Solo aplica en la rama manual.)

- Mantener `role="dialog"`, `aria-modal`, backdrop-click y el botón × tal cual; **C4:** sumar `aria-labelledby` al título.
- **Dependencia blanda con 164 (decisión en frío al implementar):** si `frontend/src/components/ui/Dialog.tsx` YA existe (164 implementado), envolver el contenido en `<Dialog open onClose={onClose} ariaLabel="Atajos de teclado">` en vez del backdrop manual y NO agregar el `onKeyDown` local (el Dialog ya trae Escape + focus-trap). Si NO existe, aplicar el patrón de arriba. Verificación: `ls src/components/ui/Dialog.tsx`.
- El `comboLabel` se parte por `+` para renderizar los `<kbd>` como hoy (`:51-56`).

**TDD:** la lógica (`visibleShortcuts`, `groupForOverlay`) ya está testeada en F1 — este componente queda sin lógica propia (solo render), coherente con §3.7. Gate: `tsc` + KPI-4 + KPI-5 + smoke §9 paso 5.

**Criterio de aceptación BINARIO:** KPI-4 → 0 hits ambos greps; KPI-5 → ≥1; `tsc` exit 0.

**Flag:** ON ⇒ overlay muestra core + navegación + listas; OFF ⇒ solo los 3 core (que es TODO lo que funciona con OFF — veracidad en ambos estados). **Runtimes:** agnóstico. **Trabajo del operador: ninguno (gana un overlay que por fin dice la verdad).**

---

### F4 — Foco roving en Historial de ejecuciones y Bandeja de revisión (j/k/flechas + Enter + Escape)

**Objetivo (1 frase):** crear la lógica pura de roving (`services/rovingFocus.ts`) y el hook (`hooks/useRovingFocus.ts`), y aplicarlos a las DOS tablas de mayor tráfico de lectura: historial (`ExecutionHistoryPage`) y revisión (`ReviewInboxPage`). **Valor:** el operador recorre y abre ejecuciones sin tocar el mouse; primer paso real del "cockpit".

**Archivos EXACTOS:**
- NUEVO `Stacky Agents/frontend/src/services/rovingFocus.ts`
- NUEVO `Stacky Agents/frontend/src/services/rovingFocus.test.ts`
- NUEVO `Stacky Agents/frontend/src/hooks/useRovingFocus.ts`
- EDITAR `Stacky Agents/frontend/src/pages/ExecutionHistoryPage.tsx`
- EDITAR `Stacky Agents/frontend/src/pages/ReviewInboxPage.tsx`

**`rovingFocus.ts` EXACTO (puro):**

```ts
// services/rovingFocus.ts — Plan 172. PURO: cero DOM.
export type RovingAction = "next" | "prev" | "first" | "last" | "open" | "escape" | null;

/** Mapea tecla→acción. hasModifier=true (Ctrl/Meta/Alt) ⇒ null SIEMPRE
 *  (no secuestrar atajos del navegador con modificador, como Ctrl+End y Alt+flechas). */
export function rovingActionForKey(key: string, hasModifier: boolean): RovingAction {
  if (hasModifier) return null;
  switch (key) {
    case "j": case "J": case "ArrowDown": return "next";
    case "k": case "K": case "ArrowUp":   return "prev";
    case "Home":  return "first";
    case "End":   return "last";
    case "Enter": return "open";
    case "Escape": return "escape";
    default: return null;
  }
}

/** Próximo índice con CLAMP (sin wraparound — decisión fija del plan).
 *  current=-1 (sin activo): next/first⇒0, prev/last⇒count-1. count<=0 ⇒ -1. */
export function nextRovingIndex(action: "next" | "prev" | "first" | "last", current: number, count: number): number;

/** Clamp del índice activo cuando la lista cambia de tamaño (borrados/paginación). */
export function clampRovingIndex(current: number, count: number): number; // count<=0 ⇒ -1; si current>=count ⇒ count-1
```

**`useRovingFocus.ts` EXACTO (pegamento fino, sin lógica):**

```ts
interface UseRovingFocusOpts {
  itemCount: number;
  onOpen: (index: number) => void;
  onEscape?: () => void;
}
export function useRovingFocus(opts: UseRovingFocusOpts): {
  activeIndex: number;
  containerProps: { onKeyDown: (ev: React.KeyboardEvent) => void; ref: React.RefObject<HTMLTableSectionElement> };
  rowProps: (index: number) => { tabIndex: number; "data-roving-item": string; onFocus: () => void };
};
```

Reglas de implementación del hook (sin ambigüedad):
1. `onKeyDown` del contenedor: si `!isUiShortcutsEnabled()` → return (flag OFF = inerte). Si `!(ev.target as HTMLElement)?.hasAttribute("data-roving-item")` → return (**crítico**: teclas sobre botones/links DENTRO de una fila no se secuestran; Enter sobre el botón "Ver detalle" de `ReviewInboxPage:111` sigue clickeando el botón). Calcular `rovingActionForKey(ev.key, ev.ctrlKey || ev.metaKey || ev.altKey)`; si null → return; `ev.preventDefault()`; `open` → `opts.onOpen(activeIndex)`; `escape` → `opts.onEscape?.()`; direccionales → `nextRovingIndex` + `setActiveIndex` + enfocar el nodo del índice destino. **C1 (v2) — LITERAL, sin ambigüedad: usar BACKTICKS, NO comillas simples** (con comillas simples `${next}` NO se interpola y el foco jamás se movería): `` containerRef.current?.querySelector(`[data-roving-item="${next}"]`) as HTMLElement | null ``, con `?.focus()`. El nodo destino ya tiene `data-roving-item` estático, así que la query funciona aunque el re-render por `setActiveIndex` aún no haya corrido (`.focus()` sobre `tabindex=-1` es válido programáticamente).
2. `rowProps(index)`: `tabIndex: index === Math.max(0, clampRovingIndex(activeIndex, itemCount)) ? 0 : -1` (si no hay activo aún, la fila 0 lleva `tabIndex=0` para que Tab entre a la lista); `data-roving-item: String(index)`; `onFocus: () => setActiveIndex(index)` (click del mouse sincroniza el roving — mouse y teclado nunca divergen).
3. `useEffect` con `[opts.itemCount]`: `setActiveIndex((i) => clampRovingIndex(i, opts.itemCount))`.
4. Foco visible: NADA que hacer — `theme.css:362-365 (selector `:where(…,[tabindex],…):focus-visible` con `box-shadow: var(--focus-ring)`; verificado en frío 2026-07-18)` pinta `:focus-visible` en `[tabindex]`. PROHIBIDO agregar CSS nuevo o `style={{}}`.

**Aplicación EXACTA — `ExecutionHistoryPage.tsx`:**
1. `const roving = useRovingFocus({ itemCount: items.length, onOpen: (i) => { const it = items[i]; if (it) setDetailId(it.id); }, onEscape: () => setDetailId(null) });`
2. `<tbody>` (ancla: `{items.map((item) => (` en `:183`) pasa a `<tbody ref={roving.containerProps.ref} onKeyDown={roving.containerProps.onKeyDown}>`.
3. `items.map((item) => (` pasa a `items.map((item, idx) => (` y el `<tr ...>` (`:184-189`) suma `{...roving.rowProps(idx)}`. El `onClick` existente NO se toca.
4. Escape con el drawer abierto: ya cubierto por `onEscape` (cerrar dos veces es idempotente: `setDetailId(null)` sobre null es no-op).

**Aplicación EXACTA — `ReviewInboxPage.tsx`:**
1. `const roving = useRovingFocus({ itemCount: sortedRows.length, onOpen: (i) => { const r = sortedRows[i]; if (r) setDetailExecutionId(r.id); }, onEscape: () => setDetailExecutionId(null) });`
2. `<tbody>` que envuelve `{sortedRows.map((row) => (` (`:103`) suma ref + onKeyDown; el map suma `idx` y el `<tr key={row.id}>` (`:104`) suma `{...roving.rowProps(idx)}`.
3. Los botones de fila ("Ver detalle" `:111`, relanzar `:112`, descartar `:115`) quedan intactos y protegidos por la regla 1 del hook (target sin `data-roving-item` ⇒ el roving no interviene). **HITL:** Enter en fila NUNCA relanza ni descarta — solo abre detalle (lectura); relanzar/descartar siguen siendo clicks explícitos en sus botones.

**TDD — `src/services/rovingFocus.test.ts` PRIMERO:**

| Test | Afirmación |
|---|---|
| `test_action_map` | j/J/ArrowDown→next; k/K/ArrowUp→prev; Home/End/Enter/Escape→first/last/open/escape; "a"→null; Tab→null. |
| `test_modifier_bypass` | `rovingActionForKey("End", true)` → null (Ctrl+End del navegador intacto); `("j", true)` → null. |
| `test_next_index_clamp` | next en último ⇒ se queda (`nextRovingIndex("next", 2, 3)` → 2); prev en 0 ⇒ 0; first→0; last→count-1; count 0 ⇒ -1. |
| `test_current_menos_uno` | `("next", -1, 5)` → 0; `("prev", -1, 5)` → 4; `("first"/-1)` → 0. |
| `test_clamp_on_shrink` | `clampRovingIndex(4, 3)` → 2; `(1, 0)` → -1; `(-1, 3)` → -1. |

**Comandos:** `npx vitest run src/services/rovingFocus.test.ts` → verde; `npx tsc --noEmit` → exit 0.

**Criterio de aceptación BINARIO:** KPI-2 verde; `tsc` exit 0; `grep -c "data-roving-item" src/hooks/useRovingFocus.ts` → ≥2; smoke §9 pasos 6-8.

**Flag:** OFF ⇒ el hook retorna acciones inertes (guard en el paso 1) y las filas se comportan como hoy. **Runtimes:** agnóstico. **Dependencia blanda con 174 (virtualización):** el hook consulta el DOM por `data-roving-item` AL MOMENTO del evento (no cachea nodos), así que sobrevive a listas virtualizadas; limitación documentada: con 174 implementado, `End` salta a la última fila RENDERIZADA — 174 deberá integrar su scroll-into-view con este hook (cita a este contrato). **Trabajo del operador: ninguno.**

---

### F5 — [RECORTABLE] Foco roving en el tablero de tickets (tarjetas)

**Objetivo (1 frase):** extender el roving a la lista principal de tarjetas del tablero (`TicketBoard.tsx`), donde Enter expande/colapsa la tarjeta activa. **Valor:** la tercera superficie de más tráfico gana teclado. **Por qué recortable:** `TicketBoard.tsx` es EL archivo caliente del repo (el 164 F4 le extirpa el `RunModal` inline `:94-231`; sesiones paralelas lo tocan); si al implementar hay WIP ajeno, esta fase se DIFIERE sin afectar el DoD del plan.

**Archivos EXACTOS:**
- EDITAR `Stacky Agents/frontend/src/pages/TicketBoard.tsx`

**Aplicación (anclas por texto, verificar en frío antes):**
1. En `function TicketCard` (`:249`): el `<div className={styles.cardHeader} onClick={() => setExpanded((x) => !x)}>` (`:422`) suma el atributo `data-card-header="true"` (ancla estable para el Enter sintético).
2. En el contenedor de la lista principal de tarjetas (el que hace `.map` de tickets y renderiza `<TicketCard` en `:735`): montar `useRovingFocus` con `itemCount` = tickets visibles y `onOpen: (i) => { const el = containerRef.current?.querySelector('[data-roving-item="' + i + '"] [data-card-header]') as HTMLElement | null; el?.click(); }` (reusa el toggle existente sin prop-drilling ni tocar el estado interno de `TicketCard`). Cada wrapper de tarjeta suma `{...roving.rowProps(idx)}`.
3. `onEscape` NO se cablea acá (no hay "detalle" que cerrar; colapsar por Escape sería comportamiento nuevo no pedido).
4. La lista de huérfanos (`:1157-1158`) NO se toca (tráfico marginal).

**TDD:** sin lógica nueva (reusa F4); gate = `tsc` + smoke §9 paso 9. **Criterio BINARIO:** `grep -c "data-card-header" src/pages/TicketBoard.tsx` → `2` (atributo + selector); `tsc` exit 0.

**Flag:** misma (`OFF` ⇒ inerte). **Runtimes:** agnóstico. **HITL:** Enter solo expande/colapsa (presentación); lanzar agente sigue requiriendo sus clicks/diálogos de siempre. **Trabajo del operador: ninguno.**

---

### F6 — Hints de atajos en la paleta (129) y en tooltips

**Objetivo (1 frase):** hacer descubribles los atajos donde el operador ya mira: un comando nuevo en la paleta Ctrl+K que abre el overlay, y el tooltip de las filas del historial enseñando Enter/j/k. **Valor:** descubribilidad sin entrenar a nadie.

**Archivos EXACTOS:**
- EDITAR `Stacky Agents/frontend/src/components/CommandPalette.tsx`
- EDITAR `Stacky Agents/frontend/src/App.tsx` (pasar la prop nueva)
- EDITAR `Stacky Agents/frontend/src/pages/ExecutionHistoryPage.tsx` (tooltip de fila)

**Cambios EXACTOS:**
1. `CommandPalette.tsx` — a `interface Props` (`:9-16`) sumar `onOpenShortcuts?: () => void;`. En el `useMemo` de `allCommands` (`:83-132`), INMEDIATAMENTE después del bloque `commands.push(...NAV_COMMANDS...)` (`:85-93`), agregar:

```ts
if (onOpenShortcuts) {
  commands.push({
    id: "action-shortcuts-overlay",
    kind: "nav",
    icon: "⌨️",
    label: "Ver atajos de teclado",
    hint: "?",   // usa el render de hint ya existente (:221)
    run: () => onOpenShortcuts(),
  });
}
```

   y sumar `onOpenShortcuts` a las deps del `useMemo` (`:132`). El footer (`:226-230`) NO se toca (sus hints ↑↓/↵/Esc de la paleta son locales y verdaderos).
2. `App.tsx` — en el montaje de `<CommandPalette ...>` (`:408-413`) sumar `onOpenShortcuts={() => setCheatsheetOpen(true)}`.
3. `ExecutionHistoryPage.tsx` — el `title="Click para ver detalle"` de la fila (`:188`) pasa a `title={withShortcutHint("Click para ver detalle", "Enter abre · j/k navega", isUiShortcutsEnabled())}` (import desde `services/shortcuts`). Con flag OFF el tooltip queda EXACTAMENTE como hoy.

**TDD:** `withShortcutHint` ya está testeado en F1 (`test_with_shortcut_hint`); el resto es wiring sin lógica. Gate: `tsc` + smoke §9 paso 10. Nota: `fuzzyScore` (`commandPaletteData.ts:31-49`) matchea el label nuevo sin cambios; NO se toca `commandPaletteData.ts` (cero riesgo sobre su test existente).

**Criterio de aceptación BINARIO:** `grep -c "action-shortcuts-overlay" src/components/CommandPalette.tsx` → ≥1; `grep -c "withShortcutHint" src/pages/ExecutionHistoryPage.tsx` → `1`; `tsc` exit 0.

**Flag:** el comando de paleta se muestra siempre (abre el overlay, que es veraz en ambos estados); el hint del tooltip respeta la flag. **Runtimes:** agnóstico. **Trabajo del operador: ninguno.**

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | **Sesión paralela** editando `App.tsx`/`TicketBoard.tsx`/`CommandPalette.tsx` (escenario real reconfirmado 2026-07-17). | Pre-flight `git status -- "<ruta>"` por archivo y por fase; anclas por TEXTO; F5 explícitamente recortable/diferible; staging por paths. |
| R2 | **StrictMode monta efectos dos veces en dev** (`main.tsx` monta en StrictMode — precedente plan 136 F7). | `register()` reemplaza por id (idempotente, test `test_registry_replace_by_id`); el ciclo register→cleanup→register queda sin efectos residuales. |
| R3 | **Regresión de paridad** en los 3 atajos migrados (el riesgo más caro: son los únicos que existen). | Tabla de paridad obligatoria en F2 + tests de F1 que clavan supresión/editable/dialog + smoke §9 pasos 1-4 uno por uno. |
| R4 | **Colisión con listeners locales existentes** (paleta `:179-193`, drawers, `PlansBoardPage`, tour del 151 cuando aterrice). | Los listeners locales operan sobre su propio foco/elemento y hacen su propio `preventDefault` ANTES de que el evento burbujee a window en los casos que manejan; el registro además suprime no-core con `role="dialog"` abierto. El tour del 151 declara no hacer `preventDefault` (su C7/R8). Smoke §9 paso 8 prueba la coexistencia. |
| R5 | **Enter secuestrado sobre botones internos de filas** (p.ej. relanzar/descartar en revisión — sería un HITL-break). | Regla dura del hook: si `ev.target` no tiene `data-roving-item`, el roving NO interviene (F4 paso 1). Smoke §9 paso 7 lo verifica explícitamente. |
| R6 | **El 174 virtualiza las listas** y el roving apunta a filas no renderizadas. | El hook consulta el DOM en el momento del evento (sin caché de nodos); contrato documentado en F4 para que 174 integre scroll-into-view. Degradación aceptable mientras tanto: `End` va a la última fila renderizada. |
| R7 | **Drift de líneas** entre este doc y HEAD al implementar. | Toda edición anclada por símbolo/texto citado; si un ancla no aparece, STOP y recontar (nunca adivinar). |
| R8 | **`?` en layouts sin Shift+/** (teclados donde `?` es otra combinación). | `eventMatchesCombo` acepta `ev.key === "?"` directo (independiente del layout) ADEMÁS de Shift+/; es la semántica de `App.tsx:181` que ya funciona hoy. |
| R9 | **Ratchets ajenos en rojo preexistente** (uiDebtRatchet/tests con drift conocido). | Este plan no crea `.tsx` (alcance cero del ratchet); correr SOLO los tests por archivo que este plan nombra; rojos preexistentes se documentan como ajenos, jamás se "arreglan" de pasada. |

---

## 7. Fuera de scope (y qué hermano lo cubre)

- **Presets de filtros, columnas visibles, sort/anchos persistentes, restauración de última vista** → plan 173 (vistas guardadas).
- **Virtualización de listas largas, prefetch on-hover, cache de navegación react-query, presupuesto de perf** → plan 174 (rendimiento percibido). El roving de F4 le deja el contrato documentado.
- **Hover-cards/peek, menú contextual de clic derecho, acciones rápidas con efecto en filas** → plan 175 (peek y acciones rápidas), que CONSUME este registro para declarar sus atajos y pasa toda acción con efecto por el diálogo del 164.
- **Primitiva `Dialog`, focus-trap y confirmaciones de marca** → plan 164 (este plan solo declara la dependencia blanda de F3).
- **Tour de onboarding y botón "?" de la TopBar** → plan 151 (§2.5: afordances distintas, cero conflicto).
- **Atajos con efecto (relanzar, descartar, publicar, lanzar agente)** → prohibidos acá por HITL; si algún día se agregan, nacen en 175 con confirmación canónica.
- **Persistencia de preferencias de teclado / remapeo de combos** → no lo pide nadie; mono-operador; se descarta.

---

## 8. Orden de implementación

1. **F0** — flag backend end-to-end + test registrado (nada de frontend depende de adivinar la flag).
2. **F1** — módulo puro `shortcuts.ts` + tests (la semántica queda clavada antes de tocar UI).
3. **F2** — hooks + migración de `App.tsx` (paridad verificada contra la tabla).
4. **F3** — overlay autogenerado + borrado de `useKeyboardShortcuts.ts`.
5. **F4** — roving puro + historial + revisión.
6. **F5** — roving tablero de tickets (RECORTABLE: diferir ante WIP ajeno sin afectar DoD).
7. **F6** — hints en paleta y tooltip.

Dependencias: F1→F2→F3 estricta; F4 depende de F1-F2 (usa flag y supresión) pero no de F3; F5 depende de F4; F6 depende de F1 (helper) y F3 (overlay como destino del comando).

## 9. Smoke manual (operador, 5 minutos, checklist del DoD)

1. Ctrl+K abre y cierra la paleta; también con el cursor dentro de un input.
2. `?` abre el overlay fuera de inputs; escribir "?" dentro de un textarea NO lo abre.
3. Ctrl+/ alterna Mi Equipo ↔ Tickets (dos veces = vuelve).
4. Con un modal cualquiera abierto, Ctrl+K sigue funcionando (paridad).
5. El overlay muestra SOLO atajos que existen (ninguna mención a "Re-ejecutar último agente"); Escape lo cierra; en claro y oscuro se ve bien.
5b. **(C3) Restauración de foco:** en Historial, Tab entra a la tabla y j/k mueve el anillo a una fila; abrir `?`; cerrar con Escape ⇒ el foco vuelve a la MISMA fila activa (no al `<body>`). Un lector de pantalla anuncia el diálogo por su título "Atajos de teclado" (C4, `aria-labelledby`).
6. Historial: Tab entra a la tabla, j/k/↑↓ mueven el anillo de foco, Enter abre el drawer de la fila activa, Escape lo cierra.
7. Revisión: j/k + Enter abre detalle; con el foco en el botón "Descartar" de una fila, Enter clickea el botón y NO abre el detalle (regla R5).
8. Con la paleta abierta, j/k escriben en el input de búsqueda (no navegan listas de atrás).
9. (Si F5 entró) Tablero: j/k entre tarjetas, Enter expande/colapsa.
10. En la paleta, "Ver atajos de teclado" aparece con hint `?` y abre el overlay.
11. Settings → panel de flags → "Atajos de teclado y foco en listas" visible en categoría Interfaz; apagarla + recargar ⇒ todo vuelve al comportamiento previo (pasos 1-4 siguen OK; j/k inertes; tooltip sin hint).

## 10. Definición de Hecho (DoD) global

- [ ] KPI-1..KPI-8 en verde con los comandos EXACTOS de §1 (por archivo, nunca suite completa).
- [ ] Tabla de paridad de F2 verificada punto por punto (smoke §9 pasos 1-4).
- [ ] Smoke manual §9 completo por el operador (pasos 5-11).
- [ ] `tests/test_plan172_shortcuts_flag.py` verde Y registrado en `HARNESS_TEST_FILES`.
- [ ] Flag visible y toggleable en Settings (regla dura: config por UI, no solo env).
- [ ] Cero `style={{}}` nuevos, cero `.tsx` nuevos, cero requests HTTP nuevos, cero cambios en `harness_defaults.env` a mano.
- [ ] Ningún atajo dispara acciones con efecto (revisión de diff contra la lista de handlers: toggles de UI y aperturas de detalle únicamente).
- [ ] **C2:** `CORE_SHORTCUT_DEFS` es la única declaración de los core (App.tsx los importa, no los re-declara); `test_collisions_zero_en_estaticos` + `test_core_defs_shape` verdes; `assertNoRuntimeCollisions()` cableado (dev-only).
- [ ] **C3:** el overlay restaura el foco al cerrar (rama sin 164) — smoke: roving en historial → `?` → Escape → el foco vuelve a la fila que estaba activa.
- [ ] **C7 (huella de regresión, convención plan 163):** registrar en `Stacky Agents/docs/sistema/error_fingerprints.json` la huella `overlay-atajos-miente` (patrón: lista estática de atajos divergente de la implementación real; guard_test = KPI-4 grep + `test_group_for_overlay`) y `matcher-shift-question-bug` (patrón: `matches()` chequea `wantShift` antes del caso `?`; guard_test = `test_match_question_shift_fix`). Con id/patrón/plan-commit/fecha.
- [ ] Resumen de implementación: qué se recortó (¿F5?), drift encontrado vs este doc, y estado de los hermanos 173-175 citados.
