import { describe, expect, it } from "vitest";
import {
  areaPath,
  costKindLabel,
  costKindTokenVar,
  filterRows,
  formatPct,
  formatTokens,
  formatUsd,
  linePath,
  niceTicks,
  scaleLinear,
  sortRows,
  toCsv,
} from "../costCenter.logic";
import type { CostKind, TopRun } from "../costCenterTypes";

function makeRun(overrides: Partial<TopRun>): TopRun {
  return {
    execution_id: 1,
    ticket_id: 10,
    agent_type: "developer",
    runtime: "claude_code_cli",
    model: "claude-sonnet-5",
    cost_usd: 1.5,
    cost_kind: "reported",
    started_at: "2026-07-15T00:00:00",
    ...overrides,
  };
}

describe("costCenter.logic — formatters", () => {
  it("formatUsd: null -> n/d", () => {
    expect(formatUsd(null)).toBe("n/d");
    expect(formatUsd(0.42)).toBe("$0.42");
  });

  it("formatTokens: 12345 -> 12.3k", () => {
    expect(formatTokens(12345)).toBe("12.3k");
    expect(formatTokens(null)).toBe("n/d");
    expect(formatTokens(1_234_567)).toBe("1.2M");
    expect(formatTokens(500)).toBe("500");
  });

  it("formatPct", () => {
    expect(formatPct(0.23)).toBe("23%");
    expect(formatPct(0)).toBe("0%");
  });
});

describe("costCenter.logic — sortRows", () => {
  it("estable y respeta la dirección", () => {
    const rows = [
      makeRun({ execution_id: 1, cost_usd: 5 }),
      makeRun({ execution_id: 2, cost_usd: 1 }),
      makeRun({ execution_id: 3, cost_usd: 5 }),  // empate con execution_id 1 -> debe conservar orden relativo
      makeRun({ execution_id: 4, cost_usd: null }),
    ];
    const asc = sortRows(rows, "cost_usd", "asc");
    // null ("n/d") siempre al final, sin importar la dirección.
    expect(asc.map((r) => r.execution_id)).toEqual([2, 1, 3, 4]);

    const desc = sortRows(rows, "cost_usd", "desc");
    expect(desc.map((r) => r.execution_id)).toEqual([1, 3, 2, 4]);

    // No muta el array original.
    expect(rows.map((r) => r.execution_id)).toEqual([1, 2, 3, 4]);
  });
});

describe("costCenter.logic — filterRows", () => {
  it("filtra por runtime+cost_kind combinados", () => {
    const rows = [
      makeRun({ execution_id: 1, runtime: "claude_code_cli", cost_kind: "reported" }),
      makeRun({ execution_id: 2, runtime: "codex_cli", cost_kind: "estimated" }),
      makeRun({ execution_id: 3, runtime: "claude_code_cli", cost_kind: "estimated" }),
      makeRun({ execution_id: 4, runtime: "github_copilot", cost_kind: "nominal" }),
    ];
    const out = filterRows(rows, { runtime: "claude_code_cli", cost_kind: "estimated" });
    expect(out.map((r) => r.execution_id)).toEqual([3]);

    const onlyRuntime = filterRows(rows, { runtime: "claude_code_cli" });
    expect(onlyRuntime.map((r) => r.execution_id)).toEqual([1, 3]);
  });
});

describe("costCenter.logic — toCsv", () => {
  it("escapa comas y comillas", () => {
    const rows = [
      makeRun({ execution_id: 1, agent_type: "dev,eloper", model: 'model "x"' }),
    ];
    const csv = toCsv(rows);
    const lines = csv.split("\n");
    expect(lines[0]).toBe("execution_id,ticket_id,agent_type,runtime,model,cost_usd,cost_kind,started_at");
    expect(lines[1]).toContain('"dev,eloper"');
    expect(lines[1]).toContain('"model ""x"""');
  });
});

describe("costCenter.logic — costKind helpers", () => {
  it("costKindLabel cubre los 4 valores", () => {
    expect(costKindLabel("reported")).toBe("Reportado");
    expect(costKindLabel("estimated")).toBe("Estimado");
    expect(costKindLabel("nominal")).toBe("Nominal (suscripción)");
    expect(costKindLabel("unknown")).toBe("n/d");
  });

  it("costKindTokenVar nunca devuelve string con '#' (gate anti-drift color)", () => {
    const kinds: CostKind[] = ["reported", "estimated", "nominal", "unknown"];
    for (const k of kinds) {
      const v = costKindTokenVar(k);
      expect(v).not.toContain("#");
      expect(v.startsWith("var(--")).toBe(true);
    }
  });
});

describe("costCenter.logic — math de SVG", () => {
  it("linePath genera M/L correctos", () => {
    expect(linePath([{ x: 0, y: 0 }, { x: 10, y: 5 }, { x: 20, y: 2 }])).toBe(
      "M 0 0 L 10 5 L 20 2",
    );
    expect(linePath([])).toBe("");
  });

  it("areaPath cierra al baseline", () => {
    const d = areaPath([{ x: 0, y: 10 }, { x: 10, y: 0 }], 20);
    expect(d).toBe("M 0 10 L 10 0 L 10 20 L 0 20 Z");
  });

  it("scaleLinear mapea extremos", () => {
    const scale = scaleLinear([0, 10], [0, 100]);
    expect(scale(0)).toBe(0);
    expect(scale(10)).toBe(100);
    expect(scale(5)).toBe(50);

    const constScale = scaleLinear([5, 5], [0, 100]);
    expect(constScale(5)).toBe(0);
  });

  it("niceTicks devuelve N ticks ordenados", () => {
    const ticks = niceTicks(0, 100, 5);
    expect(ticks).toHaveLength(5);
    expect(ticks).toEqual([0, 25, 50, 75, 100]);
    for (let i = 1; i < ticks.length; i++) {
      expect(ticks[i]).toBeGreaterThanOrEqual(ticks[i - 1]);
    }
  });
});
