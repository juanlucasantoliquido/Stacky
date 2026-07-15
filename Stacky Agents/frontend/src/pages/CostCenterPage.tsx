import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CostCenter } from "../api/endpoints";
import type { BreakdownDimension, CostFiltersParams } from "../lib/costCenterTypes";
import CostKpiCards from "../components/costcenter/CostKpiCards";
import CostBurnChart from "../components/costcenter/CostBurnChart";
import type { BurnBucket } from "../components/costcenter/CostBurnChart";
import CostBreakdownBars from "../components/costcenter/CostBreakdownBars";
import CostTable from "../components/costcenter/CostTable";
import CostFiltersBar from "../components/costcenter/CostFiltersBar";
import { Skeleton } from "../components/ui";
import LoadErrorState from "../components/LoadErrorState";
import EmptyState from "../components/EmptyState";
import styles from "./CostCenterPage.module.css";

/** Plan 142 F6 — Centro de Costos: KPIs+Codeburn read-only sobre telemetría ya
 * persistida (§1). Dueño del estado de filtros; react-query (ya instalado)
 * llama a los 3 endpoints gated por STACKY_COST_CENTER_ENABLED. Con
 * `{enabled:false}` muestra el estado "desactivado, activala en Arnés"
 * (nunca crashea ni queda en blanco). */
export default function CostCenterPage() {
  const [filters, setFilters] = useState<CostFiltersParams>({ days: 30 });
  const [bucket, setBucket] = useState<BurnBucket>("day");
  const [dimension, setDimension] = useState<BreakdownDimension>("runtime");

  const summaryQ = useQuery({
    queryKey: ["cost-center", "summary", filters],
    queryFn: () => CostCenter.summary(filters),
  });
  const burnQ = useQuery({
    queryKey: ["cost-center", "burn", filters, bucket],
    queryFn: () => CostCenter.burn({ ...filters, bucket }),
  });
  const breakdownQ = useQuery({
    queryKey: ["cost-center", "breakdown", filters, dimension],
    queryFn: () => CostCenter.breakdown(dimension, filters),
  });

  const summary = summaryQ.data;

  if (summaryQ.isLoading) {
    return (
      <div className={styles.page}>
        <Skeleton lines={3} height={80} />
      </div>
    );
  }

  if (summaryQ.isError) {
    return (
      <div className={styles.page}>
        <LoadErrorState what="el Centro de Costos" error={summaryQ.error} onRetry={() => summaryQ.refetch()} />
      </div>
    );
  }

  if (summary && !summary.enabled) {
    return (
      <div className={styles.page}>
        <EmptyState
          variant="generic"
          title="Centro de Costos desactivado"
          message="Activá STACKY_COST_CENTER_ENABLED desde Configuración → Arnés (sub-tab Observabilidad) para ver esta vista."
        />
      </div>
    );
  }

  const burnData = burnQ.data && burnQ.data.enabled ? burnQ.data : null;
  const breakdownData = breakdownQ.data && breakdownQ.data.enabled ? breakdownQ.data : null;

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Centro de Costos</h1>
      <CostFiltersBar value={filters} onChange={setFilters} />
      {summary && summary.enabled && <CostKpiCards summary={summary} />}
      <CostBurnChart
        data={burnData}
        isLoading={burnQ.isLoading}
        error={burnQ.error}
        onRetry={() => burnQ.refetch()}
        bucket={bucket}
        onBucketChange={setBucket}
      />
      <CostBreakdownBars
        data={breakdownData}
        isLoading={breakdownQ.isLoading}
        error={breakdownQ.error}
        onRetry={() => breakdownQ.refetch()}
        dimension={dimension}
        onDimensionChange={setDimension}
      />
      <CostTable
        rows={summary && summary.enabled ? summary.top_runs : []}
        isLoading={summaryQ.isLoading}
        error={summaryQ.error}
        onRetry={() => summaryQ.refetch()}
      />
    </div>
  );
}
