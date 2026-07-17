# Plan 162 — Sistema de formularios: primitivas de campos, validación inline y estados de envío

**Estado: IMPLEMENTADO — F0..F5 — 2026-07-17 (v1 -> v2 -> implementado)**

> Nota de implementación: F0-F4 verdes con output real. F5 (gate final) 6/8 comandos
> verdes; `uiDebtRatchet`/`motionDebtRatchet` fallan por drift AJENO preexistente
> (`components/devops/ServersSection.tsx`, `pages/PlansBoardPage.tsx/.module.css`,
> `pages/DevOpsPage.module.css` — ninguno tocado por este plan, confirmado limpio
> contra HEAD). `tsc --noEmit` en 0. Detalle completo en la memoria `plan-162-status`.

## Changelog v1 -> v2 (crítica adversarial)

- **C1 (IMPORTANTE, resuelto):** F4 §3 decía "migrar cualquier otro control crudo restante" — lista ABIERTA que violaba el propio G10. Verificado por grep 2026-07-17: `SettingsPage.tsx` tiene EXACTAMENTE 5 controles crudos (:79, :266, :274, :279, :289), todos ya enumerados; la lista queda CERRADA.
- **C2 (IMPORTANTE, resuelto):** F3 dejaba al implementador decidir si crear `validate` en `EditProjectModal`. Verificado: el submit (`:282-297`) valida SOLO `workspace_root` (`:284-285`) ⇒ `validate` SE CREA con exactamente esa key; único Field con `error`.
- **C3 (IMPORTANTE, resuelto):** pasar `required` a Field agrega un ` *` visible ⇒ rompería G1 (byte-idéntico). PROHIBIDO `required` en las migraciones F2-F4 (regla (g) nueva de F2 §6); la prop queda para superficies nuevas futuras.
- **C4 (MENOR, resuelto):** el mensaje real de `NewProjectModal.tsx:203` tiene un typo preexistente ("Selección un proyecto de Mantis"); v1 lo "traducía 1:1" sin notarlo. v2 CONGELA el texto corregido "Seleccioná un proyecto de Mantis" como ÚNICO mensaje que cambia (fix intencional declarado).
- **C5 (MENOR, resuelto):** el contrato documentado de `.u-pending` (`theme.css:376-377`) pide combinar con `aria-busy="true"`; los 3 botones de submit (F2/F3/F4) lo agregan (`aria-busy={<pending> || undefined}`).
- **C6 (MENOR, resuelto):** K4 solo daba el comando `grep` (Git Bash); se agrega el equivalente PowerShell.
- **C7 (MENOR, resuelto):** el criterio de F0 "~70 entradas" no era binario; ahora es piso binario "≥ 60".
- **C8 (MENOR, resuelto):** riesgo nuevo R9 — el merge 3-way silencioso puede duplicar los exports agregados al final del barrel si otra rama también apendea (gotcha real de la casa); mitigación tsc+grep post-merge.
- **[ADICIÓN ARQUITECTO]:** foco automático al PRIMER campo con error al fallar el submit — helper puro `firstErrorFieldId` en `Field.tsx` (con test), ids DOM estables `np-*`/`ep-*` y orden visual congelado. Accesibilidad de teclado real, cero trabajo del operador, idéntico en los 3 runtimes.

> Nota de numeración: este plan iba a ser el 160, pero `160_PLAN_RESOLUTOR_INCIDENCIAS_REPARACION_HTML_Y_PEGADO_IMAGENES.md` ya existe (loop paralelo) y el 161 está reservado para el plan hermano de esta misma corrida. Toda referencia interna usa **plan 162**.

## 1. Objetivo

Dotar a Stacky de un **sistema de formularios de primera clase**: 5 primitivas nuevas en `frontend/src/components/ui/` (`Field`, `Input`, `Select`, `Textarea`, `Checkbox`) que extienden el sistema de diseño del plan 138, un **patrón de validación inline accesible** (`aria-invalid` + `aria-describedby`, error junto al campo, nunca `alert()`/toast para errores de campo), y **estados de envío con feedback inmediato** adoptando por primera vez la infraestructura del plan 143 (`useOptimisticPending` + `.u-pending`, hoy con **cero consumidores**). Se congela la deuda de controles crudos con un ratchet espejo de los existentes (`formDebtRatchet.test.ts`: la deuda solo baja) y se migran 3 superficies ejemplares de forma **byte-idéntica en apariencia**. Todo lo no migrado queda exactamente como hoy.

### KPIs binarios

| # | KPI | Comando de verificación | Pasa si |
|---|-----|------------------------|---------|
| K1 | Las 5 primitivas existen, con `.module.css` par, y el barrel las exporta | `cd "Stacky Agents/frontend"` + `npx vitest run src/__tests__/formPrimitives.test.ts` | exit 0 |
| K2 | Ratchet de formularios activo y deuda congelada por archivo | `npx vitest run src/__tests__/formDebtRatchet.test.ts` | exit 0 |
| K3 | Los 3 archivos migrados tienen **0** controles crudos | abrir `src/__tests__/formDebtBaseline.json` | no existen las claves `components/NewProjectModal.tsx`, `components/EditProjectModal.tsx`, `pages/SettingsPage.tsx` |
| K4 | `useOptimisticPending` pasa de 0 a ≥3 consumidores reales | Git Bash: `grep -rl "useOptimisticPending" "Stacky Agents/frontend/src" --include=*.tsx` · PowerShell (C6): `(Get-ChildItem "Stacky Agents/frontend/src" -Recurse -Filter *.tsx | Select-String -List -Pattern "useOptimisticPending").Count` | ≥ 3 archivos `.tsx` |
| K5 | Cero regresión de tipos ni de ratchets previos | `npx tsc --noEmit` + `npx vitest run src/__tests__/uiDebtRatchet.test.ts` + `npx vitest run src/__tests__/motionDebtRatchet.test.ts` | exit 0 los tres |
| K6 | Look en reposo byte-idéntico: ningún `.module.css` de features tocado | `git diff --name-only` del trabajo del plan | ningún `*.module.css` fuera de `components/ui/` |

---

## 2. Por qué ahora / gap que cierra

Evidencia re-verificada por grep el 2026-07-17 (los `:NN` son orientativos; las anclas normativas son el TEXTO citado — regla de la casa):

