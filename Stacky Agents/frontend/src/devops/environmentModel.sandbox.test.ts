/**
 * Tests de environmentModel.ts (Plan 107 F5) — validateSandboxOverrideLocal.
 *
 * Tabla dorada §4.1 del plan 107 (fuente única de verdad, compartida con el
 * guard backend validate_sandbox_override / test_plan107_sandbox_guard.py).
 * Paridad exigida = CLASE de resultado (error vs null), no el string exacto,
 * salvo G1-G3/G5/G9 donde el código SÍ debe coincidir textualmente.
 */
import { describe, it, expect } from "vitest";
import { validateSandboxOverrideLocal } from "./environmentModel";

const SANDBOX_GOLDEN: Array<{
  id: string;
  override: string;
  production: string;
  expected: string | null;
}> = [
  { id: "G1 igual a produccion", override: "C:\\prod", production: "C:\\prod", expected: "sandbox_igual_a_produccion" },
  { id: "G2 dentro de produccion", override: "C:\\prod\\sub", production: "C:\\prod", expected: "sandbox_dentro_de_produccion" },
  { id: "G3 produccion dentro de sandbox", override: "C:\\prod", production: "C:\\prod\\sub", expected: "produccion_dentro_de_sandbox" },
  { id: "G4 hermano disjunto (prefijo de string, NO de segmento)", override: "C:\\prod-test", production: "C:\\prod", expected: null },
  { id: "G5 case-insensitive", override: "C:\\Prod\\sub", production: "C:\\prod", expected: "sandbox_dentro_de_produccion" },
  { id: "G6 drives distintos", override: "D:\\sandbox", production: "C:\\prod", expected: null },
  { id: "G7 sin produccion configurada", override: "C:\\sandbox", production: "", expected: null },
  { id: "G9 separador final", override: "C:\\prod\\", production: "C:\\prod", expected: "sandbox_igual_a_produccion" },
];

describe("validateSandboxOverrideLocal — tabla dorada §4.1", () => {
  it.each(SANDBOX_GOLDEN)("$id", ({ override, production, expected }) => {
    expect(validateSandboxOverrideLocal(override, production)).toBe(expected);
  });

  it("local guard rejects equal path", () => {
    expect(validateSandboxOverrideLocal("C:\\prod", "C:\\prod")).toBe("sandbox_igual_a_produccion");
  });

  it("local guard rejects override inside production", () => {
    expect(validateSandboxOverrideLocal("C:\\prod\\sub", "C:\\prod")).toBe("sandbox_dentro_de_produccion");
  });

  it("local guard rejects production inside override", () => {
    expect(validateSandboxOverrideLocal("C:\\prod", "C:\\prod\\sub")).toBe("produccion_dentro_de_sandbox");
  });

  it("local guard accepts disjoint sibling with common prefix", () => {
    // G4: "C:\prod-test" es HERMANO de "C:\prod" (prefijo de STRING, no de segmento) -> OK
    expect(validateSandboxOverrideLocal("C:\\prod-test", "C:\\prod")).toBeNull();
  });

  it("local guard is case-insensitive", () => {
    expect(validateSandboxOverrideLocal("C:\\Prod\\sub", "C:\\prod")).toBe("sandbox_dentro_de_produccion");
  });

  it("local guard accepts when no production configured", () => {
    expect(validateSandboxOverrideLocal("C:\\sandbox", "")).toBeNull();
  });

  it("local guard rejects non-absolute override", () => {
    expect(validateSandboxOverrideLocal("relativo\\x", "C:\\prod")).not.toBeNull();
  });

  it("local guard rejects trailing separator variant", () => {
    expect(validateSandboxOverrideLocal("C:\\prod\\", "C:\\prod")).toBe("sandbox_igual_a_produccion");
  });
});
