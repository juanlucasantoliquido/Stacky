# Plan 141 — Tema claro/oscuro/sistema y accesibilidad visual

**Estado:** CRITICADO v1→v2 · **VEREDICTO: APROBADO-CON-CAMBIOS** (2026-07-15) — v1 propuesto 2026-07-15
**Autor:** StackyArchitectaUltraEficientCode
**Depende de:** plan 138 **v2** (tokens semánticos + primitivas UI, incluye `--spinner-track`)
IMPLEMENTADO. La serie pendiente 132→134→135→136 aterriza ANTES (orden congelado por plan 134
v2 §3.3). Dentro de la serie de diseño: 138→139→140→**141**.
**Runtimes:** 100 % capa de presentación (frontend). Cero backend. Idéntico en Codex CLI,
Claude Code y GitHub Copilot Pro.
**Flag de harness:** NINGUNA (justificación por fase en §3.1).

---

## § 0. Changelog de crítica v1 → v2 (juez adversarial, 2026-07-15)

Veredicto: **APROBADO-CON-CAMBIOS** (0 bloqueantes; 1 IMPORTANTE; 1 MENOR). Plan excelente:
el gate de contraste WCAG por test puro y el anti-FOUC síncrono son de primer nivel.

- **C1 (IMPORTANTE) — resuelto in place [ADICIÓN ARQUITECTO].** El plan v1 sólo re-apuntaba
  TOKENS de color, pero el 138 v1 dejaba costuras `rgba(...)` hardcodeadas en las primitivas
  que NO se themean: en particular el `trackColor` del `Spinner` (`rgba(255,255,255,0.15)`)
  quedaba **invisible sobre el fondo claro**. Se coordinó con el 138 v2 (nuevo token
  `--spinner-track`) y este plan lo **re-apunta en el bloque claro** a `rgba(31, 35, 40, 0.15)`
  (pista oscura translúcida legible sobre superficies claras). La lista `REQUIRED` pasa de
  **52 → 53** tokens.
- **[ADICIÓN ARQUITECTO] — gate anti-drift de color (F3).** Se agrega un `it` que congela el
  invariante "TODO token con valor de color del `:root` base está re-apuntado en el bloque
  claro, salvo los invariantes de texto-sobre-solid". Hoy eso era sólo prosa (§12); ahora es
  MECÁNICO: si un plan futuro agrega un color dark-only, el test lo detecta y fuerza decisión
  consciente. Cero costo, invisible, 3 runtimes N/A.
- **C2 (MENOR) — documentado.** F5 (`:focus-visible` global + `prefers-reduced-motion`) es la
  ÚNICA parte NO dormida/opt-in del plan: cambia el comportamiento para usuarios de teclado y
  con reduced-motion desde el día 1 (aparece anillo de foco en `<button>` que hoy no tienen
  ninguno). Es una MEJORA WCAG no-regresiva (invisible con mouse; solo afecta a quien pidió
  reduced-motion en su SO), por eso NO lleva flag. Se refuerza el smoke §11 para verificar que
  no haya doble-anillo ni recorte por `overflow`.

Impacto en la serie: depende del 138 **v2** (token `--spinner-track`). 139/140 sin cambios.

---

## § 1. Resumen ejecutivo

Stacky hoy es dark-only: `theme.css:65` tiene `color-scheme: dark` hardcodeado y no hay
forma de cambiar el tema. Este plan agrega:

1. **Selector de tema** en Configuración → sub-tab **Apariencia**, con 3 valores
   `dark | light | system`, persistido en `localStorage` bajo la clave EXACTA
   `stacky.ui.theme`, **default `dark` byte-idéntico a hoy**.
2. **Paleta clara completa** (`:root[data-theme="light"]`) re-apuntando SOLO los tokens de
   color, con contraste WCAG AA verificado token por token.
3. **Gate de contraste WCAG AA** por test vitest puro (sin RTL/jsdom): parsea `theme.css`,
   computa ratios de contraste y afirma AA para una lista CONGELADA de pares en AMBOS temas.
4. **Accesibilidad visual transversal**: `:focus-visible` global consistente,
   `prefers-reduced-motion: reduce` global, y `color-scheme` nativo por tema.

**Valor / KPI:**
- **KPI-1 (accesibilidad):** 24/24 pares del gate en modo claro cumplen AA (≥4.5:1). El
  gate corre en CI vitest → cero regresiones de contraste futuras.
- **KPI-2 (inclusión):** operadores con fotofobia / entornos muy iluminados / preferencia
  de SO obtienen un tema legible; usuarios de teclado obtienen foco visible; usuarios con
  `prefers-reduced-motion` dejan de ver spinners/transiciones.
- **KPI-3 (cero costo por defecto):** default `dark` byte-idéntico → 0 operadores afectados
  sin acción explícita.
- **KPI-4 (performance):** cambiar de tema NO re-monta la app (solo cambia un atributo en
  `<html>`); anti-FOUC sin bloquear render perceptible.

**Por qué NO agrega trabajo al operador:** el default es el tema actual, pixel por pixel. La
funcionalidad queda DORMIDA hasta que el operador, si quiere, hace 2 clics en
Configuración → Apariencia. Nadie tiene que configurar, migrar ni tocar nada.

---

## § 2. Contexto y evidencia (archivo:línea)

Toda afirmación de este plan está anclada en el código real leído el 2026-07-15.

### 2.1 `theme.css` — estado actual y lo que deja el 138

- `frontend/src/theme.css:3-46` — bloque `:root` con los tokens LEGACY de color
  (superficies `--bg-base` … `--border-muted`, texto `--text-primary/-muted/-faint`, acento
  `--accent/-hot`, `--success/--warn/--danger`, `--mono-bg`, identidad de agentes
  `--agent-*`, y `--card-shadow`).
- `frontend/src/theme.css:51-66` — regla `html, body, #root`. Hoy la línea 65 es
  `color-scheme: dark;` (comentario B4 arriba explicando el fix de `<select>` nativo).
- `frontend/src/theme.css:102-108` — `input/textarea/select:focus` con
  `box-shadow: 0 0 0 3px rgba(56, 139, 253, 0.25);` HARDCODEADO (mismo valor que el token
  `--focus-ring` del 138). Los `button` NO tienen estilo de foco visible hoy.

**Lo que el plan 138 (§ F1, ya implementado antes que este plan) deja congelado y este plan
consume literalmente** (fuente: `docs/138_...md` § 10, líneas 1748-1876):
- Agrega ~68 tokens nuevos al `:root`, agrupados por capa (estados A, interacción B, spacing
  C, tipografía D, radios E, sombras F, motion G, bordes/theme-ready H).
- Cambia `theme.css` la línea de `color-scheme` a `color-scheme: var(--color-scheme);` con
  `--color-scheme: dark;` (138 F1 paso 3-b, doc 138:640-642). **⇒ el 141 NO toca la regla
  `html`; solo re-apunta el token `--color-scheme` a `light` en el bloque claro.**
- Deja un comentario-contrato `THEME-READY` dentro del `:root` (138:548-553) que anuncia
  explícitamente que el 141 agregará `:root[data-theme="light"]`.
- El test `frontend/src/__tests__/themeTokens.test.ts` (138 F1 paso 1) tiene un tercer `it`
  (doc 138:530-535) que hoy afirma:
  ```ts
  it("theme-ready: color-scheme sale de la variable y aun NO hay data-theme (lo agrega el plan 141)", () => {
    expect(FLAT).toContain("color-scheme: var(--color-scheme)");
    expect(FLAT).toContain("THEME-READY");
    // El plan 141 elimina esta asercion cuando implemente el tema claro:
    expect(THEME.includes('[data-theme="light"]')).toBe(false);
  });
  ```
  **⇒ este plan (F2) DEBE invertir esa aserción** (`false` → `true`) y actualizar el título
  del `it`. Es un requisito explícito heredado del 138.

### 2.2 Estructura de la app y punto de anclaje del tema

- `frontend/index.html:1-16` — `<html lang="es">`, `<head>` con `<title>` y links de fuentes,
  `<body>` con `<div id="root">` y `<script type="module" src="/src/main.tsx">`. No hay
  ningún script inline hoy. **⇒ el snippet anti-FOUC va en el `<head>`.**
- `frontend/src/main.tsx:1-18` — monta React en `#root`, importa `./theme.css`. **⇒ acá se
  llama `initThemeController()`.**
- `frontend/src/App.tsx:151-152` — la app se renderiza dentro de `<div className={styles.appRoot}>`.
  El atributo de tema va en el **elemento raíz del documento** (`document.documentElement`,
  es decir `<html>`), que es a lo que apunta el selector CSS `:root`. **⇒ el atributo es
  `data-theme` sobre `<html>`; NO se toca App.tsx.**

### 2.3 Configuración (dónde vive el selector)

- `frontend/src/pages/SettingsPage.tsx:17` — `type SubTab = "flow" | "sections" |
  "client-profile" | "transfer" | "webhooks" | "harness" | "playground";`
- `SettingsPage.tsx:102-145` — barra de sub-tabs (un `<button>` por valor); el último botón
  hoy es **"Playground IA"** (`sub === "playground"`, líneas 139-144).
- `SettingsPage.tsx:147-155` — panel de contenido; la última línea es
  `{sub === "playground" && <LocalLlmPlaygroundPanel />}` (línea 154).