1. **Cero primitivas de formulario.** `frontend/src/components/ui/` tiene exactamente 8 primitivas (Button, Card, IconButton, SectionHeader, Skeleton, Spinner, StatusChip, Tabs) + `index.ts`; el barrel (`components/ui/index.ts:7-22`) no exporta nada de formularios. No existe Input, Select, Textarea, Checkbox, Field ni Label.
2. **Deuda masiva de controles crudos.** Grep sobre `frontend/src`: `<select` → **67 ocurrencias en 42 archivos** (2 son falsos positivos en CSS: un comentario en `theme.css:252` y `TicketBoard.module.css`; en `.tsx/.jsx` reales: 65 en 40 archivos). `<input` → **207 ocurrencias en 64 archivos**. `<textarea` → **39 ocurrencias en 30 archivos**. Cada feature estiliza ad-hoc vía su `*.module.css` (ej. `NewProjectModal.tsx:240-246` con `className={styles.input}`).
3. **Accesibilidad de formularios inexistente.** Los `<label>` no llevan `htmlFor` ni los controles `id` (patrón repetido en cada par label+control de ese archivo: `NewProjectModal.tsx:239-246`, `:248-255` y los pares siguientes del mismo form). No hay ni una sola ocurrencia de `aria-invalid` en `frontend/src` fuera de este plan.
4. **La validación es un banner global, no inline.** `NewProjectModal.tsx:190-210` (`handleSubmit`) valida campo por campo pero reporta con **un único** `setError(...)` + banner al pie (`{error && <div className={styles.error}>{error}</div>}`, `NewProjectModal.tsx:604`): el operador no ve QUÉ campo falta hasta corregir de a uno.
5. **La infra del plan 143 sigue huérfana.** `hooks/useOptimisticPending.ts:38-45` (`useOptimisticPending`, retorna `{ pending, run, pendingClass }`) y `.u-pending` (`theme.css:378`, atenúa + `pointer-events: none`, contrato verificado por `motionA11yGuard.test.ts:45-50`) tienen **cero consumidores**: grep de `useOptimisticPending` solo pega en el hook y su test. La crítica C4 del propio plan 143 documenta "primer adoptante como plan futuro". Este plan ES ese adoptante.
6. **El sustrato para byte-idéntico ya existe.** `theme.css:279-297` estiliza globalmente `input, textarea, select` (borde, radius, padding, focus con `var(--focus-ring)`); `theme.css:334-338` (plan 141 F5) da `:focus-visible` universal. Una primitiva que renderiza el mismo elemento sin estilos base propios hereda EXACTAMENTE el look de hoy.

Sin este plan, cada modal nuevo (hay 15 `*Modal.tsx` con formularios) sigue clonando el patrón crudo, la deuda crece sin freno y el plan 143 sigue siendo infraestructura muerta.

---

## 3. Principios y guardarraíles

- **G1 — Byte-idéntico en reposo.** El look por defecto de las primitivas es el de `theme.css:279-297` (no redefinen base). Las migraciones conservan los `className` de la feature (la primitiva los mergea). Ningún `*.module.css` de features se modifica. Los únicos cambios visibles son: (a) mensajes de error inline cuando hay error (feature nueva), (b) atenuado `.u-pending` durante un submit en vuelo (feature nueva).
- **G2 — Sin flag.** Presentación pura aditiva, mismo precedente que 138 §3.1, 140, 141 y 143: no hay comportamiento nuevo que el operador deba activar ni bypass de revisión humana, nada destructivo, sin prerequisitos, sin reducción de seguridad. Justificación repetida por fase.
- **G3 — Paridad de 3 runtimes.** 100% frontend/presentación: idéntico bajo Codex CLI, Claude Code CLI y GitHub Copilot Pro. Fallback: N/A en todas las fases.
- **G4 — Dueños ajenos intocables.** `prefers-reduced-motion` y `:focus-visible`/`--focus-ring` son del plan 141 (consumir, jamás redefinir). Motion tokens y `.u-*` son del plan 143. Toast unificado es del plan 135 (el comentario del barrel `components/ui/index.ts:3-5` ya lo prohíbe ahí). Modal/diálogo/focus-trap/confirmaciones son del plan 157 de la rama `plans-ux-logs-final` (§6).
- **G5 — Ratchets existentes rigen.** `components/ui/` tiene deuda forzada CERO en `uiDebtRatchet.test.ts:78-82` (nada de hex ni `style={{`) y en `motionDebtRatchet.test.ts:78-80` (nada de tiempos literales ni `cubic-bezier(`). Los CSS nuevos usan SOLO `var(--...)` de `theme.css`. **No se crean tokens nuevos**: alcanzan `--danger` (`theme.css:21` dark / `:182` light), `--status-danger-text` (`:67`/`:207`), `--text-primary`, `--text-muted`, `--focus-ring`.
- **G6 — Anti-colisión con el propio gate** (gotcha recurrente de la casa, 6+ ocurrencias): el ratchet nuevo escanea SOLO archivos `.tsx`/`.jsx` bajo `src/` fuera de `components/ui/`. El test es `.ts` (queda fuera por extensión; PROHIBIDO renombrarlo `.tsx`). En comentarios/prosa de los archivos migrados queda PROHIBIDO escribir las secuencias literales `<input`, `<select`, `<textarea` (escribir "input crudo" o "select nativo" en su lugar).
- **G7 — Human-in-the-loop / mono-operador.** Nada de RBAC ni auth. Nada de auto-submit ni autonomía nueva: solo feedback visual de acciones que el operador ya dispara.
- **G8 — Contrato C5 del plan 143.** Toda promesa pasada a `run(...)` DEBE settlear (documentado en `useOptimisticPending.ts:9-14`). Las 3 adopciones envuelven llamadas de `api/endpoints` que resuelven o rechazan siempre; además se conserva `disabled` en los botones como cinturón.
- **G9 — Pre-flight por fase.** Antes de editar: `git status --porcelain -- "<ruta>"` de CADA archivo a tocar. Si hay WIP ajeno sin commitear ⇒ **STOP**, avisar al orquestador, no editar. El implementador NO commitea (commitea el orquestador).
- **G10 — Prohibido lo vago.** Este documento no usa muletillas vagas ni listas abiertas en instrucciones ejecutables; toda lista de archivos/props/keys es exhaustiva y cerrada.

---

## 4. Fases

### F0 — Ratchet `formDebtRatchet.test.ts` + baseline congelado

**Objetivo:** congelar HOY, por archivo, la cantidad de controles de formulario crudos fuera de `components/ui/`, con regla deuda-solo-baja; los archivos nuevos nacen con deuda 0. Valor: frena el crecimiento del problema antes de construir la solución.

**Archivos (exactos):**
- CREAR `Stacky Agents/frontend/src/__tests__/formDebtRatchet.test.ts`
- GENERAR `Stacky Agents/frontend/src/__tests__/formDebtBaseline.json` (vía REGEN, no a mano)

**Tests primero (TDD):** el propio archivo ES el test. Al correrlo sin baseline debe FALLAR con el mensaje `Falta .../formDebtBaseline.json`; tras el REGEN debe pasar. Esa es la secuencia roja→verde de la fase.

**Contenido EXACTO de `formDebtRatchet.test.ts`** (espejo de `uiDebtRatchet.test.ts` y `motionDebtRatchet.test.ts`; copiar helpers idénticos):

