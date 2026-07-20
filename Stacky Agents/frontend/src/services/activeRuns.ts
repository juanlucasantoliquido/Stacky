/**
 * Fuente única de "runs activos globales" (running/preparing/queued de TODOS
 * los proyectos). Extraída de ActiveRunsPanel.tsx (plan 134 F0) para que el
 * panel, el TopBar y el notificador global compartan la MISMA query de
 * react-query. A propósito NO se filtra por proyecto (misma intención que el
 * comentario original del panel): el objetivo es visibilidad global, incluidos
 * runs huérfanos/colgados de otro proyecto.
 */
import { Executions } from "../api/endpoints";
import type { AgentExecution } from "../types";

export const ACTIVE_RUNS_QUERY_KEY = ["executions", "active-global"] as const;
export const ACTIVE_RUNS_REFRESH_MS = 5_000;

/**
 * Merge puro y determinista: dedup por id (si un run aparece en dos listas por
 * carrera entre requests, gana la ÚLTIMA en orden running→preparing→queued —
 * comportamiento idéntico al código original del panel), orden id descendente.
 */
export function mergeActiveRuns(
  running: AgentExecution[],
  preparing: AgentExecution[],
  queued: AgentExecution[],
): AgentExecution[] {
  const byId = new Map<number, AgentExecution>();
  for (const e of [...running, ...preparing, ...queued]) byId.set(e.id, e);
  return [...byId.values()].sort((a, b) => b.id - a.id);
}

/**
 * Plan 156 F2 — Deriva los runs activos globales del latido unico (una sola
 * request a /api/executions/summary?scope=all_projects, antes eran 3 a
 * /api/executions). Reusa mergeActiveRuns. El poller central real vive en
 * useActiveRunsGlobal (queryKey compartida = executionsSummaryQueryKey).
 */
export async function fetchActiveRuns(): Promise<AgentExecution[]> {
  const s = await Executions.summary("all_projects");
  return mergeActiveRuns(s.running, s.preparing, s.queued);
}
