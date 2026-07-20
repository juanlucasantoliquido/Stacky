/**
 * connectionMonitor.ts — Plan 192 F1 (serie UX).
 *
 * Máquina de estados de conexión dashboard-backend, 100% pasiva: observa el
 * resultado (éxito/fallo) de las requests que la app YA hace por el choke-point
 * de api-client, y SOLO durante una caída dispara un probe read-only con backoff.
 * No importa nada de api/ (el probeUrl llega por enable() — grafo acíclico D7).
 * La detección sana no usa timers ni requests recurrentes (K1).
 */

export type ConnectionStatus = "healthy" | "suspect" | "down" | "recovering";

export interface ConnectionSnapshot {
  status: ConnectionStatus;
  /** Probes disparados en el ciclo down actual (0 fuera de down). */
  attempt: number;
  /** Epoch ms de entrada al estado down del ciclo actual (null fuera de down). */
  downSince: number | null;
  /** Última señal de éxito de conexión (pasiva o probe), epoch ms. */
  lastOkAt: number | null;
  /** Última transición down->recovering, epoch ms. */
  lastRecoveredAt: number | null;
  enabled: boolean;
}

export const PROBE_TIMEOUT_MS = 5000;
export const BACKOFF_BASE_MS = 1000;
export const BACKOFF_FACTOR = 2;
export const BACKOFF_CAP_MS = 30000;
export const RECOVERY_LINGER_MS = 4000;
export const STARTUP_SIGNAL_WINDOW_MS = 10000;
/** Fuente ÚNICA de los statuses de gateway (C8): client.ts la IMPORTA; prohibido duplicar el Set. */
export const GATEWAY_DOWN_STATUSES: ReadonlySet<number> = new Set([502, 503, 504]);

export interface MachineDeps {
  now(): number;
  schedule(fn: () => void, ms: number): unknown; // handle opaco
  cancel(handle: unknown): void;
  probe(url: string, timeoutMs: number): Promise<boolean>; // true = res.ok
  isHidden(): boolean;
  /** Registra cb de visibilidad; devuelve unsubscribe. */
  onVisibilityChange(cb: () => void): () => void;
  /** D13 — eventos de red del navegador; devuelven unsubscribe. */
  onOnline(cb: () => void): () => void;
  onOffline(cb: () => void): () => void;
}

export interface ConnectionMachine {
  reportSuccess(): void;
  reportFailure(): void;
  enable(opts: { probeUrl: string }): void;
  disable(): void;
  setOnRecovered(fn: (() => void) | null): void;
  probeNow(): void;
  subscribe(listener: () => void): () => void;
  getSnapshot(): ConnectionSnapshot;
  /** C3: lectura VIVA de lastOkAt (NO la copia del snapshot, que solo se regenera al transicionar). */
  getLastOkAt(): number | null;
}

