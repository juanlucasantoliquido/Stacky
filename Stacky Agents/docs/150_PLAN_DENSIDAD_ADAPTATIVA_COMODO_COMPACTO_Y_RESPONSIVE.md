# Plan 150 — Densidad adaptativa (cómodo / compacto) + responsive de superficies densas

- **Estado:** CRITICADO v2 (APROBADO tras fixes)
- **Versión:** v1 -> v2 (criticado 2026-07-16 por StackyArchitectaUltraEficientCode como juez adversarial)
- **Autor:** StackyArchitectaUltraEficientCode
- **Fecha:** 2026-07-15 (v1) / 2026-07-16 (v2)
- **Serie:** UX/UI (aterriza DESPUÉS de 138 → 139 → 140 → 141 → 143; y de la serie 132-136)
- **Depende de:** plan 138 v2 (escala de spacing `--space-1..9` + ratchet de deuda), plan 143 v3 (presets de motion `--transition-opacity` / `--duration-fast`), plan 141 v3 (dueño de `prefers-reduced-motion` + patrón anti-FOUC `data-theme` en `<head>` + patrón de key localStorage `stacky.ui.*`). **CONSUME los tres por su nombre EXACTO; no redefine ninguno.** Los tres están **IMPLEMENTADOS y verificados en el árbol** (2026-07-16): las anclas de este plan son DEFINITIVAS, sin condicionales.
- **Runtimes:** Codex CLI · Claude Code CLI · GitHub Copilot Pro — **100% presentación** (CSS + TSX + HTML + `localStorage`, servido al navegador/webview). Idéntico en los 3; **fallback N/A** (no hay lógica de runtime).
- **Flag:** **sin flag de harness** (presentación pura, aditiva, opt-in por UI; default = look de hoy byte-idéntico; reversible por revert). Justificación por fase abajo. Ninguna de las 4 excepciones duras ON-por-defecto aplica (no hay kill-switch, ni comportamiento de pipeline/runtime, ni seguridad).

## CHANGELOG v1 → v2

- **C1 (BLOQUEANTE, resuelto):** el código primario de F3 traía `style={{...}}` en `DensityToggle.tsx` NUEVO, lo que **rompe el propio KPI-5**: `uiDebtRatchet.test.ts` cuenta `style={{` en TODOS los `*.tsx` bajo `src/` y la deuda **solo puede bajar** (cabecera del test, líneas 4 y 54; gotcha confirmado: alcance 0 inline-style para .tsx nuevos). v2: `DensityToggle.module.css` es **OBLIGATORIO**, el componente nace con 0 inline styles, el test F3 lo verifica, y queda **PROHIBIDO regenerar el baseline** del ratchet como escape.
- **C2 (IMPORTANTE, resuelto):** F4 hablaba de "los dos grids" pero `TicketBoard.module.css` tiene **TRES** reglas `minmax(3xx)`: líneas **156, 992 y 1039** (verificado por grep 2026-07-16). La tercera seguía desbordando y el KPI-4 daba verde parcial. v2: el fix cubre **TODAS** las reglas que devuelva `grep -n "minmax(3"` (hoy 3) y el test cuenta `minmax(0, 1fr)` ≥ 3.
- **C3 (IMPORTANTE, resuelto):** anclas condicionales stale ("si ya aterrizó el 141..."). El 141 YA aterrizó: `index.html` tiene el snippet anti-FOUC de tema, `main.tsx:15` llama `initThemeController()`, `SettingsPage` tiene sub-tab `appearance` que monta `AppearanceSettings` (`src/components/AppearanceSettings.tsx`). v2: anclas definitivas; el toggle se monta en **`AppearanceSettings.tsx`** (v1 apuntaba primero al panel de `notifications`, hoy incorrecto).
- **C4 (IMPORTANTE, resuelto):** reuso 138/141 — v1 usaba `<button>` crudo; v2 replica **VERBATIM el patrón radiogroup de `AppearanceSettings.tsx`** (mismo panel, misma A11y, mismos estilos por byte-copy de su module.css, cero CSS inventado).
- **C5 (MENOR, resuelto):** el comentario del controlador decía que el settle "= `--duration-base` (0.2s)" pero `--transition-opacity` usa `--duration-fast` = **0.12s** (`theme.css:130,149`). Funcional era correcto (200ms ≥ 120ms); el comentario alucinaba el binding. v2: comentario corregido.
- **C6 (MENOR, resuelto):** referencias de línea drift: la escala `--space-1..9` vive en `theme.css:91-99` (no 630-639). Actualizado; `:NN` siguen siendo orientativos, las anclas son por texto.
- **C7 (MENOR, resuelto):** documentado que `#root` ya aparece en `theme.css:240` (`html, body, #root`) **sin** `transition` previa ⇒ la regla de settle no colisiona; y anotado que el assert "no migró bordes" es guard (verde pre-migración), el gate real es el conteo ≥12/≥8.
- **[ADICIÓN ARQUITECTO] #1 — test de monotonía de escala:** `densityTokens.test.ts` parsea los px REALES de `theme.css` y verifica que cada valor compacto ≤ su comodo y que la escala compacta es no-decreciente de 1..9. Protege contra una edición futura que invierta la jerarquía visual (un token compacto más grande que el siguiente rompería todos los layouts migrados en silencio).
- **[ADICIÓN ARQUITECTO] #2 — guard anti-drift de key:** el snippet inline de `index.html` NO puede importar `DENSITY_STORAGE_KEY` (es un script síncrono pre-bundle) ⇒ existen 2 copias literales de `"stacky.ui.density"` que pueden divergir. `densityBootstrap.test.ts` importa la constante real de `density.ts` y asserta que `index.html` y `densityController.ts` contienen EXACTAMENTE esa literal.

