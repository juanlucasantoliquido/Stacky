// Plan 174 F4 — Retención de queries.
import { describe, it, expect } from "vitest";
import { QUERY_TUNING, tuningFor } from "../queryTuning";

describe("QUERY_TUNING", () => {
  it("preserva los staleTime que cada página ya usaba", () => {
    // Centralizar no puede cambiar cada cuánto se revalida: eso sería un cambio
    // de carga sobre el backend disfrazado de refactor.
    expect(QUERY_TUNING.history.staleTime).toBe(30_000);
    expect(QUERY_TUNING.systemLogs.staleTime).toBe(10_000);
  });

  it("retiene al menos 10 minutos, para pintar desde cache al volver", () => {
    for (const t of Object.values(QUERY_TUNING)) {
      expect(t.gcTime).toBeGreaterThanOrEqual(10 * 60_000);
    }
  });

  it("siempre se retiene más de lo que se considera fresco", () => {
    // gcTime <= staleTime tiraría la cache justo cuando hace falta para no parpadear.
    for (const t of Object.values(QUERY_TUNING)) {
      expect(t.gcTime).toBeGreaterThan(t.staleTime);
    }
  });

  it("tuningFor devuelve el objeto exacto", () => {
    expect(tuningFor("history")).toEqual({ staleTime: 30_000, gcTime: 600_000 });
    expect(tuningFor("executionDetail")).toBe(QUERY_TUNING.executionDetail);
  });
});
