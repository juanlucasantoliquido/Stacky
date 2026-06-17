import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { Executions } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import { notifyExecutionFinished } from "../services/executionNotifier";

/**
 * U0.4 — Notifica finalización de cualquier run, no solo el abierto en el dock.
 */
export function useGlobalExecutionNotifier() {
  const activeProjectName = useWorkbench((s) => s.activeProject?.name ?? null);
  const prevRunning = useRef<Set<number>>(new Set());

  const runningQ = useQuery({
    queryKey: ["executions-running-global", activeProjectName],
    queryFn: () => Executions.list({ status: "running", project: activeProjectName }),
    refetchInterval: 5000,
    staleTime: 0,
  });

  useEffect(() => {
    const currentRows = runningQ.data ?? [];
    const current = new Set<number>(currentRows.map((e) => e.id));

    for (const prevId of prevRunning.current) {
      if (!current.has(prevId)) {
        void Executions.byId(prevId)
          .then((row) => {
            notifyExecutionFinished({
              agent_type: String(row.agent_type || "agente"),
              status:
                (row.status as "completed" | "error" | "cancelled" | "needs_review") ||
                "completed",
              ticket_label: row.ticket_id ? `Ticket ${row.ticket_id}` : undefined,
            });
          })
          .catch(() => {});
      }
    }

    prevRunning.current = current;
  }, [runningQ.data]);
}
