# Plan 151 — Onboarding / first-run guiado (mapa de capacidades) + launcher de ayuda

> **Estado:** PROPUESTO v1
> **Autor:** StackyArchitectaUltraEficientCode
> **Fecha:** 2026-07-15
> **Depende de:** plan 138 v2 (tokens `--duration-*`/`--ease-*`/`--focus-ring` + primitivas `components/ui/`: `Card`, `Button`, `IconButton`) · plan 139 v? (App Shell v2 — reagrupa la navegación; el tour ancla a su contenedor de nav) · plan 141 v3 (dueño único de `prefers-reduced-motion` + `:focus-visible`; CONSUMIDO, no reimplementado) · plan 143 v3 (tokens de transición `--transition-opacity`/`--transition-transform`; CONSUMIDO) · plan 129 (paleta global Ctrl+K, IMPLEMENTADA — el tour la señala).
> **Serie:** UX/UI (138 → 139 → 140 → 141 → 143 → **151**). Se implementa DESPUÉS de 138-143 (consume sus contratos) y después de la serie 132-136.
> **Runtimes:** 100% frontend/presentación ⇒ idéntico en Codex / Claude Code / GitHub Copilot Pro. Única dependencia de plataforma: `localStorage` del webview (con fallback declarado).
> **Flag:** default **ON** — pero NO es una flag del arnés backend (ver §4.4). Es una **preferencia de frontend** (`onboardingAutoShow`, default `true`), togglable desde la UI (Configuración). El estado "ya lo vi" vive en `localStorage`.

---

## 0. Changelog de versiones

- **v1 (2026-07-15):** versión inicial. Reemplaza el prototipo existente `OnboardingTour.tsx` (ver §3, hallazgo por grep) por una implementación al estándar de la serie: launcher re-abrible, flag por preferencia (config por UI), primitivas del 138, movimiento del 143, accesibilidad del 141, fallback de `localStorage`, y **lógica pura testeable sin DOM**.

---

## 1. Resumen ejecutivo

Un operador nuevo (o que actualiza a una versión con superficies nuevas) cae en una app con ~14 pestañas y varias capacidades ocultas (paleta Ctrl+K, panel de runs, config del arnés) y **no sabe dónde está cada cosa**. Este plan entrega un **tour de bienvenida pasivo, dismissible y saltable** que resalta 4-6 zonas clave, se muestra **solo en first-run real**, y deja un **launcher "?"** en la topbar para re-verlo cuando el operador quiera. No agrega ningún paso obligatorio, nunca actúa por el operador, y no molesta al operador existente.

**Punto crítico (hallazgo por grep):** ya existe un prototipo `OnboardingTour.tsx`, pero está **roto e incompleto** (anclas inexistentes, sin spotlight real, sin launcher, sin flag, sin a11y, `localStorage` sin protección). Este plan lo **eleva al estándar de la serie**, no lo duplica.

---

## 2. Objetivo + KPIs BINARIOS

**Objetivo:** que un operador en su primer arranque entienda en < 60 s el mapa de capacidades de la app, sin fricción y sin acciones automáticas, y pueda re-ver el tour on-demand desde la UI.

**KPIs (todos binarios, verificables por comando):**

- **KPI-1 (lógica pura):** `npx vitest run "Stacky Agents/frontend/src/services/__tests__/onboarding.test.ts"` termina **exit 0** y cubre: first-run vs operador existente, migración de la key vieja, fallback sin `localStorage`, y navegación de pasos (next/prev/clamp). Ver F0.
- **KPI-2 (tipos):** `npx tsc --noEmit -p "Stacky Agents/frontend/tsconfig.json"` termina **exit 0** con todos los cambios (el gate real de UI de la casa, dado que NO hay `@testing-library/react` ni `jsdom` — ver §4.6).
- **KPI-3 (no duplicación):** `grep -rn "stacky-agents-tour-done" "Stacky Agents/frontend/src"` devuelve **0 líneas** tras F5 (la key vieja quedó solo como origen de migración dentro de `onboarding.ts`, con el literal encapsulado en una constante `LEGACY_SEEN_KEY`, y no como key activa). El componente viejo con anclas inexistentes ya no existe.
- **KPI-4 (anclas reales):** para cada `target` de `STEPS` que sea un selector `data-tour`, existe **exactamente** ese atributo en el árbol de la app (verificado por el test de F1 `stepAnchorsAreDeclared`, que compara `STEPS` contra la lista blanca de anclas declaradas). 0 anclas huérfanas.
- **KPI-5 (no auto-show para el existente):** el helper puro `shouldAutoShow(env)` devuelve `false` cuando hay evidencia de uso previo (key vieja presente, o `seen v1` presente, o preferencia OFF). Cubierto por F0.
- **KPI-6 (launcher siempre disponible):** existe un botón "?" en la topbar (`data-tour="help-launcher"`) que llama `requestOpenTour()` sin condiciones de first-run. Verificado por `tsc` + smoke §9.

