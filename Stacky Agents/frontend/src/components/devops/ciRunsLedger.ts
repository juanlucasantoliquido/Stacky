/**
 * ciRunsLedger.ts — Plan 191 F2. Helpers PUROS de la bitácora de corridas CI.
 *
 * Sin React, sin fetch, sin efectos: solo transformaciones deterministas testeables
 * en vitest (gap conocido: sin @testing-library). El poll acotado espeja el cap
 * anti-N+1 del backend (_ACTIVE_POLLS, api/ci.py).
 */

export interface CiRun {
  project: string;
  tracker_type: string;
  ref: string;
  sha: string | null;
  pipeline_id: string;
  web_url: string | null;
  triggered_at: string;
  source: string;
  last_status?: string | null;
  finished_at?: string | null;
}

export const FINAL_STATUSES = ['success', 'failed', 'canceled', 'skipped'] as const;
export const POLL_INTERVAL_MS = 10_000; // C4 — constante nombrada
export const MAX_POLL_TARGETS = 5; // KPI-4 — mismo espíritu que _ACTIVE_POLLS del backend

function isFinal(status: string): boolean {
  return (FINAL_STATUSES as readonly string[]).includes(status);
}

/**
 * KPI-4 — elige los pipeline_id a pollear: los más recientes cuyo estado NO sea final,
 * máximo MAX_POLL_TARGETS. El estado inicial de cada run es su last_status persistido
 * (si existe), así los runs ya terminados NO se pollean nunca al montar.
 */
export function pollTargets(
  runs: CiRun[],
  statusById: Record<string, string | undefined>
): string[] {
  return runs
    .filter((r) => {
      const s = statusById[r.pipeline_id] ?? r.last_status ?? '';
      return !isFinal(s);
    })
    .slice(0, MAX_POLL_TARGETS)
    .map((r) => r.pipeline_id);
}

/**
 * KPI-5 — payload de re-disparo: SIN confirm. El confirm lo agrega el paso de
 * confirmación del flujo de trigger existente (HITL intacto).
 */
export function retriggerPayload(run: CiRun): { ref: string } {
  return { ref: run.ref };
}

/** Estado efectivo mostrado en la fila: el poll fresco gana; si no, el last_status persistido. */
export function effectiveStatus(
  run: CiRun,
  statusById: Record<string, string | undefined>
): string {
  return statusById[run.pipeline_id] ?? run.last_status ?? 'desconocido';
}

export function runLabel(run: CiRun): string {
  return `${run.ref} · #${run.pipeline_id} · ${run.triggered_at}`;
}
