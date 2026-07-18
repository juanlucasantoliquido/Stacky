/**
 * Plan 156 F2 — Poller central (latido unico) de runs activos.
 *
 * Un bus, N instrumentos: TODOS los consumidores de runs activos comparten la
 * MISMA queryKey de react-query (executionsSummaryQueryKey) => react-query hace
 * UNA sola request de red por tick aunque haya N suscriptores. El fetch pega a
 * GET /api/executions/summary (F1), que colapsa las 6 llamadas previas en 1.
 *
 * Todo lo de este modulo es PURO (funciones + constantes): testeable sin DOM.
 */
import { Executions } from "../api/endpoints";
import type { AgentExecution, ExecutionsSummary } from "../types";
import { mergeActiveRuns } from "./activeRuns";

export const EXECUTIONS_SUMMARY_REFRESH_MS = 5_000;
export const HIDDEN_TAB_BACKOFF_FACTOR = 4;
export const IDLE_BACKOFF_FACTOR = 2; // [ADICION ARQUITECTO v2] sin runs activos => pollea x2 mas lento

/** Query key central: TODOS los consumidores de runs activos la comparten
 *  => react-query hace 1 sola request por tick aunque haya N suscriptores.
 *
 *  NOTA NORMATIVA (plan 152 — centro de notificaciones y actividad): el
 *  notificador global de actividad DEBE suscribirse a
 *  executionsSummaryQueryKey("all_projects") con fetchExecutionsSummary en vez
 *  de crear su propio poller de /api/executions. Reconciliarlo con este canal
 *  es un follow-up separado (152 ya está implementado con poller propio). */
export const executionsSummaryQueryKey = (scope: "project" | "all_projects") =>
  ["executions", "summary", scope] as const;

/** true si el summary NO tiene ningun run activo (caso comun). */
export function summaryIsIdle(s: ExecutionsSummary | undefined): boolean {
  if (!s) return false; // sin dato aun: no aplicar idle backoff
  return s.running.length === 0 && s.preparing.length === 0 && s.queued.length === 0;
}

/** refetchInterval PURO: x4 con pestaña oculta, x2 adicional si no hay runs
 *  activos ([ADICION ARQUITECTO v2] — recorta el polling ocioso, el caso comun).
 *  Los factores se APILAN (multiplican). Ej.: visible+idle=10s; hidden+idle=40s;
 *  visible+activo=5s (responsive mientras hay algo que mirar). */
export function summaryRefetchInterval(
  visibility: DocumentVisibilityState,
  lastSummary?: ExecutionsSummary,
  baseMs: number = EXECUTIONS_SUMMARY_REFRESH_MS,
): number {
  let ms = baseMs;
  if (visibility === "hidden") ms *= HIDDEN_TAB_BACKOFF_FACTOR;
  if (summaryIsIdle(lastSummary)) ms *= IDLE_BACKOFF_FACTOR;
  return ms;
}

export function fetchExecutionsSummary(
  scope: "project" | "all_projects",
  project?: string | null,
): Promise<ExecutionsSummary> {
  return Executions.summary(scope, project);
}

/** Selector PURO: runs activos globales (reusa mergeActiveRuns existente). */
export function selectActiveRuns(s: ExecutionsSummary): AgentExecution[] {
  return mergeActiveRuns(s.running, s.preparing, s.queued);
}

/** Selector PURO: Set de ticket_ids activos + Map ticket_id -> ejecucion.
 *  El orden preparing->running->queued replica EXACTAMENTE useRunningStatus.ts
 *  (para no cambiar cual ejecucion gana en el Map). */
export function selectRunningByTicket(
  s: ExecutionsSummary,
): { ids: Set<number>; byTicket: Map<number, AgentExecution> } {
  const ids = new Set<number>();
  const byTicket = new Map<number, AgentExecution>();
  for (const e of [...s.preparing, ...s.running, ...s.queued]) {
    ids.add(e.ticket_id);
    if (!byTicket.has(e.ticket_id)) byTicket.set(e.ticket_id, e);
  }
  return { ids, byTicket };
}
