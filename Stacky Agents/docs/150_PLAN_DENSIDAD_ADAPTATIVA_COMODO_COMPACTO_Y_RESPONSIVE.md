# Plan 150 — Densidad adaptativa (cómodo / compacto) + responsive de superficies densas

- **Estado:** PROPUESTO v1
- **Autor:** StackyArchitectaUltraEficientCode
- **Fecha:** 2026-07-15
- **Serie:** UX/UI (aterriza DESPUÉS de 138 → 139 → 140 → 141 → 143; y de la serie 132-136)
- **Depende de:** plan 138 v2 (escala de spacing `--space-1..9` + ratchet de deuda), plan 143 v3 (presets de motion `--transition-opacity` / `--duration-base`), plan 141 v3 (dueño de `prefers-reduced-motion` + patrón anti-FOUC `data-theme` en `<head>` + patrón de key localStorage `stacky.ui.*`). **CONSUME los tres por su nombre EXACTO; no redefine ninguno.**
- **Runtimes:** Codex CLI · Claude Code CLI · GitHub Copilot Pro — **100% presentación** (CSS + TSX + HTML + `localStorage`, servido al navegador/webview). Idéntico en los 3; **fallback N/A** (no hay lógica de runtime).
- **Flag:** **sin flag de harness** (presentación pura, aditiva, opt-in por UI; default = look de hoy byte-idéntico; reversible por revert). Justificación por fase abajo. Ninguna de las 4 excepciones duras ON-por-defecto aplica (no hay kill-switch, ni comportamiento de pipeline/runtime, ni seguridad).

---

## 1. Objetivo

Dar al operador **dos densidades de interfaz** —`comodo` (DEFAULT, byte-idéntico a hoy) y `compacto`— mediante un atributo `data-density` en `<html>` que **re-apunta la escala de spacing `--space-*` del plan 138**. Toda superficie que consuma `var(--space-*)` se compacta sola. El plan además **migra a tokens las 2 superficies más densas** (`TicketBoard`, `PMCommandCenter`) para que la compactación sea REAL y visible, y **cierra el hueco responsive** de la superficie más densa (`TicketBoard` tiene 0 media queries y grids con piso `minmax(340px)` que desbordan en pantallas chicas).

Mecanismo espejo EXACTO del `data-theme` del plan 141: bloque base `:root` intacto (comodo), bloque nuevo `:root[data-density="compacto"]` que re-apunta SOLO los 9 tokens `--space-*`; selección por UI persistida en `localStorage` bajo `stacky.ui.density`; aplicación síncrona anti-FOUC en el `<head>`.

### KPIs binarios (medibles)

- **KPI-1:** `npx vitest run src/__tests__/densityTokens.test.ts` exit 0 — la escala base `--space-1..9` queda intacta con sus 9 valores del 138 **y** existe `:root[data-density="compacto"]` que re-apunta EXACTAMENTE esos 9 tokens a los valores compactos congelados (§6 F0), y **ningún otro token** dentro de ese bloque.
- **KPI-2:** `npx vitest run src/services/__tests__/density.test.ts` exit 0 — `normalizeDensity` default `"comodo"`, key congelada `stacky.ui.density`.
- **KPI-3:** `npx vitest run src/__tests__/densityBootstrap.test.ts` exit 0 — snippet anti-FOUC en `index.html <head>` lee `stacky.ui.density` y setea `data-density` síncrono; `main.tsx` cablea el init; el controlador setea el atributo; existe la regla de settle por `opacity`.
- **KPI-4:** `npx vitest run src/pages/__tests__/ticketBoardDensity.test.ts` exit 0 — `TicketBoard.module.css` consume `var(--space-` (≥ 12 ocurrencias, migración real) **y** contiene `@media (max-width: 820px)` con `minmax(0` (fix responsive).
- **KPI-5:** `npx tsc --noEmit` exit 0 **y** `npx vitest run src/__tests__/uiDebtRatchet.test.ts` exit 0 — la migración es ratchet-neutral (no agrega hex ni `style={{`).
- **KPI-6 (byte-idéntico comodo):** sin `stacky.ui.density` en `localStorage` (o `= "comodo"`), `data-density` resuelve `comodo`/ausente ⇒ escala base ⇒ layout pixel-idéntico a hoy. Garantizado por construcción (regla de migración solo-en-escala, §4) + verificado por smoke manual (§9, por el gap RTL/jsdom conocido).

---

## 2. Por qué ahora / gap (evidencia grep, números reales)

Verificación 2026-07-15 sobre `plans-138-141-serie-ux-ui`:

- **La app tiene UNA sola densidad fija.** El 138 define la escala `--space-1..9` (`theme.css:630-639`, valores `2,4,6,8,12,16,24,32,48`) pero **no hay forma de compactarla**: no existe ningún `data-density` en el código (`grep -rn "data-density" src` → 0).
- **Superficies densas que desperdician pantalla:** `TicketBoard.module.css` = **1042 líneas, 102** declaraciones `padding|margin|gap`; `PMCommandCenter.module.css` = **102**; `AgentHistoryPage.module.css` = **86** (ranking real por `grep -cE "padding|margin|gap"`). Todas con px hardcodeado.
- **Hueco responsive real:** `TicketBoard.module.css` tiene **0 `@media`** (`grep -c "@media"` → 0) y usa `grid-template-columns: repeat(auto-fill, minmax(340px, 1fr))` (línea ~156) y `minmax(320px, 1fr)` (línea ~992). Bajo ~360px de viewport el piso de 340px **desborda horizontalmente**. Es la superficie más densa y la única sin breakpoint.
- **El 138 NO hace big-bang migration** (138:150 "sin exigir una migración big-bang"; solo 3 migraciones ejemplares). Por eso `var(--space-` en el código HOY = **0 ocurrencias**. ⇒ Re-apuntar los tokens NO compacta nada por sí solo: hay que migrar al menos las superficies densas para que la densidad sea visible. Este plan cierra ese paso de forma progresiva y byte-idéntica (§4).

