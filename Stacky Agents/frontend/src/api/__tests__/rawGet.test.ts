// Plan 238 F3 — rawGet: GET que NO lanza en 4xx/5xx y preserva el cuerpo.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("../../services/connectionMonitor", () => ({
  GATEWAY_DOWN_STATUSES: new Set([502, 503, 504]),
  reportConnectionSuccess: () => {},
  reportConnectionFailure: () => {},
}));

import { rawGet } from "../client";

function stubFetch(status: number, body: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: status >= 200 && status < 300,
      status,
      text: async () => body,
    })),
  );
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("rawGet", () => {
  it("devuelve ok:true y data en 200", async () => {
    stubFetch(200, JSON.stringify({ ok: true, a: 1 }));
    const r = await rawGet<{ ok: boolean; a: number }>("/api/x");
    expect(r.ok).toBe(true);
    expect(r.status).toBe(200);
    expect(r.data).toEqual({ ok: true, a: 1 });
    expect(r.errorBody).toBeNull();
  });

  it("devuelve ok:false y errorBody en 404 sin lanzar", async () => {
    stubFetch(404, JSON.stringify({ ok: false, error: "feature_disabled" }));
    const r = await rawGet<unknown>("/api/x");
    expect(r.ok).toBe(false);
    expect(r.status).toBe(404);
    expect(r.errorBody?.error).toBe("feature_disabled");
    expect(r.data).toBeNull();
  });

  it("body no-JSON en error se expone como message", async () => {
    stubFetch(500, "boom");
    const r = await rawGet<unknown>("/api/x");
    expect(r.ok).toBe(false);
    expect(r.errorBody?.message).toBe("boom");
  });

  it("body vacio en 200 deja data null", async () => {
    stubFetch(200, "");
    const r = await rawGet<unknown>("/api/x");
    expect(r.ok).toBe(true);
    expect(r.data).toBeNull();
  });

  it("error de red re-lanza", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("network down"); }));
    await expect(rawGet<unknown>("/api/x")).rejects.toThrow();
  });
});
