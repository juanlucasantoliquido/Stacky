/**
 * Plan 162 F1 — Contrato de primitivas de FORMULARIO (sin RTL/jsdom: funciones puras + fs).
 */
import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const UI_DIR = path.join(process.cwd(), "src", "components", "ui");
const FORM_COMPONENTS = ["Field", "Input", "Select", "Textarea", "Checkbox"] as const;

describe("formPrimitives (plan 162 F1)", () => {
  it("existen los 5 pares .tsx/.module.css", () => {
    for (const c of FORM_COMPONENTS) {
      expect(fs.existsSync(path.join(UI_DIR, `${c}.tsx`)), `${c}.tsx`).toBe(true);
      expect(fs.existsSync(path.join(UI_DIR, `${c}.module.css`)), `${c}.module.css`).toBe(true);
    }
  });

  it("el barrel re-exporta los 5 componentes como funciones", async () => {
    const barrel = await import("../components/ui");
    for (const c of FORM_COMPONENTS) {
      expect(typeof (barrel as Record<string, unknown>)[c], c).toBe("function");
    }
  });

  it("los .module.css usan tokens (var(--)) y cero hex", () => {
    for (const c of FORM_COMPONENTS) {
      const css = fs.readFileSync(path.join(UI_DIR, `${c}.module.css`), "utf-8");
      expect(/#[0-9a-fA-F]{3,8}\b/.test(css), `${c}.module.css tiene hex`).toBe(false);
      expect(css.includes("var(--"), `${c}.module.css no usa tokens`).toBe(true);
    }
  });

  it("los .tsx no usan style={{ literal", () => {
    for (const c of FORM_COMPONENTS) {
      const tsx = fs.readFileSync(path.join(UI_DIR, `${c}.tsx`), "utf-8");
      expect(tsx.includes("style={{"), `${c}.tsx tiene style={{ literal`).toBe(false);
    }
  });

  it("fieldControlProps: las 4 combinaciones error/help", async () => {
    const { fieldControlProps } = await import("../components/ui/Field");
    expect(fieldControlProps("f1", false, false)).toEqual({ id: "f1" });
    expect(fieldControlProps("f1", true, false)).toEqual({
      id: "f1", "aria-invalid": true, "aria-describedby": "f1-error",
    });
    expect(fieldControlProps("f1", false, true)).toEqual({
      id: "f1", "aria-describedby": "f1-help",
    });
    expect(fieldControlProps("f1", true, true)).toEqual({
      id: "f1", "aria-invalid": true, "aria-describedby": "f1-help f1-error",
    });
  });

  it("firstErrorFieldId: primer error según orden DOM (ADICIÓN ARQUITECTO)", async () => {
    const { firstErrorFieldId } = await import("../components/ui/Field");
    expect(firstErrorFieldId("np", ["a", "b"], {})).toBeNull();
    expect(firstErrorFieldId("np", ["a", "b"], { b: "x" })).toBe("np-b");
    expect(firstErrorFieldId("np", ["a", "b"], { a: "x", b: "y" })).toBe("np-a");
  });

  it("partKeys de controles: base e invalid", async () => {
    const { inputPartKeys } = await import("../components/ui/Input");
    const { selectPartKeys } = await import("../components/ui/Select");
    const { textareaPartKeys } = await import("../components/ui/Textarea");
    const { checkboxPartKeys } = await import("../components/ui/Checkbox");
    expect(inputPartKeys(false)).toEqual(["input"]);
    expect(inputPartKeys(true)).toEqual(["input", "invalid"]);
    expect(selectPartKeys(false)).toEqual(["select"]);
    expect(selectPartKeys(true)).toEqual(["select", "invalid"]);
    expect(textareaPartKeys(false)).toEqual(["textarea"]);
    expect(textareaPartKeys(true)).toEqual(["textarea", "invalid"]);
    expect(checkboxPartKeys()).toEqual(["row"]);
  });
});
