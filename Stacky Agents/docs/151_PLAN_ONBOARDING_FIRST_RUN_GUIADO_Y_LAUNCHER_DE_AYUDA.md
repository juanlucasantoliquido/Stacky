# Plan 151 — Onboarding / first-run guiado (mapa de capacidades) + launcher de ayuda

> **Estado:** CRITICADO v2 (APROBADO-CON-CAMBIOS)
> **Versión:** v1 -> v2 (criticado 2026-07-16 por StackyArchitectaUltraEficientCode como juez adversarial)
> **Autor:** StackyArchitectaUltraEficientCode
> **Fecha:** 2026-07-15 (v1) · 2026-07-16 (v2)
> **Depende de:** plan 138 v2 (tokens `--duration-*`/`--ease-*`/`--focus-ring` + primitivas `components/ui/`: `Card`, `Button`, `IconButton` — IMPLEMENTADO) · plan 139 (App Shell v2 — IMPLEMENTADO con flag `STACKY_UI_SHELL_V2_ENABLED` default OFF; el tour ancla al contenedor de nav VIGENTE) · plan 141 (dueño único de `prefers-reduced-motion` + `:focus-visible`; IMPLEMENTADO, CONSUMIDO no reimplementado) · plan 143 (tokens `--transition-opacity`/`--transition-transform`; IMPLEMENTADO, CONSUMIDO) · plan 129 (paleta global Ctrl+K, IMPLEMENTADA — el tour la señala Y se registra en ella, ver F4b).
> **Serie:** UX/UI (138 → 139 → 140 → 141 → 143 → **151**). La serie 138-143 ya está IMPLEMENTADA ⇒ todos los tokens/primitivas que este plan consume EXISTEN en `theme.css` y `components/ui/` (verificado 2026-07-16 por grep: `--transition-opacity`/`--focus-ring` presentes en `theme.css`; barrel `components/ui/index.ts:7-22` exporta `Button`/`IconButton`/`Card`).
> **Runtimes:** 100% frontend/presentación ⇒ idéntico en Codex / Claude Code / GitHub Copilot Pro. Única dependencia de plataforma: `localStorage` del webview (con fallback declarado).
> **Flag:** default **ON** — pero NO es una flag del arnés backend (ver §4.4). Es una **preferencia de frontend** (`onboardingAutoShow`, default `true`), togglable desde la UI (Configuración). El estado "ya lo vi" vive en `localStorage`.

---

## 0. Changelog de versiones

- **v2 (2026-07-16, criticado):** veredicto **APROBADO-CON-CAMBIOS** (4 IMPORTANTES, 4 MENORES, 0 bloqueantes). Cambios:
  - **C1 (IMPORTANTE, gotcha recurrente de la casa):** KPI-3 era auto-contradictorio — pedía `grep "stacky-agents-tour-done" ⇒ 0 líneas` mientras el mismo plan ordena conservar ese literal en `LEGACY_SEEN_KEY` dentro de `onboarding.ts` (⇒ el grep JAMÁS puede dar 0). Es exactamente el gotcha "comentario/prosa de plan choca con su propio grep-gate" (6+ ocurrencias previas: planes 134/135/136/138/146). Gate reescrito con exclusión explícita del único archivo permitido (KPI-3, F3, F5, DoD).
  - **C2 (IMPORTANTE, bug de comportamiento en la spec):** `requestOpenTour()` llamaba `resetSeen()` ⇒ si el operador re-abría el tour on-demand y recargaba SIN cerrarlo, `seen` quedaba borrado y el tour **auto-aparecía en el próximo arranque** (viola §4.5 para un operador existente sin señales de uso previo). v2: on-demand **no toca `seen`**; `closeTour()` siempre `markSeen` (idempotente). `resetSeen` queda solo como helper de test/smoke.
  - **C3 (IMPORTANTE, la spec rompía su propio gate tsc):** el pseudocódigo F3 usaba `<Card ref={cardRef} tabIndex={-1} data-anchored=...>` pero la primitiva real `Card` (`components/ui/Card.tsx:23`) **no es forwardRef** y `CardProps` (`Card.tsx:6-14`) solo acepta `children/padding/elevated/className` ⇒ NO compila y el gate declarado era justamente `tsc --noEmit`. v2: wrapper `<div>` focusable propio del feature con `Card` adentro; PROHIBIDO modificar la primitiva congelada del 138 para esto.
  - **C4 (IMPORTANTE, ambigüedad de cwd para modelos menores):** los comandos vitest/tsc mezclaban rutas desde la raíz del repo, mientras la convención de la serie (planes 150/152) es cwd `frontend/`. vitest resuelve su config desde el cwd. v2: TODOS los comandos normativos arrancan con `cd "Stacky Agents/frontend"` explícito.
  - **C5 (MENOR):** líneas de evidencia refrescadas contra HEAD real 2026-07-16 (`App.tsx:22` import, `App.tsx:396` montaje, `<nav>` en `App.tsx:265`, `styles.actions` en `TopBar.tsx:202`, `initPreferences()/initUiSections()` en `App.tsx:120-121`, sub-tabs de Settings en `SettingsPage.tsx:28`). Siguen siendo ORIENTATIVAS; el texto normativo manda.
  - **C6 (MENOR):** nota de coordinación con el plan 152: la campana del Centro de Actividad se inserta en el MISMO slot `styles.actions` de la TopBar. Ambos son aditivos y coexisten; regla de no-conflicto declarada (§4.8).
  - **C7 (MENOR):** el listener global de teclado (Esc/flechas) ahora ignora eventos originados en `input`/`textarea`/`contenteditable` y no hace `preventDefault`, para no colisionar con la paleta Ctrl+K (129) ni con campos de texto. Riesgo R8 nuevo.
  - **C8 (MENOR):** `hasPriorUse` con una sola señal (`stacky:pinnedAgents`) era débil (un operador existente sin agentes fijados vería el tour). v2: constante exportada `PRIOR_USE_SIGNAL_KEYS` extensible + test dedicado; se documenta que es heurística best-effort.
  - **[ADICIÓN ARQUITECTO] F4b:** el tour se registra como comando en la **paleta global Ctrl+K** (plan 129): entrada "Ver tour de bienvenida" en el bloque de comandos estáticos de `CommandPalette.tsx` (`:89-132`). Descubribilidad doble (botón "?" + paleta) reusando infra implementada, costo ~10 líneas, KPI-7 nuevo.
- **v1 (2026-07-15):** versión inicial. Reemplaza el prototipo existente `OnboardingTour.tsx` (ver §3, hallazgo por grep) por una implementación al estándar de la serie: launcher re-abrible, flag por preferencia (config por UI), primitivas del 138, movimiento del 143, accesibilidad del 141, fallback de `localStorage`, y **lógica pura testeable sin DOM**.

---

## 1. Resumen ejecutivo

Un operador nuevo (o que actualiza a una versión con superficies nuevas) cae en una app con ~14 pestañas y varias capacidades ocultas (paleta Ctrl+K, panel de runs, config del arnés) y **no sabe dónde está cada cosa**. Este plan entrega un **tour de bienvenida pasivo, dismissible y saltable** que resalta 4-6 zonas clave, se muestra **solo en first-run real**, y deja un **launcher "?"** en la topbar (más un comando en la paleta Ctrl+K) para re-verlo cuando el operador quiera. No agrega ningún paso obligatorio, nunca actúa por el operador, y no molesta al operador existente.

**Punto crítico (hallazgo por grep, re-verificado 2026-07-16):** ya existe un prototipo `OnboardingTour.tsx`, pero está **roto e incompleto** (anclas inexistentes, sin spotlight real, sin launcher, sin flag, sin a11y, `localStorage` sin protección). Este plan lo **eleva al estándar de la serie**, no lo duplica.

---

## 2. Objetivo + KPIs BINARIOS