---

## 3. Por qué ahora / gap (evidencia por grep)

### 3.1 Ya existe un prototipo, pero está roto (NO duplicar — reemplazar)

`grep -rn "onboarding\|Onboarding\|tour" "Stacky Agents/frontend/src"` encuentra `components/OnboardingTour.tsx`, importado y montado en `App.tsx:20` y `App.tsx:296`.

Evidencia de que el prototipo NO cumple el estándar de la serie:

- **Anclas inexistentes.** `grep -rn "data-tour" "Stacky Agents/frontend/src"` devuelve **solo 4 líneas, todas dentro del propio `OnboardingTour.tsx`** (`OnboardingTour.tsx:26,32,38,44` — targets `agents`, `tickets`, `editor`, `run`). Ningún otro archivo declara esos `data-tour`: los pasos apuntan a elementos que **no existen**.
- **Sin spotlight real.** El comentario de cabecera (`OnboardingTour.tsx:2-3`) promete "spotlight (outline) sobre los componentes clave", pero el componente **nunca hace `querySelector` ni lee `getBoundingClientRect`**: solo renderiza una card posicionada por clase CSS (`OnboardingTour.tsx:83-101`). El `target` es data muerta.
- **Sin launcher.** No hay forma de re-ver el tour: una vez seteada la key, desaparece para siempre.
- **`localStorage` sin protección.** `OnboardingTour.tsx:61,72,79` llaman `localStorage.getItem/setItem` **sin try/catch**. En un webview con storage deshabilitado/particular esto **lanza** y puede romper el render.
- **Sin flag / sin config por UI**, **sin `prev`** (solo `next`+`skip`), **sin reduced-motion**, **sin primitivas del 138** (usa su propio `OnboardingTour.module.css`).
- **Key vieja** `stacky-agents-tour-done` (`OnboardingTour.tsx:9`), no versionada.

**Conclusión:** el gap es real. El plan 151 **reemplaza** este prototipo por una implementación correcta, y **migra** su key para no re-mostrar el tour a quien ya lo cerró.

### 3.2 La navegación real es densa (14 superficies)

`App.tsx:33` declara el tipo `Tab` con 14 valores: `team | tickets | review | unblocker | pm | logs | settings | docs | memory | diagnostics | history | migrador | devops | dbcompare`. `App.tsx:150-269` las renderiza como fila de botones `styles.navTab`, varias gated por `sections.*` / `*Enabled`. El plan 139 reagrupa esta fila en una sidebar; por eso el tour ancla al **contenedor de nav** (no a pestañas individuales) y degrada con gracia si una pestaña no está montada (ver §4.3 y CROSS-151/139).

### 3.3 Capacidades ocultas que el operador nuevo no descubre solo

- **Paleta Ctrl+K** (plan 129, IMPLEMENTADA): `App.tsx:18` importa `CommandPalette`, `App.tsx:286-290` la monta con `paletteOpen`. No tiene trigger visible ⇒ un nuevo operador no la descubre.
- **Panel de runs activos** (`App.tsx:24,305` `ActiveRunsPanel`): solo aparece cuando hay runs ⇒ no está garantizado en first-run (por eso NO se ancla a él; ver §4.3).
- **Topbar / selector de proyecto**: `TopBar.tsx:166-200` (proyecto) y `TopBar.tsx:201-213` (`styles.actions`: badges + versión) — ancla estable garantizada en first-run.

### 3.4 Contratos que el plan CONSUME (verificados por grep)

- **Primitivas 138:** `138_PLAN_*.md:709-716` congela 8 primitivas en `components/ui/` con barrel `index.ts`; entre ellas `Button`, `IconButton`, `Card`. El tour las CONSUME (es un componente feature, no una primitiva ⇒ NO cae bajo el ratchet de deuda de `components/ui/` — `138_PLAN_*.md:346`).
- **Motion 143:** `143_PLAN_*.md:249-254` define `--transition-opacity`, `--transition-transform`; `143_PLAN_*.md:8-9` declara que 143 CONSUME el `prefers-reduced-motion` del 141 y no lo redefine. El tour usa esos tokens para su entrada/salida.
- **A11y 141:** `141_PLAN_*.md:1219` (F5) es el **único** dueño de la regla global `@media (prefers-reduced-motion: reduce)` y de `:focus-visible`; `141_PLAN_*.md:688,807` define `--focus-ring`. El tour NO escribe ninguna regla `@media (prefers-reduced-motion)` (la global del 141 neutraliza sus transiciones automáticamente).

