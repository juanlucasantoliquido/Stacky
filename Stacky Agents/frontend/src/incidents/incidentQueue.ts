/**
 * Plan 166 F3 — Modelo PURO de la cola de incidencias en modo lote (creación
 * directa sin diálogos). Sin dependencias de DOM: testeable con vitest solo
 * (respeta el gap RTL/jsdom, ver gotcha-rtl-jsdom-structural-gap).
 */

export type QueueItemStatus = "capturando" | "analizando" | "publicada" | "error";

export interface QueueItem {
  id: string;
  title: string;
  status: QueueItemStatus;
  trackerId?: string;
  url?: string;
  error?: string;
}

/** Reemplaza el item existente por `id`, o lo agrega al final si es nuevo. */
export function upsertQueueItem(items: QueueItem[], next: QueueItem): QueueItem[] {
  const idx = items.findIndex((i) => i.id === next.id);
  if (idx === -1) return [...items, next];
  const copy = items.slice();
  copy[idx] = next;
  return copy;
}

/** Resumen de la cola: total, publicadas y en error. */
export function queueSummary(items: QueueItem[]): { total: number; publicadas: number; errores: number } {
  return {
    total: items.length,
    publicadas: items.filter((i) => i.status === "publicada").length,
    errores: items.filter((i) => i.status === "error").length,
  };
}

/**
 * Mapa TOTAL (C3/C9) de los 5 estados reales del store
 * (backend/services/incident_store.py) a los 4 estados de la cola:
 * "capturada" -> "capturando"; "analizando"|"analizada" -> "analizando"
 * (aún sin publicar por el post-hook); "publicada" -> "publicada";
 * cualquier otro valor (incluido "error", null o desconocido) -> "error",
 * para que la cola NUNCA se quede muda mostrando un estado inexistente.
 */
export function mapStoreStatus(status: string | null | undefined): QueueItemStatus {
  if (status === "capturada") return "capturando";
  if (status === "analizando" || status === "analizada") return "analizando";
  if (status === "publicada") return "publicada";
  return "error";
}

/** True si el item todavía puede cambiar de estado (vale la pena seguir pollendo). */
export function isNonTerminal(status: QueueItemStatus): boolean {
  return status === "capturando" || status === "analizando";
}