---

## 3. Principios y guardarraíles (NO negociables)

1. **Paridad 3 runtimes:** todo es CSS/TSX/HTML/`localStorage` servido al navegador/webview. Idéntico en Codex CLI, Claude Code CLI y GitHub Copilot Pro. **Fallback N/A.** Se declara por fase.
2. **Cero trabajo extra al operador:** default `comodo` = look de hoy **byte-idéntico**; `compacto` es **opt-in por un toggle en la UI**. Sin pasos nuevos, sin nueva carga de config, backward-compatible. Reversible por revert.
3. **Human-in-the-loop:** el toggle amplifica; nada autónomo, nada proactivo.
4. **Mono-operador sin auth:** preferencia local en `localStorage`; nada de RBAC/multiusuario/backend obligatorio.
5. **No degradar performance:** el cambio de densidad **re-apunta variables CSS ⇒ el reflow es instantáneo por naturaleza** (no se anima layout). El único efecto animado es un settle de `opacity` (propiedad barata, composite/paint) usando el preset `--transition-opacity` del 143; **PROHIBIDO animar `padding`/`margin`/`gap`/`width`/`height`/`top`/`left`** (§143 §4.4). El settle lo neutraliza `prefers-reduced-motion` (141 F5), que este plan **jamás reescribe**.
6. **Consumir, no redefinir:** los tokens `--space-*` (138), `--transition-opacity`/`--duration-base` (143) y el bloque `prefers-reduced-motion`/focus-ring (141 F5) se usan por su nombre EXACTO. Este plan **no crea** tokens de spacing nuevos; solo **re-apunta** los 9 existentes dentro del bloque `[data-density="compacto"]`.

### Anti-frágil (zonas calientes)

`theme.css`, `index.html`, `main.tsx`, `SettingsPage.tsx` y los `.module.css` de features son ZONAS CALIENTES (132/134/135/136/138-143 las tocan). **Todas las anclas son por TEXTO NORMATIVO** (los `:NN` de línea son orientativos). **Pre-flight por fase:** `git status --porcelain -- "<ruta>"` antes de tocar cada archivo; si hay WIP ajeno sin commitear ⇒ **STOP, avisar, no editar**. Ya verificado 2026-07-15: `TicketBoard.tsx` y `ActiveRunsPanel.module.css` tienen WIP (NO se tocan); `TicketBoard.module.css`, `PMCommandCenter.module.css`, `theme.css`, `index.html`, `main.tsx` estaban LIMPIOS. Staging quirúrgico con paths explícitos. **El implementador NO commitea** (lo hace el orquestador).

---

## 4. Regla de migración solo-en-escala (byte-idéntica y determinista)

Migrar px→token en superficies densas debe ser **byte-idéntico en comodo**, si no rompe el guardarraíl 2. La escala 138 es `{2,4,6,8,12,16,24,32,48}`; las superficies densas usan también valores **fuera de escala** (5,7,9,10,11,13,14,18,20,22px — histograma real de `TicketBoard`). Convertir un valor fuera de escala al token más cercano **cambiaría el pixel** ⇒ NO byte-idéntico. Por eso la regla es **solo-en-escala** (sin juicio de "el más cercano"):

**MAPA CONGELADO (comodo px → token):**

| px comodo | token |
|---|---|
| `2px`  | `var(--space-1)` |
| `4px`  | `var(--space-2)` |
| `6px`  | `var(--space-3)` |
| `8px`  | `var(--space-4)` |
| `12px` | `var(--space-5)` |
| `16px` | `var(--space-6)` |
| `24px` | `var(--space-7)` |
| `32px` | `var(--space-8)` |
| `48px` | `var(--space-9)` |

**REGLA (aplicar SOLO a declaraciones `padding`, `margin`, `gap`, `row-gap`, `column-gap`):**

1. Tomar TODOS los valores de longitud de la declaración (1 a 4 valores del shorthand).
2. **Si y solo si CADA valor es exactamente uno del MAPA CONGELADO, o el literal `0`**, reemplazar cada longitud por su `var(--space-N)` (el `0` queda `0`, sin token).
3. En cualquier otro caso (algún valor fuera de escala, `%`, `em`, `auto`, `calc(...)`, etc.), **dejar la declaración byte-por-byte SIN TOCAR**.
4. **NUNCA** tocar `border`, `border-width`, `width`, `height`, `min-*`, `max-*`, `flex-basis`, `border-radius`, `inset`, `top/left/right/bottom` ni ninguna propiedad que no sea de las 5 de spacing. (Los `1px` de borde quedan `1px`.)

Consecuencias: en comodo `var(--space-3)` computa `6px` = idéntico; en compacto computa `4px` = compacta. La densidad se ve en el spacing estructural dominante (que SÍ está en escala: `gap:8/12/16`, `padding:8`, `padding:16px 24px`, `padding:12px 24px`), y los detalles decorativos fuera de escala (chips `2px 5px`) quedan literales — aceptable, casi no afectan densidad. **Ratchet-neutral:** no agrega hex ni `style={{`.

---

## 5. Glosario

