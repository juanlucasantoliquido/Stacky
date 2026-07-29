// Plan 266 F0.1 — Reproducción del crash REAL reportado por el operador:
// "Cannot read properties of undefined (reading 'danger')" en radarLogic.ts:60.
//
// Ojo con cuál falla y cómo (C14): los casos 1, 2 y 3 LANZAN hoy; el caso 4 NO
// lanza — falla por ASERCIÓN (recibe undefined donde espera 0) — y el caso 5
// pasa en verde ya hoy (control positivo). Ver la tabla del plan §F0.1.
import { describe, it, expect } from "vitest";
import { trendSeries } from "../radarLogic";
import { severityCounters, actionCounters } from "../svgMath";
import type { CompareRun, SchemaDiff } from "../dbcompareTypes";

function runFixture(over: Record<string, unknown>): CompareRun {
  return {
    run_id: "run_x", source_alias: "DEV", target_alias: "QA", engine: "sqlserver",
    mode: "fresh", status: "done", phase: "done",
    started_at: "2026-07-27T10:00:00Z", finished_at: "2026-07-27T10:01:00Z",
    duration_ms: 60000, source_snapshot_id: "s1", target_snapshot_id: "s2",
    summary: null, diff: null, error: null,
    ...over,
  } as unknown as CompareRun;
}

describe("Plan 266 F0.1 — reproducción del crash de summary a medio formar", () => {
  it("trendSeries no lanza con summary sin by_severity", () => {
    const runs = [runFixture({ summary: { parity_score: 91.7 } })];
    expect(() => trendSeries(runs, "DEV", "QA")).not.toThrow();
  });

  it("severityCounters no lanza con summary sin by_severity", () => {
    const diff = { summary: { parity_score: 91.7 } } as unknown as SchemaDiff;
    expect(() => severityCounters(diff)).not.toThrow();
  });

  it("actionCounters no lanza con summary sin by_action", () => {
    const diff = { summary: { parity_score: 91.7 } } as unknown as SchemaDiff;
    expect(() => actionCounters(diff)).not.toThrow();
  });

  it("severityCounters tolera by_severity vacío", () => {
    // La forma que emite api/db_compare_watch.py:153 -- (meta["summary"] or {}).get("by_severity") or {}
    const diff = { summary: { by_severity: {} } } as unknown as SchemaDiff;
    const counters = severityCounters(diff);
    for (const c of counters) expect(c.count).toBe(0);
  });

  it("trendSeries sigue devolviendo los valores reales cuando el summary está completo", () => {
    // Control positivo: sin esto el fix podría devolver ceros siempre y el test seguiría verde.
    const runs = [
      runFixture({
        summary: { by_severity: { info: 1, warn: 2, danger: 3 } },
      }),
    ];
    const points = trendSeries(runs, "DEV", "QA");
    expect(points).toEqual([{ t: "2026-07-27T10:01:00Z", danger: 3, warn: 2, info: 1 }]);
  });
});
