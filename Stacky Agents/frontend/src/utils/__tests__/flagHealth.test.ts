import { describe, expect, it, vi } from "vitest";
import { interpretFlagHealthResponse, nextEnabledState, probeFlagHealth } from "../flagHealth";

describe("interpretFlagHealthResponse (plan 135 F0)", () => {
  it("interpreta flag_enabled true/false y todo lo demás como unknown", () => {
    expect(interpretFlagHealthResponse({ flag_enabled: true })).toBe("enabled");
    expect(interpretFlagHealthResponse({ flag_enabled: false })).toBe("disabled");
    expect(interpretFlagHealthResponse({})).toBe("unknown");
    expect(interpretFlagHealthResponse(null)).toBe("unknown");
    expect(interpretFlagHealthResponse("x")).toBe("unknown");
    expect(interpretFlagHealthResponse({ flag_enabled: "true" })).toBe("unknown");
  });
});

describe("nextEnabledState (plan 135 F0)", () => {
  it("es sticky ante unknown", () => {
    expect(nextEnabledState(true, "enabled")).toBe(true);
    expect(nextEnabledState(true, "disabled")).toBe(false);
    expect(nextEnabledState(true, "unknown")).toBe(true);
    expect(nextEnabledState(false, "enabled")).toBe(true);
    expect(nextEnabledState(false, "disabled")).toBe(false);
    expect(nextEnabledState(false, "unknown")).toBe(false);
  });
});

describe("probeFlagHealth (plan 135 F0)", () => {
  it("devuelve enabled al primer intento sin dormir", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({ json: async () => ({ flag_enabled: true }) });
    const sleepImpl = vi.fn().mockResolvedValue(undefined);
    const v = await probeFlagHealth("/x", { fetchImpl, sleepImpl });
    expect(v).toBe("enabled");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(sleepImpl).toHaveBeenCalledTimes(0);
  });

  it("reintenta ante rechazo de red y acepta el veredicto tardío", async () => {
    const fetchImpl = vi
      .fn()
      .mockRejectedValueOnce(new Error("net"))
      .mockRejectedValueOnce(new Error("net"))
      .mockResolvedValueOnce({ json: async () => ({ flag_enabled: false }) });
    const sleepImpl = vi.fn().mockResolvedValue(undefined);
    const v = await probeFlagHealth("/x", { fetchImpl, sleepImpl });
    expect(v).toBe("disabled");
    expect(fetchImpl).toHaveBeenCalledTimes(3);
    expect(sleepImpl.mock.calls.map((c) => c[0])).toEqual([400, 800]);
  });

  it("agota los reintentos y devuelve unknown", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new Error("net"));
    const sleepImpl = vi.fn().mockResolvedValue(undefined);
    const v = await probeFlagHealth("/x", { fetchImpl, sleepImpl, retries: 2 });
    expect(v).toBe("unknown");
    expect(fetchImpl).toHaveBeenCalledTimes(3);
  });

  it("JSON válido sin flag_enabled también se reintenta", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({ json: async () => ({}) });
    const sleepImpl = vi.fn().mockResolvedValue(undefined);
    const v = await probeFlagHealth("/x", { fetchImpl, sleepImpl });
    expect(v).toBe("unknown");
    expect(fetchImpl).toHaveBeenCalledTimes(3);
  });
});
