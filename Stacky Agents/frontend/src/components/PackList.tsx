import { useMutation, useQuery } from "@tanstack/react-query";

import { Packs } from "../api/endpoints";
import { useWorkbench } from "../store/workbench";
import styles from "./PackList.module.css";

export default function PackList() {
  const { activeTicketId } = useWorkbench();
  const { data } = useQuery({ queryKey: ["packs"], queryFn: Packs.list });
  const start = useMutation({
    mutationFn: (pack_id: string) =>
      Packs.start({ pack_id, ticket_id: activeTicketId! }),
  });

  return (
    <section className={styles.section}>
      <h3 className={styles.title}>PACKS</h3>
      <div className={styles.list}>
        {(data ?? []).map((p) => (
          <button
            key={p.id}
            className={styles.row}
            disabled={!activeTicketId || start.isPending}
            onClick={() => start.mutate(p.id)}
            title={p.description}
          >
            <span className={styles.play}>▶</span>
            <span className={styles.name}>{p.name}</span>
            <span className={styles.steps}>{p.steps.length} pasos</span>
          </button>
        ))}
      </div>
      {!activeTicketId && (
        <span className="muted" style={{ fontSize: 10 }}>
          elegí un ticket primero
        </span>
      )}
      {start.isSuccess && (
        <span style={{ fontSize: 11, color: "var(--success)" }}>
          pack iniciado: run #{start.data.id}
        </span>
      )}
    </section>
  );
}
