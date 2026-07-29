// Plan 212 F4 — Opciones de modelo y effort.
import { describe, it, expect } from "vitest";
import {
  buildEffortOptions,
  buildModelOptions,
  pickerCapabilities,
} from "./modelEffortOptions";
import type { RuntimeModelCatalog } from "../api/endpoints";

function cat(over: Partial<RuntimeModelCatalog> = {}): RuntimeModelCatalog {
  return {
    source: "test",
    default_model: "opus",
    default_effort: "high",
    models: [
      { id: "sonnet", label: "Sonnet 5" },
      { id: "opus", label: "Opus 5" },
    ],
    efforts: [
      { id: "low", label: "low" },
      { id: "high", label: "high" },
      { id: "xhigh", label: "xhigh" },
    ],
    effort_support: { opus: ["low", "high", "xhigh"], sonnet: ["low", "high"] },
    effort_degrade: { sonnet: { xhigh: "high" } },
    ...over,
  } as RuntimeModelCatalog;
}

describe("buildEffortOptions", () => {
  it("NUNCA esconde ni deshabilita un effort", () => {
    // Es la incidencia literal del operador: quiere verlos todos.
    const opts = buildEffortOptions(cat(), "sonnet");

    expect(opts.map((o) => o.id)).toEqual(["low", "high", "xhigh"]);
  });

  it("respeta el orden del catálogo", () => {
    expect(buildEffortOptions(cat(), "opus").map((o) => o.id)).toEqual(["low", "high", "xhigh"]);
  });

  it("anota el no soportado con a qué degrada", () => {
    const x = buildEffortOptions(cat(), "sonnet").find((o) => o.id === "xhigh")!;

    expect(x.supported).toBe(false);
    expect(x.effective).toBe("high");
    expect(x.note).toBe("se aplicará como high");
  });

  it("el soportado no lleva nota ni cambia de efectivo", () => {
    const h = buildEffortOptions(cat(), "sonnet").find((o) => o.id === "high")!;

    expect(h.supported).toBe(true);
    expect(h.effective).toBe("high");
    expect(h.note).toBe("");
  });

  it("sin dato de soporte se asume que SÍ, sin nota", () => {
    // El backend clampea igual; marcar "no soportado" sin saberlo asustaría al
    // operador sin motivo.
    const opts = buildEffortOptions(cat(), "modelo-nuevo");

    expect(opts.every((o) => o.supported && o.note === "")).toBe(true);
  });

  it("sin modelo elegido tampoco se marca nada", () => {
    expect(buildEffortOptions(cat(), null).every((o) => o.supported)).toBe(true);
  });

  it("sin degradación declarada, el efectivo es el propio id", () => {
    const c = cat({ effort_degrade: undefined });
    const x = buildEffortOptions(c, "sonnet").find((o) => o.id === "xhigh")!;

    expect(x.supported).toBe(false);
    expect(x.effective).toBe("xhigh");
  });

  it("catálogo ausente devuelve lista vacía, no rompe", () => {
    expect(buildEffortOptions(undefined, "opus")).toEqual([]);
  });
});

describe("buildModelOptions", () => {
  it("el recomendado va primero", () => {
    // Es el que se elige el 90% de las veces: no tiene por qué estar en el medio.
    const opts = buildModelOptions(cat());

    expect(opts[0].id).toBe("opus");
    expect(opts[0].recommended).toBe(true);
  });

  it("no pierde ningún modelo", () => {
    expect(buildModelOptions(cat()).map((m) => m.id).sort()).toEqual(["opus", "sonnet"]);
  });

  it("sin recomendado conserva el orden del catálogo", () => {
    const opts = buildModelOptions(cat({ default_model: null }));

    expect(opts.map((m) => m.id)).toEqual(["sonnet", "opus"]);
  });

  it("catálogo ausente devuelve lista vacía", () => {
    expect(buildModelOptions(undefined)).toEqual([]);
  });
});

describe("pickerCapabilities", () => {
  it("con catálogo completo se ofrecen las dos cosas", () => {
    const c = pickerCapabilities(cat());

    expect(c.showModels).toBe(true);
    expect(c.showEfforts).toBe(true);
  });

  it("un runtime sin efforts no los ofrece", () => {
    // Sale del catálogo, no de un if por nombre: sumar un runtime no obliga a
    // tocar este archivo.
    expect(pickerCapabilities(cat({ efforts: [] })).showEfforts).toBe(false);
  });

  it("un runtime sin modelos no los ofrece", () => {
    expect(pickerCapabilities(cat({ models: [] })).showModels).toBe(false);
  });

  it("sin catálogo no se ofrece nada", () => {
    // Plan 264 — el contrato creció de forma ADITIVA (effortMode/effortEffectiveNow);
    // ninguna clave existente se perdió, sólo se agregaron dos nuevas.
    expect(pickerCapabilities(undefined)).toEqual({
      showModels: false,
      showEfforts: false,
      note: "",
      effortMode: "nativo",
      effortEffectiveNow: true,
    });
  });
});
