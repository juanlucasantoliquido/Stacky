import { describe, expect, it } from "vitest";
import { formatStallReason } from "../stallReason";

describe("formatStallReason (plan 144 F4)", () => {
  it("null/undefined → null", () => {
    expect(formatStallReason(null)).toBeNull();
    expect(formatStallReason(undefined)).toBeNull();
  });

  it("stall con watchdog_seconds y last_signal → contiene ambos", () => {
    const msg = formatStallReason({ watchdog_seconds: 600, last_signal: "tool_use:Read" });
    expect(msg).toContain("600s");
    expect(msg).toContain("tool_use:Read");
  });

  it("last_signal 'none' → contiene 'Sin señales previas'", () => {
    const msg = formatStallReason({ watchdog_seconds: 600, last_signal: "none" });
    expect(msg).toContain("Sin señales previas");
  });

  it("trust_ok false → contiene 'workspace no confiado'", () => {
    const msg = formatStallReason({ watchdog_seconds: 600, last_signal: "none", trust_ok: false });
    expect(msg).toContain("workspace no confiado");
  });
});