```ts
/**
 * Plan 162 F0 — Ratchet de deuda de FORMULARIOS.
 * Congela, POR ARCHIVO, la cantidad de controles de formulario crudos
 * (tags input/select/textarea escritos a mano) en *.tsx y *.jsx bajo src/,
 * EXCLUYENDO components/ui/ (único lugar donde las primitivas los renderizan).
 * La deuda solo puede BAJAR. Archivos fuera del baseline: permitido 0.
 *
 * Este archivo es .ts a propósito: queda fuera del scan por extensión.
 * PROHIBIDO renombrarlo .tsx (se contaría a sí mismo por sus regex).
 *
 * Regenerar baseline (solo cuando la deuda BAJÓ):
 *   PowerShell:  $env:FORM_DEBT_REGEN='1'; npx vitest run src/__tests__/formDebtRatchet.test.ts; Remove-Item Env:\FORM_DEBT_REGEN
 *   bash:        FORM_DEBT_REGEN=1 npx vitest run src/__tests__/formDebtRatchet.test.ts
 */
import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const FRONTEND_ROOT = process.cwd(); // correr SIEMPRE desde Stacky Agents/frontend
const SRC = path.join(FRONTEND_ROOT, "src");
const BASELINE_PATH = path.join(SRC, "__tests__", "formDebtBaseline.json");

const RAW_CONTROL_RES: RegExp[] = [/<input\b/g, /<select\b/g, /<textarea\b/g];

interface Baseline {
  formDebtByFile: Record<string, number>;
}

export function countMatches(content: string, re: RegExp): number {
  const m = content.match(re);
  return m ? m.length : 0;
}

export function formDebt(content: string): number {
  return RAW_CONTROL_RES.reduce((acc, re) => acc + countMatches(content, re), 0);
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
  const formDebtByFile: Record<string, number> = {};
  for (const rel of files) {
    if (!rel.endsWith(".tsx") && !rel.endsWith(".jsx")) continue;
    if (rel.startsWith("components/ui/")) continue; // único hogar legítimo de controles crudos
    const content = fs.readFileSync(path.join(SRC, rel), "utf-8");
    const n = formDebt(content);
    if (n > 0) formDebtByFile[rel] = n;
  }
  return { formDebtByFile: sortKeys(formDebtByFile) };
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
  for (const [file, count] of Object.entries(current.formDebtByFile)) {
    const allowed = baseline.formDebtByFile[file] ?? 0;
    if (count > allowed) {
      errors.push(
        `form REGRESION en ${file}: ${count} > ${allowed} permitido. ` +
          `La deuda de formularios solo puede bajar (plan 162). Usá las primitivas ` +
          `Field/Input/Select/Textarea/Checkbox de components/ui en vez de tags crudos.`,
      );
    }
  }
  return errors;
}

describe("formDebtRatchet (plan 162 F0)", () => {
  it("src/ existe (correr desde Stacky Agents/frontend)", () => {
    expect(fs.existsSync(SRC)).toBe(true);
  });

  it("la deuda de formularios por archivo no aumenta respecto del baseline", () => {
    const current = computeCurrent();
    if (process.env.FORM_DEBT_REGEN === "1") {
      const prev = readBaseline();
      if (prev) {
        const errs = assertNoIncrease(current, prev);
        expect(errs, "REGEN rechazado: archivos que AUMENTARON su deuda:\n" + errs.join("\n")).toEqual([]);
      }
      fs.writeFileSync(BASELINE_PATH, JSON.stringify(current, null, 2) + "\n", "utf-8");
      return;
    }
    const baseline = readBaseline();
    expect(baseline, `Falta ${BASELINE_PATH}. Generarlo con FORM_DEBT_REGEN=1 (ver cabecera del test).`).not.toBeNull();
    const errs = assertNoIncrease(current, baseline as Baseline);
    expect(errs, errs.join("\n")).toEqual([]);
  });

  it("el baseline nunca contiene entradas de components/ui/ (sanidad del scope)", () => {
    const baseline = readBaseline();
    if (!baseline) return; // lo cubre el test anterior
    const bad = Object.keys(baseline.formDebtByFile).filter((f) => f.startsWith("components/ui/"));
    expect(bad, `components/ui/ está excluido del ratchet: ${bad.join(", ")}`).toEqual([]);
  });
});
```

**Casos borde codificados:** archivos `.jsx` incluidos (existe `components/TicketGraphView.jsx` con un select crudo); archivos `.ts` y `.css` excluidos por extensión (los falsos positivos de `theme.css:252` y `TicketBoard.module.css` quedan fuera por diseño); archivo nuevo sin entrada en baseline ⇒ permitido 0 (mecanismo `?? 0`, idéntico a `uiDebtRatchet.test.ts:77`).

**Comandos exactos:**
```powershell
cd "Stacky Agents/frontend"
npx vitest run src/__tests__/formDebtRatchet.test.ts          # DEBE fallar: falta baseline
$env:FORM_DEBT_REGEN='1'; npx vitest run src/__tests__/formDebtRatchet.test.ts; Remove-Item Env:\FORM_DEBT_REGEN
npx vitest run src/__tests__/formDebtRatchet.test.ts          # DEBE pasar
npx tsc --noEmit
```

**Criterio de aceptación (binario):** los 3 comandos de vitest se comportan exactamente como se indica (rojo, regen, verde) y `tsc` exit 0. `formDebtBaseline.json` existe y contiene ≥ 60 entradas con conteos > 0 (piso binario, C7; los números exactos los fija el REGEN; NO editarlo a mano).

**Flag:** sin flag — es un test, no toca runtime (precedente: 138 F0, 143 F2). **Runtimes:** N/A (tooling de test, idéntico en los 3; fallback N/A). **Trabajo del operador: ninguno.**

---

### F1 — Primitivas `Field`, `Input`, `Select`, `Textarea`, `Checkbox` + barrel + contrato

**Objetivo:** crear las 5 primitivas con el patrón EXACTO de la casa (visto en `Button.tsx`: componente función con `export default`, SIN `forwardRef` — precedente confirmado también por la crítica C3 del plan 151 sobre Card —, props que extienden los atributos HTML nativos, helper puro `*PartKeys` exportado para test, `.module.css` par solo-tokens). Valor: vocabulario único de formularios para toda la app.

**Archivos (exactos, todos CREAR salvo el barrel que se EDITA):**
- `Stacky Agents/frontend/src/components/ui/Field.tsx` + `Field.module.css`
- `Stacky Agents/frontend/src/components/ui/Input.tsx` + `Input.module.css`
- `Stacky Agents/frontend/src/components/ui/Select.tsx` + `Select.module.css`
- `Stacky Agents/frontend/src/components/ui/Textarea.tsx` + `Textarea.module.css`
- `Stacky Agents/frontend/src/components/ui/Checkbox.tsx` + `Checkbox.module.css`
- EDITAR `Stacky Agents/frontend/src/components/ui/index.ts` (solo AGREGAR líneas al final; no tocar las existentes: el contrato 138 §10.2 es congelado pero aditivo)
- CREAR `Stacky Agents/frontend/src/__tests__/formPrimitives.test.ts`

**Tests primero (TDD):** escribir `formPrimitives.test.ts` ANTES que las primitivas; correrlo (falla por archivos inexistentes); implementar; correrlo verde.

**Contenido EXACTO de `formPrimitives.test.ts`** (espejo de `uiPrimitives.test.ts:15-44`, sin RTL/jsdom — gap estructural conocido: `package.json:24-31` no trae `@testing-library/react` ni `jsdom`, así que son funciones puras + fs):

