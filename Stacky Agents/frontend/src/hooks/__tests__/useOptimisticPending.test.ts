/**
 * Plan 143 F6 — feedback óptimista. Se testea la lógica PURA (runWithPending), sin render
 * (no hay RTL/jsdom en el repo). El hook envuelve esa lógica; tsc cubre el wrapper.
 */
import { describe, it, expect } from "vitest";
import { runWithPending } from "../useOptimisticPending";

describe("Plan 143 F6 — runWithPending", () => {
  it("marca pending true al empezar y false al terminar (éxito) y devuelve el valor", async () => {
    const calls: boolean[] = [];
    const r = await runWithPending((v) => calls.push(v), async () => 42);
    expect(r).toBe(42);
    expect(calls).toEqual([true, false]);
  });
  it("des-marca pending aunque la promesa rechace, y propaga el error", async () => {
    const calls: boolean[] = [];
    await expect(
      runWithPending((v) => calls.push(v), async () => {
        throw new Error("boom");
      }),
    ).rejects.toThrow("boom");
    expect(calls).toEqual([true, false]);
  });
});
