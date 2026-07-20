import { describe, it, expect } from "vitest";
import {
  _createConnectionMachine,
  type MachineDeps,
  type ConnectionMachine,
} from "./connectionMonitor";

// ── Deferred + microtask flush ──────────────────────────────────────────────
interface Deferred<T> {
  promise: Promise<T>;
  resolve: (v: T) => void;
  reject: (e: unknown) => void;
}
function defer<T>(): Deferred<T> {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}
const tick = () => Promise.resolve().then(() => Promise.resolve());

// ── Fake deps: manual scheduler + controlled probes + event cbs ──────────────
interface TimerRec {
  fn: () => void;
  ms: number;
  cancelled: boolean;
  fired: boolean;
}
function makeHarness(opts?: { hidden?: boolean }) {
  let nowVal = 1000;
  const scheduled: TimerRec[] = [];
  const probes: Array<Deferred<boolean>> = [];
  const visCbs: Array<() => void> = [];
  const onlineCbs: Array<() => void> = [];
  const offlineCbs: Array<() => void> = [];
  let hidden = opts?.hidden ?? false;
  let cancelCount = 0;

  const deps: MachineDeps = {
    now: () => nowVal,
    schedule: (fn, ms) => {
      const h: TimerRec = { fn, ms, cancelled: false, fired: false };
      scheduled.push(h);
      return h;
    },
    cancel: (h) => {
      cancelCount += 1;
      if (h) (h as TimerRec).cancelled = true;
    },
    probe: () => {
      const d = defer<boolean>();
      probes.push(d);
      return d.promise;
    },
    isHidden: () => hidden,
    onVisibilityChange: (cb) => {
      visCbs.push(cb);
      return () => {};
    },
    onOnline: (cb) => {
      onlineCbs.push(cb);
      return () => {};
    },
    onOffline: (cb) => {
      offlineCbs.push(cb);
      return () => {};
    },
  };

  return {
    deps,
    scheduledMs: () => scheduled.map((s) => s.ms),
    probeCount: () => probes.length,
    scheduleCount: () => scheduled.length,
    setNow: (v: number) => {
      nowVal = v;
    },
    setHidden: (v: boolean) => {
      hidden = v;
    },
    cancelCount: () => cancelCount,
    visCbs,
    onlineCbs,
    offlineCbs,
    /** Fire the current pending timer (last non-cancelled, non-fired). */
    fireTimer: () => {
      for (let i = scheduled.length - 1; i >= 0; i--) {
        const s = scheduled[i];
        if (!s.cancelled && !s.fired) {
          s.fired = true;
          s.fn();
          return;
        }
      }
      throw new Error("no pending timer to fire");
    },
    hasPendingTimer: () =>
      scheduled.some((s) => !s.cancelled && !s.fired),
    settleLastProbe: async (ok: boolean) => {
      probes[probes.length - 1].resolve(ok);
      await tick();
    },
    rejectLastProbe: async () => {
      probes[probes.length - 1].reject(new Error("network"));
      await tick();
    },
  };
}

// helper: drive machine healthy -> down (attempt 0, one probe timer pending @1000)
async function driveToDown(m: ConnectionMachine, h: ReturnType<typeof makeHarness>) {
  m.reportFailure(); // healthy -> suspect + immediate probe
  await h.settleLastProbe(false); // suspect -> down, schedule @1000
}

