# Plan 143 — Sistema de movimiento, micro-interacciones y feedback óptimista

**Versión:** v2 (criticado 2026-07-15)
**Estado:** CRITICADO v1→v2 · VEREDICTO: APROBADO-CON-CAMBIOS
**Autor:** StackyArchitectaUltraEficientCode

### CHANGELOG v1→v2 (juez adversarial; refs C#)
- **C1 (IMPORTANTE):** los conteos por-archivo de KPI-3 y §6 (F3/F4) contaban DECLARACIONES de
  `transition` (líneas), pero el ratchet cuenta LITERALES de tiempo (`TIME_RE`): una línea
  `transition: a 0.12s, b 0.12s` cuenta **2**, no 1. Verificado por grep 2026-07-15:
  `TicketSelector`=5 literales (no 3), `AgentRuntimeSelector`/`AgentSelector`/`AgentCard`=2 (no 1).
  Corregidos los números y reencuadrado KPI-3 como **monotonía por-archivo** (garantía binaria dura;
  los números son ilustrativos, el baseline los recomputa).
- **C2 (IMPORTANTE):** F2 fuerza `components/shell/`→0 asumiendo que el ratchet de COLOR del 139
  ("0 hex") implica limpieza de MOTION — no lo implica. Si `shell/` (139) tuviera un tiempo
  OFF-SCALE, F1 (tabla §6.F3.T: "no migrar off-scale") contradiría a F2 (forzado 0) ⇒ deadlock para
  un modelo menor. Agregado STOP explícito en F1 Paso 2.
- **C3 (MENOR):** §2/§3 citaban **139** declaraciones (grep de líneas); el conteo hoy es **137**
  (±2 por WIP ajeno). Aclarado que es nivel-declaración, deriva con WIP, y NO es lo que gatea el
  ratchet (que cuenta literales).
- **C4 (MENOR):** F6 entrega `useOptimisticPending` + utilidades SIN consumidor en este plan; la
  reversión-ante-fallo queda probada a nivel LÓGICA (test), no visual. Documentado + primer adoptante
  recomendado como plan futuro.
- **C5 (MENOR):** `.u-pending` con `pointer-events: none` puede soft-lockear un control si la promesa
  envuelta nunca resuelve. Agregada advertencia en el JSDoc del hook (el adoptante garantiza settle).
- **C6 (MENOR) + [ADICIÓN ARQUITECTO]:** el guard de layout de KPI-4 era frágil (solo `transition:
  <propLayout>` al inicio del valor; se saltea `transition: opacity, width`). Reescrito a un regex
  robusto que detecta CUALQUIER propiedad de layout animada en shorthand o longhand, y se sumó el
  **contrato visual del feedback óptimista** (`.u-pending` DEBE atenuar y bloquear) al mismo test.
**Origen:** cierre de la serie UI/UX "mejorar drásticamente la UI y UX de Stacky". Es a MOTION
lo que el plan 138 fue a color/spacing: la capa que hace que 138→141 se sientan premium y vivas.
**Depende de:** plan 138 v2 (tokens `--duration-*` / `--ease-*` + primitivas `ui/` + ratchet de deuda)
y plan 141 v3 (dueño de `prefers-reduced-motion` y del focus ring). CONSUME ambos; no los redefine.
**Serie:** UI/UX **138 → 139 → 140 → 141 → 143** (aterriza DESPUÉS de toda la serie 132-136 y 138-141).
**Alcance:** 100% frontend (CSS/TSX). Cero backend, cero endpoint, cero dependencia nueva
(`package.json` NO se toca), cero flag de harness.
**Flag:** NO lleva flag (justificación por fase en §4.1; precedente 138 §3.1, 140 §3.1, 141 §3.1).

> Este documento está redactado para que un MODELO MENOR (Haiku, Codex CLI o GitHub Copilot Pro)
> lo implemente SIN inferir nada. Rutas, símbolos, nombres de tokens, valores y comandos son
> LITERALES. Prohibido desviarse de los nombres exactos, prohibido "mejorar" valores o alcance.
> Todo lo ambiguo ya fue decidido acá. Regla de la casa: los `:NN` citados son ORIENTATIVOS; el
> TEXTO/símbolo citado es NORMATIVO.

---

## 1. Objetivo + KPIs binarios

Stacky tiene hoy los tokens de motion definidos por el plan 138 (`--duration-fast/base/slow`,
`--ease-standard/in-out/out-expo`) pero **el 138 solo los usa dentro de sus 8 primitivas de
`components/ui/`**. El resto de la app reinventa su timing: **139 declaraciones `transition:`
con tiempo hardcodeado** (ms/s literales, fuera de tokens) y **41 bloques `@keyframes`**
repartidos en ~70 `.module.css` de features (conteos verificados por grep 2026-07-15, ver §3).
Cada feature elige su propia duración y curva ⇒ inconsistencia perceptual, timings que "saltan",
easings incoherentes. Además NINGÚN plan agrega la capa de **micro-interacción** (press/hover
consistentes, entrada/salida tokenizada) ni de **feedback óptimista** (estado "encolando/guardando"
inmediato al disparar una acción).

Este plan cierra ese gap con: (a) **tokens de motion de nivel superior** construidos SOBRE los
del 138 (duraciones de bucle + 4 presets compuestos de transición); (b) un **ratchet
anti-regresión de motion** (vitest fs+regex, baseline por archivo) espejo del ratchet de color
del 138, con deuda forzada a 0 en `components/ui/` y `components/shell/`; (c) **migraciones
ejemplares byte-idénticas** que aprietan el ratchet y demuestran el patrón; (d) una **capa de
micro-interacción/feedback** (utilidades CSS tokenizadas + un hook `useOptimisticPending`); todo
respetando el `prefers-reduced-motion` del plan 141 (consumido, NO reimplementado).

**KPIs (todos binarios):**

- **KPI-1:** `npx vitest run src/__tests__/motionTokens.test.ts` exit 0 — los 6 tokens nuevos de
  §6.F0 existen en `theme.css` con su valor EXACTO, y los 6 tokens de motion del 138
  (`--duration-*`, `--ease-*`) siguen presentes con su valor (consumidos, no alterados).
- **KPI-2:** `npx vitest run src/__tests__/motionDebtRatchet.test.ts` exit 0 — baseline congelado;
  `components/ui/` y `components/shell/` con deuda de motion CERO (forzado mecánico).
- **KPI-3:** tras F1+F3+F4+F5, la deuda de motion por archivo SOLO baja. La deuda = nº de LITERALES
  de tiempo + `cubic-bezier` (lo que cuentan `TIME_RE`/`CUBIC_RE`); una línea
  `transition: a 0.12s, b 0.12s` cuenta **2**, no 1 (C1). Números verificados por grep 2026-07-15:
  `Skeleton.module.css` 1→0, `TicketSelector.module.css` **5→0**, `AgentRuntimeSelector.module.css`
  **2→0**, `AgentSelector.module.css` **2→0**, `AgentCard.module.css` **2→0**,
  `FileSelectorModal.module.css` 5→1. **La garantía dura y BINARIA es la monotonía por-archivo que
  verifica el ratchet**; estos números son ilustrativos (el baseline los recomputa mecánicamente,
  §F2 Paso 3 — NO copiarlos a mano).
- **KPI-4:** `npx vitest run src/__tests__/motionA11yGuard.test.ts` exit 0 — `theme.css` conserva
  EXACTAMENTE 1 bloque `@media (prefers-reduced-motion: reduce)` (el del plan 141 F5: 143 no lo
  duplica ni lo elimina); las utilidades nuevas no animan ninguna propiedad de layout (§4.4, guard
  robusto C6); y `.u-pending` cumple el contrato visual del feedback óptimista (atenúa + bloquea).
- **KPI-5:** `npx vitest run src/hooks/__tests__/useOptimisticPending.test.ts` exit 0 y
  `npx tsc --noEmit` exit 0.

---

## 2. Por qué ahora / gap que cierra

El plan 138 (§1, §10.1.G) creó los tokens de motion pero explícitamente los aplicó **solo a sus
primitivas** (`components/ui/`): sus migraciones ejemplares F3-F5 tokenizan 3 archivos de motion
puntuales y su ratchet cuenta **hex y `style={{`**, NO timing de motion. El plan 141 (§5 F5)
agregó el guardarraíl de accesibilidad `@media (prefers-reduced-motion: reduce)` que neutraliza
transiciones y animaciones globalmente, pero **no tokeniza** las 139 transiciones hardcodeadas:
solo las apaga cuando el SO lo pide. El plan 140 cubre skeletons de CARGA y estados vacíos, no el
sistema de motion general. **Resultado: el motion es la única dimensión del sistema de diseño sin
dueño ni gate.** Es el análogo exacto de lo que el 138 hizo para color:

