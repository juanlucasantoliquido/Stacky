import { describe, it, expect } from "vitest";
import * as fs from "fs";
import { THEME_OPTIONS } from "../AppearanceSettings";

const cmp = fs.readFileSync(new URL("../AppearanceSettings.tsx", import.meta.url), "utf-8");
const css = fs.readFileSync(new URL("../AppearanceSettings.module.css", import.meta.url), "utf-8");
const page = fs.readFileSync(new URL("../../pages/SettingsPage.tsx", import.meta.url), "utf-8");

describe("Plan 141 F4 — opciones del selector", () => {
  it("expone exactamente dark/light/system en ese orden", () => {
    expect(THEME_OPTIONS.map((o) => o.value)).toEqual(["dark", "light", "system"]);
  });
});

describe("Plan 141 F4 — el componente aplica el tema sin re-montar", () => {
  it("usa setTheme y readStoredChoice del controlador", () => {
    expect(cmp).toContain("setTheme");
    expect(cmp).toContain("readStoredChoice");
  });
  it("es un radiogroup accesible", () => {
    expect(cmp).toContain('role="radiogroup"');
    expect(cmp).toContain('type="radio"');
  });
  it("NO usa estilos inline (ratchet §10.3 del 138)", () => {
    expect(cmp.includes("style={{")).toBe(false);
  });
  it("el CSS del panel no hardcodea hex (usa tokens)", () => {
    expect(/#[0-9a-fA-F]{3,8}\b/.test(css)).toBe(false);
  });
});

describe("Plan 141 F4 — cableado en SettingsPage", () => {
  it("agrega el sub-tab appearance con su botón, contenido e import", () => {
    expect(page).toContain('"appearance"');
    expect(page).toContain("Apariencia");
    expect(page).toContain("<AppearanceSettings");
    expect(page).toContain("import AppearanceSettings");
  });
});
