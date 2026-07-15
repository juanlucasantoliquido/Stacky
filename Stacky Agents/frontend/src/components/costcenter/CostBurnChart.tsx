import { useMemo, useState } from "react";
import { Card, Skeleton } from "../ui";
import EmptyState from "../EmptyState";
import LoadErrorState from "../LoadErrorState";
import type { CostBurn } from "../../lib/costCenterTypes";
import { areaPath, formatUsd, linePath, niceTicks, scaleLinear } from "../../lib/costCenter.logic";
import styles from "./CostBurnChart.module.css";

export type BurnBucket = "hour" | "day" | "week";

export interface CostBurnChartProps {
  data: CostBurn | null;
  isLoading: boolean;
  error?: unknown;
  onRetry?: () => void;
  bucket: BurnBucket;
  onBucketChange: (b: BurnBucket) => void;
}

const WIDTH = 640;
const HEIGHT = 200;
const PAD = 32;

const BUCKET_LABEL: Record<BurnBucket, string> = { hour: "Hora", day: "Día", week: "Semana" };

/** Plan 142 F6 — chart SVG PROPIO (área+línea) del burn temporal, sin librería de
 * gráficos (R5). Math de F5 (linePath/areaPath/scaleLinear/niceTicks). Fallback
 * "Ver como tabla" (R6/accesibilidad); estados vacío/error/skeleton del Plan 140. */
export default function CostBurnChart({
  data, isLoading, error, onRetry, bucket, onBucketChange,
}: CostBurnChartProps) {
  const [asTable, setAsTable] = useState(false);
  const [cumulative, setCumulative] = useState(false);

  const series = data?.series ?? [];

  const chart = useMemo(() => {
    if (series.length === 0) return null;
    const values = series.map((p) => (cumulative ? p.cumulative_billable_usd : p.billable_usd));
    const maxY = Math.max(...values, 0.01);
    const scaleX = scaleLinear([0, Math.max(series.length - 1, 1)], [PAD, WIDTH - PAD]);
    const scaleY = scaleLinear([0, maxY], [HEIGHT - PAD, PAD]);
    const points = values.map((v, i) => ({ x: scaleX(i), y: scaleY(v) }));
    return {
      linePathD: linePath(points),
      areaPathD: areaPath(points, HEIGHT - PAD),
      ticksY: niceTicks(0, maxY, 4),
      scaleY,
    };
  }, [series, cumulative]);

  if (error) return <LoadErrorState what="el burn de costos" error={error} onRetry={onRetry} />;
  if (isLoading) {
    return (
      <Card padding="md">
        <Skeleton height={HEIGHT} />
      </Card>
    );
  }
  if (!data || series.length === 0) {
    return (
      <Card padding="md">
        <EmptyState
          variant="generic"
          title="Sin datos de burn en el rango"
          message="Cuando corran ejecuciones con costo en esta ventana, el burn temporal va a aparecer acá."
        />
      </Card>
    );
  }

  return (
    <Card padding="md">
      <div className={styles.toolbar}>
        <div className={styles.bucketGroup} role="group" aria-label="Bucket temporal">
          {(Object.keys(BUCKET_LABEL) as BurnBucket[]).map((b) => (
            <button
              key={b}
              type="button"
              className={b === bucket ? styles.bucketBtnActive : styles.bucketBtn}
              onClick={() => onBucketChange(b)}
            >
              {BUCKET_LABEL[b]}
            </button>
          ))}
        </div>
        <label className={styles.toggle}>
          <input type="checkbox" checked={cumulative} onChange={(e) => setCumulative(e.target.checked)} />
          Acumulado
        </label>
        <button type="button" className={styles.tableToggle} onClick={() => setAsTable((v) => !v)}>
          {asTable ? "Ver como gráfico" : "Ver como tabla"}
        </button>
      </div>

      {asTable || !chart ? (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Bucket</th>
              <th>Reportado</th>
              <th>Estimado</th>
              <th>Nominal</th>
              <th>Facturable</th>
              <th>Acumulado</th>
              <th>Runs</th>
            </tr>
          </thead>
          <tbody>
            {series.map((p) => (
              <tr key={p.bucket}>
                <td>{p.bucket}</td>
                <td>{formatUsd(p.reported_usd)}</td>
                <td>{formatUsd(p.estimated_usd)}</td>
                <td>{formatUsd(p.nominal_usd)}</td>
                <td>{formatUsd(p.billable_usd)}</td>
                <td>{formatUsd(p.cumulative_billable_usd)}</td>
                <td>{p.runs}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className={styles.svg} role="img"
             aria-label="Burn de costos facturables en el tiempo">
          {chart.ticksY.map((t) => (
            <line
              key={t}
              x1={PAD} x2={WIDTH - PAD}
              y1={chart.scaleY(t)} y2={chart.scaleY(t)}
              className={styles.gridLine}
            />
          ))}
          <path d={chart.areaPathD} className={styles.area} />
          <path d={chart.linePathD} className={styles.line} />
        </svg>
      )}

      <div className={styles.comparison}>
        vs. período anterior: {formatUsd(data.period_comparison.previous_billable_usd)}
        {" → "}
        {formatUsd(data.period_comparison.current_billable_usd)}
        {" "}
        <span className={data.period_comparison.delta_pct >= 0 ? styles.deltaUp : styles.deltaDown}>
          ({data.period_comparison.delta_pct >= 0 ? "+" : ""}{data.period_comparison.delta_pct}%)
        </span>
      </div>
    </Card>
  );
}