| Dimensión | Tokens | Ratchet | Dueño |
|---|---|---|---|
| Color/spacing/tipografía | plan 138 §10.1 | plan 138 F0 (hex + `style={{`) | 138 |
| Tema claro/oscuro + a11y (focus, reduced-motion) | plan 141 F2 | plan 141 F3 (contraste + anti-drift) | 141 |
| **Motion (timing/easing/micro-interacción)** | **6 tokens (138) sin adopción general** | **NINGUNO** | **← este plan** |

**Evidencia grep verificada (2026-07-15, `Stacky Agents/frontend/src`):**

```
grep -rEn 'transition[^:]*:[^;]*[0-9]+m?s' --include='*.module.css' . | grep -vE 'var\(--(duration|ease|transition)' | wc -l
  => 139   (declaraciones-línea; deriva ±2 con WIP ajeno: 137 al re-medir 2026-07-15 — C3)
grep -rEn '@keyframes' --include='*.module.css' . | wc -l
  => 41    (bloques @keyframes repartidos en ~30 archivos)
```
> Nota (C3): estos son conteos de LÍNEAS, orientativos y volátiles ante WIP ajeno. La métrica dura
> que gatea el gate es la que recomputa el ratchet (LITERALES por archivo), no estos números.

Top archivos por transiciones hardcodeadas (grep): `TicketBoard.module.css` (12),
`ChatDrawer.module.css` (10), `TicketGraphView.module.css` (9), `AgentHistoryPage.module.css` (9),
`HarnessFlagsPanel.module.css` (7), `FlowConfigPage.module.css` (6), `DataReadinessModal.module.css`
(5). Duraciones de bucle sin tokenizar en el repo: `0.6s`, `0.7s`, `0.8s`, `1.2s`, `1.4s`, `1.6s`
(spinners y pulsos). El 138 solo tokenizó duraciones de INTERACCIÓN (`0.12/0.2/0.4s` para
transiciones), no las de BUCLE. Este plan cierra ambas costuras.

---

## 3. Conteos base de la deuda (línea base para el ratchet)

Verificados por grep el 2026-07-15. El ratchet de F2 los recalcula mecánicamente (NO se copian a
mano al baseline):

- **~137-139** declaraciones `transition:` con tiempo literal fuera de tokens. Es un grep de
  LÍNEAS (`grep -c`) y **deriva ±2 según WIP ajeno** (medido 139 al proponer, 137 al criticar
  2026-07-15). NO es la métrica que gatea el ratchet: éste cuenta LITERALES por archivo (típicamente
  2 por declaración de 2 propiedades), por eso los números por-archivo de KPI-3 son mayores que el
  nº de líneas. La monotonía la garantiza el baseline recomputado, no este número (C1, C3).
- **41** bloques `@keyframes` en `.module.css` de features (contexto; el ratchet NO los cuenta:
  gobierna DURACIÓN/easing, no la forma del keyframe).
- **0** declaraciones `animation:` con tiempo literal que además ya usen `var(--duration|ease)`
  (o sea: hoy no hay animaciones parcialmente tokenizadas — todas están 100% hardcodeadas o viven
  en `ui/` con tokens del 138).
- Único offender de motion dentro de `components/ui/` tras el 138: `Skeleton.module.css`
  (`animation: uiSkeletonPulse 1.4s var(--ease-in-out) infinite;` — el `1.4s` es literal). El
  `Spinner` del 138 no cuenta: su duración viene por `style` inline en `Spinner.tsx`
  (`animationDuration: ${durationMs ?? 800}ms`), fuera del CSS. `components/shell/` (plan 139) es
  token-only por su propio ratchet (139 §... "0 hex") — F1 verifica que también sea 0 en motion.

---

## 4. Principios y guardarraíles

### 4.1 Sin flag de harness (justificación por naturaleza del cambio)

| Fase | ¿Flag? | Por qué |
|---|---|---|
| F0 tokens + presets | No | Aditivo a `:root` de `theme.css`. Byte-idéntico: ningún elemento los consume aún. Reversible con revert. |
| F1 tokenizar Skeleton (138) | No | Reemplaza `1.4s` por `var(--duration-pulse)` (= `1.4s`). BYTE-IDÉNTICO. |
| F2 ratchet + baseline | No | Archivos de test; no tocan runtime de la app. |
| F3/F4/F5 migraciones ejemplares | No | BYTE-IDÉNTICAS (cada literal migrado mapea EXACTO a su token). Cero cambio visible. |
| F6 utilidades + hook | No | Utilidades **opt-in** (un feature debe agregar la clase para verlas; sin adopción, cero cambio). El hook es estado local efímero de presentación. |

Ninguna de las 4 excepciones duras de flag (kill-switch de seguridad, gasto/egreso, cambio de
comportamiento de agente, override de defaults) aplica: es presentación pura, aditiva y reversible.
Criterio idéntico al del plan 141 C2: una MEJORA no-regresiva que respeta reduced-motion no
necesita flag. Documentado por fase con la línea "Flag: sin flag".

### 4.2 Anti-frágil ante WIP ajeno (zonas calientes)

`theme.css` y los `.module.css` de features son ZONAS CALIENTES (132/134/135/136/138-141 las tocan).
Reglas duras:

- **Todas las anclas son por TEXTO normativo** (los `:NN` son orientativos). Los `Edit` fallan
  solos si el texto ancla no existe ⇒ el implementador PARA y reporta (auto-protección).
- **Pre-flight por fase:** antes de tocar cada archivo, correr `git status -- "<ruta>"`. Si hay
  WIP ajeno sin commitear ⇒ STOP, avisar, NO editar.
- **Staging quirúrgico:** `git add -- <paths explícitos>`. NUNCA `git add -A`.
- **NO se edita `main.tsx`** (está en la lista prohibida R6 del 138 y es hot zone). Por eso las
  utilidades CSS se APENDEAN a `theme.css` (que ya está importado globalmente), como hizo el 141
  F5 con su bloque de a11y — no se crea un stylesheet nuevo que requiera un import en `main.tsx`.
- **Lista prohibida heredada (138 §3.4-R6):** este plan NO edita ninguno de: `App.tsx`,
  `TopBar.tsx`/`.module.css`, `ActiveRunsPanel.tsx`, `CodexConsoleDock.tsx`,
  `SettingsPage.tsx`/`.module.css`, `TicketBoard.tsx`/`.module.css`, `IntentPreflightModal.tsx`,
  `AgentHistoryPage.tsx`/`.module.css`, `HarnessFlagsPanel.tsx`/`.module.css`, `ChatDrawer.tsx`,
  `RecoverExecutionButton.tsx`, `EmptyState.tsx`, `main.tsx`, ni el Toast del 135. Los archivos que
  este plan SÍ edita están todos fuera de esa lista (verificado en §6 por fase).

### 4.3 Deslinde con el plan 141 (dueño de reduced-motion)

El plan 141 F5 es el ÚNICO dueño de `@media (prefers-reduced-motion: reduce)` y del focus ring.
Este plan **jamás escribe una regla `@media (prefers-reduced-motion)`**. Sus tokens y presets fijan
la duración vía el shorthand `transition:`/`animation:`; cuando el SO pide reducir movimiento, la
regla global del 141 (`transition-duration: 0.01ms !important; animation-duration: 0.01ms
!important; animation-iteration-count: 1 !important`) gana por `!important` y neutraliza TODO lo de
este plan automáticamente, sin acoplamiento. KPI-4 lo verifica mecánicamente. (Es el mismo tipo de
deslinde que el plan 140 hace con el Toast del 135.)

### 4.4 Performance (regla dura, binaria)

Las utilidades y presets de este plan SOLO animan propiedades que **no fuerzan reflow**:
`transform` y `opacity` (composite, GPU) y `color`/`background-color`/`border-color`/`fill`/`stroke`
y `box-shadow` (paint, sin reflow). **PROHIBIDO** que un token/preset/utilidad de este plan anime
`width`, `height`, `top`, `left`, `right`, `bottom`, `margin`, `padding` u otra propiedad de layout.
KPI-4 (`motionA11yGuard.test.ts`) verifica con un regex ROBUSTO (C6) que ninguna propiedad de layout
(`width|height|top|left|right|bottom|inset|margin|padding|inline-size|block-size`) aparezca como
propiedad animada en un `transition`/`transition-property` (shorthand o longhand, en cualquier
posición del valor) ni en los `@keyframes` del bloque 143.