- **AVISO de zona caliente:** el plan 134 F6 (pendiente, aterriza ANTES) agrega un sub-tab
  **"Notificaciones"** a este mismo archivo. Para no colisionar, este plan ancla sus
  ediciones por el TEXTO `Playground IA` / `playground` (que el 134 no toca), NO por número
  de línea.

### 2.4 Accesibilidad y paletas locales preexistentes

- `frontend/src/components/RunButton.module.css:1-65` — `@keyframes spin` con
  `animation: spin 0.7s linear infinite` (spinner infinito) y `@keyframes pulse-bg`
  `... 1.6s ease-in-out infinite`. Hay más spinners/animaciones repartidos en 26
  `.module.css`. **⇒ la regla global `prefers-reduced-motion` (F5) los neutraliza a todos.**
- `frontend/src/components/HarnessFlagsPanel.module.css:684` — ya usa
  `@media (prefers-reduced-motion: no-preference)`. `devops.module.css:249-250` ya define
  `:focus-visible { outline: ... }` para tabs/botones locales. `DocGraphView.tsx:130` y
  `docs/forceLayout.ts:7` manejan reduced-motion en JS. **⇒ las reglas globales de F5 son
  COMPLEMENTARIAS y de baja especificidad; los componentes que ya se auto-gestionan ganan
  por especificidad (§ 5.6).**
- `frontend/src/components/dbcompare/dbcompare.module.css:9-29` — define tokens locales
  `--dbc-*` y los cambia con `@media (prefers-color-scheme: dark)`. **⇒ ese componente sigue
  la preferencia del SO, NO el atributo `data-theme` del operador. Es una DEGRADACIÓN
  conocida documentada en § 10 (Fuera de scope), misma lógica que los 1.231 hex legacy.**

### 2.5 Patrones reutilizables ya en el repo

- `frontend/src/services/preferences.ts:14-30` — helpers `read/write` localStorage con
  `try/catch` tolerante a modo privado. **⇒ el controlador de tema copia este patrón.**
- `frontend/src/pages/__tests__/ServersSection.test.ts:18-26` — idioma de test fs+regex:
  `fs.readFileSync(new URL('../ruta', import.meta.url), 'utf-8')`. **⇒ todos los tests de
  este plan que inspeccionan `.tsx`/`.html`/`.css` usan ESTE idioma, nunca RTL.**

---

## § 3. Decisiones de diseño (restricciones no negociables codificadas)

### 3.1 Flag de harness: NINGUNA (decisión por fase)

| Fase | ¿Flag? | Justificación |
|---|---|---|
| F0 código puro (resolver) | No | Sin consumidores; no cambia render. |
| F1 controlador + anti-FOUC | No | Dormido: nadie escribe `stacky.ui.theme` hasta F4 ⇒ siempre resuelve `dark` ⇒ byte-idéntico. |
| F2 paleta clara | No | El bloque `[data-theme="light"]` no aplica hasta que `data-theme="light"` esté seteado (F1+F4). Solo aporta tokens dormidos. |
| F3 gate de contraste | No | Solo test. |
| F4 selector en Settings | No | ES la superficie opt-in. Un flag para "mostrar el selector de tema" agrega fricción sin reducir riesgo (precedente 132 §3.1, 135 §3.1: UI-only opt-in por naturaleza no lleva flag). |
| F5 accesibilidad global | No | `:focus-visible` es una MEJORA (solo en foco por teclado), `prefers-reduced-motion` solo afecta a quien lo pidió en su SO. Invisible y no-regresivo para el resto. |

**Regla de oro:** toda config del operador va por UI (directiva de la casa). El selector de
tema cumple esto: se cambia desde Configuración, no desde `.env`. No hay kill-switch env
porque no hay riesgo backend que apagar.

### 3.2 Paridad de runtimes (por fase, explícita)

TODAS las fases son capa de presentación pura (localStorage del browser + CSS + un atributo
en `<html>`). No hay código específico de runtime, no se toca la ejecución de agentes, no se
toca backend. **Impacto por runtime: idéntico en Codex, Claude Code y Copilot Pro.
Fallback: N/A** (no hay ruta de ejecución que degradar). Se declara literalmente en cada
fase para dejar constancia.

### 3.3 Byte-idéntico por defecto (binario)

- `resolveTheme(null, prefersDark)` DEVUELVE `"dark"` sea cual sea `prefersDark` (test
  obligatorio F0). Un usuario nuevo con SO en claro **sigue viendo dark**, porque el default
  es `dark`, NO `system`.
- El bloque base `:root` (dark) queda intacto; el bloque `[data-theme="light"]` solo
  re-apunta color. Con `data-theme="dark"` (o ausente), el CSS computa exactamente los
  valores de hoy.
- `--color-scheme: dark` en base ⇒ `color-scheme: var(--color-scheme)` computa `dark`
  idéntico a hoy.

### 3.4 Performance (binario)

- El switch de tema es `document.documentElement.setAttribute("data-theme", eff)` +
  `localStorage.setItem`. **No hay `ReactDOM` re-render/re-mount**; las CSS custom properties
  re-cascadean solas. Prohibido implementar el tema vía estado global de React que fuerce
  re-render del árbol.
- Anti-FOUC: snippet inline SÍNCRONO en `<head>` que setea `data-theme` ANTES del primer
  paint. Para `dark` (default) no hay flash porque base ya es dark; para `light` el atributo
  llega antes de pintar ⇒ sin flash. Prohibido resolver el tema tras el primer render de
  React (causaría FOUC).

### 3.5 Sin dependencias nuevas (binario)

`package.json` NO se toca. Cero librerías. Todo es DOM/CSS nativo + React ya presente.
Verificación en DoD: `git status -- package.json` limpio.

---

## § 4. Glosario

- **ThemeChoice**: elección del operador, `"dark" | "light" | "system"`.
- **EffectiveTheme**: tema realmente aplicado, `"dark" | "light"` (resuelve `system` contra
  el SO).
- **`data-theme`**: atributo en `<html>` (`document.documentElement`) con el EffectiveTheme.
  Ausente o `"dark"` ⇒ base dark. `"light"` ⇒ activa `:root[data-theme="light"]`.
- **`stacky.ui.theme`**: clave localStorage (CONGELADA) que guarda el ThemeChoice.
- **Anti-FOUC**: Flash Of Unstyled Content — el parpadeo si la página pinta dark y luego
  salta a claro. Se evita seteando `data-theme` antes del primer paint.
- **Gate de contraste**: test que computa el ratio WCAG y falla si un par frozen no cumple.
- **Par de contraste**: (token de primer plano, token de fondo, umbral). Fondo translúcido
  (rgba) se compone sobre `--bg-base` antes de medir.
- **Token invariante al tema**: spacing/tipografía/radios/motion/`--border-width` — NO se
  duplican en el bloque claro.

---

## § 5. Fases

Cada fase es autocontenida y verificable sola. **Pre-flight OBLIGATORIO por fase (regla 135
v2 §3.2):** antes de editar CADA archivo correr `git status -- "<ruta>"`; si aparece con
cambios sin commitear que no sean de este plan → **STOP** y avisar al operador (WIP ajeno).
**Staging quirúrgico:** `git add -- <paths listados>`, NUNCA `git add -A`. **cwd de todos los
comandos de test:** `Stacky Agents/frontend`.

---

### F0 — Núcleo puro de resolución de tema

**Objetivo (1 frase):** funciones puras `resolveTheme` / `normalizeChoice` + la clave
congelada, testeables sin DOM. **Valor:** base determinista y probada del comportamiento del
selector, reutilizada por el controlador, el anti-FOUC y los tests.

**Archivos:**
- CREAR `frontend/src/services/theme.ts`
- CREAR `frontend/src/services/__tests__/theme.test.ts`

**Paso 1 (TDD, rojo) — escribir el test primero** `theme.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import { THEME_STORAGE_KEY, normalizeChoice, resolveTheme } from "../theme";

describe("Plan 141 F0 — clave congelada", () => {
  it("la clave localStorage es exactamente stacky.ui.theme", () => {
    expect(THEME_STORAGE_KEY).toBe("stacky.ui.theme");
  });
});

describe("Plan 141 F0 — normalizeChoice (default dark)", () => {
  it("valores válidos se conservan", () => {
    expect(normalizeChoice("dark")).toBe("dark");
    expect(normalizeChoice("light")).toBe("light");
    expect(normalizeChoice("system")).toBe("system");
  });
  it("null/undefined/vacío/inválido/mayúsculas caen a dark", () => {
    expect(normalizeChoice(null)).toBe("dark");
    expect(normalizeChoice(undefined)).toBe("dark");
    expect(normalizeChoice("")).toBe("dark");
    expect(normalizeChoice("weird")).toBe("dark");
    expect(normalizeChoice("DARK")).toBe("dark"); // case-sensitive a propósito
  });
});

describe("Plan 141 F0 — resolveTheme (byte-idéntico por defecto)", () => {
  it("default es dark AUNQUE el SO prefiera claro (byte-idéntico)", () => {
    expect(resolveTheme(null, false)).toBe("dark");
    expect(resolveTheme(null, true)).toBe("dark");
  });
  it("dark/light explícitos ignoran el SO", () => {
    expect(resolveTheme("dark", true)).toBe("dark");
    expect(resolveTheme("light", false)).toBe("light");
  });
  it("system sigue al SO", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
  });
});
```