**Objetivo:** que un operador en su primer arranque entienda en < 60 s el mapa de capacidades de la app, sin fricción y sin acciones automáticas, y pueda re-ver el tour on-demand desde la UI.

> **Convención de comandos (C4):** TODOS los comandos de este plan se ejecutan con cwd en el frontend. Prefijo obligatorio: `cd "Stacky Agents/frontend"` (desde la raíz del repo). vitest corre **por archivo** (gotcha conocido de test-order pollution).

**KPIs (todos binarios, verificables por comando):**

- **KPI-1 (lógica pura):** `cd "Stacky Agents/frontend"` y `npx vitest run src/services/__tests__/onboarding.test.ts` termina **exit 0** y cubre: first-run vs operador existente, migración de la key vieja, fallback sin `localStorage`, señales de uso previo, y navegación de pasos (next/prev/clamp). Ver F0.
- **KPI-2 (tipos):** `cd "Stacky Agents/frontend"` y `npx tsc --noEmit` termina **exit 0** con todos los cambios (el gate real de UI de la casa, dado que NO hay `@testing-library/react` ni `jsdom` — ver §4.6).
- **KPI-3 (no duplicación — comando EXACTO, C1):** `grep -rn "stacky-agents-tour-done" "Stacky Agents/frontend/src" | grep -v "services/onboarding.ts"` devuelve **0 líneas** tras F5. El literal de la key vieja vive **únicamente** en la constante `LEGACY_SEEN_KEY` de `src/services/onboarding.ts` (origen de migración); en particular, ya no vive en `components/OnboardingTour.tsx`. *(Nota anti-gotcha: el grep SIN la exclusión devuelve exactamente las líneas de `onboarding.ts` y eso es CORRECTO — no "arreglar" renombrando la constante ni gameando el gate.)*
- **KPI-4 (anclas reales):** para cada `target` de `STEPS` que sea un selector `data-tour`, existe **exactamente** ese atributo en el árbol de la app (verificado por el test de F1 `stepAnchorsAreDeclared`, que compara `STEPS` contra la lista blanca de anclas declaradas). 0 anclas huérfanas.
- **KPI-5 (no auto-show para el existente):** el helper puro `shouldAutoShow(s)` devuelve `false` cuando hay evidencia de uso previo (key vieja presente, o `seen v1` presente, o preferencia OFF, o alguna señal de `PRIOR_USE_SIGNAL_KEYS`). Cubierto por F0.
- **KPI-6 (launcher siempre disponible):** existe un botón "?" en la topbar (`data-tour="help-launcher"`) que llama `requestOpenTour()` sin condiciones de first-run. Verificado por `tsc` + smoke §9.
- **KPI-7 (paleta, [ADICIÓN ARQUITECTO]):** `grep -rn "nav-help-tour" "Stacky Agents/frontend/src/components/CommandPalette.tsx"` devuelve **exactamente 1** línea (el id del comando estático "Ver tour de bienvenida"). Verificado además por tsc + smoke §9 paso 8.

---

## 3. Por qué ahora / gap (evidencia por grep, refrescada 2026-07-16 — C5)

### 3.1 Ya existe un prototipo, pero está roto (NO duplicar — reemplazar)

`grep -rn "OnboardingTour" "Stacky Agents/frontend/src"` encuentra `components/OnboardingTour.tsx`, importado en `App.tsx:22` y montado en `App.tsx:396` (líneas reales a 2026-07-16; orientativas).

Evidencia de que el prototipo NO cumple el estándar de la serie:

- **Anclas inexistentes.** `grep -rn "data-tour" "Stacky Agents/frontend/src"` devuelve **solo 4 targets, todos dentro del propio `OnboardingTour.tsx`** (`OnboardingTour.tsx:26,32,38,44` — targets `agents`, `tickets`, `editor`, `run`). Ningún otro archivo declara esos `data-tour`: los pasos apuntan a elementos que **no existen**. (Re-verificado 2026-07-16.)
- **Sin spotlight real.** El comentario de cabecera promete "spotlight (outline) sobre los componentes clave", pero el componente **nunca hace `querySelector` ni lee `getBoundingClientRect`**: solo renderiza una card posicionada por clase CSS. El `target` es data muerta.
- **Sin launcher.** No hay forma de re-ver el tour: una vez seteada la key, desaparece para siempre.
- **`localStorage` sin protección.** El prototipo llama `localStorage.getItem/setItem` **sin try/catch**. En un webview con storage deshabilitado/particular esto **lanza** y puede romper el render.
- **Sin flag / sin config por UI**, **sin `prev`** (solo `next`+`skip`), **sin reduced-motion**, **sin primitivas del 138** (usa su propio `OnboardingTour.module.css`).
- **Key vieja** `stacky-agents-tour-done` (`OnboardingTour.tsx:9` — re-verificado), no versionada.

**Conclusión:** el gap es real. El plan 151 **reemplaza** este prototipo por una implementación correcta, y **migra** su key para no re-mostrar el tour a quien ya lo cerró.

### 3.2 La navegación real es densa (14 superficies)

`App.tsx` declara el tipo `Tab` con 14 valores: `team | tickets | review | unblocker | pm | logs | settings | docs | memory | diagnostics | history | migrador | devops | dbcompare`, renderizados como fila de botones `styles.navTab` dentro de `<nav className={styles.nav}>` (`App.tsx:265`, orientativo), varias gated por `sections.*` / `*Enabled`. El plan 139 (IMPLEMENTADO, flag OFF) reagrupa esta fila en una sidebar cuando el flag está ON; por eso el tour ancla al **contenedor de nav vigente** (no a pestañas individuales) y degrada con gracia si una pestaña no está montada (ver §4.3 y CROSS-151/139).

### 3.3 Capacidades ocultas que el operador nuevo no descubre solo

- **Paleta Ctrl+K** (plan 129, IMPLEMENTADA): `CommandPalette` montada en `App.tsx` con `paletteOpen`. No tiene trigger visible ⇒ un nuevo operador no la descubre. (Por eso F4b la usa también como segundo punto de entrada al tour.)
- **Panel de runs activos** (`ActiveRunsPanel`): solo aparece cuando hay runs ⇒ no está garantizado en first-run (por eso NO se ancla a él; ver §4.3).
- **Topbar / selector de proyecto**: `TopBar.tsx` — selector de proyecto y bloque `<div className={styles.actions}>` (`TopBar.tsx:202`, con `<CostCapIndicator>` `:211` y `<StreakBadge/>` `:212` como vecinos) — ancla estable garantizada en first-run.

### 3.4 Contratos que el plan CONSUME (verificados por grep 2026-07-16)

- **Primitivas 138 (IMPLEMENTADO):** barrel `components/ui/index.ts:7-14` exporta `Button` (variants `primary|secondary|ghost|danger`, `Button.tsx:5`), `IconButton` (variants `ghost|secondary|danger` — **no tiene `primary`**, `IconButton.tsx:4`; extiende `ButtonHTMLAttributes` ⇒ acepta `data-*`/`onClick`/`aria-*`, `IconButton.tsx:7`) y `Card` (**props SOLO `children/padding/elevated/className`, NO forwardRef, NO `tabIndex`** — `Card.tsx:6-23`; restricción que motiva el wrapper de F3, C3). El tour las CONSUME (es un componente feature, no una primitiva ⇒ NO cae bajo el ratchet de deuda de `components/ui/`).
- **Motion 143 (IMPLEMENTADO):** `--transition-opacity`, `--transition-transform` presentes en `theme.css` (grep 2026-07-16: 6 ocurrencias de `--transition-opacity|--focus-ring`). El tour usa esos tokens para su entrada/salida.
- **A11y 141 (IMPLEMENTADO):** 141 F5 es el **único** dueño de la regla global `@media (prefers-reduced-motion: reduce)` y de `:focus-visible`; `--focus-ring` existe en `theme.css`. El tour NO escribe ninguna regla `@media (prefers-reduced-motion)` (la global del 141 neutraliza sus transiciones automáticamente).
- **Store pattern:** `store/uiSectionsStore.ts` existe (zustand; `zustand` ya es dependencia — `store/workbench.ts:1` la importa). El store nuevo de F3 sigue ese patrón.
- **Preferencias:** `services/preferences.ts` existe con el patrón `read/write` protegido y la key `stacky:pinnedAgents` (`preferences.ts:4`); `initPreferences()`/`initUiSections()` se llaman en `App.tsx:120-121` (orientativo).