- **`data-density`**: atributo en `<html>` (`document.documentElement`). Ausente o `"comodo"` ⇒ escala base (byte-idéntico a hoy). `"compacto"` ⇒ activa `:root[data-density="compacto"]`.
- **`Density`**: tipo `"comodo" | "compacto"` (sin variante `system`: no hay señal del SO para densidad).
- **`stacky.ui.density`**: clave `localStorage` (CONGELADA) que guarda la elección del operador. Espejo dotted de `stacky.ui.theme` (141).
- **`data-density-animating`**: atributo transitorio en `<html>` durante ~200ms tras un toggle; dispara el settle de `opacity` (§F2). Ausente en reposo.
- **Escala comodo**: `--space-1..9` = `2,4,6,8,12,16,24,32,48px` (base 138, INTACTA).
- **Escala compacto**: re-apunte congelado de esos 9 tokens (§6 F0).

---

## 6. Fases

**Comando de tests (idioma de la casa):** `npx vitest run <ruta-relativa-del-test>` desde `Stacky Agents/frontend`. **Gate de tipos:** `npx tsc --noEmit`. Los tests que inspeccionan `.tsx`/`.html`/`.css` usan `fs.readFileSync` + regex sobre el contenido (idioma 138/141/143; RTL/jsdom NO está en `package.json` — gap estructural conocido, ver §9).

Orden por dependencia: **F0 → F1 → F2 → F3 → F4 → F5**. F4/F5 dependen solo de F0 (tokens); F3 depende de F1/F2.

---

### F0 — Escala compacta: bloque `:root[data-density="compacto"]` en `theme.css`

**Objetivo (1 frase):** agregar el bloque que re-apunta los 9 tokens `--space-*` a la escala compacta; **dormido** hasta que exista `data-density="compacto"`. **Valor:** habilita toda la compactación con 9 líneas, byte-idéntico mientras nadie active compacto.

**Pre-flight:** `git status --porcelain -- "Stacky Agents/frontend/src/theme.css"` → debe estar limpio (o STOP).

**Archivos:**
- EDITAR `frontend/src/theme.css`
- CREAR `frontend/src/__tests__/densityTokens.test.ts`

**Escala compacta CONGELADA (copiar VERBATIM):**

| token | comodo (base 138, INTACTO) | compacto (150) |
|---|---|---|
| `--space-1` | `2px`  | `2px`  |
| `--space-2` | `4px`  | `3px`  |
| `--space-3` | `6px`  | `4px`  |
| `--space-4` | `8px`  | `6px`  |
| `--space-5` | `12px` | `8px`  |
| `--space-6` | `16px` | `12px` |
| `--space-7` | `24px` | `16px` |
| `--space-8` | `32px` | `24px` |
| `--space-9` | `48px` | `32px` |

**Paso 1 (TDD, rojo) — `densityTokens.test.ts`** (fs+regex sobre `theme.css`):

```ts
import { describe, it, expect } from "vitest";
import fs from "node:fs";

const THEME = fs.readFileSync(new URL("../theme.css", import.meta.url), "utf-8");
const FLAT = THEME.replace(/\s+/g, " ");

// Escala base (138) DEBE seguir intacta.
const BASE: [string, string][] = [
  ["--space-1","2px"],["--space-2","4px"],["--space-3","6px"],
  ["--space-4","8px"],["--space-5","12px"],["--space-6","16px"],
  ["--space-7","24px"],["--space-8","32px"],["--space-9","48px"],
];
// Escala compacta (150), congelada.
const COMPACT: [string, string][] = [
  ["--space-1","2px"],["--space-2","3px"],["--space-3","4px"],
  ["--space-4","6px"],["--space-5","8px"],["--space-6","12px"],
  ["--space-7","16px"],["--space-8","24px"],["--space-9","32px"],
];

describe("Plan 150 F0 — escala de densidad", () => {
  it("la escala base 138 sigue intacta en :root", () => {
    const missing = BASE.filter(([n, v]) => !FLAT.includes(`${n}: ${v};`));
    expect(missing).toEqual([]);
  });

  it("existe el bloque :root[data-density=\"compacto\"]", () => {
    expect(THEME.includes('[data-density="compacto"]')).toBe(true);
  });

  it("el bloque compacto re-apunta los 9 --space-* a los valores congelados", () => {
    // aislar el contenido del bloque compacto
    const m = THEME.match(/\[data-density="compacto"\]\s*\{([^}]*)\}/);
    expect(m).not.toBeNull();
    const block = (m![1]).replace(/\s+/g, " ");
    const missing = COMPACT.filter(([n, v]) => !block.includes(`${n}: ${v};`));
    expect(missing).toEqual([]);
  });

  it("el bloque compacto SOLO toca --space-* (ningún otro token)", () => {
    const m = THEME.match(/\[data-density="compacto"\]\s*\{([^}]*)\}/);
    const decls = (m![1].match(/--[a-z0-9-]+:/g) ?? []);
    const nonSpace = decls.filter((d) => !/^--space-[1-9]:$/.test(d));
    expect(nonSpace).toEqual([]);
  });
});
```

Correr: `npx vitest run src/__tests__/densityTokens.test.ts` → **falla** (no existe el bloque).

**Paso 2 — editar `theme.css`.** Ancla normativa: **después del último bloque de tokens** (tras el `:root` base del 138 y, si ya aterrizó, tras `:root[data-theme="light"]` del 141). Agregar EXACTAMENTE:

```css
/* ─── Plan 150 — Densidad compacta ────────────────────────────────
   Re-apunta SOLO la escala de spacing del plan 138. Dormido salvo que
   <html data-density="compacto">. En comodo (base/ausente) el render es
   byte-idéntico. No toca ningún otro token. */
:root[data-density="compacto"] {
  --space-1: 2px;
  --space-2: 3px;
  --space-3: 4px;
  --space-4: 6px;
  --space-5: 8px;
  --space-6: 12px;
  --space-7: 16px;
  --space-8: 24px;
  --space-9: 32px;
}
```