**Paso 2 (rojo por la razón correcta):**
`npx vitest run src/services/__tests__/theme.test.ts` → falla porque `../theme` no existe.

**Paso 3 — implementar** `theme.ts` VERBATIM:
```ts
/* Plan 141 F0 — núcleo puro de resolución de tema (sin DOM, sin efectos). */

export type ThemeChoice = "dark" | "light" | "system";
export type EffectiveTheme = "dark" | "light";

/** Clave localStorage CONGELADA por el arquitecto (plan 141). NO renombrar. */
export const THEME_STORAGE_KEY = "stacky.ui.theme";

/** Normaliza un valor crudo a un ThemeChoice. Default byte-idéntico: "dark". */
export function normalizeChoice(raw: string | null | undefined): ThemeChoice {
  return raw === "light" || raw === "system" ? raw : "dark";
}

/** Resuelve el tema EFECTIVO. Pura. `prefersDark` = matchMedia del SO. */
export function resolveTheme(
  stored: string | null | undefined,
  prefersDark: boolean,
): EffectiveTheme {
  const choice = normalizeChoice(stored);
  if (choice === "system") return prefersDark ? "dark" : "light";
  return choice; // "dark" | "light"
}
```

**Paso 4 (verde):** `npx vitest run src/services/__tests__/theme.test.ts` y
`npx tsc --noEmit`.

**Criterio de aceptación (binario):** ambos comandos exit 0.
**Flag:** sin flag (§3.1). **Runtime:** presentación pura, idéntico en los 3, fallback N/A.
**Trabajo del operador:** ninguno.
**Staging:** `git add -- "src/services/theme.ts" "src/services/__tests__/theme.test.ts"`

---

### F1 — Controlador DOM + wiring en `main.tsx` + anti-FOUC en `index.html`

**Objetivo (1 frase):** aplicar el tema al `<html>` antes del primer paint y mantenerlo en
sync con el SO cuando el modo es `system`, sin re-montar la app. **Valor:** mecánica de
aplicación robusta y sin FOUC; deja el sistema listo pero DORMIDO (default dark).

**Archivos:**
- CREAR `frontend/src/services/themeController.ts`
- EDITAR `frontend/src/main.tsx`
- EDITAR `frontend/index.html`
- CREAR `frontend/src/__tests__/themeBootstrap.test.ts`

**Paso 1 (TDD, rojo)** — `themeBootstrap.test.ts` (fs+regex, sin DOM):
```ts
import { describe, it, expect } from "vitest";
import * as fs from "fs";

const html = fs.readFileSync(new URL("../../index.html", import.meta.url), "utf-8");
const mainTsx = fs.readFileSync(new URL("../main.tsx", import.meta.url), "utf-8");
const ctrl = fs.readFileSync(new URL("../services/themeController.ts", import.meta.url), "utf-8");

describe("Plan 141 F1 — anti-FOUC inline en index.html", () => {
  it("hay un script inline que lee la clave congelada y setea data-theme antes del paint", () => {
    expect(html).toContain("stacky.ui.theme");
    expect(html).toContain("data-theme");
    expect(html).toContain("prefers-color-scheme: dark");
    // default dark: el fallback ante error/valor ausente es "dark"
    expect(html).toContain('"dark"');
  });
  it("el script inline NO es un módulo (corre síncrono antes del bundle)", () => {
    // debe existir un <script> clásico (sin type=module) con la lógica de tema
    expect(/<script>[\s\S]*stacky\.ui\.theme[\s\S]*<\/script>/.test(html)).toBe(true);
  });
});

describe("Plan 141 F1 — wiring en main.tsx", () => {
  it("importa y llama initThemeController antes de montar React", () => {
    expect(mainTsx).toContain("initThemeController");
    const idxInit = mainTsx.indexOf("initThemeController(");
    const idxRoot = mainTsx.indexOf("createRoot");
    expect(idxInit).toBeGreaterThan(-1);
    expect(idxInit).toBeLessThan(idxRoot); // se llama ANTES de montar
  });
});

describe("Plan 141 F1 — controlador delega en el núcleo puro", () => {
  it("usa resolveTheme/normalizeChoice y la clave del módulo puro", () => {
    expect(ctrl).toContain("resolveTheme");
    expect(ctrl).toContain("THEME_STORAGE_KEY");
    expect(ctrl).toContain('setAttribute("data-theme"');
    expect(ctrl).toContain("prefers-color-scheme: dark");
  });
});
```

**Paso 2 (rojo):** el test falla (faltan `themeController.ts`, el wiring y el snippet).

**Paso 3 — implementar `themeController.ts`** VERBATIM:
```ts
/* Plan 141 F1 — controlador de tema (efectos DOM). La LÓGICA vive en theme.ts (puro). */
import {
  THEME_STORAGE_KEY,
  normalizeChoice,
  resolveTheme,
  type ThemeChoice,
  type EffectiveTheme,
} from "./theme";

const MQ_DARK = "(prefers-color-scheme: dark)";

/** Lee la elección persistida, tolerante a modo privado. */
export function readStoredChoice(): ThemeChoice {
  try {
    return normalizeChoice(localStorage.getItem(THEME_STORAGE_KEY));
  } catch {
    return "dark";
  }
}

function prefersDark(): boolean {
  try {
    return !!(window.matchMedia && window.matchMedia(MQ_DARK).matches);
  } catch {
    return false;
  }
}

/** Aplica el tema efectivo al <html>. Idempotente. */
export function applyEffectiveTheme(effective: EffectiveTheme): void {
  try {
    document.documentElement.setAttribute("data-theme", effective);
  } catch {
    /* sin DOM: no-op */
  }
}

/**
 * Persiste la elección, la aplica al instante y devuelve el tema efectivo.
 * NO re-monta la app: solo cambia el atributo del <html>.
 */
export function setTheme(choice: ThemeChoice): EffectiveTheme {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, choice);
  } catch {
    /* best-effort */
  }
  const eff = resolveTheme(choice, prefersDark());
  applyEffectiveTheme(eff);
  return eff;
}

/**
 * Idempotente. Aplica el tema actual e instala el listener del SO para que el
 * modo "system" reaccione a cambios de preferencia mientras la app está abierta.
 */
export function initThemeController(): void {
  applyEffectiveTheme(resolveTheme(readStoredChoice(), prefersDark()));
  try {
    const mq = window.matchMedia(MQ_DARK);
    const onChange = () => {
      if (readStoredChoice() === "system") {
        applyEffectiveTheme(resolveTheme("system", mq.matches));
      }
    };
    if (mq.addEventListener) mq.addEventListener("change", onChange);
    else if ((mq as unknown as { addListener?: (cb: () => void) => void }).addListener) {
      (mq as unknown as { addListener: (cb: () => void) => void }).addListener(onChange); // Safari viejo
    }
  } catch {
    /* sin matchMedia: "system" se resuelve una vez, sin listener */
  }
}
```

**Paso 4 — editar `main.tsx`.** Agregar el import junto a los demás y llamar al controlador
ANTES de `ReactDOM.createRoot`. Estado final del archivo:
```ts
import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import { initThemeController } from "./services/themeController";
import "./theme.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
});

// Plan 141: aplica el tema (idempotente respecto del anti-FOUC de index.html) e
// instala el listener del SO para el modo "system". Antes de montar React.
initThemeController();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>
);
```

**Paso 5 — editar `index.html`.** Insertar el `<script>` inline clásico dentro de `<head>`,
inmediatamente DESPUÉS de la línea `<title>Stacky Agents</title>` (así corre lo antes
posible). El snippet DEBE ser lógicamente idéntico a `resolveTheme`/`normalizeChoice`:
```html
    <title>Stacky Agents</title>
    <script>
      /* Plan 141 — anti-FOUC: fija data-theme antes del primer paint.
         DEBE mantenerse en sync con src/services/theme.ts (resolveTheme). */
      (function () {
        try {
          var raw = localStorage.getItem("stacky.ui.theme");
          var choice = raw === "light" || raw === "system" ? raw : "dark";
          var prefersDark =
            !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
          var effective = choice === "system" ? (prefersDark ? "dark" : "light") : choice;
          document.documentElement.setAttribute("data-theme", effective);
        } catch (e) {
          document.documentElement.setAttribute("data-theme", "dark");
        }
      })();
    </script>
```

**Casos borde cubiertos:**
- `localStorage` lanza (modo privado) → `catch` → `data-theme="dark"` (byte-idéntico).
- `matchMedia` inexistente → `prefersDark=false`; en modo `system` cae a `light` (correcto:
  ausencia de "prefiere dark" ⇒ claro).
- `initThemeController` re-aplica el MISMO valor que el snippet (idempotente): no hay salto
  visual entre el anti-FOUC y el montaje de React.

**Paso 6 (verde):** `npx vitest run src/__tests__/themeBootstrap.test.ts` y `npx tsc --noEmit`.

**Criterio de aceptación (binario):** ambos comandos exit 0; con `stacky.ui.theme` ausente,
`data-theme` resuelto = `"dark"` (lo garantiza F0 + el snippet). Nada visual cambia todavía.
**Flag:** sin flag (dormido, §3.1). **Runtime:** presentación pura, idéntico, fallback N/A.
**Trabajo del operador:** ninguno.
**Staging:** `git add -- "src/services/themeController.ts" "src/main.tsx" "index.html" "src/__tests__/themeBootstrap.test.ts"`