### 4.5 Paridad de los 3 runtimes (Codex CLI, Claude Code CLI, GitHub Copilot Pro)

Este plan es 100% capa de PRESENTACIÓN (CSS/TSX servidos al navegador). Es **idéntico en los 3
runtimes**: no hay ramas por runtime, no hay backend, no hay prompts de agente. **Fallback: N/A**
(no hay comportamiento que degradar por runtime). Declarado explícito por fase.

### 4.6 Human-in-the-loop y mono-operador

No agrega autonomía ni decisiones nuevas: amplifica la percepción del operador (feedback inmediato,
consistencia). Mono-operador sin auth: no toca permisos, roles ni RBAC. Cero trabajo del operador
(§ "Trabajo del operador: ninguno" por fase).

---

## 5. Glosario corto

- **Token de motion:** variable CSS que nombra una duración o curva de easing (ej.
  `--duration-fast`, `--ease-out-expo`). Fuente única de timing.
- **Preset compuesto:** token cuyo valor es un fragmento de shorthand `transition` listo para usar
  (ej. `--transition-transform: transform var(--duration-base) var(--ease-out-expo)`).
- **Ratchet (trinquete):** test que congela una métrica en un baseline y solo permite que BAJE.
- **reduced-motion:** preferencia del SO (`prefers-reduced-motion: reduce`) para minimizar
  animaciones. Dueño en Stacky: plan 141 F5.
- **Micro-interacción:** feedback visual pequeño y consistente ante hover/press/entrada/salida.
- **Feedback óptimista:** mostrar de inmediato que una acción está "en vuelo" (encolando/guardando)
  antes de que el backend responda, para que la UI no se sienta congelada.
- **Layout thrash / reflow:** recálculo caro del layout que dispara animar propiedades geométricas
  (width/height/top/…). Se evita animando solo `transform`/`opacity`.
- **fs+regex test:** test vitest que lee un archivo con `fs.readFileSync` y aplica regex sobre su
  contenido (idioma de tests de UI de la casa; ver 138 F0 y 141 F5).

---

## 6. Fases

Orden por dependencia: **F0 (tokens) → F1 (limpiar primitivas) → F2 (ratchet) → F3/F4/F5
(migraciones) → F6 (micro-interacción)**. El ratchet (F2) no puede forzar 0 en `ui/` hasta que F1
tokenice el `1.4s` del `Skeleton` del 138; por eso F1 precede a F2 (adaptación consciente del orden
del 138, cuyas primitivas de color nacían en 0 pero cuyo Skeleton carga una duración de bucle
hardcodeada). Cada fase deja la suite verde por sí sola y es verificable en aislamiento.

> **Comando de tests (idioma de la casa):** siempre desde `Stacky Agents/frontend`, con
> `npx vitest run <ruta>` y `npx tsc --noEmit`. No hay RTL/jsdom en `package.json` (gap
> estructural conocido): por eso los tests son fs+regex y de funciones puras, nunca de render.

---

### F0 — Tokens de motion de nivel superior en `theme.css`

**Objetivo (1 frase):** agregar al `:root` de `theme.css` 2 duraciones de bucle y 4 presets
compuestos, construidos SOBRE los tokens del 138, sin alterar ningún valor existente.
**Valor:** da nombre semántico a las duraciones de bucle (que el 138 no tokenizó) y ofrece presets
listos-para-usar que colapsan el timing+easing de las familias de propiedad más comunes.

**Archivos:**
- EDITAR `frontend/src/theme.css`
- CREAR `frontend/src/__tests__/motionTokens.test.ts`

**Pre-flight:** `git status -- "Stacky Agents/frontend/src/theme.css"` debe estar limpio.

**Paso 1 — TDD (rojo).** Crear `frontend/src/__tests__/motionTokens.test.ts` con contenido EXACTO:

```ts
/**
 * Plan 143 F0 — Contrato de tokens de motion de nivel superior.
 * Congela nombre y valor EXACTO de cada token nuevo, y verifica que los tokens de
 * motion del plan 138 sigan presentes con su valor (este plan los CONSUME, no los redefine).
 */
import { describe, it, expect } from "vitest";
import * as fs from "fs";

const THEME = fs.readFileSync(new URL("../theme.css", import.meta.url), "utf-8");

// Tokens NUEVOS del plan 143 (van al :root base de theme.css, tras el bloque Motion del 138).
const FROZEN_MOTION: [string, string][] = [
  ["--duration-spin", "0.7s"],
  ["--duration-pulse", "1.4s"],
  [
    "--transition-colors",
    "color var(--duration-fast) var(--ease-standard), background-color var(--duration-fast) var(--ease-standard), border-color var(--duration-fast) var(--ease-standard), fill var(--duration-fast) var(--ease-standard), stroke var(--duration-fast) var(--ease-standard)",
  ],
  ["--transition-transform", "transform var(--duration-base) var(--ease-out-expo)"],
  ["--transition-opacity", "opacity var(--duration-fast) var(--ease-standard)"],
  ["--transition-elevation", "box-shadow var(--duration-base) var(--ease-standard)"],
];

// Tokens del plan 138 que este plan CONSUME sin redefinir (deben seguir con su valor exacto).
const CONSUMED_138: [string, string][] = [
  ["--duration-fast", "0.12s"],
  ["--duration-base", "0.2s"],
  ["--duration-slow", "0.4s"],
  ["--ease-standard", "ease"],
  ["--ease-in-out", "ease-in-out"],
  ["--ease-out-expo", "cubic-bezier(0.16, 1, 0.3, 1)"],
];

describe("Plan 143 F0 — tokens de motion nuevos", () => {
  it("los 6 tokens nuevos existen con su valor EXACTO", () => {
    const missing = FROZEN_MOTION.filter(([n, v]) => !THEME.includes(`${n}: ${v};`));
    expect(missing.map(([n]) => n), "Tokens de motion faltantes o con valor distinto").toEqual([]);
  });
});

describe("Plan 143 F0 — tokens del 138 consumidos sin alterar", () => {
  it("los 6 tokens de motion del 138 siguen presentes con su valor", () => {
    const broken = CONSUMED_138.filter(([n, v]) => !THEME.includes(`${n}: ${v};`));
    expect(broken.map(([n]) => n), "Tokens de motion del 138 alterados o ausentes").toEqual([]);
  });
});
```

**Paso 2 — rojo por la razón correcta:** `npx vitest run src/__tests__/motionTokens.test.ts`
falla en "los 6 tokens nuevos existen" (aún no están en `theme.css`).

**Paso 3 — editar `theme.css`.** Ancla NORMATIVA: la última línea del bloque Motion del 138 es
exactamente:
```
  --ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);
```
Insertar INMEDIATAMENTE DESPUÉS de esa línea (dentro del mismo `:root`) el bloque VERBATIM
(el valor de `--transition-colors` va en UNA sola línea física; no partirlo):

```css

  /* ─── Motion de nivel superior (Plan 143) ──────────────────────────
     Construido SOBRE los tokens atómicos del plan 138 (--duration-*, --ease-*).
     NO redefine ni altera ningún token del 138. El plan 141 F5 neutraliza todo
     esto cuando el SO pide prefers-reduced-motion (no se reimplementa acá). */
  /* Duraciones de BUCLE (animaciones infinitas: spinners, pulsos). Complementan
     las duraciones de INTERACCIÓN fast/base/slow del 138 (que son para transiciones). */
  --duration-spin: 0.7s;
  --duration-pulse: 1.4s;
  /* Presets de transición por familia de propiedad. Uso: transition: var(--transition-colors);
     Solo animan propiedades sin reflow (color-family/transform/opacity/box-shadow), §4.4. */
  --transition-colors: color var(--duration-fast) var(--ease-standard), background-color var(--duration-fast) var(--ease-standard), border-color var(--duration-fast) var(--ease-standard), fill var(--duration-fast) var(--ease-standard), stroke var(--duration-fast) var(--ease-standard);
  --transition-transform: transform var(--duration-base) var(--ease-out-expo);
  --transition-opacity: opacity var(--duration-fast) var(--ease-standard);
  --transition-elevation: box-shadow var(--duration-base) var(--ease-standard);
```

**Paso 4 — verde:** los 4 comandos exit 0:
- `npx vitest run src/__tests__/motionTokens.test.ts`
- `npx vitest run src/__tests__/themeTokens.test.ts` (138 F1 — SIGUE verde: solo agregamos tokens;
  su test congela SU lista de 69, no rechaza tokens extra)
