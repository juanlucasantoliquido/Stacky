/** Plan 171 F5 — Helpers puros de telemetría operativa. */
import { describe, expect, it } from "vitest";

import { barPercents, breachLabel, severityTone, traceRows } from "../opsTelemetry";
import type { OpsBreach, RunTrace } from "../../lib/opsTelemetryTypes";

const breach = (over: Partial<OpsBreach> = {}): OpsBreach => ({
  rule_id: "R-O1",
  severity: "warn",
  agent_type: "developer",
  runtime: "codex_cli",
  message: "Tasa de error alta: 4/5 corridas en la ventana",
  observed: 0.8,
  reference: null,
  threshold: 0.3,
  ...over,
});

const trace = (over: Partial<RunTrace> = {}): RunTrace => ({
  execution_id: 1,
  agent_type: "developer",
  status: "completed",
  runtime: "codex_cli",
  model: "claude-sonnet-5",
  ticket: null,
  phases: [],
  duration_seconds: 90,
  cost: {
    cost_usd: 0.18,
    cost_kind: "estimated",
    tokens_in: 1000,
    tokens_out: 500,
    cache_read_tokens: null,
    cache_savings_usd: null,
  },
  telemetry_source: "harness_telemetry",
  session_id: "s-1",
  num_turns: 3,
  agent_name: null,
  prompt_sha: null,
  stalled: false,
  incident: null,
  sin_dato: [],
  ...over,
});

describe("severityTone", () => {
  it("critical → danger", () => {
    expect(severityTone("critical")).toBe("danger");
  });
  it("warn → warning", () => {
    expect(severityTone("warn")).toBe("warning");
  });
});

describe("breachLabel", () => {
  it("usa la celda cuando hay agente/runtime", () => {
    expect(breachLabel(breach())).toBe(
      "R-O1 · developer/codex_cli · Tasa de error alta: 4/5 corridas en la ventana",
    );
  });

  it("usa 'global' cuando la regla no tiene ámbito", () => {
    const label = breachLabel(
      breach({ rule_id: "R-O4", agent_type: null, runtime: null, message: "2 corrida(s)" }),
    );
    expect(label).toBe("R-O4 · global · 2 corrida(s)");
  });
});

describe("barPercents", () => {
  it("normaliza contra el máximo", () => {
    expect(barPercents([5, 10, 0])).toEqual([50, 100, 0]);
  });
  it("máximo 0 → todos 0 (nunca divide por cero)", () => {
    expect(barPercents([0, 0])).toEqual([0, 0]);
  });
  it("lista vacía → lista vacía", () => {
    expect(barPercents([])).toEqual([]);
  });
});

describe("traceRows", () => {
  it("arma las filas de una traza completa", () => {
    const rows = traceRows(trace());
    const byLabel = Object.fromEntries(rows.map((r) => [r.label, r.value]));

    expect(rows).toHaveLength(10);
    expect(byLabel["Estado"]).toBe("completed");
    expect(byLabel["Modelo"]).toBe("claude-sonnet-5");
    expect(byLabel["Costo"]).toContain("(estimated)");
    expect(byLabel["Duración"]).not.toBe("—");
    expect(byLabel["Turnos"]).toBe("3");
  });

  it("declara la degradación en vez de inventar", () => {
    const rows = traceRows(
      trace({
        model: null,
        duration_seconds: null,
        session_id: null,
        num_turns: null,
        cost: {
          cost_usd: null,
          cost_kind: "unknown",
          tokens_in: null,
          tokens_out: null,
          cache_read_tokens: null,
          cache_savings_usd: null,
        },
      }),
    );
    const byLabel = Object.fromEntries(rows.map((r) => [r.label, r.value]));

    expect(byLabel["Modelo"]).toBe("sin dato");
    expect(byLabel["Duración"]).toBe("—");
    expect(byLabel["Costo"]).toBe("—");
    expect(byLabel["Tokens (in/out)"]).toBe("—");
    expect(byLabel["Sesión"]).toBe("—");
    expect(byLabel["Turnos"]).toBe("—");
  });
});
