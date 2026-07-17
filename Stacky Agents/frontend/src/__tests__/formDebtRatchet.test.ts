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
