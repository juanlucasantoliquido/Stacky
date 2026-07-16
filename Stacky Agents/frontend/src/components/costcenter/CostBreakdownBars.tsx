import { useEffect, useMemo, useRef, useState } from "react";
import { Card, Skeleton } from "../ui";
import EmptyState from "../EmptyState";
import LoadErrorState from "../LoadErrorState";
import type { BreakdownDimension, CostBreakdown } from "../../lib/costCenterTypes";
import { formatUsd, scaleLinear } from "../../lib/costCenter.logic";
import styles from "./CostBreakdownBars.module.css";

export interface CostBreakdownBarsProps {
  data: CostBreakdown | null;
  isLoading: boolean;
  error?: unknown;
  onRetry?: () => void;
  dimension: BreakdownDimension;
  onDimensionChange: (d: BreakdownDimension) => void;
}

const DIMENSIONS: { value: BreakdownDimension; label: string }[] = [
  { value: "runtime", label: "Runtime" },
  { value: "model", label: "Modelo" },
  { value: "agent_type", label: "Agente" },
  { value: "ticket", label: "Ticket" },
  { value: "project", label: "Proyecto" },
  { value: "day", label: "Día" },
];

// Acento único para todas las barras (color fijo en .barFill del CSS module,
// token --status-success-text = "reportado"; nunca hex, Plan 141).

/** Ancho por fila seteado imperativamente, sin objeto de estilo inline en JSX:
 * el ratchet de deuda visual (plan 138 F0) da alcance cero a archivos nuevos,
 * así que un ancho dinámico por dato no puede ir en un prop de estilo literal. */
function BarFill({ pct }: { pct: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.style.width = `${pct}%`;
  }, [pct]);
  return <span ref={ref} className={styles.barFill} />;
}

/** Plan 142 F6 — barras horizontales SVG-simples (div-based, sin librería, R5)
 * por dimensión seleccionable. Fallback tabla implícito (misma lista sirve de
 * tabla accesible). Estados vacío/error/skeleton del Plan 140. */
export default function CostBreakdownBars({
  data, isLoading, error, onRetry, dimension, onDimensionChange,
}: CostBreakdownBarsProps) {
  const groups = data?.groups ?? [];
  const maxBillable = useMemo(
    () => Math.max(...groups.map((g) => g.billable_usd), 0.01),
    [groups],
  );
  const scaleW = useMemo(() => scaleLinear([0, maxBillable], [0, 100]), [maxBillable]);

  if (error) return <LoadErrorState what="el desglose de costos" error={error} onRetry={onRetry} />;

  return (
    <Card padding="md">
      <div className={styles.toolbar} role="group" aria-label="Dimensión de desglose">
        {DIMENSIONS.map((d) => (
          <button
            key={d.value}
            type="button"
            className={d.value === dimension ? styles.dimBtnActive : styles.dimBtn}
            onClick={() => onDimensionChange(d.value)}
          >
            {d.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <Skeleton lines={5} height={20} />
      ) : groups.length === 0 ? (
        <EmptyState
          variant="generic"
          title="Sin datos para este desglose"
          message="Cuando haya ejecuciones con costo en el rango, van a aparecer agrupadas acá."
        />
      ) : (
        <ul className={styles.bars}>
          {groups.map((g) => (
            <li key={g.key} className={styles.barRow}>
              <span className={styles.barLabel} title={g.key}>{g.key}</span>
              <span className={styles.barTrack}>
                <BarFill pct={scaleW(g.billable_usd)} />
              </span>
              <span className={styles.barValue}>{formatUsd(g.billable_usd)}</span>
              <span className={styles.barRuns}>{g.runs} runs</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
