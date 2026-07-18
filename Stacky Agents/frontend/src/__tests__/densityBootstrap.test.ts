import { describe, it, expect } from "vitest";
import fs from "node:fs";
import { DENSITY_STORAGE_KEY } from "../services/density";

const HTML  = fs.readFileSync(new URL("../../index.html", import.meta.url), "utf-8");
const MAIN  = fs.readFileSync(new URL("../main.tsx", import.meta.url), "utf-8");
const CTRL  = fs.readFileSync(new URL("../services/densityController.ts", import.meta.url), "utf-8");
const THEME = fs.readFileSync(new URL("../theme.css", import.meta.url), "utf-8");

describe("Plan 150 F2 — anti-FOUC inline en index.html", () => {
  it("hay un <script> inline que lee la key y setea data-density", () => {
    expect(HTML).toContain("stacky.ui.density");
    expect(HTML).toContain("data-density");
  });
});

describe("Plan 150 F2 — [ADICIÓN ARQUITECTO] guard anti-drift de key", () => {
  // El snippet inline NO puede importar la constante (script síncrono pre-bundle):
  // hay 2 copias literales que pueden divergir. Este guard las ancla a la constante real.
  it("index.html usa EXACTAMENTE la literal de DENSITY_STORAGE_KEY", () => {
    expect(HTML).toContain(`"${DENSITY_STORAGE_KEY}"`);
  });
  it("densityController usa EXACTAMENTE la misma key (vía import, no re-literal)", () => {
    expect(CTRL).toContain("DENSITY_STORAGE_KEY");
  });
});

describe("Plan 150 F2 — wiring en main.tsx", () => {
  it("importa y llama al init del controlador de densidad", () => {
    expect(MAIN).toMatch(/densityController/);
    expect(MAIN).toMatch(/initDensity\s*\(/);
  });
});

describe("Plan 150 F2 — controlador DOM", () => {
  it("setea el atributo data-density en documentElement", () => {
    expect(CTRL).toContain('setAttribute("data-density"');
  });
  it("usa el atributo transitorio de settle", () => {
    expect(CTRL).toContain("data-density-animating");
  });
});

describe("Plan 150 F2 — settle por opacity (cheap prop, §143)", () => {
  it("theme.css tiene la regla de settle con --transition-opacity", () => {
    const flat = THEME.replace(/\s+/g, " ");
    expect(flat).toContain("data-density-animating");
    expect(flat).toContain("var(--transition-opacity)");
  });
});