**Nota de compatibilidad (138/141):** el test `themeTokens.test.ts` (138) valida *presencia* de `--space-N: <base>px;` en el archivo aplanado, no unicidad; el bloque compacto agrega declaraciones adicionales en otro selector y NO rompe ese test (mismo mecanismo que 141 F2 al agregar `[data-theme="light"]`).

**Paso 3 (verde):** `npx vitest run src/__tests__/densityTokens.test.ts` pasa; `npx vitest run src/__tests__/themeTokens.test.ts` (138) sigue verde.

**Criterio de aceptación (binario):** ambos comandos exit 0.
**Flag:** sin flag — bloque dormido, byte-idéntico (no hay `data-density` seteado aún).
**Runtimes:** CSS puro, idéntico en los 3; fallback N/A.
**Staging:** `git add -- "src/theme.css" "src/__tests__/densityTokens.test.ts"`
**Trabajo del operador: ninguno.**

---

### F1 — Núcleo puro `density.ts` (lógica sin DOM)

**Objetivo:** normalizar la elección y congelar la key de `localStorage`, testeable sin DOM. **Valor:** una sola fuente de verdad para la lógica de densidad; espejo de `theme.ts` del 141 F0.

**Archivos:**
- CREAR `frontend/src/services/density.ts`
- CREAR `frontend/src/services/__tests__/density.test.ts`

**Paso 1 (TDD, rojo) — `density.test.ts`:**

```ts
import { describe, it, expect } from "vitest";
import { normalizeDensity, DENSITY_STORAGE_KEY } from "../density";

describe("Plan 150 F1 — density core", () => {
  it("compacto se conserva", () => {
    expect(normalizeDensity("compacto")).toBe("compacto");
  });
  it("comodo se conserva", () => {
    expect(normalizeDensity("comodo")).toBe("comodo");
  });
  it("cualquier otro valor cae a comodo (default byte-idéntico)", () => {
    for (const raw of [null, undefined, "", "COMPACTO", "dense", "x"]) {
      expect(normalizeDensity(raw as any)).toBe("comodo");
    }
  });
  it("la key está congelada", () => {
    expect(DENSITY_STORAGE_KEY).toBe("stacky.ui.density");
  });
});
```

Correr: `npx vitest run src/services/__tests__/density.test.ts` → falla (no existe `../density`).

**Paso 2 — crear `density.ts`:**

```ts
/* Plan 150 F1 — lógica pura de densidad (sin DOM). */
export type Density = "comodo" | "compacto";

/** Clave localStorage CONGELADA (espejo dotted de stacky.ui.theme del 141). */
export const DENSITY_STORAGE_KEY = "stacky.ui.density" as const;

/** Normaliza un valor crudo a Density. Default byte-idéntico: "comodo". */
export function normalizeDensity(raw: string | null | undefined): Density {
  return raw === "compacto" ? "compacto" : "comodo";
}
```

**Paso 3 (verde):** `npx vitest run src/services/__tests__/density.test.ts` exit 0; `npx tsc --noEmit` exit 0.
**Criterio de aceptación (binario):** ambos exit 0.
**Flag:** sin flag — módulo puro sin consumidores.
**Runtimes:** TS puro, idéntico; fallback N/A.
**Staging:** `git add -- "src/services/density.ts" "src/services/__tests__/density.test.ts"`
**Trabajo del operador: ninguno.**

---

### F2 — Controlador DOM + anti-FOUC en `index.html` + wiring en `main.tsx` + settle por `opacity`

**Objetivo:** aplicar la densidad al `<html>` de forma síncrona (anti-FOUC) y en runtime, con un settle de `opacity` al togglear. **Valor:** la elección persiste y se aplica antes del primer paint (sin flash); el cambio se siente suave sin animar layout.

**Pre-flight:** `git status --porcelain -- "Stacky Agents/frontend/index.html" "Stacky Agents/frontend/src/main.tsx" "Stacky Agents/frontend/src/theme.css"` → limpio (o STOP).

**Archivos:**
- CREAR `frontend/src/services/densityController.ts`
- EDITAR `frontend/index.html` (snippet inline en `<head>`)
- EDITAR `frontend/src/main.tsx` (import + init)
- EDITAR `frontend/src/theme.css` (regla de settle `opacity`)
- CREAR `frontend/src/__tests__/densityBootstrap.test.ts`

**Paso 1 (TDD, rojo) — `densityBootstrap.test.ts`** (fs+regex, sin DOM):

```ts
import { describe, it, expect } from "vitest";
import fs from "node:fs";

const HTML  = fs.readFileSync(new URL("../../index.html", import.meta.url), "utf-8");
const MAIN  = fs.readFileSync(new URL("../main.tsx", import.meta.url), "utf-8");
const CTRL  = fs.readFileSync(new URL("../services/densityController.ts", import.meta.url), "utf-8");
const THEME = fs.readFileSync(new URL("../theme.css", import.meta.url), "utf-8");

describe("Plan 150 F2 — anti-FOUC inline en index.html", () => {
  it("hay un <script> inline que lee la key y setea data-density", () => {
    expect(HTML).toContain("stacky.ui.density");
    expect(HTML).toContain("data-density");
  });
});

describe("Plan 150 F2 — wiring en main.tsx", () => {
  it("importa y llama al init del controlador de densidad", () => {
    expect(MAIN).toMatch(/densityController/);
    expect(MAIN).toMatch(/initDensity\s*\(/);
  });
});

describe("Plan 150 F2 — controlador DOM", () => {
  it("setea el atributo data-density en documentElement", () => {
    expect(CTRL).toContain('setAttribute("data-density"');
  });
  it("persiste bajo la key congelada", () => {
    expect(CTRL).toContain("stacky.ui.density");
  });
  it("usa el atributo transitorio de settle", () => {
    expect(CTRL).toContain("data-density-animating");
  });
});

describe("Plan 150 F2 — settle por opacity (cheap prop, §143)", () => {
  it("theme.css tiene la regla de settle con --transition-opacity", () => {
    const flat = THEME.replace(/\s+/g, " ");
    expect(flat).toContain("data-density-animating");
    expect(flat).toContain("var(--transition-opacity)");
  });
});
```