---

## 4. Principios y guardarraíles

### 4.1 Human-in-the-loop DURO

El tour es **pasivo e informativo**: solo señala dónde están las cosas. **Nunca** navega, publica, crea, ejecuta ni cambia estado del operador. Los únicos efectos son: (a) escribir la key `seen` en `localStorage` al cerrarlo, y (b) mover el índice de paso. No dispara ninguna acción de negocio ni toca la paleta/nav por el usuario (solo la *señala*; si el paso menciona Ctrl+K, es texto, el operador decide apretarlo).

### 4.2 Cero trabajo extra al operador

El tour **ayuda, no agrega pasos obligatorios**: es saltable en cualquier momento (Esc, botón "Saltar", click en el backdrop). No bloquea el uso de la app (backdrop no captura interacción destructiva; ver F2). El operador existente **no lo ve solo** (§4.5).

### 4.3 Anclas robustas (no frágiles) + degradación

Los pasos apuntan a **contenedores estables** vía atributos `data-tour` NORMATIVOS que este plan agrega (F1): `nav`, `topbar-actions`, `help-launcher`. Reglas:

- Si el elemento ancla **no está en el DOM** al abrir el paso, el paso degrada a **card centrada sin spotlight** (nunca crashea).
- Pasos "conceptuales" (bienvenida, Ctrl+K, cierre) son card centrada por diseño (target `null`).
- El anclaje se resuelve con `document.querySelector` protegido; el componente NO asume que el ancla exista.

### 4.4 Flag: default ON, pero como PREFERENCIA de frontend (NO flag del arnés)

Esta feature es **100% frontend sin superficie backend**. Introducir una flag del arnés (`FlagSpec` + `config.py` + `_CURATED_DEFAULTS_ON`) sería **sobre-ingeniería**: ningún code path backend la leería y no hay divergencia de runtime más allá de `localStorage`. Por eso el "flag default ON" se materializa como:

- **Preferencia `onboardingAutoShow`** (default `true`), guardada con el patrón `read/write` de `services/preferences.ts` (localStorage con try/catch — `preferences.ts:15-30`). Togglable desde Configuración (F4). Regla de la casa cumplida: **toda config del operador es tocable por UI**.

**Confirmación de que ninguna de las 4 excepciones duras aplica** (⇒ default ON es correcto):
1. **No bypasea revisión humana:** el tour no publica ni ejecuta nada.
2. **No es destructivo:** solo escribe una key booleana en `localStorage`.
3. **`localStorage` es prerequisito garantizado** en los 3 webviews; y aun así hay **fallback en memoria** (§4.6). No hay pérdida de datos.
4. **No reduce seguridad:** no toca auth, red, ni secretos.

### 4.5 No molestar al operador existente (detección de first-run real)

`shouldAutoShow(env)` (helper puro, F0) devuelve `true` **solo si**:
- la key `seen v1` (`stacky_onboarding_seen_v1`) está **ausente**, **y**
- la preferencia `onboardingAutoShow` es `true` (o ausente ⇒ default `true`), **y**
- **no hay evidencia de uso previo** (operador existente): key vieja `stacky-agents-tour-done` presente **o** cualquier señal de uso previo (p.ej. `stacky:pinnedAgents` no vacío — `preferences.ts:4`).

Efecto: el operador nuevo lo ve una vez; el existente NO lo ve solo, pero SIEMPRE puede abrirlo con el launcher "?" o desde Configuración. **Backward-compatible.**

### 4.6 Runtime parity + fallback de `localStorage`

100% presentación ⇒ idéntico en Codex/Claude/Copilot. `localStorage` está disponible en el webview/navegador de los 3. **Fallback declarado:** si `localStorage` lanza o no está (`try/catch`), el estado degrada a una variable **en memoria** (módulo `onboarding.ts`): el tour **se muestra igual**, pero el "visto" **no persiste** entre recargas (podría re-mostrarse en el próximo arranque). Es una degradación aceptable y no bloqueante. Sin `@testing-library/react` ni `jsdom` en el frontend (gap estructural confirmado), el gate de UI es `tsc --noEmit` + smoke manual; toda la lógica de decisión vive en helpers **puros testeables sin DOM**.

### 4.7 Anti-frágil (zonas calientes)

