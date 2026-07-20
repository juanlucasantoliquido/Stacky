import { describe, it, expect } from "vitest";
import {
  visibleToasts,
  remainingRatio,
  shouldHandleUndoKey,
} from "../undoToastModel";
import type { PendingUndoable } from "../undoManager";

function mk(id: string, createdAt: number, graceMs = 6000): PendingUndoable {
  return { id, label: id, createdAt, expiresAt: createdAt + graceMs };
}

const activeBody = { tagName: "BODY", isContentEditable: false };

describe("undoToastModel", () => {
  it("visibleToasts_newest_first_cap_4", () => {
    const p = [
      mk("a", 100),
      mk("b", 200),
      mk("c", 300),
      mk("d", 400),
      mk("e", 500),
      mk("f", 600),
    ];
    const v = visibleToasts(p);
    expect(v.map((x) => x.id)).toEqual(["f", "e", "d", "c"]);
  });

  it("visibleToasts_max_custom", () => {
    const p = [mk("a", 100), mk("b", 200), mk("c", 300)];
    expect(visibleToasts(p, 2).map((x) => x.id)).toEqual(["c", "b"]);
    expect(visibleToasts([], 4)).toEqual([]);
  });

  it("remainingRatio_clamp_0_1", () => {
    const p = mk("a", 1000, 6000); // expiresAt 7000
    expect(remainingRatio(p, 1000)).toBeCloseTo(1, 5);
    expect(remainingRatio(p, 4000)).toBeCloseTo(0.5, 5);
    expect(remainingRatio(p, 7000)).toBeCloseTo(0, 5);
    // fuera de rango: clamp
    expect(remainingRatio(p, 500)).toBe(1);
    expect(remainingRatio(p, 9999)).toBe(0);
  });

  it("shouldHandleUndoKey_true_ctrl_z_fuera_de_inputs", () => {
    expect(
      shouldHandleUndoKey(
        { key: "z", ctrlKey: true, metaKey: false, altKey: false, shiftKey: false },
        activeBody,
      ),
    ).toBe(true);
    // metaKey (mac) también
    expect(
      shouldHandleUndoKey(
        { key: "Z", ctrlKey: false, metaKey: true, altKey: false, shiftKey: false },
        null,
      ),
    ).toBe(true);
  });

  it("shouldHandleUndoKey_false_en_input_textarea_select_contenteditable", () => {
    const ev = { key: "z", ctrlKey: true, metaKey: false, altKey: false, shiftKey: false };
    expect(shouldHandleUndoKey(ev, { tagName: "INPUT", isContentEditable: false })).toBe(false);
    expect(shouldHandleUndoKey(ev, { tagName: "TEXTAREA", isContentEditable: false })).toBe(false);
    expect(shouldHandleUndoKey(ev, { tagName: "SELECT", isContentEditable: false })).toBe(false);
    expect(shouldHandleUndoKey(ev, { tagName: "DIV", isContentEditable: true })).toBe(false);
  });

  it("shouldHandleUndoKey_false_con_shift_o_alt", () => {
    // Ctrl+Shift+Z (redo) NO se captura
    expect(
      shouldHandleUndoKey(
        { key: "z", ctrlKey: true, metaKey: false, altKey: false, shiftKey: true },
        activeBody,
      ),
    ).toBe(false);
    // Ctrl+Alt+Z NO
    expect(
      shouldHandleUndoKey(
        { key: "z", ctrlKey: true, metaKey: false, altKey: true, shiftKey: false },
        activeBody,
      ),
    ).toBe(false);
    // sin modificador NO
    expect(
      shouldHandleUndoKey(
        { key: "z", ctrlKey: false, metaKey: false, altKey: false, shiftKey: false },
        activeBody,
      ),
    ).toBe(false);
    // otra tecla NO
    expect(
      shouldHandleUndoKey(
        { key: "y", ctrlKey: true, metaKey: false, altKey: false, shiftKey: false },
        activeBody,
      ),
    ).toBe(false);
  });
});