Correr: `npx vitest run src/__tests__/densityBootstrap.test.ts` → falla.

**Paso 2 — crear `densityController.ts`** (efectos DOM; copia el patrón try/catch de `preferences.ts:14-30`, NO importa esos helpers porque son module-private, igual que hace el controlador de tema del 141):

```ts
/* Plan 150 F2 — controlador de densidad (efectos DOM). Lógica pura en density.ts. */
import { normalizeDensity, DENSITY_STORAGE_KEY, type Density } from "./density";

/** Duración del settle de opacity; = --duration-base (0.2s = 200ms) del plan 143. */
const DENSITY_SETTLE_MS = 200;

function readDensity(): Density {
  try {
    return normalizeDensity(localStorage.getItem(DENSITY_STORAGE_KEY));
  } catch {
    return "comodo";
  }
}

function applyDensity(d: Density): void {
  document.documentElement.setAttribute("data-density", d);
}

/** Lee la preferencia y la aplica al <html>. Idempotente; llamar en main.tsx. */
export function initDensity(): void {
  applyDensity(readDensity());
}

/** Cambia densidad: persiste, aplica y dispara el settle de opacity. Sin re-render de React. */
export function setDensity(d: Density): void {
  try {
    localStorage.setItem(DENSITY_STORAGE_KEY, d);
  } catch {
    /* modo privado / storage lleno — se aplica igual en memoria */
  }
  const root = document.documentElement;
  root.setAttribute("data-density-animating", "");
  applyDensity(d);
  window.setTimeout(() => root.removeAttribute("data-density-animating"), DENSITY_SETTLE_MS);
}

/** Lee la densidad actual (para inicializar el estado del toggle). */
export function currentDensity(): Density {
  return readDensity();
}
```

**Paso 3 — snippet anti-FOUC en `index.html`.** Ancla normativa: **dentro de `<head>`, inmediatamente DESPUÉS del `<script>` anti-FOUC de tema del plan 141 F1** (si ya aterrizó); si no aterrizó, **después de los `<link>` de fuentes**. Agregar EXACTAMENTE:

```html
    <script>
      /* Plan 150 — anti-FOUC de densidad: setea data-density antes del primer paint.
         Independiente y order-agnostic respecto del snippet de tema (141). */
      (function () {
        try {
          var d = localStorage.getItem("stacky.ui.density");
          document.documentElement.setAttribute("data-density", d === "compacto" ? "compacto" : "comodo");
        } catch (e) {
          document.documentElement.setAttribute("data-density", "comodo");
        }
      })();
    </script>
```

**Paso 4 — editar `main.tsx`.** Agregar el import junto a los demás y llamar a `initDensity()` antes de `createRoot(...).render(...)` (idempotente respecto del snippet; mantiene el DOM en sync si el snippet no corrió, p. ej. tests):

```ts
import { initDensity } from "./services/densityController";
// ...
initDensity();
```

**Paso 5 — regla de settle en `theme.css`.** Ancla normativa: en la sección de utilidades/reset, agregar EXACTAMENTE (usa SOLO `opacity`, propiedad barata; el reflow por re-apuntar `--space-*` es instantáneo; `prefers-reduced-motion` del 141 F5 neutraliza la transición):

```css
/* Plan 150 — settle de densidad: SOLO opacity (composite/paint, §143 §4.4).
   El reflow por re-apuntar --space-* es instantáneo; este fundido corto lo enmascara.
   La transición vive permanente en #root (barata; opacity solo cambia al togglear).
   141 F5 (prefers-reduced-motion: reduce) la anula ⇒ cambio instantáneo. */
#root { transition: var(--transition-opacity); }
html[data-density-animating] #root { opacity: 0.72; }
```

**Paso 6 (verde):** `npx vitest run src/__tests__/densityBootstrap.test.ts` exit 0; `npx tsc --noEmit` exit 0.

**Criterio de aceptación (binario):** ambos exit 0.
**Casos borde:** `localStorage` inaccesible (modo privado) ⇒ `catch` ⇒ `comodo`. Sin `data-density-animating` en reposo ⇒ `#root` opacity 1, sin costo. Con reduced-motion ⇒ sin fundido (instantáneo).
**Flag:** sin flag — dormido: nadie escribe `stacky.ui.density` hasta F3 ⇒ siempre resuelve `comodo` ⇒ byte-idéntico.
**Runtimes:** HTML/JS/CSS servido al webview, idéntico; fallback N/A.
**Staging:** `git add -- "src/services/densityController.ts" "index.html" "src/main.tsx" "src/theme.css" "src/__tests__/densityBootstrap.test.ts"`
**Trabajo del operador: ninguno.**

---

### F3 — Toggle de densidad en la UI (superficie opt-in)

