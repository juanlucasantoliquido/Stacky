/**
 * PublishLedgerPanel.tsx — Plan 153.
 *
 * Panel de Diagnostico del ledger de publicaciones a ADO. Lista SOLO las filas
 * atascadas (pending stale + failed) y ofrece desbloqueo humano 1-click:
 * Re-publicar o Descartar. El sistema jamas republica solo (human-in-the-loop).
 *
 * Si no hay filas atascadas -> render null (cero ruido para el operador).
 * Patron: useEffect + api.get (igual que OperationalHealthCard.tsx).
 * Deuda visual cero: sin estilos inline; todo por PublishLedgerPanel.module.css.
 */
import { useCallback, useEffect, useState } from "react";
import { PublishLedger, type PublishLedgerSnapshot } from "../api/endpoints";
import { partitionLedger, ledgerRowLabel, canRepublish } from "../services/publishLedgerView";
import styles from "./PublishLedgerPanel.module.css";

export default function PublishLedgerPanel() {
  const [data, setData] = useState<PublishLedgerSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [inFlight, setInFlight] = useState<number | null>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    return PublishLedger.list()
      .then((res) => setData(res))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    let cancelled = false;
    PublishLedger.list()
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch(() => {
        if (!cancelled) setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading && data === null) return null;
  if (data === null) return null;

  const { actionable, empty } = partitionLedger(data);
  if (empty) return null; // el panel no ocupa espacio cuando no hay stuck

  const handleRepublish = async (executionId: number) => {
    setInFlight(executionId);
    try {
      await PublishLedger.republish(executionId);
      await refresh();
    } finally {
      setInFlight(null);
    }
  };

  const handleDiscard = async (executionId: number) => {
    setInFlight(executionId);
    try {
      await PublishLedger.discard(executionId);
      await refresh();
    } finally {
      setInFlight(null);
    }
  };

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>Publicaciones atascadas</h2>
        <span className={styles.subtitle}>
          {actionable.length} ejecucion(es) sin desenlace — desbloqueo humano 1-click
        </span>
      </div>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Ejecucion</th>
            <th>Detalle</th>
            <th className={styles.actionsHead}>Acciones</th>
          </tr>
        </thead>
        <tbody>
          {actionable.map((row) => {
            const busy = inFlight === row.execution_id;
            return (
              <tr key={row.id}>
                <td className={styles.idCell}>#{row.execution_id}</td>
                <td className={styles.detailCell}>{ledgerRowLabel(row)}</td>
                <td className={styles.actions}>
                  <button
                    type="button"
                    className={`${styles.btn} ${styles.btnPrimary}`}
                    disabled={busy || !canRepublish(row)}
                    onClick={() => handleRepublish(row.execution_id)}
                  >
                    {busy ? "..." : "Re-publicar"}
                  </button>
                  <button
                    type="button"
                    className={`${styles.btn} ${styles.btnDanger}`}
                    disabled={busy}
                    onClick={() => handleDiscard(row.execution_id)}
                  >
                    {busy ? "..." : "Descartar"}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
