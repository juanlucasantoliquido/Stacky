# Plan 138 — Sistema de diseño v2: tokens semánticos y primitivas UI

**Versión:** v2 (criticado 2026-07-15) — v1 propuesto 2026-07-14
**Estado:** IMPLEMENTADO F0-F6 (2026-07-15). Doc previo: CRITICADO v1→v2 · APROBADO-CON-CAMBIOS. Nota: `PipelineStatus.module.css` tenía un 7º hex (`.nextLabel strong`) no listado en la tabla de F3 — sustituido igual por `--status-info-text` (mismo valor exacto, R2) para cumplir el criterio binario "grep → 0"; los totales absolutos de deuda drift-earon levemente vs. el snapshot del doc (esperado, KPI-3 es por-archivo).
**Origen:** pedido del operador de "mejorar drásticamente la UI y UX de Stacky Agents".
**Serie:** UI/UX **138 → 139 → 140 → 141** (orden de implementación CONGELADO; este plan es la FUNDACIÓN).
**Alcance:** 100% frontend. Cero backend nuevo, cero endpoint nuevo, cero flag de harness, cero dependencia nueva (`package.json` NO se toca).
**Flag:** NO lleva flag (decisión justificada por fase en §3.1; precedente plan 132 §3.1 y plan 135 §3.1: aditivo + reversible con revert + cero backend).
**Convive con:** serie pendiente 132→134→135→136 (orden congelado por plan 134 v2 §3.3 — TODA la serie 138-141 aterriza DESPUÉS), plan 119 (shell DevOps v2, ya implementado en rama), plan 129 (paleta Ctrl+K, implementado), planes 63/78/82/86 (UI de config del arnés, implementados). Detalle en §3.3.

> Este documento está redactado para que un MODELO MENOR (Haiku, Codex CLI o GitHub
> Copilot Pro) lo implemente SIN inferir nada. Rutas, símbolos, nombres de tokens,
> firmas de props y comandos son LITERALES. Prohibido desviarse de los nombres exactos,
> prohibido "mejorar" valores o alcance. Todo lo ambiguo ya fue decidido acá.
> Regla de la casa: los `:NN` citados son ORIENTATIVOS; el TEXTO/símbolo citado es NORMATIVO.

---

## 0. Changelog de crítica v1 → v2 (juez adversarial, 2026-07-15)

Veredicto: **APROBADO-CON-CAMBIOS** (0 bloqueantes; 2 IMPORTANTES; 1 MENOR). Plan de
altísima calidad; los cambios endurecen el contrato de la serie sin ampliar alcance.

- **C1 (IMPORTANTE) — resuelto in place.** Las primitivas embebían literales `rgba(...)`
  NO tokenizados que la ratchet NO cuenta (solo cuenta hex) y que asumen fondo oscuro: el
  `trackColor` por defecto del `Spinner` (`rgba(255, 255, 255, 0.15)`) queda **invisible
  sobre el fondo claro del plan 141**. Fix: se agrega el token **`--spinner-track`** (§10.1.B),
  el `Spinner` lo usa por defecto, y el plan 141 lo re-apunta en el bloque claro. Byte-idéntico
  en dark (`--spinner-track: rgba(255, 255, 255, 0.15)`), themeable en claro. (Los overrides
  explícitos sobre fondos de color —`Button loading`, `RunButton` warn— se dejan como están:
  su pista lee bien sobre el fondo coloreado en ambos temas.)
- **C2 (IMPORTANTE) — resuelto in place.** KPI-3 fijaba un TOTAL ABSOLUTO de hex (≤ 1.214)
  que es un snapshot frágil (119 y otros planes mergean hex antes de que aterrice el 138). Se
  reescribe a términos **por-archivo** (la única garantía que el ratchet realmente da); el
  total absoluto queda como orientativo.
- **C3 (MENOR) — resuelto in place.** La regla "deuda 0 forzada" del ratchet solo cubría
  `components/ui/`; el plan 139 crea archivos en `components/shell/`. Se extiende el forzado a
  **`components/ui/` y `components/shell/`** para que el invariante "chrome/primitivas siempre
  en 0" sea mecánico, no incidental.
- **[ADICIÓN ARQUITECTO]** — el token `--spinner-track` (C1) es un fix de SERIE: cierra una
  costura no-themeable que ni 138 ni 141 v1 resolvían, respetando "tokens-only" de R4, 3
  runtimes (presentación pura), cero trabajo del operador y byte-identidad dark. El plan 141
  v2 lo consume en su bloque claro (`REQUIRED` pasa de 52 a 53 tokens).

Impacto en la serie: 141 v2 agrega `--spinner-track` a su lista `REQUIRED` de tokens claros.
139/140 no requieren cambios por esta crítica (el forced-0 extendido los beneficia).

---

## 1. Objetivo + KPIs binarios

Stacky tiene hoy una sola fuente de tokens (`theme.css`) con ~20 variables que cubren
superficies, texto y 3 colores de estado planos — sin variantes, sin escala de spacing,
sin escala tipográfica, sin sombras sistematizadas, sin motion, sin tokens de foco. El
resultado medible: **1.231 colores hex hardcodeados en 70 archivos `.module.css`** y
**772 objetos `style={{...}}` inline en 70 archivos `.tsx`**, con CERO primitivas UI
compartidas (`frontend/src/components/ui/` no existe): cada componente reinventa botones,
chips, cards, spinners y skeletons. Este plan crea la fundación del rediseño: (a) un set
completo de **tokens semánticos** en `theme.css` con valores **byte-compatibles** con la
estética actual (cero cambio visual), estructurado **theme-ready** para el tema claro del
plan 141; (b) **8 primitivas UI congeladas** en `frontend/src/components/ui/` que
consumen SOLO tokens; (c) un **ratchet anti-regresión** (test vitest fs+regex con
baseline JSON por archivo) que garantiza que la deuda visual solo puede BAJAR; y (d)
**3 migraciones ejemplares** de bajo riesgo que demuestran el patrón y aprietan el ratchet.

**KPIs (todos binarios):**

- **KPI-1:** `npx vitest run src/__tests__/themeTokens.test.ts` verde — los 69 tokens
  nuevos de §10.1 existen en `theme.css` con su valor EXACTO y los tokens legacy
  (`--bg-base`, `--accent`, etc.) conservan su valor actual sin cambios.
- **KPI-2:** `npx vitest run src/__tests__/uiPrimitives.test.ts` verde — las 8 primitivas
  de §10.2 existen en `frontend/src/components/ui/`, el barrel `index.ts` las re-exporta,
  y NINGÚN archivo de `components/ui/` contiene hex ni `style={{` literal.
- **KPI-3 (por-archivo, no total absoluto):** `npx vitest run
  src/__tests__/uiDebtRatchet.test.ts` verde — baseline congelado; tras F3-F5 los 3
  ejemplares quedan con hex = 0 POR ARCHIVO (`PipelineStatus.module.css` 6→0,
  `SyncStatusBar.module.css` 6→0, `RunButton.module.css` 5→0) y NINGÚN archivo aumenta su
  contador respecto del baseline. (El total absoluto de hex —~1.231 hoy, orientativo
  snapshot 2026-07-14— es informativo: baja ~17 con estas 3 migraciones, pero NO es un
  criterio binario porque otros planes —p. ej. 119— mergean hex antes de que aterrice el
  138; la garantía dura es la monotonía por-archivo del ratchet.)
- **KPI-4:** `npx tsc --noEmit` termina con exit code 0 y `npx vitest run` (suite
  completa frontend) verde.
- **KPI-5:** cero cambio visual — cada sustitución hex→`var(--token)` de F3-F5 usa un
  token cuyo valor es EXACTAMENTE el hex sustituido (tabla de sustituciones en cada fase);
  no existe sustitución con valor distinto.

**Trabajo del operador: ninguno.** Todo es invisible y automático; no hay flag que
activar, no hay configuración nueva, no hay cambio de comportamiento.

---

## 2. Por qué ahora / gap (evidencia verificada 2026-07-14)

Evidencia re-verificada contra el working tree en `main` (los `:NN` son orientativos, el
texto citado es normativo):

1. **`frontend/src/theme.css` es la única fuente de tokens y está incompleta.** El bloque
   `:root` (`theme.css:3-46`) define: superficies y bordes (`--bg-base: #0d1117`,
   `--bg-panel: #161b22`, `--bg-elev: #21262d`, `--border: #30363d`, `--border-muted`,
   líneas 5-9), texto (`--text-primary: #e6edf3`, `--text-muted: #8b949e`,
   `--text-faint: #6e7681`, líneas 12-14), accent y estados PLANOS
   (`--accent: #388bfd`, `--accent-hot: #58a6ff`, `--success: #3fb950`,
   `--warn: #d29922`, `--danger: #f85149`, líneas 17-21 — SIN variantes bg/border/text y
   SIN estado `info`), identidad de agentes (líneas 26-31), fuentes (líneas 34-36), los
   ÚNICOS dos radios (`--radius: 6px`, `--radius-sm: 4px`, líneas 39-40) y tokens de card
   (`--card-radius: 10px`, `--card-shadow: 0 2px 12px rgba(0,0,0,0.35)` — la única sombra,
   líneas 43-45). **NO existe**: escala de spacing, escala tipográfica de tamaños/pesos,
   escala de elevación, tokens de motion (duración/easing), token de focus ring (el ring
   está hardcodeado en `theme.css:107` como `box-shadow: 0 0 0 3px rgba(56, 139, 253, 0.25)`),
   ni variantes de estado. El `color-scheme: dark` está hardcodeado en `theme.css:65`.
2. **1.231 hex hardcodeados en 70 archivos `.module.css`** (fuera de `theme.css`, que no
   es `.module.css`). Comando reproducible desde `Stacky Agents/frontend`:
   `grep -rEo '#[0-9a-fA-F]{3,8}\b' --include='*.module.css' src | wc -l` → 1231.
   Peores: `pages/PMCommandCenter.module.css` (140), `components/AgentHistoryPage.module.css`
   (84), `pages/UnblockerPage.module.css` (68), `components/ChatDrawer.module.css` (57),
   `pages/SystemLogsPage.module.css` (56), `components/DataReadinessModal.module.css` (53).
3. **772 `style={{` inline en 70 archivos `.tsx`.** Comando reproducible:
   `grep -rc 'style={{' --include='*.tsx' src` (suma = 772). Peores:
   `components/devops/BlockProperties.tsx` (58), `components/devops/PipelineBuilderSection.tsx`
   (53), `components/devops/PublicationsSection.tsx` (34),
   `components/devops/RemoteConsoleSection.tsx` (33), `components/MigratorWizard.tsx` (32),
   `components/ConfigTransferPanel.tsx` (32), `components/devops/ServersSection.tsx` (31).
4. **Hay DOS paletas conviviendo.** `theme.css` usa la paleta GitHub-dark
   (`#388bfd`, `#3fb950`, `#d29922`, `#f85149`), pero los 1.231 hex de los módulos usan
   mayoritariamente una paleta tipo Tailwind: los hex más frecuentes son `#fff` (71),
   `#e2e8f0` (54), `#64748b` (40), `#fca5a5` (39), `#94a3b8` (38), `#6366f1` (37),
   `#f87171` (32), `#4ade80` (24), `#fde68a` (22), `#fbbf24` (21), `#93c5fd` (19).
   Ejemplos: `components/AgentHistoryPage.module.css` usa fondos propios `#0f0f14`/`#1a1a24`
   con texto `#e2e8f0` y acento indigo `#6366f1`; `App.module.css` contiene `#a5b4fc` y
   `#6366f1`. Los tokens de ESTADO nuevos anclan la paleta dominante de los módulos
   (Tailwind) porque es la que la UI realmente renderiza hoy en chips/estados (ver §3.4-R3);
   la unificación de paletas NO es de este plan (§6).
