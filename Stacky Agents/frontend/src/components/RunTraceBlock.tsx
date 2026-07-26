import { useQuery } from "@tanstack/react-query";

import { Ops } from "../api/endpoints";
import { SectionHeader, Skeleton, StatusChip } from "./ui";
import { traceRows } from "../services/opsTelemetry";
import { formatDateTime } from "../services/format";
import styles from "./RunTraceBlock.module.css";

/**
 * Plan 171 F7 — Traza estructurada de la corrida abierta.
 *
 * Una sola carga al abrir el drawer (acción explícita del operador). Si la flag
 * está apagada el backend responde `{enabled:false}` y el bloque no se renderiza:
 * el drawer queda exactamente como hoy.
 */
export default function RunTraceBlock({ executionId }: { executionId: number }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["run-trace", executionId],
    queryFn: () => Ops.runTrace(executionId),
  });

  if (isLoading) return <Skeleton lines={3} height={16} />;
  if (isError || !data || data.enabled === false || !data.trace) return null;

  const trace = data.trace;
  const rows = traceRows(trace);

  return (
    <section className={styles.block}>
      <SectionHeader
        title="Traza de la corrida"
        actions={trace.stalled ? <StatusChip tone="warning">Posiblemente colgada</StatusChip> : null}
      />
      <dl className={styles.rows}>
        {rows.map((row) => (
          <div key={row.label} className={styles.row}>
            <dt className={styles.label}>{row.label}</dt>
            <dd className={styles.value}>{row.value}</dd>
          </div>
        ))}
      </dl>
      {trace.phases.length > 0 && (
        <div className={styles.phases}>
          {trace.phases.map((phase) => (
            <span key={phase.name}>
              <span className={styles.phaseName}>{phase.name}</span> →{" "}
              {formatDateTime(phase.ts)}
            </span>
          ))}
        </div>
      )}
      {trace.sin_dato.length > 0 && (
        <p className={styles.sinDato}>
          Sin dato en esta corrida: {trace.sin_dato.join(", ")}. Las corridas
          claude_code_cli históricas previas al Plan 158 pueden no registrar modelo si
          el backfill no las alcanzó.
        </p>
      )}
    </section>
  );
}
