import { describe, it, expect } from "vitest";
import { polarToCartesian, arcPath, gaugeSweep, severityCounters, actionCounters } from "../svgMath";
import type { SchemaDiff } from "../dbcompareTypes";

function fixtureDiff(): SchemaDiff {
  return {
    version: 1,
    engine: "sqlserver",
    source: { alias: "src", snapshot_id: "s1", content_hash: "h1" },
    target: { alias: "tgt", snapshot_id: "s2", content_hash: "h2" },
    items: [],
    summary: {
      by_severity: { danger: 2, warn: 3, info: 1 },
      by_action: { added: 2, removed: 1, changed: 3 },
      by_object_type: { table: 4, view: 1, sequence: 1 },
      objects_total: 10,
      objects_unchanged: 4,
      parity_score: 40.0,
    },
  };
}

describe("Plan 124 F3 — svgMath (pure)", () => {
  it("polarToCartesian en 0deg (arriba) y 90deg (derecha)", () => {
    expect(polarToCartesian(100, 100, 50, 0)).toEqual({ x: 100, y: 50 });
    const right = polarToCartesian(100, 100, 50, 90);
    expect(right.x).toBeCloseTo(150, 5);
    expect(right.y).toBeCloseTo(100, 5);
  });

  it("arcPath golden string: gauge 270 grados (135 -> 405)", () => {
    expect(arcPath(100, 100, 80, 135, 405)).toBe("M 156.57 156.57 A 80 80 0 1 1 156.57 43.43");
  });

  it("arcPath golden string: semicírculo (0 -> 180)", () => {
    expect(arcPath(50, 50, 40, 0, 180)).toBe("M 50 10 A 40 40 0 0 1 50 90");
  });

  describe("gaugeSweep", () => {
    it("score 0 -> endDeg 135", () => {
      expect(gaugeSweep(0)).toEqual({ startDeg: 135, endDeg: 135 });
    });
    it("score 50 -> endDeg 270", () => {
      expect(gaugeSweep(50)).toEqual({ startDeg: 135, endDeg: 270 });
    });
    it("score 100 -> endDeg 405", () => {
      expect(gaugeSweep(100)).toEqual({ startDeg: 135, endDeg: 405 });
    });
    it("clampea fuera de rango", () => {
      expect(gaugeSweep(-10)).toEqual({ startDeg: 135, endDeg: 135 });
      expect(gaugeSweep(150)).toEqual({ startDeg: 135, endDeg: 405 });
    });
  });

  it("severityCounters respeta el orden fijo danger,warn,info y counts exactos", () => {
    expect(severityCounters(fixtureDiff())).toEqual([
      { severity: "danger", count: 2 },
      { severity: "warn", count: 3 },
      { severity: "info", count: 1 },
    ]);
  });

  it("actionCounters respeta el orden fijo added,removed,changed y counts exactos", () => {
    expect(actionCounters(fixtureDiff())).toEqual([
      { action: "added", count: 2 },
      { action: "removed", count: 1 },
      { action: "changed", count: 3 },
    ]);
  });
});
