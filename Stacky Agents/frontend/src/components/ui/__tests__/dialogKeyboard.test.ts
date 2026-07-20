/**
 * Plan 164 F1 — Tests PUROS de la lógica de teclado/foco de la primitiva Dialog.
 * Sin DOM (RTL/jsdom no están en el repo): se testea la decisión pura de teclado,
 * el próximo índice enfocable (focus-trap) y la guarda de cierre.
 */
import { describe, it, expect } from "vitest";
import {
  dialogKeydownAction,
  nextFocusableIndex,
  canCloseByGuard,
} from "../dialogKeyboard";

describe("dialogKeyboard (plan 164 F1)", () => {
  it("test_escape_cierra", () => {
    expect(
      dialogKeydownAction("Escape", false, { atFirst: false, atLast: false }),
    ).toBe("close");
  });

  it("test_tab_wrap_adelante", () => {
    expect(
      dialogKeydownAction("Tab", false, { atFirst: false, atLast: true }),
    ).toBe("focus-first");
  });

  it("test_shift_tab_wrap_atras", () => {
    expect(
      dialogKeydownAction("Tab", true, { atFirst: true, atLast: false }),
    ).toBe("focus-last");
  });

  it("test_tab_intermedio_no_actua", () => {
    expect(
      dialogKeydownAction("Tab", false, { atFirst: false, atLast: false }),
    ).toBe(null);
  });

  it("test_next_index_wrap", () => {
    expect(nextFocusableIndex(3, 2, false)).toBe(0);
    expect(nextFocusableIndex(3, 0, true)).toBe(2);
    expect(nextFocusableIndex(0, 0, false)).toBe(-1);
  });

  it("test_closeGuard_bloquea", () => {
    expect(canCloseByGuard({ dirty: true, busy: false })).toBe(false);
    expect(canCloseByGuard({ dirty: false, busy: true })).toBe(false);
    expect(canCloseByGuard({ dirty: false, busy: false })).toBe(true);
    expect(canCloseByGuard(undefined)).toBe(true);
  });
});
