/** Lógica pura del notificador y del título de pestaña (plan 134 F2/F3). */

export type FinishOutcome = "ok" | "attention" | null;

/** TTL del registro de ejecuciones ya notificadas. */
export const NOTIFIED_TTL_MS = 10 * 60_000;

/**
 * Dedup por execution_id: true si execId NO fue notificado dentro del TTL.
 * Muta `seen` (registra execId y poda entradas vencidas). Determinista dado
 * (execId, nowMs, seen).
 */
export function shouldNotifyExecution(
  execId: number,
  nowMs: number,
  seen: Map<number, number>,
  ttlMs: number = NOTIFIED_TTL_MS,
): boolean {
  for (const [id, at] of seen) {
    if (nowMs - at > ttlMs) seen.delete(id);
  }
  if (seen.has(execId)) return false;
  seen.set(execId, nowMs);
  return true;
}

/**
 * Combina el desenlace acumulado con el status de un run recién terminado.
 * "attention" (error/needs_review) es pegajoso: nunca lo pisa un completed.
 * "cancelled" (u otro status desconocido) no cambia la señal: lo canceló el
 * propio operador, no es novedad.
 */
export function combineOutcome(prev: FinishOutcome, status: string): FinishOutcome {
  if (status === "error" || status === "needs_review") return "attention";
  if (status === "completed") return prev === "attention" ? "attention" : "ok";
  return prev;
}

/** Título de pestaña derivado del estado real (F3). Actividad gana al desenlace. */
export function computeTabTitle(
  activeCount: number,
  lastOutcome: FinishOutcome,
  baseTitle: string,
): string {
  if (activeCount > 0) return `(${activeCount}▶) ${baseTitle}`;
  if (lastOutcome === "ok") return `✅ ${baseTitle}`;
  if (lastOutcome === "attention") return `❌ ${baseTitle}`;
  return baseTitle;
}

/** Cuerpo de la notificación con contexto de proyecto/ticket (campos F1, opcionales). */
export function buildNotificationBody(row: {
  ticket_id?: number | null;
  project?: string | null;
  ticket_title?: string | null;
}): string {
  const parts: string[] = [];
  if (row.project) parts.push(row.project);
  if (row.ticket_title) parts.push(row.ticket_title);
  else if (row.ticket_id != null) parts.push(`Ticket ${row.ticket_id}`);
  return parts.length > 0 ? parts.join(" · ") : "Ejecución finalizada.";
}