`App.tsx`, `main.tsx`, `theme.css` y la topbar son zonas calientes (planes 132/134/135/136/138-143). Reglas:
- **Pre-flight `git status -- "<ruta>"` por archivo** antes de tocarlo. Si aparece WIP ajeno (sesión concurrente en la rama `plans-138-141-serie-ux-ui`) ⇒ **STOP y avisar**, no mezclar.
- **Anclas por TEXTO NORMATIVO** (este documento describe exactamente qué atributo agregar y a qué elemento), no por número de línea.
- **Staging quirúrgico** (`git add -- "<ruta>"` explícito por archivo). **Quien implementa NO commitea**; lo hace el orquestador.

---

## 5. Glosario

- **first-run real:** primer arranque de un operador que nunca usó la app (sin key `seen`, sin evidencia de uso previo).
- **operador existente:** ya tiene datos/uso previo; NO se le auto-muestra el tour.
- **launcher:** botón "?" persistente en la topbar que re-abre el tour on-demand.
- **auto-show:** el tour aparece solo, en first-run. Controlado por `shouldAutoShow`.
- **on-demand:** el tour aparece porque el operador lo pidió (launcher o Configuración). Ignora el gate de first-run.
- **step:** un paso del tour (título + cuerpo + target opcional + posición).
- **ancla `data-tour`:** atributo normativo en un contenedor estable al que un step apunta.
- **seen v1:** key `localStorage` `stacky_onboarding_seen_v1` = `"1"` cuando el operador cerró/terminó el tour.

---

## 6. Fases F0..F5

> **Regla transversal de tests:** la lógica de decisión y navegación es **pura** (sin DOM) y se testea con vitest. El componente React NO se testea con RTL (no existe en el repo); su gate es `tsc --noEmit` + smoke §9. Cada fase declara paridad de runtime (N/A salvo el fallback de `localStorage`, común a todas) y una línea "Trabajo del operador".

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
export const LEGACY_SEEN_KEY = "stacky-agents-tour-done"; // migración del prototipo
export const AUTOSHOW_PREF_KEY = "stacky:onboardingAutoShow"; // patrón preferences.ts

// Abstracción de storage inyectable (para testear sin DOM y para el fallback en memoria)
export interface StorageLike {
  getItem(k: string): string | null;
  setItem(k: string, v: string): void;
  removeItem(k: string): void;
}
// Devuelve localStorage envuelto en try/catch, o un Map en memoria si lanza/no existe.
export function safeStorage(): StorageLike;

// Señales de "uso previo" (operador existente). priorUsePresent==true si alguna existe.
export function hasPriorUse(s: StorageLike): boolean; // legacy key OR stacky:pinnedAgents no vacío

export function isSeen(s: StorageLike): boolean;       // seen v1 == "1"
export function isAutoShowEnabled(s: StorageLike): boolean; // pref ausente => true (default ON)

// Decisión de AUTO-show (first-run). Pura.
export function shouldAutoShow(s: StorageLike): boolean;
//   true  sii  !isSeen && isAutoShowEnabled && !hasPriorUse

export function markSeen(s: StorageLike): void;        // setItem(SEEN_KEY, "1")
export function resetSeen(s: StorageLike): void;       // removeItem(SEEN_KEY) — para "re-ver"
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
  const pinned = s.getItem("stacky:pinnedAgents");
  try { return Array.isArray(JSON.parse(pinned ?? "[]")) && JSON.parse(pinned!).length > 0; }
  catch { return false; }
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

(Los tests inyectan un `StorageLike` de mentira — Map-backed — así **no tocan el `localStorage` real ni el DOM**.)

**Criterio BINARIO + comando:**
`npx vitest run "Stacky Agents/frontend/src/services/__tests__/onboarding.test.ts"` ⇒ **exit 0**, ≥10 casos verdes.

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

**Criterio BINARIO + comando:** mismo comando de F0 (`npx vitest run ".../onboarding.test.ts"`) ⇒ exit 0 con los casos nuevos.

**Flag/default:** N/A. **Impacto runtime:** idéntico (data pura). **Trabajo del operador:** ninguno.

---

### F2 — Anclas `data-tour` NORMATIVAS en contenedores estables

**Objetivo (1 frase):** agregar los atributos `data-tour="nav"` y `data-tour="topbar-actions"` a los contenedores estables (el `help-launcher` lo agrega F3).
**Valor:** los pasos apuntan a elementos que EXISTEN; additivo y sin cambio de comportamiento.

**Archivos EXACTOS (pre-flight `git status --` por archivo — zona caliente):**
- `Stacky Agents/frontend/src/App.tsx`
- `Stacky Agents/frontend/src/components/TopBar.tsx`

**Cambios NORMATIVOS (por texto, no por línea):**
1. En `App.tsx`, al elemento `<nav ...>` que envuelve los botones `styles.navTab` (el contenedor de navegación de la app; hoy alrededor de `App.tsx:150-269`), **agregar el atributo** `data-tour="nav"`:
   ```diff
   - <nav className={styles.nav ...}>
   + <nav className={styles.nav ...} data-tour="nav">
   ```
   (Solo se agrega el atributo; NO se cambia className, hijos ni lógica.)
