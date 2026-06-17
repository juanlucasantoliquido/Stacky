import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Executions } from "../api/endpoints";
import type { AgentExecution } from "../types";
import styles from "./ActiveRunsPanel.module.css";

const REFRESH_MS = 5_000;

/**
 * Trae TODOS los runs activos (running/preparing/queued) SIN filtro de proyecto.
 * A propósito no filtramos por proyecto: el objetivo es poder cancelar cualquier
 * ejecución activa —incluidos runs huérfanos/colgados de otro proyecto o cuyo
 * stacky_status quedó desincronizado— que el board no logra mostrar.
 */
async function fetchActiveRuns(): Promise<AgentExecution[]> {
  const [running, preparing, queued] = await Promise.all([
    Executions.list({ status: "running", all_projects: true }),
    Executions.list({ status: "preparing", all_projects: true }),
    Executions.list({ status: "queued", all_projects: true }),
  ]);
  const byId = new Map<number, AgentExecution>();
  for (const e of [...running, ...preparing, ...queued]) byId.set(e.id, e);
  return [...byId.values()].sort((a, b) => b.id - a.id);
}

export default function ActiveRunsPanel() {
  const qc = useQueryClient();

  const { data } = useQuery({
    queryKey: ["executions", "active-global"],
    queryFn: fetchActiveRuns,
    refetchInterval: REFRESH_MS,
  });

  const cancelMutation = useMutation({
    mutationFn: (id: number) => Executions.cancel(id),
    onSettled: () => {
      // Refrescar todo lo que depende del estado de runs activos.
      qc.invalidateQueries({ queryKey: ["executions"] });
      qc.invalidateQueries({ queryKey: ["tickets"] });
      qc.invalidateQueries({ queryKey: ["tickets-hierarchy"] });
    },
  });

  const runs = data ?? [];
  if (runs.length === 0) return null;

  return (
    <div className={styles.panel} role="region" aria-label="Ejecuciones activas">
      <div className={styles.head}>
        EJECUCIONES ACTIVAS <span className={styles.count}>{runs.length}</span>
      </div>
      <ul className={styles.list}>
        {runs.map((e) => {
          const cancelling =
            cancelMutation.isPending && cancelMutation.variables === e.id;
          return (
            <li key={e.id} className={styles.item}>
              <span className={styles.dot} aria-hidden />
              <span className={styles.id}>#{e.id}</span>
              <span className={styles.meta}>
                ticket {e.ticket_id} · {e.agent_type} · {e.status}
              </span>
              <button
                type="button"
                className={styles.cancelBtn}
                disabled={cancelling}
                title="Cancelar esta ejecución (detiene la sesión del agente)"
                onClick={() => {
                  if (cancelling) return;
                  if (
                    window.confirm(
                      `¿Cancelar la ejecución #${e.id} (ticket ${e.ticket_id}, ${e.agent_type})? Se detendrá la sesión del agente.`
                    )
                  ) {
                    cancelMutation.mutate(e.id);
                  }
                }}
              >
                {cancelling ? "cancelando…" : "✕ Cancelar"}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
