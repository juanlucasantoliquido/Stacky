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
import { Tickets, Executions } from "../api/endpoints";
import type { AgentExecution, Ticket } from "../types";

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

/** Intervalo de polling para ejecuciones activas (ms) */
const EXEC_POLL_INTERVAL = 5_000;

/** Intervalo de refetch para la lista de tickets cuando hay actividad (ms) */
const TICKETS_ACTIVE_POLL_INTERVAL = 8_000;

export function useRunningStatus(): RunningStatusResult {
  // ── Fuente 1: stacky_status desde el listado de tickets ──────────────────
  // Cuando hay actividad, refrescamos más frecuentemente.
  // En reposo, el intervalo normal de Tickets.list (60s) aplica.
  const { data: tickets } = useQuery<Ticket[]>({
    queryKey: ["tickets"],
    queryFn: Tickets.list,
    // No sobreescribir staleTime global — usar el existente. Solo
    // refetcharemos más rápido si ya tenemos tickets corriendo.
    refetchInterval: (query) => {
      const data = query.state.data as Ticket[] | undefined;
      const hasRunning = data?.some((t) => t.stacky_status === "running");
      return hasRunning ? TICKETS_ACTIVE_POLL_INTERVAL : 60_000;
    },
  });

  // ── Fuente 2: polling de ejecuciones activas (metadata + fallback) ────────
  const { data: activeExecs } = useQuery<AgentExecution[]>({
    queryKey: ["executions-active"],
    queryFn: () => Executions.list({ status: "running" }),
    refetchInterval: EXEC_POLL_INTERVAL,
    staleTime: 0,
  });

  const { data: queuedExecs } = useQuery<AgentExecution[]>({
    queryKey: ["executions-queued"],
    queryFn: () => Executions.list({ status: "queued" }),
    refetchInterval: EXEC_POLL_INTERVAL,
    staleTime: 0,
  });

  // ── Combinar ambas fuentes ─────────────────────────────────────────────────
  const runningTicketIds = useMemo<Set<number>>(() => {
    const ids = new Set<number>();
    // Fuente 1: stacky_status en ticket list
    for (const t of tickets ?? []) {
      if (t.stacky_status === "running") ids.add(t.id);
    }
    // Fuente 2: executions activas (fallback — captura el caso donde
    // stacky_status aún no llegó al cliente pero ya hay ejecución)
    for (const e of [...(activeExecs ?? []), ...(queuedExecs ?? [])]) {
      ids.add(e.ticket_id);
    }
    return ids;
  }, [tickets, activeExecs, queuedExecs]);

  const runningByTicket = useMemo<Map<number, AgentExecution>>(() => {
    const map = new Map<number, AgentExecution>();
    for (const e of [...(activeExecs ?? []), ...(queuedExecs ?? [])]) {
      if (!map.has(e.ticket_id)) map.set(e.ticket_id, e);
    }
    return map;
  }, [activeExecs, queuedExecs]);

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
