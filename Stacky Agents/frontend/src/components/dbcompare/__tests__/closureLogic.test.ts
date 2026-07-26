// Plan 176 F7 — Lógica del panel de verificación de cierre.
import { describe, it, expect } from "vitest";
import {
  canVerify,
  closureSummaryLabel,
  explainResult,
  sortForDisplay,
  type ClosureReport,
  type ClosureResult,
} from "../closureLogic";

function reporte(over: Partial<ClosureReport["summary"]> = {}): ClosureReport {
  return {
    version: 1,
    old_run_id: "viejo",
    verification_run_id: "nuevo",
    results: [],
    summary: { ok: 0, violado: 0, sin_expectativa: 0, ...over },
  };
}

function res(over: Partial<ClosureResult> = {}): ClosureResult {
  return { item_key: "table:dbo.A", expectation: "resuelto", status: "ok", ...over };
}

describe("canVerify", () => {
  it("una corrida que no terminó no se puede verificar", () => {
    expect(canVerify("running", { confirmado: 3, excluido: 1 })).toBe(false);
  });

  it("sin decisiones no hay nada que verificar", () => {
    expect(canVerify("done", { confirmado: 0, excluido: 0 })).toBe(false);
    expect(canVerify("done", null)).toBe(false);
  });

  it("con una sola decisión ya vale la pena", () => {
    expect(canVerify("done", { confirmado: 1, excluido: 0 })).toBe(true);
    expect(canVerify("done", { confirmado: 0, excluido: 1 })).toBe(true);
  });
});

describe("closureSummaryLabel", () => {
  it("arma el resumen literal", () => {
    expect(closureSummaryLabel(reporte({ ok: 3, violado: 1, sin_expectativa: 2 })))
      .toBe("3 ok · 1 violados · 2 sin expectativa");
  });

  it("sin reporte no explota", () => {
    expect(closureSummaryLabel(null)).toBe("0 ok · 0 violados · 0 sin expectativa");
  });
});

describe("explainResult", () => {
  it("distingue los cuatro casos", () => {
    expect(explainResult(res({ expectation: "resuelto", status: "ok" })))
      .toContain("Se aplicó");
    expect(explainResult(res({ expectation: "resuelto", status: "violado" })))
      .toContain("sigue ahí");
    // Que un excluido persista es lo correcto, no un fallo.
    expect(explainResult(res({ expectation: "persiste", status: "ok" })))
      .toContain("Intacto");
    expect(explainResult(res({ expectation: "persiste", status: "violado" })))
      .toContain("no debía");
  });
});

describe("sortForDisplay", () => {
  it("los violados van primero: es lo único que exige acción", () => {
    const ordenado = sortForDisplay([
      res({ item_key: "table:dbo.A", status: "ok" }),
      res({ item_key: "table:dbo.Z", status: "violado" }),
      res({ item_key: "table:dbo.B", status: "ok" }),
    ]);

    expect(ordenado.map((r) => r.item_key)).toEqual([
      "table:dbo.Z", "table:dbo.A", "table:dbo.B",
    ]);
  });

  it("no muta el original", () => {
    const original = [res({ item_key: "b", status: "ok" }),
                      res({ item_key: "a", status: "violado" })];
    sortForDisplay(original);

    expect(original[0].item_key).toBe("b");
  });

  it("tolera una lista vacía", () => {
    expect(sortForDisplay([])).toEqual([]);
  });
});
