import { describe, it, expect } from "vitest";
import { runStatusTone, runStatusLabel } from "../runStatus";

describe("Plan 140 F1 — runStatus (puro)", () => {
  it("completed/success/done -> success + Completado", () => {
    for (const s of ["completed", "success", "done", "COMPLETED", " Done "]) {
      expect(runStatusTone(s)).toBe("success");
      expect(runStatusLabel(s)).toBe("Completado");
    }
  });
  it("running/in_progress -> info + En ejecución", () => {
    expect(runStatusTone("running")).toBe("info");
    expect(runStatusLabel("in_progress")).toBe("En ejecución");
  });
  it("needs_review/review -> warning + Requiere revisión", () => {
    expect(runStatusTone("needs_review")).toBe("warning");
    expect(runStatusLabel("review")).toBe("Requiere revisión");
  });
  it("error/failed -> danger + Error", () => {
    expect(runStatusTone("error")).toBe("danger");
    expect(runStatusTone("failed")).toBe("danger");
    expect(runStatusLabel("error")).toBe("Error");
  });
  it("cancelled/canceled/pending/queued -> neutral", () => {
    for (const s of ["cancelled", "canceled", "pending", "queued"]) {
      expect(runStatusTone(s)).toBe("neutral");
    }
  });
  it("desconocido -> neutral + crudo", () => {
    expect(runStatusTone("banana")).toBe("neutral");
    expect(runStatusLabel("banana")).toBe("banana");
  });
  it("vacío/null -> neutral + —", () => {
    expect(runStatusTone("")).toBe("neutral");
    expect(runStatusLabel(null)).toBe("—");
  });
});