2. En `TopBar.tsx`, al `<div className={styles.actions}>` (hoy `TopBar.tsx:201`) **agregar** `data-tour="topbar-actions"`:
   ```diff
   - <div className={styles.actions}>
   + <div className={styles.actions} data-tour="topbar-actions">
   ```

**Casos borde:** ninguno funcional — son atributos `data-*` inertes. No afectan estilos, foco, ni tests existentes.

**CROSS-151/139 (nota de coordinación):** si el plan 139 (App Shell v2) ya reemplazó la fila de tabs por una sidebar cuando se implemente 151, el `data-tour="nav"` va en el **contenedor de nav de la sidebar** del 139 (el `<nav>`/`<aside>` que agrupa los ítems), no en la fila vieja. El requisito es: **existe un único elemento con `data-tour="nav"` que representa la navegación principal**. F1 `stepAnchorsAreDeclared` no depende de qué layout esté vigente.

**Tests:** no hay test unitario de DOM (sin jsdom). Gate: `tsc --noEmit` (KPI-2) + smoke §9 (el paso "nav" resalta el contenedor real).

**Criterio BINARIO + comando:** `npx tsc --noEmit -p "Stacky Agents/frontend/tsconfig.json"` ⇒ exit 0. `grep -rn 'data-tour="nav"' "Stacky Agents/frontend/src"` ⇒ exactamente 1 (App.tsx o la sidebar del 139). `grep -rn 'data-tour="topbar-actions"'` ⇒ exactamente 1.

**Flag/default:** N/A. **Impacto runtime:** idéntico (atributos inertes). **Trabajo del operador:** ninguno.

---

### F3 — Componente `OnboardingTour` v2 + launcher "?" (reescritura del prototipo)

**Objetivo (1 frase):** reescribir `OnboardingTour.tsx` como componente accesible que consume F0/F1 + primitivas 138 + tokens de motion 143 + `--focus-ring` 141, y agregar el botón "?" en la topbar.
**Valor:** entrega el tour real (spotlight, prev/next/skip, Esc, foco) y el launcher re-abrible, al estándar de la serie.

**Archivos EXACTOS (pre-flight `git status --`):**
- REESCRIBIR: `Stacky Agents/frontend/src/components/OnboardingTour.tsx`
- REESCRIBIR: `Stacky Agents/frontend/src/components/OnboardingTour.module.css`
- NUEVO: `Stacky Agents/frontend/src/store/onboardingStore.ts` (zustand — patrón de `store/uiSectionsStore`)
- NUEVO: `Stacky Agents/frontend/src/components/HelpLauncher.tsx`
- `Stacky Agents/frontend/src/components/TopBar.tsx` (montar `<HelpLauncher />` dentro de `styles.actions`)

**Store compartido (contrato):**
```ts
// onboardingStore.ts  (zustand, mismo patrón que uiSectionsStore)
interface OnboardingState {
  open: boolean;
  requestOpenTour(): void;   // on-demand: resetSeen(safeStorage()) + open=true  (siempre)
  closeTour(): void;         // markSeen(safeStorage()) + open=false
  setOpen(v: boolean): void;
}
```
> `requestOpenTour` llama `resetSeen` para que, si el operador re-abre, al cerrarlo vuelva a marcar seen (idempotente). El auto-show inicial NO usa el store para decidir; usa `shouldAutoShow` en el effect de F5.

**`OnboardingTour.tsx` v2 (pseudocódigo con casos borde):**
```tsx
import { Card, Button, IconButton } from "./ui";           // primitivas 138 (barrel)
import { STEPS } from "../services/onboardingSteps";
import { nextStep, prevStep, isLastStep } from "../services/onboarding";
import { useOnboardingStore } from "../store/onboardingStore";
import styles from "./OnboardingTour.module.css";

export default function OnboardingTour() {
  const open = useOnboardingStore(s => s.open);
  const close = useOnboardingStore(s => s.closeTour);
  const [i, setI] = useState(0);
  const cardRef = useRef<HTMLDivElement>(null);

  // Reset al abrir + foco al primer control + Esc = cerrar (saltar)
  useEffect(() => {
    if (!open) return;
    setI(0);
    cardRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      else if (e.key === "ArrowRight") setI(v => nextStep(v, STEPS.length));
      else if (e.key === "ArrowLeft")  setI(v => prevStep(v));
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
      <Card ref={cardRef} tabIndex={-1}
            className={`${styles.card} ${styles[step.position]} ${rect ? "" : styles.centered}`}
            data-anchored={rect ? "1" : "0"}>
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
    </div>,
    document.body
  );
}
```
Casos borde:
- `safeRect(sel)`: `try { el = document.querySelector(sel); return el?.getBoundingClientRect() ?? null } catch { return null }`. Ancla ausente ⇒ `rect=null` ⇒ card **centrada** (clase `.centered`), sin spotlight, sin crash (cubre §4.3).
- `spotlightVars(rect)`: setea CSS custom props `--r-top/left/w/h` para posicionar el recorte; el spotlight es un `div` con `box-shadow` grande (oscurece el resto) — **sin capturar clicks** (el backdrop maneja el dismiss).
- Recalcular `rect` en resize/scroll: escuchar `resize` (y recomputar) es opcional; si no, el spotlight queda estático hasta cambiar de paso — aceptable para v1 (documentado en §7).