---

### F2 — Paleta clara en `theme.css` + retiro de la aserción anti-`data-theme` del 138

**Objetivo (1 frase):** agregar `:root[data-theme="light"]` re-apuntando SOLO tokens de color
con contraste verificado, y actualizar el test del 138 según su propio contrato. **Valor:**
el tema claro cobra existencia real; el sistema de tokens del 138 pasa a ser bi-tema.

**Archivos:**
- EDITAR `frontend/src/theme.css`
- EDITAR `frontend/src/__tests__/themeTokens.test.ts` (creado por el 138)
- CREAR `frontend/src/__tests__/themeLightTokens.test.ts`

**Pre-flight crítico:** `git status -- "src/__tests__/themeTokens.test.ts" "src/theme.css"`.
Este plan asume el 138 YA implementado y mergeado. Si `themeTokens.test.ts` no existe →
STOP: el 138 no está; no se puede continuar.

**Paso 1 (TDD, rojo)** — `themeLightTokens.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import * as fs from "fs";

const THEME = fs.readFileSync(new URL("../theme.css", import.meta.url), "utf-8");

/** Extrae el cuerpo del bloque :root[data-theme="light"] { ... }. */
function lightBlock(): string {
  const m = THEME.match(/:root\[data-theme="light"\]\s*\{([\s\S]*?)\}/);
  return m ? m[1] : "";
}
const LIGHT = lightBlock();

// Tokens de COLOR que el bloque claro DEBE re-apuntar (nombre → valor exacto).
const REQUIRED: Array<[string, string]> = [
  ["--bg-base", "#ffffff"],
  ["--bg-panel", "#f6f8fa"],
  ["--bg-elev", "#eaeef2"],
  ["--border", "#d0d7de"],
  ["--border-muted", "#eaeef2"],
  ["--mono-bg", "#f6f8fa"],
  ["--text-primary", "#1f2328"],
  ["--text-muted", "#57606a"],
  ["--text-faint", "#6e7781"],
  ["--accent", "#0969da"],
  ["--accent-hot", "#0550ae"],
  ["--success", "#1a7f37"],
  ["--warn", "#9a6700"],
  ["--danger", "#cf222e"],
  ["--agent-business", "#8250df"],
  ["--agent-functional", "#bc4c00"],
  ["--agent-technical", "#0969da"],
  ["--agent-developer", "#1a7f37"],
  ["--agent-qa", "#9a6700"],
  ["--agent-custom", "#57606a"],
  ["--card-shadow", "0 2px 12px rgba(140, 149, 159, 0.15)"],
  ["--status-success-text", "#116329"],
  ["--status-success-soft-text", "#166534"],
  ["--status-success-solid", "#1a7f37"],
  ["--status-success-bg", "rgba(34, 197, 94, 0.14)"],
  ["--status-success-border", "rgba(34, 197, 94, 0.35)"],
  ["--status-warning-text", "#7d4e00"],
  ["--status-warning-soft-text", "#8a5a00"],
  ["--status-warning-muted-text", "#7d4e00"],
  ["--status-warning-solid", "#bf8700"],
  ["--status-warning-bg", "rgba(245, 158, 11, 0.16)"],
  ["--status-warning-border", "rgba(245, 158, 11, 0.4)"],
  ["--status-danger-text", "#b31c28"],
  ["--status-danger-soft-text", "#cf222e"],
  ["--status-danger-solid", "#cf222e"],
  ["--status-danger-bg", "rgba(239, 68, 68, 0.13)"],
  ["--status-danger-border", "rgba(239, 68, 68, 0.35)"],
  ["--status-info-text", "#0a58ca"],
  ["--status-info-solid", "#0969da"],
  ["--status-info-hot", "#0550ae"],
  ["--status-info-bg", "rgba(59, 130, 246, 0.12)"],
  ["--status-info-border", "rgba(59, 130, 246, 0.4)"],
  ["--status-neutral-bg", "rgba(31, 35, 40, 0.06)"],
  ["--status-neutral-border", "rgba(31, 35, 40, 0.15)"],
  ["--accent-active", "#0550ae"],
  ["--warn-hover", "#7d5300"],
  ["--focus-ring", "0 0 0 3px rgba(9, 105, 218, 0.35)"],
  ["--spinner-track", "rgba(31, 35, 40, 0.15)"],
  ["--shadow-1", "0 1px 3px rgba(31, 35, 40, 0.12)"],
  ["--shadow-2", "0 2px 12px rgba(31, 35, 40, 0.14)"],
  ["--shadow-3", "0 8px 24px rgba(31, 35, 40, 0.18)"],
  ["--shadow-overlay", "0 16px 48px rgba(31, 35, 40, 0.24)"],
  ["--color-scheme", "light"],
];

// Tokens INVARIANTES al tema: PROHIBIDO que aparezcan en el bloque claro.
const FORBIDDEN = [
  "--space-1", "--space-9",
  "--text-2xs", "--text-sm", "--text-2xl",
  "--weight-regular", "--weight-bold",
  "--leading-tight", "--leading-relaxed",
  "--radius-xs", "--radius-md", "--radius-lg", "--radius-full",
  "--duration-fast", "--duration-slow",
  "--ease-standard", "--ease-out-expo",
  "--border-width",
];

describe("Plan 141 F2 — bloque claro completo y correcto", () => {
  it("existe el bloque :root[data-theme=\"light\"]", () => {
    expect(LIGHT.length).toBeGreaterThan(0);
  });
  it("re-apunta los 53 tokens de color con valor exacto", () => {
    const missing = REQUIRED.filter(([n, v]) => !LIGHT.includes(`${n}: ${v};`));
    expect(missing.map(([n]) => n)).toEqual([]);
    expect(REQUIRED.length).toBe(53);
  });
  it("NO duplica tokens invariantes al tema (spacing/tipografía/radio/motion/border-width)", () => {
    const leaked = FORBIDDEN.filter((n) => LIGHT.includes(`${n}:`));
    expect(leaked).toEqual([]);
  });
  it("NO re-declara --status-neutral-text (auto-tema vía var(--text-muted))", () => {
    expect(LIGHT.includes("--status-neutral-text:")).toBe(false);
  });
});
```

**Paso 2 (rojo):** falla — no existe el bloque claro.

**Paso 3 — editar `theme.css`.** Insertar el siguiente bloque COMPLETO y VERBATIM
inmediatamente DESPUÉS de la llave de cierre `}` del `:root` base (es decir, tras el bloque
de tokens que dejó el 138 F1, antes de la regla `/* ─── Reset ─── */`):

```css

/* ═══ Plan 141 — Tema claro (re-apunta SOLO tokens de color) ═══════════
   Contraste WCAG AA verificado token a token (ver plan 141 § 6). Spacing,
   tipografía, radios, motion y --border-width son INVARIANTES: NO se duplican.
   --status-neutral-text NO se re-declara: es var(--text-muted) y auto-tema.
   --text-on-solid (#ffffff) y --text-on-warn (#1c1810) son invariantes: los
   solids claros se eligieron oscuros para que el texto siga siendo AA. */
:root[data-theme="light"] {
  /* Superficies (GitHub Light) */
  --bg-base: #ffffff;
  --bg-panel: #f6f8fa;
  --bg-elev: #eaeef2;
  --border: #d0d7de;
  --border-muted: #eaeef2;
  --mono-bg: #f6f8fa;

  /* Texto */
  --text-primary: #1f2328;
  --text-muted: #57606a;
  --text-faint: #6e7781;

  /* Acento / estado legacy */
  --accent: #0969da;
  --accent-hot: #0550ae;
  --success: #1a7f37;
  --warn: #9a6700;
  --danger: #cf222e;

  /* Identidad de agentes */
  --agent-business: #8250df;
  --agent-functional: #bc4c00;
  --agent-technical: #0969da;
  --agent-developer: #1a7f37;
  --agent-qa: #9a6700;
  --agent-custom: #57606a;

  /* Sombra legacy de tarjetas */
  --card-shadow: 0 2px 12px rgba(140, 149, 159, 0.15);

  /* Estados semánticos (grupo A) */
  --status-success-text: #116329;
  --status-success-soft-text: #166534;
  --status-success-solid: #1a7f37;
  --status-success-bg: rgba(34, 197, 94, 0.14);
  --status-success-border: rgba(34, 197, 94, 0.35);
  --status-warning-text: #7d4e00;
  --status-warning-soft-text: #8a5a00;
  --status-warning-muted-text: #7d4e00;
  --status-warning-solid: #bf8700;
  --status-warning-bg: rgba(245, 158, 11, 0.16);
  --status-warning-border: rgba(245, 158, 11, 0.4);
  --status-danger-text: #b31c28;
  --status-danger-soft-text: #cf222e;
  --status-danger-solid: #cf222e;
  --status-danger-bg: rgba(239, 68, 68, 0.13);
  --status-danger-border: rgba(239, 68, 68, 0.35);
  --status-info-text: #0a58ca;
  --status-info-solid: #0969da;
  --status-info-hot: #0550ae;
  --status-info-bg: rgba(59, 130, 246, 0.12);
  --status-info-border: rgba(59, 130, 246, 0.4);
  --status-neutral-bg: rgba(31, 35, 40, 0.06);
  --status-neutral-border: rgba(31, 35, 40, 0.15);

  /* Interacción / acento (grupo B) */
  --accent-active: #0550ae;
  --warn-hover: #7d5300;
  --focus-ring: 0 0 0 3px rgba(9, 105, 218, 0.35);
  /* Pista del spinner: oscura translúcida, legible sobre superficies claras (138 v2 C1). */
  --spinner-track: rgba(31, 35, 40, 0.15);

  /* Sombras (grupo F) */
  --shadow-1: 0 1px 3px rgba(31, 35, 40, 0.12);
  --shadow-2: 0 2px 12px rgba(31, 35, 40, 0.14);
  --shadow-3: 0 8px 24px rgba(31, 35, 40, 0.18);
  --shadow-overlay: 0 16px 48px rgba(31, 35, 40, 0.24);

  /* color-scheme nativo (grupo H) */
  --color-scheme: light;
}
```

