import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Tickets, type TicketSyncResult } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import type { Ticket } from "../types";
import styles from "./TicketSelector.module.css";

export default function TicketSelector() {
  const [search, setSearch] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const { activeTicketId, setActiveTicket, runningExecutionId } = useWorkbench();
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["tickets"],
    queryFn: Tickets.list,
    refetchInterval: 60_000,
  });

  const sync = useMutation({
    mutationFn: Tickets.sync,
    onSuccess: (res: TicketSyncResult) => {
      if (res.ok) {
        setFeedback(
          `Sincronizado: ${res.fetched ?? 0} traídos · ${res.created ?? 0} nuevos · ${res.updated ?? 0} actualizados`
        );
      } else {
        setFeedback(res.message ?? "Error al sincronizar");
      }
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
    },
    onError: (err: Error) => {
      setFeedback(err.message || "Error al sincronizar");
    },
  });

  const tickets = (data ?? []).filter((t) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return t.title.toLowerCase().includes(q) || String(t.ado_id).includes(q);
  });

  return (
    <section className={styles.section}>
      <div className={styles.header}>
        <h3 className={styles.title}>TICKETS</h3>
        <button
          type="button"
          className={styles.refresh}
          onClick={() => {
            setFeedback(null);
            sync.mutate();
          }}
          disabled={sync.isPending}
          title="Actualizar tickets desde Azure DevOps"
        >
          {sync.isPending ? "↻" : "⟳"} {sync.isPending ? "Actualizando…" : "Actualizar"}
        </button>
      </div>
      <input
        className={styles.search}
        placeholder="Buscar..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      {feedback && <div className={styles.feedback}>{feedback}</div>}
      <div className={styles.list}>
        {isLoading && <div className="muted">cargando…</div>}
        {!isLoading && tickets.length === 0 && (
          <div className="muted">sin tickets</div>
        )}
        {tickets.map((t) => (
          <Row
            key={t.id}
            ticket={t}
            active={t.id === activeTicketId}
            running={runningExecutionId != null && t.id === activeTicketId}
            onSelect={() => setActiveTicket(t.id)}
          />
        ))}
      </div>
    </section>
  );
}

function Row({
  ticket,
  active,
  running,
  onSelect,
}: {
  ticket: Ticket;
  active: boolean;
  running: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      className={`${styles.row} ${active ? styles.active : ""} ${running ? styles.running : ""}`}
      onClick={onSelect}
    >
      <div className={styles.rowHead}>
        <span className={styles.adoId}>ADO-{ticket.ado_id}</span>
        {running && <span className={styles.runningBadge} title="Agente procesando">⏳</span>}
        <span className={styles.state}>{ticket.ado_state ?? "—"}</span>
      </div>
      <div className={styles.rowTitle}>{ticket.title}</div>
      {ticket.last_execution && (
        <div className={styles.rowMeta}>
          última: {ticket.last_execution.agent_type} •{" "}
          {ticket.last_execution.status}
        </div>
      )}
    </button>
  );
}
