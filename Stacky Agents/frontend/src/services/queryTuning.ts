/** Plan 174 F4 — Retención por tipo de query.
 *
 *  `staleTime` = cuándo revalidar. Se PRESERVAN los valores que ya usaba cada
 *  página: este módulo no acelera ni frena la revalidación, solo centraliza.
 *  `gcTime` = cuánto retener para poder pintar desde cache al volver, que es lo
 *  que elimina el flash de vacío. No toca el default global de main.tsx.
 */
export const QUERY_TUNING = {
  history: { staleTime: 30_000, gcTime: 10 * 60_000 },
  systemLogs: { staleTime: 10_000, gcTime: 10 * 60_000 },
  executionDetail: { staleTime: 30_000, gcTime: 10 * 60_000 },
} as const;

export type QueryTuningKey = keyof typeof QUERY_TUNING;

export function tuningFor(key: QueryTuningKey): { staleTime: number; gcTime: number } {
  return QUERY_TUNING[key];
}