**Paso 4 — actualizar `themeTokens.test.ts` (contrato del 138).** Localizar el tercer `it`
(su título contiene `aun NO hay data-theme (lo agrega el plan 141)`). Reemplazar SOLO ese
bloque `it` por:
```ts
  it("theme-ready: color-scheme sale de la variable y el plan 141 YA agrego data-theme", () => {
    expect(FLAT).toContain("color-scheme: var(--color-scheme)");
    expect(FLAT).toContain("THEME-READY");
    // Plan 141 F2: el tema claro existe.
    expect(THEME.includes('[data-theme="light"]')).toBe(true);
  });
```
No tocar los otros dos `it` del `describe` (tokens nuevos / tokens legacy intactos): el
bloque claro NO altera el `:root` base, así que siguen verdes.

**Casos borde:**
- Los tokens `rgba(...)` van con el MISMO formato de espacios que el test (`rgba(34, 197, 94,
  0.14)` con espacios tras coma). Copiar VERBATIM del bloque de arriba.
- `--radius-md`/`--radius-lg` (invariantes) NO van al bloque claro aunque sean "6px/10px":
  radios no dependen del tema.

**Paso 5 (verde):**
`npx vitest run src/__tests__/themeLightTokens.test.ts`,
`npx vitest run src/__tests__/themeTokens.test.ts`,
`npx vitest run src/__tests__/uiDebtRatchet.test.ts` (theme.css NO entra al ratchet ⇒ sigue
verde) y `npx tsc --noEmit`.

**Criterio de aceptación (binario):** los 4 comandos exit 0.
**Flag:** sin flag (§3.1). **Runtime:** presentación pura, idéntico, fallback N/A.
**Trabajo del operador:** ninguno (el tema claro no se activa hasta F4).
**Staging:** `git add -- "src/theme.css" "src/__tests__/themeTokens.test.ts" "src/__tests__/themeLightTokens.test.ts"`

---

### F3 — Gate de contraste WCAG AA (test puro)

**Objetivo (1 frase):** test vitest que parsea `theme.css`, computa el ratio WCAG de una
lista CONGELADA de pares y afirma AA en AMBOS temas, documentando las excepciones dark.
**Valor:** blindaje permanente contra regresiones de contraste en CI.

**Archivos:**
- CREAR `frontend/src/__tests__/themeContrast.test.ts`

**Fórmula WCAG (pseudocódigo EXACTO a implementar en el test):**
```
sRGBtoLinear(c8bit):
  c = c8bit / 255
  return c/12.92               si c <= 0.03928
         ((c+0.055)/1.055)^2.4  en otro caso
relativeLuminance(r,g,b) = 0.2126*L(r) + 0.7152*L(g) + 0.0722*L(b)   // L = sRGBtoLinear
contrastRatio(fg,bg):
  L1 = luminance(fg); L2 = luminance(bg)
  hi = max(L1,L2); lo = min(L1,L2)
  return (hi + 0.05) / (lo + 0.05)
composite(rgba, baseRgb):        // aplanar translúcido sobre un fondo opaco
  return round( rgba.rgb*rgba.a + baseRgb*(1 - rgba.a) )   // por canal
resolveColor(token, themeMap, baseMap):   // resuelve var() y hereda de la base
  raw = themeMap[token] ?? baseMap[token]
  si raw es "var(--X)": return resolveColor("--X", themeMap, baseMap)
  return parse(raw)   // #hex de 3/6 dígitos, o rgba(r,g,b,a)
```
Umbrales: texto normal **≥ 4.5**; texto grande / borde de foco **≥ 3.0**. Todos los pares de
este gate son texto normal ⇒ umbral 4.5. Fondos translúcidos (los `--status-*-bg` y
`--status-neutral-bg`) se componen sobre `--bg-base` del tema antes de medir.

**Implementación** `themeContrast.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import * as fs from "fs";

const THEME = fs.readFileSync(new URL("../theme.css", import.meta.url), "utf-8");

function block(selector: RegExp): Record<string, string> {
  const m = THEME.match(selector);
  const body = m ? m[1] : "";
  const map: Record<string, string> = {};
  for (const line of body.split(";")) {
    const mm = line.match(/(--[a-z0-9-]+)\s*:\s*(.+)$/i);
    if (mm) map[mm[1]] = mm[2].trim();
  }
  return map;
}
const BASE = block(/:root\s*\{([\s\S]*?)\n\}/);                       // dark (base)
const LIGHT = block(/:root\[data-theme="light"\]\s*\{([\s\S]*?)\n\}/); // light

function toRgba(v: string): [number, number, number, number] {
  const s = v.trim();
  if (s.startsWith("#")) {
    let h = s.slice(1);
    if (h.length === 3) h = h.split("").map((c) => c + c).join("");
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16), 1];
  }
  const m = s.match(/rgba?\(([^)]+)\)/)!;
  const p = m[1].split(",").map((x) => parseFloat(x.trim()));
  return [p[0], p[1], p[2], p[3] ?? 1];
}
function resolveColor(token: string, theme: Record<string, string>): [number, number, number, number] {
  const raw = theme[token] ?? BASE[token];
  const varRef = raw.match(/^var\((--[a-z0-9-]+)\)$/i);
  if (varRef) return resolveColor(varRef[1], theme);
  return toRgba(raw);
}
function lin(c: number) { const x = c / 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }
function lum([r, g, b]: number[]) { return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b); }
function composite(fg: number[], base: number[]) {
  const a = fg[3];
  return [0, 1, 2].map((i) => Math.round(fg[i] * a + base[i] * (1 - a)));
}
function ratio(fgTok: string, bgTok: string, theme: Record<string, string>): number {
  const base = resolveColor("--bg-base", theme).slice(0, 3);
  const fg = resolveColor(fgTok, theme).slice(0, 3);
  const bgc = resolveColor(bgTok, theme);
  const bg = bgc[3] >= 1 ? bgc.slice(0, 3) : composite(bgc, base);
  const L1 = lum(fg), L2 = lum(bg);
  return (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
}

// Lista CONGELADA de pares (fg, bg). Ver plan 141 § 6.
const PAIRS: Array<[string, string]> = [
  ["--text-primary", "--bg-base"], ["--text-primary", "--bg-panel"], ["--text-primary", "--bg-elev"],
  ["--text-muted", "--bg-base"], ["--text-muted", "--bg-panel"],
  ["--accent", "--bg-base"], ["--accent-hot", "--bg-base"],
  ["--success", "--bg-base"], ["--warn", "--bg-base"], ["--danger", "--bg-base"],
  ["--agent-business", "--bg-base"], ["--agent-functional", "--bg-base"], ["--agent-technical", "--bg-base"],
  ["--agent-developer", "--bg-base"], ["--agent-qa", "--bg-base"],
  ["--status-success-text", "--status-success-bg"], ["--status-warning-text", "--status-warning-bg"],
  ["--status-danger-text", "--status-danger-bg"], ["--status-info-text", "--status-info-bg"],
  ["--status-neutral-text", "--status-neutral-bg"],
  ["--text-on-solid", "--status-success-solid"], ["--text-on-warn", "--status-warning-solid"],
  ["--text-on-solid", "--status-danger-solid"], ["--text-on-solid", "--status-info-solid"],
];
const AA = 4.5;

// Excepciones DARK conocidas y documentadas (§ 6): texto blanco sobre solids brillantes
// del 138. El dark es byte-idéntico ⇒ NO se "arreglan". Se pinnea el ratio como tripwire.
const DARK_SHORTFALLS: Record<string, number> = {
  "--text-on-solid|--status-success-solid": 2.28,
  "--text-on-solid|--status-danger-solid": 3.76,
  "--text-on-solid|--status-info-solid": 3.68,
};

describe("Plan 141 F3 — gate WCAG AA modo CLARO (estricto)", () => {
  it("los 24 pares cumplen AA (>= 4.5) en el tema claro", () => {
    const fails = PAIRS
      .map(([f, b]) => [f, b, ratio(f, b, LIGHT)] as const)
      .filter(([, , r]) => r < AA);
    expect(fails.map(([f, b, r]) => `${f}/${b}=${r.toFixed(2)}`)).toEqual([]);
  });
});

describe("Plan 141 F3 — gate WCAG AA modo OSCURO (con excepciones frozen)", () => {
  it("todo par cumple AA salvo las 3 excepciones documentadas", () => {
    const unexpected = PAIRS
      .map(([f, b]) => [`${f}|${b}`, ratio(f, b, BASE)] as const)
      .filter(([key, r]) => r < AA && !(key in DARK_SHORTFALLS));
    expect(unexpected.map(([k, r]) => `${k}=${r.toFixed(2)}`)).toEqual([]);
  });
  it("las excepciones dark siguen en su ratio documentado (tripwire anti-drift)", () => {
    for (const [key, expected] of Object.entries(DARK_SHORTFALLS)) {
      const [f, b] = key.split("|");
      expect(Math.abs(ratio(f, b, BASE) - expected)).toBeLessThan(0.1);
    }
  });
});

// [ADICIÓN ARQUITECTO v2] — anti-drift de color base↔claro (gate mecánico del contrato §12).
describe("Plan 141 F3 — anti-drift de color base ↔ tema claro", () => {
  it("todo token con valor de color del :root base está re-apuntado en claro (salvo invariantes de texto-sobre-solid)", () => {
    const isColor = (v: string) => /#[0-9a-fA-F]|rgba?\(/.test(v);
    // Invariantes a propósito: texto que va SIEMPRE del mismo color sobre solids (§6).
    // --status-neutral-text se auto-themea (var(--text-muted)) ⇒ isColor=false ⇒ excluido.
    const INVARIANT = new Set(["--text-on-solid", "--text-on-warn"]);
    const drift = Object.keys(BASE)
      .filter((k) => isColor(BASE[k]) && !INVARIANT.has(k) && !(k in LIGHT))
      .sort();
    // Si `drift` NO está vacío: agregá cada token al bloque :root[data-theme="light"] de
    // theme.css (y a REQUIRED de themeLightTokens.test.ts). Sólo va a INVARIANT si es texto
    // invariante sobre un solid. Esto impide que un plan futuro introduzca un color dark-only.
    expect(drift, `Tokens de color sin re-apuntar en claro: ${drift.join(", ")}`).toEqual([]);
  });
});
```

