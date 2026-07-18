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
// Plan 156 F6 — diálogos modales nativos del navegador. Definido
// perifrásticamente para NO auto-cazarse (ver §9 del plan): exige `(` tras el
// identificador y un lookbehind que descarta métodos ajenos `obj.metodo(`,
// salvo el prefijo explícito window.
const NATIVE_DIALOG_RE = /(?<![.\w])(?:window\.)?(?:confirm|alert|prompt)\s*\(/g;

interface Baseline {
  hexByFile: Record<string, number>;
  inlineStyleByFile: Record<string, number>;
  nativeDialogByFile: Record<string, number>;
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
  const nativeDialogByFile: Record<string, number> = {};
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
    // Plan 156 F6 — diálogos nativos en .ts/.tsx (excluye __tests__ para no
    // auto-contarse: el propio archivo del ratchet contiene el regex).
    if ((rel.endsWith(".ts") || rel.endsWith(".tsx")) && !rel.includes("__tests__/")) {
      const n = countMatches(content, NATIVE_DIALOG_RE);
      if (n > 0) nativeDialogByFile[rel] = n;
    }
  }
  return {
    hexByFile: sortKeys(hexByFile),
    inlineStyleByFile: sortKeys(inlineStyleByFile),
    nativeDialogByFile: sortKeys(nativeDialogByFile),
  };
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
      // Robusto a baseline viejo que aún no tiene la dimensión nueva (F6).
      const allowedBase = (baseline[kind] ?? {})[file] ?? 0;
      // Chrome/primitivas del sistema de diseño: SIEMPRE 0 (invariante mecánico).
      // Cubre ui/ (plan 138) y shell/ (plan 139). NO aplica a diálogos nativos:
      // es deuda heredada distribuida (only-decrease desde su baseline en frío).
      const forcedZero =
        kind !== "nativeDialogByFile" &&
        (file.startsWith("components/ui/") || file.startsWith("components/shell/"));
      const allowed = forcedZero ? 0 : allowedBase;
      if (count > allowed) {
        const hint =
          kind === "nativeDialogByFile"
            ? `Usá ConfirmButton / el sistema de notificaciones en vez de los ` +
              `diálogos modales nativos del navegador (plan 156 F6).`
            : `Usa tokens de theme.css o clases de *.module.css en vez de hex/style inline.`;
        errors.push(
          `${kind} REGRESION en ${file}: ${count} > ${allowed} permitido. ` +
            `La deuda visual solo puede bajar (plan 138). ${hint}`,
        );
      }
    }
  };
  check("hexByFile");
  check("inlineStyleByFile");
  check("nativeDialogByFile");
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