---

## 4. Principios y guardarraíles

### 4.1 Human-in-the-loop DURO

El tour es **pasivo e informativo**: solo señala dónde están las cosas. **Nunca** navega, publica, crea, ejecuta ni cambia estado del operador. Los únicos efectos son: (a) escribir la key `seen` en `localStorage` al cerrarlo, y (b) mover el índice de paso. No dispara ninguna acción de negocio ni toca la paleta/nav por el usuario (solo la *señala*; si el paso menciona Ctrl+K, es texto, el operador decide apretarlo). El comando de paleta de F4b solo ABRE el tour (misma acción que el botón "?"), nunca otra cosa.

### 4.2 Cero trabajo extra al operador

El tour **ayuda, no agrega pasos obligatorios**: es saltable en cualquier momento (Esc, botón "Saltar", click en el backdrop). No bloquea el uso de la app. El operador existente **no lo ve solo** (§4.5). El dismiss PERSISTE (key `seen v1`); nunca reaparece solo tras cerrarlo.

### 4.3 Anclas robustas (no frágiles) + degradación

Los pasos apuntan a **contenedores estables** vía atributos `data-tour` NORMATIVOS que este plan agrega (F1): `nav`, `topbar-actions`, `help-launcher`. Reglas:

- Si el elemento ancla **no está en el DOM** al abrir el paso, el paso degrada a **card centrada sin spotlight** (nunca crashea).
- Pasos "conceptuales" (bienvenida, Ctrl+K, cierre) son card centrada por diseño (target `null`).
- El anclaje se resuelve con `document.querySelector` protegido; el componente NO asume que el ancla exista.

### 4.4 Flag: default ON, pero como PREFERENCIA de frontend (NO flag del arnés)

Esta feature es **100% frontend sin superficie backend**. Introducir una flag del arnés (`FlagSpec` + `config.py` + `_CURATED_DEFAULTS_ON`) sería **sobre-ingeniería**: ningún code path backend la leería y no hay divergencia de runtime más allá de `localStorage`. Por eso el "flag default ON" se materializa como:

- **Preferencia `onboardingAutoShow`** (default `true`), guardada con el patrón `read/write` de `services/preferences.ts` (localStorage con try/catch). Togglable desde Configuración (F4). Regla de la casa cumplida: **toda config del operador es tocable por UI**.

**Confirmación de que ninguna de las 4 excepciones duras aplica** (⇒ default ON es correcto):
1. **No bypasea revisión humana:** el tour no publica ni ejecuta nada.
2. **No es destructivo:** solo escribe una key booleana en `localStorage`.
3. **`localStorage` es prerequisito garantizado** en los 3 webviews; y aun así hay **fallback en memoria** (§4.6). No hay pérdida de datos.
4. **No reduce seguridad:** no toca auth, red, ni secretos.

### 4.5 No molestar al operador existente (detección de first-run real)

`shouldAutoShow(s)` (helper puro, F0) devuelve `true` **solo si**:
- la key `seen v1` (`stacky_onboarding_seen_v1`) está **ausente**, **y**
- la preferencia `onboardingAutoShow` es `true` (o ausente ⇒ default `true`), **y**
- **no hay evidencia de uso previo** (`hasPriorUse` — C8): key vieja `stacky-agents-tour-done` presente, **o** alguna key de `PRIOR_USE_SIGNAL_KEYS` con contenido no vacío (hoy: `stacky:pinnedAgents` con array no vacío; lista extensible sin tocar la lógica).

**Invariante de C2:** abrir el tour **on-demand** (launcher "?", Configuración, paleta) NUNCA borra `seen` ni altera el gate de auto-show. La única transición de `seen` en producción es `closeTour() ⇒ markSeen()` (idempotente). Por construcción, recargar a mitad de un tour re-abierto NO puede provocar un auto-show fantasma en el próximo arranque.

Efecto: el operador nuevo lo ve una vez; el existente NO lo ve solo, pero SIEMPRE puede abrirlo con el launcher "?", desde Configuración, o vía Ctrl+K. **Backward-compatible.** (Nota mono-operador: "first-run" es del NAVEGADOR/webview del único operador, no hay noción de usuario — coherente con el sustrato sin auth.)

### 4.6 Runtime parity + fallback de `localStorage`

100% presentación ⇒ idéntico en Codex/Claude/Copilot. `localStorage` está disponible en el webview/navegador de los 3. **Fallback declarado:** si `localStorage` lanza o no está (`try/catch`), el estado degrada a una variable **en memoria** (módulo `onboarding.ts`): el tour **se muestra igual**, pero el "visto" **no persiste** entre recargas (podría re-mostrarse en el próximo arranque). Es una degradación aceptable y no bloqueante. Sin `@testing-library/react` ni `jsdom` en el frontend (gap estructural confirmado — NO agregarlas en este plan), el gate de UI es `tsc --noEmit` + smoke manual; toda la lógica de decisión vive en helpers **puros testeables sin DOM**.

### 4.7 Anti-frágil (zonas calientes)

`App.tsx`, `TopBar.tsx`, `SettingsPage.tsx`, `CommandPalette.tsx` y `theme.css` son zonas calientes (planes 132/134/135/136/138-143/152). Reglas:
- **Pre-flight `git status --porcelain -- "<ruta>"` por archivo** antes de tocarlo. Si aparece WIP ajeno (sesión concurrente en la rama `plans-138-141-serie-ux-ui`) ⇒ **STOP y avisar**, no mezclar.
- **Anclas por TEXTO NORMATIVO** (este documento describe exactamente qué atributo agregar y a qué elemento; los `:NN` son orientativos).
- **Staging quirúrgico** (`git add -- "<ruta>"` explícito por archivo). **Quien implementa NO commitea**; lo hace el orquestador.

### 4.8 Coordinación con plan 152 (C6)

El plan 152 (Centro de notificaciones) inserta su campana en el MISMO slot `styles.actions` de `TopBar.tsx:202`. Regla de no-conflicto: ambos cambios son **aditivos** (cada uno agrega su propio elemento hijo, sin tocar los existentes). Orden visual sugerido dentro de `styles.actions`: `[HelpLauncher "?"] [Campana 152] [CostCapIndicator] [StreakBadge]` — pero el orden es estético y NO normativo; lo único normativo es que `HelpLauncher` viva dentro del div `styles.actions` y ninguno de los dos planes reordene/elimine hijos ajenos. Si 152 ya aterrizó al implementar 151 (o viceversa), el pre-flight de §4.7 detecta el estado real y el implementador agrega su elemento sin tocar el del otro.

---

## 5. Glosario

- **first-run real:** primer arranque de un operador que nunca usó la app (sin key `seen`, sin evidencia de uso previo).
- **operador existente:** ya tiene datos/uso previo; NO se le auto-muestra el tour.
- **launcher:** botón "?" persistente en la topbar que re-abre el tour on-demand.
- **auto-show:** el tour aparece solo, en first-run. Controlado por `shouldAutoShow`.
- **on-demand:** el tour aparece porque el operador lo pidió (launcher, Configuración o paleta Ctrl+K). Ignora el gate de first-run y **no toca `seen`** (C2).
- **step:** un paso del tour (título + cuerpo + target opcional + posición).
- **ancla `data-tour`:** atributo normativo en un contenedor estable al que un step apunta.
- **seen v1:** key `localStorage` `stacky_onboarding_seen_v1` = `"1"` cuando el operador cerró/terminó el tour.

