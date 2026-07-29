// Plan 266 F1/F1.5 — módulo puro de normalización del summary + tabla de verdad
// compartida (Python la recorre en tests/test_plan266_summary_shape.py).
import { describe, it, expect } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import {
  EMPTY_BY_SEVERITY,
  toCount,
  toScore,
  safeBySeverity,
  safeByAction,
  safeByObjectType,
  safeSummary,
} from "./summaryShape";

describe("Plan 266 F1 — safeBySeverity (casos borde)", () => {
  const cases: [unknown, { info: number; warn: number; danger: number }][] = [
    [undefined, { info: 0, warn: 0, danger: 0 }],
    [null, { info: 0, warn: 0, danger: 0 }],
    [{}, { info: 0, warn: 0, danger: 0 }],
    [{ danger: 3 }, { info: 0, warn: 0, danger: 3 }],
    [{ danger: "3" }, { info: 0, warn: 0, danger: 3 }],
    [{ danger: "abc" }, { info: 0, warn: 0, danger: 0 }],
    [{ danger: -5 }, { info: 0, warn: 0, danger: 0 }],
    [{ danger: 2.9 }, { info: 0, warn: 0, danger: 2 }],
    [{ danger: NaN }, { info: 0, warn: 0, danger: 0 }],
    [{ danger: Infinity }, { info: 0, warn: 0, danger: 0 }],
    [{ danger: true }, { info: 0, warn: 0, danger: 0 }],
    [42, { info: 0, warn: 0, danger: 0 }],
    ["texto", { info: 0, warn: 0, danger: 0 }],
    [[1, 2, 3], { info: 0, warn: 0, danger: 0 }],
    [{ danger: 3, extra: 9 }, { info: 0, warn: 0, danger: 3 }],
    [{ info: 1, warn: 2, danger: 3 }, { info: 1, warn: 2, danger: 3 }],
  ];

  for (const [input, expected] of cases) {
    it(`safeBySeverity(${JSON.stringify(input)}) === ${JSON.stringify(expected)}`, () => {
      expect(safeBySeverity(input)).toEqual(expected);
    });
  }
});

describe("Plan 266 F1 — toScore", () => {
  it("91.7 -> 91.7", () => expect(toScore(91.7)).toBe(91.7));
  it('"91.7" -> 91.7', () => expect(toScore("91.7")).toBe(91.7));
  it("120 -> 100 (clamp superior)", () => expect(toScore(120)).toBe(100));
  it("-3 -> 0 (clamp inferior)", () => expect(toScore(-3)).toBe(0));
  it("undefined -> 0", () => expect(toScore(undefined)).toBe(0));
  it("91.74 -> 91.7 (redondeo a 1 decimal)", () => expect(toScore(91.74)).toBe(91.7));
  it("null -> 0", () => expect(toScore(null)).toBe(0));
});

describe("Plan 266 F1 — safeSummary", () => {
  it("safeSummary(undefined) devuelve el objeto completo con los 3 mapas en ceros", () => {
    expect(safeSummary(undefined)).toEqual({
      by_severity: { info: 0, warn: 0, danger: 0 },
      by_action: { added: 0, removed: 0, changed: 0 },
      by_object_type: { table: 0, view: 0, sequence: 0 },
      objects_total: 0,
      objects_unchanged: 0,
      parity_score: 0,
    });
  });

  it("safeSummary no muta la entrada", () => {
    const src = { by_severity: { danger: 3 }, parity_score: 91.7 };
    const copia = JSON.parse(JSON.stringify(src));
    safeSummary(src);
    expect(src).toEqual(copia);
  });

  it("safeBySeverity(EMPTY_BY_SEVERITY) devuelve un objeto NUEVO, no la constante", () => {
    const result = safeBySeverity(EMPTY_BY_SEVERITY);
    expect(result).not.toBe(EMPTY_BY_SEVERITY);
    expect(result).toEqual(EMPTY_BY_SEVERITY);
  });

  it("safeByAction: undefined, {}, parcial, completo", () => {
    expect(safeByAction(undefined)).toEqual({ added: 0, removed: 0, changed: 0 });
    expect(safeByAction({})).toEqual({ added: 0, removed: 0, changed: 0 });
    expect(safeByAction({ added: 2 })).toEqual({ added: 2, removed: 0, changed: 0 });
    expect(safeByAction({ added: 1, removed: 2, changed: 3 })).toEqual({
      added: 1, removed: 2, changed: 3,
    });
  });

  it("safeByObjectType: undefined, {}, parcial, completo", () => {
    expect(safeByObjectType(undefined)).toEqual({ table: 0, view: 0, sequence: 0 });
    expect(safeByObjectType({})).toEqual({ table: 0, view: 0, sequence: 0 });
    expect(safeByObjectType({ table: 5 })).toEqual({ table: 5, view: 0, sequence: 0 });
    expect(safeByObjectType({ table: 1, view: 2, sequence: 3 })).toEqual({
      table: 1, view: 2, sequence: 3,
    });
  });
});

// --------------------------------------------------------------------------
// F1.5.2(a) — tabla de verdad ÚNICA, compartida con dbcompare_runs._count (Python).
// --------------------------------------------------------------------------

// vitest se invoca desde `Stacky Agents/frontend`, igual que los ratchets de src/__tests__.
const TRUTH_PATH = resolve(
  process.cwd(),
  "src/components/dbcompare/__fixtures__/summaryShapeTruthTable.json",
);
type Caso = { in: unknown; out: number; why: string };
const TRUTH: Caso[] = existsSync(TRUTH_PATH)
  ? (JSON.parse(readFileSync(TRUTH_PATH, "utf-8")) as Caso[])
  : [];

function materializar(v: unknown): unknown {
  if (
    v !== null && typeof v === "object" && !Array.isArray(v) &&
    Object.keys(v as object).length === 1 &&
    typeof (v as { raw?: unknown }).raw === "string"
  ) {
    const raw = (v as { raw: string }).raw;
    if (raw === "NaN") return NaN;
    if (raw === "Infinity") return Infinity;
    if (raw === "-Infinity") return -Infinity;
    throw new Error(`sobre raw desconocido en la tabla de verdad: ${raw}`);
  }
  return v;
}

describe("Plan 266 F1.5 — tabla de verdad compartida (toCount)", () => {
  it("la tabla de verdad compartida existe", () => {
    expect(existsSync(TRUTH_PATH)).toBe(true);
  });

  it("la tabla de verdad compartida tiene al menos 17 casos", () => {
    expect(TRUTH.length).toBeGreaterThanOrEqual(17);
  });

  it("toCount cumple cada caso de la tabla de verdad", () => {
    for (const c of TRUTH) {
      expect(toCount(materializar(c.in)), c.why).toBe(c.out);
    }
  });
});
