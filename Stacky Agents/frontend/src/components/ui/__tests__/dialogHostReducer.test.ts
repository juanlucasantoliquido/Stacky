/**
 * Plan 164 F1 — Tests PUROS del reducer del host de diálogos + helpers.
 * Sin DOM: sólo transiciones de la cola FIFO, settle idempotente (C1),
 * valor de dismiss por kind (C1) y type-to-confirm (A2).
 */
import { describe, it, expect } from "vitest";
import {
  dialogHostReducer,
  dismissValueFor,
  textPromptCanConfirm,
  type DialogRequest,
  type DialogHostState,
} from "../dialogHostReducer";

function req(id: string): DialogRequest {
  return { id, kind: "confirm", opts: {} };
}

const EMPTY: DialogHostState = { queue: [], current: null };

describe("dialogHostReducer (plan 164 F1)", () => {
  it("test_enqueue_abre_primero", () => {
    const A = req("A");
    const s = dialogHostReducer(EMPTY, { type: "enqueue", request: A });
    expect(s.current).toBe(A);
    expect(s.queue).toEqual([]);
  });

  it("test_fifo", () => {
    const A = req("A");
    const B = req("B");
    let s = dialogHostReducer(EMPTY, { type: "enqueue", request: A });
    s = dialogHostReducer(s, { type: "enqueue", request: B });
    expect(s.current).toBe(A);
    expect(s.queue).toEqual([B]);
  });

  it("test_resolve_avanza", () => {
    const A = req("A");
    const B = req("B");
    const start: DialogHostState = { current: A, queue: [B] };
    const s = dialogHostReducer(start, { type: "resolveCurrent", id: "A" });
    expect(s.current).toBe(B);
    expect(s.queue).toEqual([]);
  });

  it("test_resolve_ultimo_deja_vacio", () => {
    const A = req("A");
    const start: DialogHostState = { current: A, queue: [] };
    const s = dialogHostReducer(start, { type: "resolveCurrent", id: "A" });
    expect(s.current).toBe(null);
    expect(s.queue).toEqual([]);
  });

  it("test_settle_idempotente (C1)", () => {
    // resolver sobre current === null es no-op (mismo estado)
    const s0 = dialogHostReducer(EMPTY, { type: "resolveCurrent", id: "X" });
    expect(s0).toBe(EMPTY);
    // resolver con un id que ya no es current no re-avanza la cola
    const A = req("A");
    const B = req("B");
    const start: DialogHostState = { current: A, queue: [B] };
    const s1 = dialogHostReducer(start, { type: "resolveCurrent", id: "STALE" });
    expect(s1).toBe(start);
    expect(s1.current).toBe(A);
  });

  it("test_dismiss_value_por_kind (C1)", () => {
    expect(dismissValueFor("confirm")).toBe(false);
    expect(dismissValueFor("alert")).toBe(undefined);
    expect(dismissValueFor("prompt")).toBe(null);
  });

  it("test_type_to_confirm (A2)", () => {
    expect(textPromptCanConfirm("x", undefined)).toBe(true);
    expect(textPromptCanConfirm("ab", "abc")).toBe(false);
    expect(textPromptCanConfirm("abc", "abc")).toBe(true);
  });
});