---

## 6. Fases F0..F5 (+F4b)

> **Regla transversal de tests:** la lógica de decisión y navegación es **pura** (sin DOM) y se testea con vitest **por archivo** desde `frontend/` (C4). El componente React NO se testea con RTL (no existe en el repo); su gate es `tsc --noEmit` + smoke §9. Cada fase declara paridad de runtime (N/A salvo el fallback de `localStorage`, común a todas) y una línea "Trabajo del operador".

---

### F0 — Módulo puro de decisión + storage seguro (TEST-FIRST)

**Objetivo (1 frase):** centralizar TODA la lógica de "¿mostrar el tour?", migración y navegación de pasos en un módulo puro y testeable sin DOM.
**Valor:** el corazón del plan queda cubierto por tests deterministas; el componente React queda como cascarón fino.

**Archivos EXACTOS:**
- NUEVO: `Stacky Agents/frontend/src/services/onboarding.ts`
- NUEVO (test primero): `Stacky Agents/frontend/src/services/__tests__/onboarding.test.ts`

**Símbolos/keys EXACTOS (contrato congelado):**
```ts
// onboarding.ts
export const SEEN_KEY = "stacky_onboarding_seen_v1";
export const LEGACY_SEEN_KEY = "stacky-agents-tour-done"; // migración del prototipo — ÚNICO lugar del literal (KPI-3)
export const AUTOSHOW_PREF_KEY = "stacky:onboardingAutoShow"; // patrón preferences.ts

// C8 — señales de uso previo, extensible sin tocar la lógica.
// Cada entrada: key de localStorage cuyo valor JSON-array no vacío indica uso previo.
export const PRIOR_USE_SIGNAL_KEYS = ["stacky:pinnedAgents"] as const;

// Abstracción de storage inyectable (para testear sin DOM y para el fallback en memoria)
export interface StorageLike {
  getItem(k: string): string | null;
  setItem(k: string, v: string): void;
  removeItem(k: string): void;
}
// Devuelve localStorage envuelto en try/catch, o un Map en memoria si lanza/no existe.
export function safeStorage(): StorageLike;

// Señales de "uso previo" (operador existente). true si legacy key presente
// O alguna key de PRIOR_USE_SIGNAL_KEYS parsea a array no vacío. Heurística best-effort.
export function hasPriorUse(s: StorageLike): boolean;

export function isSeen(s: StorageLike): boolean;       // seen v1 == "1"
export function isAutoShowEnabled(s: StorageLike): boolean; // pref ausente => true (default ON)

// Decisión de AUTO-show (first-run). Pura.
export function shouldAutoShow(s: StorageLike): boolean;
//   true  sii  !isSeen && isAutoShowEnabled && !hasPriorUse

export function markSeen(s: StorageLike): void;        // setItem(SEEN_KEY, "1")
// C2: resetSeen NO se usa en ningún flujo de producción. Existe SOLO para tests
// y para el smoke manual (limpiar estado). Ningún componente/store la importa.
export function resetSeen(s: StorageLike): void;       // removeItem(SEEN_KEY)
export function setAutoShow(s: StorageLike, on: boolean): void;

// Migración: si legacy key presente => tratar como seen v1 (no re-mostrar al existente).
// Idempotente. NO borra la legacy key (solo la lee), pero SIEMPRE que exista => markSeen.
export function migrateLegacy(s: StorageLike): void;

// Navegación de pasos (pura). total = STEPS.length.
export function clampStep(i: number, total: number): number; // 0..total-1
export function nextStep(i: number, total: number): number;  // min(i+1, total-1)
export function prevStep(i: number): number;                  // max(i-1, 0)
export function isLastStep(i: number, total: number): boolean;
```

**Pseudocódigo con casos borde:**
```ts
export function safeStorage(): StorageLike {
  try {
    const t = "__stacky_probe__";
    localStorage.setItem(t, "1"); localStorage.removeItem(t);
    return localStorage;
  } catch {
    const mem = new Map<string, string>(); // fallback en memoria (no persiste)
    return {
      getItem: (k) => (mem.has(k) ? mem.get(k)! : null),
      setItem: (k, v) => { mem.set(k, v); },
      removeItem: (k) => { mem.delete(k); },
    };
  }
}
export function shouldAutoShow(s) {
  return !isSeen(s) && isAutoShowEnabled(s) && !hasPriorUse(s);
}
export function migrateLegacy(s) {
  try { if (s.getItem(LEGACY_SEEN_KEY) != null) markSeen(s); } catch { /* no-op */ }
}
export function hasPriorUse(s) {
  if (s.getItem(LEGACY_SEEN_KEY) != null) return true;
  for (const key of PRIOR_USE_SIGNAL_KEYS) {
    const raw = s.getItem(key);
    if (raw == null) continue;
    try { const v = JSON.parse(raw); if (Array.isArray(v) && v.length > 0) return true; }
    catch { /* malformado => no cuenta como señal */ }
  }
  return false;
}
```
Casos borde cubiertos: pref ausente ⇒ default ON; `pinnedAgents` = `"[]"` ⇒ no es uso previo; `pinnedAgents` malformado ⇒ `false` (no crashea); storage que lanza ⇒ fallback en memoria; `clampStep(-1)`⇒0; `nextStep(total-1)`⇒`total-1`; `prevStep(0)`⇒0.

**Tests PRIMERO — `onboarding.test.ts` (casos exactos):**
1. `shouldAutoShow`: storage vacío ⇒ `true`.
2. `shouldAutoShow`: `SEEN_KEY="1"` ⇒ `false`.
3. `shouldAutoShow`: pref `AUTOSHOW_PREF_KEY="false"` ⇒ `false`.
4. `shouldAutoShow`: `hasPriorUse` (legacy key presente) ⇒ `false`.
5. `shouldAutoShow`: `stacky:pinnedAgents='["a.agent.md"]'` ⇒ `false` (operador existente).
6. `shouldAutoShow`: `stacky:pinnedAgents='[]'` y todo lo demás vacío ⇒ `true`.
7. `migrateLegacy`: legacy presente ⇒ tras migrar, `isSeen==true` y `shouldAutoShow==false`; idempotente (2ª llamada no cambia nada).
8. `safeStorage`: con un mock que lanza en `setItem` ⇒ devuelve store en memoria funcional; `markSeen`+`isSeen` funcionan en memoria.
9. Navegación: `clampStep`, `nextStep`, `prevStep`, `isLastStep` en bordes (usar `total=6`).
10. `setAutoShow(false)` ⇒ `isAutoShowEnabled==false`; `resetSeen` ⇒ `isSeen==false`.
11. **(C8)** `hasPriorUse`: itera `PRIOR_USE_SIGNAL_KEYS` — con una key extra inyectada en la constante (test parametrizado sobre la lista real): array no vacío ⇒ `true`; malformado ⇒ `false`; garantiza que agregar señales futuras no exige tocar la lógica.
12. **(C2, invariante)** simular flujo on-demand: `markSeen` ⇒ (abrir on-demand NO llama resetSeen; no hay API que lo haga desde el store) ⇒ `isSeen` sigue `true` y `shouldAutoShow` sigue `false`.

(Los tests inyectan un `StorageLike` de mentira — Map-backed — así **no tocan el `localStorage` real ni el DOM**.)

**Criterio BINARIO + comando (C4):**
`cd "Stacky Agents/frontend"` y `npx vitest run src/services/__tests__/onboarding.test.ts` ⇒ **exit 0**, ≥12 casos verdes.

**Flag/default:** N/A (módulo). La preferencia `onboardingAutoShow` default ON se materializa aquí como "pref ausente ⇒ true".

**Impacto por runtime + fallback:** idéntico en los 3 (lógica pura). Fallback `localStorage` implementado en `safeStorage()`.

**Trabajo del operador:** ninguno.

---

### F1 — Datos de pasos (`STEPS`) + lista blanca de anclas (TEST-FIRST parcial)