- `npx vitest run src/__tests__/a11yCss.test.ts` (141 F5 — sin cambios)
- `npx tsc --noEmit`

**Interacción con tests de 138/141 (verificado):** el test de 138 F1 (`themeTokens.test.ts`) asserta
`FROZEN_TOKENS.length === 69` sobre SU propio array y `includes()` de cada token — NO escanea
`theme.css` en busca de tokens no declarados, así que agregar tokens no lo rompe. El anti-drift de
141 F3 (`themeContrast.test.ts`) solo exige re-apuntar en el tema claro los tokens **cuyo valor es
un color** (`isColor = /#[0-9a-fA-F]|rgba?\(/`); los tokens de este plan tienen valores de motion
(sin `#` ni `rgba(`, incluido `--transition-colors` cuyo valor no contiene ningún hex/rgba), por lo
que NO son marcados ni deben ir al bloque claro. La lista `FORBIDDEN` de 141 F2 tampoco se afecta
(esos tokens no aparecen en el bloque `:root[data-theme="light"]`).

**Criterio de aceptación (binario):** los 4 comandos exit 0.
**Flag:** sin flag (§4.1). **Runtime:** presentación pura, idéntico, fallback N/A.
**Trabajo del operador:** ninguno.
**Staging:** `git add -- "Stacky Agents/frontend/src/theme.css" "Stacky Agents/frontend/src/__tests__/motionTokens.test.ts"`

---

### F1 — Tokenizar la animación de la primitiva `Skeleton` del 138

**Objetivo (1 frase):** reemplazar el `1.4s` hardcodeado del `Skeleton` del 138 por
`var(--duration-pulse)` para que `components/ui/` quede con deuda de motion 0 antes del ratchet.
**Valor:** habilita el forced-0 de `ui/` en F2 y es la primera prueba de que el token nuevo funciona.

**Archivos:** EDITAR `frontend/src/components/ui/Skeleton.module.css`

**Pre-flight:** `git status -- "Stacky Agents/frontend/src/components/ui/Skeleton.module.css"` limpio.
(Este archivo lo crea el plan 138 F2; F1 asume que el 138 ya está implementado en el árbol.)

**Paso 1 — editar.** Ancla NORMATIVA (línea creada por 138 F2), reemplazar EXACTO:
```
  animation: uiSkeletonPulse 1.4s var(--ease-in-out) infinite;
```
por:
```
  animation: uiSkeletonPulse var(--duration-pulse) var(--ease-in-out) infinite;
```
Es BYTE-IDÉNTICO: `--duration-pulse` = `1.4s`. Si el ancla no existe (138 no implementado o cambió el
valor), STOP y reportar — no inventar.

**Paso 2 — verificar `components/shell/` (plan 139) también en 0.** Correr:
```
grep -rEn '[0-9]*\.?[0-9]+m?s|cubic-bezier' "Stacky Agents/frontend/src/components/shell/" --include='*.module.css'
```
Resultado ESPERADO: vacío. **OJO (C2):** el ratchet del 139 es de COLOR ("0 hex"), NO garantiza que
`shell/` esté limpio de MOTION. Dos ramas:
- Si devuelve líneas con tiempo literal ON-SCALE (`0.12s`/`0.2s`/`0.4s`/`0.7s`/`1.4s`) o
  `cubic-bezier(0.16, 1, 0.3, 1)`: tokenizar con la **tabla §6.F3.T** (literal → `var(--duration-*)`
  / `cubic-bezier(...)` → `var(--ease-out-expo)`), byte-idéntico. Documentar cada reemplazo en el commit.
- Si devuelve algún tiempo **OFF-SCALE** (`0.1s`, `0.15s`, `0.6s`, `0.8s`, `1.2s`, `1.6s`, u otro
  fuera de la tabla): **STOP y reportar**. NO forzar: un off-scale no es tokenizable byte-idéntico y
  el forced-0 de `shell/` en F2 (Paso 1, `it` tercero) sería inalcanzable ⇒ el plan quedaría
  bloqueado. Es la ÚNICA situación donde el forced-0 de `shell/` es inválido; requiere decisión de
  diseño del operador (snap al scale = cambio visual), fuera de scope (§8). Si `components/shell/` ni
  siquiera existe (139 no implementado), este paso es vacío-trivial y el forced-0 de F2 pasa sin
  archivos: continuar normal.

**Paso 3 — verde:** `npx vitest run src/__tests__/uiPrimitives.test.ts` (test de las primitivas del
138 F2) sigue verde, y `npx tsc --noEmit` exit 0. El cambio es solo CSS: no afecta lógica.

**Criterio de aceptación (binario):** `grep -c 'cubic-bezier\|[0-9]\+m\?s' src/components/ui/Skeleton.module.css`
no cuenta ningún tiempo literal fuera de `var(...)` (el `1.4s` desapareció) y `npx tsc --noEmit` exit 0.
**Flag:** sin flag (byte-idéntico). **Runtime:** presentación pura, idéntico, fallback N/A.
**Trabajo del operador:** ninguno.
**Staging:** `git add -- "Stacky Agents/frontend/src/components/ui/Skeleton.module.css"`
(y los archivos de `shell/` que el Paso 2 haya tocado, con paths explícitos).

---

### F2 — Ratchet anti-regresión de motion + baseline congelado

**Objetivo (1 frase):** congelar la deuda de motion actual (tiempos literales + `cubic-bezier`
inline por `.module.css`) en un baseline JSON y hacer fallar cualquier commit que la AUMENTE, con
deuda forzada a 0 en `components/ui/` y `components/shell/`.
**Valor:** convierte "no reintroducir motion hardcodeado" en un gate mecánico; es el candado que
protege el resto del sistema de motion (espejo del ratchet de color del 138 F0).

**Archivos (crear):**
- `frontend/src/__tests__/motionDebtRatchet.test.ts`
- `frontend/src/__tests__/motionDebtBaseline.json` (lo genera el propio test en modo regen)

**Paso 1 — TDD.** Crear `frontend/src/__tests__/motionDebtRatchet.test.ts` con contenido EXACTO
(estructura calcada del ratchet del 138 F0; cambia QUÉ cuenta):