/** Factory PURA (testeable con deps fake). */
export function _createConnectionMachine(deps: MachineDeps): ConnectionMachine {
  let status: ConnectionStatus = "healthy";
  let enabled = false;
  let probeUrl = "";
  let attempt = 0;
  let downSince: number | null = null;
  let lastOkAt: number | null = null;
  let lastFailureAt: number | null = null; // interno, no va al snapshot
  let lastRecoveredAt: number | null = null;
  let gen = 0; // generación anti-stale (D3)
  let timerHandle: unknown = null; // probe programado o linger
  let pendingWhileHidden = false;
  let onRecovered: (() => void) | null = null;
  let visibilityUnsub: (() => void) | null = null;
  let onlineUnsub: (() => void) | null = null; // D13
  let offlineUnsub: (() => void) | null = null; // D13
  const listeners = new Set<() => void>();
  let snapshot: ConnectionSnapshot = makeSnapshot();

  function makeSnapshot(): ConnectionSnapshot {
    return { status, attempt, downSince, lastOkAt, lastRecoveredAt, enabled };
  }
  function notify() {
    snapshot = makeSnapshot();
    listeners.forEach((l) => l());
  }
  function clearTimer() {
    if (timerHandle !== null) {
      deps.cancel(timerHandle);
      timerHandle = null;
    }
  }
  function transition(next: ConnectionStatus) {
    gen += 1;
    clearTimer();
    status = next;
    notify();
  }

  function delayForNextProbe(): number {
    // attempt = probes YA disparados en este ciclo down (k de D5)
    return Math.min(BACKOFF_BASE_MS * Math.pow(BACKOFF_FACTOR, attempt), BACKOFF_CAP_MS);
  }

  function fireProbe(countsAsAttempt: boolean) {
    if (deps.isHidden()) {
      pendingWhileHidden = true;
      return;
    }
    pendingWhileHidden = false;
    if (countsAsAttempt) {
      attempt += 1;
      notify();
    }
    const myGen = gen;
    deps.probe(probeUrl, PROBE_TIMEOUT_MS).then(
      (ok) => {
        if (gen !== myGen) return;
        ok ? onProbeOk() : onProbeFail();
      },
      () => {
        if (gen !== myGen) return;
        onProbeFail();
      },
    );
  }

  function scheduleProbe(ms: number) {
    clearTimer();
    if (deps.isHidden()) {
      pendingWhileHidden = true;
      return;
    }
    timerHandle = deps.schedule(() => {
      timerHandle = null;
      fireProbe(true);
    }, ms);
  }

  function onProbeOk() {
    lastOkAt = deps.now();
    if (status === "suspect") {
      transition("healthy");
      attempt = 0;
      notify();
      return;
    }
    if (status === "down") {
      enterRecovering();
    }
  }
  function onProbeFail() {
    lastFailureAt = deps.now();
    if (status === "suspect") {
      downSince = deps.now();
      attempt = 0;
      transition("down");
      scheduleProbe(delayForNextProbe());
      return;
    }
    if (status === "down") {
      scheduleProbe(delayForNextProbe());
      notify();
    }
  }
  function enterRecovering() {
    lastRecoveredAt = deps.now();
    attempt = 0;
    downSince = null;
    transition("recovering");
    const fn = onRecovered;
    if (fn) fn(); // EXACTAMENTE 1 vez por ciclo (gen ya avanzó)
    timerHandle = deps.schedule(() => {
      timerHandle = null;
      transition("healthy");
    }, RECOVERY_LINGER_MS);
  }

  function reportSuccess() {
    lastOkAt = deps.now();
    if (!enabled) return; // inerte
    if (status === "suspect") {
      transition("healthy");
      return;
    }
    if (status === "down") {
      enterRecovering();
      return;
    }
    // healthy / recovering: sin transición; snapshot.lastOkAt se refresca en el próximo notify
  }
  function reportFailure() {
    lastFailureAt = deps.now();
    if (!enabled) return; // inerte (solo registra lastFailureAt)
    if (status === "healthy") {
      transition("suspect");
      fireProbe(false);
      return;
    }
    if (status === "recovering") {
      transition("suspect");
      fireProbe(false);
      return;
    }
    // suspect / down: el probe en curso ya decide; no reprogramar acá
  }

  function enable(opts: { probeUrl: string }) {
    if (enabled) return; // idempotente
    enabled = true;
    probeUrl = opts.probeUrl;
    visibilityUnsub = deps.onVisibilityChange(() => {
      if (
        !deps.isHidden() &&
        pendingWhileHidden &&
        (status === "down" || status === "suspect")
      ) {
        fireProbe(status === "down");
      }
    });
    // D13 — señal de red del navegador (t20/t21):
    offlineUnsub = deps.onOffline(() => {
      reportFailure();
    });
    onlineUnsub = deps.onOnline(() => {
      if (status === "down" || status === "suspect") {
        clearTimer();
        fireProbe(status === "down");
      }
    });
    const failedRecently =
      lastFailureAt !== null &&
      (lastOkAt === null || lastFailureAt > lastOkAt) &&
      deps.now() - lastFailureAt <= STARTUP_SIGNAL_WINDOW_MS;
    if (failedRecently) {
      transition("suspect");
      fireProbe(false); // arranque en frío con backend caído
    } else {
      notify(); // healthy, cero probes
    }
  }
  function disable() {
    if (!enabled) return;
    enabled = false;
    gen += 1;
    clearTimer();
    if (visibilityUnsub) {
      visibilityUnsub();
      visibilityUnsub = null;
    }
    if (onlineUnsub) {
      onlineUnsub();
      onlineUnsub = null;
    } // D13
    if (offlineUnsub) {
      offlineUnsub();
      offlineUnsub = null;
    } // D13
    status = "healthy";
    attempt = 0;
    downSince = null;
    pendingWhileHidden = false;
    notify();
  }
  function probeNow() {
    if (!enabled || (status !== "down" && status !== "suspect")) return;
    clearTimer();
    fireProbe(status === "down");
  }

  return {
    reportSuccess,
    reportFailure,
    enable,
    disable,
    probeNow,
    setOnRecovered: (fn) => {
      onRecovered = fn;
    },
    subscribe: (l) => {
      listeners.add(l);
      return () => {
        listeners.delete(l);
      };
    },
    getSnapshot: () => snapshot,
    getLastOkAt: () => lastOkAt,
  };
}

// ── Singleton cableado a browser APIs ───────────────────────────────────────
function realProbe(url: string, timeoutMs: number): Promise<boolean> {
  const ctrl = new AbortController();
  const t = window.setTimeout(() => ctrl.abort(), timeoutMs);
  return fetch(url, { signal: ctrl.signal, cache: "no-store" })
    .then((res) => res.ok)
    .finally(() => window.clearTimeout(t));
}

export const connectionMonitor: ConnectionMachine = _createConnectionMachine({
  now: () => Date.now(),
  schedule: (fn, ms) => window.setTimeout(fn, ms),
  cancel: (h) => window.clearTimeout(h as number),
  probe: realProbe,
  isHidden: () => typeof document !== "undefined" && document.hidden === true,
  onVisibilityChange: (cb) => {
    if (typeof document === "undefined") return () => {};
    document.addEventListener("visibilitychange", cb);
    return () => document.removeEventListener("visibilitychange", cb);
  },
  onOnline: (cb) => {
    if (typeof window === "undefined") return () => {};
    window.addEventListener("online", cb);
    return () => window.removeEventListener("online", cb);
  },
  onOffline: (cb) => {
    if (typeof window === "undefined") return () => {};
    window.addEventListener("offline", cb);
    return () => window.removeEventListener("offline", cb);
  },
});

/** Atajos que usa client.ts (delegan en el singleton). */
export function reportConnectionSuccess(): void {
  connectionMonitor.reportSuccess();
}
export function reportConnectionFailure(): void {
  connectionMonitor.reportFailure();
}
/** F5: true si el monitor está habilitado (ConnectionBanner es dueño de la superficie "backend caído"). */
export function connectionMonitorOwnsBackendSurface(): boolean {
  return connectionMonitor.getSnapshot().enabled;
}