**Objetivo (1 frase):** definir los 4-6 pasos como data pura y garantizar que cada `target` apunta a un ancla declarada (sin anclas huérfanas).
**Valor:** evita el bug del prototipo (anclas inexistentes) con un test que compara pasos contra anclas reales.

**Archivos EXACTOS:**
- NUEVO: `Stacky Agents/frontend/src/services/onboardingSteps.ts`
- Ampliar test: `Stacky Agents/frontend/src/services/__tests__/onboarding.test.ts` (mismo archivo; agrega `describe("stepAnchors")`).

**Símbolos EXACTOS:**
```ts
// onboardingSteps.ts
export type StepPosition = "center" | "right" | "bottom" | "left" | "top";
export interface TourStep {
  id: string;
  target: string | null;   // selector data-tour o null (card centrada)
  title: string;
  body: string;
  position: StepPosition;
}
// Anclas NORMATIVAS que F2 agrega al DOM (F2/F3 las declaran físicamente):
export const DECLARED_ANCHORS = ["nav", "topbar-actions", "help-launcher"] as const;

export const STEPS: TourStep[] = [
  { id: "welcome",  target: null,                          position: "center",
    title: "Bienvenido a Stacky Agents",
    body:  "Tu equipo de agentes IA para cerrar tickets más rápido. Te muestro el mapa en 5 pasos. Podés saltarlo cuando quieras (Esc)." },
  { id: "nav",      target: '[data-tour="nav"]',           position: "right",
    title: "El mapa: la navegación",
    body:  "Acá están todas las superficies: tu Equipo, Tickets, Configuración, Diagnóstico y más. Cada una es una capacidad distinta." },
  { id: "project",  target: '[data-tour="topbar-actions"]', position: "bottom",
    title: "Tu proyecto y estado",
    body:  "Arriba a la derecha ves el proyecto activo, la versión y si hay agentes trabajando. Cambiá de proyecto desde el selector de la izquierda." },
  { id: "palette",  target: null,                          position: "center",
    title: "Ctrl+K es tu atajo",
    body:  "Apretá Ctrl+K en cualquier momento para buscar tickets, agentes o saltar entre pantallas con el teclado." },
  { id: "help",     target: '[data-tour="help-launcher"]', position: "bottom",
    title: "¿Perdido? Este botón",
    body:  "Este “?” re-abre este tour cuando quieras. No molesta: solo aparece si lo pedís." },
  { id: "done",     target: null,                          position: "center",
    title: "Listo, explorá",
    body:  "Eso es todo. Nada de esto ejecuta acciones por vos: Stacky siempre te deja decidir. ¡A trabajar!" },
];
```
> Los `body`/`title` referencian solo elementos garantizados en first-run (nav, topbar, launcher) o conceptos (Ctrl+K). **No** se ancla a `ActiveRunsPanel` (condicional) ni a pestañas individuales (el 139 las reagrupa).

**Test (agregar al archivo de F0):**
- `stepAnchorsAreDeclared`: por cada `s of STEPS` con `s.target != null`, extraer el nombre de `[data-tour="X"]` y verificar que `X ∈ DECLARED_ANCHORS`. **0 huérfanas.**
- `stepsAreNonEmpty`: cada step tiene `title` y `body` no vacíos; `STEPS.length` entre 4 y 6.

**Criterio BINARIO + comando (C4):** `cd "Stacky Agents/frontend"` y `npx vitest run src/services/__tests__/onboarding.test.ts` ⇒ exit 0 con los casos nuevos.

**Flag/default:** N/A. **Impacto runtime:** idéntico (data pura). **Trabajo del operador:** ninguno.

---

### F2 — Anclas `data-tour` NORMATIVAS en contenedores estables

**Objetivo (1 frase):** agregar los atributos `data-tour="nav"` y `data-tour="topbar-actions"` a los contenedores estables (el `help-launcher` lo agrega F3).
**Valor:** los pasos apuntan a elementos que EXISTEN; additivo y sin cambio de comportamiento.

**Archivos EXACTOS (pre-flight `git status --porcelain --` por archivo — zona caliente):**
- `Stacky Agents/frontend/src/App.tsx`
- `Stacky Agents/frontend/src/components/TopBar.tsx`

**Cambios NORMATIVOS (por texto, no por línea):**
1. En `App.tsx`, al elemento `<nav className={styles.nav}>` que envuelve los botones `styles.navTab` (hoy `App.tsx:265`, orientativo), **agregar el atributo** `data-tour="nav"`:
   ```diff
   - <nav className={styles.nav}>
   + <nav className={styles.nav} data-tour="nav">
   ```
   (Solo se agrega el atributo; NO se cambia className, hijos ni lógica.)
2. En `TopBar.tsx`, al `<div className={styles.actions}>` (hoy `TopBar.tsx:202`, orientativo) **agregar** `data-tour="topbar-actions"`:
   ```diff
   - <div className={styles.actions}>
   + <div className={styles.actions} data-tour="topbar-actions">
   ```

**Casos borde:** ninguno funcional — son atributos `data-*` inertes. No afectan estilos, foco, ni tests existentes.

**CROSS-151/139 (nota de coordinación):** el plan 139 está IMPLEMENTADO con flag `STACKY_UI_SHELL_V2_ENABLED` default OFF. Regla: el `data-tour="nav"` va en el **contenedor de nav del layout DEFAULT** (la fila de tabs actual). Si el shell v2 está activo (flag ON) y monta OTRO contenedor de nav, el implementador agrega el MISMO atributo al contenedor de nav de la sidebar v2 (en su componente), de modo que **en cada layout renderizado exista exactamente un elemento con `data-tour="nav"`** (los dos layouts son mutuamente excluyentes en runtime ⇒ el `querySelector` nunca ve dos). El gate por grep de abajo admite 1 o 2 declaraciones estáticas por eso, pero el smoke §9 verifica que el layout vigente resalte su nav. F1 `stepAnchorsAreDeclared` no depende de qué layout esté vigente. Fallback §4.3 cubre cualquier hueco.

**Tests:** no hay test unitario de DOM (sin jsdom). Gate: `tsc --noEmit` (KPI-2) + smoke §9 (el paso "nav" resalta el contenedor real).

**Criterio BINARIO + comando (C4):** `cd "Stacky Agents/frontend"` y `npx tsc --noEmit` ⇒ exit 0. `grep -rn 'data-tour="nav"' "Stacky Agents/frontend/src"` ⇒ 1 (o 2 si el shell v2 tiene nav propio, ver CROSS-151/139; nunca 0). `grep -rn 'data-tour="topbar-actions"' "Stacky Agents/frontend/src"` ⇒ exactamente 1.

**Flag/default:** N/A. **Impacto runtime:** idéntico (atributos inertes). **Trabajo del operador:** ninguno.

---

### F3 — Componente `OnboardingTour` v2 + launcher "?" (reescritura del prototipo)

**Objetivo (1 frase):** reescribir `OnboardingTour.tsx` como componente accesible que consume F0/F1 + primitivas 138 + tokens de motion 143 + `--focus-ring` 141, y agregar el botón "?" en la topbar.
**Valor:** entrega el tour real (spotlight, prev/next/skip, Esc, foco) y el launcher re-abrible, al estándar de la serie.

**Archivos EXACTOS (pre-flight `git status --porcelain --`):**
- REESCRIBIR: `Stacky Agents/frontend/src/components/OnboardingTour.tsx`
- REESCRIBIR: `Stacky Agents/frontend/src/components/OnboardingTour.module.css`
- NUEVO: `Stacky Agents/frontend/src/store/onboardingStore.ts` (zustand — mismo patrón que `store/uiSectionsStore.ts`, que EXISTE; `zustand` ya es dependencia, `store/workbench.ts:1`)
- NUEVO: `Stacky Agents/frontend/src/components/HelpLauncher.tsx`
- `Stacky Agents/frontend/src/components/TopBar.tsx` (montar `<HelpLauncher />` dentro de `styles.actions`)

