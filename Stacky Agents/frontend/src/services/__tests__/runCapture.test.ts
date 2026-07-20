import { describe, expect, it } from "vitest";
import { diffFinishedIds, shouldPublishCostTransition } from "../runCapture";

describe("diffFinishedIds (plan 152 F2)", () => {
  it("1. primer snapshot (prev=null) → []", () => {
    expect(diffFinishedIds(null, new Set([1, 2]))).toEqual([]);
  });

  it("2. uno finaliza → [1]", () => {
    expect(diffFinishedIds(new Set([1, 2]), new Set([2]))).toEqual([1]);
  });

  it("3. todos finalizan → [1,2,3]", () => {
    expect(diffFinishedIds(new Set([1, 2, 3]), new Set()).sort()).toEqual([1, 2, 3]);
  });

  it("4. aparecer no es finalizar → []", () => {
    expect(diffFinishedIds(new Set([1]), new Set([1, 2]))).toEqual([]);
  });

  it("5. sin cambios → []", () => {
    expect(diffFinishedIds(new Set([1]), new Set([1]))).toEqual([]);
  });
});

describe("shouldPublishCostTransition (plan 152 F2/F6b)", () => {
  it("6. tabla: solo transición hacia/entre alert|over|blocked", () => {
    expect(shouldPublishCostTransition(null, "ok")).toBe(false);
    expect(shouldPublishCostTransition("ok", "alert")).toBe(true);
    expect(shouldPublishCostTransition("alert", "alert")).toBe(false);
    expect(shouldPublishCostTransition("alert", "over")).toBe(true);
    expect(shouldPublishCostTransition("over", "ok")).toBe(false);
    expect(shouldPublishCostTransition(null, "blocked")).toBe(true);
    expect(shouldPublishCostTransition("unset", "alert")).toBe(true);
  });
});
