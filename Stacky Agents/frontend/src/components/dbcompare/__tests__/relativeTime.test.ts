import { describe, it, expect } from "vitest";
import { relativeTimeEs } from "../relativeTime";

const NOW = "2026-07-14T12:00:00.000Z";

function isoSecondsBefore(seconds: number): string {
  return new Date(new Date(NOW).getTime() - seconds * 1000).toISOString();
}

describe("Plan 124 F6 — relativeTime (pure)", () => {
  it("< 60s -> 'hace segundos'", () => {
    expect(relativeTimeEs(isoSecondsBefore(59), NOW)).toBe("hace segundos");
  });

  it("frontera 60s -> 'hace 1 min'", () => {
    expect(relativeTimeEs(isoSecondsBefore(60), NOW)).toBe("hace 1 min");
  });

  it("< 60min -> 'hace 59 min'", () => {
    expect(relativeTimeEs(isoSecondsBefore(59 * 60), NOW)).toBe("hace 59 min");
  });

  it("frontera 60min -> 'hace 1 h'", () => {
    expect(relativeTimeEs(isoSecondsBefore(60 * 60), NOW)).toBe("hace 1 h");
  });

  it("< 24h -> 'hace 23 h'", () => {
    expect(relativeTimeEs(isoSecondsBefore(23 * 3600), NOW)).toBe("hace 23 h");
  });

  it("frontera 24h -> 'hace 1 d'", () => {
    expect(relativeTimeEs(isoSecondsBefore(24 * 3600), NOW)).toBe("hace 1 d");
  });
});
