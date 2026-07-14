import { describe, it, expect } from "vitest";
import { isTerminal, nextPollDelayMs } from "../useCompareRun";

describe("Plan 124 F1 — useCompareRun (pure helpers)", () => {
  describe("isTerminal", () => {
    it("done is terminal", () => {
      expect(isTerminal("done")).toBe(true);
    });
    it("error is terminal", () => {
      expect(isTerminal("error")).toBe(true);
    });
    it("running is NOT terminal", () => {
      expect(isTerminal("running")).toBe(false);
    });
    it("unknown status is NOT terminal", () => {
      expect(isTerminal("queued")).toBe(false);
    });
  });

  describe("nextPollDelayMs", () => {
    it("under 10s -> 1000ms", () => {
      expect(nextPollDelayMs(9999)).toBe(1000);
    });
    it("exactly 10000ms -> 2000ms [FIX C5]", () => {
      expect(nextPollDelayMs(10000)).toBe(2000);
    });
    it("under 60s -> 2000ms", () => {
      expect(nextPollDelayMs(59999)).toBe(2000);
    });
    it("exactly 60000ms -> 5000ms", () => {
      expect(nextPollDelayMs(60000)).toBe(5000);
    });
  });
});
