/**
 * Plan 185 F5 — Ratchet anti-regresión de confirmaciones nativas.
 *
 * Congela el conteo GLOBAL de llamadas `confirm` nativas del navegador en
 * frontend/src. La deuda solo puede BAJAR (mismo contrato de una vía que
 * uiDebtRatchet / motionDebtRatchet). Convertir un flujo reversible a undo con
 * gracia (Plan 185) o al diálogo canónico (Plan 164) baja este número.
 *
 * Definición EXACTA de confirmCallCount (C7 — dos conjuntos DISJUNTOS, sin doble
 * conteo):
 *   (a) ocurrencias de la subcadena literal `window.confirm(`, MÁS
 *   (b) matches del regex /[^.\w]confirm\(/g  (un no-punto/no-word antes de
 *       `confirm(`), que por construcción NUNCA cubre `window.confirm(` (ahí el
 *       char previo es `.`, excluido por [^.\w]).
 * `askConfirm(` y `useConfirm(` NO matchean ninguno: la `C` de camelCase es
 * mayúscula y el regex es minúsculas.
 *
 * Si el conteo BAJÓ: editá a mano undoConfirmBaseline.json al nuevo valor.
 */
import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const FRONTEND_ROOT = process.cwd(); // correr SIEMPRE desde Stacky Agents/frontend
const SRC = path.join(FRONTEND_ROOT, "src");
const BASELINE_PATH = path.join(SRC, "__tests__", "undoConfirmBaseline.json");

// Exclusiones por RUTA EXACTA (relativa a src/): este propio test y su baseline.
const SELF_REL = "__tests__/undoConfirmRatchet.test.ts";
const BASELINE_REL = "__tests__/undoConfirmBaseline.json";

const WINDOW_CONFIRM = "window.confirm(";
const BARE_CONFIRM_RE = /[^.\w]confirm\(/g;

export function countConfirms(content: string): number {
  let n = 0;
  let idx = content.indexOf(WINDOW_CONFIRM);
  while (idx !== -1) {
    n += 1;
    idx = content.indexOf(WINDOW_CONFIRM, idx + WINDOW_CONFIRM.length);
  }
  const m = content.match(BARE_CONFIRM_RE);
  n += m ? m.length : 0;
  return n;
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

function computeCount(): number {
  let total = 0;
  for (const rel of listFiles(SRC)) {
    if (rel === SELF_REL || rel === BASELINE_REL) continue;
    if (!(rel.endsWith(".ts") || rel.endsWith(".tsx"))) continue;
    const content = fs.readFileSync(path.join(SRC, rel), "utf-8");
    total += countConfirms(content);
  }
  return total;
}

describe("undoConfirmRatchet (plan 185 F5)", () => {
  it("countConfirms cuenta window.confirm( y confirm( pero NO useConfirm(/askConfirm(", () => {
    expect(countConfirms("if (window.confirm('x')) {}")).toBe(1);
    expect(countConfirms(" confirm('y')")).toBe(1);
    expect(countConfirms("const ask = useConfirm();")).toBe(0);
    expect(countConfirms("askConfirm('z')")).toBe(0);
    // disjuntos: window.confirm( se cuenta 1 sola vez
    expect(countConfirms("window.confirm(a)")).toBe(1);
  });

  it("el conteo de confirm nativos no supera el baseline (ratchet de una vía)", () => {
    const baseline = JSON.parse(fs.readFileSync(BASELINE_PATH, "utf-8")) as {
      confirmCallCount: number;
    };
    const current = computeCount();
    expect(
      current,
      `confirm nativos = ${current} > baseline ${baseline.confirmCallCount}. ` +
        `La deuda de confirmaciones solo puede bajar (plan 185 F5): convertí el ` +
        `flujo a undo con gracia (scheduleUndoable) o al diálogo canónico (useConfirm).`,
    ).toBeLessThanOrEqual(baseline.confirmCallCount);
    expect(
      current,
      `confirm nativos = ${current} < baseline ${baseline.confirmCallCount}: ` +
        `bajá el baseline a ${current} en undoConfirmBaseline.json.`,
    ).toBe(baseline.confirmCallCount);
  });
});
