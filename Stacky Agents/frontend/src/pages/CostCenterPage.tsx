import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CostCenter, Ops } from "../api/endpoints";
import type { BreakdownDimension, CostFiltersParams } from "../lib/costCenterTypes";
import CostKpiCards from "../components/costcenter/CostKpiCards";
import CostBurnChart from "../components/costcenter/CostBurnChart";
import CostStackedBurnChart from "../components/costcenter/CostStackedBurnChart";
import CostHeatmap from "../components/costcenter/CostHeatmap";
import CostDistributionChart from "../components/costcenter/CostDistributionChart";
import type { BurnBucket } from "../components/costcenter/CostBurnChart";
import CostBreakdownBars from "../components/costcenter/CostBreakdownBars";
import CostTable from "../components/costcenter/CostTable";
import CostFiltersBar from "../components/costcenter/CostFiltersBar";
import OpsHealthSection from "../components/costcenter/OpsHealthSection";
import OpsTrendsSection from "../components/costcenter/OpsTrendsSection";
import HarvestSection from "../components/costcenter/HarvestSection";
import OpsThresholdsForm from "../components/costcenter/OpsThresholdsForm";
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
  // Plan 199 F6 — agrupación de la serie apilada (runtime | model | agent_type).
  const [stackGroupBy, setStackGroupBy] = useState("runtime");

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
  // Plan 199 F6 — tres vistas nuevas sobre los MISMOS filtros. Comparten
  // queryKey con `filters`, así cambiar un filtro las refresca a todas.
  const stackedQ = useQuery({
    queryKey: ["cost-center", "burn-stacked", filters, bucket, stackGroupBy],
    queryFn: () => CostCenter.burnStacked({ ...filters, bucket, group_by: stackGroupBy }),
  });
  const heatmapQ = useQuery({
    queryKey: ["cost-center", "heatmap", filters],
    queryFn: () => CostCenter.heatmap(filters),
  });
  const distributionQ = useQuery({
    queryKey: ["cost-center", "distribution", filters],
    queryFn: () => CostCenter.distribution(filters),
  });
  // Plan 171 — salud operativa y tendencia. Carga on-mount + botón Refrescar:
  // sin pollers nuevos (el latido único del Plan 156 sigue siendo el único).
  const opsQ = useQuery({
    queryKey: ["ops", "summary", filters],
    queryFn: () => Ops.summary(filters),
  });
  const trendsQ = useQuery({
    queryKey: ["ops", "trends", filters],
    queryFn: () => Ops.trends(filters),
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
      {/* Plan 199 F6 — de dónde sale el gasto, cuándo, y con qué forma. Cada
          uno degrada solo a su estado vacío si el backend no trae datos. */}
      <CostStackedBurnChart
        data={stackedQ.data?.enabled === false ? null : stackedQ.data ?? null}
        isLoading={stackedQ.isLoading}
        error={stackedQ.error}
        onRetry={() => stackedQ.refetch()}
        groupBy={stackGroupBy}
        onGroupByChange={setStackGroupBy}
      />
      <CostHeatmap
        data={heatmapQ.data?.enabled === false ? null : heatmapQ.data ?? null}
        isLoading={heatmapQ.isLoading}
        error={heatmapQ.error}
        onRetry={() => heatmapQ.refetch()}
      />
      <CostDistributionChart
        data={distributionQ.data?.enabled === false ? null : distributionQ.data ?? null}
        isLoading={distributionQ.isLoading}
        error={distributionQ.error}
        onRetry={() => distributionQ.refetch()}
      />
      <CostTable
        rows={summary && summary.enabled ? summary.top_runs : []}
        isLoading={summaryQ.isLoading}
        error={summaryQ.error}
        onRetry={() => summaryQ.refetch()}
      />
      {/* Plan 199 F6 — se auto-oculta si STACKY_TELEMETRY_HARVEST_ENABLED está OFF. */}
      <HarvestSection />
      <OpsHealthSection
        data={opsQ.data ?? null}
        isLoading={opsQ.isLoading}
        error={opsQ.error}
        onRetry={() => opsQ.refetch()}
      />
      <OpsTrendsSection
        data={trendsQ.data ?? null}
        isLoading={trendsQ.isLoading}
        error={trendsQ.error}
        onRetry={() => trendsQ.refetch()}
      />
      {opsQ.data?.enabled && opsQ.data.thresholds ? (
        <OpsThresholdsForm
          initial={opsQ.data.thresholds}
          onSaved={() => {
            void opsQ.refetch();
          }}
        />
      ) : null}
    </div>
  );
}
