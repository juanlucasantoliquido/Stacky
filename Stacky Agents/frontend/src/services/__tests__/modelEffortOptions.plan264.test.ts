import { describe, it, expect } from "vitest";
import { buildEffortOptions, pickerCapabilities } from "../modelEffortOptions";
import type { RuntimeModelCatalog } from "../../api/endpoints";

function _cat(overrides: Partial<RuntimeModelCatalog>): RuntimeModelCatalog {
  return {
    source: "static_config_file",
    default_model: "m1",
    default_effort: "medium",
    models: [{ id: "m1", label: "Modelo 1" }],
    efforts: [
      { id: "low", label: "low" },
      { id: "medium", label: "medium" },
      { id: "high", label: "high" },
      { id: "xhigh", label: "xhigh" },
      { id: "max", label: "max" },
    ],
    effort_support: {},
    ...overrides,
  };
}

describe("Plan 264 F5 — pickerCapabilities se adapta a effort_mode (función pura, sin DOM)", () => {
  it("1 — catálogo undefined: no lanza; nativo por default; note vacía; effectiveNow true", () => {
    const caps = pickerCapabilities(undefined);
    expect(caps.effortMode).toBe("nativo");
    expect(caps.note).toBe("");
    expect(caps.effortEffectiveNow).toBe(true);
  });

  it("2 — effort_mode no_aplica con efforts no vacío: showEfforts false igual", () => {
    const cat = _cat({ effort_mode: "no_aplica" });
    const caps = pickerCapabilities(cat);
    expect(caps.showEfforts).toBe(false);
  });

  it("3 — effort_mode presupuesto_turnos con effort_note: se expone la nota, showEfforts true", () => {
    const cat = _cat({
      effort_mode: "presupuesto_turnos",
      effort_note: "Codex no acepta un esfuerzo explícito...",
    });
    const caps = pickerCapabilities(cat);
    expect(caps.note).toBe("Codex no acepta un esfuerzo explícito...");
    expect(caps.showEfforts).toBe(true);
  });

  it("4 — buildEffortOptions con un modelo que degrada sigue devolviendo los 5 (regresión Plan 212 F4)", () => {
    const cat = _cat({
      effort_support: { m1: ["low", "medium", "high"] },
      effort_degrade: { m1: { xhigh: "high", max: "high" } },
    });
    const options = buildEffortOptions(cat, "m1");
    expect(options).toHaveLength(5);
    const max = options.find((o) => o.id === "max");
    expect(max?.supported).toBe(false);
    expect(max?.effective).toBe("high");
  });

  it("5 — catálogo SIN effort_mode (deploy viejo): nativo, showEfforts según efforts.length (retrocompatible)", () => {
    const cat = _cat({}); // sin effort_mode ni effort_effective_now
    const caps = pickerCapabilities(cat);
    expect(caps.effortMode).toBe("nativo");
    expect(caps.showEfforts).toBe(true); // tiene 5 efforts declarados
  });

  it("6 — [C8] presupuesto_turnos con effort_effective_now:false: showEfforts sigue true, effectiveNow false", () => {
    const cat = _cat({
      effort_mode: "presupuesto_turnos",
      effort_effective_now: false,
      effort_note: "queda registrada pero no cambia esta corrida",
    });
    const caps = pickerCapabilities(cat);
    expect(caps.showEfforts).toBe(true);
    expect(caps.effortEffectiveNow).toBe(false);
  });
});
