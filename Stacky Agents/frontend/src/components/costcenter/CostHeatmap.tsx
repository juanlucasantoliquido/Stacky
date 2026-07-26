import { useMemo, useRef, useEffect } from "react";

import { Card, Skeleton } from "../ui";
import EmptyState from "../EmptyState";
import LoadErrorState from "../LoadErrorState";
import { formatUsd } from "../../lib/costCenter.logic";
import {
  WEEKDAY_LABELS,
  heatIntensity,
  heatmapGrid,
  heatmapTooltip,
} from "../../lib/costCharts.logic";
import type { CostHeatmap as CostHeatmapData } from "../../lib/costCenterTypes";
import styles from "./CostHeatmap.module.css";

/**
 * Plan 199 F6 — Cuándo se gasta: día de semana × hora.
 *
 * Responde algo que ni el total ni la serie temporal contestan: si el gasto se
 * concentra en horario laboral o si hay algo corriendo de madrugada.
 *
 * Sin librería de gráficos (regla del 142): es una grilla de divs.
 */
export default function CostHeatmap({
  data,
  isLoading,
  error,
  onRetry,
}: {
  data: CostHeatmapData | null;
  isLoading: boolean;
  error?: unknown;
  onRetry?: () => void;
}) {
  const grid = useMemo(() => heatmapGrid(data?.cells), [data]);
  const max = data?.max_billable_usd ?? 0;
  const hayDatos = (data?.cells?.length ?? 0) > 0 && max > 0;

  if (error) {
    return (
      <Card>
        <LoadErrorState what="el mapa de calor de costos" error={error} onRetry={onRetry} />
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
  if (!hayDatos) {
    return (
      <Card>
        <EmptyState
          title="Sin gasto en la ventana elegida"
          message="Cambiá el rango de fechas o los filtros."
        />
      </Card>
    );
  }

  return (
    <Card>
      <div className={styles.grid}>
        {grid.map((fila, weekday) => (
          <div key={weekday} className={styles.row}>
            <span className={styles.rowLabel}>{WEEKDAY_LABELS[weekday]}</span>
            {fila.map((celda) => (
              <HeatCell
                key={celda.hour}
                intensity={heatIntensity(celda.billable_usd, max)}
                title={heatmapTooltip(celda, formatUsd)}
              />
            ))}
          </div>
        ))}
        <div className={styles.hourAxis}>
          {Array.from({ length: 24 }, (_, h) => (
            <span key={h} className={styles.hourTick}>
              {h % 3 === 0 ? h : ""}
            </span>
          ))}
        </div>
      </div>

      <div className={styles.legend}>
        <span>menos</span>
        {[0, 0.25, 0.5, 0.75, 1].map((i) => (
          <HeatCell key={i} intensity={i} title="" legend />
        ))}
        <span>más · máx {formatUsd(max)}</span>
      </div>
    </Card>
  );
}

/**
 * La intensidad es un valor continuo, no una clase de CSS module: se aplica por
 * `ref` + effect, que es el patrón que el ratchet de deuda visual admite en
 * archivos nuevos (el atributo de estilo inline tiene tolerancia cero).
 */
function HeatCell({
  intensity,
  title,
  legend = false,
}: {
  intensity: number;
  title: string;
  legend?: boolean;
}) {
  const ref = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    if (ref.current) {
      ref.current.style.backgroundColor = `color-mix(in srgb, var(--accent) ${Math.round(
        intensity * 100
      )}%, transparent)`;
    }
  }, [intensity]);

  return (
    <span
      ref={ref}
      className={legend ? styles.legendSwatch : styles.cell}
      title={title}
      aria-label={title || undefined}
    />
  );
}