**Casos borde:**
- `--status-neutral-text` = `var(--text-muted)` ⇒ `resolveColor` sigue la referencia: en dark
  da `#8b949e`, en light hereda `--text-muted` claro `#57606a`. Cubierto por `resolveColor`.
- El regex de bloque usa `\n\}` para cerrar en la llave a inicio de línea; el `:root` base y
  el bloque claro terminan así (llave sola). Verificar tras F2 que ambos matchean.
- `--text-on-solid`/`--text-on-warn` no están en el bloque claro (invariantes) ⇒
  `resolveColor` los toma de la base (`#ffffff` / `#1c1810`), correcto para ambos temas.

**Paso final (verde):** `npx vitest run src/__tests__/themeContrast.test.ts` y `npx tsc --noEmit`.

**Criterio de aceptación (binario):** ambos exit 0 (light 0 fallos; dark 0 fallos
inesperados; 3 excepciones en su valor).
**Flag:** sin flag. **Runtime:** presentación pura, idéntico, fallback N/A.
**Trabajo del operador:** ninguno.
**Staging:** `git add -- "src/__tests__/themeContrast.test.ts"`

---

### F4 — Selector de tema en Configuración → sub-tab "Apariencia"

**Objetivo (1 frase):** exponer el control de 3 valores en Settings, que aplica el tema al
instante sin re-montar la app. **Valor:** la única superficie opt-in; activa toda la mecánica
de F0-F2.

**Archivos:**
- CREAR `frontend/src/components/AppearanceSettings.tsx`
- CREAR `frontend/src/components/AppearanceSettings.module.css`
- EDITAR `frontend/src/pages/SettingsPage.tsx`
- CREAR `frontend/src/components/__tests__/AppearanceSettings.test.ts`

**Pre-flight crítico:** `git status -- "src/pages/SettingsPage.tsx"`. El plan 134 F6 toca
este archivo (sub-tab Notificaciones). Si aparece WIP sin commitear ajeno a este plan → STOP.
Las ediciones de este plan anclan por el TEXTO `Playground IA`/`playground`, que el 134 no
toca; si igual hubiera conflicto, resolver a mano preservando ambos sub-tabs.

**Paso 1 (TDD, rojo)** — `AppearanceSettings.test.ts` (fs+regex + import puro, sin RTL):
```ts
import { describe, it, expect } from "vitest";
import * as fs from "fs";
import { THEME_OPTIONS } from "../AppearanceSettings";

const cmp = fs.readFileSync(new URL("../AppearanceSettings.tsx", import.meta.url), "utf-8");
const css = fs.readFileSync(new URL("../AppearanceSettings.module.css", import.meta.url), "utf-8");
const page = fs.readFileSync(new URL("../../pages/SettingsPage.tsx", import.meta.url), "utf-8");

describe("Plan 141 F4 — opciones del selector", () => {
  it("expone exactamente dark/light/system en ese orden", () => {
    expect(THEME_OPTIONS.map((o) => o.value)).toEqual(["dark", "light", "system"]);
  });
});

describe("Plan 141 F4 — el componente aplica el tema sin re-montar", () => {
  it("usa setTheme y readStoredChoice del controlador", () => {
    expect(cmp).toContain("setTheme");
    expect(cmp).toContain("readStoredChoice");
  });
  it("es un radiogroup accesible", () => {
    expect(cmp).toContain('role="radiogroup"');
    expect(cmp).toContain('type="radio"');
  });
  it("NO usa estilos inline (ratchet §10.3 del 138)", () => {
    expect(cmp.includes("style={{")).toBe(false);
  });
  it("el CSS del panel no hardcodea hex (usa tokens)", () => {
    expect(/#[0-9a-fA-F]{3,8}\b/.test(css)).toBe(false);
  });
});

describe("Plan 141 F4 — cableado en SettingsPage", () => {
  it("agrega el sub-tab appearance con su botón, contenido e import", () => {
    expect(page).toContain('"appearance"');
    expect(page).toContain("Apariencia");
    expect(page).toContain("<AppearanceSettings");
    expect(page).toContain("import AppearanceSettings");
  });
});
```

**Paso 2 (rojo):** falla — faltan los archivos y el cableado.

**Paso 3 — crear `AppearanceSettings.tsx`** VERBATIM:
```tsx
import { useState } from "react";
import { readStoredChoice, setTheme } from "../services/themeController";
import type { ThemeChoice } from "../services/theme";
import styles from "./AppearanceSettings.module.css";

export const THEME_OPTIONS: Array<{ value: ThemeChoice; label: string; hint: string }> = [
  { value: "dark", label: "Oscuro", hint: "Tema oscuro (por defecto)." },
  { value: "light", label: "Claro", hint: "Tema claro de alto contraste." },
  { value: "system", label: "Sistema", hint: "Sigue la preferencia del sistema operativo." },
];

export default function AppearanceSettings() {
  const [choice, setChoice] = useState<ThemeChoice>(() => readStoredChoice());

  const pick = (value: ThemeChoice) => {
    setChoice(value);
    setTheme(value); // aplica al instante, sin re-montar la app
  };

  return (
    <div className={styles.panel}>
      <p className={styles.intro}>
        Elegí el tema de la interfaz. El cambio es inmediato y se recuerda entre sesiones.
      </p>
      <div className={styles.group} role="radiogroup" aria-label="Tema de la interfaz">
        {THEME_OPTIONS.map((opt) => (
          <label
            key={opt.value}
            className={`${styles.option} ${choice === opt.value ? styles.active : ""}`}
          >
            <input
              type="radio"
              name="stacky-theme"
              value={opt.value}
              checked={choice === opt.value}
              onChange={() => pick(opt.value)}
              className={styles.radio}
            />
            <span className={styles.optLabel}>{opt.label}</span>
            <span className={styles.optHint}>{opt.hint}</span>
          </label>
        ))}
      </div>
    </div>
  );
}
```

**Paso 4 — crear `AppearanceSettings.module.css`** (SOLO tokens, CERO hex):
```css
.panel { padding: var(--space-6); display: flex; flex-direction: column; gap: var(--space-5); }
.intro { color: var(--text-muted); font-size: var(--text-sm); margin: 0; }
.group { display: flex; flex-direction: column; gap: var(--space-3); max-width: 480px; }
.option {
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-rows: auto auto;
  column-gap: var(--space-4);
  align-items: center;
  padding: var(--space-4) var(--space-5);
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-panel);
  cursor: pointer;
  transition: border-color var(--duration-fast) var(--ease-standard),
              background var(--duration-fast) var(--ease-standard);
}
.option:hover { border-color: var(--text-faint); }
.option.active { border-color: var(--accent); background: var(--bg-elev); }
.radio { grid-row: 1 / span 2; margin: 0; }
.optLabel { color: var(--text-primary); font-weight: var(--weight-semibold); font-size: var(--text-md); }
.optHint { grid-column: 2; color: var(--text-muted); font-size: var(--text-xs); }
```

**Paso 5 — editar `SettingsPage.tsx`.** Cuatro ediciones puntuales:

