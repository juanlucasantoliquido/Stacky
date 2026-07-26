// Plan 176 F5 — Lógica del panel de precondiciones.
import { describe, it, expect } from "vitest";
import {
  canEvaluate,
  headlineFor,
  sortForDisplay,
  statusClass,
  statusLabel,
  statusOf,
  summarizeGates,
  type Gate,
  type GateResult,
} from "../gatesLogic";

function gate(over: Partial<Gate> = {}): Gate {
  return {
    gate_id: "g001_null_count_dbo.T",
    item_key: "table:dbo.T",
    kind: "null_count",
    description: "Filas con RUT en NULL",
    sql: "SELECT COUNT(*) …",
    check: "expect_zero",
    target_alias: "TEST",
    ...over,
  };
}

function res(status: GateResult["status"], value = 0): GateResult {
  return { status, value, detail: "", checked_at: "2026-07-26T00:00:00Z" };
}

describe("statusOf", () => {
  it("sin resultado NO es 'pasó' ni 'falló'", () => {
    expect(statusOf(null, "g1")).toBe("sin_correr");
    expect(statusOf({}, "g1")).toBe("sin_correr");
  });

  it("lee el resultado guardado", () => {
    expect(statusOf({ g1: res("fail", 3) }, "g1")).toBe("fail");
  });
});

describe("etiquetas", () => {
  it("cada estado se distingue de un vistazo", () => {
    const todos = (["pass", "fail", "error", "info", "sin_correr"] as const)
      .map(statusLabel);
    expect(new Set(todos).size).toBe(5);
  });

  it("fail dice que bloquea", () => {
    expect(statusLabel("fail")).toContain("Bloquea");
  });

  it("cada estado tiene su clase", () => {
    expect(statusClass("pass")).toBe("gatePass");
    expect(statusClass("fail")).toBe("gateFail");
    expect(statusClass("sin_correr")).toBe("gatePending");
  });
});

describe("summarizeGates", () => {
  it("cuenta por estado", () => {
    const gates = [
      gate({ gate_id: "a" }), gate({ gate_id: "b" }),
      gate({ gate_id: "c" }), gate({ gate_id: "d" }),
    ];
    const r = { a: res("pass"), b: res("fail", 2), c: res("error") };

    expect(summarizeGates(gates, r))
      .toEqual({ total: 4, pass: 1, fail: 1, error: 1, sinCorrer: 1 });
  });

  it("info no cuenta como veredicto: no hay valor correcto", () => {
    const s = summarizeGates([gate({ gate_id: "a" })], { a: res("info", 120) });

    expect(s.pass).toBe(0);
    expect(s.fail).toBe(0);
    expect(s.sinCorrer).toBe(0);
  });

  it("sin gates da cero", () => {
    expect(summarizeGates(null, null).total).toBe(0);
  });
});

describe("headlineFor", () => {
  it("sin gates lo dice y no alarma", () => {
    expect(headlineFor([], {})).toContain("no requiere");
  });

  it("un fail manda sobre todo lo demás", () => {
    const gates = [gate({ gate_id: "a" }), gate({ gate_id: "b" })];

    expect(headlineFor(gates, { a: res("pass"), b: res("fail", 5) }))
      .toContain("bloquea la migración");
  });

  it("singular y plural", () => {
    const g2 = [gate({ gate_id: "a" }), gate({ gate_id: "b" })];
    expect(headlineFor([gate({ gate_id: "a" })], { a: res("fail", 1) }))
      .toBe("1 precondición bloquea la migración.");
    expect(headlineFor(g2, { a: res("fail"), b: res("fail") }))
      .toBe("2 precondiciones bloquean la migración.");
  });

  it("nada corrido no se confunde con todo verde", () => {
    expect(headlineFor([gate()], {})).toContain("sin verificar");
  });

  it("todo verde lo dice", () => {
    expect(headlineFor([gate({ gate_id: "a" })], { a: res("pass") }))
      .toContain("verde");
  });

  it("un error no se presenta como verde", () => {
    const gates = [gate({ gate_id: "a" }), gate({ gate_id: "b" })];

    expect(headlineFor(gates, { a: res("pass"), b: res("error") }))
      .toContain("no se pudieron verificar");
  });
});

describe("sortForDisplay", () => {
  it("los bloqueantes primero", () => {
    const gates = [
      gate({ gate_id: "a" }), gate({ gate_id: "b" }), gate({ gate_id: "c" }),
    ];
    const r = { a: res("pass"), b: res("fail"), c: res("error") };

    expect(sortForDisplay(gates, r).map((g) => g.gate_id)).toEqual(["b", "c", "a"]);
  });

  it("a igual estado, por id (determinista)", () => {
    const gates = [gate({ gate_id: "z" }), gate({ gate_id: "a" })];

    expect(sortForDisplay(gates, {}).map((g) => g.gate_id)).toEqual(["a", "z"]);
  });

  it("no muta el original", () => {
    const gates = [gate({ gate_id: "z" }), gate({ gate_id: "a" })];
    sortForDisplay(gates, {});

    expect(gates[0].gate_id).toBe("z");
  });
});

describe("canEvaluate", () => {
  it("hace falta diff terminado, flag y al menos una gate", () => {
    expect(canEvaluate("done", true, [gate()])).toBe(true);
    expect(canEvaluate("running", true, [gate()])).toBe(false);
    expect(canEvaluate("done", false, [gate()])).toBe(false);
    expect(canEvaluate("done", true, [])).toBe(false);
  });
});