**Estilos `OnboardingTour.module.css` (reglas clave, solo tokens — sin hex nuevos):**
- Entrada/salida de la card con `transition: var(--transition-opacity), var(--transition-transform);` (tokens del 143). **NO** se escribe ninguna `@media (prefers-reduced-motion)` (la global del 141 F5 neutraliza estas transiciones automáticamente — §4/§3.4).
- Foco visible: la card y botones usan `:focus-visible { box-shadow: var(--focus-ring); }` (token del 141). En realidad los `Button`/`IconButton` del 138 ya traen su foco; la card usa el token directo.
- `z-index` por encima de modales existentes pero **por debajo** de toasts críticos (documentar el valor elegido con el token/escala del 138 si existe; si no, un literal aislado en el `.module.css` de este feature — permitido, no está bajo el ratchet de `components/ui/`).

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
Montaje en `TopBar.tsx`: dentro de `<div className={styles.actions} data-tour="topbar-actions">` (de F2), agregar `<HelpLauncher />` **antes** de `<CostCapIndicator .../>` o al final del bloque (elección estética; el atributo `data-tour="help-launcher"` va en el propio IconButton, cumpliendo el ancla del step "help").

**Tests:** sin RTL. La lógica (next/prev/last) ya está cubierta por F0. Gate del componente: `tsc --noEmit` (KPI-2) + smoke §9.

**Criterio BINARIO + comando:**
- `npx tsc --noEmit -p "Stacky Agents/frontend/tsconfig.json"` ⇒ exit 0.
- `grep -rn 'data-tour="help-launcher"' "Stacky Agents/frontend/src"` ⇒ exactamente 1.
- `grep -rn "stacky-agents-tour-done" "Stacky Agents/frontend/src/components/OnboardingTour.tsx"` ⇒ 0 (la key vieja ya no vive en el componente).

**Flag/default:** el componente se monta siempre; la decisión de mostrarse (auto vs on-demand) la maneja el store + el effect de F5. El launcher está SIEMPRE disponible (KPI-6).
**Impacto runtime:** idéntico (los 3 renderizan React igual). Fallback `localStorage` heredado de F0 (`closeTour`/`requestOpenTour` usan `safeStorage()`).
**Trabajo del operador:** ninguno; gana el botón "?" para re-ver.

---

### F4 — Toggle en Configuración (config por UI)

**Objetivo (1 frase):** exponer en Configuración un control para (a) activar/desactivar el auto-show en first-run y (b) re-ver el tour ahora.
**Valor:** cumple la regla dura de la casa (toda config del operador tocable por UI) y da control al operador existente.

**Archivos EXACTOS (pre-flight `git status --`):**
- `Stacky Agents/frontend/src/pages/SettingsPage.tsx` (agregar controles en el panel de "Secciones/UI" — `SettingsPage.tsx:26` sub-tab `"sections"`, panel `SectionsVisibilityPanel` `SettingsPage.tsx:59+`).

**Cambios NORMATIVOS:**
- Dentro del panel de secciones (o un bloque nuevo "Onboarding" en el mismo sub-tab), agregar:
  1. Un checkbox/toggle "Mostrar el tour de bienvenida en el primer arranque" ligado a `isAutoShowEnabled(safeStorage())` / `setAutoShow(safeStorage(), v)`.
  2. Un botón "Re-ver tour ahora" que llama `useOnboardingStore.getState().requestOpenTour()`.
- Reusar los estilos de toggle ya presentes (`styles.toggle`, `styles.toggleSlider` — `SettingsPage.tsx:75-82`) para no introducir CSS nuevo.

**Casos borde:** si `localStorage` está en fallback memoria, el toggle funciona pero no persiste entre recargas (consistente con §4.6; opcionalmente mostrar un hint discreto). El botón "Re-ver" funciona siempre (usa el store en memoria).

