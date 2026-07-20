/**
 * publishLedgerView.ts — Plan 153.
 * Helpers PUROS (sin DOM, sin fetch) para el panel del ledger de publicaciones.
 * Testeables sin RTL/jsdom (gap estructural conocido: no estan en package.json).
 */
import type { PublishLedgerItem, PublishLedgerSnapshot } from "../api/endpoints";

/** Concatena pending_stale + failed ordenado por updated_at descendente. */
export function partitionLedger(
  snapshot: PublishLedgerSnapshot,
): { actionable: PublishLedgerItem[]; empty: boolean } {
  const all = [...(snapshot.pending_stale ?? []), ...(snapshot.failed ?? [])];
  all.sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""));
  return { actionable: all, empty: all.length === 0 };
}

/** Etiqueta legible de una fila del ledger para el operador. */
export function ledgerRowLabel(item: PublishLedgerItem): string {
  let when: string;
  try {
    when = item.updated_at ? new Date(item.updated_at).toLocaleString() : "sin fecha";
  } catch {
    when = item.updated_at ?? "sin fecha";
  }
  const err = item.error ?? "sin error registrado";
  return `exec ${item.execution_id} · ${item.status} desde ${when} · ${err}`;
}

/** Re-publicar solo tiene sentido si la fila NO esta ya posteada. */
export function canRepublish(item: PublishLedgerItem): boolean {
  return item.status !== "posted";
}
