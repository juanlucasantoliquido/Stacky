import { Card } from "../ui";
import type { CostSummary } from "../../lib/costCenterTypes";
import { formatPct, formatTokens, formatUsd } from "../../lib/costCenter.logic";
import styles from "./CostKpiCards.module.css";

export interface CostKpiCardsProps {
  summary: CostSummary;
}

interface Kpi {
  label: string;
  value: string;
  hint?: string;
}

/** Plan 142 F6 — fila de KPI cards (Card del Plan 138). Cada monto pasa por
 * formatUsd/formatTokens (F5): `null` siempre se ve como "n/d", nunca "$0.00". */
export default function CostKpiCards({ summary }: CostKpiCardsProps) {
  const kpis: Kpi[] = [
    { label: "Costo facturable", value: formatUsd(summary.billable_usd),
      hint: summary.capped ? "Ventana acotada a las 20.000 ejecuciones más recientes" : undefined },
    { label: "Reportado", value: formatUsd(summary.reported_usd) },
    { label: "Estimado", value: formatUsd(summary.estimated_usd),
      hint: `${formatPct(summary.pct_estimated)} del facturable` },
    { label: "Nominal (suscripción)", value: formatUsd(summary.nominal_usd), hint: "No facturable" },
    { label: "Tokens in", value: formatTokens(summary.tokens_in_total) },
    { label: "Tokens out", value: formatTokens(summary.tokens_out_total) },
    { label: "Cache leído", value: formatTokens(summary.cache_read_total) },
    { label: "Ahorro estimado (cache)", value: formatUsd(summary.cache_savings_usd_total) },
    { label: "Promedio / run", value: formatUsd(summary.avg_cost_per_run_usd) },
    { label: "Costo / tarea completada", value: formatUsd(summary.cost_per_completed_task_usd) },
    { label: "Ratio tokens out/in", value: summary.tokens_out_in_ratio.toFixed(2) },
    { label: "Runs sin costo", value: `${summary.runs_without_cost} / ${summary.runs_total}` },
  ];

  return (
    <div className={styles.grid}>
      {kpis.map((k) => (
        <Card key={k.label} padding="sm">
          <div className={styles.label}>{k.label}</div>
          <div className={styles.value}>{k.value}</div>
          {k.hint && <div className={styles.hint}>{k.hint}</div>}
        </Card>
      ))}
    </div>
  );
}
