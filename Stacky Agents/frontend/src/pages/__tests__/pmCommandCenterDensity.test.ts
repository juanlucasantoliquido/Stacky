import { describe, it, expect } from "vitest";
import fs from "node:fs";

const CSS = fs.readFileSync(new URL("../PMCommandCenter.module.css", import.meta.url), "utf-8");

describe("Plan 150 F5 — PMCommandCenter migrado a spacing tokens", () => {
  it("consume var(--space-*) (≥8) — este es el gate real", () => {
    const n = (CSS.match(/var\(--space-[1-9]\)/g) ?? []).length;
    expect(n).toBeGreaterThanOrEqual(8);
  });
  it("guard: no migró bordes 1px (verde también pre-migración, C7)", () => {
    expect(CSS).not.toContain("border: var(--space-");
  });
});