```ts
/**
 * Plan 143 F2 — Ratchet de deuda de MOTION.
 * Congela, POR ARCHIVO, la cantidad de timing de motion HARDCODEADO en *.module.css
 * bajo src/: tiempos literales (ms/s NO vía var) + timing-functions cubic-bezier inline.
 * La deuda solo puede BAJAR. theme.css queda FUERA (no es *.module.css: ahí los tiempos son
 * las DEFINICIONES de tokens, legítimas).
 *
 * Regenerar baseline (solo cuando la deuda BAJÓ):
 *   PowerShell:  $env:MOTION_DEBT_REGEN='1'; npx vitest run src/__tests__/motionDebtRatchet.test.ts; Remove-Item Env:\MOTION_DEBT_REGEN
 *   bash:        MOTION_DEBT_REGEN=1 npx vitest run src/__tests__/motionDebtRatchet.test.ts
 *
 * Si renombrás/movés un archivo con deuda: mover a mano su entrada del baseline a la clave
 * nueva (mismo contador) y correr el test normal.
 */
import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const FRONTEND_ROOT = process.cwd(); // correr SIEMPRE desde Stacky Agents/frontend
const SRC = path.join(FRONTEND_ROOT, "src");
const BASELINE_PATH = path.join(SRC, "__tests__", "motionDebtBaseline.json");

// Un tiempo literal CSS: <número>[ms|s], NO parte de un identificador. Cubre 0.12s, 120ms, 1.4s, 0s.
const TIME_RE = /\b\d+(?:\.\d+)?m?s\b/g;
// Timing-function cubic-bezier escrita inline (debe ser var(--ease-out-expo)).
const CUBIC_RE = /cubic-bezier\s*\(/g;

interface Baseline {
  motionByFile: Record<string, number>;
}

export function countMatches(content: string, re: RegExp): number {
  const m = content.match(re);
  return m ? m.length : 0;
}

export function motionDebt(content: string): number {
  return countMatches(content, TIME_RE) + countMatches(content, CUBIC_RE);
}

function listFiles(root: string): string[] {
  const entries = fs.readdirSync(root, { recursive: true }) as string[];
  return entries
    .map((p) => p.split(path.sep).join("/"))
    .filter((p) => {
      const abs = path.join(root, p);
      return fs.existsSync(abs) && fs.statSync(abs).isFile();
    });
}

function computeCurrent(): Baseline {
  const files = listFiles(SRC);
  const motionByFile: Record<string, number> = {};
  for (const rel of files) {
    if (!rel.endsWith(".module.css")) continue; // theme.css y .css globales quedan fuera
    const content = fs.readFileSync(path.join(SRC, rel), "utf-8");
    const n = motionDebt(content);
    if (n > 0) motionByFile[rel] = n;
  }
  return { motionByFile: sortKeys(motionByFile) };
}

function sortKeys(obj: Record<string, number>): Record<string, number> {
  const out: Record<string, number> = {};
  for (const k of Object.keys(obj).sort()) out[k] = obj[k];
  return out;
}

function readBaseline(): Baseline | null {
  if (!fs.existsSync(BASELINE_PATH)) return null;
  return JSON.parse(fs.readFileSync(BASELINE_PATH, "utf-8")) as Baseline;
}

function assertNoIncrease(current: Baseline, baseline: Baseline): string[] {
  const errors: string[] = [];
  for (const [file, count] of Object.entries(current.motionByFile)) {
    const allowedBase = baseline.motionByFile[file] ?? 0;
    // Chrome/primitivas: SIEMPRE 0 (invariante mecánico). Cubre ui/ (138) y shell/ (139).
    const forcedZero = file.startsWith("components/ui/") || file.startsWith("components/shell/");
    const allowed = forcedZero ? 0 : allowedBase;
    if (count > allowed) {
      errors.push(
        `motion REGRESION en ${file}: ${count} > ${allowed} permitido. ` +
          `La deuda de motion solo puede bajar (plan 143). Usá var(--duration-*) / ` +
          `var(--ease-*) / var(--transition-*) de theme.css en vez de tiempos o cubic-bezier literales.`,
      );
    }
  }
  return errors;
}

describe("motionDebtRatchet (plan 143 F2)", () => {
  it("src/ existe (correr desde Stacky Agents/frontend)", () => {
    expect(fs.existsSync(SRC)).toBe(true);
  });

  it("la deuda de motion por archivo no aumenta respecto del baseline", () => {
    const current = computeCurrent();
    if (process.env.MOTION_DEBT_REGEN === "1") {
      const prev = readBaseline();
      if (prev) {
        const errs = assertNoIncrease(current, prev);
        expect(errs, "REGEN rechazado: archivos que AUMENTARON su deuda:\n" + errs.join("\n")).toEqual([]);
      }
      fs.writeFileSync(BASELINE_PATH, JSON.stringify(current, null, 2) + "\n", "utf-8");
      return;
    }
    const baseline = readBaseline();
    expect(baseline, `Falta ${BASELINE_PATH}. Generarlo con MOTION_DEBT_REGEN=1 (ver cabecera del test).`).not.toBeNull();
    const errs = assertNoIncrease(current, baseline as Baseline);
    expect(errs, errs.join("\n")).toEqual([]);
  });

  it("components/ui/ y components/shell/ nacen y se mantienen con deuda de motion CERO", () => {
    const current = computeCurrent();
    const dirty = Object.keys(current.motionByFile).filter(
      (f) => f.startsWith("components/ui/") || f.startsWith("components/shell/"),
    );
    expect(dirty, `Archivos de ui/ o shell/ con motion hardcodeado: ${dirty.join(", ")}`).toEqual([]);
  });
});
```

**Paso 2 — rojo por la razón correcta:** `npx vitest run src/__tests__/motionDebtRatchet.test.ts`
falla con `Falta ...motionDebtBaseline.json`.

**Paso 3 — generar el baseline:**
```powershell
# PowerShell, cwd = Stacky Agents\frontend
$env:MOTION_DEBT_REGEN='1'; npx vitest run src/__tests__/motionDebtRatchet.test.ts; Remove-Item Env:\MOTION_DEBT_REGEN
```
Esto escribe `frontend/src/__tests__/motionDebtBaseline.json` con el esquema
`{ "motionByFile": { "components/DataReadinessModal.module.css": 6, ... } }` (claves = rutas
relativas a `src/` con `/`, ordenadas; solo archivos con contador > 0; los valores los calcula el
test — NO copiarlos de este doc). **Prerequisito:** F1 ya corrió (si no, `Skeleton.module.css`
aparecería con deuda 1 y el tercer `it` fallaría por forced-0). Confirmarlo: la clave
`components/ui/Skeleton.module.css` NO debe estar en el JSON generado.

**Paso 4 — verde:** `npx vitest run src/__tests__/motionDebtRatchet.test.ts` pasa; `npx tsc --noEmit`
exit 0.

**Casos borde (por diseño):** archivo nuevo con motion hardcodeado → falla (permitido = 0 si no está
en baseline); archivo borrado → entrada stale inofensiva (se poda en el próximo regen); renombre →
falla con instrucción en la cabecera; regen tramposo con deuda aumentada → el modo regen lo rechaza;
`theme.css` NO se cuenta (no es `.module.css`: ahí los tiempos son las definiciones de tokens);
`var(--duration-fast)` no cuenta (sin tiempo literal); `linear`/`ease`/`ease-in-out` como palabra
NO se cuentan (solo tiempos literales + `cubic-bezier`), por eso dejar `linear` en un spinner no
suma deuda.

**Criterio de aceptación (binario):** `npx vitest run src/__tests__/motionDebtRatchet.test.ts` y
`npx tsc --noEmit` exit 0; el baseline NO contiene claves bajo `components/ui/` ni `components/shell/`.
**Flag:** sin flag (archivos de test). **Runtime:** presentación pura, idéntico, fallback N/A.
**Trabajo del operador:** ninguno.
**Staging:** `git add -- "Stacky Agents/frontend/src/__tests__/motionDebtRatchet.test.ts" "Stacky Agents/frontend/src/__tests__/motionDebtBaseline.json"`

---

### F3 — Migración ejemplar 1: `TicketSelector.module.css` (transición + animación)

**Objetivo (1 frase):** tokenizar las 2 transiciones y la animación de pulso de
`TicketSelector.module.css` a tokens, byte-idéntico, apretando el ratchet.
**Valor:** demuestra el patrón completo (transición Y animación de bucle) en un archivo real y
seguro (no está en la lista prohibida R6 ni en el scope de 138-141).

**Tabla de mapeo §6.F3.T (literal → token; usar en TODAS las migraciones):**

| Literal | Token |
|---|---|
| `0.12s` | `var(--duration-fast)` |
| `0.2s` | `var(--duration-base)` |
| `0.4s` | `var(--duration-slow)` |
| `0.7s` | `var(--duration-spin)` |
| `1.4s` | `var(--duration-pulse)` |
| `ease` (timing-function) | `var(--ease-standard)` |
| `ease-in-out` | `var(--ease-in-out)` |
| `cubic-bezier(0.16, 1, 0.3, 1)` | `var(--ease-out-expo)` |
| `linear` | **se deja como `linear`** (correcto para rotación continua; el ratchet no lo cuenta) |
| cualquier otro tiempo (`0.1s`, `0.15s`, `0.6s`, `0.8s`, `1.2s`, `1.6s`) | **NO migrar** (off-scale; requiere decisión de diseño → fuera de scope, §8) |

**Archivos:** EDITAR `frontend/src/components/TicketSelector.module.css`
**Pre-flight:** `git status -- "Stacky Agents/frontend/src/components/TicketSelector.module.css"` limpio.

**Paso 1 — editar (3 reemplazos byte-idénticos).** Hay 2 líneas de transición IDÉNTICAS
(`:33` y `:78`): usar reemplazo de TODAS las ocurrencias (el reemplazo es idéntico para ambas).

- Reemplazar TODAS las ocurrencias de:
  `transition: background 0.12s ease, border-color 0.12s ease;`
  por:
  `transition: background var(--duration-fast) var(--ease-standard), border-color var(--duration-fast) var(--ease-standard);`
- Reemplazar (única, `:154`):
  `animation: selectorPulse 1.4s infinite;`
  por:
  `animation: selectorPulse var(--duration-pulse) infinite;`

Si cualquier ancla no existe (WIP ajeno cambió el archivo), STOP y reportar.

**Paso 2 — apretar el ratchet:** el archivo pasa de deuda **5 → 0** (4×`0.12s` en las 2 transiciones
+ 1×`1.4s`; C1). Regenerar baseline:
```powershell
$env:MOTION_DEBT_REGEN='1'; npx vitest run src/__tests__/motionDebtRatchet.test.ts; Remove-Item Env:\MOTION_DEBT_REGEN
```
(el modo regen rechaza si algo subió; como solo bajó, escribe el baseline nuevo sin la clave
`components/TicketSelector.module.css`).

