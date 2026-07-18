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