```ts
/**
 * Plan 162 F1 — Contrato de primitivas de FORMULARIO (sin RTL/jsdom: funciones puras + fs).
 */
import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const UI_DIR = path.join(process.cwd(), "src", "components", "ui");
const FORM_COMPONENTS = ["Field", "Input", "Select", "Textarea", "Checkbox"] as const;

describe("formPrimitives (plan 162 F1)", () => {
  it("existen los 5 pares .tsx/.module.css", () => {
    for (const c of FORM_COMPONENTS) {
      expect(fs.existsSync(path.join(UI_DIR, `${c}.tsx`)), `${c}.tsx`).toBe(true);
      expect(fs.existsSync(path.join(UI_DIR, `${c}.module.css`)), `${c}.module.css`).toBe(true);
    }
  });

  it("el barrel re-exporta los 5 componentes como funciones", async () => {
    const barrel = await import("../components/ui");
    for (const c of FORM_COMPONENTS) {
      expect(typeof (barrel as Record<string, unknown>)[c], c).toBe("function");
    }
  });

  it("los .module.css usan tokens (var(--)) y cero hex", () => {
    for (const c of FORM_COMPONENTS) {
      const css = fs.readFileSync(path.join(UI_DIR, `${c}.module.css`), "utf-8");
      expect(/#[0-9a-fA-F]{3,8}\b/.test(css), `${c}.module.css tiene hex`).toBe(false);
      expect(css.includes("var(--"), `${c}.module.css no usa tokens`).toBe(true);
    }
  });

  it("los .tsx no usan style={{ literal", () => {
    for (const c of FORM_COMPONENTS) {
      const tsx = fs.readFileSync(path.join(UI_DIR, `${c}.tsx`), "utf-8");
      expect(tsx.includes("style={{"), `${c}.tsx tiene style={{ literal`).toBe(false);
    }
  });

  it("fieldControlProps: las 4 combinaciones error/help", async () => {
    const { fieldControlProps } = await import("../components/ui/Field");
    expect(fieldControlProps("f1", false, false)).toEqual({ id: "f1" });
    expect(fieldControlProps("f1", true, false)).toEqual({
      id: "f1", "aria-invalid": true, "aria-describedby": "f1-error",
    });
    expect(fieldControlProps("f1", false, true)).toEqual({
      id: "f1", "aria-describedby": "f1-help",
    });
    expect(fieldControlProps("f1", true, true)).toEqual({
      id: "f1", "aria-invalid": true, "aria-describedby": "f1-help f1-error",
    });
  });

  it("firstErrorFieldId: primer error según orden DOM (ADICIÓN ARQUITECTO)", async () => {
    const { firstErrorFieldId } = await import("../components/ui/Field");
    expect(firstErrorFieldId("np", ["a", "b"], {})).toBeNull();
    expect(firstErrorFieldId("np", ["a", "b"], { b: "x" })).toBe("np-b");
    expect(firstErrorFieldId("np", ["a", "b"], { a: "x", b: "y" })).toBe("np-a");
  });

  it("partKeys de controles: base e invalid", async () => {
    const { inputPartKeys } = await import("../components/ui/Input");
    const { selectPartKeys } = await import("../components/ui/Select");
    const { textareaPartKeys } = await import("../components/ui/Textarea");
    const { checkboxPartKeys } = await import("../components/ui/Checkbox");
    expect(inputPartKeys(false)).toEqual(["input"]);
    expect(inputPartKeys(true)).toEqual(["input", "invalid"]);
    expect(selectPartKeys(false)).toEqual(["select"]);
    expect(selectPartKeys(true)).toEqual(["select", "invalid"]);
    expect(textareaPartKeys(false)).toEqual(["textarea"]);
    expect(textareaPartKeys(true)).toEqual(["textarea", "invalid"]);
    expect(checkboxPartKeys()).toEqual(["row"]);
  });
});
```

**API EXACTA de cada primitiva:**

`Input.tsx` (plantilla; `Select`/`Textarea` son idénticos mutatis mutandis — reemplazar Input→Select/Textarea, input→select/textarea, `InputHTMLAttributes<HTMLInputElement>`→`SelectHTMLAttributes<HTMLSelectElement>`/`TextareaHTMLAttributes<HTMLTextAreaElement>`; Select y Textarea renderizan `{children}` dentro del tag):

```tsx
import { InputHTMLAttributes } from "react";
import styles from "./Input.module.css";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  /** Pinta el estado de error (borde --danger). El texto del error lo pone Field. */
  invalid?: boolean;
}

export function inputPartKeys(invalid: boolean): string[] {
  return invalid ? ["input", "invalid"] : ["input"];
}

export default function Input({ invalid, className, ...rest }: InputProps) {
  const cls = inputPartKeys(invalid ?? false).map((k) => styles[k]).filter(Boolean).join(" ");
  return <input className={className ? `${cls} ${className}` : cls} {...rest} />;
}
```

REGLA DURA: a diferencia de `Button.tsx:45` (que fuerza `type="button"`), **Input NO fuerza `type`**: hoy hay inputs crudos sin `type` (ej. `SettingsPage.tsx:266`) y forzarlo cambiaría el DOM. Todo atributo nativo (`value`, `onChange`, `placeholder`, `disabled`, `type`, `checked`) pasa por `...rest`.

`Input.module.css` (mismo esquema para Select/Textarea, cambiando el nombre de la clase base):

```css
/* Plan 162 — base intencionalmente vacía: el look de reposo es el global de
   theme.css (bloque "Controls"). Solo estados. Cero hex, cero tiempos (ratchets 138/143). */
.input {
}

.invalid {
  border-color: var(--danger);
}
```

`Field.tsx`:

```tsx
import { ReactNode, useId } from "react";
import styles from "./Field.module.css";

export interface FieldControlProps {
  id: string;
  "aria-invalid"?: true;
  "aria-describedby"?: string;
}

/** Lógica pura, testeable sin React. Orden de describedby: help antes que error. */
export function fieldControlProps(id: string, hasError: boolean, hasHelp: boolean): FieldControlProps {
  const describedBy = [hasHelp ? `${id}-help` : null, hasError ? `${id}-error` : null]
    .filter(Boolean)
    .join(" ");
  const out: FieldControlProps = { id };
  if (hasError) out["aria-invalid"] = true;
  if (describedBy) out["aria-describedby"] = describedBy;
  return out;
}

/** [ADICIÓN ARQUITECTO] Devuelve el id DOM del primer campo con error según el
    orden visual declarado, o null. Pura, testeable sin React ni DOM. */
export function firstErrorFieldId(
  prefix: string,
  domOrder: readonly string[],
  errors: Record<string, string>,
): string | null {
  const k = domOrder.find((key) => key in errors);
  return k ? `${prefix}-${k}` : null;
}

export interface FieldProps {
  label: ReactNode;
  /** Clase del label. En migraciones pasar SIEMPRE la clase existente de la feature
      (ej. styles.label del module.css del modal) para look byte-idéntico. */
  labelClassName?: string;
  help?: ReactNode;
  /** Texto de error inline. Truthy ⇒ aria-invalid + aria-describedby en el control. */
  error?: ReactNode;
  required?: boolean;
  /** Override del id; default useId(). */
  id?: string;
  /** ÚNICA forma de children: render-prop que recibe los props a esparcir en el control. */
  children: (ctl: FieldControlProps) => ReactNode;
}

export default function Field({ label, labelClassName, help, error, required, id, children }: FieldProps) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  const ctl = fieldControlProps(fieldId, Boolean(error), Boolean(help));
  return (
    <div className={styles.field}>
      <label htmlFor={fieldId} className={labelClassName ?? styles.label}>
        {label}
        {required ? <span className={styles.required} aria-hidden="true"> *</span> : null}
      </label>
      {children(ctl)}
      {help ? <div id={`${fieldId}-help`} className={styles.help}>{help}</div> : null}
      {error ? <div id={`${fieldId}-error`} className={styles.error} role="alert">{error}</div> : null}
    </div>
  );
}
```

`Field.module.css`:

```css
/* Plan 162 — display:contents: los hijos participan del layout del padre como si
   no hubiera wrapper ⇒ byte-idéntico con el patrón label+control hermanos de hoy. */
.field {
  display: contents;
}

.label {
  color: var(--text-primary);
  font-size: 12px;
}

.required {
  color: var(--danger);
}

.help {
  color: var(--text-muted);
  font-size: 12px;
}

.error {
  color: var(--status-danger-text);
  font-size: 12px;
}
```

`Checkbox.tsx` (label envolvente, patrón de la casa visto en `NewProjectModal.tsx:449-456` `styles.checkboxRow`; el contenido del label se renderiza SIN span envolvente para no alterar selectores/spacing existentes):

```tsx
import { InputHTMLAttributes, ReactNode } from "react";
import styles from "./Checkbox.module.css";

export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label: ReactNode;
  /** En migraciones pasar la clase existente de la feature (ej. styles.checkboxRow). */
  labelClassName?: string;
}

export function checkboxPartKeys(): string[] {
  return ["row"];
}

export default function Checkbox({ label, labelClassName, className, ...rest }: CheckboxProps) {
  const cls = checkboxPartKeys().map((k) => styles[k]).filter(Boolean).join(" ");
  return (
    <label className={labelClassName ?? cls}>
      <input type="checkbox" className={className} {...rest} />
      {label}
    </label>
  );
}
```

`Checkbox.module.css`:

```css
.row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--text-primary);
  cursor: pointer;
}
```

**Líneas EXACTAS a agregar al final de `components/ui/index.ts`:**

```ts
// Plan 162 — primitivas de formulario (aditivo al contrato 138 §10.2).
export { default as Field, fieldControlProps, firstErrorFieldId } from "./Field";
export type { FieldProps, FieldControlProps } from "./Field";
export { default as Input, inputPartKeys } from "./Input";
export type { InputProps } from "./Input";
export { default as Select, selectPartKeys } from "./Select";
export type { SelectProps } from "./Select";
export { default as Textarea, textareaPartKeys } from "./Textarea";
export type { TextareaProps } from "./Textarea";
export { default as Checkbox, checkboxPartKeys } from "./Checkbox";
export type { CheckboxProps } from "./Checkbox";
```

Nota: `useId` requiere React 18 — confirmado `react: ^18.3.1` en `frontend/package.json:17`.

**Comandos exactos:**
```powershell
cd "Stacky Agents/frontend"
npx vitest run src/__tests__/formPrimitives.test.ts
npx vitest run src/__tests__/uiPrimitives.test.ts
npx vitest run src/__tests__/uiDebtRatchet.test.ts
npx vitest run src/__tests__/motionDebtRatchet.test.ts
npx vitest run src/__tests__/formDebtRatchet.test.ts
npx tsc --noEmit
```

**Criterio de aceptación (binario):** los 6 comandos exit 0. `uiPrimitives.test.ts` NO se modifica (su lista de 8 es contrato congelado del 138; las nuevas van en `formPrimitives.test.ts`).

**Flag:** sin flag — primitivas sin consumidores aún; look de la app inalterado (precedente 138 F2). **Runtimes:** idéntico en los 3; fallback N/A. **Trabajo del operador: ninguno.**

---

### F2 — Migración ejemplar M1: `NewProjectModal.tsx` (Tier A: Field + validación inline + primer adoptante 143)

**Objetivo:** migrar el formulario más representativo de la app a primitivas + validación inline por campo + submit con `useOptimisticPending`, con apariencia en reposo byte-idéntica. Valor: patrón de referencia copiable para toda migración futura.

**Archivo (exacto):** EDITAR `Stacky Agents/frontend/src/components/NewProjectModal.tsx`. PROHIBIDO tocar `NewProjectModal.module.css`.

**Pre-flight adicional obligatorio:** `grep -n "> " "Stacky Agents/frontend/src/components/NewProjectModal.module.css"` buscando combinadores hijo (`.algo > label`, `.algo > input`). Si alguna regla matchea por combinador hijo elementos que este plan envuelve/reemplaza ⇒ **STOP y reportar** (el `display: contents` de Field NO es transparente para selectores `>`). Repetir este pre-flight en F3 y F4 con el module.css correspondiente.

**Cambios EXACTOS (en orden):**

1. Imports: agregar
   ```ts
   import { Field, Input, Select, Checkbox, firstErrorFieldId } from "./ui";
   import useOptimisticPending from "../hooks/useOptimisticPending";
   ```
2. Estado: agregar `const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});` y reemplazar `const [saving, setSaving] = useState(false);` (ancla: `NewProjectModal.tsx:40`) por
   ```ts
   const { pending: saving, run, pendingClass } = useOptimisticPending();
   ```
   Todos los usos de lectura de `saving` quedan iguales; los `setSaving(true/false)` se ELIMINAN (los maneja `run`).
3. En `patch(...)` (ancla: `function patch(key: keyof InitProjectPayload, value: unknown)`, `NewProjectModal.tsx:50-52`): tras `setForm(...)` agregar limpieza del error del campo editado:
   ```ts
   setFieldErrors((fe) => {
     if (!(key in fe)) return fe;
     const next = { ...fe };
     delete next[key as string];
     return next;
   });
   ```
4. Nueva función pura ANTES de `handleSubmit` — traduce 1:1 las condiciones existentes de `handleSubmit` (ancla: `NewProjectModal.tsx:190-210`), MISMOS mensajes, keys = nombre del campo del payload:
   ```ts
   function validate(f: InitProjectPayload): Record<string, string> {
     const errs: Record<string, string> = {};
     if (!f.name.trim()) errs.name = "Ingresá un nombre de proyecto";
     if (!f.workspace_root.trim()) errs.workspace_root = "Ingresá el workspace root";
     if (f.tracker_type === "azure_devops") {
       if (!f.organization?.trim()) errs.organization = "Ingresá la organización de Azure DevOps";
       if (!f.ado_project?.trim()) errs.ado_project = "Ingresá el proyecto de Azure DevOps";
     } else if (f.tracker_type === "jira") {
       if (!f.jira_url?.trim()) errs.jira_url = "Ingresá la URL de Jira";
       if (!f.jira_key?.trim()) errs.jira_key = "Ingresá la clave del proyecto Jira";
     } else {
       if (!f.mantis_url?.trim()) errs.mantis_url = "Ingresá la URL de Mantis";
       if (!f.mantis_project_id?.trim()) errs.mantis_project_id = "Seleccioná un proyecto de Mantis";
       const protocol = f.mantis_protocol || "rest";
       if (protocol === "soap") {
         if (!f.mantis_username?.trim()) errs.mantis_username = "Ingresá el usuario de Mantis (SOAP)";
       } else {
         if (!f.mantis_token?.trim()) errs.mantis_token = "Ingresá el token de API de Mantis";
       }
     }
     return errs;
   }

   // [ADICIÓN ARQUITECTO] Orden VISUAL del form (para foco-al-primer-error).
   const NP_FIELD_DOM_ORDER = ["name", "workspace_root", "organization", "ado_project", "jira_url", "jira_key", "mantis_url", "mantis_project_id", "mantis_username", "mantis_token"] as const;
   ```
   Nota (C4): el mensaje actual de `NewProjectModal.tsx:203` dice "Selección un proyecto de Mantis" (typo preexistente). Queda CONGELADO el texto corregido "Seleccioná un proyecto de Mantis" de la tabla de arriba: es el ÚNICO mensaje que cambia respecto del código actual (fix intencional de typo); los demás son byte-idénticos.
5. `handleSubmit` reescrito (reemplaza el cuerpo completo de `NewProjectModal.tsx:190-226`):
   ```ts
   async function handleSubmit() {
     setError(null);
     const errs = validate(form);
     setFieldErrors(errs);
     if (Object.keys(errs).length > 0) {
       // [ADICIÓN ARQUITECTO] foco al primer campo con error (ids de la regla (h)).
       const fid = firstErrorFieldId("np", NP_FIELD_DOM_ORDER, errs);
       if (fid) document.getElementById(fid)?.focus();
       return;
     }
     try {
       const result = await run(() => Projects.init(buildPayload()));
       if (result.ok) {
         onCreated(result.project.name, result.project.display_name);
         onClose();
       } else {
         setError((result as any).error || "Error desconocido");
       }
     } catch (e: any) {
       setError(e?.message || "Error de conexión");
     }
   }
   ```
   (`run` re-lanza — contrato del hook `useOptimisticPending.ts:14` — por eso el try/catch se conserva; el banner global `:604` se conserva para errores de API, que NO son errores de campo.)
6. Migrar TODOS los pares label+control del cuerpo. Patrón mecánico (ejemplo con el primer campo, ancla `NewProjectModal.tsx:239-246`):
   ```tsx
   <Field label="Nombre interno del proyecto (ID, en mayúsculas)" labelClassName={styles.label} error={fieldErrors.name}>
     {(ctl) => (
       <Input
         {...ctl}
         invalid={Boolean(fieldErrors.name)}
         className={styles.input}
         type="text"
         placeholder="Ej: RSPACIFICO, B2IMPACT"
         value={form.name}
         onChange={(e) => patch("name", e.target.value.toUpperCase())}
       />
     )}
   </Field>
   ```
   Reglas cerradas del patrón: (a) el `className` de la feature se CONSERVA tal cual; (b) `labelClassName` = la clase que el label tenía (`styles.label` o `styles.labelSm`); (c) `error={fieldErrors.<key>}` SOLO en los campos con key en `validate` — los demás campos van sin `error` (Field sigue aportando `htmlFor`/`id`); (d) selects nativos (anclas `:434` "Versión API" y `:547` "Proyecto Mantis") ⇒ `Select` con las mismas `<option>` como children; (e) checkboxes envueltos en `styles.checkboxRow` (anclas `:449-456` y `:583-590`) ⇒ `Checkbox` con `labelClassName={styles.checkboxRow}` y `label` = el JSX interno existente sin modificar; (f) los inputs con botón "examinar" al lado (anclas `:266-284`, `:286-312`) conservan su div contenedor: Field envuelve label+div, el control dentro del div recibe `{...ctl}` vía la render-prop; (g) PROHIBIDO pasar `required` a Field en las migraciones F2-F4 (C3): agregaría un ` *` visible y rompería G1 — la prop queda solo para superficies NUEVAS futuras; (h) [ADICIÓN ARQUITECTO] todo Field cuyo campo tiene key en `validate` pasa además `id={"np-" + <key>}` (ids DOM estables para el foco-al-primer-error; en F3 el prefijo es `"ep-"`), los Field sin key en `validate` no pasan `id` (usan el `useId()` default).
7. Footer (ancla `:607-614`): los botones nativos NO se reemplazan por la primitiva Button (cambiaría el look — fuera de scope). Solo el botón de submit suma el feedback del 143:
   ```tsx
   <button
     className={`${styles.btnAccent} ${pendingClass}`.trim()}
     onClick={handleSubmit}
     disabled={saving}
     aria-busy={saving || undefined}
   >
     {saving ? "Inicializando…" : "Crear e inicializar"}
   </button>
   ```
8. Bajar el baseline: `$env:FORM_DEBT_REGEN='1'; npx vitest run src/__tests__/formDebtRatchet.test.ts; Remove-Item Env:\FORM_DEBT_REGEN`.

**Tests primero:** el "test que falla por la razón correcta" de esta fase es el propio ratchet + K3: antes de migrar, `formDebtBaseline.json` contiene `components/NewProjectModal.tsx`; el criterio es que DESPUÉS del regen esa clave desaparezca. Complemento estático: `grep -c "useOptimisticPending" src/components/NewProjectModal.tsx` ≥ 1.

**Comandos exactos:**
```powershell
cd "Stacky Agents/frontend"
npx vitest run src/__tests__/formDebtRatchet.test.ts
npx vitest run src/__tests__/uiDebtRatchet.test.ts
npx vitest run src/__tests__/motionDebtRatchet.test.ts
npx vitest run src/hooks/__tests__/useOptimisticPending.test.ts
npx tsc --noEmit
```

**Criterio de aceptación (binario):** los 5 comandos exit 0; `formDebtBaseline.json` sin la clave `components/NewProjectModal.tsx`; `git diff --name-only` de la fase = exactamente `frontend/src/components/NewProjectModal.tsx` + `frontend/src/__tests__/formDebtBaseline.json`.

**Flag:** sin flag — reemplazo 1:1 de presentación, look en reposo idéntico (G1); los errores inline solo aparecen donde hoy aparecía el banner (mejora estricta de feedback, precedente 140/141). **Runtimes:** idéntico en los 3; fallback N/A. **Trabajo del operador: ninguno.**

---

### F3 — Migración ejemplar M2: `EditProjectModal.tsx` (Tier A, gemelo)

**Objetivo:** replicar el patrón de F2 en el gemelo de edición, demostrando que la migración es mecánica. Valor: segundo consumidor real de las primitivas y del 143.

**Archivo (exacto):** EDITAR `Stacky Agents/frontend/src/components/EditProjectModal.tsx`. PROHIBIDO tocar `EditProjectModal.module.css`. Pre-flight de combinadores hijo como en F2.

**Cambios (mismo procedimiento cerrado de F2, con estas anclas):**
1. Imports y estado: ídem F2 §1-2. `saving` viene de `const [saving, setSaving] = useState(false);` (ancla `EditProjectModal.tsx:44`) ⇒ reemplazar por el hook. ATENCIÓN: `savingWorkflow` (ancla `:61`) es OTRO estado, de los workflows — NO tocarlo; el botón "Guardar workflow" (ancla `:721-724`) queda como está.
2. Migrar TODOS los pares label+control, los 2 selects nativos (anclas `:573` y `:687`) y todo textarea/checkbox del archivo con las reglas (a)-(h) de F2 §6 (prefijo de ids: `"ep-"`). Validación inline RESUELTA (C2 — verificado 2026-07-17, sin decisión del implementador): el submit actual (`EditProjectModal.tsx:282-297`) valida SOLO el workspace root (ancla `if (!String(form.workspace_root ?? "").trim())`, `:284-285`). Se crea `validate` con EXACTAMENTE una key: `function validate(f: typeof form): Record<string, string> { const errs: Record<string, string> = {}; if (!String(f.workspace_root ?? "").trim()) errs.workspace_root = "Ingresá el workspace root"; return errs; }`. El ÚNICO Field con `error` es el de workspace root (`id="ep-workspace_root"`); todos los demás van sin `error`. Foco-al-primer-error: `firstErrorFieldId("ep", ["workspace_root"], errs)` con el mismo patrón de F2 §5.
3. Submit principal (anclas `:748-752`, botones `styles.btnGhost`/`styles.btnAccent` con `{saving ? "Guardando…" : "Guardar cambios"}`): mismo tratamiento que F2 §5 y §7 (`run(...)` + `pendingClass` + `aria-busy={saving || undefined}`, C5). El backdrop con `shouldCloseOnBackdrop({ dirty, busy: saving })` (ancla `:304`, plan 136) sigue leyendo `saving` del hook sin cambios.
4. Regen del baseline como F2 §8.

**Comandos exactos:** los mismos 5 de F2.

**Criterio de aceptación (binario):** 5 comandos exit 0; `formDebtBaseline.json` sin la clave `components/EditProjectModal.tsx`; diff limitado a `EditProjectModal.tsx` + baseline.

**Flag:** sin flag (misma justificación F2). **Runtimes:** idéntico en los 3; fallback N/A. **Trabajo del operador: ninguno.**

---

### F4 — Migración ejemplar M3: `SettingsPage.tsx` (Tier B: controles sin label visible)

**Objetivo:** demostrar el segundo tier del patrón — controles sueltos con placeholder y sin label visible — sin agregar labels (que cambiarían el look). Valor: tercer consumidor y cobertura del caso más común fuera de modales.

**Archivo (exacto):** EDITAR `Stacky Agents/frontend/src/pages/SettingsPage.tsx`. PROHIBIDO tocar su module.css. Pre-flight de combinadores hijo como en F2.

**Cambios EXACTOS:**
1. Imports: `import { Input, Select, Checkbox } from "../components/ui";` y `import useOptimisticPending from "../hooks/useOptimisticPending";` (NO se importa Field: Tier B no agrega labels).
2. Sección webhooks (subcomponente con estado en anclas `:207-214`):
   - `const [creating, setCreating] = useState(false);` (ancla `:214`) ⇒ `const { pending: creating, run, pendingClass } = useOptimisticPending();`
   - `create` (ancla `:229-248`): eliminar `setCreating(true/false)`; envolver el cuerpo async: `await run(async () => { await Webhooks.create({...}); setUrl(""); setSecret(""); load(); });` conservando el try/catch existente alrededor (con `run` adentro del try: re-lanza y el catch actual lo captura).
   - Input de URL (ancla `:266-271`) ⇒ `<Input className={styles.inputInline} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com/webhook" aria-label="URL del webhook" />`
   - Los 2 selects (anclas `:274-278` y `:279-286`) ⇒ `Select` con `aria-label="Evento del webhook"` y `aria-label="Formato del webhook"`, mismas options/props.
   - Input de secret (ancla `:289-294`) ⇒ `Input` con `aria-label="Secret HMAC opcional"`.
   - Botón "Crear" (ancla `:295`): `className={`${styles.subTab} ${pendingClass}`.trim()}` + `aria-busy={creating || undefined}` (C5), resto igual (`disabled={creating || !url.trim()}` se conserva).
3. Toggle checkbox (ancla `:78-79`, `<label className={styles.toggle}>` con un input checkbox adentro): ⇒ `<Checkbox labelClassName={styles.toggle} label={<JSX interno existente sin modificar>} checked={...} onChange={...} />` conservando exactamente los props actuales del input. LISTA CERRADA (C1 — verificada por grep 2026-07-17): los ÚNICOS 5 controles crudos de `SettingsPage.tsx` son el toggle (`:79`), el input de URL (`:266`), los 2 selects (`:274`, `:279`) y el input de secret (`:289`); con §2 y este §3 el archivo queda en deuda 0 y la clave `pages/SettingsPage.tsx` desaparece del baseline. Si tras un rebase apareciera un control nuevo, el ratchet lo reporta ⇒ STOP y avisar al orquestador (no improvisar la migración).
4. Regen del baseline como F2 §8.

**Comandos exactos:** los mismos 5 de F2.

**Criterio de aceptación (binario):** 5 comandos exit 0; `formDebtBaseline.json` sin la clave `pages/SettingsPage.tsx`; diff limitado a `SettingsPage.tsx` + baseline; K4 ya se cumple (≥3 consumidores de `useOptimisticPending`).

**Flag:** sin flag (misma justificación F2; los `aria-label` son invisibles). **Runtimes:** idéntico en los 3; fallback N/A. **Trabajo del operador: ninguno.**

---

### F5 — Gate final: suite nombrada + tipos + smoke manual documentado

**Objetivo:** verificación integral sin falsos verdes. Valor: cierre auditable del plan.

**Sin archivos nuevos.** Correr POR ARCHIVO (test-order pollution conocida en vitest, igual que pytest — nunca la suite completa):

```powershell
cd "Stacky Agents/frontend"
npx vitest run src/__tests__/formDebtRatchet.test.ts
npx vitest run src/__tests__/formPrimitives.test.ts
npx vitest run src/__tests__/uiPrimitives.test.ts
npx vitest run src/__tests__/uiDebtRatchet.test.ts
npx vitest run src/__tests__/motionDebtRatchet.test.ts
npx vitest run src/__tests__/motionA11yGuard.test.ts
npx vitest run src/hooks/__tests__/useOptimisticPending.test.ts
npx tsc --noEmit
```

**Smoke manual (checklist para el operador o quien supervise; NO bloquea el cierre de código, se documenta como pendiente si no se ejecuta — precedente 132 F3/134 F8):**
1. Abrir "Nuevo proyecto": look idéntico al actual en reposo. Submit vacío ⇒ errores inline bajo Nombre y Workspace root (rojos, sin alert ni toast) y el foco salta al PRIMER campo con error (ADICIÓN ARQUITECTO); tipear en el campo ⇒ su error desaparece.
2. Submit válido ⇒ botón "Crear e inicializar" se atenúa y bloquea de inmediato (`.u-pending`) hasta resolver.
3. "Editar proyecto": ídem 1-2 con "Guardar cambios"; guardar un workflow sigue funcionando igual (estado `savingWorkflow` intacto).
4. Settings → webhooks: crear un webhook muestra el botón "Crear" atenuado durante el POST; los selects abren con esquema oscuro correcto (color-scheme, `theme.css:251-254`).
5. Tema claro y oscuro (plan 141): los errores inline son legibles en ambos (usan `--status-danger-text`, que ya tiene variante por tema).

**Criterio de aceptación (binario):** los 8 comandos exit 0 con output leído (no reportado por terceros). Checklist de smoke transcripto en el resumen final con estado ejecutado/pendiente por ítem.

**Flag:** N/A. **Runtimes:** N/A; fallback N/A. **Trabajo del operador: ninguno** (el smoke es opcional y quien lo corre es quien supervisa).

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|--------|-----------|
| R1 | `display: contents` de Field no es transparente para selectores con combinador hijo (`.body > label`): una regla así dejaría de matchear tras envolver | Pre-flight obligatorio por superficie (F2/F3/F4): grep de combinadores hijo en el module.css; si matchea elementos migrados ⇒ STOP y reportar. No adivinar |
| R2 | Promesa que nunca settlea deja el botón en `.u-pending` para siempre (contrato C5 del 143, `useOptimisticPending.ts:9-14`) | Solo se envuelven llamadas de `api/endpoints` (fetch: resuelve o rechaza); se conserva `disabled` como cinturón; no se envuelven operaciones sin timeout |
| R3 | El ratchet nuevo se cuenta a sí mismo o colisiona con prosa (gotcha 6+ veces en la casa) | Scan restringido a `.tsx`/`.jsx`; el test es `.ts` con prohibición explícita de renombrar; G6 prohíbe las secuencias literales en comentarios de archivos migrados |
| R4 | REGEN del baseline congela deuda nueva de ramas paralelas | El REGEN copia el mecanismo de `uiDebtRatchet.test.ts:104-111`: rechaza la regeneración si algún archivo AUMENTÓ vs. el baseline previo |
| R5 | Colisión de alcance con el plan paralelo `160` (Resolutor de incidencias: toca `IncidentResolverModal.tsx`) | `IncidentResolverModal.tsx` explícitamente NO se migra en este plan (queda en baseline); §6 |
| R6 | Cambio de DOM (id/aria/clase extra) rompe algún test/snapshot existente | No hay RTL/jsdom ni snapshots de DOM en el frontend (`package.json:24-31`); los ratchets existentes son fs+regex y se corren todos en cada fase |
| R7 | `Checkbox` altera spacing al reemplazar el label envolvente | El label conserva la clase de la feature vía `labelClassName` y el contenido se renderiza sin wrapper extra (F1); smoke visual en F5 |
| R8 | Un modelo menor "mejora" el look de los botones de footer migrándolos a Button | Prohibición explícita en F2 §7: los botones nativos de footer NO se tocan salvo agregar `pendingClass` (+ `aria-busy`, C5) |
| R9 | Merge 3-way silencioso duplica los exports agregados al final del barrel `components/ui/index.ts` si otra rama también apendea (gotcha real de la casa) | Tras cualquier merge que toque el barrel: `npx tsc --noEmit` (un re-export duplicado es error de compilación) + grep de líneas `export { default as` duplicadas en el barrel (C8) |

## 6. Fuera de scope

- **Primitiva Modal/Dialog, focus-trap y confirmaciones (incluido `window.confirm`)**: dueño exclusivo el plan `157_PLAN_DIALOGO_CANONICO_FOCUS_TRAP_Y_CONFIRMACIONES.md` de la rama paralela `plans-ux-logs-final`. Este plan NO define contenedores de diálogo: migra solo el CONTENIDO de formularios.
- **`IncidentResolverModal.tsx` y `EpicFromBriefModal.tsx`**: el primero es alcance del plan paralelo 160 (resolutor de incidencias); ambos quedan congelados en el baseline para migración futura.
- **Toast/surfacing global de errores**: plan 135. El banner de error de API de cada modal se conserva.
- **Densidad/spacing de superficies densas**: plan 150. **Onboarding**: plan 151. **Centro de notificaciones**: plan 152. **DB Compare config UX**: plan 157 de esta rama.
- **Adopción masiva de `Button`/`IconButton`** en footers y demás superficies: alcance del 138 y sucesores; aquí solo `pendingClass` sobre los botones nativos existentes.
- **Migración del resto de los ~70 archivos con deuda**: queda congelada por el ratchet; cada plan futuro que toque una superficie la baja.
- **Inputs `type="radio"`, `type="file"`, `type="range"`, `type="color"`**: sin primitiva propia en este plan; permanecen en baseline.
- **Backend**: cero cambios (100% frontend).

## 7. Glosario, orden de implementación y DoD

**Glosario:**
- **Primitiva**: componente base de `components/ui/` con `.module.css` par, props extendiendo atributos HTML nativos y helper puro `*PartKeys` (plan 138).
- **Barrel**: `components/ui/index.ts`, punto único de export.
- **Ratchet**: test fs+regex con baseline JSON por archivo donde la deuda solo puede bajar; REGEN = regenerar baseline vía env var, solo cuando bajó.
- **Tier A / Tier B**: migración con label visible (Field envolvente) / control suelto sin label (primitiva + `aria-label`).
- **Byte-idéntico**: mismo render visual en reposo; atributos invisibles (id/aria) y estados nuevos (error inline, pending) permitidos.
- **Tokens**: variables CSS de `theme.css` (planes 138/141/143). **`.u-pending`**: utilidad del 143 que atenúa y bloquea (`theme.css:378`).
- **Smoke manual**: verificación visual humana documentada, sin framework (no hay RTL/jsdom).

**Orden de implementación:** 1) F0 → 2) F1 → 3) F2 → 4) F3 → 5) F4 → 6) F5. F2-F4 dependen de F1; F0 va primero para congelar el estado del mundo. Cada fase deja verde todo lo anterior antes de avanzar.

**Definición de Hecho (DoD) global:**
1. K1-K6 de §1 verdes con output real leído (cero falsos verdes; la verificación final la hace el agente principal).
2. Baseline `formDebtBaseline.json` versionado, sin claves de los 3 archivos migrados ni de `components/ui/`.
3. Ningún archivo fuera de la lista cerrada tocado: 5 pares de primitivas + barrel + 2 tests nuevos + baseline + 3 superficies migradas.
4. Ningún `*.module.css` de features modificado; ningún token nuevo en `theme.css`.
5. Estado del doc actualizado a IMPLEMENTADO al cierre (regla de la casa: sincronizar encabezado).
6. Checklist de smoke de F5 transcripto con estado por ítem.
