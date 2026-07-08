/**
 * Tests de productionModel.ts - Plan 95 F4
 * TDD: lógica pura del flujo "Llevar a producción" (sin React).
 */
import { describe, it, expect } from "vitest";
import { mergeButtonEnabled, pipelineStatusLabel, shouldContinuePolling } from "./productionModel";

describe("productionModel", () => {
  it("merge_enabled_only_open_and_mergeable", () => {
    expect(mergeButtonEnabled({ state: "open", mergeable: true })).toBe(true);
    expect(mergeButtonEnabled({ state: "open", mergeable: false })).toBe(false);
    expect(mergeButtonEnabled({ state: "merged", mergeable: true })).toBe(false);
    expect(mergeButtonEnabled({ state: "closed", mergeable: true })).toBe(false);
  });

  it("labels_en_llano", () => {
    expect(pipelineStatusLabel("running")).toMatch(/corriendo/);
    expect(pipelineStatusLabel("success")).toMatch(/pasó/);
    expect(pipelineStatusLabel("failed")).toMatch(/falló/);
  });

  it("status_none_handled", () => {
    expect(pipelineStatusLabel("none")).toBe("sin pipeline");
    expect(pipelineStatusLabel(undefined)).toBe("sin pipeline");
  });

  it("polling_stops_on_cap_hidden_or_not_open", () => {
    expect(shouldContinuePolling(0, "open", false)).toBe(true);
    expect(shouldContinuePolling(60, "open", false)).toBe(false); // tope
    expect(shouldContinuePolling(5, "open", true)).toBe(false); // pestaña oculta
    expect(shouldContinuePolling(5, "merged", false)).toBe(false); // ya no está open
  });
});