**Tests:** la lógica `setAutoShow`/`isAutoShowEnabled` ya está en F0. Gate UI: `tsc --noEmit` + smoke §9.

**Criterio BINARIO + comando:** `npx tsc --noEmit ...` ⇒ exit 0. Smoke §9: apagar el toggle ⇒ borrar `seen` ⇒ recargar ⇒ el tour NO aparece solo; prender el toggle ⇒ borrar `seen` ⇒ recargar ⇒ aparece.

**Flag/default:** la preferencia default ON (F0). **Impacto runtime:** idéntico. **Trabajo del operador:** ninguno obligatorio; gana control fino.

---

### F5 — Wire en `App.tsx`, migración y first-run gate (cierre)

**Objetivo (1 frase):** conectar el auto-show real (solo first-run) y migrar la key vieja, sin romper backward-compat.
**Valor:** el operador nuevo ve el tour una vez; el existente no; la key vieja no re-molesta.

**Archivos EXACTOS (pre-flight `git status --` — zona caliente `App.tsx`):**
- `Stacky Agents/frontend/src/App.tsx`

**Cambios NORMATIVOS:**
1. `App.tsx` ya monta `<OnboardingTour />` (hoy `App.tsx:296`). Se **mantiene** el montaje (el componente decide con el store).
2. Agregar un `useEffect` de arranque (junto a los `initPreferences()` / `initUiSections()` ya existentes — `App.tsx:25-26`) que:
   ```ts
   useEffect(() => {
     const s = safeStorage();
     migrateLegacy(s);                 // operador que cerró el prototipo => no re-mostrar
     if (shouldAutoShow(s)) {
       useOnboardingStore.getState().setOpen(true);
     }
   }, []);
   ```
   > Este effect NO llama `resetSeen`. El auto-show abre el tour; al cerrarlo, `closeTour` marca `seen`, y no vuelve a auto-aparecer.
3. Verificar que el import viejo `import OnboardingTour from "./components/OnboardingTour"` (`App.tsx:20`) siga válido (mismo path; el componente fue reescrito, no movido).

**Casos borde:**
- Operador existente con la key vieja: `migrateLegacy` ⇒ `seen`; `shouldAutoShow` ⇒ `false`. No lo ve. ✔
- Operador existente sin key vieja pero con `pinnedAgents`: `hasPriorUse` ⇒ `true`; no lo ve. ✔
- First-run real: `shouldAutoShow` ⇒ `true`; se abre una vez. ✔
- `localStorage` deshabilitado: `safeStorage` en memoria; el tour se muestra pero no persiste (degradación aceptable §4.6). ✔

**Tests:** la decisión (`migrateLegacy`, `shouldAutoShow`) está cubierta por F0 con storage inyectado. El wire en `App.tsx` no tiene test unitario (sin jsdom); gate `tsc --noEmit` + smoke §9.

**Criterio BINARIO + comando:**
- `npx vitest run "Stacky Agents/frontend/src/services/__tests__/onboarding.test.ts"` ⇒ exit 0 (regresión completa de F0/F1).
- `npx tsc --noEmit -p "Stacky Agents/frontend/tsconfig.json"` ⇒ exit 0.
- `grep -rn "stacky-agents-tour-done" "Stacky Agents/frontend/src"` ⇒ 0 fuera de la constante `LEGACY_SEEN_KEY` en `onboarding.ts` (KPI-3).

**Flag/default:** preferencia default ON (§4.4). **Impacto runtime:** idéntico; fallback `localStorage` en `safeStorage`. **Trabajo del operador:** ninguno.

---

## 7. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|--------|------------|
| R1 | El plan 139 reagrupa la nav ⇒ el ancla `data-tour="nav"` podría quedar en un contenedor inexistente. | F2/CROSS-151/139: el ancla va en el contenedor de nav vigente (fila o sidebar). Fallback §4.3: si falta, card centrada (no crashea). Test F1 no depende del layout. |
| R2 | `localStorage` deshabilitado (webview restringido) ⇒ throw. | `safeStorage()` con probe + fallback en memoria (F0). Todo el módulo usa la abstracción. |
| R3 | Molestar al operador existente. | `shouldAutoShow` con `hasPriorUse` + `migrateLegacy` (F0/F5). Solo first-run real. |
| R4 | Zona caliente `App.tsx`/`TopBar.tsx` con sesión concurrente en la rama. | Pre-flight `git status --` por archivo; STOP ante WIP ajeno; staging quirúrgico; anclas por texto normativo (§4.7). |
| R5 | Ratchet de `components/ui/` (138) prohíbe hex/`style={{`. | El tour es componente **feature** (`components/OnboardingTour.tsx`), NO primitiva; no cae bajo el ratchet (`138_PLAN_*.md:346`). Igual, sus estilos usan tokens; los pocos literales (z-index) viven en su `.module.css` de feature. |
| R6 | Spotlight desalineado tras scroll/resize. | v1: recomputa `rect` al cambiar de paso; scroll/resize continuo queda fuera de scope (§8). Aceptable: la card sigue legible; el spotlight es decorativo. |
| R7 | Doble fuente de verdad del "flag" (harness vs frontend). | Decisión explícita §4.4: NO hay flag del arnés; preferencia frontend única. Evita drift `harness_defaults.env`. |

