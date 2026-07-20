import { describe, it, expect } from "vitest";
import { isFailedStatus, evidenceFileName, evidenceToFiles } from "./deployEvidence";

describe("isFailedStatus", () => {
  it("true para failed y failed_smoke", () => {
    expect(isFailedStatus("failed")).toBe(true);
    expect(isFailedStatus("failed_smoke")).toBe(true);
  });
  it("false para ok / running / undefined", () => {
    expect(isFailedStatus("ok")).toBe(false);
    expect(isFailedStatus("running")).toBe(false);
    expect(isFailedStatus(undefined)).toBe(false);
  });
});

describe("evidenceFileName", () => {
  it("respeta extensiones permitidas (.md / .json)", () => {
    expect(evidenceFileName("r123", "md")).toBe("evidencia-r123.md");
    expect(evidenceFileName("r123", "json")).toBe("evidencia-r123.json");
  });
});

describe("evidenceToFiles", () => {
  it("devuelve 2 Files con nombres correctos y JSON parseable", async () => {
    const files = evidenceToFiles("r1", "# md", { a: 1, b: "x" });
    expect(files.length).toBe(2);
    expect(files[0].name).toBe("evidencia-r1.md");
    expect(files[1].name).toBe("evidencia-r1.json");
    // File.text() existe en Node ≥20 (undici). Si no, se saltea la lectura.
    if (typeof File !== "undefined" && typeof files[1].text === "function") {
      expect(JSON.parse(await files[1].text())).toEqual({ a: 1, b: "x" });
      expect(await files[0].text()).toBe("# md");
    }
  });
});