**Store compartido (contrato — C2 aplicado):**
```ts
// onboardingStore.ts  (zustand, mismo patrón que uiSectionsStore)
interface OnboardingState {
  open: boolean;
  requestOpenTour(): void;   // on-demand: SOLO open=true. NO toca `seen` (C2).
  closeTour(): void;         // markSeen(safeStorage()) + open=false (idempotente)
  setOpen(v: boolean): void; // usado por el auto-show de F5
}
```
> **C2 (regla dura):** `requestOpenTour` NO llama `resetSeen`. El "visto" solo transiciona a `seen` (nunca al revés) en producción; `resetSeen` es exclusivo de tests/smoke. Esto garantiza que re-abrir el tour y recargar a mitad NUNCA re-activa el auto-show. El auto-show inicial NO usa el store para decidir; usa `shouldAutoShow` en el effect de F5.

**`OnboardingTour.tsx` v2 (pseudocódigo con casos borde — C3 y C7 aplicados):**
```tsx
import { Card, Button } from "./ui";                        // primitivas 138 (barrel)
import { STEPS } from "../services/onboardingSteps";
import { nextStep, prevStep, isLastStep } from "../services/onboarding";
import { useOnboardingStore } from "../store/onboardingStore";
import styles from "./OnboardingTour.module.css";

export default function OnboardingTour() {
  const open = useOnboardingStore(s => s.open);
  const close = useOnboardingStore(s => s.closeTour);
  const [i, setI] = useState(0);
  const cardRef = useRef<HTMLDivElement>(null);             // ref al WRAPPER, no a Card (C3)

  // Reset al abrir + foco al wrapper + Esc = cerrar (saltar)
  useEffect(() => {
    if (!open) return;
    setI(0);
    cardRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      // C7: no interferir con inputs ni con la paleta — ignorar eventos de campos editables.
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if (e.key === "Escape") close();
      else if (e.key === "ArrowRight") setI(v => nextStep(v, STEPS.length));
      else if (e.key === "ArrowLeft")  setI(v => prevStep(v));
      // C7: sin preventDefault/stopPropagation — otros listeners (paleta) siguen funcionando.
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, close]);

  if (!open) return null;
  const step = STEPS[i];
  const rect = step.target ? safeRect(step.target) : null;  // querySelector protegido

  return createPortal(
    <div className={styles.root} role="dialog" aria-modal="true"
         aria-label="Tour de bienvenida de Stacky Agents">
      <div className={styles.backdrop} onClick={close} aria-hidden="true" />
      {rect && <div className={styles.spotlight} style={spotlightVars(rect)} aria-hidden="true" />}
      {/* C3: Card real NO acepta ref/tabIndex/data-* (Card.tsx:6-23, sin forwardRef).
          El wrapper focusable es un div del feature; Card va adentro sin props extra. */}
      <div ref={cardRef} tabIndex={-1}
           className={`${styles.cardWrap} ${styles[step.position]} ${rect ? "" : styles.centered}`}
           data-anchored={rect ? "1" : "0"}>
        <Card padding="md" elevated>
          <h3 className={styles.title}>{step.title}</h3>
          <p className={styles.body}>{step.body}</p>
          <div className={styles.footer}>
            <span className={styles.count}>{i + 1} / {STEPS.length}</span>
            <div className={styles.actions}>
              <Button variant="ghost" onClick={close}>Saltar</Button>
              {i > 0 && <Button variant="secondary" onClick={() => setI(prevStep(i))}>Anterior</Button>}
              <Button variant="primary"
                      onClick={() => isLastStep(i, STEPS.length) ? close() : setI(nextStep(i, STEPS.length))}>
                {isLastStep(i, STEPS.length) ? "Empezar" : "Siguiente"}
              </Button>
            </div>
          </div>
        </Card>
      </div>
    </div>,
    document.body
  );
}
```
Casos borde:
- `safeRect(sel)`: `try { el = document.querySelector(sel); return el?.getBoundingClientRect() ?? null } catch { return null }`. Ancla ausente ⇒ `rect=null` ⇒ card **centrada** (clase `.centered`), sin spotlight, sin crash (cubre §4.3).
- `spotlightVars(rect)`: setea CSS custom props `--r-top/left/w/h` para posicionar el recorte; el spotlight es un `div` con `box-shadow` grande (oscurece el resto) — **sin capturar clicks** (el backdrop maneja el dismiss). *(Nota ratchet 138: `style={{...}}` con custom props calculadas en runtime en un .tsx REESCRITO puede disparar `uiDebtRatchet` si el archivo cuenta como "nuevo" con alcance 0 inline-style — gotcha conocido. Alternativa OBLIGATORIA si el ratchet lo marca: setear las custom props imperativamente vía `ref` + `useEffect` (`el.style.setProperty("--r-top", ...)`), patrón ya validado en la serie 138-143.)*
- Recalcular `rect` en resize/scroll: escuchar `resize` (y recomputar) es opcional; si no, el spotlight queda estático hasta cambiar de paso — aceptable para v1 (documentado en §7 R6).

**Estilos `OnboardingTour.module.css` (reglas clave, solo tokens — sin hex nuevos):**
- Entrada/salida de la card con `transition: var(--transition-opacity), var(--transition-transform);` (tokens del 143, EXISTEN en `theme.css`). **NO** se escribe ninguna `@media (prefers-reduced-motion)` (la global del 141 F5 neutraliza estas transiciones automáticamente — §4/§3.4).
- Foco visible: el wrapper `.cardWrap` usa `:focus-visible { box-shadow: var(--focus-ring); }` (token del 141, EXISTE). Los `Button` del 138 ya traen su propio foco.
- `z-index` por encima de modales existentes pero **por debajo** de toasts críticos (usar la escala del 138 si existe token; si no, un literal aislado en el `.module.css` de este feature — permitido, no está bajo el ratchet de `components/ui/`).

**`HelpLauncher.tsx` (launcher "?"):**
```tsx
import { IconButton } from "./ui";
import { useOnboardingStore } from "../store/onboardingStore";
export default function HelpLauncher() {
  const requestOpen = useOnboardingStore(s => s.requestOpenTour);
  return (
    <IconButton aria-label="Ver tour de bienvenida" title="Ver tour de bienvenida"
                data-tour="help-launcher" onClick={requestOpen}>?</IconButton>
  );
}
```
> `IconButton` extiende `ButtonHTMLAttributes` (`IconButton.tsx:7`) ⇒ `data-tour`/`aria-label`/`onClick` pasan sin cambios a la primitiva. Sus variants son `ghost|secondary|danger` (NO `primary` — `IconButton.tsx:4`); se usa el default sin `variant`.

Montaje en `TopBar.tsx`: dentro de `<div className={styles.actions} data-tour="topbar-actions">` (de F2), agregar `<HelpLauncher />` **antes** de `<CostCapIndicator .../>` o al final del bloque (elección estética; ver regla de no-conflicto con la campana del 152 en §4.8). El atributo `data-tour="help-launcher"` va en el propio IconButton, cumpliendo el ancla del step "help".

**Tests:** sin RTL. La lógica (next/prev/last) ya está cubierta por F0. Gate del componente: `tsc --noEmit` (KPI-2) + smoke §9.

**Criterio BINARIO + comando (C1/C4):**
- `cd "Stacky Agents/frontend"` y `npx tsc --noEmit` ⇒ exit 0.
- `grep -rn 'data-tour="help-launcher"' "Stacky Agents/frontend/src"` ⇒ exactamente 1.
- `grep -rn "stacky-agents-tour-done" "Stacky Agents/frontend/src/components"` ⇒ **0 líneas** (la key vieja ya no vive en ningún componente; su único hogar es `services/onboarding.ts`).

