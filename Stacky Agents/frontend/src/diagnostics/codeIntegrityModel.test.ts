import { describe, it, expect } from "vitest";
import {
  reportToView,
  buildCopyText,
  fmtSummary,
  type CodeIntegrityReport,
} from "./codeIntegrityModel";

describe("codeIntegrityModel", () => {
  it("reportToView con ok:true -> kind ok y summary formateado", () => {
    const report: CodeIntegrityReport = {
      ok: true,
      files_scanned: 310,
      elapsed_ms: 1240,
      syntax_errors: [],
      broken_imports: [],
    };
    const view = reportToView(report);
    expect(view.kind).toBe("ok");
    if (view.kind === "ok") {
      expect(view.summary).toBe("310 archivos en 1.2 s");
    }
  });

  it("reportToView con hallazgos -> kind findings, sintaxis primero, orden preservado", () => {
    const report: CodeIntegrityReport = {
      ok: false,
      files_scanned: 5,
      elapsed_ms: 100,
      syntax_errors: [{ file: "api/x.py", line: 223, message: "invalid syntax" }],
      broken_imports: [
        { file: "api/__init__.py", line: 55, import: "api.pr_reviewx", message: "modulo de primera parte no encontrado" },
      ],
    };
    const view = reportToView(report);
    expect(view.kind).toBe("findings");
    if (view.kind === "findings") {
      expect(view.findings.map((f) => f.file)).toEqual(["api/x.py", "api/__init__.py"]);
    }
  });

  it("reportToView con error -> kind error y nombre de clase en el mensaje", () => {
    const report: CodeIntegrityReport = { ok: false, error: "RuntimeError" };
    const view = reportToView(report);
    expect(view.kind).toBe("error");
    if (view.kind === "error") {
      expect(view.message).toContain("RuntimeError");
    }
  });

  it("buildCopyText mezcla sintaxis+imports en líneas exactas", () => {
    const report: CodeIntegrityReport = {
      ok: false,
      syntax_errors: [{ file: "api/x.py", line: 223, message: "invalid syntax" }],
      broken_imports: [
        { file: "api/__init__.py", line: 55, import: "api.pr_reviewx", message: "modulo de primera parte no encontrado" },
      ],
    };
    const text = buildCopyText(report);
    expect(text).toBe(
      "api/x.py:223 — invalid syntax\napi/__init__.py:55 — import roto: api.pr_reviewx"
    );
  });

  it("defensivo: listas ausentes -> vacías, sin throw", () => {
    const report: CodeIntegrityReport = { ok: false };
    expect(() => reportToView(report)).not.toThrow();
    const view = reportToView(report);
    expect(view.kind).toBe("findings");
    if (view.kind === "findings") {
      expect(view.findings).toEqual([]);
    }
  });

  it("fmtSummary con campos ausentes -> 0 archivos en 0.0 s", () => {
    expect(fmtSummary({ ok: true })).toBe("0 archivos en 0.0 s");
  });
});
