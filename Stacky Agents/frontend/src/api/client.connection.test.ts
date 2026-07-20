import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Espiar los reportes del monitor sin arrastrar su singleton/browser APIs.
// El mock DEBE re-exportar GATEWAY_DOWN_STATUSES porque client.ts la importa (C8).
vi.mock("../services/connectionMonitor", () => ({
  GATEWAY_DOWN_STATUSES: new Set([502, 503, 504]),
  reportConnectionSuccess: vi.fn(),
  reportConnectionFailure: vi.fn(),
}));

import { api, rawPost } from "./client";
import {
  reportConnectionSuccess,
  reportConnectionFailure,
} from "../services/connectionMonitor";

const okSpy = reportConnectionSuccess as unknown as ReturnType<typeof vi.fn>;
const failSpy = reportConnectionFailure as unknown as ReturnType<typeof vi.fn>;

function res(opts: {
  ok: boolean;
  status: number;
  statusText?: string;
  json?: unknown;
  text?: string;
}) {
  return {
    ok: opts.ok,
    status: opts.status,
    statusText: opts.statusText ?? "",
    json: async () => opts.json ?? {},
    text: async () => opts.text ?? "",
  } as unknown as Response;
}

beforeEach(() => {
  okSpy.mockReset();
  failSpy.mockReset();
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("client.ts interceptor de conexion (Plan 192 F2)", () => {
  it("c1: api.get 200 JSON => reportConnectionSuccess 1; devuelve el JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ ok: true, status: 200, json: { hello: "world" } })));
    const out = await api.get<{ hello: string }>("/x");
    expect(out).toEqual({ hello: "world" });
    expect(okSpy).toHaveBeenCalledTimes(1);
    expect(failSpy).not.toHaveBeenCalled();
  });

  it("c2: api.get fetch rechaza TypeError => reportConnectionFailure 1; mismo error relanzado", async () => {
    const err = new TypeError("Failed to fetch");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(err));
    await expect(api.get("/x")).rejects.toBe(err);
    expect(failSpy).toHaveBeenCalledTimes(1);
    expect(okSpy).not.toHaveBeenCalled();
  });

  it("c3: api.get rechaza AbortError => NINGUN reporte de fallo; error relanzado", async () => {
    const err = new DOMException("aborted", "AbortError");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(err));
    await expect(api.get("/x")).rejects.toBe(err);
    expect(failSpy).not.toHaveBeenCalled();
    expect(okSpy).not.toHaveBeenCalled();
  });

  it("c4: api.get 503 => reportConnectionFailure 1; lanza el mismo Error de hoy", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ ok: false, status: 503, statusText: "Service Unavailable", text: "down" })));
    await expect(api.get("/x")).rejects.toThrow(/503/);
    expect(failSpy).toHaveBeenCalledTimes(1);
    expect(okSpy).not.toHaveBeenCalled();
  });

  it("c5: api.get 500 => reportConnectionSuccess 1 (backend vivo); lanza como hoy (K6 sin retry)", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(res({ ok: false, status: 500, statusText: "Server Error", text: "boom" }));
    vi.stubGlobal("fetch", fetchSpy);
    await expect(api.get("/x")).rejects.toThrow(/500/);
    expect(okSpy).toHaveBeenCalledTimes(1);
    expect(failSpy).not.toHaveBeenCalled();
    expect(fetchSpy).toHaveBeenCalledTimes(1); // sin reintento
  });

  it("c6: api.post (mutacion) rechaza => reportConnectionFailure 1; error relanzado; fetch 1 sola vez (K6)", async () => {
    const err = new TypeError("Failed to fetch");
    const fetchSpy = vi.fn().mockRejectedValue(err);
    vi.stubGlobal("fetch", fetchSpy);
    await expect(api.post("/x", { a: 1 })).rejects.toBe(err);
    expect(failSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledTimes(1); // cero reintentos de mutacion
  });

  it("c7: rawPost 200 => success reportado, RawResponse intacto", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ ok: true, status: 200, text: JSON.stringify({ id: 7 }) })));
    const out = await rawPost<{ id: number }>("/x", { a: 1 });
    expect(out.ok).toBe(true);
    expect(out.status).toBe(200);
    expect(out.data).toEqual({ id: 7 });
    expect(okSpy).toHaveBeenCalledTimes(1);
  });

  it("c7b: rawPost rechaza TypeError => failure reportado; error relanzado", async () => {
    const err = new TypeError("Failed to fetch");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(err));
    await expect(rawPost("/x", { a: 1 })).rejects.toBe(err);
    expect(failSpy).toHaveBeenCalledTimes(1);
  });
});
