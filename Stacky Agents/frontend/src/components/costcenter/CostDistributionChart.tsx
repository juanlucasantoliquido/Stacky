import { useMemo } from "react";

import { Card, Skeleton } from "../ui";
import EmptyState from "../EmptyState";
import LoadErrorState from "../LoadErrorState";
import { formatUsd } from "../../lib/costCenter.logic";
import {
  binHeight,
  binLabel,
  distributionHeadline,
  maxBinCount,
} from "../../lib/costCharts.logic";
import type { CostDistribution } from "../../lib/costCenterTypes";
import styles from "./CostDistributionChart.module.css";

const WIDTH = 640;
const HEIGHT = 180;
const PAD = 24;

/**
 * Plan 199 F6 — La forma del gasto por corrida, que un promedio esconde.
 *
 * Cien corridas baratas y una carísima dan el mismo promedio que ciento una
 * medianas, y no son la misma situación: en la primera el gasto está en la cola
 * y es ahí donde hay algo que mirar.
 *
 * SVG propio, sin librería de gráficos (regla del 142).
 */
export default function CostDistributionChart({
  data,
  isLoading,
  error,
  onRetry,
}: {
  data: CostDistribution | null;
  isLoading: boolean;
  error?: unknown;
  onRetry?: () => void;
}) {
  const bins = data?.bins ?? [];
  const maxCount = useMemo(() => maxBinCount(bins), [bins]);
  const titular = distributionHeadline(bins, data?.total ?? 0);

  if (error) {
    return (
      <Card>
        <LoadErrorState what="la distribución de costos" error={error} onRetry={onRetry} />
      </Card>
    );
  }
  if (isLoading) {
    return (
      <Card>
        <Skeleton />
      </Card>
    );
  }
  if (!bins.length || !maxCount) {
    return (
      <Card>
        <EmptyState
          title="Sin corridas con costo conocido"
          message="Una corrida sin costo no es una corrida de cero: no entra en el histograma."
        />
      </Card>
    );
  }

  const anchoBarra = (WIDTH - PAD * 2) / bins.length;
  const alto = HEIGHT - PAD * 2;

  return (
    <Card>
      <p className={styles.headline}>{titular}</p>
      <svg
        className={styles.chart}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`Distribución de costo por corrida. ${titular}`}
      >
        {bins.map((bin, i) => {
          const h = binHeight(bin.count, maxCount, alto);
          return (
            <rect
              key={i}
              className={styles.bar}
              x={PAD + i * anchoBarra + 1}
              y={PAD + (alto - h)}
              width={Math.max(1, anchoBarra - 2)}
              height={h}
            >
              <title>{`${binLabel(bin, formatUsd)} · ${bin.count} corrida(s)`}</title>
            </rect>
          );
        })}
        <text className={styles.axis} x={PAD} y={HEIGHT - 6}>
          {formatUsd(data?.min ?? 0)}
        </text>
        <text className={styles.axis} x={WIDTH - PAD} y={HEIGHT - 6} textAnchor="end">
          {formatUsd(data?.max ?? 0)}
        </text>
      </svg>
    </Card>
  );
}
