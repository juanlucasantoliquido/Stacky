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
import { Button, useConfirm } from "./ui";
import {
  MAX_RECONCILIATION_ROWS,
  actionForItem,
  correctionPath,
  type ReconciliationItem,
} from "./reconciliationActions";
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

/** Plan 269 F8 — una linea de texto llano con la precision OBSERVADA del
 *  veredicto. El numero se MUESTRA; jamas se usa para auto-ajustar pesos ni
 *  umbrales (eso seria auto-tuneo y lo decide el operador en otro plan). */
function textoCalibracion(a: RunReconciliationResponse["verdict_agreement"]): string {
  if (!a || !a.propuestos) {
    return "Todavía no hay casos suficientes para saber si estoy calibrado.";
  }
  const pct = a.ratio === null || a.ratio === undefined ? null : Math.round(a.ratio * 100);
  const cola = pct === null ? "" : ` (${pct}%)`;
  return `De los ${a.propuestos} casos que marqué como probable falso rojo en ${a.days} días, corregiste ${a.confirmados}${cola}.`;
}

export default function RunReconciliationCard() {
  const [status, setStatus] = useState<Status>("checking-visibility");
  const [hidden, setHidden] = useState(false);
  const [report, setReport] = useState<RunReconciliationResponse | null>(null);
  const [corrigiendo, setCorrigiendo] = useState<number | null>(null);
  const askConfirm = useConfirm();

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
  // Cap de filas: una card de diagnostico no vuelca 200 lineas.
  const itemsVisibles: ReconciliationItem[] = ((report?.items ?? []) as ReconciliationItem[])
    .slice(0, MAX_RECONCILIATION_ROWS);

  /** Plan 269 F6 — la correccion la dispara el HUMANO, con confirmacion, y va al
   *  endpoint que NO publica en ningun sistema externo. Se usa `fetch` crudo y no
   *  el wrapper api.*, porque ese LANZA en cualquier non-2xx y una card de
   *  diagnostico no debe romperse por eso. */
  const corregir = async (it: ReconciliationItem) => {
    const accion = actionForItem(it);
    if (!accion) return;
    if (!(await askConfirm({ message: accion.confirm }))) return;
    setCorrigiendo(it.ticket_id);
    try {
      await fetch(correctionPath(it.ticket_id), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: accion.targetStatus, reason: accion.reason }),
      });
      refresh();
    } catch {
      /* la card degrada en silencio: el operador puede volver a intentar */
    } finally {
      setCorrigiendo(null);
    }
  };

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
          {/* Plan 269 F6 — de "hay 7 falsos rojos" a "corregí este". La card
              LISTA los items y ofrece un boton SOLO si el kind tiene una
              correccion obvia y segura y el backend habilito el HITL. Nada se
              corrige solo: cada click pide confirmacion explicita. */}
          {report?.hitl_enabled && itemsVisibles.length > 0 && (
            <ul className={styles.itemList}>
              {itemsVisibles.map((it) => {
                const accion = actionForItem(it);
                return (
                  <li key={`${it.execution_id}-${it.ticket_id}`} className={styles.itemRow}>
                    <span className={styles.itemTicket}>#{it.ticket_id}</span>
                    <span className={styles.itemDetail}>{it.detail}</span>
                    {accion && (
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={corrigiendo === it.ticket_id}
                        onClick={() => void corregir(it)}
                      >
                        {corrigiendo === it.ticket_id ? "Corrigiendo…" : accion.label}
                      </Button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          {report?.verdict_agreement && (
            <p className={styles.muted}>{textoCalibracion(report.verdict_agreement)}</p>
          )}
          <p className={styles.muted}>
            Solo lectura: nada de esto cambia por su cuenta. Vos decidís qué hacer con cada caso.
          </p>
        </>
      )}
    </div>
  );
}
