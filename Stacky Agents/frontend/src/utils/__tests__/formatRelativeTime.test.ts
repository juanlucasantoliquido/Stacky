import { describe, it, expect } from "vitest";
import { formatRelativeTime } from "../formatRelativeTime";

const NOW = Date.parse("2026-07-15T12:00:00.000Z");
const before = (sec: number) => new Date(NOW - sec * 1000).toISOString();

describe("Plan 140 F0 — formatRelativeTime (puro)", () => {
  it("iso vacío/null/undefined -> —", () => {
    expect(formatRelativeTime("", NOW)).toBe("—");
    expect(formatRelativeTime(null, NOW)).toBe("—");
    expect(formatRelativeTime(undefined, NOW)).toBe("—");
  });
  it("iso inválido -> —", () => {
    expect(formatRelativeTime("no-es-fecha", NOW)).toBe("—");
  });
  it("futuro -> recién", () => {
    expect(formatRelativeTime(before(-120), NOW)).toBe("recién");
  });
  it("< 60s -> recién", () => {
    expect(formatRelativeTime(before(59), NOW)).toBe("recién");
  });
  it("frontera 60s -> hace 1 min", () => {
    expect(formatRelativeTime(before(60), NOW)).toBe("hace 1 min");
  });
  it("< 60min -> hace 59 min", () => {
    expect(formatRelativeTime(before(59 * 60), NOW)).toBe("hace 59 min");
  });
  it("frontera 60min -> hace 1 h", () => {
    expect(formatRelativeTime(before(3600), NOW)).toBe("hace 1 h");
  });
  it("< 24h -> hace 23 h", () => {
    expect(formatRelativeTime(before(23 * 3600), NOW)).toBe("hace 23 h");
  });
  it("frontera 24h -> hace 1 d", () => {
    expect(formatRelativeTime(before(86400), NOW)).toBe("hace 1 d");
  });
  it("< 7d -> hace 6 d", () => {
    expect(formatRelativeTime(before(6 * 86400), NOW)).toBe("hace 6 d");
  });
  it("frontera 7d -> fecha absoluta UTC", () => {
    expect(formatRelativeTime(before(7 * 86400), NOW)).toBe("8 jul 2026");
  });
  it("mucho tiempo atrás -> fecha absoluta UTC", () => {
    expect(formatRelativeTime("2026-01-03T00:00:00.000Z", NOW)).toBe("3 ene 2026");
  });
});
