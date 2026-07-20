import { describe, it, expect } from "vitest";
import { resolveModalInit } from "./incidentModalInit";

describe("resolveModalInit", () => {
  it("sin args -> texto vacío y sin adjuntos (KPI-4: comportamiento actual)", () => {
    const init = resolveModalInit();
    expect(init.text).toBe("");
    expect(init.files).toEqual([]);
  });

  it("con texto -> lo devuelve tal cual", () => {
    const init = resolveModalInit("hola incidencia");
    expect(init.text).toBe("hola incidencia");
    expect(init.files).toEqual([]);
  });

  it("con files -> misma referencia y largo", () => {
    const f = [{ name: "evidencia-r1.md" } as unknown as File];
    const init = resolveModalInit("t", f);
    expect(init.files).toBe(f);
    expect(init.files.length).toBe(1);
  });

  it("initialText vacío explícito se respeta (no lo pisa el default)", () => {
    expect(resolveModalInit("", undefined).text).toBe("");
  });
});