---

## 8. Fuera de scope

- Backend: **nada**. Sin endpoints, sin flag del arnés, sin `config.py`.
- Recalcular el spotlight en scroll/resize continuo (solo al cambiar de paso en v1).
- Tours contextuales por-pantalla o tooltips permanentes (esto es un tour de bienvenida global).
- Telemetría de "cuántos pasos completó" (no hay superficie de métricas para esto y agregaría trabajo).
- Internacionalización (la app es español; el tour también).
- Tests con `@testing-library/react`/`jsdom` (no existen en el repo; el gate es `tsc` + smoke — §4.6).

---

## 9. Orden de implementación + Definition of Done

**Orden (dependencias):** F0 → F1 → F2 → F3 → F4 → F5. (F0/F1 son pura lógica y datos; F2 agrega anclas; F3 el componente+launcher; F4 la config; F5 el wire final.)

**Smoke manual (§9, obligatorio antes de dar por hecho — no hay RTL):**
1. Limpiar `localStorage` (o usar perfil nuevo del webview) ⇒ recargar ⇒ **el tour aparece** en el paso 1.
2. Recorrer con "Siguiente"/"Anterior"/flechas; verificar que el paso "nav" **resalta el contenedor de navegación real** y "help" resalta el "?".
3. "Saltar" / Esc / click en backdrop ⇒ cierra; recargar ⇒ **no reaparece** (seen persistido).
4. Click en "?" de la topbar ⇒ **reabre** el tour on-demand.
5. Configuración → apagar "Mostrar tour en primer arranque" → limpiar `seen` → recargar ⇒ **no auto-aparece**; "Re-ver tour ahora" ⇒ aparece.
6. Simular operador existente: setear `stacky:pinnedAgents='["x.agent.md"]'` con `seen` ausente ⇒ recargar ⇒ **no auto-aparece**.
7. Simular `localStorage` deshabilitado (DevTools) ⇒ el tour se muestra igual, sin errores en consola.

**DoD (todo verde):**
- [ ] KPI-1: `npx vitest run "Stacky Agents/frontend/src/services/__tests__/onboarding.test.ts"` exit 0 (≥12 casos con F0+F1).
- [ ] KPI-2: `npx tsc --noEmit -p "Stacky Agents/frontend/tsconfig.json"` exit 0.
- [ ] KPI-3: `grep -rn "stacky-agents-tour-done" "Stacky Agents/frontend/src"` ⇒ 0 (salvo `LEGACY_SEEN_KEY` en `onboarding.ts`).
- [ ] KPI-4: 0 anclas huérfanas (test `stepAnchorsAreDeclared`).
- [ ] KPI-5: `shouldAutoShow` respeta operador existente (test).
- [ ] KPI-6: launcher "?" presente (`grep data-tour="help-launcher"` ⇒ 1).
- [ ] Smoke §9 pasos 1-7 OK.
- [ ] `git status --` limpio de WIP ajeno en `App.tsx`/`TopBar.tsx`/`SettingsPage.tsx`; staging quirúrgico. (El orquestador commitea.)

---

## 10. Nota de paridad (resumen por runtime)

| Fase | Codex | Claude Code | Copilot | Fallback |
|------|-------|-------------|---------|----------|
| F0 lógica pura | ✔ idéntico | ✔ | ✔ | `safeStorage()` en memoria si `localStorage` lanza |
| F1 data/steps | ✔ | ✔ | ✔ | N/A (data pura) |
| F2 anclas | ✔ | ✔ | ✔ | atributos inertes |
| F3 componente+launcher | ✔ (React) | ✔ | ✔ | card centrada si falta ancla |
| F4 config UI | ✔ | ✔ | ✔ | toggle no persiste sin `localStorage` |
| F5 wire+migración | ✔ | ✔ | ✔ | tour se muestra sin persistir "visto" |

Toda la superficie es presentación en el webview; los 3 runtimes renderizan React y exponen `localStorage` igual ⇒ paridad 100%.
