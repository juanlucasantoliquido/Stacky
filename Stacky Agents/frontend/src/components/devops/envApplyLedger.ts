// Plan 198 — helpers PUROS para el historial de applies de ambientes + drift de layout.
// Sin React, sin fetch: solo formateo de fila y badge de drift (testeados en vitest).
// Los tipos de contrato viven en el modelo canónico de ambientes; se re-exportan acá
// para que el componente y sus tests los consuman desde un único lugar.
import type { EnvApply, EnvAppliesResponse } from '../../devops/environmentModel';

export type { EnvApply, EnvAppliesResponse };

/** Línea legible de un apply: cuándo · dónde · cuántas carpetas · resultado. */
export function applyRow(a: EnvApply): string {
  const where = a.server_alias ?? 'Local';
  const ok = a.result_ok ? 'OK' : 'FALLÓ';
  return `${a.applied_at} · ${where} · ${a.created_count} creadas · ${ok}`;
}

/** Badge de drift de la DEFINICIÓN del layout (Plan 198 C1): compara fingerprints.
 * null = sin applies previos (no hay con qué comparar). */
export function driftBadge(
  drift: boolean | null,
): { tone: 'ok' | 'warn' | 'none'; text: string } {
  if (drift === null) return { tone: 'none', text: '' };
  return drift
    ? { tone: 'warn', text: 'La definición del layout cambió desde el último apply — replanificá' }
    : { tone: 'ok', text: 'Definición del layout igual al último apply' };
}
