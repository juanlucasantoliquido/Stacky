import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// flagGate (envuelto por connectionFlags) lee HarnessFlags.list de ../api/endpoints.
vi.mock("../api/endpoints", () => ({
  HarnessFlags: { list: vi.fn() },
}));

import { HarnessFlags } from "../api/endpoints";
import {
  isConnectionResilienceEnabled,
  readCachedConnectionFlag,
  _resetForTests,
} from "./connectionFlags";

const KEY = "STACKY_CONNECTION_RESILIENCE_ENABLED";
const CACHE_KEY = "stacky.flag." + KEY;
const listMock = HarnessFlags.list as unknown as ReturnType<typeof vi.fn>;

function fakeLocalStorage() {
  const m = new Map<string, string>();
  return {
    getItem: (k: string) => (m.has(k) ? m.get(k)! : null),
    setItem: (k: string, v: string) => {
      m.set(k, v);
    },
    removeItem: (k: string) => {
      m.delete(k);
    },
    _map: m,
  };
}

beforeEach(() => {
  _resetForTests();
  listMock.mockReset();
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("connectionFlags (wrapper de flagGate — Plan 192 F2)", () => {
  it("flag presente value:false => false", async () => {
    listMock.mockResolvedValue({ flags: [{ key: KEY, value: false }] });
    expect(await isConnectionResilienceEnabled()).toBe(false);
  });

  it("flag presente value:true => true", async () => {
    listMock.mockResolvedValue({ flags: [{ key: KEY, value: true }] });
    expect(await isConnectionResilienceEnabled()).toBe(true);
  });

  it("key ausente => true (fail-open)", async () => {
    listMock.mockResolvedValue({ flags: [{ key: "OTRA", value: false }] });
    expect(await isConnectionResilienceEnabled()).toBe(true);
  });

  it("list() rechaza => true (fail-open, backend caido)", async () => {
    listMock.mockRejectedValue(new Error("network down"));
    expect(await isConnectionResilienceEnabled()).toBe(true);
  });

  it("promesa cacheada: 2 invocaciones => 1 sola llamada a HarnessFlags.list", async () => {
    listMock.mockResolvedValue({ flags: [{ key: KEY, value: true }] });
    const [a, b] = await Promise.all([
      isConnectionResilienceEnabled(),
      isConnectionResilienceEnabled(),
    ]);
    expect(a).toBe(true);
    expect(b).toBe(true);
    expect(listMock).toHaveBeenCalledTimes(1);
  });

  it("_resetForTests limpia el cache (nueva request tras reset)", async () => {
    listMock.mockResolvedValue({ flags: [{ key: KEY, value: true }] });
    await isConnectionResilienceEnabled();
    _resetForTests();
    await isConnectionResilienceEnabled();
    expect(listMock).toHaveBeenCalledTimes(2);
  });

  it("readCachedConnectionFlag lee '0'/'1' del cache localStorage (C10)", () => {
    const ls = fakeLocalStorage();
    vi.stubGlobal("localStorage", ls);
    ls.setItem(CACHE_KEY, "0");
    expect(readCachedConnectionFlag()).toBe(false);
    ls.setItem(CACHE_KEY, "1");
    expect(readCachedConnectionFlag()).toBe(true);
    ls.removeItem(CACHE_KEY);
    expect(readCachedConnectionFlag()).toBe(true); // sin cache => fail-open
  });

  it("readCachedConnectionFlag sin localStorage disponible => true (fail-open, C10)", () => {
    // vitest node no tiene localStorage: el try/catch cae al default true sin lanzar
    expect(readCachedConnectionFlag()).toBe(true);
  });
});
