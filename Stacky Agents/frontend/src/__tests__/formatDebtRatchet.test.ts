/**
 * Plan 161 F1 — Ratchet de deuda de formato.
 * Congela, POR ARCHIVO, la cantidad de formatters crudos (toLocale-familia,
 * toFixed, y new Intl.-familia) bajo src/. La deuda solo puede BAJAR.
 *
 * Regenerar baseline (solo cuando la deuda BAJÓ):
 *   PowerShell:  $env:FORMAT_DEBT_REGEN='1'; npx vitest run src/__tests__/formatDebtRatchet.test.ts; Remove-Item Env:\FORMAT_DEBT_REGEN
 *   bash:        FORMAT_DEBT_REGEN=1 npx vitest run src/__tests__/formatDebtRatchet.test.ts
 *
 * Si renombrás/movés un archivo con deuda: mover a mano su entrada del baseline
 * a la clave nueva (mismo contador) y correr el test normal.
 */
import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const FRONTEND_ROOT = process.cwd(); // correr SIEMPRE desde Stacky Agents/frontend
const SRC = path.join(FRONTEND_ROOT, "src");
const BASELINE_PATH = path.join(SRC, "__tests__", "formatDebtBaseline.json");

// C1: array de regexes; la deuda de un archivo es la SUMA de matches de todas.
const FORMAT_RES: RegExp[] = [
  /\.(toLocaleString|toLocaleDateString|toLocaleTimeString|toFixed)\s*\(/g,
  /\bnew\s+Intl\.(NumberFormat|DateTimeFormat|RelativeTimeFormat)\s*\(/g,
];

// Único lugar legítimo de esos métodos: el módulo canónico, su test, y el
// propio ratchet (se auto-excluye porque su fuente contiene las regexes).
const ALLOWLIST = new Set(["services/format.ts", "services/format.test.ts", "__tests__/formatDebtRatchet.test.ts"]);

interface Baseline {
  formatByFile: Record<string, number>;
}

export function countMatches(content: string, res: RegExp[]): number {
  return res.reduce((sum, re) => {
    const m = content.match(re);
    return sum + (m ? m.length : 0);
  }, 0);
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
  const formatByFile: Record<string, number> = {};
  for (const rel of files) {
    if (!(rel.endsWith(".ts") || rel.endsWith(".tsx"))) continue;
    if (ALLOWLIST.has(rel)) continue;
    const content = fs.readFileSync(path.join(SRC, rel), "utf-8");
    const n = countMatches(content, FORMAT_RES);
    if (n > 0) formatByFile[rel] = n;
  }
  return { formatByFile: sortKeys(formatByFile) };
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
  for (const [file, count] of Object.entries(current.formatByFile)) {
    const allowedBase = baseline.formatByFile[file] ?? 0;
    // Chrome/primitivas del sistema de diseño: SIEMPRE 0 (invariante mecánico).
    const forcedZero = file.startsWith("components/ui/") || file.startsWith("components/shell/");
    const allowed = forcedZero ? 0 : allowedBase;
    if (count > allowed) {
      errors.push(
        `format REGRESION en ${file}: ${count} > ${allowed} permitido. ` +
          `La deuda de formato solo puede bajar (plan 161). Importá ` +
          `formatDate/formatDateTime/formatDuration/formatCostUsd/formatTokens/formatInt/formatBytes/formatPercent ` +
          `de services/format en vez de formatear a mano.`,
      );
    }
  }
  return errors;
}

describe("formatDebtRatchet (plan 161 F1)", () => {
  it("src/ existe (correr desde Stacky Agents/frontend)", () => {
    expect(fs.existsSync(SRC)).toBe(true);
  });

  it("la deuda de formato por archivo no aumenta respecto del baseline", () => {
    const current = computeCurrent();
    if (process.env.FORMAT_DEBT_REGEN === "1") {
      const prev = readBaseline();
      if (prev) {
        const errs = assertNoIncrease(current, prev);
        expect(errs, "REGEN rechazado: hay archivos que AUMENTARON su deuda:\n" + errs.join("\n")).toEqual([]);
      }
      fs.writeFileSync(BASELINE_PATH, JSON.stringify(current, null, 2) + "\n", "utf-8");
      return;
    }
    const baseline = readBaseline();
    expect(baseline, `Falta ${BASELINE_PATH}. Generarlo con FORMAT_DEBT_REGEN=1 (ver cabecera del test).`).not.toBeNull();
    const errs = assertNoIncrease(current, baseline as Baseline);
    expect(errs, errs.join("\n")).toEqual([]);
  });

  it("components/ui/ y components/shell/ nacen y se mantienen con deuda CERO", () => {
    const current = computeCurrent();
    const dirty = Object.keys(current.formatByFile).filter(
      (f) => f.startsWith("components/ui/") || f.startsWith("components/shell/"),
    );
    expect(dirty, `Archivos de ui/ o shell/ con formatter crudo: ${dirty.join(", ")}`).toEqual([]);
  });
});
