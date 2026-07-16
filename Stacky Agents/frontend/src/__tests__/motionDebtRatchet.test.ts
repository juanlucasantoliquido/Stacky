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
