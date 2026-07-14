// Plan 130 — modelo PURO del verificador de integridad de código (sin React).
export interface CodeIntegrityFinding {
  file: string;
  line: number;
  message: string;
  import?: string;
}

export interface CodeIntegrityReport {
  ok: boolean;
  root?: string;
  files_scanned?: number;
  elapsed_ms?: number;
  syntax_errors?: CodeIntegrityFinding[];
  broken_imports?: CodeIntegrityFinding[];
  error?: string;
}

export type CardView =
  | { kind: "ok"; summary: string }
  | { kind: "findings"; findings: CodeIntegrityFinding[]; summary: string; copyText: string }
  | { kind: "error"; message: string };

export function fmtSummary(r: CodeIntegrityReport): string {
  const files = r.files_scanned ?? 0;
  const seconds = (r.elapsed_ms ?? 0) / 1000;
  return `${files} archivos en ${seconds.toFixed(1)} s`;
}

export function buildCopyText(r: CodeIntegrityReport): string {
  const findings = [...(r.syntax_errors ?? []), ...(r.broken_imports ?? [])];
  return findings
    .map((f) => `${f.file}:${f.line} — ${f.import ? "import roto: " + f.import : f.message}`)
    .join("\n");
}

export function reportToView(r: CodeIntegrityReport): CardView {
  if (r.error) {
    return { kind: "error", message: `El verificador falló (${r.error})` };
  }
  if (r.ok) {
    return { kind: "ok", summary: fmtSummary(r) };
  }
  const findings = [...(r.syntax_errors ?? []), ...(r.broken_imports ?? [])];
  return {
    kind: "findings",
    findings,
    summary: fmtSummary(r),
    copyText: buildCopyText(r),
  };
}
