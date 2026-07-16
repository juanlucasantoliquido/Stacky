// Plan 119 — mapea el testResult existente de ServersSection a la celda "Estado".
export type StateTone = 'ok' | 'warn' | 'none';
export interface StateCell { tone: StateTone; label: string; }

// `result` es la MISMA forma que ServersSection ya maneja hoy en `testResults`
// (Record<string, { ok: boolean; detail: string }>, ServersSection.tsx:43). No se cambia su producción.
export function mapTestResultToState(result: { ok?: boolean; detail?: string } | undefined): StateCell {
  if (!result) return { tone: 'none', label: 'sin probar' };
  if (result.ok) return { tone: 'ok', label: 'Alcanzable' };
  return { tone: 'warn', label: result.detail?.trim() || 'No alcanzable' };
}
