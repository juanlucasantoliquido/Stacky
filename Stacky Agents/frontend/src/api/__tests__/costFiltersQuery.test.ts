// Plan 199 F4 — costFiltersToQuery: los filtros nuevos (multi-runtime, multi-modelo,
// rango de costo) viajan al backend; `source` NO viaja (lo consume la UI en F6).
import { describe, it, expect, vi } from "vitest";

vi.mock("../../services/connectionMonitor", () => ({
  GATEWAY_DOWN_STATUSES: new Set([502, 503, 504]),
  reportConnectionSuccess: () => {},
  reportConnectionFailure: () => {},
}));

import { costFiltersToQuery } from "../endpoints";

describe("costFiltersToQuery — filtros heredados del 142", () => {
  it("sin params devuelve una query vacía", () => {
    expect(costFiltersToQuery().toString()).toBe("");
    expect(costFiltersToQuery(undefined).toString()).toBe("");
  });

  it("preserva los filtros previos del 142 (backward-compatible)", () => {
    const p = costFiltersToQuery({
      days: 30,
      runtime: "codex_cli",
      model: "gpt-5",
      agent_type: "developer",
      ticket_id: 123,
      project: "Pacifico",
      status: "completed,failed",
      cost_kind: "billable",
      top_n: 10,
    });
    expect(p.get("days")).toBe("30");
    expect(p.get("runtime")).toBe("codex_cli");
    expect(p.get("model")).toBe("gpt-5");
    expect(p.get("agent_type")).toBe("developer");
    expect(p.get("ticket_id")).toBe("123");
    expect(p.get("project")).toBe("Pacifico");
    expect(p.get("status")).toBe("completed,failed");
    expect(p.get("cost_kind")).toBe("billable");
    expect(p.get("top_n")).toBe("10");
  });
});

describe("costFiltersToQuery — Plan 199 F4 (filtros nuevos)", () => {
  it("serializa runtimes y models como csv", () => {
    const p = costFiltersToQuery({
      runtimes: "codex_cli,claude_code_cli",
      models: "gpt-5,opus-4",
    });
    expect(p.get("runtimes")).toBe("codex_cli,claude_code_cli");
    expect(p.get("models")).toBe("gpt-5,opus-4");
  });

  it("serializa el rango de costo min/max", () => {
    const p = costFiltersToQuery({ min_cost: 0.5, max_cost: 12.25 });
    expect(p.get("min_cost")).toBe("0.5");
    expect(p.get("max_cost")).toBe("12.25");
  });

  it("min_cost=0 SI viaja (0 es un umbral valido, no ausencia)", () => {
    // Guard contra el bug clasico `if (params.min_cost)`, que descarta el 0.
    const p = costFiltersToQuery({ min_cost: 0 });
    expect(p.get("min_cost")).toBe("0");
  });

  it("`source` NO viaja al backend del 142 (lo consume la UI)", () => {
    const p = costFiltersToQuery({ source: "harvest", days: 7 });
    expect(p.get("source")).toBeNull();
    expect(p.get("days")).toBe("7");
  });

  it("los filtros nuevos ausentes no agregan claves vacias", () => {
    const p = costFiltersToQuery({ days: 30 });
    expect(p.has("runtimes")).toBe(false);
    expect(p.has("models")).toBe(false);
    expect(p.has("min_cost")).toBe(false);
    expect(p.has("max_cost")).toBe(false);
  });
});
