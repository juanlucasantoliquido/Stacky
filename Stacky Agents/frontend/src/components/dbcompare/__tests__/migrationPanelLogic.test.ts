// Plan 157 F6 — tests puros del Panel de Migración (vitest).
import { describe, it, expect } from "vitest";
import { selectableRuns, zipUrlFor } from "../migrationPanelLogic";
import type { CompareRun } from "../dbcompareTypes";

const mkRun = (id: string, status: CompareRun["status"]): CompareRun => ({
  run_id: id,
  source_alias: "A",
  target_alias: "B",
  engine: "sqlserver",
  mode: "fresh",
  status,
  phase: "done",
  started_at: "",
  finished_at: null,
  duration_ms: 0,
  source_snapshot_id: null,
  target_snapshot_id: null,
  summary: null,
  diff: null,
  error: null,
});

describe("selectableRuns", () => {
  it("filtra sólo las corridas done", () => {
    const runs = [mkRun("1", "done"), mkRun("2", "running"), mkRun("3", "error"), mkRun("4", "done")];
    expect(selectableRuns(runs).map((r) => r.run_id)).toEqual(["1", "4"]);
  });
  it("lista vacía → vacío", () => {
    expect(selectableRuns([])).toEqual([]);
  });
});

describe("zipUrlFor", () => {
  it("arma la URL del bundle", () => {
    expect(zipUrlFor("run_X")).toBe("/api/db-compare/runs/run_X/scripts.zip");
  });
  it("encodea el run_id", () => {
    expect(zipUrlFor("a b")).toBe("/api/db-compare/runs/a%20b/scripts.zip");
  });
  it("respeta un apiBase provisto", () => {
    expect(zipUrlFor("r", "http://x")).toBe("http://x/api/db-compare/runs/r/scripts.zip");
  });
});
