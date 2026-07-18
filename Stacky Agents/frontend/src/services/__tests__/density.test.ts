import { describe, it, expect } from "vitest";
import { normalizeDensity, DENSITY_STORAGE_KEY } from "../density";

describe("Plan 150 F1 — density core", () => {
  it("compacto se conserva", () => {
    expect(normalizeDensity("compacto")).toBe("compacto");
  });
  it("comodo se conserva", () => {
    expect(normalizeDensity("comodo")).toBe("comodo");
  });
  it("cualquier otro valor cae a comodo (default byte-idéntico)", () => {
    for (const raw of [null, undefined, "", "COMPACTO", "dense", "x"]) {
      expect(normalizeDensity(raw as any)).toBe("comodo");
    }
  });
  it("la key está congelada", () => {
    expect(DENSITY_STORAGE_KEY).toBe("stacky.ui.density");
  });
});