5. **`frontend/src/components/ui/` NO existe** (verificado por glob vacío). La única
   "primitiva" reusable es `components/EmptyState.tsx` (props en `EmptyState.tsx:12-19`),
   que este plan NO toca (la consume el plan 140).
6. **`lucide-react` YA está instalado** (`frontend/package.json:15`,
   `"lucide-react": "^0.453.0"`) pero la navegación usa emojis. Este plan NO migra
   iconografía (es del 139); solo constata que NO hace falta dependencia nueva.
7. **No hay RTL/jsdom** (`frontend/package.json:24-31` no incluye `@testing-library/react`
   ni `jsdom` — gap estructural confirmado, memoria "Gotcha RTL/jsdom estructural"). El
   idioma de tests de la casa para UI es vitest con funciones puras + fs+regex, como
   `frontend/src/pages/__tests__/DevOpsPage.test.ts:40-95` (lee el archivo fuente con
   `fs.readFileSync` y aplica regex sobre el contenido).

**Por qué ahora:** los planes 139 (App Shell v2), 140 (estados universales) y 141 (tema
claro) necesitan un contrato de tokens y primitivas congelado ANTES de escribirse. Sin
esta fundación, cada plan de la serie re-inventaría botones/chips/spinners y sumaría más
deuda al montón de 1.231+772. El ratchet convierte la deuda en una curva monótona
descendente sin exigir una migración big-bang.

---

## 3. Principios y guardarraíles

### 3.1 Sin flag de harness (justificación por naturaleza del cambio)

Este plan NO introduce flag, siguiendo el precedente del plan 132 §3.1 y 135 §3.1:

- **F0 (ratchet):** archivos de test + baseline JSON. No tocan runtime de la app. Reversible con revert.
- **F1 (tokens):** SOLO agrega variables CSS nuevas a `:root` (ningún selector existente
  cambia de valor computado; el único edit a una regla existente es `color-scheme:
  var(--color-scheme)` con `--color-scheme: dark`, computacionalmente idéntico). Sin
  consumidores nuevos, el render es byte-idéntico.
- **F2 (primitivas):** archivos NUEVOS sin ningún consumidor obligatorio. Código muerto
  hasta que F3-F5 (y los planes 139-141) los consuman.
- **F3-F5 (ejemplares):** sustituciones valor-idéntico (KPI-5). Cero cambio de pixel.
- **F6 (apriete):** regenera un JSON.

Una flag acá agregaría trabajo al operador (decisión que no necesita tomar) y un camino
de código muerto (tema con flag OFF = tema sin flag). Regla de la casa: "cero trabajo
extra para el operador; si algo amerita flag, default seguro" — acá nada lo amerita.

### 3.2 Orden de la serie + pre-flight por fase + staging quirúrgico

- **Precondición de aterrizaje:** TODA la serie 138-141 aterriza DESPUÉS de la serie
  pendiente 132→134→135→136 (orden congelado por plan 134 v2 §3.3). El 138 no toca
  ninguno de los archivos de esa serie (ver lista prohibida en §3.4-R6), así que puede
  IMPLEMENTARSE en paralelo en worktree aislado, pero NO mergearse a main antes que ellos.
- **Pre-flight por archivo (regla del 135 v2 §3.2(d), adoptada calcada):** antes de
  editar CADA archivo, correr `git status -- "<ruta>"`. Si el archivo aparece modificado
  con WIP ajeno sin commitear → **STOP y avisar al operador**. No pisar WIP jamás.
- **Staging quirúrgico obligatorio:** `git add -- <paths>` explícitos con las rutas de la
  fase. **NUNCA `git add -A`** ni `git add .` (memoria de la casa: WIP ajeno conviviendo
  en el working tree es la norma, no la excepción).
- **Prohibido en todo el plan:** `git stash`, `git reset`, `git checkout --`, `git rebase`.

### 3.3 Convivencia con planes vecinos (contratos externos — NO duplicar)

| Plan vecino | Estado | Qué hace | Regla de convivencia del 138 |
|---|---|---|---|
| **119** shell DevOps v2 | Implementado (rama `plan-119-devops-ui-v2`; `DevOpsPage.module.css` aún NO está en main — verificado por glob) | Rediseño del dashboard DevOps con flag `STACKY_DEVOPS_UI_V2_ENABLED` | Su CSS consume `var(--bg-*)`, `var(--text-*)`, `var(--accent)`. El 138 es ADITIVO: prohibido renombrar/eliminar/cambiar valor de tokens existentes (§3.4-R1), por lo que el CSS del 119 rinde idéntico cuando aterrice. Al mergearse 119 a main DESPUÉS del baseline de F0, sus archivos nuevos entran al ratchet con la regeneración documentada en §5-R2. |
| **129** paleta Ctrl+K | Implementado | Búsqueda global | El 138 no toca `CommandPalette.tsx` (lista prohibida). Sin intersección. |
| **135 F5** Toast unificado | Pendiente | Extrae el Toast desde `RecoverExecutionButton.tsx` | **PROHIBIDO crear un Toast en `components/ui/`.** El Toast es contrato EXTERNO del plan 135 F5. Cuando exista, podrá migrarse a tokens en un plan futuro; no acá. |
| **140** estados universales | Pendiente (serie) | Consume `Skeleton`/`StatusChip` de este plan y el `EmptyState` EXISTENTE | `components/EmptyState.tsx` NO se toca ni se mueve a `ui/` (lista prohibida §3.4-R6). El barrel de `ui/` NO lo re-exporta: la decisión de moverlo/adaptarlo es del 140. |
| **141** tema claro/oscuro/sistema | Pendiente (serie) | Agrega `:root[data-theme="light"]` + selector en Settings (localStorage `stacky.ui.theme`, valores `dark`\|`light`\|`system`, default `dark`) | El 138 SOLO deja la estructura theme-ready (§F1 paso 3): tokens agrupados por capa, `--color-scheme` variable y comentario-contrato. **NO implementa el tema claro** ni el atributo `data-theme`. |
| **63/78/82/86** UI config arnés | Implementados | Panel de flags | Sin intersección: `HarnessFlagsPanel.tsx` está en la lista prohibida; sus `.module.css` conservan sus hex (el ratchet los congela, no los rompe). |

### 3.4 Reglas duras (el implementador NO puede violarlas)

- **R1 — Aditividad de tokens:** PROHIBIDO renombrar, eliminar o cambiar el valor de
  cualquier token existente de `theme.css:5-45`. Solo se AGREGAN tokens nuevos.
- **R2 — Byte-compatibilidad:** en F3-F5, un hex solo se sustituye por `var(--token)` si
  el valor del token es EXACTAMENTE ese color (mismo color computado; `#fff` ≡ `#ffffff`
  cuenta como idéntico). Si un hex del archivo NO tiene token con valor idéntico, SE DEJA
  el hex (el ratchet lo sigue contando; migración progresiva futura).
- **R3 — Anclaje de estados:** los tokens `--status-*` toman los valores de la paleta
  DOMINANTE de los `.module.css` (evidencia §2.4), no los de `--success/--warn/--danger`
  legacy. Ambas familias conviven; la unificación es trabajo futuro (§6). PROHIBIDO
  "corregir" un valor por gusto estético.
- **R4 — Primitivas puras:** todo archivo bajo `components/ui/` usa SOLO tokens de
  `theme.css` (cero hex — el ratchet lo fuerza a 0) y PROHIBIDO el literal `style={{` en
  sus `.tsx`. Permitido `style={fn(...)}` donde `fn` es una función pura EXPORTADA y
  testeada (patrón `skeletonStyle`/`spinnerStyle` de F2).
- **R5 — Sin dependencias:** `package.json` NO se modifica. Nada de RTL/jsdom/styled-*.
- **R6 — Lista prohibida (archivos que tocan los planes 132/134/135/136 pendientes o WIP
  vivo):** PROHIBIDO editar `App.tsx`, `TopBar.tsx`, `ActiveRunsPanel.tsx`,
  `CodexConsoleDock.tsx`, `SettingsPage.tsx`, `EpicFromBriefModal.tsx`, `TicketBoard.tsx`,
  `IntentPreflightModal.tsx`, `AgentHistoryPage.tsx`, `HarnessFlagsPanel.tsx`,
  `FlagGateBanner.tsx`, `PrReviewerSection.tsx`, `ReplayPlayer.tsx`, `CommandPalette.tsx`,
  `AgentLaunchModal.tsx`, `ChatDrawer.tsx`, `AgentConfigModal.tsx`, `EditProjectModal.tsx`,
  `CreateChildTaskButton.tsx`, `PipelineTriggerCard.tsx`, `RecoverExecutionButton.tsx`,
  `EmptyState.tsx`, `main.tsx`, `endpoints.ts`, `workbench.ts` y sus `.module.css`
  asociados. Los únicos archivos EXISTENTES que este plan edita son: `theme.css` (F1),
  `PipelineStatus.module.css` (F3), `SyncStatusBar.module.css` (F4),
  `RunButton.module.css` + `RunButton.tsx` (F5). Nada más.
- **R7 — Tests backend intactos:** este plan no toca backend; PROHIBIDO tocar
  `HARNESS_TEST_FILES` (sh/ps1) o cualquier archivo Python.

### 3.5 Paridad de los 3 runtimes (Codex CLI, Claude Code CLI, GitHub Copilot Pro)

Este plan es 100% presentación: los runtimes de agentes NO leen `theme.css` ni
`components/ui/`. Igual se declara por fase (mandato de la casa) con la línea:
*"Impacto por runtime: ninguno (presentación pura; los 3 runtimes no consumen estos
archivos). Fallback: no aplica. Paridad: preservada por construcción."*

---

## 4. Fases

Convenciones comunes a TODAS las fases:

- **cwd para comandos frontend:** `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend`
- **Comando de tests:** `npx vitest run <ruta-relativa-del-test>` · **Gate de tipos:** `npx tsc --noEmit`
- **Pre-flight:** `git status -- "<ruta>"` por CADA archivo antes de editarlo (§3.2).
- **Trabajo del operador: ninguno** (aplica a las 7 fases; no se repite abajo).
- **Impacto por runtime:** ninguno en las 7 fases (§3.5; no se repite abajo).

---

### F0 — Ratchet anti-regresión: test + baseline congelado

**Objetivo (1 frase):** congelar la deuda visual actual (hex por `.module.css`,
`style={{` por `.tsx`) en un baseline JSON y hacer fallar cualquier commit que la AUMENTE.
**Valor:** convierte "no empeorar la UI" de una intención en un gate mecánico que corre
en vitest; es el candado que protege todo el resto de la serie.

**Archivos (crear):**
- `frontend/src/__tests__/uiDebtRatchet.test.ts`
- `frontend/src/__tests__/uiDebtBaseline.json` (generado por el propio test en modo regen)

**Paso 1 — TDD: escribir el test.** Contenido EXACTO de
`frontend/src/__tests__/uiDebtRatchet.test.ts`:

