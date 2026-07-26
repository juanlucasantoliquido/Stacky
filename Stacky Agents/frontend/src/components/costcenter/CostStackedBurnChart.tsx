import { useMemo } from "react";

import { Card, Select, Skeleton } from "../ui";
import EmptyState from "../EmptyState";
import LoadErrorState from "../LoadErrorState";
import { formatUsd } from "../../lib/costCenter.logic";
import { maxTotalOf, stackSegments } from "../../lib/costCharts.logic";
import type { CostBurnStacked } from "../../lib/costCenterTypes";
import styles from "./CostStackedBurnChart.module.css";

const WIDTH = 640;
const HEIGHT = 200;
const PAD = 28;

// Paleta estable por índice: el mismo grupo conserva su color entre corridas,
// o comparar dos gráficos sería imposible.
const COLORS = [
  "var(--accent)",
  "var(--ok)",
  "var(--warn)",
  "var(--danger)",
  "var(--muted)",
];

const GROUP_LABEL: Record<string, string> = {
  runtime: "Runtime",
  model: "Modelo",
  agent_type: "Agente",
};

/**
 * Plan 199 F6 — De dónde sale el gasto en el tiempo, no solo cuánto.
 *
 * Un pico en el burn puede ser "un runtime se disparó" o "todos subieron
 * parejo", y se arreglan distinto. Apilar por grupo lo distingue de un vistazo.
 */
export default function CostStackedBurnChart({
  data,
  isLoading,
  error,
  onRetry,
  groupBy,
  onGroupByChange,
}: {
  data: CostBurnStacked | null;
  isLoading: boolean;
  error?: unknown;
  onRetry?: () => void;
  groupBy: string;
  onGroupByChange: (g: string) => void;
}) {
  const series = data?.series ?? [];
  const groups = data?.groups ?? [];
  const maxTotal = useMemo(() => maxTotalOf(series), [series]);

  const selector = (
    <div className={styles.header}>
      <Select value={groupBy} onChange={(e) => onGroupByChange(e.target.value)}>
        {Object.entries(GROUP_LABEL).map(([v, label]) => (
          <option key={v} value={v}>
            Agrupar por {label.toLowerCase()}
          </option>
        ))}
      </Select>
    </div>
  );

  if (error) {
    return (
      <Card>
        {selector}
        <LoadErrorState what="el gasto apilado" error={error} onRetry={onRetry} />
      </Card>
    );
  }
  if (isLoading) {
    return (
      <Card>
        {selector}
        <Skeleton />
      </Card>
    );
  }
  if (!series.length || maxTotal <= 0) {
    return (
      <Card>
        {selector}
        <EmptyState
          title="Sin gasto facturable en la ventana"
          message="Un costo nominal no suma acá: solo lo reportado y lo estimado."
        />
      </Card>
    );
  }

  const anchoBarra = (WIDTH - PAD * 2) / series.length;
  const alto = HEIGHT - PAD * 2;

  return (
    <Card>
      {selector}
      <svg
        className={styles.chart}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`Gasto apilado por ${GROUP_LABEL[groupBy] ?? groupBy}`}
      >
        {series.map((punto, i) => (
          <g key={punto.bucket}>
            {stackSegments(punto, groups, maxTotal, alto).map((seg) => (
              <rect
                key={seg.group}
                x={PAD + i * anchoBarra + 1}
                y={PAD + seg.y}
                width={Math.max(1, anchoBarra - 2)}
                height={seg.height}
                fill={COLORS[groups.indexOf(seg.group) % COLORS.length]}
              >
                <title>{`${punto.bucket} · ${seg.group} · ${formatUsd(seg.value)}`}</title>
              </rect>
            ))}
          </g>
        ))}
        <text className={styles.axis} x={PAD} y={HEIGHT - 6}>
          {series[0]?.bucket}
        </text>
        <text className={styles.axis} x={WIDTH - PAD} y={HEIGHT - 6} textAnchor="end">
          {series[series.length - 1]?.bucket}
        </text>
      </svg>

      <div className={styles.legend}>
        {groups.map((g) => (
          <span key={g} className={styles.legendItem}>
            <Swatch color={COLORS[groups.indexOf(g) % COLORS.length]} />
            {g || "(sin dato)"}
          </span>
        ))}
      </div>
    </Card>
  );
}

/** El color viene de la paleta por índice, no de una clase: SVG-like inline en
 *  un <span> lo prohibiría el ratchet, así que se dibuja como un svg mínimo. */
function Swatch({ color }: { color: string }) {
  return (
    <svg className={styles.legendSwatch} viewBox="0 0 10 10" aria-hidden="true">
      <rect width="10" height="10" rx="2" fill={color} />
    </svg>
  );
}
