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