```ts
/**
 * Plan 138 F0 — Ratchet de deuda visual.
 * Congela, POR ARCHIVO, la cantidad de colores hex en *.module.css y de
 * `style={{` literales en *.tsx bajo src/. La deuda solo puede BAJAR.
 *
 * Regenerar baseline (solo cuando la deuda BAJÓ):
 *   PowerShell:  $env:UI_DEBT_REGEN='1'; npx vitest run src/__tests__/uiDebtRatchet.test.ts; Remove-Item Env:\UI_DEBT_REGEN
 *   bash:        UI_DEBT_REGEN=1 npx vitest run src/__tests__/uiDebtRatchet.test.ts
 *
 * Si renombrás/movés un archivo con deuda: mover a mano su entrada del baseline
 * a la clave nueva (mismo contador) y correr el test normal.
 */
import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const FRONTEND_ROOT = process.cwd(); // correr SIEMPRE desde Stacky Agents/frontend
const SRC = path.join(FRONTEND_ROOT, "src");
const BASELINE_PATH = path.join(SRC, "__tests__", "uiDebtBaseline.json");

const HEX_RE = /#[0-9a-fA-F]{3,8}\b/g;
const INLINE_STYLE_RE = /style=\{\{/g;

interface Baseline {
  hexByFile: Record<string, number>;
  inlineStyleByFile: Record<string, number>;
}

export function countMatches(content: string, re: RegExp): number {
  const m = content.match(re);
  return m ? m.length : 0;
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
  const hexByFile: Record<string, number> = {};
  const inlineStyleByFile: Record<string, number> = {};
  for (const rel of files) {
    const content = fs.readFileSync(path.join(SRC, rel), "utf-8");
    if (rel.endsWith(".module.css")) {
      const n = countMatches(content, HEX_RE);
      if (n > 0) hexByFile[rel] = n;
    }
    if (rel.endsWith(".tsx")) {
      const n = countMatches(content, INLINE_STYLE_RE);
      if (n > 0) inlineStyleByFile[rel] = n;
    }
  }
  return { hexByFile: sortKeys(hexByFile), inlineStyleByFile: sortKeys(inlineStyleByFile) };
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
  const check = (kind: keyof Baseline) => {
    for (const [file, count] of Object.entries(current[kind])) {
      const allowedBase = baseline[kind][file] ?? 0;
      // Chrome/primitivas del sistema de diseño: SIEMPRE 0 (invariante mecánico).
      // Cubre ui/ (plan 138) y shell/ (plan 139).
      const forcedZero =
        file.startsWith("components/ui/") || file.startsWith("components/shell/");
      const allowed = forcedZero ? 0 : allowedBase;
      if (count > allowed) {
        errors.push(
          `${kind} REGRESION en ${file}: ${count} > ${allowed} permitido. ` +
            `La deuda visual solo puede bajar (plan 138). Usa tokens de theme.css ` +
            `o clases de *.module.css en vez de hex/style inline.`,
        );
      }
    }
  };
  check("hexByFile");
  check("inlineStyleByFile");
  return errors;
}

describe("uiDebtRatchet (plan 138 F0)", () => {
  it("src/ existe (correr desde Stacky Agents/frontend)", () => {
    expect(fs.existsSync(SRC)).toBe(true);
  });

  it("la deuda visual por archivo no aumenta respecto del baseline", () => {
    const current = computeCurrent();
    if (process.env.UI_DEBT_REGEN === "1") {
      const prev = readBaseline();
      if (prev) {
        const errs = assertNoIncrease(current, prev);
        expect(errs, "REGEN rechazado: hay archivos que AUMENTARON su deuda:\n" + errs.join("\n")).toEqual([]);
      }
      fs.writeFileSync(BASELINE_PATH, JSON.stringify(current, null, 2) + "\n", "utf-8");
      return;
    }
    const baseline = readBaseline();
    expect(baseline, `Falta ${BASELINE_PATH}. Generarlo con UI_DEBT_REGEN=1 (ver cabecera del test).`).not.toBeNull();
    const errs = assertNoIncrease(current, baseline as Baseline);
    expect(errs, errs.join("\n")).toEqual([]);
  });

  it("components/ui/ y components/shell/ nacen y se mantienen con deuda CERO", () => {
    const current = computeCurrent();
    const dirty = [
      ...Object.keys(current.hexByFile),
      ...Object.keys(current.inlineStyleByFile),
    ].filter((f) => f.startsWith("components/ui/") || f.startsWith("components/shell/"));
    expect(dirty, `Archivos de ui/ o shell/ con hex o style={{ literal: ${dirty.join(", ")}`).toEqual([]);
  });
});
```

**Paso 2 — confirmar rojo por la razón correcta:**
`npx vitest run src/__tests__/uiDebtRatchet.test.ts` debe FALLAR con el mensaje
`Falta ...uiDebtBaseline.json`.

**Paso 3 — generar el baseline (script exacto de regeneración):**

```powershell
# PowerShell 5.1, cwd = Stacky Agents\frontend
$env:UI_DEBT_REGEN='1'; npx vitest run src/__tests__/uiDebtRatchet.test.ts; Remove-Item Env:\UI_DEBT_REGEN
```

Esto escribe `frontend/src/__tests__/uiDebtBaseline.json` con el esquema:

```json
{
  "hexByFile": { "App.module.css": 2, "components/ChatDrawer.module.css": 57 },
  "inlineStyleByFile": { "pages/PMCommandCenter.tsx": 16 }
}
```

(claves = rutas relativas a `src/` con `/`, ordenadas alfabéticamente; solo archivos con
contador > 0; los valores reales los calcula el test — NO copiarlos de este doc).

**Paso 4 — confirmar verde:** `npx vitest run src/__tests__/uiDebtRatchet.test.ts` pasa.

**Casos borde cubiertos por diseño:** archivo nuevo con deuda → falla (permitido = 0);
archivo borrado → entrada stale inofensiva (se poda en el próximo regen); renombre de
archivo con deuda → falla con instrucción en la cabecera del test (mover entrada a mano);
regen tramposo con deuda aumentada → el propio modo regen lo rechaza; `theme.css` NO se
cuenta (no es `.module.css` — ahí los hex son legítimos: son los tokens).

**Criterio de aceptación (binario):** los 2 comandos siguientes pasan con exit 0:
`npx vitest run src/__tests__/uiDebtRatchet.test.ts` y `npx tsc --noEmit`.
**Flag:** sin flag — son archivos de test; no tocan runtime (§3.1).
**Staging:** `git add -- src/__tests__/uiDebtRatchet.test.ts src/__tests__/uiDebtBaseline.json`

---

### F1 — Tokens semánticos en `theme.css` (aditivo, byte-compatible, theme-ready)

**Objetivo (1 frase):** extender `:root` de `theme.css` con los 69 tokens congelados de
§10.1 sin alterar ningún valor existente.
**Valor:** da nombre semántico a los valores que la UI ya usa, habilita las primitivas de
F2 y deja la estructura lista para el tema claro del plan 141.

**Archivos (editar):** `frontend/src/theme.css`
**Archivos (crear):** `frontend/src/__tests__/themeTokens.test.ts`

**Paso 1 — TDD: escribir el test.** Contenido EXACTO de
`frontend/src/__tests__/themeTokens.test.ts` (la tabla `FROZEN_TOKENS` se copia VERBATIM
de §10.1 — misma fuente, cero divergencia):

```ts
/**
 * Plan 138 F1 — Contrato de tokens del sistema de diseño v2.
 * Congela nombre y valor EXACTO de cada token nuevo, y verifica que los
 * tokens legacy no cambiaron. Fuente de verdad: plan 138 §10.1.
 */
import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const THEME = fs.readFileSync(path.join(process.cwd(), "src", "theme.css"), "utf-8");
const FLAT = THEME.replace(/\s+/g, " ");

const FROZEN_TOKENS: Array<[string, string]> = [
  // §10.1.A Estados
  ["--status-success-text", "#4ade80"],
  ["--status-success-soft-text", "#86efac"],
  ["--status-success-solid", "#22c55e"],
  ["--status-success-bg", "rgba(34, 197, 94, 0.18)"],
  ["--status-success-border", "rgba(34, 197, 94, 0.3)"],
  ["--status-warning-text", "#fbbf24"],
  ["--status-warning-soft-text", "#fde68a"],
  ["--status-warning-muted-text", "#fdba74"],
  ["--status-warning-solid", "#f59e0b"],
  ["--status-warning-bg", "rgba(245, 158, 11, 0.18)"],
  ["--status-warning-border", "rgba(245, 158, 11, 0.28)"],
  ["--status-danger-text", "#f87171"],
  ["--status-danger-soft-text", "#fca5a5"],
  ["--status-danger-solid", "#ef4444"],
  ["--status-danger-bg", "rgba(239, 68, 68, 0.18)"],
  ["--status-danger-border", "rgba(239, 68, 68, 0.28)"],
  ["--status-info-text", "#93c5fd"],
  ["--status-info-solid", "#3b82f6"],
  ["--status-info-hot", "#60a5fa"],
  ["--status-info-bg", "rgba(59, 130, 246, 0.18)"],
  ["--status-info-border", "rgba(59, 130, 246, 0.4)"],
  ["--status-neutral-text", "var(--text-muted)"],
  ["--status-neutral-bg", "rgba(255, 255, 255, 0.06)"],
  ["--status-neutral-border", "rgba(255, 255, 255, 0.1)"],
  // §10.1.B Interacción
  ["--accent-active", "#1f6feb"],
  ["--warn-hover", "#e3b341"],
  ["--text-on-solid", "#ffffff"],
  ["--text-on-warn", "#1c1810"],
  ["--focus-ring", "0 0 0 3px rgba(56, 139, 253, 0.25)"],
  ["--spinner-track", "rgba(255, 255, 255, 0.15)"],
  // §10.1.C Spacing
  ["--space-1", "2px"],
  ["--space-2", "4px"],
  ["--space-3", "6px"],
  ["--space-4", "8px"],
  ["--space-5", "12px"],
  ["--space-6", "16px"],
  ["--space-7", "24px"],
  ["--space-8", "32px"],
  ["--space-9", "48px"],
  // §10.1.D Tipografía
  ["--text-2xs", "10px"],
  ["--text-xs", "11px"],
  ["--text-sm", "12px"],
  ["--text-md", "13px"],
  ["--text-lg", "15px"],
  ["--text-xl", "18px"],
  ["--text-2xl", "22px"],
  ["--weight-regular", "400"],
  ["--weight-medium", "500"],
  ["--weight-semibold", "600"],
  ["--weight-bold", "700"],
  ["--leading-tight", "1.2"],
  ["--leading-normal", "1.4"],
  ["--leading-relaxed", "1.6"],
  // §10.1.E Radios
  ["--radius-xs", "2px"],
  ["--radius-md", "6px"],
  ["--radius-lg", "10px"],
  ["--radius-full", "999px"],
  // §10.1.F Sombras
  ["--shadow-1", "0 1px 3px rgba(0, 0, 0, 0.3)"],
  ["--shadow-2", "0 2px 12px rgba(0, 0, 0, 0.35)"],
  ["--shadow-3", "0 8px 24px rgba(0, 0, 0, 0.45)"],
  ["--shadow-overlay", "0 16px 48px rgba(0, 0, 0, 0.55)"],
  // §10.1.G Motion
  ["--duration-fast", "0.12s"],
  ["--duration-base", "0.2s"],
  ["--duration-slow", "0.4s"],
  ["--ease-standard", "ease"],
  ["--ease-in-out", "ease-in-out"],
  ["--ease-out-expo", "cubic-bezier(0.16, 1, 0.3, 1)"],
  // §10.1.H Bordes / theme-ready
  ["--border-width", "1px"],
  ["--color-scheme", "dark"],
];

const LEGACY_TOKENS: Array<[string, string]> = [
  ["--bg-base", "#0d1117"],
  ["--bg-panel", "#161b22"],
  ["--bg-elev", "#21262d"],
  ["--border", "#30363d"],
  ["--text-primary", "#e6edf3"],
  ["--text-muted", "#8b949e"],
  ["--accent", "#388bfd"],
  ["--accent-hot", "#58a6ff"],
  ["--success", "#3fb950"],
  ["--warn", "#d29922"],
  ["--danger", "#f85149"],
  ["--radius", "6px"],
  ["--radius-sm", "4px"],
  ["--card-radius", "10px"],
  ["--card-shadow", "0 2px 12px rgba(0,0,0,0.35)"],
];

describe("themeTokens (plan 138 F1)", () => {
  it("tokens nuevos: 69 nombres con valor exacto", () => {
    expect(FROZEN_TOKENS.length).toBe(69);
    const missing = FROZEN_TOKENS.filter(([n, v]) => !FLAT.includes(`${n}: ${v};`));
    expect(missing, "Tokens faltantes o con valor distinto: " + missing.map(([n]) => n).join(", ")).toEqual([]);
  });

  it("tokens legacy intactos (R1 aditividad)", () => {
    const broken = LEGACY_TOKENS.filter(([n, v]) => !FLAT.includes(`${n}: ${v};`));
    expect(broken, "Tokens legacy alterados: " + broken.map(([n]) => n).join(", ")).toEqual([]);
  });

  it("theme-ready: color-scheme sale de la variable y aun NO hay data-theme (lo agrega el plan 141)", () => {
    expect(FLAT).toContain("color-scheme: var(--color-scheme)");
    expect(FLAT).toContain("THEME-READY");
    // El plan 141 elimina esta asercion cuando implemente el tema claro:
    expect(THEME.includes('[data-theme="light"]')).toBe(false);
  });
});
```

**Paso 2 — rojo por la razón correcta:**
`npx vitest run src/__tests__/themeTokens.test.ts` falla en "tokens nuevos".

**Paso 3 — editar `theme.css`.** DOS ediciones, nada más:

**(a)** Insertar el bloque siguiente COMPLETO y VERBATIM inmediatamente ANTES de la llave
de cierre `}` del `:root` (hoy `theme.css:46`), después de `--avatar-border: 8px;`:

```css
  /* ═══ Plan 138 — Sistema de diseño v2 (tokens semánticos) ═══════════
     THEME-READY: el plan 141 agregará `:root[data-theme="light"] { ... }`
     re-apuntando SOLO los tokens de color (superficies, texto, estados,
     sombras, --color-scheme). Spacing, tipografía, radios y motion son
     invariantes al tema. Contrato congelado: plan 138 §10.1 —
     PROHIBIDO renombrar o cambiar valores sin actualizar themeTokens.test.ts. */

  /* Estados semánticos (paleta dominante actual de los .module.css) */
  --status-success-text: #4ade80;
  --status-success-soft-text: #86efac;
  --status-success-solid: #22c55e;
  --status-success-bg: rgba(34, 197, 94, 0.18);
  --status-success-border: rgba(34, 197, 94, 0.3);
  --status-warning-text: #fbbf24;
  --status-warning-soft-text: #fde68a;
  --status-warning-muted-text: #fdba74;
  --status-warning-solid: #f59e0b;
  --status-warning-bg: rgba(245, 158, 11, 0.18);
  --status-warning-border: rgba(245, 158, 11, 0.28);
  --status-danger-text: #f87171;
  --status-danger-soft-text: #fca5a5;
  --status-danger-solid: #ef4444;
  --status-danger-bg: rgba(239, 68, 68, 0.18);
  --status-danger-border: rgba(239, 68, 68, 0.28);
  --status-info-text: #93c5fd;
  --status-info-solid: #3b82f6;
  --status-info-hot: #60a5fa;
  --status-info-bg: rgba(59, 130, 246, 0.18);
  --status-info-border: rgba(59, 130, 246, 0.4);
  --status-neutral-text: var(--text-muted);
  --status-neutral-bg: rgba(255, 255, 255, 0.06);
  --status-neutral-border: rgba(255, 255, 255, 0.1);

  /* Interacción / acento */
  --accent-active: #1f6feb;
  --warn-hover: #e3b341;
  --text-on-solid: #ffffff;
  --text-on-warn: #1c1810;
  --focus-ring: 0 0 0 3px rgba(56, 139, 253, 0.25);
  /* Pista del spinner (translúcida): el 141 la re-apunta en el bloque claro (C1). */
  --spinner-track: rgba(255, 255, 255, 0.15);

  /* Escala de spacing */
  --space-1: 2px;
  --space-2: 4px;
  --space-3: 6px;
  --space-4: 8px;
  --space-5: 12px;
  --space-6: 16px;
  --space-7: 24px;
  --space-8: 32px;
  --space-9: 48px;

  /* Escala tipográfica */
  --text-2xs: 10px;
  --text-xs: 11px;
  --text-sm: 12px;
  --text-md: 13px;
  --text-lg: 15px;
  --text-xl: 18px;
  --text-2xl: 22px;
  --weight-regular: 400;
  --weight-medium: 500;
  --weight-semibold: 600;
  --weight-bold: 700;
  --leading-tight: 1.2;
  --leading-normal: 1.4;
  --leading-relaxed: 1.6;

  /* Radios (complementan --radius/--radius-sm/--card-radius legacy) */
  --radius-xs: 2px;
  --radius-md: 6px;
  --radius-lg: 10px;
  --radius-full: 999px;

  /* Elevación / sombras (--shadow-2 = --card-shadow legacy, byte-identica) */
  --shadow-1: 0 1px 3px rgba(0, 0, 0, 0.3);
  --shadow-2: 0 2px 12px rgba(0, 0, 0, 0.35);
  --shadow-3: 0 8px 24px rgba(0, 0, 0, 0.45);
  --shadow-overlay: 0 16px 48px rgba(0, 0, 0, 0.55);

  /* Motion */
  --duration-fast: 0.12s;
  --duration-base: 0.2s;
  --duration-slow: 0.4s;
  --ease-standard: ease;
  --ease-in-out: ease-in-out;
  --ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);

  /* Bordes / theme-ready */
  --border-width: 1px;
  --color-scheme: dark;
```

**(b)** En la regla `html, body, #root` (hoy `theme.css:51-66`), reemplazar la línea
`color-scheme: dark;` por `color-scheme: var(--color-scheme);` SIN tocar el comentario B4
que la precede. (Computa idéntico: `--color-scheme: dark`.)

**Casos borde:** el token `--radius-md` duplica el valor de `--radius` y `--radius-lg` el
de `--card-radius` a propósito (los nombres nuevos completan la escala; los legacy quedan
por R1). `--status-neutral-text` referencia `var(--text-muted)` — válido en CSS custom
properties y el test lo verifica como string literal.

**Paso 4 — verde:** `npx vitest run src/__tests__/themeTokens.test.ts` y
`npx vitest run src/__tests__/uiDebtRatchet.test.ts` (theme.css no entra al ratchet) y
`npx tsc --noEmit`.

**Criterio de aceptación (binario):** los 3 comandos del paso 4 con exit 0.
**Flag:** sin flag — tokens sin consumidores; render byte-idéntico (§3.1).
**Staging:** `git add -- src/theme.css src/__tests__/themeTokens.test.ts`

---

### F2 — Primitivas UI en `frontend/src/components/ui/`

**Objetivo (1 frase):** crear las 8 primitivas congeladas (§10.2) + barrel, consumiendo
SOLO tokens de F1, con deuda cero y funciones puras testeables.
**Valor:** el vocabulario visual compartido que consumen los planes 139/140/141 y toda
migración futura; mata la reinvención de botones/chips/spinners.

**Archivos (crear, 17):**
- `frontend/src/components/ui/Spinner.tsx` + `Spinner.module.css`
- `frontend/src/components/ui/Skeleton.tsx` + `Skeleton.module.css`
- `frontend/src/components/ui/StatusChip.tsx` + `StatusChip.module.css`
- `frontend/src/components/ui/Button.tsx` + `Button.module.css`
- `frontend/src/components/ui/IconButton.tsx` + `IconButton.module.css`
- `frontend/src/components/ui/Card.tsx` + `Card.module.css`
- `frontend/src/components/ui/SectionHeader.tsx` + `SectionHeader.module.css`
- `frontend/src/components/ui/Tabs.tsx` + `Tabs.module.css`
- `frontend/src/components/ui/index.ts`
- `frontend/src/__tests__/uiPrimitives.test.ts`

**Patrón obligatorio (R4):** cada `.tsx` compone clases con una función pura exportada
`<nombre>PartKeys(...)` que devuelve claves semánticas (testeables sin CSS Modules), y el
componente las mapea con `styles[k]`. Estilos dinámicos van por `style={fn(props)}` con
`fn` pura exportada — NUNCA `style={{`.

**Paso 1 — TDD: escribir el test.** Contenido EXACTO de
`frontend/src/__tests__/uiPrimitives.test.ts`:

```ts
/**
 * Plan 138 F2 — Contrato de primitivas UI (sin RTL/jsdom: funciones puras + fs).
 * Fuente de verdad de firmas: plan 138 §10.2.
 */
import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const UI_DIR = path.join(process.cwd(), "src", "components", "ui");
const COMPONENTS = [
  "Button", "IconButton", "StatusChip", "Card",
  "SectionHeader", "Tabs", "Skeleton", "Spinner",
] as const;

describe("uiPrimitives (plan 138 F2)", () => {
  it("existen los 8 pares .tsx/.module.css y el barrel", () => {
    for (const c of COMPONENTS) {
      expect(fs.existsSync(path.join(UI_DIR, `${c}.tsx`)), `${c}.tsx`).toBe(true);
      expect(fs.existsSync(path.join(UI_DIR, `${c}.module.css`)), `${c}.module.css`).toBe(true);
    }
    expect(fs.existsSync(path.join(UI_DIR, "index.ts"))).toBe(true);
  });

  it("el barrel re-exporta los 8 componentes como funciones", async () => {
    const barrel = await import("../components/ui");
    for (const c of COMPONENTS) {
      expect(typeof (barrel as Record<string, unknown>)[c], c).toBe("function");
    }
  });

  it("los .module.css de ui/ usan tokens (var(--)) y cero hex", () => {
    for (const c of COMPONENTS) {
      const css = fs.readFileSync(path.join(UI_DIR, `${c}.module.css`), "utf-8");
      expect(/#[0-9a-fA-F]{3,8}\b/.test(css), `${c}.module.css tiene hex`).toBe(false);
      expect(css.includes("var(--"), `${c}.module.css no usa tokens`).toBe(true);
    }
  });

  it("los .tsx de ui/ no usan style={{ literal", () => {
    for (const c of COMPONENTS) {
      const tsx = fs.readFileSync(path.join(UI_DIR, `${c}.tsx`), "utf-8");
      expect(tsx.includes("style={{"), `${c}.tsx tiene style={{ literal`).toBe(false);
    }
  });

  it("buttonPartKeys: defaults y variantes", async () => {
    const { buttonPartKeys } = await import("../components/ui/Button");
    expect(buttonPartKeys("secondary", "md", false)).toEqual(["btn", "secondary", "md"]);
    expect(buttonPartKeys("primary", "sm", true)).toEqual(["btn", "primary", "sm", "loading"]);
    expect(buttonPartKeys("danger", "md", false)).toEqual(["btn", "danger", "md"]);
    expect(buttonPartKeys("ghost", "sm", false)).toEqual(["btn", "ghost", "sm"]);
  });

  it("iconButtonPartKeys: defaults y variantes", async () => {
    const { iconButtonPartKeys } = await import("../components/ui/IconButton");
    expect(iconButtonPartKeys("ghost", "md")).toEqual(["btn", "ghost", "md"]);
    expect(iconButtonPartKeys("danger", "sm")).toEqual(["btn", "danger", "sm"]);
  });

  it("chipPartKeys: los 5 tonos y 2 tamanos", async () => {
    const { chipPartKeys } = await import("../components/ui/StatusChip");
    for (const tone of ["success", "warning", "danger", "info", "neutral"] as const) {
      expect(chipPartKeys(tone, "sm")).toEqual(["chip", tone, "sm"]);
      expect(chipPartKeys(tone, "md")).toEqual(["chip", tone, "md"]);
    }
  });

  it("cardPartKeys: padding y elevacion", async () => {
    const { cardPartKeys } = await import("../components/ui/Card");
    expect(cardPartKeys("md", false)).toEqual(["card", "padMd"]);
    expect(cardPartKeys("none", true)).toEqual(["card", "padNone", "elevated"]);
    expect(cardPartKeys("sm", false)).toEqual(["card", "padSm"]);
  });

  it("tabPartKeys: activo vs inactivo", async () => {
    const { tabPartKeys } = await import("../components/ui/Tabs");
    expect(tabPartKeys(true, "md")).toEqual(["tab", "md", "active"]);
    expect(tabPartKeys(false, "sm")).toEqual(["tab", "sm"]);
  });

  it("skeletonStyle: defaults y numeros→px", async () => {
    const { skeletonStyle } = await import("../components/ui/Skeleton");
    expect(skeletonStyle(undefined, undefined, undefined)).toEqual({
      width: "100%", height: "14px", borderRadius: "var(--radius-sm)",
    });
    expect(skeletonStyle(120, 20, 8)).toEqual({
      width: "120px", height: "20px", borderRadius: "8px",
    });
    expect(skeletonStyle("50%", "2em", "var(--radius-full)")).toEqual({
      width: "50%", height: "2em", borderRadius: "var(--radius-full)",
    });
  });

  it("spinnerStyle: defaults y overrides", async () => {
    const { spinnerStyle } = await import("../components/ui/Spinner");
    expect(spinnerStyle(undefined, undefined, undefined, undefined)).toEqual({
      width: "14px", height: "14px", borderWidth: "2px",
      borderColor: "var(--spinner-track)", borderTopColor: "var(--accent)",
      animationDuration: "800ms",
    });
    expect(spinnerStyle(13, "var(--text-on-warn)", "rgba(28, 24, 16, 0.25)", 700)).toEqual({
      width: "13px", height: "13px", borderWidth: "2px",
      borderColor: "rgba(28, 24, 16, 0.25)", borderTopColor: "var(--text-on-warn)",
      animationDuration: "700ms",
    });
  });
});
```

**Paso 2 — rojo por la razón correcta:** el test falla en "existen los 8 pares".

**Paso 3 — crear las primitivas.** Código COMPLETO y VERBATIM (orden: Spinner y Skeleton
primero porque Button importa Spinner):

`frontend/src/components/ui/Spinner.module.css`:
```css
@keyframes uiSpin {
  to { transform: rotate(360deg); }
}

.spinner {
  display: inline-block;
  border-radius: var(--radius-full);
  border-style: solid;
  animation-name: uiSpin;
  animation-timing-function: linear;
  animation-iteration-count: infinite;
  flex-shrink: 0;
}
```

`frontend/src/components/ui/Spinner.tsx`:
```tsx
import { CSSProperties } from "react";
import styles from "./Spinner.module.css";

export interface SpinnerProps {
  /** Diámetro en px. Default 14. */
  size?: number;
  /** Color del arco. Default "var(--accent)". */
  color?: string;
  /** Color de la pista. Default "var(--spinner-track)" (themeable por el plan 141). */
  trackColor?: string;
  /** Duración de la vuelta en ms. Default 800. */
  durationMs?: number;
  /** aria-label. Default "Cargando". */
  label?: string;
}

export function spinnerStyle(
  size: number | undefined,
  color: string | undefined,
  trackColor: string | undefined,
  durationMs: number | undefined,
): CSSProperties {
  const s = size ?? 14;
  return {
    width: `${s}px`,
    height: `${s}px`,
    borderWidth: "2px",
    borderColor: trackColor ?? "var(--spinner-track)",
    borderTopColor: color ?? "var(--accent)",
    animationDuration: `${durationMs ?? 800}ms`,
  };
}

export default function Spinner({ size, color, trackColor, durationMs, label }: SpinnerProps) {
  return (
    <span
      className={styles.spinner}
      style={spinnerStyle(size, color, trackColor, durationMs)}
      role="status"
      aria-label={label ?? "Cargando"}
    />
  );
}
```

`frontend/src/components/ui/Skeleton.module.css`:
```css
@keyframes uiSkeletonPulse {
  0%, 100% { opacity: 1; }
  50%      { opacity: 0.55; }
}

.skeleton {
  display: block;
  background: var(--bg-elev);
  animation: uiSkeletonPulse 1.4s var(--ease-in-out) infinite;
}

.stack {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
```

`frontend/src/components/ui/Skeleton.tsx`:
```tsx
import { CSSProperties } from "react";
import styles from "./Skeleton.module.css";

export interface SkeletonProps {
  /** number → px; string se pasa tal cual. Default "100%". */
  width?: number | string;
  /** number → px; string se pasa tal cual. Default 14. */
  height?: number | string;
  /** number → px; string se pasa tal cual. Default "var(--radius-sm)". */
  radius?: number | string;
  /** Cantidad de barras apiladas. Default 1. */
  lines?: number;
  className?: string;
}

function toCssSize(v: number | string | undefined, fallback: string): string {
  if (v === undefined) return fallback;
  return typeof v === "number" ? `${v}px` : v;
}

export function skeletonStyle(
  width: number | string | undefined,
  height: number | string | undefined,
  radius: number | string | undefined,
): CSSProperties {
  return {
    width: toCssSize(width, "100%"),
    height: toCssSize(height, "14px"),
    borderRadius: toCssSize(radius, "var(--radius-sm)"),
  };
}

export default function Skeleton({ width, height, radius, lines, className }: SkeletonProps) {
  const n = Math.max(1, lines ?? 1);
  const bar = (key: number) => (
    <span
      key={key}
      className={className ? `${styles.skeleton} ${className}` : styles.skeleton}
      style={skeletonStyle(width, height, radius)}
      aria-hidden="true"
    />
  );
  if (n === 1) return bar(0);
  return <span className={styles.stack}>{Array.from({ length: n }, (_, i) => bar(i))}</span>;
}
```

`frontend/src/components/ui/StatusChip.module.css`:
```css
.chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  border-radius: var(--radius-full);
  border: var(--border-width) solid;
  font-weight: var(--weight-medium);
  white-space: nowrap;
}

.sm { padding: 2px 8px; font-size: var(--text-xs); }
.md { padding: 3px 10px; font-size: var(--text-sm); }

.success {
  background: var(--status-success-bg);
  border-color: var(--status-success-border);
  color: var(--status-success-text);
}
.warning {
  background: var(--status-warning-bg);
  border-color: var(--status-warning-border);
  color: var(--status-warning-text);
}
.danger {
  background: var(--status-danger-bg);
  border-color: var(--status-danger-border);
  color: var(--status-danger-text);
}
.info {
  background: var(--status-info-bg);
  border-color: var(--status-info-border);
  color: var(--status-info-text);
}
.neutral {
  background: var(--status-neutral-bg);
  border-color: var(--status-neutral-border);
  color: var(--status-neutral-text);
}
```

`frontend/src/components/ui/StatusChip.tsx`:
```tsx
import { ReactNode } from "react";
import styles from "./StatusChip.module.css";

export type StatusTone = "success" | "warning" | "danger" | "info" | "neutral";
export type ChipSize = "sm" | "md";

export interface StatusChipProps {
  tone: StatusTone;
  children: ReactNode;
  icon?: ReactNode;
  /** Default "sm". */
  size?: ChipSize;
  title?: string;
}

export function chipPartKeys(tone: StatusTone, size: ChipSize): string[] {
  return ["chip", tone, size];
}

export default function StatusChip({ tone, children, icon, size, title }: StatusChipProps) {
  const cls = chipPartKeys(tone, size ?? "sm").map((k) => styles[k]).filter(Boolean).join(" ");
  return (
    <span className={cls} title={title}>
      {icon}
      {children}
    </span>
  );
}
```

`frontend/src/components/ui/Button.module.css`:
```css
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  font-family: var(--font-sans);
  font-weight: var(--weight-semibold);
  border-radius: var(--radius-sm);
  border: var(--border-width) solid transparent;
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard),
    border-color var(--duration-fast) var(--ease-standard),
    color var(--duration-fast) var(--ease-standard);
}

.sm { padding: 3px 10px; font-size: var(--text-sm); }
.md { padding: 6px 14px; font-size: var(--text-md); }

.primary {
  background: var(--accent);
  color: var(--text-on-solid);
  border-color: rgba(240, 246, 252, 0.1);
}
.primary:hover:not(:disabled) { background: var(--accent-hot); }
.primary:active:not(:disabled) { background: var(--accent-active); }

.secondary {
  background: transparent;
  color: var(--text-primary);
  border-color: var(--border);
}
.secondary:hover:not(:disabled) {
  background: var(--bg-elev);
  border-color: var(--text-faint);
}

.ghost {
  background: transparent;
  color: var(--text-muted);
  border-color: transparent;
}
.ghost:hover:not(:disabled) {
  background: var(--bg-elev);
  color: var(--text-primary);
}

.danger {
  background: transparent;
  color: var(--status-danger-text);
  border-color: var(--status-danger-border);
}
.danger:hover:not(:disabled) { background: var(--status-danger-bg); }

.btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.btn:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.loading { cursor: progress; }
```

`frontend/src/components/ui/Button.tsx`:
```tsx
import { ButtonHTMLAttributes, ReactNode } from "react";
import styles from "./Button.module.css";
import Spinner from "./Spinner";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Default "secondary" (el look del <button> global de theme.css). */
  variant?: ButtonVariant;
  /** Default "md". */
  size?: ButtonSize;
  /** Muestra Spinner a la izquierda y deshabilita. Default false. */
  loading?: boolean;
  iconLeft?: ReactNode;
  iconRight?: ReactNode;
}

export function buttonPartKeys(
  variant: ButtonVariant,
  size: ButtonSize,
  loading: boolean,
): string[] {
  const keys = ["btn", variant, size];
  if (loading) keys.push("loading");
  return keys;
}

export default function Button({
  variant,
  size,
  loading,
  iconLeft,
  iconRight,
  className,
  disabled,
  children,
  type,
  ...rest
}: ButtonProps) {
  const keys = buttonPartKeys(variant ?? "secondary", size ?? "md", loading ?? false);
  const cls = keys.map((k) => styles[k]).filter(Boolean).join(" ");
  return (
    <button
      type={type ?? "button"}
      className={className ? `${cls} ${className}` : cls}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? <Spinner size={12} color="currentColor" trackColor="rgba(255, 255, 255, 0.25)" /> : iconLeft}
      {children}
      {iconRight}
    </button>
  );
}
```

`frontend/src/components/ui/IconButton.module.css`:
```css
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  border: var(--border-width) solid transparent;
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard),
    border-color var(--duration-fast) var(--ease-standard),
    color var(--duration-fast) var(--ease-standard);
}

.sm { padding: 3px; font-size: var(--text-sm); }
.md { padding: 5px; font-size: var(--text-md); }

.ghost {
  background: transparent;
  color: var(--text-muted);
  border-color: transparent;
}
.ghost:hover:not(:disabled) {
  background: var(--bg-elev);
  color: var(--text-primary);
}

.secondary {
  background: transparent;
  color: var(--text-primary);
  border-color: var(--border);
}
.secondary:hover:not(:disabled) {
  background: var(--bg-elev);
  border-color: var(--text-faint);
}

.danger {
  background: transparent;
  color: var(--status-danger-text);
  border-color: transparent;
}
.danger:hover:not(:disabled) { background: var(--status-danger-bg); }

.btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.btn:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}
```

`frontend/src/components/ui/IconButton.tsx`:
```tsx
import { ButtonHTMLAttributes, ReactNode } from "react";
import styles from "./IconButton.module.css";

export type IconButtonVariant = "ghost" | "secondary" | "danger";
export type IconButtonSize = "sm" | "md";

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Texto accesible OBLIGATORIO (aria-label y title). */
  label: string;
  icon: ReactNode;
  /** Default "ghost". */
  variant?: IconButtonVariant;
  /** Default "md". */
  size?: IconButtonSize;
}

export function iconButtonPartKeys(
  variant: IconButtonVariant,
  size: IconButtonSize,
): string[] {
  return ["btn", variant, size];
}

export default function IconButton({
  label,
  icon,
  variant,
  size,
  className,
  type,
  ...rest
}: IconButtonProps) {
  const keys = iconButtonPartKeys(variant ?? "ghost", size ?? "md");
  const cls = keys.map((k) => styles[k]).filter(Boolean).join(" ");
  return (
    <button
      type={type ?? "button"}
      className={className ? `${cls} ${className}` : cls}
      aria-label={label}
      title={label}
      {...rest}
    >
      {icon}
    </button>
  );
}
```

`frontend/src/components/ui/Card.module.css`:
```css
.card {
  background: var(--bg-panel);
  border: var(--border-width) solid var(--border);
  border-radius: var(--radius);
}

.elevated { box-shadow: var(--shadow-2); }

.padNone { padding: 0; }
.padSm   { padding: var(--space-4); }
.padMd   { padding: var(--space-6); }
```

`frontend/src/components/ui/Card.tsx`:
```tsx
import { ReactNode } from "react";
import styles from "./Card.module.css";

export type CardPadding = "none" | "sm" | "md";

export interface CardProps {
  children: ReactNode;
  /** Default "md". */
  padding?: CardPadding;
  /** box-shadow var(--shadow-2). Default false. */
  elevated?: boolean;
  className?: string;
}

const PAD_KEY: Record<CardPadding, string> = { none: "padNone", sm: "padSm", md: "padMd" };

export function cardPartKeys(padding: CardPadding, elevated: boolean): string[] {
  const keys = ["card", PAD_KEY[padding]];
  if (elevated) keys.push("elevated");
  return keys;
}

export default function Card({ children, padding, elevated, className }: CardProps) {
  const keys = cardPartKeys(padding ?? "md", elevated ?? false);
  const cls = keys.map((k) => styles[k]).filter(Boolean).join(" ");
  return <div className={className ? `${cls} ${className}` : cls}>{children}</div>;
}
```

`frontend/src/components/ui/SectionHeader.module.css`:
```css
.root {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-5);
}

.titles {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.title {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: var(--weight-semibold);
  color: var(--text-primary);
  line-height: var(--leading-tight);
}

.subtitle {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-muted);
  line-height: var(--leading-normal);
}

.actions {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-shrink: 0;
}
```

`frontend/src/components/ui/SectionHeader.tsx`:
```tsx
import { ReactNode } from "react";
import styles from "./SectionHeader.module.css";

export interface SectionHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}

export default function SectionHeader({ title, subtitle, actions }: SectionHeaderProps) {
  return (
    <div className={styles.root}>
      <div className={styles.titles}>
        <h3 className={styles.title}>{title}</h3>
        {subtitle ? <p className={styles.subtitle}>{subtitle}</p> : null}
      </div>
      {actions ? <div className={styles.actions}>{actions}</div> : null}
    </div>
  );
}
```

`frontend/src/components/ui/Tabs.module.css`:
```css
.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  border-bottom: var(--border-width) solid var(--border);
}

.tab {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  border-radius: 0;
  color: var(--text-muted);
  cursor: pointer;
  transition: color var(--duration-fast) var(--ease-standard),
    border-color var(--duration-fast) var(--ease-standard);
}

.sm { padding: var(--space-2) var(--space-4); font-size: var(--text-sm); }
.md { padding: var(--space-3) var(--space-5); font-size: var(--text-md); }

.tab:hover:not(.active) { color: var(--text-primary); }

.active {
  color: var(--text-primary);
  border-bottom-color: var(--accent);
}

.tab:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}
```

`frontend/src/components/ui/Tabs.tsx`:
```tsx
import { ReactNode } from "react";
import styles from "./Tabs.module.css";

export type TabsSize = "sm" | "md";

export interface TabItem {
  id: string;
  label: ReactNode;
  icon?: ReactNode;
  badge?: ReactNode;
}

export interface TabsProps {
  items: TabItem[];
  activeId: string;
  onChange: (id: string) => void;
  /** Default "md". */
  size?: TabsSize;
  "aria-label"?: string;
}

export function tabPartKeys(active: boolean, size: TabsSize): string[] {
  const keys = ["tab", size];
  if (active) keys.push("active");
  return keys;
}

export default function Tabs({ items, activeId, onChange, size, ...rest }: TabsProps) {
  return (
    <div className={styles.tabs} role="tablist" aria-label={rest["aria-label"]}>
      {items.map((item) => {
        const keys = tabPartKeys(item.id === activeId, size ?? "md");
        const cls = keys.map((k) => styles[k]).filter(Boolean).join(" ");
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={item.id === activeId}
            className={cls}
            onClick={() => onChange(item.id)}
          >
            {item.icon}
            {item.label}
            {item.badge}
          </button>
        );
      })}
    </div>
  );
}
```

`frontend/src/components/ui/index.ts`:
```ts
/**
 * Plan 138 — barrel de primitivas UI. Contrato congelado en plan 138 §10.2.
 * NOTA: EmptyState (components/EmptyState.tsx) NO se re-exporta a propósito:
 * su adopción/movida es decisión del plan 140. El Toast unificado es contrato
 * del plan 135 F5 — PROHIBIDO crearlo acá.
 */
export { default as Button, buttonPartKeys } from "./Button";
export type { ButtonProps, ButtonVariant, ButtonSize } from "./Button";
export { default as IconButton, iconButtonPartKeys } from "./IconButton";
export type { IconButtonProps, IconButtonVariant, IconButtonSize } from "./IconButton";
export { default as StatusChip, chipPartKeys } from "./StatusChip";
export type { StatusChipProps, StatusTone, ChipSize } from "./StatusChip";
export { default as Card, cardPartKeys } from "./Card";
export type { CardProps, CardPadding } from "./Card";
export { default as SectionHeader } from "./SectionHeader";
export type { SectionHeaderProps } from "./SectionHeader";
export { default as Tabs, tabPartKeys } from "./Tabs";
export type { TabsProps, TabItem, TabsSize } from "./Tabs";
export { default as Skeleton, skeletonStyle } from "./Skeleton";
export type { SkeletonProps } from "./Skeleton";
export { default as Spinner, spinnerStyle } from "./Spinner";
export type { SpinnerProps } from "./Spinner";
```

**Casos borde:** `Button` con `loading` fuerza `disabled` (evita doble-submit — alinea
con la filosofía del plan 136 sin depender de él); `IconButton.label` es prop OBLIGATORIA
(accesibilidad); `Skeleton.lines > 1` envuelve en `.stack`; `Tabs` renderiza
`role="tablist"/"tab"` con `aria-selected`; todos los `type` de botón default `"button"`
(no disparan submits de formularios).

**Paso 4 — verde:**
`npx vitest run src/__tests__/uiPrimitives.test.ts` ·
`npx vitest run src/__tests__/uiDebtRatchet.test.ts` (los archivos nuevos de `ui/` deben
dar deuda 0; si falla, hay un hex o `style={{` colado) · `npx tsc --noEmit`.

**Criterio de aceptación (binario):** los 3 comandos del paso 4 con exit 0.
**Flag:** sin flag — archivos nuevos sin consumidor obligatorio (§3.1).
**Staging:** `git add -- src/components/ui src/__tests__/uiPrimitives.test.ts`

---

### F3 — Migración ejemplar 1: `PipelineStatus.module.css` (solo CSS, valor-idéntico)

**Objetivo (1 frase):** llevar los 6 hex de `PipelineStatus.module.css` a 0 usando tokens
de estado con valor EXACTO.
**Valor:** demuestra el patrón de migración CSS puro más simple; los chips
done/pending/next de PipelineStatus son el caso de uso canónico de `--status-*`.

**Pre-flight:** `git status -- "frontend/src/components/PipelineStatus.module.css"` — si
trae WIP ajeno → STOP. (No está en la lista prohibida §3.4-R6 ni en el WIP conocido.)

**Archivos (editar):** `frontend/src/components/PipelineStatus.module.css` — NADA más
(el `.tsx` no se toca).

**Tabla de sustituciones (TODAS valor-idéntico; aplicar EXACTAMENTE estas y ninguna otra):**

| Ubicación (orientativa) | Antes | Después |
|---|---|---|
| `.progressFill` (línea 21) | `linear-gradient(90deg, #22c55e, #3b82f6)` | `linear-gradient(90deg, var(--status-success-solid), var(--status-info-solid))` |
| `.stage.done` (líneas 47-49) | `background: rgba(34, 197, 94, 0.18);` / `color: #4ade80;` / `border: 1px solid rgba(34, 197, 94, 0.3);` | `background: var(--status-success-bg);` / `color: var(--status-success-text);` / `border: var(--border-width) solid var(--status-success-border);` |
| `.stage.pending` (líneas 53-55) | `background: rgba(255, 255, 255, 0.06);` / `border: 1px solid rgba(255, 255, 255, 0.1);` | `background: var(--status-neutral-bg);` / `border: var(--border-width) solid var(--status-neutral-border);` (el `color: rgba(255,255,255,0.35)` QUEDA como está — no hay token idéntico) |
| `.stage.next` (líneas 59-61) | `background: rgba(59, 130, 246, 0.18);` / `color: #93c5fd;` / `border: 1px solid rgba(59, 130, 246, 0.4);` | `background: var(--status-info-bg);` / `color: var(--status-info-text);` / `border: var(--border-width) solid var(--status-info-border);` |
| `.checkmark` (línea 84) | `color: #4ade80;` | `color: var(--status-success-text);` |
| `.arrow` (línea 89) | `color: #93c5fd;` | `color: var(--status-info-text);` |

**Test (es el ratchet — no se escribe test nuevo):** tras editar, correr
`npx vitest run src/__tests__/uiDebtRatchet.test.ts` (sigue verde: la deuda bajó, nunca
subió) y verificar el contador con:
`grep -cE '#[0-9a-fA-F]{3,8}\b' src/components/PipelineStatus.module.css` → **0**.

**Criterio de aceptación (binario):** el grep de arriba devuelve 0; ratchet verde;
`npx tsc --noEmit` exit 0.
**Flag:** sin flag — sustitución valor-idéntico, cero cambio de pixel (§3.1, R2).
**Staging:** `git add -- src/components/PipelineStatus.module.css`

---

### F4 — Migración ejemplar 2: `SyncStatusBar.module.css` (solo CSS, valor-idéntico)

**Objetivo (1 frase):** llevar los 6 hex de `SyncStatusBar.module.css` a 0.
**Valor:** demuestra tokens de estado "solid" (dots de semáforo) y de texto suave.

**Pre-flight:** `git status -- "frontend/src/components/SyncStatusBar.module.css"` — si
trae WIP ajeno → STOP.

**Archivos (editar):** `frontend/src/components/SyncStatusBar.module.css` — NADA más.

**Tabla de sustituciones (TODAS valor-idéntico):**

| Ubicación (orientativa) | Antes | Después |
|---|---|---|
| `.dot.green` (línea 44) | `background: #22c55e;` | `background: var(--status-success-solid);` |
| `.dot.yellow` (línea 45) | `background: #f59e0b;` | `background: var(--status-warning-solid);` |
| `.dot.red` (línea 46) | `background: #ef4444;` | `background: var(--status-danger-solid);` |
| `.spinner` (línea 52) | `border-top-color: #60a5fa;` | `border-top-color: var(--status-info-hot);` |
| `.labelStale` (línea 71) | `color: #fdba74;` | `color: var(--status-warning-muted-text);` |
| `.labelError` (línea 75) | `color: #fca5a5;` | `color: var(--status-danger-soft-text);` |

Los `rgba(...)` del archivo QUEDAN como están (sin token idéntico; el ratchet no cuenta
rgba). El spinner casero de este archivo NO se reemplaza por la primitiva (el `.tsx` no
se toca en esta fase; adopción de primitivas se demuestra en F5).

**Criterio de aceptación (binario):**
`grep -cE '#[0-9a-fA-F]{3,8}\b' src/components/SyncStatusBar.module.css` → **0**;
`npx vitest run src/__tests__/uiDebtRatchet.test.ts` verde; `npx tsc --noEmit` exit 0.
**Flag:** sin flag — sustitución valor-idéntico (§3.1, R2).
**Staging:** `git add -- src/components/SyncStatusBar.module.css`

---

### F5 — Migración ejemplar 3: `RunButton` (CSS a tokens + adopción de la primitiva `Spinner`)

**Objetivo (1 frase):** llevar los 5 hex de `RunButton.module.css` a 0 y reemplazar su
spinner casero por la primitiva `Spinner` con parámetros byte-compatibles.
**Valor:** demuestra la SEGUNDA mitad del patrón: un componente existente adoptando una
primitiva de `ui/` sin cambiar un pixel.

**Pre-flight:** `git status -- "frontend/src/components/RunButton.module.css"` y
`git status -- "frontend/src/components/RunButton.tsx"` — si alguno trae WIP ajeno → STOP.

**Archivos (editar):** `frontend/src/components/RunButton.module.css` y
`frontend/src/components/RunButton.tsx`.

**Paso 1 — `RunButton.module.css`, sustituciones valor-idéntico:**

| Ubicación (orientativa) | Antes | Después |
|---|---|---|
| `.btn` (línea 15) | `color: #fff;` | `color: var(--text-on-solid);` |
| `.btn:active:not(:disabled)` (línea 32) | `background: #1f6feb;` | `background: var(--accent-active);` |
| `.running` (línea 48) | `color: #1c1810;` | `color: var(--text-on-warn);` |
| `.running:hover:not(:disabled)` (línea 55) | `background: #e3b341;` | `background: var(--warn-hover);` |

**Paso 2 — `RunButton.module.css`, borrar el spinner casero:** eliminar COMPLETOS el
bloque `.spinner { ... }` (líneas 58-67, incluye `border-top-color: #1c1810` — el 5º hex)
y el bloque `@keyframes spin { ... }` (líneas 1-3; solo lo usaba `.spinner`). El bloque
`@keyframes pulse-bg` QUEDA (lo usa `.running`).

**Paso 3 — `RunButton.tsx`:** aplicar exactamente estos dos cambios:

1. Agregar import (línea 2): `import Spinner from "./ui/Spinner";`
2. Reemplazar la línea 19 `<span className={styles.spinner} aria-hidden="true" />` por:
   `<Spinner size={13} color="var(--text-on-warn)" trackColor="rgba(28, 24, 16, 0.25)" durationMs={700} label="Procesando" />`

Byte-compatibilidad del reemplazo: el spinner casero era 13px, borde 2px,
pista `rgba(28, 24, 16, 0.25)`, arco `#1c1810` (= `--text-on-warn`), vuelta 0.7s —
la primitiva reproduce los 5 valores EXACTOS vía props.

**Criterio de aceptación (binario):**
`grep -cE '#[0-9a-fA-F]{3,8}\b' src/components/RunButton.module.css` → **0**;
`grep -c 'styles.spinner' src/components/RunButton.tsx` → **0**;
`npx vitest run src/__tests__/uiDebtRatchet.test.ts` verde; `npx tsc --noEmit` exit 0.
**Flag:** sin flag — sustitución valor-idéntico + primitiva equivalente (§3.1, R2).
**Staging:** `git add -- src/components/RunButton.module.css src/components/RunButton.tsx`

---

### F6 — Apriete del ratchet + verificación integral

**Objetivo (1 frase):** regenerar el baseline con la deuda ya reducida (F3-F5) y correr
la verificación completa del plan.
**Valor:** deja el candado apretado: a partir de acá, ni siquiera se puede VOLVER a los
niveles de deuda pre-138.

**Paso 1 — regenerar baseline (mismo script de F0):**

```powershell
# cwd = Stacky Agents\frontend
$env:UI_DEBT_REGEN='1'; npx vitest run src/__tests__/uiDebtRatchet.test.ts; Remove-Item Env:\UI_DEBT_REGEN
```

El modo regen valida internamente que NINGÚN archivo aumentó (si aumentó, falla — eso
significa que alguna fase anterior se hizo mal).

**Paso 2 — verificación integral (comandos exactos, todos deben dar exit 0):**

```powershell
# cwd = Stacky Agents\frontend
npx vitest run src/__tests__/uiDebtRatchet.test.ts src/__tests__/themeTokens.test.ts src/__tests__/uiPrimitives.test.ts
npx tsc --noEmit
npx vitest run
```

**Paso 3 — verificación del diff (sanidad final):** `git status` y revisar que SOLO
aparecen los archivos listados en este plan (tests nuevos, baseline, theme.css, ui/*,
los 3 ejemplares). Si aparece cualquier otro archivo modificado → investigar antes de
commitear; staging SIEMPRE con pathspec explícito (§3.2).

**Criterio de aceptación (binario):** los 3 comandos del paso 2 con exit 0, y en
`uiDebtBaseline.json` las entradas `components/PipelineStatus.module.css`,
`components/SyncStatusBar.module.css` y `components/RunButton.module.css` NO existen
(deuda 0 ⇒ no se listan).
**Flag:** sin flag — regeneración de JSON de test (§3.1).
**Staging:** `git add -- src/__tests__/uiDebtBaseline.json`

---

## 5. Riesgos y mitigaciones

- **R-1 · Colisión con la serie 132→134→135→136 y con WIP vivo.** El working tree HOY
  tiene WIP ajeno (p. ej. `TicketBoard.tsx`, `endpoints.ts`, `DocGraphView.*`). Mitigación:
  lista prohibida §3.4-R6 (este plan solo edita 5 archivos existentes, ninguno en WIP),
  pre-flight `git status -- "<ruta>"` por archivo, aterrizaje de la serie 138-141 DESPUÉS
  de 132-136, staging quirúrgico.
- **R-2 · El plan 119 aterriza a main DESPUÉS del baseline de F0.** Sus archivos nuevos
  (p. ej. `DevOpsPage.module.css`) pueden traer hex y romperían el ratchet en verde…
  no: los archivos NUEVOS con deuda fallan (permitido=0). Procedimiento documentado:
  quien mergee 119 corre el regen (`UI_DEBT_REGEN=1`) — el modo regen ACEPTA archivos
  nuevos (solo rechaza AUMENTOS de archivos ya listados) y los congela como nueva deuda
  conocida. Trade-off aceptado y explícito: el ratchet protege lo existente y captura lo
  nuevo en el siguiente apriete.
- **R-3 · Doble paleta (GitHub-dark vs Tailwind).** Anclar `--status-*` a la paleta
  Tailwind dominante podría leerse como "bendecir" la divergencia. Mitigación: R3 lo
  declara explícito y acota; la unificación real es un plan futuro post-141 con el
  ratchet ya instalado; los tokens hacen que esa futura unificación sea UN cambio en
  `theme.css` en vez de 1.231 ediciones.
- **R-4 · Renombre/movida de un archivo con deuda rompe el ratchet.** Mitigación: mensaje
  de error del test + cabecera con la instrucción exacta (mover la entrada del baseline a
  mano, mismo contador).
- **R-5 · Vitest y CSS Modules (los `styles.x` son undefined en tests).** Mitigación de
  diseño: el patrón `*PartKeys`/`*Style` testea las funciones puras SIN depender de los
  class names generados; los fs-tests validan el CSS como texto. Cero RTL/jsdom (R5).
- **R-6 · Un modelo menor "mejora" un valor (p. ej. redondea `0.28` a `0.3`).**
  Mitigación: `themeTokens.test.ts` congela los 69 valores byte a byte; cualquier desvío
  es rojo inmediato.
- **R-7 · `Button`/`Tabs` de F2 no se parecen a algún botón/tab existente puntual.**
  No es riesgo de este plan: NINGÚN componente existente se migra a `Button`/`Tabs` acá
  (solo `Spinner` en F5, byte-compatible). La adopción visible es de los planes 139/140,
  detrás de su propia flag (`STACKY_UI_SHELL_V2_ENABLED` en el 139).
- **R-8 · `readdirSync recursive` requiere Node ≥ 18.17.** El repo ya corre vitest 4
  (`package.json:30`), que exige Node ≥ 18; si el entorno tuviera un Node más viejo, el
  test falla con error claro de firma — actualizar Node, no reescribir el walker.

## 6. Fuera de scope (explícito)

- **La migración masiva de los 70 `.module.css` (1.231 hex) y 70 `.tsx` (772 inline)**:
  es PROGRESIVA vía ratchet — cada plan futuro que toque un archivo baja su contador;
  este plan solo migra los 3 ejemplares.
- **Unificación de las dos paletas** (GitHub-dark vs Tailwind/indigo de PMCommandCenter,
  AgentHistoryPage, etc.): post-141.
- **Tema claro, `data-theme`, selector en Settings, accesibilidad**: plan 141 (este plan
  solo deja la estructura theme-ready).
- **Shell, sidebar agrupada, TopBar, iconografía lucide**: plan 139 (flag
  `STACKY_UI_SHELL_V2_ENABLED` default OFF, patrón del plan 119).
- **Skeletons/vacíos/jerarquía aplicados a páginas reales**: plan 140.
- **Toast unificado**: plan 135 F5 (contrato externo).
- **`EmptyState.tsx`**: no se toca ni se re-exporta (lo consume el 140).
- **Backend, flags de harness, `package.json`, `HARNESS_TEST_FILES`**: intocados.

## 7. Glosario (para el modelo menor)

- **Token:** variable CSS (`--nombre: valor`) definida en `:root` de `theme.css`; única
  fuente de verdad de colores/espaciados/tipografía del sistema de diseño.
- **Primitiva UI:** componente React chico y genérico en `frontend/src/components/ui/`
  (Button, Spinner, …) que consume SOLO tokens; los componentes de negocio lo componen.
- **CSS Module:** archivo `*.module.css` cuyas clases se importan como objeto
  (`styles.x`) — el estándar de estilos de la casa.
- **Ratchet:** mecanismo trinquete — un test que permite que un contador BAJE pero nunca
  SUBA respecto de un baseline congelado.
- **Baseline:** el JSON `uiDebtBaseline.json` con el contador de deuda por archivo.
- **Byte-compatible:** el valor computado por el navegador es EXACTAMENTE el mismo antes
  y después del cambio (cero diferencia de pixel).
- **Barrel:** `index.ts` que re-exporta los módulos de una carpeta para importar desde
  `components/ui`.
- **Test fs+regex:** test vitest que lee archivos fuente con `fs` y los valida con
  regex/includes — el idioma de la casa para UI porque NO hay RTL/jsdom
  (`package.json:24-31`).
- **Paridad de runtimes:** Codex CLI, Claude Code CLI y GitHub Copilot Pro deben recibir
  el mismo trato en cada feature; acá no aplica funcionalmente (frontend puro) pero se
  declara por fase.
- **WIP ajeno:** cambios sin commitear de OTRA sesión/plan presentes en el working tree;
  jamás se pisan ni se stashean.

## 8. Orden de implementación (estricto)

1. **F0** — ratchet + baseline (candado primero).
2. **F1** — tokens en `theme.css` (fundación de valores).
3. **F2** — primitivas `ui/` (consumen F1; el ratchet de F0 las vigila desde que nacen).
4. **F3** — ejemplar PipelineStatus (consume F1).
5. **F4** — ejemplar SyncStatusBar (consume F1).
6. **F5** — ejemplar RunButton (consume F1 y F2).
7. **F6** — apriete del baseline + verificación integral.

Sin saltos ni reordenamientos: F2 depende de F1 (tokens), F5 depende de F2 (Spinner),
F6 depende de F3-F5 (deuda reducida).

## 9. Definición de Hecho (DoD) global

Todas las casillas, verificadas con comandos (cwd `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend`):

- [ ] `npx vitest run src/__tests__/uiDebtRatchet.test.ts` verde (KPI-3).
- [ ] `npx vitest run src/__tests__/themeTokens.test.ts` verde (KPI-1).
- [ ] `npx vitest run src/__tests__/uiPrimitives.test.ts` verde (KPI-2).
- [ ] `npx tsc --noEmit` exit 0 (KPI-4).
- [ ] `npx vitest run` (suite completa) verde (KPI-4).
- [ ] `grep -cE '#[0-9a-fA-F]{3,8}\b'` devuelve 0 para los 3 `.module.css` ejemplares (KPI-5).
- [ ] `git status` no muestra NINGÚN archivo modificado fuera de los listados en este plan.
- [ ] `package.json` sin cambios (`git status -- package.json` limpio).
- [ ] Los tokens legacy de `theme.css:5-45` conservan su valor (lo prueba themeTokens).
- [ ] Cero flags nuevas, cero cambios backend, cero trabajo del operador.

---

## § 10. Contrato congelado para la serie 139-141

Esta sección es COPY-PASTEABLE y es la única fuente de verdad de nombres. Los planes
139/140/141 consumen estos nombres tal cual; cualquier cambio exige actualizar este doc,
`themeTokens.test.ts` y `uiPrimitives.test.ts` a la vez.

### 10.1 Tokens (nombre exacto → valor exacto)

**A. Estados** (paleta dominante actual; ver §3.4-R3)

| Token | Valor |
|---|---|
| `--status-success-text` | `#4ade80` |
| `--status-success-soft-text` | `#86efac` |
| `--status-success-solid` | `#22c55e` |
| `--status-success-bg` | `rgba(34, 197, 94, 0.18)` |
| `--status-success-border` | `rgba(34, 197, 94, 0.3)` |
| `--status-warning-text` | `#fbbf24` |
| `--status-warning-soft-text` | `#fde68a` |
| `--status-warning-muted-text` | `#fdba74` |
| `--status-warning-solid` | `#f59e0b` |
| `--status-warning-bg` | `rgba(245, 158, 11, 0.18)` |
| `--status-warning-border` | `rgba(245, 158, 11, 0.28)` |
| `--status-danger-text` | `#f87171` |
| `--status-danger-soft-text` | `#fca5a5` |
| `--status-danger-solid` | `#ef4444` |
| `--status-danger-bg` | `rgba(239, 68, 68, 0.18)` |
| `--status-danger-border` | `rgba(239, 68, 68, 0.28)` |
| `--status-info-text` | `#93c5fd` |
| `--status-info-solid` | `#3b82f6` |
| `--status-info-hot` | `#60a5fa` |
| `--status-info-bg` | `rgba(59, 130, 246, 0.18)` |
| `--status-info-border` | `rgba(59, 130, 246, 0.4)` |
| `--status-neutral-text` | `var(--text-muted)` |
| `--status-neutral-bg` | `rgba(255, 255, 255, 0.06)` |
| `--status-neutral-border` | `rgba(255, 255, 255, 0.1)` |

**B. Interacción / acento**

| Token | Valor |
|---|---|
| `--accent-active` | `#1f6feb` |
| `--warn-hover` | `#e3b341` |
| `--text-on-solid` | `#ffffff` |
| `--text-on-warn` | `#1c1810` |
| `--focus-ring` | `0 0 0 3px rgba(56, 139, 253, 0.25)` |
| `--spinner-track` | `rgba(255, 255, 255, 0.15)` |

**C. Spacing**

| Token | Valor |
|---|---|
| `--space-1` … `--space-9` | `2px`, `4px`, `6px`, `8px`, `12px`, `16px`, `24px`, `32px`, `48px` |

**D. Tipografía**

| Token | Valor |
|---|---|
| `--text-2xs` / `--text-xs` / `--text-sm` / `--text-md` / `--text-lg` / `--text-xl` / `--text-2xl` | `10px` / `11px` / `12px` / `13px` / `15px` / `18px` / `22px` |
| `--weight-regular` / `--weight-medium` / `--weight-semibold` / `--weight-bold` | `400` / `500` / `600` / `700` |
| `--leading-tight` / `--leading-normal` / `--leading-relaxed` | `1.2` / `1.4` / `1.6` |

**E. Radios** (los legacy `--radius: 6px`, `--radius-sm: 4px`, `--card-radius: 10px` siguen vigentes)

| Token | Valor |
|---|---|
| `--radius-xs` / `--radius-md` / `--radius-lg` / `--radius-full` | `2px` / `6px` / `10px` / `999px` |

**F. Sombras**

| Token | Valor |
|---|---|
| `--shadow-1` | `0 1px 3px rgba(0, 0, 0, 0.3)` |
| `--shadow-2` | `0 2px 12px rgba(0, 0, 0, 0.35)` |
| `--shadow-3` | `0 8px 24px rgba(0, 0, 0, 0.45)` |
| `--shadow-overlay` | `0 16px 48px rgba(0, 0, 0, 0.55)` |

**G. Motion**

| Token | Valor |
|---|---|
| `--duration-fast` / `--duration-base` / `--duration-slow` | `0.12s` / `0.2s` / `0.4s` |
| `--ease-standard` / `--ease-in-out` / `--ease-out-expo` | `ease` / `ease-in-out` / `cubic-bezier(0.16, 1, 0.3, 1)` |

**H. Bordes / theme-ready**

| Token | Valor |
|---|---|
| `--border-width` | `1px` |
| `--color-scheme` | `dark` |

**Contrato theme-ready para el plan 141:** el 141 agrega `:root[data-theme="light"]`
re-apuntando SOLO tokens de color (superficies/texto legacy, estados A, interacción B,
sombras F y `--color-scheme`); C/D/E/G/`--border-width` son invariantes al tema. El
selector va en Settings con localStorage `stacky.ui.theme` (`dark`|`light`|`system`,
default `dark`). El 141 debe además retirar la aserción `data-theme` de
`themeTokens.test.ts` (F1 paso 1, tercer `it`).

### 10.2 Primitivas (ruta exacta + firma de props TypeScript completa)

Todas en `frontend/src/components/ui/`, con default export + función pura exportada, y
re-exportadas por `frontend/src/components/ui/index.ts`.

| Primitiva | Ruta | Firma de props |
|---|---|---|
| `Button` | `components/ui/Button.tsx` | `interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> { variant?: "primary" \| "secondary" \| "ghost" \| "danger"; size?: "sm" \| "md"; loading?: boolean; iconLeft?: ReactNode; iconRight?: ReactNode; }` — defaults: `variant="secondary"`, `size="md"`, `loading=false`, `type="button"`. Pura: `buttonPartKeys(variant, size, loading): string[]` |
| `IconButton` | `components/ui/IconButton.tsx` | `interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> { label: string; icon: ReactNode; variant?: "ghost" \| "secondary" \| "danger"; size?: "sm" \| "md"; }` — `label` OBLIGATORIO (aria-label+title); defaults `variant="ghost"`, `size="md"`. Pura: `iconButtonPartKeys(variant, size)` |
| `StatusChip` | `components/ui/StatusChip.tsx` | `interface StatusChipProps { tone: "success" \| "warning" \| "danger" \| "info" \| "neutral"; children: ReactNode; icon?: ReactNode; size?: "sm" \| "md"; title?: string; }` — default `size="sm"`. Pura: `chipPartKeys(tone, size)` |
| `Card` | `components/ui/Card.tsx` | `interface CardProps { children: ReactNode; padding?: "none" \| "sm" \| "md"; elevated?: boolean; className?: string; }` — defaults `padding="md"`, `elevated=false`. Pura: `cardPartKeys(padding, elevated)` |
| `SectionHeader` | `components/ui/SectionHeader.tsx` | `interface SectionHeaderProps { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; }` |
| `Tabs` | `components/ui/Tabs.tsx` | `interface TabItem { id: string; label: ReactNode; icon?: ReactNode; badge?: ReactNode; }` · `interface TabsProps { items: TabItem[]; activeId: string; onChange: (id: string) => void; size?: "sm" \| "md"; "aria-label"?: string; }` — default `size="md"`. Pura: `tabPartKeys(active, size)` |
| `Skeleton` | `components/ui/Skeleton.tsx` | `interface SkeletonProps { width?: number \| string; height?: number \| string; radius?: number \| string; lines?: number; className?: string; }` — defaults `width="100%"`, `height=14`, `radius="var(--radius-sm)"`, `lines=1`. Pura: `skeletonStyle(width, height, radius): CSSProperties` |
| `Spinner` | `components/ui/Spinner.tsx` | `interface SpinnerProps { size?: number; color?: string; trackColor?: string; durationMs?: number; label?: string; }` — defaults `size=14`, `color="var(--accent)"`, `trackColor="var(--spinner-track)"`, `durationMs=800`, `label="Cargando"`. Pura: `spinnerStyle(size, color, trackColor, durationMs): CSSProperties` |

**Contratos EXTERNOS que la serie consume pero este plan NO crea:**
- `EmptyState` — YA existe en `components/EmptyState.tsx` (props `EmptyState.tsx:12-19`);
  lo adopta/decide el plan 140.
- `Toast` unificado — lo extrae el plan 135 F5 desde `RecoverExecutionButton.tsx`;
  PROHIBIDO duplicarlo en `ui/`.

### 10.3 Ratchet (contrato de mecanismo)

- Test: `frontend/src/__tests__/uiDebtRatchet.test.ts` · Baseline:
  `frontend/src/__tests__/uiDebtBaseline.json` (claves relativas a `src/`, separador `/`).
- Regex congeladas: hex `/#[0-9a-fA-F]{3,8}\b/g` sobre `*.module.css`; inline
  `/style=\{\{/g` sobre `*.tsx`. `theme.css` fuera del conteo (no es module.css).
- Regla: contador por archivo ≤ baseline (ausente = 0); `components/ui/**` y
  `components/shell/**` (plan 139) SIEMPRE 0 (forzado, no incidental).
- Regeneración: `UI_DEBT_REGEN=1 npx vitest run src/__tests__/uiDebtRatchet.test.ts`
  (rechaza aumentos; poda entradas de archivos borrados).
