import { describe, it, expect } from "vitest";
import { previousRunDelta } from "../runHistory";
import type { CompareRun, DiffSummary } from "../dbcompareTypes";

function summary(score: number): DiffSummary {
  return {
    by_severity: { info: 0, warn: 0, danger: 0 },
    by_action: { added: 0, removed: 0, changed: 0 },
    by_object_type: { table: 0, view: 0, sequence: 0 },
    objects_total: 10,
    objects_unchanged: 9,
    parity_score: score,
  };
}

function run(partial: Partial<CompareRun>): CompareRun {
  return {
    run_id: "run_x",
    source_alias: "DEV",
    target_alias: "PROD",
    engine: "sqlserver",
    mode: "fresh",
    status: "done",
    phase: "done",
    started_at: "2026-07-14T09:59:00Z",
    finished_at: "2026-07-14T10:00:00Z",
    duration_ms: 1000,
    source_snapshot_id: "s1",
    target_snapshot_id: "s2",
    summary: summary(92.4),
    diff: null,
    error: null,
    ...partial,
  };
}

describe("Plan 124 F6 [ADICIÓN ARQUITECTO] — runHistory (pure)", () => {
  it("sin corridas previas -> null", () => {
    const current = run({ run_id: "run_current" });
    expect(previousRunDelta(current, [])).toBeNull();
  });

  it("una previa del mismo par en orden inverso de alias -> encontrada", () => {
    const current = run({ run_id: "run_current", source_alias: "DEV", target_alias: "PROD", summary: summary(92.4) });
    const previous = run({
      run_id: "run_prev",
      source_alias: "PROD", // orden invertido respecto de current
      target_alias: "DEV",
      finished_at: "2026-07-12T10:00:00Z",
      summary: summary(89.3),
    });
    const out = previousRunDelta(current, [previous]);
    expect(out).toEqual({
      previousRunId: "run_prev",
      previousScore: 89.3,
      deltaPoints: 3.1,
      previousFinishedAt: "2026-07-12T10:00:00Z",
    });
  });

  it("varias previas -> se elige la de finished_at mas reciente", () => {
    const current = run({ run_id: "run_current", summary: summary(95) });
    const older = run({ run_id: "run_older", finished_at: "2026-07-10T10:00:00Z", summary: summary(80) });
    const newer = run({ run_id: "run_newer", finished_at: "2026-07-13T10:00:00Z", summary: summary(90) });
    const out = previousRunDelta(current, [older, newer]);
    expect(out?.previousRunId).toBe("run_newer");
    expect(out?.deltaPoints).toBe(5);
  });

  it("delta negativo calculado exacto", () => {
    const current = run({ run_id: "run_current", summary: summary(80) });
    const previous = run({ run_id: "run_prev", finished_at: "2026-07-12T10:00:00Z", summary: summary(95) });
    const out = previousRunDelta(current, [previous]);
    expect(out?.deltaPoints).toBe(-15);
  });

  it("ignora corridas de otro par y corridas no done", () => {
    const current = run({ run_id: "run_current", source_alias: "DEV", target_alias: "PROD" });
    const otherPair = run({ run_id: "run_other", source_alias: "DEV", target_alias: "TEST", finished_at: "2026-07-13T10:00:00Z" });
    const notDone = run({ run_id: "run_running", status: "running", finished_at: null });
    expect(previousRunDelta(current, [otherPair, notDone])).toBeNull();
  });
});
