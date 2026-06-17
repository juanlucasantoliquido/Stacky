import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Executions } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import type { AgentExecution, ExecutionStatus } from "../types";
import styles from "./ExecutionHistory.module.css";

// Estados "activos" (un run no terminó): alineado con el backend
// (run_guard.ACTIVE_STATUSES) y con los estados que el endpoint /cancel acepta.
const ACTIVE_STATUSES: ReadonlyArray<ExecutionStatus> = ["preparing", "queued", "running"];

function isActiveStatus(status: ExecutionStatus): boolean {
  return ACTIVE_STATUSES.includes(status);
}

export default function ExecutionHistory() {
  const { activeTicketId, activeExecutionId, setActiveExecution } = useWorkbench();
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["executions", activeTicketId],
    queryFn: () => Executions.list({ ticket_id: activeTicketId! }),
    enabled: activeTicketId != null,
    refetchInterval: 5_000,
  });

  const cancelMutation = useMutation({
    mutationFn: (id: number) => Executions.cancel(id),
    onSettled: () => {
      // Refrescar el historial y cualquier indicador de "running" global
      // (todas las queries cuyo key empieza con "executions").
      qc.invalidateQueries({ queryKey: ["executions"] });
    },
  });

  if (!activeTicketId) {
    return (
      <section className={styles.section}>
        <header className={styles.head}>HISTORIAL</header>
        <div className={styles.empty}>
          <span className="muted">elegí un ticket</span>
        </div>
      </section>
    );
  }

  return (
    <section className={styles.section}>
      <header className={styles.head}>HISTORIAL — ticket {activeTicketId}</header>
      <div className={styles.body}>
        {isLoading && <div className="muted">cargando…</div>}
        {!isLoading && (data ?? []).length === 0 && (
          <div className="muted">sin ejecuciones</div>
        )}
        {(data ?? []).map((e) => (
          <Row
            key={e.id}
            exec={e}
            active={e.id === activeExecutionId}
            onClick={() => setActiveExecution(e.id)}
            onCancel={() => cancelMutation.mutate(e.id)}
            cancelling={cancelMutation.isPending && cancelMutation.variables === e.id}
          />
        ))}
      </div>
    </section>
  );
}

function Row({
  exec,
  active,
  onClick,
  onCancel,
  cancelling,
}: {
  exec: AgentExecution;
  active: boolean;
  onClick: () => void;
  onCancel: () => void;
  cancelling: boolean;
}) {
  const icon =
    exec.status === "running"
      ? "⏳"
      : exec.verdict === "approved"
      ? "✓"
      : exec.verdict === "discarded" || exec.status === "error"
      ? "✗"
      : "◐";
  const canCancel = isActiveStatus(exec.status);
  return (
    <div
      className={`${styles.row} ${active ? styles.active : ""}`}
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          onClick();
        }
      }}
    >
      <span className={styles.icon}>{icon}</span>
      <span className={styles.id}>#{exec.id}</span>
      <span className={styles.agent}>{exec.agent_type}</span>
      <span className={styles.time}>
        {new Date(exec.started_at).toLocaleTimeString()}
      </span>
      {canCancel ? (
        <button
          type="button"
          className={styles.cancelBtn}
          disabled={cancelling}
          title="Cancelar ejecución (detiene la sesión del agente)"
          onClick={(ev) => {
            ev.stopPropagation();
            if (cancelling) return;
            if (
              window.confirm(
                `¿Cancelar la ejecución #${exec.id}? Se detendrá la sesión del agente.`
              )
            ) {
              onCancel();
            }
          }}
        >
          {cancelling ? "cancelando…" : "✕ Cancelar"}
        </button>
      ) : (
        <span />
      )}
    </div>
  );
}
