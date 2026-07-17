import { describe, it, expect } from "vitest";
import {
  formatRelativeTime,
  formatDate,
  formatTime,
  formatDateTime,
  formatDuration,
  formatCostUsd,
  formatTokens,
  formatInt,
  formatBytes,
  formatPercent,
  formatDurationBetween,
} from "./format";

describe("format.ts (plan 161 F0)", () => {
  describe("formatDate", () => {
    it("null/undefined/vacío/inválido -> —", () => {
      expect(formatDate(null, "utc")).toBe("—");
      expect(formatDate(undefined, "utc")).toBe("—");
      expect(formatDate("", "utc")).toBe("—");
      expect(formatDate("no-es-fecha", "utc")).toBe("—");
    });

    it("2026-07-03T14:03:27Z utc -> 3 jul 2026", () => {
      expect(formatDate("2026-07-03T14:03:27Z", "utc")).toBe("3 jul 2026");
    });

    it("2026-12-31T23:59:59Z utc -> 31 dic 2026", () => {
      expect(formatDate("2026-12-31T23:59:59Z", "utc")).toBe("31 dic 2026");
    });

    it("date-only 2026-07-03 utc -> 3 jul 2026", () => {
      expect(formatDate("2026-07-03", "utc")).toBe("3 jul 2026");
    });

    it("date-only 2026-07-03 local -> 3 jul 2026 (determinista en cualquier zona, C2)", () => {
      expect(formatDate("2026-07-03", "local")).toBe("3 jul 2026");
    });
  });

  describe("formatTime", () => {
    it("null/inválido -> —", () => {
      expect(formatTime(null)).toBe("—");
      expect(formatTime("x")).toBe("—");
    });

    it("2026-07-03T09:05:07Z utc -> 09:05:07", () => {
      expect(formatTime("2026-07-03T09:05:07Z", "utc")).toBe("09:05:07");
    });
  });

  describe("formatDateTime", () => {
    it("null/inválido -> —", () => {
      expect(formatDateTime(null)).toBe("—");
      expect(formatDateTime("x")).toBe("—");
    });

    it("2026-07-03T14:03:27Z utc -> 3 jul 2026 14:03", () => {
      expect(formatDateTime("2026-07-03T14:03:27Z", "utc")).toBe("3 jul 2026 14:03");
    });

    it("2026-01-09T05:07:00Z utc -> 9 ene 2026 05:07", () => {
      expect(formatDateTime("2026-01-09T05:07:00Z", "utc")).toBe("9 ene 2026 05:07");
    });

    it("2026-07-03T14:03:27Z local (default) matchea shape D mes YYYY HH:mm", () => {
      expect(formatDateTime("2026-07-03T14:03:27Z")).toMatch(/^\d{1,2} [a-z]{3} \d{4} \d{2}:\d{2}$/);
    });
  });

  describe("formatDuration", () => {
    it("null/undefined/NaN/-1 -> —", () => {
      expect(formatDuration(null)).toBe("—");
      expect(formatDuration(undefined)).toBe("—");
      expect(formatDuration(NaN)).toBe("—");
      expect(formatDuration(-1)).toBe("—");
    });

    it("0 -> 0ms", () => {
      expect(formatDuration(0)).toBe("0ms");
    });

    it("850 -> 850ms", () => {
      expect(formatDuration(850)).toBe("850ms");
    });

    it("1000 -> 1.0s", () => {
      expect(formatDuration(1000)).toBe("1.0s");
    });

    it("59940 -> 59.9s", () => {
      expect(formatDuration(59_940)).toBe("59.9s");
    });

    it("59960 -> 1m 0s", () => {
      expect(formatDuration(59_960)).toBe("1m 0s");
    });

    it("61000 -> 1m 1s", () => {
      expect(formatDuration(61_000)).toBe("1m 1s");
    });

    it("245000 -> 4m 5s", () => {
      expect(formatDuration(245_000)).toBe("4m 5s");
    });

    it("3600000 -> 1h 0m", () => {
      expect(formatDuration(3_600_000)).toBe("1h 0m");
    });

    it("5430000 -> 1h 30m", () => {
      expect(formatDuration(5_430_000)).toBe("1h 30m");
    });

    it("90000000 -> 25h 0m", () => {
      expect(formatDuration(90_000_000)).toBe("25h 0m");
    });
  });

  describe("formatCostUsd", () => {
    it("null/undefined/NaN -> —", () => {
      expect(formatCostUsd(null)).toBe("—");
      expect(formatCostUsd(undefined)).toBe("—");
      expect(formatCostUsd(NaN)).toBe("—");
    });

    it("0 -> $0.00", () => {
      expect(formatCostUsd(0)).toBe("$0.00");
    });

    it("0.0042 -> $0.0042", () => {
      expect(formatCostUsd(0.0042)).toBe("$0.0042");
    });

    it("0.42 -> $0.42", () => {
      expect(formatCostUsd(0.42)).toBe("$0.42");
    });

    it("12.5 -> $12.50", () => {
      expect(formatCostUsd(12.5)).toBe("$12.50");
    });

    it("1234.567 -> $1234.57", () => {
      expect(formatCostUsd(1234.567)).toBe("$1234.57");
    });

    it("-0.5 -> -$0.50", () => {
      expect(formatCostUsd(-0.5)).toBe("-$0.50");
    });

    it("-0.005 -> -$0.0050", () => {
      expect(formatCostUsd(-0.005)).toBe("-$0.0050");
    });
  });

  describe("formatTokens", () => {
    it("null/NaN -> —", () => {
      expect(formatTokens(null)).toBe("—");
      expect(formatTokens(NaN)).toBe("—");
    });

    it("0 -> 0", () => {
      expect(formatTokens(0)).toBe("0");
    });

    it("500 -> 500", () => {
      expect(formatTokens(500)).toBe("500");
    });

    it("999 -> 999", () => {
      expect(formatTokens(999)).toBe("999");
    });

    it("12345 -> 12.3k", () => {
      expect(formatTokens(12_345)).toBe("12.3k");
    });

    it("1234567 -> 1.2M", () => {
      expect(formatTokens(1_234_567)).toBe("1.2M");
    });

    it("-2500 -> -2.5k", () => {
      expect(formatTokens(-2500)).toBe("-2.5k");
    });
  });

  describe("formatInt", () => {
    it("null/NaN -> —", () => {
      expect(formatInt(null)).toBe("—");
      expect(formatInt(NaN)).toBe("—");
    });

    it("0 -> 0", () => {
      expect(formatInt(0)).toBe("0");
    });

    it("999 -> 999", () => {
      expect(formatInt(999)).toBe("999");
    });

    it("12345 -> 12.345", () => {
      expect(formatInt(12_345)).toBe("12.345");
    });

    it("1234567 -> 1.234.567", () => {
      expect(formatInt(1_234_567)).toBe("1.234.567");
    });

    it("-12345 -> -12.345", () => {
      expect(formatInt(-12_345)).toBe("-12.345");
    });

    it("1234.9 -> 1.234 (trunc)", () => {
      expect(formatInt(1234.9)).toBe("1.234");
    });
  });

  describe("formatBytes", () => {
    it("null/NaN/-1 -> —", () => {
      expect(formatBytes(null)).toBe("—");
      expect(formatBytes(NaN)).toBe("—");
      expect(formatBytes(-1)).toBe("—");
    });

    it("0 -> 0 B", () => {
      expect(formatBytes(0)).toBe("0 B");
    });

    it("512 -> 512 B", () => {
      expect(formatBytes(512)).toBe("512 B");
    });

    it("1536 -> 1.5 KB", () => {
      expect(formatBytes(1536)).toBe("1.5 KB");
    });

    it("1048576 -> 1.0 MB", () => {
      expect(formatBytes(1_048_576)).toBe("1.0 MB");
    });

    it("3221225472 -> 3.0 GB", () => {
      expect(formatBytes(3_221_225_472)).toBe("3.0 GB");
    });
  });

  describe("formatPercent", () => {
    it("null/NaN -> —", () => {
      expect(formatPercent(null)).toBe("—");
      expect(formatPercent(NaN)).toBe("—");
    });

    it("85 -> 85%", () => {
      expect(formatPercent(85)).toBe("85%");
    });

    it("85.34 decimals=1 -> 85.3%", () => {
      expect(formatPercent(85.34, 1)).toBe("85.3%");
    });

    it("0 -> 0%", () => {
      expect(formatPercent(0)).toBe("0%");
    });

    it("-5 -> -5%", () => {
      expect(formatPercent(-5)).toBe("-5%");
    });
  });

  describe("formatDurationBetween", () => {
    it("null o inválido en start -> —", () => {
      expect(formatDurationBetween(null, "2026-07-03T00:00:00Z")).toBe("—");
      expect(formatDurationBetween("no-es-fecha", "2026-07-03T00:00:00Z")).toBe("—");
    });

    it("(00:00:00, 00:04:05) -> 4m 5s", () => {
      expect(formatDurationBetween("2026-07-03T00:00:00Z", "2026-07-03T00:04:05Z")).toBe("4m 5s");
    });

    it("fin < inicio -> —", () => {
      expect(formatDurationBetween("2026-07-03T01:00:00Z", "2026-07-03T00:00:00Z")).toBe("—");
    });
  });

  describe("formatRelativeTime (re-export)", () => {
    it("resuelve el re-export con el contrato ya congelado", () => {
      expect(formatRelativeTime("2026-07-17T11:59:30Z", Date.parse("2026-07-17T12:00:00Z"))).toBe("recién");
    });
  });
});
