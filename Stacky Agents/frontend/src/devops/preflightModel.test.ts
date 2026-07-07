/**
 * Tests de preflightModel.ts - Plan 93 F4
 * TDD: lógica pura del semáforo de preflight (sin React).
 */
import { describe, it, expect } from "vitest";
import {
  overallStatus,
  sortBySeverity,
  summaryLine,
  type PreflightCheck,
} from "./preflightModel";

function check(id: string, status: PreflightCheck["status"], title = id): PreflightCheck {
  return { id, status, title, detail: "", fix_hint: "" };
}

describe("preflightModel", () => {
  it("overall_fail_wins", () => {
    const checks = [check("a", "ok"), check("b", "warn"), check("c", "fail"), check("d", "unavailable")];
    expect(overallStatus(checks)).toBe("fail");
  });

  it("overall_ok_when_all_ok", () => {
    const checks = [check("a", "ok"), check("b", "ok")];
    expect(overallStatus(checks)).toBe("ok");
  });

  it("sort_by_severity_stable", () => {
    const checks = [check("a", "ok"), check("b", "fail"), check("c", "warn"), check("d", "unavailable")];
    const sorted = sortBySeverity(checks);
    expect(sorted.map((c) => c.id)).toEqual(["b", "c", "d", "a"]);
  });

  it("unavailable_beats_ok", () => {
    const checks = [check("a", "ok"), check("b", "unavailable")];
    expect(overallStatus(checks)).toBe("unavailable");
    const sorted = sortBySeverity(checks);
    expect(sorted[0].id).toBe("b");
  });

  it("summary_line_counts_problems", () => {
    const checks = [
      check("a", "fail", "Runners sin match"),
      check("b", "warn", "1 paso con ejemplo"),
      check("c", "ok"),
    ];
    const line = summaryLine(checks);
    expect(line).toContain("1 problema");
    expect(line).toContain("1 aviso");
  });

  it("summary_line_all_ok", () => {
    const checks = [check("a", "ok"), check("b", "ok")];
    expect(summaryLine(checks)).toBe("Todo verde: el pipeline debería funcionar");
  });
});
