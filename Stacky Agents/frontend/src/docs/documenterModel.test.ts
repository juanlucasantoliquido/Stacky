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

  it("summarizeDocumenterStatus_exposes_current_execution_id", () => {
    // Fix "no me hizo nada" (Tarea 2) — necesario para enganchar la consola en vivo.
    const running = summarizeDocumenterStatus({
      ok: true, state: "running", current_execution_id: 123,
    });
    expect(running.currentExecutionId).toBe(123);

    const noExec = summarizeDocumenterStatus({ ok: true, state: "running" });
    expect(noExec.currentExecutionId).toBeNull();
  });

  it("summarizeDocumenterStatus_exposes_error_message", () => {
    // Fix "no me hizo nada" (Tarea 1) — antes era 100% silencioso.
    const failed = summarizeDocumenterStatus({
      ok: true, state: "completed", written: [], skipped: [],
      error: "ENRIQUECER: ejecución 42 terminó en 'error': config faltante",
    });
    expect(failed.errorMessage).toContain("config faltante");

    const ok = summarizeDocumenterStatus({ ok: true, state: "completed" });
    expect(ok.errorMessage).toBeNull();
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
