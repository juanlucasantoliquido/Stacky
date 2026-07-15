import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { clampRows } from "../SkeletonList";

const SRC = "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/components/SkeletonList.tsx";
const CSS = "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/components/SkeletonList.module.css";

describe("Plan 140 F2 — SkeletonList", () => {
  it("clampRows fija 1..24", () => {
    expect(clampRows(0)).toBe(1);
    expect(clampRows(-3)).toBe(1);
    expect(clampRows(6)).toBe(6);
    expect(clampRows(999)).toBe(24);
    expect(clampRows(NaN)).toBe(1);
    expect(clampRows(3.9)).toBe(3);
  });
  it("consume la primitiva Skeleton de ui (no reinventa)", () => {
    const src = readFileSync(SRC, "utf-8");
    expect(/from ["']\.\/ui["']/.test(src)).toBe(true);
    expect(/<Skeleton\b/.test(src)).toBe(true);
  });
  it("es ratchet-safe: sin style-doble-llave ni hex", () => {
    const src = readFileSync(SRC, "utf-8");
    const css = readFileSync(CSS, "utf-8");
    expect(/style=\{\{/.test(src)).toBe(false);
    expect(/#[0-9a-fA-F]{3,8}\b/.test(css)).toBe(false);
  });
  it("anuncia carga accesible", () => {
    const src = readFileSync(SRC, "utf-8");
    expect(/role="status"/.test(src)).toBe(true);
    expect(/aria-busy="true"/.test(src)).toBe(true);
  });
});
