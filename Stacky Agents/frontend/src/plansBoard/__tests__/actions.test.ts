import { describe, expect, it } from "vitest";
import type { RuntimeModelCatalog } from "../../api/endpoints";
import { allowedActionsForCard, buildRunPayload, effortsForModel } from "../actions";

describe("Plan 196 — allowedActionsForCard (espejo de allowed_actions_for)", () => {
  it("PROPUESTO habilita solo criticar", () => {
    expect(allowedActionsForCard("PROPUESTO", null)).toEqual(["criticar"]);
  });

  it("CRITICADO habilita solo implementar", () => {
    expect(allowedActionsForCard("CRITICADO", null)).toEqual(["implementar"]);
  });

  it("IMPLEMENTADO habilita solo supervisar", () => {
    expect(allowedActionsForCard("IMPLEMENTADO", null)).toEqual(["supervisar"]);
  });

  it("SIN_ESTADO no habilita nada", () => {
    expect(allowedActionsForCard("SIN_ESTADO", null)).toEqual([]);
  });

  it("doc_drift fuerza re-supervision aunque el estado no lo pida", () => {
    expect(allowedActionsForCard("PROPUESTO", true)).toContain("supervisar");
  });
});

describe("Plan 196 — effortsForModel", () => {
  const rt = {
    source: "test",
    default_model: "claude-haiku-4-5",
    default_effort: "high",
    models: [{ id: "claude-haiku-4-5", label: "Haiku" }],
    efforts: [
      { id: "low", label: "Bajo" },
      { id: "medium", label: "Medio" },
      { id: "high", label: "Alto" },
      { id: "xhigh", label: "Muy alto" },
    ],
    effort_support: { "claude-haiku-4-5": ["low", "medium", "high"] },
  } as unknown as RuntimeModelCatalog;

  it("filtra por effort_support del modelo", () => {
    expect(effortsForModel(rt, "claude-haiku-4-5").map((e) => e.id)).toEqual([
      "low",
      "medium",
      "high",
    ]);
  });

  it("cae a TODOS los efforts si el modelo no esta en la matriz", () => {
    expect(effortsForModel(rt, "modelo-desconocido")).toHaveLength(4);
  });
});

describe("Plan 196 — buildRunPayload", () => {
  it("proponer: sin numero, con idea saneada", () => {
    expect(buildRunPayload("proponer", null, " mi idea ", "", "")).toEqual({
      action: "proponer",
      plan_number: null,
      idea: "mi idea",
      model: null,
      effort: null,
      runtime: "claude_code_cli",
    });
  });

  it("criticar: con numero, sin idea, con modelo", () => {
    const p = buildRunPayload("criticar", 187, "", "claude-opus-4-8", "xhigh");
    expect(p.plan_number).toBe(187);
    expect(p.idea).toBeNull();
    expect(p.model).toBe("claude-opus-4-8");
  });
});
