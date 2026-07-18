/**
 * Plan 156 F4 — Tests de los helpers puros del reloj de sync (sin DOM).
 */
import { describe, it, expect } from "vitest";
import { secondsSince, isStaleAt } from "../syncStatus";

describe("syncStatus (plan 156 F4)", () => {
  it("test_secondsSince_null: sin lastSyncedAt → null", () => {
    expect(secondsSince(null)).toBeNull();
    expect(secondsSince(null, 123456)).toBeNull();
  });

  it("test_secondsSince_calcula: now-90s con nowMs fijo → 90", () => {
    const now = 1_000_000_000_000;
    const last = new Date(now - 90_000).toISOString();
    expect(secondsSince(last, now)).toBe(90);
  });

  it("test_isStale_umbral: umbral = intervalMs*2 = 90s", () => {
    const now = 1_000_000_000_000;
    const at91 = new Date(now - 91_000).toISOString();
    const at30 = new Date(now - 30_000).toISOString();
    expect(isStaleAt(at91, 45_000, now)).toBe(true);
    expect(isStaleAt(at30, 45_000, now)).toBe(false);
    expect(isStaleAt(null, 45_000, now)).toBe(false);
  });
});
