/**
 * consoleHistoryPanel.test.ts — Plan 265 F5(b). 4 casos del doc (D6).
 * Correr POR ARCHIVO: npx vitest run src/services/__tests__/consoleHistoryPanel.test.ts
 */
import { describe, it, expect } from "vitest";
import { historyPanelState } from "../consoleHistoryPanel";

describe("consoleHistoryPanel", () => {
  it("1. 200 con items -> available true, items presentes", () => {
    const r = historyPanelState({ status: 200, body: [{ id: 1 }, { id: 2 }] });
    expect(r.available).toBe(true);
    expect(r.items.length).toBe(2);
  });

  it("2. 404 feature_disabled -> available:false con motivo no vacío", () => {
    const r = historyPanelState({
      status: 404,
      body: { error: "feature_disabled", feature: "STACKY_EXECUTION_HISTORY_ENABLED" },
    });
    expect(r.available).toBe(false);
    expect(r.reason).toBeTruthy();
  });

  it("3. 500 -> available:false con motivo", () => {
    const r = historyPanelState({ status: 500, body: { error: "internal" } });
    expect(r.available).toBe(false);
    expect(r.reason).toBeTruthy();
  });

  it("4. body basura -> no lanza", () => {
    expect(() => historyPanelState({ status: 200, body: "no es un array" })).not.toThrow();
    expect(() => historyPanelState({ status: 200, body: null })).not.toThrow();
    expect(() => historyPanelState({ status: 200, body: undefined })).not.toThrow();
    const r = historyPanelState({ status: 200, body: "no es un array" });
    expect(Array.isArray(r.items)).toBe(true);
  });
});
