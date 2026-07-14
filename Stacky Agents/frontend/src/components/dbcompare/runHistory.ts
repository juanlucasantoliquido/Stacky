// Plan 124 [ADICIÓN ARQUITECTO de la crítica v2] — delta de parity score contra la corrida
// anterior del mismo par de ambientes (en cualquier orden de alias). Cero endpoints nuevos:
// consume el mismo `listRuns(20)` que ya trae `RunsTimeline` (F6).
import type { CompareRun } from "./dbcompareTypes";

export interface PreviousRunDelta {
  previousRunId: string;
  previousScore: number;
  deltaPoints: number;
  previousFinishedAt: string;
}

function pairKey(a: string, b: string): string {
  return [a, b].sort().join("|");
}

/**
 * Busca, entre `historicalRuns`, la corrida DONE más reciente (por `finished_at`) del MISMO
 * par que `current` (en cualquier orden de alias), distinta de `current` misma, y devuelve el
 * delta de `parity_score`. `null` si no hay ninguna candidata — no se renderiza "N/A".
 */
export function previousRunDelta(current: CompareRun, historicalRuns: CompareRun[]): PreviousRunDelta | null {
  const key = pairKey(current.source_alias, current.target_alias);
  const candidates = historicalRuns.filter(
    (r) =>
      r.run_id !== current.run_id &&
      r.status === "done" &&
      r.finished_at !== null &&
      r.summary !== null &&
      pairKey(r.source_alias, r.target_alias) === key
  );
  if (candidates.length === 0) return null;

  candidates.sort((a, b) => (a.finished_at! < b.finished_at! ? 1 : a.finished_at! > b.finished_at! ? -1 : 0));
  const previous = candidates[0];
  const currentScore = current.summary?.parity_score ?? 0;
  const previousScore = previous.summary!.parity_score;
  const deltaPoints = Math.round((currentScore - previousScore) * 10) / 10;

  return {
    previousRunId: previous.run_id,
    previousScore,
    deltaPoints,
    previousFinishedAt: previous.finished_at!,
  };
}
