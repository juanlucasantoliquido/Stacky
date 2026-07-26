/**
 * Plan 211 F5 — Modelo PURO de los hallazgos del inspector post-build y del
 * barrido de residuos de port.
 *
 * Los findings los persiste el gate de build (Plan 210) en
 * `execution.metadata.build_verdict`; acá solo se agrupan y etiquetan.
 */
import type { DevBuildFinding, DevBuildVerdictSummary } from "./devBuildModel";

export type FindingSeverityColor = "red" | "amber" | "gray";

const _KIND_LABEL: Record<string, string> = {
  post_build_event: "Evento post-build",
  after_targets: "Target atado al build",
  copy_task: "Tarea Copy",
  abs_output_path: "Salida con ruta absoluta",
  foreign_output_path: "Salida hacia otro cliente",
  foreign_token_in_project: "Token de otro cliente en el proyecto",
  server: "Servidor de otro cliente",
  path: "Ruta de otro cliente",
  workspace: "Workspace de otro cliente",
  product: "Nombre de producto ajeno",
  client_label: "Etiqueta de cliente ajena",
};

export function findingLabel(kind: string): string {
  return _KIND_LABEL[kind] ?? kind;
}

export function severityColor(sev: string): FindingSeverityColor {
  if (sev === "blocking") return "red";
  if (sev === "warning") return "amber";
  return "gray";
}

export function groupBySeverity(items: DevBuildFinding[]): {
  blocking: DevBuildFinding[];
  warning: DevBuildFinding[];
} {
  const blocking: DevBuildFinding[] = [];
  const warning: DevBuildFinding[] = [];
  for (const it of items ?? []) {
    (it.severity === "blocking" ? blocking : warning).push(it);
  }
  return { blocking, warning };
}

export function countBlocking(items: DevBuildFinding[]): number {
  return (items ?? []).filter((i) => i.severity === "blocking").length;
}

/** Todos los findings del veredicto: bloqueantes primero. */
export function findingsFromVerdict(
  v: DevBuildVerdictSummary | null | undefined,
): DevBuildFinding[] {
  if (!v) return [];
  return [...(v.blocking_findings ?? []), ...(v.warnings ?? [])];
}

/** Color del pane completo: rojo si algo bloquea, ámbar si solo hay avisos. */
export function paneColor(items: DevBuildFinding[]): FindingSeverityColor {
  if (!items?.length) return "gray";
  return countBlocking(items) > 0 ? "red" : "amber";
}
