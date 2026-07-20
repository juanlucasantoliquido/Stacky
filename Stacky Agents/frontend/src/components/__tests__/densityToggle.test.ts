import { describe, it, expect } from "vitest";
import fs from "node:fs";

const TOGGLE = fs.readFileSync(new URL("../DensityToggle.tsx", import.meta.url), "utf-8");
const APPEARANCE = fs.readFileSync(new URL("../AppearanceSettings.tsx", import.meta.url), "utf-8");

describe("Plan 150 F3 — DensityToggle", () => {
  it("usa el controlador (setDensity/currentDensity)", () => {
    expect(TOGGLE).toMatch(/setDensity/);
    expect(TOGGLE).toMatch(/currentDensity/);
  });
  it("ofrece ambas densidades", () => {
    expect(TOGGLE).toContain('"comodo"');
    expect(TOGGLE).toContain('"compacto"');
  });
  it("estilos por module.css, CERO inline styles (ratchet 138, C1)", () => {
    expect(TOGGLE).toMatch(/import\s+styles\s+from\s+"\.\/DensityToggle\.module\.css"/);
    expect(TOGGLE).not.toContain("style={{");
  });
});

describe("Plan 150 F3 — montaje en Apariencia (141 F4)", () => {
  it("AppearanceSettings importa y monta DensityToggle", () => {
    expect(APPEARANCE).toMatch(/import\s+DensityToggle/);
    expect(APPEARANCE).toContain("<DensityToggle");
  });
});
