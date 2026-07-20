// Plan 178 F7 — Lógica pura del radar (vitest por archivo, sin RTL/jsdom).
import { describe, expect, it } from "vitest";

import type { CompareRun } from "./dbcompareTypes";
import type { RadarCell } from "./radarTypes";
import {
  buildMatrix,
  cellStateClass,
  formatCellTitle,
  relativeFromIso,
  sparklinePath,
  trendSeries,
} from "./radarLogic";

function cell(source: string, target: string, sev: { info?: number; warn?: number; danger?: number }): RadarCell {
  const by_severity = { info: sev.info || 0, warn: sev.warn || 0, danger: sev.danger || 0 };
  const state = by_severity.danger > 0 ? "red" : by_severity.warn + by_severity.info > 0 ? "amber" : "green";
  return {
    source_alias: source,
    target_alias: target,
    state,
    by_severity,
    parity_score: 98.5,
    run_id: `run_${source}_${target}`,
    finished_at: "2026-07-18T12:00:00Z",
    initiated_by: "watch",
    watched: true,
  };
}

function run(source: string, target: string, finished: string, sev: { info?: number; warn?: number; danger?: number }, status: "done" | "running" = "done"): CompareRun {
  return {
    run_id: `run_${finished}`,
    source_alias: source,
    target_alias: target,
    engine: "mssql",
    mode: "fresh",
    status,
    phase: "done",
    started_at: finished,
    finished_at: finished,
    duration_ms: 10,
    source_snapshot_id: "s",
    target_snapshot_id: "t",
    summary: {
      by_severity: { info: sev.info || 0, warn: sev.warn || 0, danger: sev.danger || 0 },
      by_action: { added: 0, removed: 0, changed: 0 },
      by_object_type: { table: 0, view: 0, sequence: 0 },
      objects_total: 1,
      objects_unchanged: 0,
      parity_score: 90,
    },
    diff: null,
    error: null,
  };
}

describe("buildMatrix", () => {
  it("3 ambientes + 2 cells → matriz 3×3 con diagonal null en posición correcta", () => {
    const envs = [{ alias: "DEV" }, { alias: "TEST" }, { alias: "PROD" }];
    const cells = [cell("DEV", "TEST", { warn: 2 }), cell("TEST", "PROD", { danger: 1 })];
    const m = buildMatrix(envs, cells);
    expect(m.length).toBe(3);
    expect(m[0][0]).toBeNull(); // diagonal
    expect(m[1][1]).toBeNull();
    expect(m[0][1]?.source_alias).toBe("DEV"); // [DEV][TEST]
    expect(m[0][1]?.target_alias).toBe("TEST");
    expect(m[1][2]?.run_id).toBe("run_TEST_PROD"); // [TEST][PROD]
    expect(m[0][2]).toBeNull(); // sin datos DEV→PROD
  });
});

describe("cellStateClass", () => {
  it("clasifica por severidad", () => {
    expect(cellStateClass(cell("A", "B", { danger: 1 }))).toBe("red");
    expect(cellStateClass(cell("A", "B", { warn: 1 }))).toBe("amber");
    expect(cellStateClass(cell("A", "B", {}))).toBe("green");
    expect(cellStateClass(null)).toBe("gray");
  });
});

describe("trendSeries", () => {
  it("filtra el par en ambas direcciones, ordena ascendente, ignora no-done", () => {
    const runs = [
      run("TEST", "DEV", "2026-07-18T10:00:00Z", { warn: 3 }),
      run("DEV", "TEST", "2026-07-18T09:00:00Z", { warn: 1 }),
      run("DEV", "PROD", "2026-07-18T11:00:00Z", { danger: 1 }),
      run("DEV", "TEST", "2026-07-18T12:00:00Z", { danger: 2 }, "running"),
    ];
    const series = trendSeries(runs, "DEV", "TEST");
    expect(series.map((p) => p.t)).toEqual(["2026-07-18T09:00:00Z", "2026-07-18T10:00:00Z"]);
    expect(series[0].warn).toBe(1);
    expect(series[1].warn).toBe(3);
  });
});

describe("sparklinePath", () => {
  it("0 puntos → cadena vacía", () => {
    expect(sparklinePath([], 100, 24)).toBe("");
  });
  it("1 punto → path válido (línea plana)", () => {
    expect(sparklinePath([{ danger: 1, warn: 0 }], 100, 24)).toBe("M0,0 L100,0");
  });
  it("serie conocida → path determinista", () => {
    const pts = [
      { danger: 0, warn: 0 },
      { danger: 1, warn: 1 },
      { danger: 0, warn: 2 },
    ];
    expect(sparklinePath(pts, 100, 24)).toBe("M0,24 L50,0 L100,0");
  });
});

describe("relativeFromIso", () => {
  const now = Date.parse("2026-07-18T13:00:00Z");
  it("ISO inválido → cadena vacía", () => {
    expect(relativeFromIso("nope", now)).toBe("");
  });
  it("distancias conocidas", () => {
    expect(relativeFromIso("2026-07-18T12:59:40Z", now)).toBe("hace <1 min");
    expect(relativeFromIso("2026-07-18T12:55:00Z", now)).toBe("hace 5 min");
    expect(relativeFromIso("2026-07-18T10:00:00Z", now)).toBe("hace 3 h");
    expect(relativeFromIso("2026-07-16T13:00:00Z", now)).toBe("hace 2 d");
  });
});

describe("formatCellTitle", () => {
  it("contiene alias y parity", () => {
    const now = Date.parse("2026-07-18T13:00:00Z");
    const title = formatCellTitle(cell("DEV", "TEST", { warn: 2 }), now);
    expect(title).toContain("DEV");
    expect(title).toContain("TEST");
    expect(title).toContain("98.5");
  });
});