**Flag/default:** el componente se monta siempre; la decisión de mostrarse (auto vs on-demand) la maneja el store + el effect de F5. El launcher está SIEMPRE disponible (KPI-6).
**Impacto runtime:** idéntico (los 3 renderizan React igual). Fallback `localStorage` heredado de F0 (`closeTour` usa `safeStorage()`).
**Trabajo del operador:** ninguno; gana el botón "?" para re-ver.

---

### F4 — Toggle en Configuración (config por UI)

**Objetivo (1 frase):** exponer en Configuración un control para (a) activar/desactivar el auto-show en first-run y (b) re-ver el tour ahora.
**Valor:** cumple la regla dura de la casa (toda config del operador tocable por UI) y da control al operador existente.

**Archivos EXACTOS (pre-flight `git status --porcelain --`):**
- `Stacky Agents/frontend/src/pages/SettingsPage.tsx` (agregar controles en el panel del sub-tab `"sections"` — el tipo `SubTab` real hoy es `"flow" | "sections" | "client-profile" | "transfer" | "webhooks" | "notifications" | "harness" | "playground" | "appearance"`, `SettingsPage.tsx:28`; el panel se renderiza en `SettingsPage.tsx:172`, orientativo).

**Cambios NORMATIVOS:**
- Dentro del panel de secciones (o un bloque nuevo "Onboarding" en el mismo sub-tab `"sections"`), agregar:
  1. Un checkbox/toggle "Mostrar el tour de bienvenida en el primer arranque" ligado a `isAutoShowEnabled(safeStorage())` / `setAutoShow(safeStorage(), v)`.
  2. Un botón "Re-ver tour ahora" que llama `useOnboardingStore.getState().requestOpenTour()` (que por C2 NO toca `seen`).
- Reusar los estilos de toggle ya presentes (`styles.toggle`, `styles.toggleSlider` — `SettingsPage.tsx:77-84`, orientativo) para no introducir CSS nuevo.

**Casos borde:** si `localStorage` está en fallback memoria, el toggle funciona pero no persiste entre recargas (consistente con §4.6; opcionalmente mostrar un hint discreto). El botón "Re-ver" funciona siempre (usa el store en memoria).

**Tests:** la lógica `setAutoShow`/`isAutoShowEnabled` ya está en F0. Gate UI: `tsc --noEmit` + smoke §9.

**Criterio BINARIO + comando (C4):** `cd "Stacky Agents/frontend"` y `npx tsc --noEmit` ⇒ exit 0. Smoke §9 paso 5: apagar el toggle ⇒ borrar `seen` (DevTools) ⇒ recargar ⇒ el tour NO aparece solo; prender el toggle ⇒ borrar `seen` ⇒ recargar ⇒ aparece.

**Flag/default:** la preferencia default ON (F0). **Impacto runtime:** idéntico. **Trabajo del operador:** ninguno obligatorio; gana control fino.

---

### F4b — [ADICIÓN ARQUITECTO] Comando "Ver tour de bienvenida" en la paleta Ctrl+K (reuso plan 129)

**Objetivo (1 frase):** registrar el tour como comando estático de la paleta global (plan 129, IMPLEMENTADA) para descubribilidad doble con costo ~10 líneas.
**Valor:** el punto de entrada "ayuda" queda donde el operador ya busca todo (Ctrl+K); coherente con el step "palette" del propio tour (el tour enseña Ctrl+K, y Ctrl+K sabe abrir el tour). Reuso puro de infra existente, cero backend, cero dependencia nueva.

**Archivo EXACTO (pre-flight `git status --porcelain --` — zona caliente):**
- `Stacky Agents/frontend/src/components/CommandPalette.tsx`

**Cambio NORMATIVO (por texto):** en el bloque de comandos estáticos de `allCommands` (`CommandPalette.tsx:89-132`, orientativo — el `commands.push(...)` que hoy registra `nav-team`, `nav-tickets`, `nav-settings`, `nav-diagnostics`, `nav-pm`, `nav-logs`), agregar UNA entrada más con la MISMA forma `Command` existente:
```ts
{
  id: "nav-help-tour",
  kind: "nav",
  icon: "❓",
  label: "Ver tour de bienvenida",
  run: () => useOnboardingStore.getState().requestOpenTour(),
},
```
con el import `import { useOnboardingStore } from "../store/onboardingStore";` arriba del archivo. No se toca ninguna otra entrada ni la lógica de filtrado/render.

**Casos borde:** la paleta se cierra sola al ejecutar un comando (comportamiento existente de `run`); el tour se abre encima — sin conflicto de teclado por C7 (el listener del tour ignora inputs y no hace preventDefault). Human-in-the-loop intacto: el comando solo ABRE el tour (§4.1).

**Criterio BINARIO + comando:** `cd "Stacky Agents/frontend"` y `npx tsc --noEmit` ⇒ exit 0. `grep -rn "nav-help-tour" "Stacky Agents/frontend/src/components/CommandPalette.tsx"` ⇒ exactamente 1 (KPI-7). Smoke §9 paso 8.

**Flag/default:** N/A (la entrada existe siempre, como el resto de comandos nav). **Impacto runtime:** idéntico. **Trabajo del operador:** ninguno; gana un segundo punto de entrada.

---

### F5 — Wire en `App.tsx`, migración y first-run gate (cierre)

**Objetivo (1 frase):** conectar el auto-show real (solo first-run) y migrar la key vieja, sin romper backward-compat.
**Valor:** el operador nuevo ve el tour una vez; el existente no; la key vieja no re-molesta.

**Archivos EXACTOS (pre-flight `git status --porcelain --` — zona caliente `App.tsx`):**
- `Stacky Agents/frontend/src/App.tsx`

**Cambios NORMATIVOS:**
1. `App.tsx` ya monta `<OnboardingTour />` (hoy `App.tsx:396`, orientativo). Se **mantiene** el montaje (el componente decide con el store).
2. Agregar un `useEffect` de arranque (junto a los `initPreferences()` / `initUiSections()` ya existentes — `App.tsx:120-121`, orientativo) que:
   ```ts
   useEffect(() => {
     const s = safeStorage();
     migrateLegacy(s);                 // operador que cerró el prototipo => no re-mostrar
     if (shouldAutoShow(s)) {
       useOnboardingStore.getState().setOpen(true);
     }
   }, []);
   ```
   > Este effect NO llama `resetSeen` (C2: nada en producción la llama). El auto-show abre el tour; al cerrarlo, `closeTour` marca `seen`, y no vuelve a auto-aparecer.
3. Verificar que el import viejo `import OnboardingTour from "./components/OnboardingTour"` (`App.tsx:22`, orientativo) siga válido (mismo path; el componente fue reescrito, no movido).

**Casos borde:**
- Operador existente con la key vieja: `migrateLegacy` ⇒ `seen`; `shouldAutoShow` ⇒ `false`. No lo ve. ✔
- Operador existente sin key vieja pero con `pinnedAgents`: `hasPriorUse` ⇒ `true`; no lo ve. ✔
- First-run real: `shouldAutoShow` ⇒ `true`; se abre una vez. ✔
- Re-abrió on-demand y recargó a mitad: `seen` intacto (C2) ⇒ no auto-aparece. ✔
- `localStorage` deshabilitado: `safeStorage` en memoria; el tour se muestra pero no persiste (degradación aceptable §4.6). ✔

**Tests:** la decisión (`migrateLegacy`, `shouldAutoShow`) está cubierta por F0 con storage inyectado. El wire en `App.tsx` no tiene test unitario (sin jsdom); gate `tsc --noEmit` + smoke §9.

**Criterio BINARIO + comando (C1/C4):**
- `cd "Stacky Agents/frontend"` y `npx vitest run src/services/__tests__/onboarding.test.ts` ⇒ exit 0 (regresión completa de F0/F1).
- `cd "Stacky Agents/frontend"` y `npx tsc --noEmit` ⇒ exit 0.
- `grep -rn "stacky-agents-tour-done" "Stacky Agents/frontend/src" | grep -v "services/onboarding.ts"` ⇒ **0 líneas** (KPI-3, comando exacto).