describe("connectionMonitor state machine (Plan 192 F1)", () => {
  it("t1: enabled + solo reportSuccess => healthy, sin timers ni probes (K1)", async () => {
    const h = makeHarness();
    const m = _createConnectionMachine(h.deps);
    m.enable({ probeUrl: "/p" });
    m.reportSuccess();
    m.reportSuccess();
    m.reportSuccess();
    expect(m.getSnapshot().status).toBe("healthy");
    expect(h.scheduleCount()).toBe(0);
    expect(h.probeCount()).toBe(0);
  });

  it("t2: healthy + 1 reportFailure => suspect + 1 probe inmediato", () => {
    const h = makeHarness();
    const m = _createConnectionMachine(h.deps);
    m.enable({ probeUrl: "/p" });
    m.reportFailure();
    expect(m.getSnapshot().status).toBe("suspect");
    expect(h.probeCount()).toBe(1);
    expect(h.scheduleCount()).toBe(0); // suspect no programa timer
  });

  it("t3: suspect + probe true => healthy, onRecovered NO llamado", async () => {
    const h = makeHarness();
    const m = _createConnectionMachine(h.deps);
    let recovered = 0;
    m.setOnRecovered(() => {
      recovered += 1;
    });
    m.enable({ probeUrl: "/p" });
    m.reportFailure();
    await h.settleLastProbe(true);
    expect(m.getSnapshot().status).toBe("healthy");
    expect(recovered).toBe(0);
  });

  it("t4: suspect + reportSuccess antes de que resuelva el probe => healthy, probe tardio ignorado", async () => {
    const h = makeHarness();
    const m = _createConnectionMachine(h.deps);
    m.enable({ probeUrl: "/p" });
    m.reportFailure(); // suspect, probe en vuelo (gen 1)
    m.reportSuccess(); // suspect -> healthy (gen 2)
    expect(m.getSnapshot().status).toBe("healthy");
    await h.settleLastProbe(false); // resultado stale: ignorado
    expect(m.getSnapshot().status).toBe("healthy");
  });

  it("t5: suspect + probe false => down, attempt 0 hasta disparar el proximo, siguiente @1000", async () => {
    const h = makeHarness();
    const m = _createConnectionMachine(h.deps);
    m.enable({ probeUrl: "/p" });
    m.reportFailure();
    await h.settleLastProbe(false);
    expect(m.getSnapshot().status).toBe("down");
    expect(m.getSnapshot().attempt).toBe(0);
    expect(h.scheduledMs().slice(-1)[0]).toBe(1000);
    h.fireTimer(); // dispara el proximo probe
    expect(m.getSnapshot().attempt).toBe(1);
  });

  it("t6: down con probes que siempre fallan => backoff 1000,2000,4000,8000,16000,30000,30000 (K3)", async () => {
    const h = makeHarness();
    const m = _createConnectionMachine(h.deps);
    m.enable({ probeUrl: "/p" });
    await driveToDown(m, h); // schedule @1000
    for (let i = 0; i < 6; i++) {
      h.fireTimer();
      await h.settleLastProbe(false);
    }
    expect(h.scheduledMs()).toEqual([1000, 2000, 4000, 8000, 16000, 30000, 30000]);
  });

  it("t7: down + probe true => recovering, onRecovered 1 vez, linger => healthy, attempt 0 (K4/K5)", async () => {
    const h = makeHarness();
    const m = _createConnectionMachine(h.deps);
    let recovered = 0;
    m.setOnRecovered(() => {
      recovered += 1;
    });
    m.enable({ probeUrl: "/p" });
    await driveToDown(m, h);
    h.fireTimer();
    await h.settleLastProbe(true);
    expect(m.getSnapshot().status).toBe("recovering");
    expect(recovered).toBe(1);
    expect(h.hasPendingTimer()).toBe(true); // linger programado
    h.fireTimer(); // dispara linger
    expect(m.getSnapshot().status).toBe("healthy");
    expect(m.getSnapshot().attempt).toBe(0);
  });

  it("t8: down + reportSuccess pasivo => recovering + onRecovered 1 vez + probe pendiente cancelado", async () => {
    const h = makeHarness();
    const m = _createConnectionMachine(h.deps);
    let recovered = 0;
    m.setOnRecovered(() => {
      recovered += 1;
    });
    m.enable({ probeUrl: "/p" });
    await driveToDown(m, h); // timer pendiente @1000
    const before = h.cancelCount();
    m.reportSuccess();
    expect(m.getSnapshot().status).toBe("recovering");
    expect(recovered).toBe(1);
    expect(h.cancelCount()).toBeGreaterThan(before); // cancelo el probe pendiente
  });

  it("t9: recovering + reportFailure => cancela linger, suspect, probe inmediato", async () => {
    const h = makeHarness();
    const m = _createConnectionMachine(h.deps);
    m.enable({ probeUrl: "/p" });
    await driveToDown(m, h);
    h.fireTimer();
    await h.settleLastProbe(true); // recovering
    const probesBefore = h.probeCount();
    m.reportFailure();
    expect(m.getSnapshot().status).toBe("suspect");
    expect(h.probeCount()).toBe(probesBefore + 1);
  });

  it("t10: down con isHidden => sin probe; visibilitychange a visible => probe inmediato (K4)", async () => {
    const h = makeHarness();
    const m = _createConnectionMachine(h.deps);
    m.enable({ probeUrl: "/p" });
    await driveToDown(m, h); // timer @1000 (visible)
    h.setHidden(true);
    const probesBefore = h.probeCount();
    h.fireTimer(); // fireProbe pero oculto => no probe
    expect(h.probeCount()).toBe(probesBefore);
    h.setHidden(false);
    h.visCbs[0](); // vuelve a visible
    expect(h.probeCount()).toBe(probesBefore + 1);
  });

  it("t11: probeNow en down => cancela timer, probe inmediato, attempt++, reprograma con delay del k actual", async () => {
    const h = makeHarness();
    const m = _createConnectionMachine(h.deps);
    m.enable({ probeUrl: "/p" });
    await driveToDown(m, h); // attempt 0, timer @1000
    const before = h.cancelCount();
    m.probeNow();
    expect(h.cancelCount()).toBeGreaterThan(before);
    expect(m.getSnapshot().attempt).toBe(1);
    await h.settleLastProbe(false);
    // backoff NO reseteado: proximo delay corresponde a k=1 => 2000 (no 1000)
    expect(h.scheduledMs().slice(-1)[0]).toBe(2000);
  });

  it("t12: sin enable / tras disable => reportes inertes; disable en down cancela timers (K7)", async () => {
    const h = makeHarness();
    const m = _createConnectionMachine(h.deps);
    // sin enable
    expect(m.getSnapshot().enabled).toBe(false);
    m.reportFailure();
    m.reportSuccess();
    expect(m.getSnapshot().status).toBe("healthy");
    expect(h.scheduleCount()).toBe(0);
    expect(h.probeCount()).toBe(0);
    // enable -> down -> disable
    m.enable({ probeUrl: "/p" });
    expect(m.getSnapshot().enabled).toBe(true);
    await driveToDown(m, h);
    const before = h.cancelCount();
    m.disable();
    expect(m.getSnapshot().enabled).toBe(false);
    expect(m.getSnapshot().status).toBe("healthy");
    expect(h.cancelCount()).toBeGreaterThan(before);
  });

  it("t13: getSnapshot estable sin cambios; nueva referencia tras transicion", () => {
    const h = makeHarness();
    const m = _createConnectionMachine(h.deps);
    m.enable({ probeUrl: "/p" });
    const a = m.getSnapshot();
    const b = m.getSnapshot();
    expect(a).toBe(b);
    m.reportFailure();
    const c = m.getSnapshot();
    expect(c).not.toBe(a);
  });

  it("t14: setOnRecovered es slot unico; null limpia; nunca acumula", async () => {
    const h = makeHarness();
    const m = _createConnectionMachine(h.deps);
    let a = 0;
    let b = 0;
    m.setOnRecovered(() => {
      a += 1;
    });
    m.setOnRecovered(() => {
      b += 1;
    }); // reemplaza a fn1
    m.enable({ probeUrl: "/p" });
    await driveToDown(m, h);
    h.fireTimer();
    await h.settleLastProbe(true); // recovering: solo fn2
    expect(a).toBe(0);
    expect(b).toBe(1);
    m.setOnRecovered(null); // limpia
    // nuevo ciclo down -> recovering: nadie debe ser llamado
    m.reportFailure(); // recovering -> suspect + probe
    await h.settleLastProbe(false); // -> down
    h.fireTimer();
    await h.settleLastProbe(true); // -> recovering
    expect(a).toBe(0);
    expect(b).toBe(1);
  });

  it("t15: enable idempotente; disable + enable vuelve a funcionar", async () => {
    const h = makeHarness();
    const m = _createConnectionMachine(h.deps);
    m.enable({ probeUrl: "/p" });
    m.enable({ probeUrl: "/p" }); // idempotente: no re-registra listeners
    expect(h.visCbs.length).toBe(1);
    expect(h.onlineCbs.length).toBe(1);
    expect(h.offlineCbs.length).toBe(1);
    m.disable();
    m.enable({ probeUrl: "/p" }); // nueva sesion: registra de nuevo
    expect(h.visCbs.length).toBe(2);
    m.reportFailure();
    expect(m.getSnapshot().status).toBe("suspect");
  });

  it("t16: reportFailure disabled, luego enable dentro de la ventana => suspect + probe (arranque en frio)", () => {
    const h = makeHarness();
    const m = _createConnectionMachine(h.deps);
    h.setNow(1000);
    m.reportFailure(); // disabled, solo registra lastFailureAt
    h.setNow(2000); // dentro de STARTUP_SIGNAL_WINDOW_MS
    m.enable({ probeUrl: "/p" });
    expect(m.getSnapshot().status).toBe("suspect");
    expect(h.probeCount()).toBe(1);
  });

  it("t17: enable sin fallo reciente => healthy, cero probes", () => {
    const h = makeHarness();
    const m = _createConnectionMachine(h.deps);
    m.enable({ probeUrl: "/p" });
    expect(m.getSnapshot().status).toBe("healthy");
    expect(h.probeCount()).toBe(0);
  });

  it("t18: probe en vuelo resuelve tras una transicion (gen distinto) => ignorado, sin onRecovered duplicado", async () => {
    const h = makeHarness();
    const m = _createConnectionMachine(h.deps);
    let recovered = 0;
    m.setOnRecovered(() => {
      recovered += 1;
    });
    m.enable({ probeUrl: "/p" });
    await driveToDown(m, h);
    h.fireTimer(); // probe en vuelo (gen G)
    m.reportSuccess(); // down -> recovering (gen G+1), onRecovered 1 vez
    expect(m.getSnapshot().status).toBe("recovering");
    expect(recovered).toBe(1);
    await h.settleLastProbe(true); // gen stale: ignorado
    expect(recovered).toBe(1);
    expect(m.getSnapshot().status).toBe("recovering");
  });

  it("t19: healthy + reportSuccess => snapshot MISMA ref pero getLastOkAt VIVO (C3)", () => {
    const h = makeHarness();
    const m = _createConnectionMachine(h.deps);
    m.enable({ probeUrl: "/p" });
    const a = m.getSnapshot();
    h.setNow(5000);
    m.reportSuccess();
    const b = m.getSnapshot();
    expect(a).toBe(b); // sin notify => misma referencia
    expect(m.getLastOkAt()).toBe(5000); // lectura viva, no la copia del snapshot
  });

  it("t20: [D13] healthy + evento offline => suspect + 1 probe inmediato (K11)", () => {
    const h = makeHarness();
    const m = _createConnectionMachine(h.deps);
    m.enable({ probeUrl: "/p" });
    h.offlineCbs[0](); // evento offline
    expect(m.getSnapshot().status).toBe("suspect");
    expect(h.probeCount()).toBe(1);
  });

  it("t21: [D13] down + evento online => cancela timer + probe inmediato attempt++; en healthy no hace nada", async () => {
    const h = makeHarness();
    const m = _createConnectionMachine(h.deps);
    m.enable({ probeUrl: "/p" });
    await driveToDown(m, h); // timer pendiente
    const before = h.cancelCount();
    const probesBefore = h.probeCount();
    h.onlineCbs[0](); // evento online estando down
    expect(h.cancelCount()).toBeGreaterThan(before);
    expect(h.probeCount()).toBe(probesBefore + 1);
    expect(m.getSnapshot().attempt).toBe(1);

    // en healthy el evento online no hace nada
    const h2 = makeHarness();
    const m2 = _createConnectionMachine(h2.deps);
    m2.enable({ probeUrl: "/p" });
    h2.onlineCbs[0]();
    expect(m2.getSnapshot().status).toBe("healthy");
    expect(h2.probeCount()).toBe(0);
  });
});
