// Plan 174 F3 — Política de prefetch (pura, con timer inyectado).
import { describe, it, expect, vi } from "vitest";
import {
  createPrefetchScheduler,
  PREFETCH_HOVER_DELAY_MS,
  PREFETCH_MAX_CONCURRENT,
  type PrefetchTimer,
} from "../prefetchPolicy";

/** Timer manual: nada corre hasta que el test lo decide. */
function timerManual() {
  const cbs = new Map<number, () => void>();
  let siguiente = 1;
  const timer: PrefetchTimer = {
    set: (fn) => {
      const id = siguiente++;
      cbs.set(id, fn);
      return id;
    },
    clear: (id) => {
      cbs.delete(id);
    },
  };
  return {
    timer,
    /** Dispara todos los timers pendientes. */
    avanzar() {
      const pendientes = [...cbs.entries()];
      cbs.clear();
      for (const [, fn] of pendientes) fn();
    },
    pendientes: () => cbs.size,
  };
}

describe("createPrefetchScheduler", () => {
  it("sin interacción NO hace ni una request", () => {
    // Presupuesto del plan 156: cero requests por tick sin que el operador toque nada.
    const run = vi.fn(async () => {});
    const t = timerManual();

    createPrefetchScheduler(run, t.timer);
    t.avanzar();

    expect(run).not.toHaveBeenCalled();
  });

  it("no dispara antes del debounce", () => {
    const run = vi.fn(async () => {});
    const t = timerManual();
    const s = createPrefetchScheduler(run, t.timer);

    s.enter("a");

    expect(run).not.toHaveBeenCalled();
    expect(PREFETCH_HOVER_DELAY_MS).toBe(150);
  });

  it("salir antes del debounce cancela: el mouse de paso no gasta nada", () => {
    const run = vi.fn(async () => {});
    const t = timerManual();
    const s = createPrefetchScheduler(run, t.timer);

    s.enter("a");
    s.leave("a");
    t.avanzar();

    expect(run).not.toHaveBeenCalled();
  });

  it("vencido el debounce dispara una vez, y re-entrar en vuelo no repite", () => {
    const run = vi.fn(() => new Promise<void>(() => {}));
    const t = timerManual();
    const s = createPrefetchScheduler(run, t.timer);

    s.enter("a");
    t.avanzar();
    s.enter("a");
    t.avanzar();

    expect(run).toHaveBeenCalledTimes(1);
    expect(run).toHaveBeenCalledWith("a");
  });

  it("con uno en vuelo, el siguiente se DESCARTA (no se encola)", () => {
    // Una cola convertiría un paseo del mouse por la tabla en 30 requests diferidos.
    const run = vi.fn(() => new Promise<void>(() => {}));
    const t = timerManual();
    const s = createPrefetchScheduler(run, t.timer);

    s.enter("a");
    t.avanzar();
    s.enter("b");
    t.avanzar();

    expect(run).toHaveBeenCalledTimes(1);
    expect(s.inFlightCount()).toBeLessThanOrEqual(PREFETCH_MAX_CONCURRENT);
  });

  it("liberado el slot, el siguiente sí entra", async () => {
    let resolver: (() => void) | null = null;
    const run = vi.fn(() => new Promise<void>((res) => { resolver = () => res(); }));
    const t = timerManual();
    const s = createPrefetchScheduler(run, t.timer);

    s.enter("a");
    t.avanzar();
    resolver?.();
    await Promise.resolve();
    await Promise.resolve();
    s.enter("b");
    t.avanzar();

    expect(run).toHaveBeenCalledTimes(2);
    expect(run).toHaveBeenLastCalledWith("b");
  });

  it("enter repetido con timer pendiente no acumula timers", () => {
    const run = vi.fn(async () => {});
    const t = timerManual();
    const s = createPrefetchScheduler(run, t.timer);

    s.enter("a");
    s.enter("a");
    s.enter("a");

    expect(t.pendientes()).toBe(1);
  });

  it("dispose limpia lo pendiente: un unmount no dispara requests fantasma", () => {
    const run = vi.fn(async () => {});
    const t = timerManual();
    const s = createPrefetchScheduler(run, t.timer);

    s.enter("a");
    s.dispose();
    t.avanzar();

    expect(run).not.toHaveBeenCalled();
  });

  it("un prefetch que falla no rompe ni bloquea el slot para siempre", async () => {
    const run = vi.fn(async () => {
      throw new Error("red caída");
    });
    const t = timerManual();
    const s = createPrefetchScheduler(run, t.timer);

    s.enter("a");
    t.avanzar();
    await Promise.resolve();
    await Promise.resolve();

    expect(s.inFlightCount()).toBe(0);
  });
});
