import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  DEFAULT_GRACE_MS,
  scheduleUndoable,
  undo,
  undoLatest,
  flushAll,
  pending,
  subscribe,
  setBypass,
  _resetForTests,
} from "../undoManager";

// Drena varias vueltas de microtasks (las cadenas de commit son promesas de 2+ niveles).
async function drain(): Promise<void> {
  for (let i = 0; i < 6; i++) await Promise.resolve();
}

beforeEach(() => {
  vi.useFakeTimers();
  _resetForTests();
});

describe("undoManager", () => {
  it("commit_dispara_al_vencer_gracia", async () => {
    const commit = vi.fn();
    const onCommitted = vi.fn();
    scheduleUndoable({ id: "t:1", label: "L", commit, onCommitted });
    expect(commit).toHaveBeenCalledTimes(0);
    await vi.advanceTimersByTimeAsync(DEFAULT_GRACE_MS);
    expect(commit).toHaveBeenCalledTimes(1);
    expect(onCommitted).toHaveBeenCalledTimes(1);
    expect(pending()).toHaveLength(0);
  });

  it("undo_dentro_de_gracia_cancela", async () => {
    const commit = vi.fn();
    const onUndo = vi.fn();
    scheduleUndoable({ id: "t:1", label: "L", commit, onUndo });
    await vi.advanceTimersByTimeAsync(3000);
    const ok = undo("t:1");
    expect(ok).toBe(true);
    expect(onUndo).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(DEFAULT_GRACE_MS);
    expect(commit).toHaveBeenCalledTimes(0);
  });

  it("undo_tarde_devuelve_false", async () => {
    const onUndo = vi.fn();
    scheduleUndoable({ id: "t:1", label: "L", commit: vi.fn(), onUndo });
    await vi.advanceTimersByTimeAsync(DEFAULT_GRACE_MS);
    expect(undo("t:1")).toBe(false);
    expect(onUndo).toHaveBeenCalledTimes(0);
  });

  it("undo_dos_veces_segunda_false", async () => {
    scheduleUndoable({ id: "t:1", label: "L", commit: vi.fn() });
    expect(undo("t:1")).toBe(true);
    expect(undo("t:1")).toBe(false);
  });

  it("replaced_flushea_anterior", async () => {
    const commitA = vi.fn();
    const commitB = vi.fn();
    scheduleUndoable({ id: "t:1", label: "A", commit: commitA });
    scheduleUndoable({ id: "t:1", label: "B", commit: commitB });
    await drain();
    // el anterior (A) se flusheó (reason replaced) al reprogramar el mismo id
    expect(commitA).toHaveBeenCalledTimes(1);
    // B sigue agendado (aún no vence)
    expect(commitB).toHaveBeenCalledTimes(0);
    expect(pending().map((p) => p.label)).toEqual(["B"]);
  });

  it("flushAll_commitea_todo_ya", async () => {
    const c1 = vi.fn();
    const c2 = vi.fn();
    const c3 = vi.fn();
    scheduleUndoable({ id: "a:1", label: "1", commit: c1 });
    scheduleUndoable({ id: "b:1", label: "2", commit: c2 });
    scheduleUndoable({ id: "c:1", label: "3", commit: c3 });
    flushAll("pagehide");
    await drain();
    expect(c1).toHaveBeenCalledTimes(1);
    expect(c2).toHaveBeenCalledTimes(1);
    expect(c3).toHaveBeenCalledTimes(1);
    expect(pending()).toHaveLength(0);
    // idempotente: segundo flush sin pendientes = no-op
    flushAll("pagehide");
    await drain();
    expect(c1).toHaveBeenCalledTimes(1);
  });

  it("bypass_commit_inmediato", async () => {
    const listener = vi.fn();
    subscribe(listener);
    setBypass(true);
    const commit = vi.fn();
    scheduleUndoable({ id: "t:1", label: "L", commit });
    await drain();
    expect(commit).toHaveBeenCalledTimes(1);
    expect(pending()).toHaveLength(0);
    expect(listener).toHaveBeenCalledTimes(0);
  });

  it("commit_que_lanza_invoca_onError", async () => {
    const err = new Error("boom");
    const onError = vi.fn();
    const onCommitted = vi.fn();
    scheduleUndoable({
      id: "t:1",
      label: "L",
      commit: () => {
        throw err;
      },
      onError,
      onCommitted,
    });
    await vi.advanceTimersByTimeAsync(DEFAULT_GRACE_MS);
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith(err);
    expect(onCommitted).toHaveBeenCalledTimes(0);
    expect(pending()).toHaveLength(0);
  });

  it("clamp_de_gracia", async () => {
    const commit = vi.fn();
    scheduleUndoable({ id: "t:1", label: "L", graceMs: 100, commit });
    await vi.advanceTimersByTimeAsync(1999);
    expect(commit).toHaveBeenCalledTimes(0); // clamp a 2000, aún no vence
    await vi.advanceTimersByTimeAsync(1);
    expect(commit).toHaveBeenCalledTimes(1);
  });

  it("subscribe_notifica_en_alta_y_baja", () => {
    const listener = vi.fn();
    const unsub = subscribe(listener);
    scheduleUndoable({ id: "t:1", label: "L", commit: vi.fn() });
    undo("t:1");
    expect(listener.mock.calls.length).toBeGreaterThanOrEqual(2);
    unsub();
    scheduleUndoable({ id: "t:2", label: "L2", commit: vi.fn() });
    // tras desuscribir no crece
    expect(listener.mock.calls.length).toBeGreaterThanOrEqual(2);
    const before = listener.mock.calls.length;
    undo("t:2");
    expect(listener.mock.calls.length).toBe(before);
  });

  it("replaced_serializa_commits_mismo_id", async () => {
    const order: string[] = [];
    let resolveA!: () => void;
    const pA = new Promise<void>((r) => {
      resolveA = r;
    });
    scheduleUndoable({
      id: "x",
      label: "A",
      commit: () => {
        order.push("A-commit");
        return pA.then(() => {
          order.push("A-resolve");
        });
      },
    });
    await vi.advanceTimersByTimeAsync(DEFAULT_GRACE_MS); // A despachado (queda esperando pA)
    scheduleUndoable({
      id: "x",
      label: "B",
      commit: () => {
        order.push("B-commit");
      },
    });
    flushAll("manual"); // B se despacha encadenado tras A (mismo id)
    await drain();
    // A no resolvió aún ⇒ B NO debe haber ejecutado
    expect(order).toEqual(["A-commit"]);
    resolveA();
    await drain();
    expect(order).toEqual(["A-commit", "A-resolve", "B-commit"]);
  });

  it("undoLatest_deshace_el_mas_reciente", async () => {
    const onUndo1 = vi.fn();
    const onUndo2 = vi.fn();
    scheduleUndoable({ id: "t:1", label: "1", commit: vi.fn(), onUndo: onUndo1 });
    await vi.advanceTimersByTimeAsync(10); // asegura createdAt distinto
    scheduleUndoable({ id: "t:2", label: "2", commit: vi.fn(), onUndo: onUndo2 });
    expect(undoLatest()).toBe(true);
    expect(onUndo2).toHaveBeenCalledTimes(1);
    expect(onUndo1).toHaveBeenCalledTimes(0);
    expect(pending().map((p) => p.id)).toEqual(["t:1"]);
    // vacío ⇒ false
    undo("t:1");
    expect(undoLatest()).toBe(false);
  });
});
