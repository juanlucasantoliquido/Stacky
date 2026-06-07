/**
 * inconsistencyDetector.ts
 *
 * Lógica de detección del estado INCONSISTENTE de un ticket.
 *
 * Definición (plan §7.1):
 *   ticket.stacky_status == 'completed'
 *   AND any(executions where status in {preparing, running, queued})
 *
 * Este módulo es puro (sin side effects) para facilitar tests unitarios.
 */

import type { AgentExecution } from "../types";

export type InconsistencyInfo = {
  isInconsistent: true;
  orphanExecution: AgentExecution;
} | {
  isInconsistent: false;
  orphanExecution: null;
};

/**
 * Detecta si un ticket está en estado INCONSISTENTE.
 *
 * @param stackyStatus - El stacky_status del ticket ("completed", "running", ...)
 * @param executions   - Lista de ejecuciones del ticket (activas + históricas).
 */
export function detectInconsistency(
  stackyStatus: string | undefined,
  executions: AgentExecution[]
): InconsistencyInfo {
  if (stackyStatus !== "completed") {
    return { isInconsistent: false, orphanExecution: null };
  }

  const orphan = executions.find(
    (e) => e.status === "preparing" || e.status === "running" || e.status === "queued"
  );

  if (!orphan) {
    return { isInconsistent: false, orphanExecution: null };
  }

  return { isInconsistent: true, orphanExecution: orphan };
}

/**
 * Helper: dado el runningByTicket map del hook useRunningStatus y el
 * stacky_status del ticket, determina si es inconsistente.
 *
 * Útil cuando no tenemos la lista completa de ejecuciones pero sí la
 * ejecución activa inferida desde el polling global.
 */
export function detectInconsistencyFromRunning(
  stackyStatus: string | undefined,
  runningExecution: AgentExecution | null
): InconsistencyInfo {
  if (stackyStatus !== "completed" || !runningExecution) {
    return { isInconsistent: false, orphanExecution: null };
  }
  return { isInconsistent: true, orphanExecution: runningExecution };
}
