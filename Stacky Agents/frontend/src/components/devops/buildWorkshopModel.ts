/**
 * Plan 201 F9 — Modelo PURO del Taller de Compilación.
 *
 * Sin render, sin fetch: solo transformaciones testeables. La UI (F10) queda
 * como render puro sobre estos helpers.
 */

export interface SolutionProject {
  name: string;
  csproj_path: string;
  type: "web" | "console" | "service" | "library" | "unknown";
  target_framework: string;
}

export interface SolutionEntry {
  slug: string;
  sln_path: string;
  sln_name: string;
  friendly_name: string;
  tracked: boolean;
  projects: SolutionProject[];
}

export interface Toolchain {
  available: boolean;
  builder: "msbuild" | "dotnet" | null;
  version: string | null;
  remediation: { message: string; command: string; url: string } | null;
}

export interface BuildArtifactInfo {
  slug: string;
  dir: string;
  files: number;
  bytes: number;
}

export interface BuildSummary {
  duration_sec: number | null;
  toolchain: { builder: string | null; version: string | null };
  artifacts: BuildArtifactInfo[];
}

export interface BuildStatus {
  status: "running" | "success" | "failed" | "cancelled" | "toolchain_missing";
  mode: "single" | "unified";
  slugs: string[];
  log: { ts: string; level: string; message: string }[];
  artifact_ready: boolean;
  error: string | null;
  summary?: BuildSummary | null;
}

export interface Catalog {
  scanned_at: string | null;
  truncated: boolean;
  solutions: SolutionEntry[];
}

export function trackedSlugs(solutions: SolutionEntry[]): string[] {
  return (solutions || []).filter((s) => s.tracked).map((s) => s.slug);
}

/** El tamaño de un artefacto se formatea con el formateador canónico del repo
 *  (plan 161): una sola implementación para todo lo que se muestra. */
export { formatBytes } from "../../services/format";

export function canCompile(toolchain: Toolchain, selectedCount: number): boolean {
  return Boolean(toolchain?.available) && selectedCount >= 1;
}

export function compileMode(
  unified: boolean,
  selectedCount: number,
): "single" | "unified" | "invalid" {
  if (selectedCount > 1 && !unified) return "invalid";
  return unified ? "unified" : "single";
}

const _STATUS_LABEL: Record<BuildStatus["status"], string> = {
  running: "Compilando…",
  success: "Compilado",
  failed: "Falló",
  cancelled: "Cancelado",
  toolchain_missing: "Sin herramientas de compilación",
};

export function buildStatusLabel(status: BuildStatus["status"]): string {
  return _STATUS_LABEL[status] ?? status;
}

export function formatBuildDuration(
  startIso: string,
  endIso: string | null,
  now?: Date,
): string {
  if (!endIso) return "en curso";
  const start = Date.parse(startIso);
  const end = Date.parse(endIso);
  if (Number.isNaN(start) || Number.isNaN(end)) return "—";
  void now;
  const secs = Math.max(0, Math.round((end - start) / 1000));
  if (secs < 60) return `${secs} s`;
  const min = Math.floor(secs / 60);
  return `${min} min ${secs % 60} s`;
}

const _TYPE_LABEL: Record<SolutionProject["type"], string> = {
  web: "Web",
  console: "Consola",
  service: "Servicio",
  library: "Librería",
  unknown: "Desconocido",
};

export function projectTypeLabel(t: SolutionProject["type"]): string {
  return _TYPE_LABEL[t] ?? String(t);
}

export function summarizeCatalog(solutions: SolutionEntry[]): {
  total: number;
  tracked: number;
  byType: Record<string, number>;
} {
  const byType: Record<string, number> = {};
  let tracked = 0;
  for (const sol of solutions || []) {
    if (sol.tracked) tracked += 1;
    for (const p of sol.projects || []) {
      byType[p.type] = (byType[p.type] ?? 0) + 1;
    }
  }
  return { total: (solutions || []).length, tracked, byType };
}
