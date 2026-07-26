/**
 * Plan 210 F7 — Modelo PURO del veredicto de build del Developer.
 *
 * El veredicto lo produce la máquina; acá solo se traduce a algo legible. Sin
 * render, sin fetch: testeable barato.
 */

export interface DevBuildFinding {
  kind: string;
  severity: "blocking" | "warning";
  file: string;
  detail: string;
}

export interface DevBuildVerdictSummary {
  gate_ok: boolean;
  reason: string;
  entry_kind: "sln" | "csproj" | "none";
  solution: string;
  blocking_findings: DevBuildFinding[];
  warnings: DevBuildFinding[];
}

export type VerdictColor = "green" | "red" | "gray";

const _REASON_LABEL: Record<string, string> = {
  ok: "La solución compiló sin errores.",
  no_sln: "No se encontró ninguna solución .sln para compilar.",
  csproj_not_allowed:
    "Solo hay proyectos sueltos (.csproj) y el perfil no los acepta como entrada de build.",
  csproj_entry: "La entrada de build es un .csproj suelto, no una solución.",
  build_failed: "La compilación devolvió errores.",
  toolchain_missing: "Falta el toolchain .NET en esta máquina.",
  build_workshop_unavailable: "El Taller de Compilación no está disponible.",
  workspace_missing: "No se pudo resolver el workspace del proyecto.",
  stale_verdict: "El veredicto disponible es de otra corrida.",
  not_verified: "Ninguna máquina verificó este build.",
};

export function verdictColor(v: DevBuildVerdictSummary | null | undefined): VerdictColor {
  if (!v) return "gray";
  return v.gate_ok ? "green" : "red";
}

export function verdictLabel(reason: string): string {
  return _REASON_LABEL[reason] ?? reason;
}

export function verdictBadge(
  v: DevBuildVerdictSummary | null | undefined,
): { text: string; color: VerdictColor } {
  if (!v) return { text: "Build sin verificar", color: "gray" };
  if (v.gate_ok) return { text: "Build verificado por máquina", color: "green" };
  return { text: `Build NO verificado — ${verdictLabel(v.reason)}`, color: "red" };
}

/** Hallazgos que bloquean, primero; después las advertencias. */
export function orderedFindings(v: DevBuildVerdictSummary | null | undefined): DevBuildFinding[] {
  if (!v) return [];
  return [...(v.blocking_findings ?? []), ...(v.warnings ?? [])];
}

/** Lee el resumen de la metadata de una ejecución. Null si no aplica. */
export function readBuildVerdict(
  metadata: Record<string, unknown> | undefined | null,
): DevBuildVerdictSummary | null {
  const raw = metadata?.build_verdict;
  if (!raw || typeof raw !== "object") return null;
  const v = raw as Partial<DevBuildVerdictSummary>;
  if (typeof v.gate_ok !== "boolean") return null;
  return {
    gate_ok: v.gate_ok,
    reason: String(v.reason ?? "not_verified"),
    entry_kind: (v.entry_kind ?? "none") as DevBuildVerdictSummary["entry_kind"],
    solution: String(v.solution ?? ""),
    blocking_findings: Array.isArray(v.blocking_findings) ? v.blocking_findings : [],
    warnings: Array.isArray(v.warnings) ? v.warnings : [],
  };
}
