import { describe, it, expect } from "vitest";
import { PHASE_ORDER, phaseState } from "../runProgressLogic";
import type { CompareRun } from "../dbcompareTypes";

function run(phase: CompareRun["phase"], status: CompareRun["status"] = "running"): CompareRun {
  return {
    run_id: "run_x",
    source_alias: "a",
    target_alias: "b",
    engine: "sqlserver",
    mode: "fresh",
    status,
    phase,
    started_at: "2026-07-12T14:00:00Z",
    finished_at: null,
    duration_ms: 0,
    source_snapshot_id: null,
    target_snapshot_id: null,
    summary: null,
    diff: null,
    error: null,
  };
}

describe("Plan 124 F2 — runProgressLogic (pure)", () => {
  it("PHASE_ORDER es la secuencia exacta", () => {
    expect(PHASE_ORDER).toEqual(["queued", "snapshot_source", "snapshot_target", "diff", "done"]);
  });

  it("fase actual = queued, se pregunta por queued -> active", () => {
    expect(phaseState(run("queued"), "queued")).toBe("active");
  });

  it("fase actual = queued, se pregunta por snapshot_source -> pending", () => {
    expect(phaseState(run("queued"), "snapshot_source")).toBe("pending");
  });

  it("fase actual = snapshot_target, se pregunta por snapshot_source -> done", () => {
    expect(phaseState(run("snapshot_target"), "snapshot_source")).toBe("done");
  });

  it("fase actual = diff, se pregunta por diff -> active", () => {
    expect(phaseState(run("diff"), "diff")).toBe("active");
  });

  it("run terminado (phase=done), cualquier fase -> done", () => {
    expect(phaseState(run("done", "done"), "queued")).toBe("done");
    expect(phaseState(run("done", "done"), "diff")).toBe("done");
  });
});