**Objetivo:** un control `Cómodo / Compacto` en Configuración que llama a `setDensity`. **Valor:** ES la superficie opt-in; hasta acá nadie escribe la key ⇒ todo dormido.

**Pre-flight:** `git status --porcelain -- "Stacky Agents/frontend/src/pages/SettingsPage.tsx"` → limpio (o STOP).

**Archivos:**
- CREAR `frontend/src/components/DensityToggle.tsx`
- EDITAR `frontend/src/pages/SettingsPage.tsx` (montar el toggle)
- CREAR `frontend/src/pages/__tests__/densityToggle.test.ts`

**Paso 1 (TDD, rojo) — `densityToggle.test.ts`** (fs+regex; RTL/jsdom no está disponible, §9):

```ts
import { describe, it, expect } from "vitest";
import fs from "node:fs";

const TOGGLE = fs.readFileSync(new URL("../../components/DensityToggle.tsx", import.meta.url), "utf-8");
const SETTINGS = fs.readFileSync(new URL("../SettingsPage.tsx", import.meta.url), "utf-8");

describe("Plan 150 F3 — DensityToggle", () => {
  it("usa el controlador (setDensity/currentDensity)", () => {
    expect(TOGGLE).toMatch(/setDensity/);
    expect(TOGGLE).toMatch(/currentDensity/);
  });
  it("ofrece ambas densidades", () => {
    expect(TOGGLE).toContain('"comodo"');
    expect(TOGGLE).toContain('"compacto"');
  });
});

describe("Plan 150 F3 — montaje en Settings", () => {
  it("SettingsPage importa y monta DensityToggle", () => {
    expect(SETTINGS).toMatch(/import\s+DensityToggle/);
    expect(SETTINGS).toContain("<DensityToggle");
  });
});
```

Correr: `npx vitest run src/pages/__tests__/densityToggle.test.ts` → falla.

**Paso 2 — crear `DensityToggle.tsx`** (dos botones; sin re-render global — solo estado local para reflejar la selección):

```tsx
/* Plan 150 F3 — toggle de densidad de interfaz. */
import { useState } from "react";
import { currentDensity, setDensity } from "../services/densityController";
import type { Density } from "../services/density";

const OPTIONS: { value: Density; label: string }[] = [
  { value: "comodo",   label: "Cómodo" },
  { value: "compacto", label: "Compacto" },
];

export default function DensityToggle() {
  const [d, setD] = useState<Density>(() => currentDensity());
  const choose = (next: Density) => {
    setDensity(next);
    setD(next);
  };
  return (
    <div role="group" aria-label="Densidad de la interfaz" style={{ display: "flex", gap: "var(--space-3)" }}>
      {OPTIONS.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={d === o.value}
          onClick={() => choose(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
```

> Nota ratchet: este `style={{ ... }}` inline vive en un archivo NUEVO fuera de la lista congelada del 138 (que cubre `theme.css` y las 8 primitivas `ui/`). Si el baseline del ratchet contara este archivo tras mergear, regenerar el baseline con el procedimiento del 138 §5-R2 (`UI_DEBT_REGEN=1 npx vitest run src/__tests__/uiDebtRatchet.test.ts`). Preferible: mover los 2 estilos inline a `DensityToggle.module.css` (`.group { display:flex; gap: var(--space-3); }`) para nacer con deuda 0; si se hace, el test del Paso 1 debe buscar el import del módulo en vez del `style={{`.

**Paso 3 — montar en `SettingsPage.tsx`.** Ancla normativa: montar `<DensityToggle />` en el **panel de preferencias del sub-tab `notifications`** (que hoy ya agrupa toggles de apariencia/preferencia: sonido y notificaciones de escritorio, `SettingsPage.tsx:~330-370`). **Si el plan 141 F4 ya introdujo un sub-tab/sección de apariencia con el selector de tema, montar `<DensityToggle />` ahí, inmediatamente después del selector de tema** (co-locación preferida). Agregar el import `import DensityToggle from "../components/DensityToggle";` junto a los demás.

**Paso 4 (verde):** `npx vitest run src/pages/__tests__/densityToggle.test.ts` exit 0; `npx tsc --noEmit` exit 0.

**Criterio de aceptación (binario):** ambos exit 0.
**Casos borde:** al montar, `currentDensity()` refleja lo persistido (si el operador ya eligió compacto, el botón correcto aparece `aria-pressed`).
**Flag:** sin flag — ES la superficie opt-in UI-only por naturaleza (precedente 132 §3.1, 135 §3.1, 141 F4). Un flag "mostrar el toggle" agrega fricción sin reducir riesgo.
**Runtimes:** TSX servido al webview, idéntico; fallback N/A.
**Staging:** `git add -- "src/components/DensityToggle.tsx" "src/pages/SettingsPage.tsx" "src/pages/__tests__/densityToggle.test.ts"` (+ `DensityToggle.module.css` si se opta por el módulo CSS).
**Trabajo del operador:** opt-in por UI; default `comodo` = hoy.

---

### F4 — Migrar `TicketBoard.module.css` a tokens (solo-en-escala) + fix responsive 820px

**Objetivo:** que la superficie más densa responda a la densidad y no desborde en pantallas chicas. **Valor:** hace la densidad REAL y visible; cierra el único hueco responsive de 0 breakpoints.

**Pre-flight:** `git status --porcelain -- "Stacky Agents/frontend/src/pages/TicketBoard.module.css"` → limpio (verificado 2026-07-15). **NO tocar `TicketBoard.tsx` (tiene WIP ajeno).**

**Archivos:**
- EDITAR `frontend/src/pages/TicketBoard.module.css`
- CREAR `frontend/src/pages/__tests__/ticketBoardDensity.test.ts`

