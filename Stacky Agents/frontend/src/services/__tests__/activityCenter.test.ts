import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import {
  __resetActivityForTests,
  getActivitySnapshot,
  markActivityRead,
  publishActivity,
  setActivityMuted,
  subscribeActivity,
} from "../activityCenter";
import { groupByKind, unreadCount, LS_STATE_KEY, type ActivityEvent } from "../activityReducer";

/** localStorage de mentira (Map-backed) para el entorno node de vitest. */
function memStorage() {
  const mem = new Map<string, string>();
  return {
    getItem: (k: string) => (mem.has(k) ? mem.get(k)! : null),
    setItem: (k: string, v: string) => { mem.set(k, v); },
    removeItem: (k: string) => { mem.delete(k); },
    _mem: mem,
  };
}

function evt(over: Partial<ActivityEvent> = {}): ActivityEvent {
  return { key: "run:1", kind: "run", severity: "info", title: "t", ts: 1000, ...over };
}

beforeEach(() => {
  (globalThis as any).localStorage = memStorage();
  __resetActivityForTests();
});

afterEach(() => {
  delete (globalThis as any).localStorage;
});

describe("activityCenter store (plan 152 F1)", () => {
  it("1. publish + snapshot refleja el evento; subscriber llamado 1 vez", () => {
    const cb = vi.fn();
    subscribeActivity(cb);
    publishActivity(evt({ key: "run:1" }));
    expect(getActivitySnapshot().events).toHaveLength(1);
    expect(cb).toHaveBeenCalledTimes(1);
  });

  it("2. unsubscribe deja de recibir notificaciones", () => {
    const cb = vi.fn();
    const off = subscribeActivity(cb);
    off();
    publishActivity(evt({ key: "run:9" }));
    expect(cb).not.toHaveBeenCalled();
  });

  it("3. getActivitySnapshot estable: sin publish → misma referencia", () => {
    const a = getActivitySnapshot();
    const b = getActivitySnapshot();
    expect(a).toBe(b);
    publishActivity(evt({ key: "run:1" }));
    const c = getActivitySnapshot();
    expect(c).not.toBe(a);
  });

  it("4. markActivityRead → unreadCount 0", () => {
    publishActivity(evt({ key: "run:1", ts: Date.now() }));
    expect(unreadCount(getActivitySnapshot())).toBeGreaterThan(0);
    markActivityRead();
    expect(unreadCount(getActivitySnapshot())).toBe(0);
  });

  it("4b. (C9) publish después de markActivityRead → unread 1", () => {
    markActivityRead();
    publishActivity(evt({ key: "run:2", ts: Date.now() + 100000 }));
    expect(unreadCount(getActivitySnapshot())).toBe(1);
  });

  it("5. dedup end-to-end: publicar run:1 dos veces → 1 evento", () => {
    publishActivity(evt({ key: "run:1", ts: 100 }));
    publishActivity(evt({ key: "run:1", ts: 200 }));
    expect(getActivitySnapshot().events).toHaveLength(1);
  });

  it("6. tope: publicar 60 eventos → snapshot con 50", () => {
    for (let i = 0; i < 60; i++) publishActivity(evt({ key: `run:${i}`, ts: i }));
    expect(getActivitySnapshot().events).toHaveLength(50);
  });

  it("7. extensibilidad: solo kind run → groupByKind sin error/cost", () => {
    publishActivity(evt({ key: "run:1", kind: "run" }));
    publishActivity(evt({ key: "run:2", kind: "run" }));
    const g = groupByKind(getActivitySnapshot().events);
    expect(Object.keys(g)).toEqual(["run"]);
    expect(g.error).toBeUndefined();
    expect(g.cost).toBeUndefined();
  });

  it("8. mute: setActivityMuted(error,true) descarta el evento error", () => {
    setActivityMuted("error", true);
    publishActivity(evt({ key: "error:1", kind: "error", severity: "error" }));
    expect(getActivitySnapshot().events).toHaveLength(0);
  });

  it("9. persistencia guardada: JSON válido tras publish; localStorage que throw no rompe", () => {
    publishActivity(evt({ key: "run:1", ts: 100 }));
    const raw = (globalThis as any).localStorage.getItem(LS_STATE_KEY);
    expect(raw).toBeTruthy();
    expect(() => JSON.parse(raw)).not.toThrow();

    // localStorage forzado a throw en setItem: publishActivity no debe romper.
    (globalThis as any).localStorage = {
      getItem: () => null,
      setItem: () => { throw new Error("cuota"); },
      removeItem: () => {},
    };
    __resetActivityForTests();
    expect(() => publishActivity(evt({ key: "run:2", ts: 200 }))).not.toThrow();
    expect(getActivitySnapshot().events).toHaveLength(1);
  });
});
