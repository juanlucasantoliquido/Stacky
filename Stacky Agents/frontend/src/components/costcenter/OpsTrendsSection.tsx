import { SectionHeader, Skeleton } from "../ui";
import LoadErrorState from "../LoadErrorState";
import type { OpsTrendsResponse } from "../../lib/opsTelemetryTypes";
import { barPercents } from "../../services/opsTelemetry";
import { formatCostUsd } from "../../services/format";
import styles from "./OpsTrendsSection.module.css";

/**
 * Plan 171 F6 — Serie diaria de corridas y errores.
 *
 * El eje es continuo por construcción (el backend rellena los días sin corridas),
 * así que un hueco visual significa "cero", no "sin dato". Las alturas se aplican
 * con ref imperativo para no romper el ratchet de deuda visual.
 */
export default function OpsTrendsSection({
  data,
  isLoading,
  error,
  onRetry,
}: {
  data: OpsTrendsResponse | null;
  isLoading: boolean;
  error: unknown;
  onRetry: () => void;
}) {
  if (isLoading) return <Skeleton lines={2} height={60} />;
  if (error) {
    return <LoadErrorState what="la tendencia diaria" error={error} onRetry={onRetry} />;
  }
  if (!data || data.enabled === false) return null;

  const series = data.series ?? [];
  const runsPct = barPercents(series.map((s) => s.runs));
  const errorsPct = barPercents(series.map((s) => s.errors));

  return (
    <section className={styles.section}>
      <SectionHeader title="Tendencia diaria (corridas y errores)" />
      {series.length === 0 ? (
        <p className={styles.empty}>Sin datos en la ventana seleccionada.</p>
      ) : (
        <>
          <div className={styles.chart}>
            {series.map((point, i) => (
              <div
                key={point.date}
                className={styles.day}
                title={`${point.date} · ${point.runs} corridas · ${point.errors} errores · ${formatCostUsd(point.billable_usd)}`}
              >
                <div className={styles.track}>
                  <div
                    className={styles.barFill}
                    ref={(el) => {
                      if (el) el.style.height = `${runsPct[i] ?? 0}%`;
                    }}
                  />
                </div>
                <div className={styles.track}>
                  <div
                    className={`${styles.barFill} ${styles.barErrors}`}
                    ref={(el) => {
                      if (el) el.style.height = `${errorsPct[i] ?? 0}%`;
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
          <div className={styles.legend}>
            <span>
              <span className={styles.swatch} />
              Corridas
            </span>
            <span>
              <span className={`${styles.swatch} ${styles.swatchErrors}`} />
              Errores
            </span>
          </div>
        </>
      )}
    </section>
  );
}