(a) Import (junto a los otros imports de componentes, tras `import LocalLlmPlaygroundPanel`):
```tsx
import AppearanceSettings from "../components/AppearanceSettings";
```
(b) Ampliar el tipo `SubTab` agregando `| "appearance"` al final:
```tsx
type SubTab = "flow" | "sections" | "client-profile" | "transfer" | "webhooks" | "harness" | "playground" | "appearance";
```
(c) Botón: inmediatamente DESPUÉS del `<button>` cuyo texto es `Playground IA` (el que setea
`"playground"`), insertar:
```tsx
        <button
          className={`${styles.subTab} ${sub === "appearance" ? styles.active : ""}`}
          onClick={() => setSub("appearance")}
        >
          Apariencia
        </button>
```
(d) Contenido: inmediatamente DESPUÉS de la línea
`{sub === "playground" && <LocalLlmPlaygroundPanel />}`, insertar:
```tsx
        {sub === "appearance" && <AppearanceSettings />}
```

**Casos borde:**
- No se reutiliza ningún store global: el tema se aplica imperativamente sobre `<html>`. El
  `useState(readStoredChoice)` solo refleja el radio seleccionado. En modo `system`, si el
  SO cambia, el efectivo cambia pero la ELECCIÓN sigue siendo `system` (el radio no se mueve;
  correcto).
- El componente no llama a ningún endpoint: es 100 % local (a diferencia de otros paneles de
  Settings). Sin dependencia de backend ⇒ paridad total de runtimes.

**Paso 6 (verde):** `npx vitest run src/components/__tests__/AppearanceSettings.test.ts`,
`npx vitest run src/__tests__/uiDebtRatchet.test.ts` (el nuevo `.tsx`/`.module.css` no debe
subir el ratchet: 0 hex, 0 inline style) y `npx tsc --noEmit`.

**Criterio de aceptación (binario):** los 3 comandos exit 0; el sub-tab "Apariencia" existe
en el código con las 3 opciones.
**Flag:** sin flag (§3.1). **Runtime:** presentación pura, idéntico, fallback N/A.
**Trabajo del operador:** OPCIONAL — 2 clics (Configuración → Apariencia → elegir tema).
**Staging:** `git add -- "src/components/AppearanceSettings.tsx" "src/components/AppearanceSettings.module.css" "src/pages/SettingsPage.tsx" "src/components/__tests__/AppearanceSettings.test.ts"`

---

### F5 — Accesibilidad visual global: `:focus-visible` + `prefers-reduced-motion`

**Objetivo (1 frase):** foco visible consistente por teclado y respeto a la preferencia de
reducir movimiento, globalmente y con baja especificidad. **Valor:** cumplimiento WCAG
2.4.7 (foco visible) y 2.3.3/2.2.2 (movimiento) transversal, sin tocar componente por
componente.

**Archivos:**
- EDITAR `frontend/src/theme.css`
- CREAR `frontend/src/__tests__/a11yCss.test.ts`

**Paso 1 (TDD, rojo)** — `a11yCss.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import * as fs from "fs";

const THEME = fs.readFileSync(new URL("../theme.css", import.meta.url), "utf-8");

describe("Plan 141 F5 — foco visible global", () => {
  it("hay una regla :focus-visible que usa el token --focus-ring", () => {
    expect(THEME).toContain(":focus-visible");
    expect(THEME).toContain("box-shadow: var(--focus-ring)");
  });
  it("el foco de inputs usa el token (no un rgba hardcodeado)", () => {
    // input:focus ahora usa var(--focus-ring); el rgba viejo desaparece.
    expect(THEME).toContain("box-shadow: var(--focus-ring)");
    expect(THEME).not.toContain("box-shadow: 0 0 0 3px rgba(56, 139, 253, 0.25)");
  });
});

describe("Plan 141 F5 — prefers-reduced-motion global", () => {
  it("neutraliza animaciones y transiciones (incluye spinners infinitos)", () => {
    expect(THEME).toContain("@media (prefers-reduced-motion: reduce)");
    expect(THEME).toContain("animation-iteration-count: 1 !important");
    expect(THEME).toContain("transition-duration: 0.01ms !important");
  });
});
```

**Paso 2 (rojo):** falla — las reglas no existen.

**Paso 3 — editar `theme.css`.** Dos ediciones:

(a) En la regla `input, textarea, select:focus` (hoy `theme.css:102-108`), reemplazar la
línea `box-shadow: 0 0 0 3px rgba(56, 139, 253, 0.25);` por `box-shadow: var(--focus-ring);`.
Es BYTE-IDÉNTICO en dark (`--focus-ring` dark = `0 0 0 3px rgba(56, 139, 253, 0.25)`) y hace
que el foco de inputs siga el tema en claro. No tocar la línea `border-color: var(--accent);`.

