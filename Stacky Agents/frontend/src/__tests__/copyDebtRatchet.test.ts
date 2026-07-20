/**
 * Plan 194 F5 — Ratchet de deuda de portapapeles.
 * Congela, POR ARCHIVO, la cantidad de escrituras directas al portapapeles
 * (patrón writeText fuera del servicio canónico) bajo src/. La deuda solo BAJA.
 *
 * Regenerar baseline (solo cuando la deuda BAJÓ):
 *   PowerShell:  $env:COPY_DEBT_REGEN='1'; npx vitest run src/__tests__/copyDebtRatchet.test.ts; Remove-Item Env:\COPY_DEBT_REGEN
 *   bash:        COPY_DEBT_REGEN=1 npx vitest run src/__tests__/copyDebtRatchet.test.ts
 *
 * Si renombrás/movés un archivo con deuda: mover a mano su entrada del baseline
 * a la clave nueva (mismo contador) y correr el test normal.
 * El único lugar legítimo de escritura al portapapeles es services/copyService.
 */
import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const FRONTEND_ROOT = process.cwd(); // correr SIEMPRE desde Stacky Agents/frontend
const SRC = path.join(FRONTEND_ROOT, "src");
const BASELINE_PATH = path.join(SRC, "__tests__", "copyDebtBaseline.json");

// Atrapa navigator.clipboard.writeText( y las llamadas partidas en 2 líneas
// (la línea de continuación matchea sola, SIN flag multiline). NO ratchetea
// clipboard.write( a secas (§4.11): demasiado genérico.
const COPY_RES: RegExp[] = [/\.writeText\s*\(/g];

// Único lugar legítimo: el módulo canónico, su test, y el propio ratchet
// (se auto-excluye porque su fuente contiene el patrón).
const ALLOWLIST = new Set([
  "services/copyService.ts",
  "services/__tests__/copyService.test.ts",
  "__tests__/copyDebtRatchet.test.ts",
]);

interface Baseline {
  copyByFile: Record<string, number>;
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
  const copyByFile: Record<string, number> = {};
  for (const rel of files) {
    if (!(rel.endsWith(".ts") || rel.endsWith(".tsx"))) continue;
    if (ALLOWLIST.has(rel)) continue;
    const content = fs.readFileSync(path.join(SRC, rel), "utf-8");
    const n = countMatches(content, COPY_RES);
    if (n > 0) copyByFile[rel] = n;
  }
  return { copyByFile: sortKeys(copyByFile) };
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
  for (const [file, count] of Object.entries(current.copyByFile)) {
    const allowedBase = baseline.copyByFile[file] ?? 0;
    // Primitivas del sistema de diseño: SIEMPRE 0 (invariante mecánico).
    const forcedZero = file.startsWith("components/ui/") || file.startsWith("components/shell/");
    const allowed = forcedZero ? 0 : allowedBase;
    if (count > allowed) {
      errors.push(
        `REGRESION de portapapeles en ${file}: ${count} > ${allowed}. ` +
          `La deuda solo puede bajar (plan 194). Usa copyText de services/copyService.`,
      );
    }
  }
  return errors;
}

describe("copyDebtRatchet (plan 194 F5)", () => {
  it("src/ existe (correr desde Stacky Agents/frontend)", () => {
    expect(fs.existsSync(SRC)).toBe(true);
  });

  it("la deuda de portapapeles por archivo no aumenta respecto del baseline", () => {
    const current = computeCurrent();
    if (process.env.COPY_DEBT_REGEN === "1") {
      const prev = readBaseline();
      if (prev) {
        const errs = assertNoIncrease(current, prev);
        expect(errs, "REGEN rechazado: hay archivos que AUMENTARON su deuda:\n" + errs.join("\n")).toEqual([]);
      }
      fs.writeFileSync(BASELINE_PATH, JSON.stringify(current, null, 2) + "\n", "utf-8");
      return;
    }
    const baseline = readBaseline();
    expect(baseline, `Falta ${BASELINE_PATH}. Generarlo con COPY_DEBT_REGEN=1 (ver cabecera del test).`).not.toBeNull();
    const errs = assertNoIncrease(current, baseline as Baseline);
    expect(errs, errs.join("\n")).toEqual([]);
  });

  it("components/ui/ y components/shell/ nacen y se mantienen con deuda CERO", () => {
    const current = computeCurrent();
    const dirty = Object.keys(current.copyByFile).filter(
      (f) => f.startsWith("components/ui/") || f.startsWith("components/shell/"),
    );
    expect(dirty, `Archivos de ui/ o shell/ con escritura directa: ${dirty.join(", ")}`).toEqual([]);
  });
});
