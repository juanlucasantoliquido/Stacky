import { SectionHeader, Skeleton, StatusChip } from "../ui";
import LoadErrorState from "../LoadErrorState";
import type { OpsGroup, OpsSummaryResponse } from "../../lib/opsTelemetryTypes";
import { breachLabel, severityTone } from "../../services/opsTelemetry";
import { formatCostUsd, formatDuration, formatPercent } from "../../services/format";
import styles from "./OpsHealthSection.module.css";

/**
 * Plan 171 F6 — Salud operativa dentro del Centro de Costos.
 *
 * Solo AVISA: chips por umbral, tabla por (agente × runtime) y la línea de
 * corridas posiblemente colgadas. Ninguna acción automática — el operador
 * decide. Con la flag apagada el backend responde `{enabled:false}` y esta
 * sección no se renderiza (la página queda como estaba).
 */

const DASH = "—";

function pct(value: number | null): string {
  return value == null ? DASH : formatPercent(value * 100, 1);
}

function secs(value: number | null): string {
  return value == null ? DASH : formatDuration(value * 1000);
}

function modelsLabel(models: Record<string, number>): string {
  const entries = Object.entries(models || {});
  if (!entries.length) return DASH;
  return entries.map(([name, n]) => `${name} ×${n}`).join(", ");
}

export default function OpsHealthSection({
  data,
  isLoading,
  error,
  onRetry,
}: {
  data: OpsSummaryResponse | null;
  isLoading: boolean;
  error: unknown;
  onRetry: () => void;
}) {
  if (isLoading) return <Skeleton lines={3} height={70} />;
  if (error) {
    return <LoadErrorState what="la salud operativa" error={error} onRetry={onRetry} />;
  }
  if (!data || data.enabled === false) return null;

  const groups: OpsGroup[] = data.groups ?? [];
  const breaches = data.breaches ?? [];
  const stalls = data.stalls;

  return (
    <section className={styles.section}>
      <SectionHeader title="Salud operativa" />

      <div className={styles.chips}>
        {breaches.length === 0 ? (
          <StatusChip tone="neutral">Sin avisos</StatusChip>
        ) : (
          breaches.map((b, i) => (
            <StatusChip
              key={`${b.rule_id}-${b.agent_type ?? ""}-${b.runtime ?? ""}-${i}`}
              tone={severityTone(b.severity)}
            >
              {breachLabel(b)}
            </StatusChip>
          ))
        )}
      </div>

      {groups.length === 0 ? (
        <p className={styles.empty}>Sin corridas en la ventana seleccionada.</p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Agente</th>
                <th>Runtime</th>
                <th className={styles.num}>Corridas</th>
                <th className={styles.num}>Errores</th>
                <th className={styles.num}>% error</th>
                <th className={styles.num}>p50</th>
                <th className={styles.num}>p90</th>
                <th className={styles.num}>Costo</th>
                <th>Modelos</th>
              </tr>
            </thead>
            <tbody>
              {groups.map((g) => (
                <tr key={`${g.agent_type}-${g.runtime}`}>
                  <td>{g.agent_type}</td>
                  <td>{g.runtime}</td>
                  <td className={styles.num}>{g.runs}</td>
                  <td className={styles.num}>{g.error}</td>
                  <td className={styles.num}>{pct(g.error_rate)}</td>
                  <td className={styles.num}>{secs(g.p50_seconds)}</td>
                  <td className={styles.num}>{secs(g.p90_seconds)}</td>
                  <td className={styles.num}>{formatCostUsd(g.billable_usd)}</td>
                  <td className={styles.models}>{modelsLabel(g.models)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {stalls && stalls.count > 0 && (
        <p className={styles.stalls}>
          {stalls.count} corrida(s) posiblemente colgadas: #
          {stalls.execution_ids.join(", #")}
        </p>
      )}
    </section>
  );
}