**Paso 3 — verde:** `npx vitest run src/__tests__/motionDebtRatchet.test.ts`,
`npx vitest run src/__tests__/uiDebtRatchet.test.ts` (138: no tocamos hex/`style={{`, sigue verde) y
`npx tsc --noEmit`, todos exit 0.

**Criterio de aceptación (binario):**
`grep -oE '[0-9]*\.?[0-9]+m?s' src/components/TicketSelector.module.css` no imprime `0.12s` ni `1.4s`
(quedan solo, si los hubiera, tiempos off-scale que no migramos); ratchet verde; tsc exit 0.
**Flag:** sin flag (byte-idéntico). **Runtime:** presentación pura, idéntico, fallback N/A.
**Trabajo del operador:** ninguno.
**Staging:** `git add -- "Stacky Agents/frontend/src/components/TicketSelector.module.css" "Stacky Agents/frontend/src/__tests__/motionDebtBaseline.json"`

---

### F4 — Migración ejemplar 2: selectores de agente (`AgentRuntimeSelector` + `AgentSelector` + `AgentCard`)

**Objetivo (1 frase):** tokenizar la transición única de cada uno de los 3 `.module.css` de
selección de agente, byte-idéntico.
**Valor:** demuestra que el patrón escala barato a varios archivos hermanos; los 3 están fuera de la
lista prohibida y del scope de 138-141.

**Archivos:** EDITAR
- `frontend/src/components/AgentRuntimeSelector.module.css`
- `frontend/src/components/AgentSelector.module.css`
- `frontend/src/components/AgentCard.module.css`

**Pre-flight:** `git status -- "Stacky Agents/frontend/src/components/AgentRuntimeSelector.module.css" "Stacky Agents/frontend/src/components/AgentSelector.module.css" "Stacky Agents/frontend/src/components/AgentCard.module.css"` limpio.

**Paso 1 — editar (1 reemplazo byte-idéntico por archivo; tabla §6.F3.T):**

- `AgentRuntimeSelector.module.css` — reemplazar
  `transition: background 0.12s, color 0.12s;`
  por
  `transition: background var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard);`
  (byte-idéntico: la timing-function por defecto de CSS es `ease` = `--ease-standard`).
- `AgentSelector.module.css` — reemplazar
  `transition: background 0.12s ease, border-color 0.12s ease;`
  por
  `transition: background var(--duration-fast) var(--ease-standard), border-color var(--duration-fast) var(--ease-standard);`
- `AgentCard.module.css` — reemplazar
  `transition: border-color 0.12s ease, background 0.12s ease;`
  por
  `transition: border-color var(--duration-fast) var(--ease-standard), background var(--duration-fast) var(--ease-standard);`

Cualquier ancla ausente ⇒ STOP y reportar.

**Paso 2 — apretar ratchet + verde:** regenerar baseline (comando de F3 Paso 2); luego
`npx vitest run src/__tests__/motionDebtRatchet.test.ts` y `npx tsc --noEmit` exit 0. Los 3 archivos
salen del baseline (deuda **2 → 0** cada uno: cada declaración anima 2 propiedades = 2 literales `0.12s`; C1).

**Criterio de aceptación (binario):** los 3 archivos ya no contienen `0.12s`
(`grep -c '0.12s' <archivo>` = 0); ratchet verde; tsc exit 0.
**Flag:** sin flag. **Runtime:** presentación pura, idéntico, fallback N/A.
**Trabajo del operador:** ninguno.
**Staging:** `git add -- "Stacky Agents/frontend/src/components/AgentRuntimeSelector.module.css" "Stacky Agents/frontend/src/components/AgentSelector.module.css" "Stacky Agents/frontend/src/components/AgentCard.module.css" "Stacky Agents/frontend/src/__tests__/motionDebtBaseline.json"`

---

### F5 — Migración ejemplar 3: `FileSelectorModal.module.css` (parcial: spin + off-scale diferido)

**Objetivo (1 frase):** tokenizar el spinner (`0.7s`) y las transiciones `0.12s` de
`FileSelectorModal.module.css`, dejando documentado el `0.1s` off-scale sin tocar.
**Valor:** demuestra (a) el consumo de `--duration-spin`, (b) que el ratchet acepta migraciones
PARCIALES (la deuda baja aunque no llegue a 0), y (c) el diferimiento consciente de valores off-scale
sin cambiar píxeles. Archivo fuera de la lista prohibida.

**Archivos:** EDITAR `frontend/src/components/FileSelectorModal.module.css`
**Pre-flight:** `git status -- "Stacky Agents/frontend/src/components/FileSelectorModal.module.css"` limpio.

**Paso 1 — editar (byte-idéntico; tabla §6.F3.T):**

- Reemplazar (`:137`)
  `animation: spin 0.7s linear infinite;`
  por
  `animation: spin var(--duration-spin) linear infinite;`
- Reemplazar (`:254`)
  `transition: background 0.12s, color 0.12s;`
  por
  `transition: background var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard);`
- Reemplazar (`:271`)
  `transition: opacity 0.12s;`
  por
  `transition: opacity var(--duration-fast) var(--ease-standard);`
- **NO tocar** la línea (`:186`) `transition: background 0.1s;` — `0.1s` es off-scale; migrarlo
  cambiaría el timing (no hay token `0.1s`). Queda en el baseline como deuda residual documentada
  (§8). El `@keyframes spin { ... }` del archivo se deja igual (define la rotación, no tiene tiempo
  literal).

Cualquier ancla ausente (p.ej. si un plan de modales tocó el archivo) ⇒ STOP y reportar.

**Paso 2 — apretar ratchet + verde:** el archivo pasa de deuda 5 → 1. Regenerar baseline (comando de
F3 Paso 2); luego `npx vitest run src/__tests__/motionDebtRatchet.test.ts` y `npx tsc --noEmit`
exit 0. El baseline debe mostrar `components/FileSelectorModal.module.css: 1`.

**Criterio de aceptación (binario):** el archivo ya no contiene `0.7s` ni `0.12s`
(`grep -cE '0\.7s|0\.12s' <archivo>` = 0) pero SÍ conserva `0.1s`; ratchet verde; tsc exit 0.
**Flag:** sin flag. **Runtime:** presentación pura, idéntico, fallback N/A.
**Trabajo del operador:** ninguno.
**Staging:** `git add -- "Stacky Agents/frontend/src/components/FileSelectorModal.module.css" "Stacky Agents/frontend/src/__tests__/motionDebtBaseline.json"`

---

### F6 — Capa de micro-interacción: utilidades tokenizadas + hook `useOptimisticPending`

**Objetivo (1 frase):** agregar utilidades CSS opt-in (press/hover/entrada + feedback óptimista) a
`theme.css` y un hook de estado "acción en vuelo", ambos tokenizados y reduced-motion-safe.
**Valor:** da a cualquier feature una forma consistente y de una línea de sumar micro-interacción y
feedback inmediato, sin reinventar timing ni romper el ratchet.
**Nota de consumidor (C4):** este plan NO cablea las utilidades ni el hook a ninguna feature (§8: no
edita features; la lista prohibida R6 cubre casi todos los botones de acción). Por eso la reversión
óptimista ante fallo queda probada a nivel LÓGICA (`runWithPending`, test de rechazo) y CONTRATO CSS
(`.u-pending` atenúa+bloquea, KPI-4), pero NO validada visualmente en un flujo real. Primer adoptante
recomendado: un plan futuro que envuelva UNA acción segura fuera de R6 (p.ej. el botón "Encolar" de un
selector ya migrado) para probar el lazo end-to-end. Mientras tanto la capa es adopción-cero =
cambio-cero (no hay dead-code de runtime: las clases sin uso no se emiten, el hook sin import no entra
al bundle).

**Archivos:**
- EDITAR `frontend/src/theme.css` (APPEND al final, tras el bloque de a11y del 141 F5)
- CREAR `frontend/src/hooks/useOptimisticPending.ts`
- CREAR `frontend/src/hooks/__tests__/useOptimisticPending.test.ts`
- CREAR `frontend/src/__tests__/motionA11yGuard.test.ts`

**Pre-flight:** `git status -- "Stacky Agents/frontend/src/theme.css"` limpio.

**Paso 1 — TDD del hook (rojo).** Crear `frontend/src/hooks/__tests__/useOptimisticPending.test.ts`:

