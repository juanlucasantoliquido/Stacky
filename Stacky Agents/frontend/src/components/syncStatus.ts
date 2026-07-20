/**
 * Plan 156 F4 — Helpers puros del reloj de sincronización.
 *
 * Réplica EXACTA de la lógica que vivía inline en useTicketSync
 * (secondsSinceSync + isStale), extraída para que el tic-tac de 1s viva en la
 * hoja SyncStatusBar y NO fuerce re-render del board completo.
 */
export function secondsSince(lastSyncedAt: string | null, nowMs: number = Date.now()): number | null {
  if (!lastSyncedAt) return null;
  return Math.floor((nowMs - new Date(lastSyncedAt).getTime()) / 1000);
}

export function isStaleAt(
  lastSyncedAt: string | null,
  intervalMs: number,
  nowMs: number = Date.now(),
): boolean {
  const secs = secondsSince(lastSyncedAt, nowMs);
  return secs !== null && secs * 1000 > intervalMs * 2;
}