(b) Agregar al FINAL de `theme.css` (tras la sección Utilities) el bloque VERBATIM:
```css

/* ─── Accesibilidad visual (Plan 141 F5) ──────────────────────── */

/* Foco visible por teclado en cualquier control interactivo. Baja especificidad
   (:where = 0) para que los estilos de foco por componente puedan sobreescribirlo.
   Usa el token --focus-ring del plan 138 (re-apuntado por tema en 141 F2). */
:where(a, button, input, textarea, select, [tabindex], [role="button"], [role="tab"]):focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: var(--focus-ring);
}

/* Respeta la preferencia del SO de reducir movimiento. Neutraliza transiciones y
   animaciones (incluidos los spinners infinitos, ej. RunButton.module.css) sin
   redefinir los tokens --duration-*, que siguen siendo la fuente de verdad del
   movimiento cuando NO se pide reducirlo. El !important gana incluso a estilos
   inline (ej. el Spinner del plan 138). Patrón WCAG SC 2.2.2 / 2.3.3. */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

**Paso 4 (verde):** `npx vitest run src/__tests__/a11yCss.test.ts`,
`npx vitest run src/__tests__/themeTokens.test.ts` (sigue verde: no tocamos tokens),
`npx vitest run src/__tests__/uiDebtRatchet.test.ts` (theme.css fuera del ratchet) y
`npx tsc --noEmit`.

**Criterio de aceptación (binario):** los 4 comandos exit 0.
**Flag:** sin flag (§3.1 — corrección invisible para quien no usa teclado / reduced-motion).
**Runtime:** presentación pura, idéntico, fallback N/A. **Trabajo del operador:** ninguno.
**Staging:** `git add -- "src/theme.css" "src/__tests__/a11yCss.test.ts"`

**Nota de especificidad (§5.6):** las reglas locales preexistentes de foco
(`devops.module.css:249-250` `[role="tab"]:focus-visible`, `HarnessFlagsPanel.module.css`
`.toggle input:focus-visible`) tienen MAYOR especificidad que la regla global `:where(...)`
(0,1,0) ⇒ ganan y no cambian. La regla global solo agrega foco visible a los controles que
HOY no tienen ninguno (ej. los `<button>` genéricos, `theme.css:69`). El `input:focus`
(0,1,1) preexistente sigue ganando sobre el `:focus-visible` global, así que los inputs
conservan su ring (ahora tokenizado). Cero regresión en dark.

---

## § 6. Gate de contraste — lista congelada de pares y resultados verificados

Ratios computados el 2026-07-15 con la fórmula WCAG de F3 (fondos translúcidos compuestos
sobre `--bg-base` del tema). **Umbral: ≥ 4.5:1 (texto normal).**

| # | Primer plano | Fondo | Dark | Light |
|---|---|---|---|---|
| 1 | `--text-primary` | `--bg-base` | 16.02 | 15.80 |
| 2 | `--text-primary` | `--bg-panel` | 14.64 | 14.84 |
| 3 | `--text-primary` | `--bg-elev` | 12.88 | 13.55 |
| 4 | `--text-muted` | `--bg-base` | 6.15 | 6.39 |
| 5 | `--text-muted` | `--bg-panel` | 5.62 | 6.00 |
| 6 | `--accent` | `--bg-base` | 5.66 | 5.19 |
| 7 | `--accent-hot` | `--bg-base` | 7.49 | 7.59 |
| 8 | `--success` | `--bg-base` | 7.45 | 5.08 |
| 9 | `--warn` | `--bg-base` | 7.50 | 4.87 |
| 10 | `--danger` | `--bg-base` | 5.65 | 5.36 |
| 11 | `--agent-business` | `--bg-base` | 5.64 | 5.05 |
| 12 | `--agent-functional` | `--bg-base` | 7.47 | 5.03 |
| 13 | `--agent-technical` | `--bg-base` | 5.66 | 5.19 |
| 14 | `--agent-developer` | `--bg-base` | 7.45 | 5.08 |
| 15 | `--agent-qa` | `--bg-base` | 7.50 | 4.87 |
| 16 | `--status-success-text` | `--status-success-bg` | 8.10 | 6.56 |
| 17 | `--status-warning-text` | `--status-warning-bg` | 8.36 | 6.25 |
| 18 | `--status-danger-text` | `--status-danger-bg` | 5.73 | 5.70 |
| 19 | `--status-info-text` | `--status-info-bg` | 8.51 | 5.61 |
| 20 | `--status-neutral-text` | `--status-neutral-bg` | 5.37 | 5.71 |
| 21 | `--text-on-solid` | `--status-success-solid` | **2.28 ✗** | 5.08 |
| 22 | `--text-on-warn` | `--status-warning-solid` | 8.23 | 5.63 |
| 23 | `--text-on-solid` | `--status-danger-solid` | **3.76 ✗** | 5.36 |
| 24 | `--text-on-solid` | `--status-info-solid` | **3.68 ✗** | 5.19 |

**Modo CLARO:** 24/24 cumplen AA (mínimo 4.87). Gate estricto.

**Excepciones DARK documentadas (filas 21, 23, 24):** texto blanco (`--text-on-solid`) sobre
los solids brillantes tipo Tailwind-500 del 138 NO alcanza 4.5:1. **NO se corrigen**: el tema
oscuro debe seguir byte-idéntico (los solids son contrato congelado del 138 §10.1). El gate
las registra en `DARK_SHORTFALLS` con su ratio exacto (tripwire: si el 138 cambiara un solid,
el test rompe y fuerza revisión consciente). Nótese que el **tema claro resuelve estas 3
deficiencias** (solids más oscuros ⇒ texto blanco AA). Fila 22 usa `--text-on-warn` (texto
oscuro) a propósito, y sí cumple en ambos temas.

---

## § 7. Orden de implementación

1. **F0** — núcleo puro (`theme.ts` + test). Sin impacto visual.
2. **F1** — controlador + `main.tsx` + anti-FOUC en `index.html`. Dormido (default dark).
3. **F2** — paleta clara en `theme.css` + retiro de la aserción del 138 + test del bloque.
4. **F3** — gate de contraste (test).
5. **F4** — selector en Settings (activa todo lo anterior). Debe ir DESPUÉS de F2 para que
   elegir "Claro" tenga efecto visible.
6. **F5** — accesibilidad global (independiente; puede ir en cualquier momento tras F2 porque
   usa `--focus-ring`, que ya existe desde el 138).

Cada fase deja la suite verde por sí sola. F0-F3 y F5 son invisibles (byte-idéntico dark)
hasta que F4 expone el selector: propiedad deliberada de despliegue seguro.

---

## § 8. Definition of Done (global)

- [ ] `npx vitest run src/services/__tests__/theme.test.ts` exit 0 (F0).
- [ ] `npx vitest run src/__tests__/themeBootstrap.test.ts` exit 0 (F1).
- [ ] `npx vitest run src/__tests__/themeLightTokens.test.ts` exit 0 (F2).
- [ ] `npx vitest run src/__tests__/themeTokens.test.ts` exit 0 (F2, aserción invertida).
- [ ] `npx vitest run src/__tests__/themeContrast.test.ts` exit 0 (F3).
- [ ] `npx vitest run src/components/__tests__/AppearanceSettings.test.ts` exit 0 (F4).
- [ ] `npx vitest run src/__tests__/a11yCss.test.ts` exit 0 (F5).
- [ ] `npx vitest run src/__tests__/uiDebtRatchet.test.ts` exit 0 (ratchet no sube).
- [ ] `npx tsc --noEmit` exit 0.
- [ ] `git status -- package.json` limpio (cero dependencias nuevas).
- [ ] `git status` no muestra archivos modificados fuera de los listados en cada fase.
- [ ] Con `stacky.ui.theme` ausente, la app renderiza EXACTAMENTE igual que hoy (dark).
- [ ] Smoke manual (§ 11) completo.

---

## § 9. Riesgos y mitigaciones

| Riesgo | Sev | Mitigación |
|---|---|---|
| Drift entre el snippet anti-FOUC (index.html) y `resolveTheme` (theme.ts). | Media | `themeBootstrap.test.ts` (F1) verifica los literales clave; el snippet es minúsculo y está comentado como "sync con theme.ts". Ambos codifican la misma tabla de 3 valores. |
| El 138 no está implementado cuando se implementa el 141. | Alta | Pre-flight de F2 hace STOP si `themeTokens.test.ts` no existe. El plan declara la dependencia en el encabezado. |
| Colisión con el sub-tab "Notificaciones" del plan 134 F6 en `SettingsPage.tsx`. | Media | Anclaje por TEXTO (`Playground IA`/`playground`), no por línea; pre-flight `git status` del archivo. Ambos sub-tabs coexisten (uniones de tipo aditivas). |
| Superficies legacy con hex Tailwind hardcodeado (1.231 hex, §2.4 del 138) se ven imperfectas en claro. | Media | DEGRADACIÓN DECLARADA (§10). Por eso el default sigue dark y el claro es opt-in. La migración de los hex al ratchet del 138 (planes 139/140) reduce el gap con el tiempo; NO es de este plan. |
| `dbcompare.module.css` sigue el SO, no `data-theme` ⇒ inconsistencia si operador elige claro con SO en oscuro. | Baja | Documentado en §10 (fuera de scope). Es un componente detrás de flag; no afecta la operación principal. |
| La regla global `:focus-visible` quita el `outline` nativo; si un ancestro tiene `overflow:hidden` el ring por box-shadow podría recortarse. | Baja | Mismo patrón que el app ya usa para inputs (theme.css:107). Componentes con overflow ya definen su propio `outline` (devops.module.css:250) y ganan por especificidad. |
| `animation-iteration-count: 1` deja un spinner en su fotograma final. | Baja | Con `animation-duration: 0.01ms` completa al instante; keyframes de rotación terminan en 360° = estado inicial. Comportamiento esperado de reduced-motion. |

---

## § 10. Fuera de scope (explícito)

- **Unificar las dos paletas** (GitHub-dark de `theme.css` vs Tailwind dominante de los
  módulos, §2.4 del 138). Este plan mapea TOKENS, no los 1.231 hex legacy. Las superficies
  aún no migradas al ratchet del 138 pueden verse imperfectas en tema claro; **por eso el
  default NO cambia y sigue siendo `dark`.**
- **Migrar `dbcompare.module.css`** (y cualquier `@media (prefers-color-scheme)` local) al
  atributo `data-theme`. Hoy sigue el SO; queda para un plan posterior.
- **Persistencia del tema en backend** (`/api/preferences`). El tema es 100 % local
  (localStorage), coherente con mono-operador sin auth. No se sincroniza entre máquinas.
- **Temas adicionales** (alto contraste extremo, sepia, daltonismo). Solo dark/light/system.
- **Cambiar el default a `system`.** El default es `dark` por la restricción byte-idéntico.
- **Tocar las primitivas UI del 138** o adoptarlas en pantallas (eso es 139/140).

---

## § 11. Smoke manual final (pasos numerados)

Con el frontend corriendo (`npm run dev` en `Stacky Agents/frontend`):

1. **Default byte-idéntico:** abrir la app con `localStorage` limpio. Debe verse EXACTAMENTE
   como hoy (dark). En DevTools, `document.documentElement.getAttribute("data-theme")` = `"dark"`.
2. **Cambiar a Claro:** Configuración → Apariencia → "Claro". La UI cambia a claro al
   instante, sin recargar ni parpadear. `data-theme` = `"light"`.
3. **Persistencia:** recargar (F5). Sigue en claro, SIN flash oscuro previo (anti-FOUC).
4. **Cambiar a Sistema, SO en oscuro:** elegir "Sistema" con el SO en modo oscuro ⇒ app
   oscura. Cambiar el SO a claro EN VIVO (sin recargar) ⇒ la app pasa a claro sola (listener
   `matchMedia`). Volver el SO a oscuro ⇒ app oscura.
5. **Volver a Oscuro:** elegir "Oscuro" ⇒ app oscura aunque el SO esté en claro.
6. **Foco por teclado:** con Tab, recorrer botones/inputs/tabs. Cada control muestra un anillo
   de foco visible (azul) en ambos temas. Con el mouse (click) NO aparece el anillo
   (`:focus-visible`). **Verificar además (C2):** NO hay doble anillo (regla global `:where`
   + regla del componente) en tabs de DevOps/HarnessFlags (que ya tienen foco propio), y el
   anillo NO queda recortado por `overflow:hidden` en tarjetas/drawers.
7. **Reduced-motion:** activar "Reducir movimiento" en el SO. Lanzar un run (spinner de
   RunButton) ⇒ el spinner NO gira (queda estático); las transiciones de hover/tabs son
   instantáneas. Desactivar ⇒ vuelven las animaciones.
8. **Contraste (spot check):** en claro, verificar que chips de estado (éxito/alerta/error),
   texto atenuado y links se leen sin esfuerzo sobre las superficies claras.

---

## § 12. Contrato congelado para futuros planes

- Clave localStorage: `stacky.ui.theme` (valores `dark`|`light`|`system`, default `dark`).
- Atributo DOM: `data-theme` en `<html>` (`document.documentElement`), valores `dark`|`light`.
- Módulo puro: `frontend/src/services/theme.ts` (`resolveTheme`, `normalizeChoice`,
  `THEME_STORAGE_KEY`, tipos `ThemeChoice`/`EffectiveTheme`).
- Controlador: `frontend/src/services/themeController.ts` (`setTheme`, `readStoredChoice`,
  `applyEffectiveTheme`, `initThemeController`).
- Gate: `frontend/src/__tests__/themeContrast.test.ts` — 24 pares frozen + 3 excepciones dark.
  Todo token de color nuevo que sea foreground/background de UI debería sumarse al gate.
- Paleta clara: bloque `:root[data-theme="light"]` en `theme.css` (53 tokens de color). Todo
  token de color nuevo en el `:root` base DEBE re-apuntarse acá o justificarse como invariante.
