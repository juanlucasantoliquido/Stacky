/**
 * RunReconciliationCard.tsx — Plan 254 F5: "Cierres inconsistentes" en Diagnóstico.
 *
 * Convierte "creemos que arreglamos el falso rojo" en un número que el operador
 * mira. READ-ONLY: el endpoint no cambia ningún estado, no reintenta y no corre
 * en un loop — es un GET a pedido. La card LISTA; el humano decide.
 *
 * Cero trabajo extra: si no hay discrepancias muestra 0 y no pide nada. La card
 * decide su propia visibilidad con un fetch de montaje (404 con la flag
 * STACKY_RUN_RECONCILIATION_ENABLED en OFF → la card no existe).
 */
import { useEffect, useState } from "react";
import { ScanSearch } from "lucide-react";
import { RunReconciliation, type RunReconciliationResponse } from "../api/endpoints";
import styles from "./RunReconciliationCard.module.css";

type Status = "checking-visibility" | "idle" | "running" | "done";

/** Etiquetas humanas de DISCREPANCY_KINDS (services/run_reconciliation.py). */
const KIND_LABELS: Record<string, string> = {
  red_with_delivered_work: "Marcados en error habiendo entregado trabajo",
  green_with_dirty_close: "Terminados con éxito sobre un cierre sucio (sin revisar)",
  green_self_reported_only: "Terminados solo porque el agente lo dijo",
  unclassified_outcome: "Sin causa registrada",
  drain_timeout: "Quedó salida sin terminar de leer",
};

export default function RunReconciliationCard() {
  const [status, setStatus] = useState<Status>("checking-visibility");
  const [hidden, setHidden] = useState(false);
  const [report, setReport] = useState<RunReconciliationResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    RunReconciliation.get()
      .then((res) => {
        if (cancelled) return;
        setReport(res);
        setStatus("done");
      })
      .catch(() => {
        if (!cancelled) setHidden(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (hidden || status === "checking-visibility") return null;

  const refresh = () => {
    setStatus("running");
    RunReconciliation.get()
      .then((res) => {
        setReport(res);
        setStatus("done");
      })
      .catch(() => setStatus("done"));
  };

  const falsoRojo = report?.by_kind?.red_with_delivered_work ?? 0;
  const total = report?.total ?? 0;

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>
          <ScanSearch size={16} />
          Cierres inconsistentes
        </h2>
        <button className={styles.runBtn} onClick={refresh} disabled={status === "running"}>
          {status === "running" ? "Revisando…" : "Revisar ahora"}
        </button>
      </div>

      {total === 0 ? (
        <p className={styles.okLine}>
          ✓ Ninguna corrida quedó con el estado en desacuerdo con lo que realmente pasó.
        </p>
      ) : (
        <>
          <p className={styles.summary}>
            {total} corrida{total === 1 ? "" : "s"} con el estado en desacuerdo con la evidencia.
            {falsoRojo > 0 && (
              <>
                {" "}
                <strong className={styles.falsoRojo}>
                  {falsoRojo} figura{falsoRojo === 1 ? "" : "n"} como fallada
                  {falsoRojo === 1 ? "" : "s"} habiendo entregado trabajo.
                </strong>
              </>
            )}
          </p>
          <ul className={styles.kindList}>
            {Object.entries(report?.by_kind ?? {})
              .filter(([, n]) => n > 0)
              .map(([kind, n]) => (
                <li key={kind}>
                  <span className={styles.count}>{n}</span> {KIND_LABELS[kind] ?? kind}
                </li>
              ))}
          </ul>
          <p className={styles.muted}>
            Solo lectura: nada de esto cambia por su cuenta. Vos decidís qué hacer con cada caso.
          </p>
        </>
      )}
    </div>
  );
}
