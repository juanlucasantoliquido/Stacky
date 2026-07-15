import { describe, it, expect } from "vitest";
import * as fs from "fs";

const html = fs.readFileSync(new URL("../../index.html", import.meta.url), "utf-8");
const mainTsx = fs.readFileSync(new URL("../main.tsx", import.meta.url), "utf-8");
const ctrl = fs.readFileSync(new URL("../services/themeController.ts", import.meta.url), "utf-8");

describe("Plan 141 F1 — anti-FOUC inline en index.html", () => {
  it("hay un script inline que lee la clave congelada y setea data-theme antes del paint", () => {
    expect(html).toContain("stacky.ui.theme");
    expect(html).toContain("data-theme");
    expect(html).toContain("prefers-color-scheme: dark");
    // default dark: el fallback ante error/valor ausente es "dark"
    expect(html).toContain('"dark"');
  });
  it("el script inline NO es un módulo (corre síncrono antes del bundle)", () => {
    // debe existir un <script> clásico (sin type=module) con la lógica de tema
    expect(/<script>[\s\S]*stacky\.ui\.theme[\s\S]*<\/script>/.test(html)).toBe(true);
  });
  it("[ADICIÓN ARQUITECTO v3] setea también el color-scheme nativo de forma síncrona", () => {
    // evita el flash de fondo/scrollbars/controles UA en modo claro antes de theme.css
    expect(html).toContain("style.colorScheme");
  });
});

describe("Plan 141 F1 — wiring en main.tsx", () => {
  it("importa y llama initThemeController antes de montar React", () => {
    expect(mainTsx).toContain("initThemeController");
    const idxInit = mainTsx.indexOf("initThemeController(");
    const idxRoot = mainTsx.indexOf("createRoot");
    expect(idxInit).toBeGreaterThan(-1);
    expect(idxInit).toBeLessThan(idxRoot); // se llama ANTES de montar
  });
});

describe("Plan 141 F1 — controlador delega en el núcleo puro", () => {
  it("usa resolveTheme/normalizeChoice y la clave del módulo puro", () => {
    expect(ctrl).toContain("resolveTheme");
    expect(ctrl).toContain("THEME_STORAGE_KEY");
    expect(ctrl).toContain('setAttribute("data-theme"');
    expect(ctrl).toContain("prefers-color-scheme: dark");
  });
  it("[ADICIÓN ARQUITECTO v3] applyEffectiveTheme fija el color-scheme nativo", () => {
    expect(ctrl).toContain("style.colorScheme");
  });
});
