import { useEffect, useState } from "react";
import { api } from "../api/client";
import styles from "./ABCompare.module.css";

interface ExecutionSummary {
  id: number;
  agent_type: string;
  status: string;
  output?: string | null;
  metadata?: any;
}

interface Props {
  executionIds: number[];
  onPickWinner?: (executionId: number) => void;
  onClose: () => void;
}

const COLUMN_LABELS = ["Variante A", "Variante B", "Variante C", "Variante D"];

export default function ABCompare({ executionIds, onPickWinner, onClose }: Props) {
  const [executions, setExecutions] = useState<(ExecutionSummary | null)[]>([]);
  const [winnerId, setWinnerId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all(
      executionIds.map((id) =>
        api
          .get<ExecutionSummary>(`/api/executions/${id}`)
          .catch(() => null)
      )
    ).then((results) => {
      if (!cancelled) setExecutions(results);
    });
    return () => {
      cancelled = true;
    };
  }, [executionIds]);

  const handlePick = (id: number) => {
    setWinnerId(id);
    onPickWinner?.(id);
  };

  return (
    <div className={styles.overlay} role="dialog" aria-modal="true">
      <header className={styles.header}>
        <h2>Comparar variantes</h2>
        <button className={styles.closeBtn} onClick={onClose} aria-label="Cerrar">×</button>
      </header>
      <div className={styles.grid} style={{ gridTemplateColumns: `repeat(${executions.length}, 1fr)` }}>
        {executions.map((ex, idx) => (
          <div key={idx} className={`${styles.column} ${winnerId === ex?.id ? styles.winner : ""}`}>
            <div className={styles.colHeader}>
              <strong>{COLUMN_LABELS[idx] ?? `Variante ${idx + 1}`}</strong>
              {ex && (
                <span className={styles.modelTag}>
                  {ex.metadata?.model ?? ex.metadata?.routing_decision?.model ?? "—"}
                </span>
              )}
            </div>
            {ex == null ? (
              <p className={styles.muted}>No se pudo cargar.</p>
            ) : (
              <>
                <pre className={styles.output}>{ex.output ?? "(sin output)"}</pre>
                <button
                  className={`${styles.pickBtn} ${winnerId === ex.id ? styles.picked : ""}`}
                  onClick={() => handlePick(ex.id)}
                  disabled={winnerId === ex.id}
                >
                  {winnerId === ex.id ? "✓ Elegida" : "Elegir"}
                </button>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
