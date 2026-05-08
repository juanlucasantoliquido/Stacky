import { useQuery } from "@tanstack/react-query";

import { Executions } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import type { AgentExecution } from "../types";
import styles from "./ExecutionHistory.module.css";

export default function ExecutionHistory() {
  const { activeTicketId, activeExecutionId, setActiveExecution } = useWorkbench();

  const { data, isLoading } = useQuery({
    queryKey: ["executions", activeTicketId],
    queryFn: () => Executions.list({ ticket_id: activeTicketId! }),
    enabled: activeTicketId != null,
    refetchInterval: 5_000,
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
}: {
  exec: AgentExecution;
  active: boolean;
  onClick: () => void;
}) {
  const icon =
    exec.status === "running"
      ? "⏳"
      : exec.verdict === "approved"
      ? "✓"
      : exec.verdict === "discarded" || exec.status === "error"
      ? "✗"
      : "◐";
  return (
    <button
      className={`${styles.row} ${active ? styles.active : ""}`}
      onClick={onClick}
    >
      <span className={styles.icon}>{icon}</span>
      <span className={styles.id}>#{exec.id}</span>
      <span className={styles.agent}>{exec.agent_type}</span>
      <span className={styles.time}>
        {new Date(exec.started_at).toLocaleTimeString()}
      </span>
    </button>
  );
}