---

## 1. Objetivo

Dar al operador **dos densidades de interfaz** —`comodo` (DEFAULT, byte-idéntico a hoy) y `compacto`— mediante un atributo `data-density` en `<html>` que **re-apunta la escala de spacing `--space-*` del plan 138**. Toda superficie que consuma `var(--space-*)` se compacta sola. El plan además **migra a tokens las 2 superficies más densas** (`TicketBoard`, `PMCommandCenter`) para que la compactación sea REAL y visible, y **cierra el hueco responsive** de la superficie más densa (`TicketBoard` tiene 0 media queries y grids con piso `minmax(340px)`/`minmax(320px)` que desbordan en pantallas chicas).

Mecanismo espejo EXACTO del `data-theme` del plan 141: bloque base `:root` intacto (comodo), bloque nuevo `:root[data-density="compacto"]` que re-apunta SOLO los 9 tokens `--space-*`; selección por UI persistida en `localStorage` bajo `stacky.ui.density`; aplicación síncrona anti-FOUC en el `<head>`.

### KPIs binarios (medibles)

- **KPI-1:** `npx vitest run src/__tests__/densityTokens.test.ts` exit 0 — la escala base `--space-1..9` queda intacta con sus 9 valores del 138 **y** existe `:root[data-density="compacto"]` que re-apunta EXACTAMENTE esos 9 tokens a los valores compactos congelados (§6 F0), **ningún otro token** dentro de ese bloque, **y** la escala compacta es monótona y nunca supera a la base ([ADICIÓN ARQUITECTO] #1).
- **KPI-2:** `npx vitest run src/services/__tests__/density.test.ts` exit 0 — `normalizeDensity` default `"comodo"`, key congelada `stacky.ui.density`.
- **KPI-3:** `npx vitest run src/__tests__/densityBootstrap.test.ts` exit 0 — snippet anti-FOUC en `index.html <head>` lee `stacky.ui.density` y setea `data-density` síncrono; `main.tsx` cablea el init; el controlador setea el atributo; existe la regla de settle por `opacity`; las literales de key de `index.html` y del controlador coinciden con `DENSITY_STORAGE_KEY` ([ADICIÓN ARQUITECTO] #2).
- **KPI-4:** `npx vitest run src/components/__tests__/densityToggle.test.ts` exit 0 — el toggle usa el controlador, ofrece ambas densidades, importa su module.css, **no contiene `style={{`**, y `AppearanceSettings.tsx` lo monta.
- **KPI-5:** `npx vitest run src/pages/__tests__/ticketBoardDensity.test.ts` exit 0 — `TicketBoard.module.css` consume `var(--space-` (≥ 12 ocurrencias, migración real) **y** contiene `@media (max-width: 820px)` con **≥ 3** ocurrencias de `minmax(0, 1fr)` (fix responsive de las 3 reglas, C2).
- **KPI-6:** `npx tsc --noEmit` exit 0 **y** `npx vitest run src/__tests__/uiDebtRatchet.test.ts` exit 0 — TODO el plan es ratchet-neutral (no agrega hex ni `style={{`; C1). **PROHIBIDO regenerar el baseline (`UI_DEBT_REGEN=1`) para pasar este KPI.**
- **KPI-7 (byte-idéntico comodo):** sin `stacky.ui.density` en `localStorage` (o `= "comodo"`), `data-density` resuelve `comodo` ⇒ escala base ⇒ layout pixel-idéntico a hoy. Garantizado por construcción (regla de migración solo-en-escala, §4) + verificado por smoke manual (§9, por el gap RTL/jsdom conocido).

---

## 2. Por qué ahora / gap (evidencia grep, números reales, reverificados 2026-07-16)

Verificación sobre `plans-138-141-serie-ux-ui`:

- **La app tiene UNA sola densidad fija.** El 138 define la escala `--space-1..9` (`theme.css:91-99`, valores `2,4,6,8,12,16,24,32,48`) pero **no hay forma de compactarla**: no existe ningún `data-density` en el código (`grep -rn "data-density" src index.html` → 0, reverificado).
- **Superficies densas que desperdician pantalla:** `TicketBoard.module.css` = **1042 líneas, 102** declaraciones `padding|margin|gap`; `PMCommandCenter.module.css` = **102**; `AgentHistoryPage.module.css` = **86** (ranking real por `grep -cE "padding|margin|gap"`). Todas con px hardcodeado.
- **Hueco responsive real:** `TicketBoard.module.css` tiene **0 `@media`** (`grep -c "@media"` → 0) y usa `grid-template-columns: repeat(auto-fill, minmax(340px, 1fr))` (línea 156) y `minmax(320px, 1fr)` (líneas **992 y 1039** — son TRES reglas en total, no dos; C2). Bajo ~360px de viewport el piso de 340px **desborda horizontalmente**. Es la superficie más densa y la única sin breakpoint.
- **El 138 NO hace big-bang migration** (138:150 "sin exigir una migración big-bang"; solo 3 migraciones ejemplares). Por eso `var(--space-` en los `.module.css` de páginas HOY = **0 ocurrencias**. ⇒ Re-apuntar los tokens NO compacta nada por sí solo: hay que migrar al menos las superficies densas para que la densidad sea visible. Este plan cierra ese paso de forma progresiva y byte-idéntica (§4).
- **Infra 141/143 lista para espejar (verificado):** `index.html` ya tiene el `<script>` anti-FOUC de tema (comentario "Plan 141", lee `stacky.ui.theme`); `main.tsx:6,15` importa y llama `initThemeController()`; `SettingsPage.tsx` tiene sub-tab `appearance` que monta `AppearanceSettings` (`src/components/AppearanceSettings.tsx`, radiogroup de tema con `readStoredChoice`/`setTheme`); `theme.css:149` define `--transition-opacity: opacity var(--duration-fast) var(--ease-standard)` con `--duration-fast: 0.12s` (`theme.css:130`).

---

## 3. Principios y guardarraíles (NO negociables)

1. **Paridad 3 runtimes:** todo es CSS/TSX/HTML/`localStorage` servido al navegador/webview. Idéntico en Codex CLI, Claude Code CLI y GitHub Copilot Pro. **Fallback N/A.** Se declara por fase.
2. **Cero trabajo extra al operador:** default `comodo` = look de hoy **byte-idéntico**; `compacto` es **opt-in por un toggle en la UI**. Sin pasos nuevos, sin nueva carga de config, backward-compatible. Reversible por revert.
3. **Human-in-the-loop:** el toggle amplifica; nada autónomo, nada proactivo.
4. **Mono-operador sin auth:** preferencia local en `localStorage`; nada de RBAC/multiusuario/backend obligatorio.
5. **No degradar performance:** el cambio de densidad **re-apunta variables CSS ⇒ el reflow es instantáneo por naturaleza** (no se anima layout). El único efecto animado es un settle de `opacity` (propiedad barata, composite/paint) usando el preset `--transition-opacity` del 143; **PROHIBIDO animar `padding`/`margin`/`gap`/`width`/`height`/`top`/`left`** (§143 §4.4). El settle lo neutraliza `prefers-reduced-motion` (141 F5), que este plan **jamás reescribe**.
6. **Consumir, no redefinir:** los tokens `--space-*` (138), `--transition-opacity`/`--duration-fast` (143) y el bloque `prefers-reduced-motion`/focus-ring (141 F5) se usan por su nombre EXACTO. Este plan **no crea** tokens de spacing nuevos; solo **re-apunta** los 9 existentes dentro del bloque `[data-density="compacto"]`.
7. **Ratchet primero (C1):** ningún archivo NUEVO de este plan puede nacer con `style={{` ni hex crudo. `uiDebtRatchet.test.ts` escanea TODOS los `*.tsx` bajo `src/` y la deuda solo puede bajar. **PROHIBIDO usar `UI_DEBT_REGEN=1` para absorber deuda nueva de este plan** (el regen existe para bajar el baseline, no para subirlo).

### Anti-frágil (zonas calientes)

`theme.css`, `index.html`, `main.tsx`, `SettingsPage.tsx`, `AppearanceSettings.tsx` y los `.module.css` de features son ZONAS CALIENTES (132/134/135/136/138-143 las tocan). **Todas las anclas son por TEXTO NORMATIVO** (los `:NN` de línea son orientativos). **Pre-flight por fase:** `git status --porcelain -- "<ruta>"` antes de tocar cada archivo; si hay WIP ajeno sin commitear ⇒ **STOP, avisar, no editar**. Verificado 2026-07-15: `TicketBoard.tsx` y `ActiveRunsPanel.module.css` tenían WIP (NO se tocan); re-chequear en frío igual. Staging quirúrgico con paths explícitos. **El implementador NO commitea** (lo hace el orquestador).

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
3. En cualquier otro caso (algún valor fuera de escala, `%`, `em`, `auto`, `calc(...)`), **dejar la declaración byte-por-byte SIN TOCAR**.
4. **NUNCA** tocar `border`, `border-width`, `width`, `height`, `min-*`, `max-*`, `flex-basis`, `border-radius`, `inset`, `top/left/right/bottom` ni ninguna propiedad que no sea de las 5 de spacing. (Los `1px` de borde quedan `1px`.)

Consecuencias: en comodo `var(--space-3)` computa `6px` = idéntico; en compacto computa `4px` = compacta. La densidad se ve en el spacing estructural dominante (que SÍ está en escala: `gap:8/12/16`, `padding:8`, `padding:16px 24px`, `padding:12px 24px`), y los detalles decorativos fuera de escala (chips `2px 5px`) quedan literales — aceptable, casi no afectan densidad. **Ratchet-neutral:** no agrega hex ni `style={{`.

---

## 5. Glosario

- **`data-density`**: atributo en `<html>` (`document.documentElement`). Ausente o `"comodo"` ⇒ escala base (byte-idéntico a hoy). `"compacto"` ⇒ activa `:root[data-density="compacto"]`.
- **`Density`**: tipo `"comodo" | "compacto"` (sin variante `system`: no hay señal del SO para densidad).
- **`stacky.ui.density`**: clave `localStorage` (CONGELADA) que guarda la elección del operador. Espejo dotted de `stacky.ui.theme` (141).
- **`data-density-animating`**: atributo transitorio en `<html>` durante ~200ms tras un toggle; dispara el settle de `opacity` (§F2). Ausente en reposo.
- **Escala comodo**: `--space-1..9` = `2,4,6,8,12,16,24,32,48px` (base 138, `theme.css:91-99`, INTACTA).
- **Escala compacto**: re-apunte congelado de esos 9 tokens (§6 F0).

---

## 6. Fases

**Comando de tests (idioma de la casa):** `npx vitest run <ruta-relativa-del-test>` desde `Stacky Agents/frontend` — **UN archivo por corrida** (gotcha vitest test-order pollution). **Gate de tipos:** `npx tsc --noEmit`. Los tests que inspeccionan `.tsx`/`.html`/`.css` usan `fs.readFileSync` + regex sobre el contenido (idioma 138/141/143; RTL/jsdom NO está en `package.json` — gap estructural conocido, ver §9).

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

function compactBlock(): string {
  const m = THEME.match(/\[data-density="compacto"\]\s*\{([^}]*)\}/);
  expect(m, "falta el bloque :root[data-density=\"compacto\"]").not.toBeNull();
  return m![1];
}

describe("Plan 150 F0 — escala de densidad", () => {
  it("la escala base 138 sigue intacta en :root", () => {
    const missing = BASE.filter(([n, v]) => !FLAT.includes(`${n}: ${v};`));
    expect(missing).toEqual([]);
  });

  it("existe el bloque :root[data-density=\"compacto\"]", () => {
    expect(THEME.includes('[data-density="compacto"]')).toBe(true);
  });

  it("el bloque compacto re-apunta los 9 --space-* a los valores congelados", () => {
    const block = compactBlock().replace(/\s+/g, " ");
    const missing = COMPACT.filter(([n, v]) => !block.includes(`${n}: ${v};`));
    expect(missing).toEqual([]);
  });

  it("el bloque compacto SOLO toca --space-* (ningún otro token)", () => {
    const decls = (compactBlock().match(/--[a-z0-9-]+:/g) ?? []);
    const nonSpace = decls.filter((d) => !/^--space-[1-9]:$/.test(d));
    expect(nonSpace).toEqual([]);
  });

  it("[ADICIÓN ARQUITECTO] monotonía: compacto ≤ comodo y escala no-decreciente (parsea px REALES del CSS)", () => {
    const block = compactBlock();
    const px = (src: string, n: number): number => {
      const m = src.match(new RegExp(`--space-${n}:\\s*(\\d+)px`));
      expect(m, `--space-${n} ilegible`).not.toBeNull();
      return parseInt(m![1], 10);
    };
    let prev = 0;
    for (let n = 1; n <= 9; n++) {
      const base = px(FLAT, n);      // primera ocurrencia = :root base (theme.css:91-99)
      const comp = px(block, n);     // dentro del bloque compacto
      expect(comp, `--space-${n} compacto no puede superar al comodo`).toBeLessThanOrEqual(base);
      expect(comp, `--space-${n} compacto invierte la jerarquía`).toBeGreaterThanOrEqual(prev);
      prev = comp;
    }
  });
});
```

Correr: `npx vitest run src/__tests__/densityTokens.test.ts` → **falla** (no existe el bloque).

**Paso 2 — editar `theme.css`.** Ancla normativa DEFINITIVA (C3): **inmediatamente después del bloque `:root[data-theme="light"]` del plan 141** (buscar `[data-theme="light"]`, insertar tras su `}` de cierre). Agregar EXACTAMENTE:

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

**Nota de compatibilidad (138/141):** el test `themeTokens.test.ts` (138) valida *presencia* de `--space-N: <base>px;` en el archivo aplanado, no unicidad; el bloque compacto agrega declaraciones adicionales en otro selector y NO rompe ese test (mismo mecanismo que 141 F2 al agregar `[data-theme="light"]`). El test de monotonía ([ADICIÓN] #1) depende de que el bloque compacto esté DESPUÉS del `:root` base en el archivo (la "primera ocurrencia" de `--space-N` en FLAT debe ser la base) — el ancla del Paso 2 lo garantiza.

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

**Paso 1 (TDD, rojo) — `densityBootstrap.test.ts`** (fs+regex, sin DOM; importa la constante pura de F1 — sin DOM, es seguro):

```ts
import { describe, it, expect } from "vitest";
import fs from "node:fs";
import { DENSITY_STORAGE_KEY } from "../services/density";

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