**Flag/default:** preferencia default ON (§4.4). **Impacto runtime:** idéntico; fallback `localStorage` en `safeStorage`. **Trabajo del operador:** ninguno.

---

## 7. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|--------|------------|
| R1 | El plan 139 (flag OFF) reagrupa la nav si el operador lo activa ⇒ el ancla `data-tour="nav"` podría quedar en un contenedor no montado. | F2/CROSS-151/139: el atributo va en el contenedor de nav de CADA layout (mutuamente excluyentes en runtime). Fallback §4.3: si falta, card centrada (no crashea). Test F1 no depende del layout. |
| R2 | `localStorage` deshabilitado (webview restringido) ⇒ throw. | `safeStorage()` con probe + fallback en memoria (F0). Todo el módulo usa la abstracción. |
| R3 | Molestar al operador existente. | `shouldAutoShow` con `hasPriorUse` (señales extensibles `PRIOR_USE_SIGNAL_KEYS`, C8) + `migrateLegacy` (F0/F5) + invariante C2 (on-demand nunca borra `seen`). Solo first-run real. |
| R4 | Zona caliente `App.tsx`/`TopBar.tsx`/`CommandPalette.tsx` con sesión concurrente en la rama. | Pre-flight `git status --porcelain --` por archivo; STOP ante WIP ajeno; staging quirúrgico; anclas por texto normativo (§4.7). |
| R5 | Ratchet uiDebtRatchet (138): archivo REESCRITO puede contar como "nuevo" con alcance 0 inline-style, y `style={spotlightVars(rect)}` es inline-style. | Plan A: custom props vía `style` solo si el ratchet no lo marca. Plan B OBLIGATORIO si marca: `ref` + `useEffect` con `el.style.setProperty(...)` (patrón validado en la serie, gotcha conocido). Los demás estilos van 100% en el `.module.css` con tokens. |
| R6 | Spotlight desalineado tras scroll/resize. | v1: recomputa `rect` al cambiar de paso; scroll/resize continuo queda fuera de scope (§8). Aceptable: la card sigue legible; el spotlight es decorativo. |
| R7 | Doble fuente de verdad del "flag" (harness vs frontend). | Decisión explícita §4.4: NO hay flag del arnés; preferencia frontend única. Evita drift `harness_defaults.env`. |
| R8 | Colisión de teclado con la paleta Ctrl+K u otros listeners globales (C7). | El listener del tour ignora eventos de `input`/`textarea`/`contenteditable` y NO hace `preventDefault`/`stopPropagation`; solo reacciona a Esc/flechas. Smoke §9 paso 8 lo verifica con la paleta. |
| R9 | Colisión de slot en TopBar con la campana del plan 152 (C6). | §4.8: ambos aditivos, ninguno reordena/borra hijos ajenos; pre-flight detecta el estado real del archivo. |

---

## 8. Fuera de scope

- Backend: **nada**. Sin endpoints, sin flag del arnés, sin `config.py`.
- Recalcular el spotlight en scroll/resize continuo (solo al cambiar de paso en v1).
- Tours contextuales por-pantalla o tooltips permanentes (esto es un tour de bienvenida global).
- Telemetría de "cuántos pasos completó" (no hay superficie de métricas para esto y agregaría trabajo).
- Internacionalización (la app es español; el tour también).
- Tests con `@testing-library/react`/`jsdom` (no existen en el repo; el gate es `tsc` + smoke — §4.6). NO agregarlas en este plan.
- Modificar las primitivas de `components/ui/` (p.ej. hacer `Card` forwardRef): contrato congelado del 138; el wrapper de F3 lo hace innecesario (C3).

---

## 9. Orden de implementación + Definition of Done

**Orden (dependencias):** F0 → F1 → F2 → F3 → F4 → F4b → F5. (F0/F1 son pura lógica y datos; F2 agrega anclas; F3 el componente+launcher+store; F4 la config; F4b la paleta — necesita el store de F3; F5 el wire final.)

**Smoke manual (§9, obligatorio antes de dar por hecho — no hay RTL):**
1. Limpiar `localStorage` (o usar perfil nuevo del webview) ⇒ recargar ⇒ **el tour aparece** en el paso 1.
2. Recorrer con "Siguiente"/"Anterior"/flechas; verificar que el paso "nav" **resalta el contenedor de navegación real** y "help" resalta el "?".
3. "Saltar" / Esc / click en backdrop ⇒ cierra; recargar ⇒ **no reaparece** (seen persistido).
4. Click en "?" de la topbar ⇒ **reabre** el tour on-demand; **recargar a mitad del tour re-abierto ⇒ NO auto-aparece** (invariante C2).
5. Configuración → apagar "Mostrar tour en primer arranque" → limpiar `seen` (DevTools) → recargar ⇒ **no auto-aparece**; "Re-ver tour ahora" ⇒ aparece.
6. Simular operador existente: setear `stacky:pinnedAgents='["x.agent.md"]'` con `seen` ausente ⇒ recargar ⇒ **no auto-aparece**.
7. Simular `localStorage` deshabilitado (DevTools) ⇒ el tour se muestra igual, sin errores en consola.
8. **(F4b)** Ctrl+K ⇒ tipear "tour" ⇒ aparece "Ver tour de bienvenida" ⇒ Enter ⇒ el tour se abre; Esc cierra el tour sin romper la paleta.

**DoD (todo verde):**
- [ ] KPI-1: `cd "Stacky Agents/frontend"` y `npx vitest run src/services/__tests__/onboarding.test.ts` exit 0 (≥14 casos con F0+F1).
- [ ] KPI-2: `cd "Stacky Agents/frontend"` y `npx tsc --noEmit` exit 0.
- [ ] KPI-3: `grep -rn "stacky-agents-tour-done" "Stacky Agents/frontend/src" | grep -v "services/onboarding.ts"` ⇒ 0 líneas (comando exacto, C1).
- [ ] KPI-4: 0 anclas huérfanas (test `stepAnchorsAreDeclared`).
- [ ] KPI-5: `shouldAutoShow` respeta operador existente (tests F0, incl. señales C8 e invariante C2).
- [ ] KPI-6: launcher "?" presente (`grep 'data-tour="help-launcher"'` ⇒ 1).
- [ ] KPI-7: comando de paleta presente (`grep "nav-help-tour"` en `CommandPalette.tsx` ⇒ 1).
- [ ] Smoke §9 pasos 1-8 OK.
- [ ] `npx vitest run src/__tests__/uiDebtRatchet.test.ts` exit 0 (desde `frontend/` — el tour reescrito no agrega deuda; ver R5).
- [ ] `git status --porcelain --` limpio de WIP ajeno en `App.tsx`/`TopBar.tsx`/`SettingsPage.tsx`/`CommandPalette.tsx`; staging quirúrgico. (El orquestador commitea.)

---

## 10. Nota de paridad (resumen por runtime)

| Fase | Codex | Claude Code | Copilot | Fallback |
|------|-------|-------------|---------|----------|
| F0 lógica pura | ✔ idéntico | ✔ | ✔ | `safeStorage()` en memoria si `localStorage` lanza |
| F1 data/steps | ✔ | ✔ | ✔ | N/A (data pura) |
| F2 anclas | ✔ | ✔ | ✔ | atributos inertes |
| F3 componente+launcher | ✔ (React) | ✔ | ✔ | card centrada si falta ancla |
| F4 config UI | ✔ | ✔ | ✔ | toggle no persiste sin `localStorage` |
| F4b paleta | ✔ | ✔ | ✔ | N/A (reuso de la paleta existente) |
| F5 wire+migración | ✔ | ✔ | ✔ | tour se muestra sin persistir "visto" |

Toda la superficie es presentación en el webview; los 3 runtimes renderizan React y exponen `localStorage` igual ⇒ paridad 100%.