```ts
/**
 * Plan 143 F6 — feedback óptimista. Se testea la lógica PURA (runWithPending), sin render
 * (no hay RTL/jsdom en el repo). El hook envuelve esa lógica; tsc cubre el wrapper.
 */
import { describe, it, expect } from "vitest";
import { runWithPending } from "../useOptimisticPending";

describe("Plan 143 F6 — runWithPending", () => {
  it("marca pending true al empezar y false al terminar (éxito) y devuelve el valor", async () => {
    const calls: boolean[] = [];
    const r = await runWithPending((v) => calls.push(v), async () => 42);
    expect(r).toBe(42);
    expect(calls).toEqual([true, false]);
  });
  it("des-marca pending aunque la promesa rechace, y propaga el error", async () => {
    const calls: boolean[] = [];
    await expect(
      runWithPending((v) => calls.push(v), async () => {
        throw new Error("boom");
      }),
    ).rejects.toThrow("boom");
    expect(calls).toEqual([true, false]);
  });
});
```

**Paso 2 — rojo:** falla (no existe `useOptimisticPending.ts`).

**Paso 3 — crear el hook.** `frontend/src/hooks/useOptimisticPending.ts` con contenido EXACTO:

```ts
import { useCallback, useState } from "react";

/**
 * Plan 143 F6 — feedback óptimista LOCAL y EFÍMERO para UNA acción en vuelo.
 * NO reemplaza las señales persistentes de runs (plan 134) ni el surfacing de errores
 * (plan 135): es solo el estado visual "encolando/guardando" mientras dura una promesa.
 * Presentación pura, sin backend.
 *
 * CONTRATO DEL ADOPTANTE (C5): la promesa `op()` DEBE resolver O rechazar. `run` des-marca
 * `pending` en `finally`, así que un éxito o un error revierten el estado óptimista y liberan el
 * control (`.u-pending` vuelve a interactivo). Pero una promesa que NUNCA settlea dejaría el
 * control atenuado + `pointer-events: none` para siempre (soft-lock). Si la acción puede colgarse,
 * el adoptante DEBE imponer un timeout/AbortController antes de pasarla a `run`.
 * `run` re-lanza el error (no lo traga): el surfacing lo hace el plan 135, no este hook.
 */
export interface OptimisticPending {
  /** true mientras la operación envuelta está en vuelo. */
  pending: boolean;
  /** Envuelve una promesa: marca pending mientras corre; SIEMPRE la des-marca al terminar. */
  run: <T>(op: () => Promise<T>) => Promise<T>;
  /** Clase CSS a aplicar cuando pending: "u-pending" (plan 143) o "" cuando no. */
  pendingClass: string;
}

/** Lógica pura, testeable sin React. */
export async function runWithPending<T>(
  setPending: (v: boolean) => void,
  op: () => Promise<T>,
): Promise<T> {
  setPending(true);
  try {
    return await op();
  } finally {
    setPending(false);
  }
}

export function useOptimisticPending(): OptimisticPending {
  const [pending, setPending] = useState(false);
  const run = useCallback(
    <T,>(op: () => Promise<T>): Promise<T> => runWithPending(setPending, op),
    [],
  );
  return { pending, run, pendingClass: pending ? "u-pending" : "" };
}

export default useOptimisticPending;
```

Ejemplo de uso (documentación; NO editar features en este plan):
```tsx
const { pending, run, pendingClass } = useOptimisticPending();
<button className={pendingClass} aria-busy={pending}
  onClick={() => run(() => api.encolar(ticket))}>Encolar</button>
```

**Paso 4 — TDD del guard de a11y/performance (rojo).** Crear
`frontend/src/__tests__/motionA11yGuard.test.ts`:

```ts
/**
 * Plan 143 F6 — el plan 143 CONSUME el reduced-motion del 141, no lo redefine; y sus
 * utilidades no animan propiedades de layout (§4.4).
 */
import { describe, it, expect } from "vitest";
import * as fs from "fs";

const THEME = fs.readFileSync(new URL("../theme.css", import.meta.url), "utf-8");

describe("Plan 143 F6 — deslinde con 141 (reduced-motion)", () => {
  it("conserva EXACTAMENTE 1 bloque prefers-reduced-motion (el del plan 141 F5)", () => {
    const n = (THEME.match(/@media \(prefers-reduced-motion: reduce\)/g) || []).length;
    expect(n).toBe(1);
  });
});

describe("Plan 143 F6 — utilidades presentes, sin reflow y con contrato óptimista", () => {
  const BLOCK = THEME.slice(THEME.indexOf("/* ─── Micro-interacciones tokenizadas (Plan 143)"));

  it("existen las utilidades tokenizadas", () => {
    for (const cls of [".u-pressable", ".u-pending", ".u-fade-in", ".u-fade-in-up", ".u-transition-colors"]) {
      expect(THEME, `Falta la utilidad ${cls}`).toContain(cls);
    }
  });

  // [ADICIÓN ARQUITECTO] guard ROBUSTO (C6): detecta CUALQUIER propiedad de layout animada, en
  // shorthand o longhand y en cualquier posición del valor — no solo "transition: width". Cubre
  // "transition: opacity, width 0.2s" y "transition-property: height", que el guard v1 se salteaba.
  const LAYOUT = "width|height|top|left|right|bottom|inset|margin|padding|inline-size|block-size";
  it("ninguna utilidad anima propiedades de layout (§4.4)", () => {
    const re = new RegExp(`transition(?:-property)?\\s*:[^;{}]*\\b(?:${LAYOUT})\\b`, "g");
    const offenders = BLOCK.match(re) || [];
    expect(offenders, `Utilidad anima layout (reflow): ${offenders.join(" | ")}`).toEqual([]);
    // Los @keyframes del bloque 143 solo pueden animar opacity/transform (sin layout).
    const kfs = BLOCK.match(/@keyframes[\s\S]*?\}\s*\}/g) || [];
    for (const kf of kfs) {
      const bad = kf.match(new RegExp(`\\b(?:${LAYOUT})\\s*:`, "g"));
      expect(bad, `keyframe anima layout: ${kf.slice(0, 48)}`).toBeNull();
    }
  });

  // [ADICIÓN ARQUITECTO] contrato VISUAL del feedback óptimista (C4/C5): .u-pending DEBE atenuar
  // (opacity < 1) Y bloquear (pointer-events: none). Así el "en vuelo" es inequívoco y quitar la
  // clase revierte el estado: blinda la reversión-ante-fallo que el hook garantiza en su `finally`.
  it(".u-pending atenúa y bloquea (contrato de feedback óptimista)", () => {
    const m = BLOCK.match(/\.u-pending\s*\{[^}]*\}/);
    expect(m, "Falta el bloque .u-pending").not.toBeNull();
    const body = m ? m[0] : "";
    expect(/opacity\s*:\s*0?\.\d+/.test(body), ".u-pending debe atenuar (opacity < 1)").toBe(true);
    expect(/pointer-events\s*:\s*none/.test(body), ".u-pending debe bloquear la interacción").toBe(true);
  });
});
```

**Paso 5 — rojo:** falla ("existen las utilidades" y quizás el conteo si el 141 aún no aterrizó — el
141 debe estar implementado antes; ver §7 orden).

**Paso 6 — editar `theme.css` (APPEND al final del archivo).** Ancla NORMATIVA: el archivo termina
con el bloque de a11y del 141 F5 (que contiene `@media (prefers-reduced-motion: reduce)`). Agregar al
FINAL del archivo el bloque VERBATIM:

```css

/* ─── Micro-interacciones tokenizadas (Plan 143) ───────────────────────
   Utilidades OPT-IN: un feature las adopta agregando la clase; sin adopción, cero
   cambio visual. Solo animan transform/opacity/box-shadow/color-family (nunca layout
   → sin reflow, §4.4). El plan 141 F5 las neutraliza globalmente bajo prefers-reduced-motion. */

.u-transition-colors { transition: var(--transition-colors); }
.u-transition-transform { transition: var(--transition-transform); }
.u-transition-elevation { transition: var(--transition-elevation); }

/* "Presionable": hundimiento sutil al hacer :active. */
.u-pressable { transition: var(--transition-transform); }
.u-pressable:active { transform: translateY(1px); }

/* Entrada de listas/paneles (una sola vez). */
.u-fade-in { animation: uiFadeIn var(--duration-base) var(--ease-out-expo) both; }
.u-fade-in-up { animation: uiFadeInUp var(--duration-base) var(--ease-out-expo) both; }
@keyframes uiFadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes uiFadeInUp {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Feedback óptimista: acción en vuelo (encolando/guardando). Atenúa y bloquea la
   interacción sin ocultar el control. Combinar con aria-busy="true" en el elemento. */
.u-pending {
  opacity: 0.6;
  pointer-events: none;
  transition: opacity var(--duration-fast) var(--ease-standard);
}
```