**Paso 1 (TDD, rojo) — `ticketBoardDensity.test.ts`:**

```ts
import { describe, it, expect } from "vitest";
import fs from "node:fs";

const CSS = fs.readFileSync(new URL("../TicketBoard.module.css", import.meta.url), "utf-8");

describe("Plan 150 F4 — TicketBoard migrado a spacing tokens", () => {
  it("consume var(--space-*) en cantidad significativa (≥12)", () => {
    const n = (CSS.match(/var\(--space-[1-9]\)/g) ?? []).length;
    expect(n).toBeGreaterThanOrEqual(12);
  });
  it("NO quedó ningún borde migrado por error (1px sigue literal)", () => {
    // regla solo-en-escala: 1px no está en el mapa ⇒ no debe tokenizarse
    expect(CSS).not.toContain("border: var(--space-");
  });
});

describe("Plan 150 F4 — fix responsive", () => {
  it("agrega breakpoint 820px que colapsa los grids que desbordan", () => {
    const flat = CSS.replace(/\s+/g, " ");
    expect(flat).toMatch(/@media \(max-width: 820px\)/);
    expect(flat).toContain("minmax(0");
  });
});
```

Correr: `npx vitest run src/pages/__tests__/ticketBoardDensity.test.ts` → falla.

**Paso 2 — migración solo-en-escala** aplicando la REGLA §4 a TODAS las declaraciones `padding|margin|gap|row-gap|column-gap` del archivo. Ejemplos deterministas (byte-idénticos en comodo):

- `gap: 16px;` → `gap: var(--space-6);`
- `gap: 8px;` → `gap: var(--space-4);`
- `gap: 12px;` → `gap: var(--space-5);`
- `padding: 8px;` → `padding: var(--space-4);`
- `padding: 16px 24px;` → `padding: var(--space-6) var(--space-7);`
- `padding: 12px 24px;` → `padding: var(--space-5) var(--space-7);`
- `margin: 8px 0;` → `margin: var(--space-4) 0;`
- **NO migrar** (algún valor fuera de escala): `padding: 14px 24px;` (14 ✗), `gap: 10px;` (10 ✗), `padding: 6px 14px;` (14 ✗), `padding: 2px 5px;` (5 ✗), `padding: 7px 12px;` (7 ✗), `padding: 12px 14px;` (14 ✗). Quedan **byte-por-byte** iguales.
- **NUNCA tocar** `border: 1px ...`, `min-width`, `max-width`, `width`, `border-radius`, `grid-template-columns` (excepto el fix responsive del Paso 3).

**Paso 3 — fix responsive.** Al FINAL del archivo agregar EXACTAMENTE (colapsa los dos grids con piso alto a columnas flexibles bajo el breakpoint del shell 139):

```css
/* Plan 150 — responsive de superficie densa: bajo el breakpoint del shell (139),
   los grids con piso minmax(340px)/minmax(320px) desbordarían; se colapsan a
   columnas flexibles. Reusa 820px = breakpoint de shell del plan 139.
   (Precedente de content-grid en el repo: 720px; se estandariza en 820px para
   alinear con el shell entrante.) */
@media (max-width: 820px) {
  .board { grid-template-columns: minmax(0, 1fr); }
  .grid  { grid-template-columns: minmax(0, 1fr); }
}
```

> El implementador debe reemplazar `.board` / `.grid` por los **nombres de clase reales** de las 2 reglas que hoy declaran `grid-template-columns: repeat(auto-fill, minmax(340px, 1fr))` (~línea 156) y `minmax(320px, 1fr)` (~línea 992) en `TicketBoard.module.css`. Confirmarlos con `grep -n "minmax(3" TicketBoard.module.css` antes de escribir.

**Paso 4 (verde):** `npx vitest run src/pages/__tests__/ticketBoardDensity.test.ts` exit 0; `npx tsc --noEmit` exit 0; `npx vitest run src/__tests__/uiDebtRatchet.test.ts` exit 0 (ratchet-neutral).

**Criterio de aceptación (binario):** los tres exit 0.
**Flag:** sin flag — comodo byte-idéntico por la regla solo-en-escala; compacto lo activa el toggle F3.
**Runtimes:** CSS servido al webview, idéntico; fallback N/A.
**Staging:** `git add -- "src/pages/TicketBoard.module.css" "src/pages/__tests__/ticketBoardDensity.test.ts"`
**Trabajo del operador: ninguno.**

---

### F5 — Migrar `PMCommandCenter.module.css` a tokens (solo-en-escala)

