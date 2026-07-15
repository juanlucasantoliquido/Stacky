/**
 * Plan 138 F2 — Contrato de primitivas UI (sin RTL/jsdom: funciones puras + fs).
 * Fuente de verdad de firmas: plan 138 §10.2.
 */
import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const UI_DIR = path.join(process.cwd(), "src", "components", "ui");
const COMPONENTS = [
  "Button", "IconButton", "StatusChip", "Card",
  "SectionHeader", "Tabs", "Skeleton", "Spinner",
] as const;

describe("uiPrimitives (plan 138 F2)", () => {
  it("existen los 8 pares .tsx/.module.css y el barrel", () => {
    for (const c of COMPONENTS) {
      expect(fs.existsSync(path.join(UI_DIR, `${c}.tsx`)), `${c}.tsx`).toBe(true);
      expect(fs.existsSync(path.join(UI_DIR, `${c}.module.css`)), `${c}.module.css`).toBe(true);
    }
    expect(fs.existsSync(path.join(UI_DIR, "index.ts"))).toBe(true);
  });

  it("el barrel re-exporta los 8 componentes como funciones", async () => {
    const barrel = await import("../components/ui");
    for (const c of COMPONENTS) {
      expect(typeof (barrel as Record<string, unknown>)[c], c).toBe("function");
    }
  });

  it("los .module.css de ui/ usan tokens (var(--)) y cero hex", () => {
    for (const c of COMPONENTS) {
      const css = fs.readFileSync(path.join(UI_DIR, `${c}.module.css`), "utf-8");
      expect(/#[0-9a-fA-F]{3,8}\b/.test(css), `${c}.module.css tiene hex`).toBe(false);
      expect(css.includes("var(--"), `${c}.module.css no usa tokens`).toBe(true);
    }
  });

  it("los .tsx de ui/ no usan style={{ literal", () => {
    for (const c of COMPONENTS) {
      const tsx = fs.readFileSync(path.join(UI_DIR, `${c}.tsx`), "utf-8");
      expect(tsx.includes("style={{"), `${c}.tsx tiene style={{ literal`).toBe(false);
    }
  });

  it("buttonPartKeys: defaults y variantes", async () => {
    const { buttonPartKeys } = await import("../components/ui/Button");
    expect(buttonPartKeys("secondary", "md", false)).toEqual(["btn", "secondary", "md"]);
    expect(buttonPartKeys("primary", "sm", true)).toEqual(["btn", "primary", "sm", "loading"]);
    expect(buttonPartKeys("danger", "md", false)).toEqual(["btn", "danger", "md"]);
    expect(buttonPartKeys("ghost", "sm", false)).toEqual(["btn", "ghost", "sm"]);
  });

  it("iconButtonPartKeys: defaults y variantes", async () => {
    const { iconButtonPartKeys } = await import("../components/ui/IconButton");
    expect(iconButtonPartKeys("ghost", "md")).toEqual(["btn", "ghost", "md"]);
    expect(iconButtonPartKeys("danger", "sm")).toEqual(["btn", "danger", "sm"]);
  });

  it("chipPartKeys: los 5 tonos y 2 tamanos", async () => {
    const { chipPartKeys } = await import("../components/ui/StatusChip");
    for (const tone of ["success", "warning", "danger", "info", "neutral"] as const) {
      expect(chipPartKeys(tone, "sm")).toEqual(["chip", tone, "sm"]);
      expect(chipPartKeys(tone, "md")).toEqual(["chip", tone, "md"]);
    }
  });

  it("cardPartKeys: padding y elevacion", async () => {
    const { cardPartKeys } = await import("../components/ui/Card");
    expect(cardPartKeys("md", false)).toEqual(["card", "padMd"]);
    expect(cardPartKeys("none", true)).toEqual(["card", "padNone", "elevated"]);
    expect(cardPartKeys("sm", false)).toEqual(["card", "padSm"]);
  });

  it("tabPartKeys: activo vs inactivo", async () => {
    const { tabPartKeys } = await import("../components/ui/Tabs");
    expect(tabPartKeys(true, "md")).toEqual(["tab", "md", "active"]);
    expect(tabPartKeys(false, "sm")).toEqual(["tab", "sm"]);
  });

  it("skeletonStyle: defaults y numeros→px", async () => {
    const { skeletonStyle } = await import("../components/ui/Skeleton");
    expect(skeletonStyle(undefined, undefined, undefined)).toEqual({
      width: "100%", height: "14px", borderRadius: "var(--radius-sm)",
    });
    expect(skeletonStyle(120, 20, 8)).toEqual({
      width: "120px", height: "20px", borderRadius: "8px",
    });
    expect(skeletonStyle("50%", "2em", "var(--radius-full)")).toEqual({
      width: "50%", height: "2em", borderRadius: "var(--radius-full)",
    });
  });

  it("spinnerStyle: defaults y overrides", async () => {
    const { spinnerStyle } = await import("../components/ui/Spinner");
    expect(spinnerStyle(undefined, undefined, undefined, undefined)).toEqual({
      width: "14px", height: "14px", borderWidth: "2px",
      borderColor: "var(--spinner-track)", borderTopColor: "var(--accent)",
      animationDuration: "800ms",
    });
    expect(spinnerStyle(13, "var(--text-on-warn)", "rgba(28, 24, 16, 0.25)", 700)).toEqual({
      width: "13px", height: "13px", borderWidth: "2px",
      borderColor: "rgba(28, 24, 16, 0.25)", borderTopColor: "var(--text-on-warn)",
      animationDuration: "700ms",
    });
  });
});
