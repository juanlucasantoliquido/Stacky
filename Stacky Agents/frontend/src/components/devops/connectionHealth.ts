/**
 * connectionHealth.ts — Plan 116 F3 (lógica PURA, testeable sin DOM).
 *
 * Deriva el peor estado por grupo y su clase CSS de chip a partir del snapshot
 * del doctor de conexiones. Sin efectos, sin fetch.
 */
import type { ConnectionDiagResult, ConnectionsSnapshot } from '../../api/endpoints';

export type GroupId = 'tracker' | 'servers' | 'clis' | 'credentials';
export type ChipStatus = 'fail' | 'warn' | 'ok' | 'skip';

/** Peor estado del grupo: fail > warn > ok > skip. Sin resultados → 'skip'. */
export function worstStatus(
  snapshot: ConnectionsSnapshot | null | undefined,
  group: GroupId
): ChipStatus {
  const inGroup = (snapshot?.results ?? []).filter((r) => r.group === group);
  if (inGroup.length === 0) return 'skip';
  const order: ChipStatus[] = ['fail', 'warn', 'ok', 'skip'];
  for (const s of order) {
    if (inGroup.some((r: ConnectionDiagResult) => r.status === s)) return s;
  }
  return 'skip';
}

/** Resultados accionables (fail|warn) del snapshot, en orden de aparición. */
export function actionableResults(
  snapshot: ConnectionsSnapshot | null | undefined
): ConnectionDiagResult[] {
  return (snapshot?.results ?? []).filter(
    (r) => r.status === 'fail' || r.status === 'warn'
  );
}