**Objetivo:** que la segunda superficie más densa (empatada #1, 102 decls) responda a la densidad. **Valor:** cobertura de densidad en el otro tablero denso; no requiere fix responsive (ya tiene `@media (max-width: 720px)`).

**Pre-flight:** `git status --porcelain -- "Stacky Agents/frontend/src/pages/PMCommandCenter.module.css"` → limpio (verificado 2026-07-15).

**Archivos:**
- EDITAR `frontend/src/pages/PMCommandCenter.module.css`
- CREAR `frontend/src/pages/__tests__/pmCommandCenterDensity.test.ts`

**Paso 1 (TDD, rojo):**

```ts
import { describe, it, expect } from "vitest";
import fs from "node:fs";

const CSS = fs.readFileSync(new URL("../PMCommandCenter.module.css", import.meta.url), "utf-8");

describe("Plan 150 F5 — PMCommandCenter migrado a spacing tokens", () => {
  it("consume var(--space-*) (≥8)", () => {
    const n = (CSS.match(/var\(--space-[1-9]\)/g) ?? []).length;
    expect(n).toBeGreaterThanOrEqual(8);
  });
  it("no migró bordes 1px", () => {
    expect(CSS).not.toContain("border: var(--space-");
  });
});
```

Correr: `npx vitest run src/pages/__tests__/pmCommandCenterDensity.test.ts` → falla.

**Paso 2 — migración solo-en-escala** (REGLA §4, mismos ejemplos que F4). Confirmar valores fuera de escala con `grep -oE "[0-9]+px" PMCommandCenter.module.css | sort | uniq -c` y dejar intactas las declaraciones que los contengan. **No** agregar breakpoint (ya existe el de 720px; NO modificarlo).

**Paso 3 (verde):** `npx vitest run src/pages/__tests__/pmCommandCenterDensity.test.ts` exit 0; `npx tsc --noEmit` exit 0; `npx vitest run src/__tests__/uiDebtRatchet.test.ts` exit 0.

**Criterio de aceptación (binario):** los tres exit 0.
**Flag:** sin flag — comodo byte-idéntico.
**Runtimes:** CSS, idéntico; fallback N/A.
**Staging:** `git add -- "src/pages/PMCommandCenter.module.css" "src/pages/__tests__/pmCommandCenterDensity.test.ts"`
**Trabajo del operador: ninguno.**

---

## 7. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Migrar un valor fuera de escala rompe byte-idéntico en comodo | **Regla solo-en-escala §4** (determinista, sin "el más cercano"). Test F4/F5 verifica que no se tokenizaron bordes; smoke manual (§9) confirma pixel-idéntico en comodo. |
| Animar `padding/gap` degradaría performance (layout thrash) | **PROHIBIDO por §3.5 y §143 §4.4.** El único efecto animado es `opacity` en `#root` (composite/paint). El reflow por re-apuntar `--space-*` es instantáneo por diseño. |
| Colisión con snippets/edits de 141 en `index.html`/`main.tsx`/`theme.css` (zonas calientes) | Pre-flight `git status` por fase; snippet de densidad **independiente y order-agnostic** del de tema (distinta key, distinto atributo); anclas por texto normativo. |
| El ratchet del 138 marca deuda por el `style={{` de `DensityToggle.tsx` | Nota en F3: preferir `DensityToggle.module.css`; si no, regen del baseline por 138 §5-R2. La migración CSS (F4/F5) es ratchet-neutral (no toca hex ni inline styles). |
| FOUC de densidad en dev (Vite no bloquea render como prod) | Snippet inline SÍNCRONO en `<head>` que setea `data-density` antes del primer paint (mismo patrón que el anti-FOUC de tema del 141). |
| El test `themeTokens.test.ts` del 138 falla por el bloque compacto duplicando `--space-*` | No: ese test valida *presencia* en el archivo aplanado, no unicidad (§F0 nota de compatibilidad; mismo caso que 141 F2). |
| `data-density-animating` deja `#root` en opacity 0.72 si el `setTimeout` no corre | El atributo es transitorio y el removeAttribute es la única vía; si por bug quedara, `opacity:0.72` es visible pero recuperable con cualquier toggle. Riesgo bajo; alternativa: `requestAnimationFrame` doble (no necesario). |

---

## 8. Fuera de scope (declarado)

- **Rediseño mobile completo.** Solo se agrega **1 breakpoint** (820px) a la superficie más densa sin él (`TicketBoard`). Un layout mobile integral es otro plan.
- **Migrar TODAS las superficies a tokens.** Solo las 2 más densas (`TicketBoard`, `PMCommandCenter`). `AgentHistoryPage` (86 decls) y el resto migran **progresivamente** en planes futuros (modelo 138: sin big-bang).
- **Tercera densidad / densidad por-superficie / auto por viewport.** Binario `comodo|compacto` global. Sin variante `system`.
- **Contar px crudo en el ratchet.** La migración es ratchet-neutral; extender el ratchet a spacing-debt es un endurecimiento futuro, no acá.
- **Sync de la densidad al backend.** Preferencia local (`localStorage`), consistente con mono-operador. No se toca `/api/preferences`.

---

## 9. Orden de implementación + DoD global

**Orden:** F0 → F1 → F2 → F3 → F4 → F5.

**Definition of Done (todo exit 0):**
1. `npx vitest run src/__tests__/densityTokens.test.ts`
2. `npx vitest run src/services/__tests__/density.test.ts`
3. `npx vitest run src/__tests__/densityBootstrap.test.ts`
4. `npx vitest run src/pages/__tests__/densityToggle.test.ts`
5. `npx vitest run src/pages/__tests__/ticketBoardDensity.test.ts`
6. `npx vitest run src/pages/__tests__/pmCommandCenterDensity.test.ts`
7. `npx vitest run src/__tests__/themeTokens.test.ts` (138, no regresión) y `npx vitest run src/__tests__/uiDebtRatchet.test.ts` (ratchet)
8. `npx tsc --noEmit`
9. **Smoke manual** (obligatorio por el gap RTL/jsdom: `@testing-library/react` y `jsdom` NO están en `package.json` del frontend — no hay test de render; el gate real es `tsc` + smoke): con `stacky.ui.density` ausente ⇒ layout **pixel-idéntico** a hoy (comodo); togglear a `compacto` ⇒ `TicketBoard`/`PMCommandCenter` se compactan; con `prefers-reduced-motion: reduce` activo el cambio es **instantáneo** (sin fundido); en viewport < 820px `TicketBoard` **no desborda** (columna flexible). Reload conserva la elección (anti-FOUC, sin flash).

**El implementador NO commitea** (lo hace el orquestador). Staging quirúrgico por fase con los paths listados.
