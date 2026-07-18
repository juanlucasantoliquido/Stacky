/**
 * useRunningStatus — Hook centralizado para saber qué tickets tienen un
 * agente corriendo en este momento.
 *
 * Estrategia dual:
 *   1. Fuente primaria: `stacky_status === "running"` del listado de tickets
 *      (campo devuelto por el backend desde la implementación ticket_status).
 *   2. Fuente secundaria: polling de `GET /executions?status=running` cada 5 s
 *      (ya existente en TicketBoard). Útil como fallback y como fuente de
 *      metadata de la ejecución activa (agent_type, execution_id).
 *
 * El hook unifica ambas fuentes en un único Set<number> de ticket_ids activos
 * y en un Map<number, AgentExecution> para acceso a metadata de ejecución.
 *
 * Uso:
 *   const { runningTicketIds, runningByTicket, isTicketRunning } = useRunningStatus();
 */
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Tickets } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import type { AgentExecution, ExecutionsSummary, Ticket } from "../types";
import {
  executionsSummaryQueryKey,
  fetchExecutionsSummary,
  selectRunningByTicket,
  summaryRefetchInterval,
} from "../services/executionsSummary";

export interface RunningStatusResult {
  /** Set de ticket_ids que tienen stacky_status="running" en BD */
  runningTicketIds: Set<number>;
  /** Map ticketId → AgentExecution activa (fuente: executions polling) */
  runningByTicket: Map<number, AgentExecution>;
  /** Helper: true si el ticket tiene un agente corriendo */
  isTicketRunning: (ticketId: number) => boolean;
  /** Cantidad total de tickets con agente corriendo */
  runningCount: number;
  /** Lista de tickets activos (requiere pasar el listado de tickets) */
  getRunningTickets: (tickets: Ticket[]) => Ticket[];
}

/** Intervalo de refetch para la lista de tickets cuando hay actividad (ms) */
const TICKETS_ACTIVE_POLL_INTERVAL = 8_000;

export function useRunningStatus(): RunningStatusResult {
  const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);
  // ── Fuente 1: stacky_status desde el listado de tickets ──────────────────
  // Cuando hay actividad, refrescamos más frecuentemente.
  // En reposo, el intervalo normal de Tickets.list (60s) aplica.
  const { data: tickets } = useQuery<Ticket[]>({
    queryKey: ["tickets", activeProjectName],
    queryFn: () => Tickets.list(activeProjectName),
    // No sobreescribir staleTime global — usar el existente. Solo
    // refetcharemos más rápido si ya tenemos tickets corriendo.
    refetchInterval: (query) => {
      const data = query.state.data as Ticket[] | undefined;
      const hasRunning = data?.some((t) => t.stacky_status === "running");
      return hasRunning ? TICKETS_ACTIVE_POLL_INTERVAL : 60_000;
    },
  });

  // ── Fuente 2: latido único de ejecuciones activas (metadata + fallback) ────
  // Plan 156 F2: UNA sola query al summary (scope=project) reemplaza los 3
  // polls previos (running/preparing/queued). La key incluye activeProjectName
  // para invalidar al cambiar de proyecto; se pasa el mismo nombre al fetch para
  // preservar EXACTO el filtro por proyecto del código anterior.
  const { data: summary } = useQuery<ExecutionsSummary>({
    queryKey: [...executionsSummaryQueryKey("project"), activeProjectName],
    queryFn: () => fetchExecutionsSummary("project", activeProjectName),
    // La forma (query)=>number recibe el último dato para aplicar el idle
    // backoff (×2) cuando no hay runs activos, apilado con el de visibilidad.
    refetchInterval: (query) => summaryRefetchInterval(document.visibilityState, query.state.data),
    staleTime: 0,
  });

  const { ids: execTicketIds, byTicket } = useMemo(
    () => (summary ? selectRunningByTicket(summary) : { ids: new Set<number>(), byTicket: new Map<number, AgentExecution>() }),
    [summary],
  );

  // ── Combinar ambas fuentes ─────────────────────────────────────────────────
  const runningTicketIds = useMemo<Set<number>>(() => {
    const ids = new Set<number>();
    // Fuente 1: stacky_status en ticket list
    for (const t of tickets ?? []) {
      if (t.stacky_status === "running") ids.add(t.id);
    }
    // Fuente 2: executions activas (fallback — captura el caso donde
    // stacky_status aún no llegó al cliente pero ya hay ejecución)
    for (const id of execTicketIds) ids.add(id);
    return ids;
  }, [tickets, execTicketIds]);

  const runningByTicket = byTicket;

  const isTicketRunning = useMemo(
    () => (ticketId: number) => runningTicketIds.has(ticketId),
    [runningTicketIds]
  );

  const getRunningTickets = useMemo(
    () => (allTickets: Ticket[]) => allTickets.filter((t) => runningTicketIds.has(t.id)),
    [runningTicketIds]
  );

  return {
    runningTicketIds,
    runningByTicket,
    isTicketRunning,
    runningCount: runningTicketIds.size,
    getRunningTickets,
  };
}
