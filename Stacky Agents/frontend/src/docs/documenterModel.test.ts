import { describe, it, expect } from "vitest";
import { summarizeDocumenterStatus, healthDelta } from "./documenterModel";
import type { DocumenterStatusResponse } from "../api/endpoints";

describe("summarizeDocumenterStatus", () => {
  it("summarizeDocumenterStatus_maps_states", () => {
    const running = summarizeDocumenterStatus({ ok: true, state: "running" });
    expect(running.uiState).toBe("running");
    expect(running.running).toBe(true);

    const done = summarizeDocumenterStatus({ ok: true, state: "completed" });
    expect(done.uiState).toBe("completed");

    const decided = summarizeDocumenterStatus({ ok: true, state: "decided_keep" });
    expect(decided.uiState).toBe("decided");

    const unknown = summarizeDocumenterStatus(null);
    expect(unknown.uiState).toBe("unknown");
  });

  it("summarizeDocumenterStatus_flags_degraded", () => {
    const s: DocumenterStatusResponse = {
      ok: true, state: "completed", degraded: true,
      written: ["a.md", "b.md"], skipped: [["c.md", "canonical_readonly"]],
      branch: null, diff_stat: "",
    };
    const sum = summarizeDocumenterStatus(s);
    expect(sum.degraded).toBe(true);
    expect(sum.writtenCount).toBe(2);
    expect(sum.skippedCount).toBe(1);
  });
});

describe("healthDelta", () => {
  it("healthDelta_describes_improvement", () => {
    expect(healthDelta({ status: "SIN_DOCS" }, { status: "INCOMPLETA" })).toBe(
      "SIN_DOCS → INCOMPLETA"
    );
    expect(healthDelta({ status: "SANA" }, { status: "SANA" })).toContain("Sin cambio");
    expect(healthDelta(null, { status: "SANA" })).toBe("");
  });
});