**Paso 7 — verde:** los 6 comandos exit 0:
- `npx vitest run src/hooks/__tests__/useOptimisticPending.test.ts`
- `npx vitest run src/__tests__/motionA11yGuard.test.ts`
- `npx vitest run src/__tests__/motionTokens.test.ts` (F0 sigue verde)
- `npx vitest run src/__tests__/motionDebtRatchet.test.ts` (theme.css fuera del ratchet; sin cambio)
- `npx vitest run src/__tests__/a11yCss.test.ts` (141 F5 intacto)
- `npx tsc --noEmit`

**Criterio de aceptación (binario):** los 6 comandos exit 0.
**Flag:** sin flag (utilidades opt-in + hook de presentación). **Runtime:** presentación pura,
idéntico, fallback N/A. **Trabajo del operador:** ninguno.
**Staging:** `git add -- "Stacky Agents/frontend/src/theme.css" "Stacky Agents/frontend/src/hooks/useOptimisticPending.ts" "Stacky Agents/frontend/src/hooks/__tests__/useOptimisticPending.test.ts" "Stacky Agents/frontend/src/__tests__/motionA11yGuard.test.ts"`

---

## 7. Riesgos y mitigaciones

| Riesgo | Prob. | Mitigación |
|---|---|---|
| El 138/139/141 aún no están implementados en el árbol al momento de implementar 143 | Media | Este plan DEPENDE de ellos (§ encabezado). Pre-flight: verificar que existan `components/ui/Skeleton.module.css` (138) y el bloque `@media (prefers-reduced-motion: reduce)` en `theme.css` (141). Si faltan, STOP: implementar la serie primero (orden congelado). |
| WIP ajeno tocó un archivo a migrar y el ancla de texto cambió | Media | Todos los `Edit` fallan solos si el ancla no existe ⇒ STOP y reportar. Pre-flight `git status` por fase. Los archivos elegidos están fuera de la lista prohibida R6 del 138 y del scope de 138-141. |
| Un `Edit` byte-idéntico introduce un cambio visual sutil | Baja | Cada literal migrado mapea EXACTO a su token (0.12s=fast, 1.4s=pulse, 0.7s=spin, ease=standard). La timing-function por defecto de CSS es `ease` = `--ease-standard`, así que agregarla no cambia nada. Valores off-scale NO se migran. |
| El regex del ratchet cuenta un falso positivo (ej. `2px`, `100%`, un hex) | Baja | `TIME_RE` exige `<número>[ms\|s]` con boundaries; `px/%/rem/deg/fr` y hex no matchean (verificado con casos borde en §6.F2). `cubic-bezier` solo aparece en timing-functions. |
| `theme.css` es zona caliente (138/141 lo editan) y el append colisiona | Baja | Se APENDEA al final (patrón del 141 F5), sin tocar reglas existentes; pre-flight `git status`; staging quirúrgico. No se toca `main.tsx`. |
| El hook se solapa con 134 (awareness de runs) o 135 (errores mudos) | Baja | Deslinde explícito en el JSDoc del hook: es estado LOCAL y EFÍMERO de una acción en vuelo; no persiste señales ni surfacea errores. Complementa, no reemplaza. |
| Regenerar el baseline "esconde" una regresión de otro archivo | Baja | El modo `MOTION_DEBT_REGEN=1` corre `assertNoIncrease` contra el baseline previo ANTES de reescribir y rechaza si algo subió (igual que el 138 F0). |
| `components/shell/` (139) tiene motion OFF-SCALE ⇒ F2 fuerza shell/→0 pero F1 no puede tokenizarlo byte-idéntico (C2) | Media | F1 Paso 2 bifurca: on-scale ⇒ tokenizar; **off-scale ⇒ STOP y reportar** (el forced-0 de shell/ es inválido, requiere decisión de diseño). Si shell/ no existe (139 no implementado), el paso es vacío-trivial. |

---

## 8. Fuera de scope (explícito)

- **Migrar los 139 sitios de transición.** Este plan tokeniza 6 archivos ejemplares + la primitiva
  Skeleton; el resto baja progresivamente bajo el ratchet en planes/PRs futuros. El ratchet garantiza
  monotonía, no migración completa.
- **Valores de tiempo off-scale** (`0.1s`, `0.15s`, `0.6s`, `0.8s`, `1.2s`, `1.6s`): requieren una
  decisión de diseño (snap al scale = cambio visual). Quedan como deuda residual en el baseline;
  su migración es trabajo futuro, NO byte-idéntico.
- **Redefinir `prefers-reduced-motion` o el focus ring.** Son del plan 141 (consumidos).
- **Nuevas primitivas UI o Toast.** Son del 138/135. Este plan no crea componentes visuales, solo
  utilidades CSS y un hook de estado.
- **Timing embebido en lógica TS/JS** (ej. el `durationMs ?? 800` del `Spinner` del 138, animaciones
  manejadas en JS como `DocGraphView`/`forceLayout`): el ratchet gobierna declaraciones CSS. La
  configurabilidad por prop es una decisión de componente, no deuda de CSS.
- **Backend, endpoints, flags, agentes, prompts.** Nada de eso se toca.

---

## 9. Próximos planes UX/UI recomendados (roadmap liviano; NO son planes completos)

Candidatos (numeración final **150/151/152** — se renumeró desde 144/145/146 para no colisionar con
una serie de confiabilidad ajena 144-149 de otra sesión) que se apoyan en la fundación 138-143 ya
montada (una línea de rationale c/u). **YA PROPUESTOS como planes completos:**

- **150 — Densidad adaptativa / responsive:** tokens de densidad (`cómodo` / `compacto`) que
  reescalan la escala de spacing del 138 según viewport o preferencia; alto valor en tableros densos
  (`TicketBoard`) y pantallas chicas. Reusa spacing del 138 + motion del 143 para transicionar la
  densidad suavemente.
- **151 — Onboarding / first-run guiado:** tour de capacidades para operador nuevo (dónde está cada
  cosa), aprovechando el sistema de diseño + micro-interacciones ya consistentes; reduce la curva sin
  agregar backend (estado local + `localStorage`).
- **152 — Centro de notificaciones/actividad unificado:** consolida toasts (135) + señales
  persistentes de runs (134) + KPIs de costos (142) en un único feed con las micro-interacciones de
  entrada/salida del 143; un solo lugar para "qué pasó / qué está pasando".

---

## 10. Orden de implementación + Definición de Hecho (DoD) global

**Orden (numerado, por dependencia):**
1. **F0** — tokens + presets en `theme.css` (fundación; los demás los consumen).
2. **F1** — tokenizar `Skeleton` del 138 (deja `ui/` y `shell/` en 0 de motion).
3. **F2** — ratchet + baseline con forced-0 (el candado; requiere F1).
4. **F3** — migración `TicketSelector` (aprieta el ratchet).
5. **F4** — migración selectores de agente (aprieta el ratchet).
6. **F5** — migración `FileSelectorModal` parcial (aprieta el ratchet; demuestra off-scale diferido).
7. **F6** — utilidades de micro-interacción + hook `useOptimisticPending`.

F3/F4/F5 pueden reordenarse entre sí (independientes). F6 puede ir en cualquier momento tras F0
(y tras que el 141 F5 esté en el árbol, por KPI-4). F0→F1→F2 es estricto.

**DoD global (todos binarios, cwd = `Stacky Agents/frontend`):**
- [ ] `npx vitest run src/__tests__/motionTokens.test.ts` exit 0 (KPI-1).
- [ ] `npx vitest run src/__tests__/motionDebtRatchet.test.ts` exit 0; baseline sin claves bajo
      `components/ui/` ni `components/shell/` (KPI-2).
- [ ] La deuda por archivo bajó en los 6 archivos migrados + Skeleton (KPI-3), verificable en el
      diff del `motionDebtBaseline.json`.
- [ ] `npx vitest run src/__tests__/motionA11yGuard.test.ts` exit 0: 1 solo bloque
      `prefers-reduced-motion`, utilidades sin propiedades de layout (KPI-4).
- [ ] `npx vitest run src/hooks/__tests__/useOptimisticPending.test.ts` exit 0 y
      `npx tsc --noEmit` exit 0 (KPI-5).
- [ ] Suites preexistentes intactas: `npx vitest run src/__tests__/themeTokens.test.ts`,
      `npx vitest run src/__tests__/uiDebtRatchet.test.ts`, `npx vitest run src/__tests__/a11yCss.test.ts`
      todos exit 0.
- [ ] Sin flag nuevo, sin backend tocado, sin dependencia nueva (`package.json` sin cambios).
- [ ] Trabajo del operador: ninguno en todas las fases.
```
