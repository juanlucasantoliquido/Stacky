// Plan 213 F5 — Lógica del panel de supuestos.
import { describe, it, expect } from "vitest";
import {
  badgeLabel,
  groupByImpact,
  hasSomethingToShow,
  isUnbased,
  orderedForDisplay,
  overloadWarning,
  pendingHighCount,
  readAssumptions,
  statusLabel,
  withIndices,
  type AssumptionDTO,
} from "../assumptionsModel";

function sup(over: Partial<AssumptionDTO> = {}): AssumptionDTO {
  return { text: "algo", basis: "doc M12", impact: "medium", status: "pending", ...over };
}

describe("readAssumptions", () => {
  it("sin metadata devuelve null", () => {
    expect(readAssumptions(null)).toBeNull();
    expect(readAssumptions({})).toBeNull();
  });

  it("una metadata corrupta no rompe el panel", () => {
    expect(readAssumptions({ assumptions: "no soy objeto" })).toBeNull();
    expect(readAssumptions({ assumptions: [1, 2] })).toBeNull();
  });

  it("lee el bloque cuando está", () => {
    expect(readAssumptions({ assumptions: { total: 2 } })?.total).toBe(2);
  });
});

describe("groupByImpact", () => {
  it("agrupa por impacto", () => {
    const grupos = groupByImpact([
      sup({ impact: "high" }), sup({ impact: "low" }), sup({ impact: "high" }),
    ]);

    expect(grupos.high).toHaveLength(2);
    expect(grupos.low).toHaveLength(1);
    expect(grupos.medium).toHaveLength(0);
  });

  it("un impacto desconocido cae en medium, no se pierde", () => {
    const grupos = groupByImpact([sup({ impact: "altísimo" as never })]);

    expect(grupos.medium).toHaveLength(1);
  });

  it("sin items no explota", () => {
    expect(groupByImpact(null).high).toEqual([]);
  });
});

describe("pendingHighCount", () => {
  it("cuenta solo los altos sin decidir", () => {
    expect(pendingHighCount([
      sup({ impact: "high" }),
      sup({ impact: "high", status: "confirmed" }),
      sup({ impact: "medium" }),
    ])).toBe(1);
  });

  it("un item sin status cuenta como pendiente", () => {
    expect(pendingHighCount([{ text: "x", impact: "high" }])).toBe(1);
  });
});

describe("badgeLabel", () => {
  it("sin supuestos no dice nada", () => {
    expect(badgeLabel(null)).toBe("");
    expect(badgeLabel({ total: 0 })).toBe("");
  });

  it("uno solo va en singular", () => {
    expect(badgeLabel({ total: 1, items: [sup({ impact: "medium" })] }))
      .toBe("1 supuesto");
  });

  it("destaca cuántos altos faltan confirmar", () => {
    expect(badgeLabel({
      total: 3,
      items: [sup({ impact: "high" }), sup({ impact: "high" }), sup()],
    })).toBe("3 supuestos · 2 sin confirmar");
  });

  it("todo confirmado no muestra el contador de pendientes", () => {
    expect(badgeLabel({
      total: 2,
      items: [sup({ impact: "high", status: "confirmed" }), sup()],
    })).toBe("2 supuestos");
  });
});

describe("isUnbased", () => {
  it("sin base es señal de posible invención", () => {
    expect(isUnbased(sup({ basis: "" }))).toBe(true);
    expect(isUnbased(sup({ basis: "   " }))).toBe(true);
    expect(isUnbased({ text: "x", impact: "high" })).toBe(true);
    expect(isUnbased(sup({ basis: "doc M12" }))).toBe(false);
  });
});

describe("índices", () => {
  it("withIndices conserva la posición real", () => {
    const con = withIndices([sup({ text: "a" }), sup({ text: "b" })]);

    expect(con.map((c) => c.index)).toEqual([0, 1]);
  });

  it("orderedForDisplay reordena pero NO pierde el índice original", () => {
    // Crítico: el PATCH indexa por posición en `items`. Si la vista reordena y
    // se manda el índice de la vista, se confirmaría otro supuesto.
    const orden = orderedForDisplay([
      sup({ text: "bajo", impact: "low" }),
      sup({ text: "alto", impact: "high" }),
    ]);

    expect(orden.map((o) => o.item.text)).toEqual(["alto", "bajo"]);
    expect(orden.map((o) => o.index)).toEqual([1, 0]);
  });
});

describe("avisos", () => {
  it("overload avisa", () => {
    expect(overloadWarning({ overload: true })).toContain("mayormente supuesto");
    expect(overloadWarning({ overload: false })).toBeNull();
    expect(overloadWarning(null)).toBeNull();
  });

  it("statusLabel traduce los tres estados", () => {
    expect(statusLabel("confirmed")).toBe("Confirmado");
    expect(statusLabel("corrected")).toBe("Corregido");
    expect(statusLabel("pending")).toBe("Sin confirmar");
    expect(statusLabel(undefined)).toBe("Sin confirmar");
  });
});

describe("hasSomethingToShow", () => {
  it("sin nada, el panel no se renderiza (cero ruido)", () => {
    expect(hasSomethingToShow(null)).toBe(false);
    expect(hasSomethingToShow({ items: [], pending: [] })).toBe(false);
  });

  it("un pendiente solo ya amerita mostrarlo", () => {
    expect(hasSomethingToShow({ items: [], pending: [{ text: "tope" }] })).toBe(true);
  });

  it("con supuestos se muestra", () => {
    expect(hasSomethingToShow({ items: [sup()] })).toBe(true);
  });
});