describe("Plan 150 F2 — [ADICIÓN ARQUITECTO] guard anti-drift de key", () => {
  // El snippet inline NO puede importar la constante (script síncrono pre-bundle):
  // hay 2 copias literales que pueden divergir. Este guard las ancla a la constante real.
  it("index.html usa EXACTAMENTE la literal de DENSITY_STORAGE_KEY", () => {
    expect(HTML).toContain(`"${DENSITY_STORAGE_KEY}"`);
  });
  it("densityController usa EXACTAMENTE la misma key (vía import, no re-literal)", () => {
    expect(CTRL).toContain("DENSITY_STORAGE_KEY");
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

**Paso 2 — crear `densityController.ts`** (efectos DOM; copia el patrón try/catch de `preferences.ts` — helpers `read`/`write` module-private, NO importables — igual que hace `themeController.ts` del 141):

```ts
/* Plan 150 F2 — controlador de densidad (efectos DOM). Lógica pura en density.ts. */
import { normalizeDensity, DENSITY_STORAGE_KEY, type Density } from "./density";

/** Duración del settle. La transición usa --transition-opacity (--duration-fast = 0.12s,
 *  theme.css:130,149); 200ms ≥ 120ms deja margen holgado para remover el atributo
 *  DESPUÉS de que el fundido terminó. (C5: no es --duration-base.) */
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

**Paso 3 — snippet anti-FOUC en `index.html`.** Ancla normativa DEFINITIVA (C3): **dentro de `<head>`, inmediatamente DESPUÉS del `</script>` del snippet anti-FOUC de tema del plan 141** (buscar el comentario `Plan 141 — anti-FOUC`; el snippet de densidad va tras el cierre de ese script). Agregar EXACTAMENTE:

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

**Paso 4 — editar `main.tsx`.** Ancla DEFINITIVA (C3): agregar el import junto al de `themeController` (`main.tsx:6`) y llamar `initDensity();` **en la línea siguiente a `initThemeController();`** (`main.tsx:15`, antes del `createRoot(...).render(...)`; idempotente respecto del snippet; mantiene el DOM en sync si el snippet no corrió, p. ej. tests):

```ts
import { initDensity } from "./services/densityController";
// ...
initThemeController();
initDensity();
```

**Paso 5 — regla de settle en `theme.css`.** Ancla normativa: al final de la sección de utilidades/reset. Nota (C7): `#root` hoy solo aparece en `theme.css:240` (`html, body, #root { ... }`) **sin** `transition` ⇒ esta regla no pisa nada. Agregar EXACTAMENTE (usa SOLO `opacity`, propiedad barata; el reflow por re-apuntar `--space-*` es instantáneo; `prefers-reduced-motion` del 141 F5 neutraliza la transición):

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

### F3 — Toggle de densidad en Apariencia (superficie opt-in, ratchet-neutral NATO)

**Objetivo:** un control `Cómodo / Compacto` en Configuración → Apariencia que llama a `setDensity`. **Valor:** ES la superficie opt-in; hasta acá nadie escribe la key ⇒ todo dormido.

**Pre-flight:** `git status --porcelain -- "Stacky Agents/frontend/src/components/AppearanceSettings.tsx"` → limpio (o STOP).

**Archivos:**
- CREAR `frontend/src/components/DensityToggle.tsx`
- CREAR `frontend/src/components/DensityToggle.module.css` (**OBLIGATORIO**, C1 — no opcional)
- EDITAR `frontend/src/components/AppearanceSettings.tsx` (montar el toggle; C3/C4)
- CREAR `frontend/src/components/__tests__/densityToggle.test.ts`

**Paso 1 (TDD, rojo) — `densityToggle.test.ts`** (fs+regex; RTL/jsdom no está disponible, §9):

```ts
import { describe, it, expect } from "vitest";
import fs from "node:fs";

const TOGGLE = fs.readFileSync(new URL("../DensityToggle.tsx", import.meta.url), "utf-8");
const APPEARANCE = fs.readFileSync(new URL("../AppearanceSettings.tsx", import.meta.url), "utf-8");

describe("Plan 150 F3 — DensityToggle", () => {
  it("usa el controlador (setDensity/currentDensity)", () => {
    expect(TOGGLE).toMatch(/setDensity/);
    expect(TOGGLE).toMatch(/currentDensity/);
  });
  it("ofrece ambas densidades", () => {
    expect(TOGGLE).toContain('"comodo"');
    expect(TOGGLE).toContain('"compacto"');
  });
  it("estilos por module.css, CERO inline styles (ratchet 138, C1)", () => {
    expect(TOGGLE).toMatch(/import\s+styles\s+from\s+"\.\/DensityToggle\.module\.css"/);
    expect(TOGGLE).not.toContain("style={{");
  });
});

describe("Plan 150 F3 — montaje en Apariencia (141 F4)", () => {
  it("AppearanceSettings importa y monta DensityToggle", () => {
    expect(APPEARANCE).toMatch(/import\s+DensityToggle/);
    expect(APPEARANCE).toContain("<DensityToggle");
  });
});
```

Correr: `npx vitest run src/components/__tests__/densityToggle.test.ts` → falla.

**Paso 2 — crear `DensityToggle.tsx`** (C4: **espejo VERBATIM del patrón radiogroup de `AppearanceSettings.tsx`** — mismo panel, misma A11y, coherencia visual; cero `style={{`):

```tsx
/* Plan 150 F3 — toggle de densidad de interfaz (espejo del radiogroup de tema, 141 F4). */
import { useState } from "react";
import { currentDensity, setDensity } from "../services/densityController";
import type { Density } from "../services/density";
import styles from "./DensityToggle.module.css";

export const DENSITY_OPTIONS: Array<{ value: Density; label: string; hint: string }> = [
  { value: "comodo",   label: "Cómodo",   hint: "Espaciado estándar (por defecto)." },
  { value: "compacto", label: "Compacto", hint: "Más información por pantalla." },
];

export default function DensityToggle() {
  const [choice, setChoice] = useState<Density>(() => currentDensity());

  const pick = (value: Density) => {
    setChoice(value);
    setDensity(value); // aplica al instante, sin re-montar la app
  };

  return (
    <div className={styles.group} role="radiogroup" aria-label="Densidad de la interfaz">
      {DENSITY_OPTIONS.map((opt) => (
        <label
          key={opt.value}
          className={`${styles.option} ${choice === opt.value ? styles.active : ""}`}
        >
          <input
            type="radio"
            name="stacky-density"
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
  );
}
```

**Paso 3 — crear `DensityToggle.module.css`.** Regla determinista (C1/C4, sin CSS inventado): **copiar BYTE-POR-BYTE de `AppearanceSettings.module.css` las reglas de las clases `.group`, `.option`, `.active`, `.radio`, `.optLabel`, `.optHint`** (probadas contra el ratchet cuando aterrizó el 141), con este comentario de cabecera:

```css
/* Plan 150 F3 — estilos del toggle de densidad.
   Byte-copy de las clases equivalentes de AppearanceSettings.module.css (141 F4)
   para coherencia visual en el mismo panel. 0 inline styles: ratchet-neutral nato. */
```

**Paso 4 — montar en `AppearanceSettings.tsx`.** Ancla normativa DEFINITIVA (C3): agregar `import DensityToggle from "./DensityToggle";` junto a los demás imports, y **después del `</div>` que cierra el radiogroup de tema** (el `div` con `role="radiogroup"` `aria-label="Tema de la interfaz"`) insertar:

```tsx
      <p className={styles.intro}>
        Densidad de la interfaz. "Compacto" muestra más información por pantalla.
      </p>
      <DensityToggle />
```

**Paso 5 (verde):** `npx vitest run src/components/__tests__/densityToggle.test.ts` exit 0; `npx tsc --noEmit` exit 0; `npx vitest run src/__tests__/uiDebtRatchet.test.ts` exit 0 (**sin regenerar baseline**, C1).

**Criterio de aceptación (binario):** los tres exit 0.
**Casos borde:** al montar, `currentDensity()` refleja lo persistido (si el operador ya eligió compacto, el radio correcto aparece `checked`).
**Flag:** sin flag — ES la superficie opt-in UI-only por naturaleza (precedente 132 §3.1, 135 §3.1, 141 F4). Un flag "mostrar el toggle" agrega fricción sin reducir riesgo.
**Runtimes:** TSX servido al webview, idéntico; fallback N/A.
**Staging:** `git add -- "src/components/DensityToggle.tsx" "src/components/DensityToggle.module.css" "src/components/AppearanceSettings.tsx" "src/components/__tests__/densityToggle.test.ts"`
**Trabajo del operador:** opt-in por UI; default `comodo` = hoy.

---

### F4 — Migrar `TicketBoard.module.css` a tokens (solo-en-escala) + fix responsive 820px

**Objetivo:** que la superficie más densa responda a la densidad y no desborde en pantallas chicas. **Valor:** hace la densidad REAL y visible; cierra el único hueco responsive de 0 breakpoints.

**Pre-flight:** `git status --porcelain -- "Stacky Agents/frontend/src/pages/TicketBoard.module.css"` → limpio (verificado 2026-07-15; re-chequear en frío). **NO tocar `TicketBoard.tsx` (tenía WIP ajeno).**

**Archivos:**
- EDITAR `frontend/src/pages/TicketBoard.module.css`
- CREAR `frontend/src/pages/__tests__/ticketBoardDensity.test.ts`

**Paso 1 (TDD, rojo) — `ticketBoardDensity.test.ts`:**

```ts
import { describe, it, expect } from "vitest";
import fs from "node:fs";

const CSS = fs.readFileSync(new URL("../TicketBoard.module.css", import.meta.url), "utf-8");

describe("Plan 150 F4 — TicketBoard migrado a spacing tokens", () => {
  it("consume var(--space-*) en cantidad significativa (≥12) — este es el gate real", () => {
    const n = (CSS.match(/var\(--space-[1-9]\)/g) ?? []).length;
    expect(n).toBeGreaterThanOrEqual(12);
  });
  it("guard: ningún borde migrado por error (verde también pre-migración, C7)", () => {
    // regla solo-en-escala: 1px no está en el mapa ⇒ no debe tokenizarse
    expect(CSS).not.toContain("border: var(--space-");
  });
});

describe("Plan 150 F4 — fix responsive (las TRES reglas minmax, C2)", () => {
  it("agrega breakpoint 820px que colapsa TODOS los grids que desbordan", () => {
    const flat = CSS.replace(/\s+/g, " ");
    expect(flat).toMatch(/@media \(max-width: 820px\)/);
    const collapsed = (flat.match(/minmax\(0, 1fr\)/g) ?? []).length;
    const floors = (CSS.match(/minmax\(3\d{2}px/g) ?? []).length; // hoy 3 (líneas 156, 992, 1039)
    expect(collapsed).toBeGreaterThanOrEqual(floors);
    expect(floors).toBeGreaterThanOrEqual(3);
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

**Paso 3 — fix responsive (C2: cubre las TRES reglas).** Primero confirmar el inventario real: `grep -n "minmax(3" TicketBoard.module.css` — hoy devuelve **3 reglas** (líneas 156 `minmax(340px, 1fr)`, 992 y 1039 `minmax(320px, 1fr)`). Anotar el **nombre de clase real** de cada una (la clase del selector que la contiene). Al FINAL del archivo agregar un ÚNICO bloque `@media` con **una línea por cada clase encontrada** (colapsa cada grid con piso alto a columna flexible bajo el breakpoint del shell 139):

```css
/* Plan 150 — responsive de superficie densa: bajo el breakpoint del shell (139,
   AppSidebar.module.css usa 820px), los grids con piso minmax(340px)/minmax(320px)
   desbordarían; se colapsan a columnas flexibles. TODAS las reglas minmax(3xx) del
   archivo quedan cubiertas (hoy 3). Precedente de content-grid en el repo: 720px
   (PMCommandCenter:565); se estandariza en 820px para alinear con el shell. */
@media (max-width: 820px) {
  .<clase-de-linea-156>  { grid-template-columns: minmax(0, 1fr); }
  .<clase-de-linea-992>  { grid-template-columns: minmax(0, 1fr); }
  .<clase-de-linea-1039> { grid-template-columns: minmax(0, 1fr); }
}
```

> Reemplazar cada `.<clase-de-linea-NNN>` por el nombre real; si dos reglas comparten clase, dejar una sola línea (el test cuenta `minmax(0, 1fr)` ≥ cantidad de pisos `minmax(3xx)`, que en ese caso también baja). Si al implementar aparecieran MÁS reglas `minmax(3xx)` (archivo caliente), cubrirlas TODAS: el test lo exige por conteo, no por lista fija.

**Paso 4 (verde):** `npx vitest run src/pages/__tests__/ticketBoardDensity.test.ts` exit 0; `npx tsc --noEmit` exit 0; `npx vitest run src/__tests__/uiDebtRatchet.test.ts` exit 0 (ratchet-neutral).

**Criterio de aceptación (binario):** los tres exit 0.
**Flag:** sin flag — comodo byte-idéntico por la regla solo-en-escala; compacto lo activa el toggle F3.
**Runtimes:** CSS servido al webview, idéntico; fallback N/A.
**Staging:** `git add -- "src/pages/TicketBoard.module.css" "src/pages/__tests__/ticketBoardDensity.test.ts"`
**Trabajo del operador: ninguno.**

---

### F5 — Migrar `PMCommandCenter.module.css` a tokens (solo-en-escala)

**Objetivo:** que la segunda superficie más densa (empatada #1, 102 decls) responda a la densidad. **Valor:** cobertura de densidad en el otro tablero denso; no requiere fix responsive (ya tiene `@media (max-width: 720px)` en la línea 565).

**Pre-flight:** `git status --porcelain -- "Stacky Agents/frontend/src/pages/PMCommandCenter.module.css"` → limpio (verificado 2026-07-15; re-chequear en frío).

**Archivos:**
- EDITAR `frontend/src/pages/PMCommandCenter.module.css`
- CREAR `frontend/src/pages/__tests__/pmCommandCenterDensity.test.ts`

**Paso 1 (TDD, rojo):**

```ts
import { describe, it, expect } from "vitest";
import fs from "node:fs";

const CSS = fs.readFileSync(new URL("../PMCommandCenter.module.css", import.meta.url), "utf-8");

describe("Plan 150 F5 — PMCommandCenter migrado a spacing tokens", () => {
  it("consume var(--space-*) (≥8) — este es el gate real", () => {
    const n = (CSS.match(/var\(--space-[1-9]\)/g) ?? []).length;
    expect(n).toBeGreaterThanOrEqual(8);
  });
  it("guard: no migró bordes 1px (verde también pre-migración, C7)", () => {
    expect(CSS).not.toContain("border: var(--space-");
  });
});
```

Correr: `npx vitest run src/pages/__tests__/pmCommandCenterDensity.test.ts` → falla.

**Paso 2 — migración solo-en-escala** (REGLA §4, mismos ejemplos que F4). Confirmar valores fuera de escala con `grep -oE "[0-9]+px" PMCommandCenter.module.css | sort | uniq -c` y dejar intactas las declaraciones que los contengan. **No** agregar breakpoint (ya existe el de 720px en la línea 565; NO modificarlo).

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
| Migrar un valor fuera de escala rompe byte-idéntico en comodo | **Regla solo-en-escala §4** (determinista, sin "el más cercano"). Guard F4/F5 verifica que no se tokenizaron bordes; smoke manual (§9) confirma pixel-idéntico en comodo. |
| Animar `padding/gap` degradaría performance (layout thrash) | **PROHIBIDO por §3.5 y §143 §4.4.** El único efecto animado es `opacity` en `#root` (composite/paint). El reflow por re-apuntar `--space-*` es instantáneo por diseño. |
| Colisión con snippets/edits de 141 en `index.html`/`main.tsx`/`theme.css` (zonas calientes) | 141 ya aterrizó ⇒ anclas DEFINITIVAS contra sus artefactos reales (C3). Pre-flight `git status` por fase; snippet de densidad **independiente y order-agnostic** del de tema (distinta key, distinto atributo). |
| El ratchet del 138 marca deuda por inline styles en archivos nuevos | **Resuelto por diseño (C1):** `DensityToggle.module.css` obligatorio, test F3 asserta `not.toContain("style={{")`, y `uiDebtRatchet` corre en F3/F4/F5 **sin regenerar baseline**. |
| El fix responsive deja un grid sin cubrir (archivo caliente puede sumar reglas) | **Test por CONTEO (C2):** `minmax(0, 1fr)` ≥ cantidad de pisos `minmax(3xx)` del archivo, con piso 3. Nueva regla sin colapsar ⇒ test rojo. |
| Una edición futura invierte la escala compacta (p. ej. `--space-5` compacto > `--space-6` compacto) rompiendo jerarquía visual en silencio | **[ADICIÓN ARQUITECTO] #1:** test de monotonía en `densityTokens.test.ts` parsea los px reales del CSS. |
| Las 2 copias literales de la key (`index.html` inline + código) divergen tras un refactor | **[ADICIÓN ARQUITECTO] #2:** guard anti-drift en `densityBootstrap.test.ts` ancla ambas a `DENSITY_STORAGE_KEY`. |
| FOUC de densidad en dev (Vite no bloquea render como prod) | Snippet inline SÍNCRONO en `<head>` que setea `data-density` antes del primer paint (mismo patrón que el anti-FOUC de tema del 141, ya probado en el árbol). |
| El test `themeTokens.test.ts` del 138 falla por el bloque compacto duplicando `--space-*` | No: ese test valida *presencia* en el archivo aplanado, no unicidad (§F0 nota de compatibilidad; mismo caso que 141 F2). |
| `data-density-animating` deja `#root` en opacity 0.72 si el `setTimeout` no corre | El atributo es transitorio y el removeAttribute es la única vía; si por bug quedara, `opacity:0.72` es visible pero recuperable con cualquier toggle. Riesgo bajo; alternativa: `requestAnimationFrame` doble (no necesario). |

---

## 8. Fuera de scope (declarado)

- **Rediseño mobile completo.** Solo se agrega **1 breakpoint** (820px) a la superficie más densa sin él (`TicketBoard`). Un layout mobile integral es otro plan.
- **Migrar TODAS las superficies a tokens.** Solo las 2 más densas (`TicketBoard`, `PMCommandCenter`). `AgentHistoryPage` (86 decls) y el resto migran **progresivamente** en planes futuros (modelo 138: sin big-bang).
- **Tercera densidad / densidad por-superficie / auto por viewport.** Binario `comodo|compacto` global. Sin variante `system`.
- **Contar px crudo en el ratchet.** La migración es ratchet-neutral; extender el ratchet a spacing-debt es un endurecimiento futuro, no acá.
- **Sync de la densidad al backend.** Preferencia local (`localStorage`), consistente con mono-operador. No se toca `/api/preferences`.
- **Registrar la densidad en la paleta global (129).** Valor real pero scope aparte; candidato a bullet de un plan futuro de "acciones de apariencia en paleta".

---

## 9. Orden de implementación + DoD global

**Orden:** F0 → F1 → F2 → F3 → F4 → F5.

**Definition of Done (todo exit 0, corriendo cada test POR ARCHIVO):**
1. `npx vitest run src/__tests__/densityTokens.test.ts`
2. `npx vitest run src/services/__tests__/density.test.ts`
3. `npx vitest run src/__tests__/densityBootstrap.test.ts`
4. `npx vitest run src/components/__tests__/densityToggle.test.ts`
5. `npx vitest run src/pages/__tests__/ticketBoardDensity.test.ts`
6. `npx vitest run src/pages/__tests__/pmCommandCenterDensity.test.ts`
7. `npx vitest run src/__tests__/themeTokens.test.ts` (138, no regresión) y `npx vitest run src/__tests__/uiDebtRatchet.test.ts` (ratchet, **sin `UI_DEBT_REGEN`**)
8. `npx tsc --noEmit`
9. **Smoke manual** (obligatorio por el gap RTL/jsdom: `@testing-library/react` y `jsdom` NO están en `package.json` del frontend — no hay test de render; el gate real es `tsc` + smoke): con `stacky.ui.density` ausente ⇒ layout **pixel-idéntico** a hoy (comodo); togglear a `compacto` en Configuración → Apariencia ⇒ `TicketBoard`/`PMCommandCenter` se compactan; con `prefers-reduced-motion: reduce` activo el cambio es **instantáneo** (sin fundido); en viewport < 820px `TicketBoard` **no desborda** (las 3 zonas de grid colapsan a columna flexible). Reload conserva la elección (anti-FOUC, sin flash).

**El implementador NO commitea** (lo hace el orquestador). Staging quirúrgico por fase con los paths listados. Tests frontend nuevos NO se registran en `HARNESS_TEST_FILES` (ese ratchet cubre solo `test_*.py` de backend); el gate frontend es el DoD de arriba.
