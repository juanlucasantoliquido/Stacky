// Plan 157 F6 — lógica pura del Panel de Migración (testeable con vitest). Sin React.
import type { CompareRun } from "./dbcompareTypes";

/** Corridas seleccionables para migración: sólo las terminadas ("done"). */
export function selectableRuns(runs: CompareRun[]): CompareRun[] {
  return runs.filter((r) => r.status === "done");
}

/** URL del bundle .zip de scripts de una corrida (mismo contrato que
 * api/db_compare.py: GET /api/db-compare/runs/<run_id>/scripts.zip). */
export function zipUrlFor(runId: string, apiBase = ""): string {
  return `${apiBase}/api/db-compare/runs/${encodeURIComponent(runId)}/scripts.zip`;
}
