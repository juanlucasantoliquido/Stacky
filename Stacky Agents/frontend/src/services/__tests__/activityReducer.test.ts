import { describe, expect, it } from "vitest";
import {
  ACTIVITY_CAP,
  appendEvent,
  emptyState,
  groupByKind,
  hydrateState,
  isMuted,
  markAllRead,
  serializeState,
  setMuted,
  severityFromRunStatus,
  unreadCount,
  type ActivityEvent,
  type ActivityState,
} from "../activityReducer";

function evt(over: Partial<ActivityEvent> = {}): ActivityEvent {
  return {
    key: "run:1",
    kind: "run",
    severity: "info",
    title: "t",
    ts: 1000,
    ...over,
  };
}

describe("appendEvent (plan 152 F0)", () => {
  it("1. key nueva agrega y ordena desc por ts", () => {
    let s = emptyState();
    s = appendEvent(s, evt({ key: "run:1", ts: 100 }));
    s = appendEvent(s, evt({ key: "run:2", ts: 300 }));
    s = appendEvent(s, evt({ key: "run:3", ts: 200 }));
    expect(s.events.map((e) => e.key)).toEqual(["run:2", "run:3", "run:1"]);
  });

  it("2. key duplicada NO duplica y conserva el ts más nuevo", () => {
    let s = emptyState();
    s = appendEvent(s, evt({ key: "run:1", ts: 100, title: "viejo" }));
    s = appendEvent(s, evt({ key: "run:1", ts: 500, title: "nuevo" }));
    expect(s.events).toHaveLength(1);
    expect(s.events[0].ts).toBe(500);
    expect(s.events[0].title).toBe("nuevo");
  });

  it("3. respeta ACTIVITY_CAP=50 (51 eventos → longitud 50, cae el más viejo)", () => {
    let s = emptyState();
    for (let i = 0; i < 51; i++) {
      s = appendEvent(s, evt({ key: `run:${i}`, ts: i }));
    }
    expect(ACTIVITY_CAP).toBe(50);
    expect(s.events).toHaveLength(50);
    // el más viejo (ts=0) se descartó
    expect(s.events.some((e) => e.key === "run:0")).toBe(false);
    expect(s.events.some((e) => e.key === "run:50")).toBe(true);
  });
});

describe("unreadCount / markAllRead (plan 152 F0)", () => {
  it("4. cuenta solo ts > lastReadAt (borde ts === lastReadAt → leído)", () => {
    let s: ActivityState = { events: [], lastReadAt: 200, muted: [] };
    s = appendEvent(s, evt({ key: "a", ts: 100 })); // leído
    s = appendEvent(s, evt({ key: "b", ts: 200 })); // borde → leído
    s = appendEvent(s, evt({ key: "c", ts: 300 })); // no leído
    expect(unreadCount(s)).toBe(1);
  });

  it("5. markAllRead deja unreadCount === 0", () => {
    let s = emptyState();
    s = appendEvent(s, evt({ key: "a", ts: 100 }));
    s = appendEvent(s, evt({ key: "b", ts: 300 }));
    expect(unreadCount(s)).toBeGreaterThan(0);
    s = markAllRead(s, 400);
    expect(unreadCount(s)).toBe(0);
  });
});

describe("groupByKind (plan 152 F0/§4.5)", () => {
  it("6. eventos solo run → sin claves error/cost", () => {
    const events = [evt({ key: "run:1", kind: "run" }), evt({ key: "run:2", kind: "run" })];
    const g = groupByKind(events);
    expect(Object.keys(g)).toEqual(["run"]);
    expect(g.error).toBeUndefined();
    expect(g.cost).toBeUndefined();
  });
});

describe("isMuted / setMuted (plan 152 F0)", () => {
  it("7. round-trip", () => {
    let s = emptyState();
    expect(isMuted(s, "error")).toBe(false);
    s = setMuted(s, "error", true);
    expect(isMuted(s, "error")).toBe(true);
    s = setMuted(s, "error", false);
    expect(isMuted(s, "error")).toBe(false);
  });
});

describe("severityFromRunStatus (plan 152 F0/C8)", () => {
  it("8. error→error, needs_review→attention, completed→success, cancelled→info", () => {
    expect(severityFromRunStatus("error")).toBe("error");
    expect(severityFromRunStatus("needs_review")).toBe("attention");
    expect(severityFromRunStatus("completed")).toBe("success");
    expect(severityFromRunStatus("cancelled")).toBe("info");
    expect(severityFromRunStatus("whatever")).toBe("info");
  });
});

describe("hydrateState / serializeState (plan 152 F0)", () => {
  it("9. hydrateState(null) y hydrateState('{corrupto') → emptyState() sin throw", () => {
    expect(() => hydrateState(null)).not.toThrow();
    expect(hydrateState(null)).toEqual(emptyState());
    expect(() => hydrateState("{corrupto")).not.toThrow();
    expect(hydrateState("{corrupto")).toEqual(emptyState());
  });

  it("10. serializeState→hydrateState round-trip preserva orden y recorta a 50", () => {
    let s = emptyState();
    for (let i = 0; i < 60; i++) {
      s = appendEvent(s, evt({ key: `run:${i}`, ts: i }));
    }
    s = markAllRead(s, 999);
    s = setMuted(s, "cost", true);
    const round = hydrateState(serializeState(s));
    expect(round.events).toHaveLength(50);
    expect(round.events.map((e) => e.key)).toEqual(s.events.map((e) => e.key));
    expect(round.lastReadAt).toBe(999);
    expect(round.muted).toContain("cost");
  });
});
