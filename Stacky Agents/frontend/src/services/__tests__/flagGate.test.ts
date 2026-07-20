/**
 * flagGate.test.ts — Plan 197 §6.1 (contrato mínimo C7).
 * 5 casos de flagEnabledFrom (187 K6 generalizados por key) + 2 de cache.
 * Correr POR ARCHIVO: npx vitest run src/services/__tests__/flagGate.test.ts
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock del módulo de endpoints ANTES de importar flagGate (hoisted por vitest).
vi.mock("../../api/endpoints", () => ({
  HarnessFlags: { list: vi.fn() },
}));

import { flagEnabledFrom, getBoolFlag, readCachedBoolFlag, resetFlagGateCache } from "../flagGate";
import { HarnessFlags } from "../../api/endpoints";

const KEY = "STACKY_SOME_FLAG_ENABLED";

describe("flagGate.flagEnabledFrom (187 K6 generalizado)", () => {
  it("off_cuando_value_false_literal", () => {
    expect(flagEnabledFrom([{ key: KEY, value: false }], KEY)).toBe(false);
  });
  it("on_cuando_value_true", () => {
    expect(flagEnabledFrom([{ key: KEY, value: true }], KEY)).toBe(true);
  });
  it("on_cuando_key_ausente", () => {
    expect(flagEnabledFrom([{ key: "OTRA", value: false }], KEY)).toBe(true);
  });
  it("on_cuando_flags_undefined_o_null", () => {
    expect(flagEnabledFrom(undefined, KEY)).toBe(true);
    expect(flagEnabledFrom(null, KEY)).toBe(true);
    expect(flagEnabledFrom([], KEY)).toBe(true);
  });
  it("on_cuando_value_string_false", () => {
    // fail-open: SOLO el boolean false literal apaga (un string "false" NO).
    expect(flagEnabledFrom([{ key: KEY, value: "false" }], KEY)).toBe(true);
  });
});

describe("flagGate cache", () => {
  beforeEach(() => {
    resetFlagGateCache();
    vi.mocked(HarnessFlags.list).mockReset();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("getBoolFlag hace UNA sola llamada a HarnessFlags.list ante N invocaciones", async () => {
    vi.mocked(HarnessFlags.list).mockResolvedValue({
      ok: true,
      flags: [{ key: KEY, value: true }],
      active_profile: null,
      categories: [],
    } as never);
    const [a, b, c] = await Promise.all([getBoolFlag(KEY), getBoolFlag(KEY), getBoolFlag(KEY)]);
    expect(a).toBe(true);
    expect(b).toBe(true);
    expect(c).toBe(true);
    expect(HarnessFlags.list).toHaveBeenCalledTimes(1);
  });

  it("readCachedBoolFlag devuelve true (fail-open) sin localStorage disponible", () => {
    // vitest node no define localStorage ⇒ typeof localStorage === "undefined".
    expect(readCachedBoolFlag(KEY)).toBe(true);
  });
});
