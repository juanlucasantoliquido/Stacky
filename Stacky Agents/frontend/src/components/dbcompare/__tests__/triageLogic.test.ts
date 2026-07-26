// Plan 176 F2 — Lógica del triage del diff.
import { describe, it, expect } from "vitest";
import {
  canTriage,
  cycleDecision,
  decisionBadgeClass,
  decisionFor,
  decisionHelp,
  decisionLabel,
  hasAnyDecision,
  noteFor,
  summarizeTriage,
  type TriageDoc,
} from "../triageLogic";

function doc(items: Record<string, { decision: string; note?: string }>): TriageDoc {
  return { version: 1, run_id: "r", items: items as never };
}

describe("decisionFor", () => {
  it("ausente es pendiente: no decidir es un estado válido", () => {
    expect(decisionFor(null, "table:dbo.A")).toBe("pendiente");
    expect(decisionFor(doc({}), "table:dbo.A")).toBe("pendiente");
  });

  it("lee la decisión guardada", () => {
    expect(decisionFor(doc({ "table:dbo.A": { decision: "excluido" } }), "table:dbo.A"))
      .toBe("excluido");
  });

  it("sin item_key no revienta", () => {
    // El backend es el único emisor de item_key; si falta, la fila no se decide.
    expect(decisionFor(doc({}), undefined)).toBe("pendiente");
    expect(decisionFor(doc({}), "")).toBe("pendiente");
  });
});

describe("noteFor", () => {
  it("devuelve la nota o vacío", () => {
    expect(noteFor(doc({ k: { decision: "excluido", note: "ya migrada" } }), "k"))
      .toBe("ya migrada");
    expect(noteFor(doc({}), "k")).toBe("");
    expect(noteFor(null, null)).toBe("");
  });
});

describe("cycleDecision", () => {
  it("cicla en el orden literal del plan", () => {
    expect(cycleDecision("pendiente")).toBe("confirmado");
    expect(cycleDecision("confirmado")).toBe("excluido");
    expect(cycleDecision("excluido")).toBe("pendiente");
  });

  it("tres clicks vuelven al inicio", () => {
    expect(cycleDecision(cycleDecision(cycleDecision("pendiente")))).toBe("pendiente");
  });
});

describe("summarizeTriage", () => {
  it("cuenta y deduce los pendientes", () => {
    const resumen = summarizeTriage(
      doc({ a: { decision: "confirmado" }, b: { decision: "excluido" } }), 5);

    expect(resumen).toEqual({ confirmado: 1, excluido: 1, pendiente: 3 });
  });

  it("nunca da pendientes negativos", () => {
    // Si el diff encogió entre corridas, un negativo sería mentira.
    const resumen = summarizeTriage(
      doc({ a: { decision: "confirmado" }, b: { decision: "confirmado" } }), 1);

    expect(resumen.pendiente).toBe(0);
  });

  it("sin triage, todo pendiente", () => {
    expect(summarizeTriage(null, 4))
      .toEqual({ confirmado: 0, excluido: 0, pendiente: 4 });
  });
});

describe("presentación", () => {
  it("cada decisión tiene su clase de badge", () => {
    expect(decisionBadgeClass("confirmado")).toBe("triageConfirmado");
    expect(decisionBadgeClass("excluido")).toBe("triageExcluido");
    expect(decisionBadgeClass("pendiente")).toBe("triagePendiente");
  });

  it("las etiquetas se distinguen de un vistazo", () => {
    const etiquetas = (["confirmado", "excluido", "pendiente"] as const).map(decisionLabel);
    expect(new Set(etiquetas).size).toBe(3);
  });

  it("la ayuda dice la CONSECUENCIA, no solo el nombre", () => {
    expect(decisionHelp("confirmado")).toContain("script");
    expect(decisionHelp("excluido")).toContain("NO se migra");
    // Lo más importante: sin decidir, igual se migra. El default es migrar todo.
    expect(decisionHelp("pendiente")).toContain("se migra igual");
  });
});

describe("canTriage", () => {
  it("solo un diff terminado y con la capacidad encendida", () => {
    expect(canTriage("done", true)).toBe(true);
    expect(canTriage("running", true)).toBe(false);
    expect(canTriage("done", false)).toBe(false);
    expect(canTriage(null, null)).toBe(false);
  });
});

describe("hasAnyDecision", () => {
  it("detecta si hay algo curado", () => {
    expect(hasAnyDecision(null)).toBe(false);
    expect(hasAnyDecision(doc({}))).toBe(false);
    expect(hasAnyDecision(doc({ a: { decision: "confirmado" } }))).toBe(true);
  });
});
