import { useCallback, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CostCenter, Ops } from "../api/endpoints";
import type {
  BreakdownDimension, CostFiltersParams,
  Distribution, ExecutionScore, Grade, StatsBlock, TicketScore,
} from "../lib/costCenterTypes";
import { COST_STAT_DIMENSIONS, COST_STAT_METRICS } from "../lib/costCenterTypes";
import {
  costSubTabFrom, costSubTabToSegment, parseRoute, serializeRoute,
} from "../services/routes";
import type { CostSubTab } from "../services/routes";
import { Card, SectionHeader, Select, StatusChip, Tabs } from "../components/ui";
import type { StatusTone } from "../components/ui";
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

/* ── Plan 242 F7 — helpers de presentación, PUROS ──────────────────────────
 * Viven acá y no en un `.logic.ts` nuevo porque esta corrida sólo tiene
 * permitido tocar esta página; son funciones sin React ni DOM, así que se
 * pueden extraer sin cambiar comportamiento cuando el plan siguiente cree su
 * módulo propio. */

const NUM_ES = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 4 });

/** `null` es AUSENCIA de dato, no un 0: se muestra como raya, nunca como cero. */
function fmt(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : NUM_ES.format(v);
}

/** Tono del chip por nota. Usa los tonos del tema (`success`/`warning`/
 *  `danger`/`neutral`); NO existe la familia de tokens `--color-*`. */
function gradeTone(grade: Grade): StatusTone {
  if (grade === "A") return "success";
  if (grade === "B") return "info";
  if (grade === "C") return "warning";
  if (grade === "D" || grade === "E") return "danger";
  return "neutral";
}

/** "p50 0,0412 · p90 0,213 · p99 0,88 (n=412)"; sin datos ⇒ lo dice. */
function percentileSummary(d: Distribution): string {
  if (!d || d.n === 0) return "Sin datos";
  return `p50 ${fmt(d.p50)} · p90 ${fmt(d.p90)} · p99 ${fmt(d.p99)} (n=${d.n})`;
}

/** Cuando no aplica devuelve el motivo del backend TAL CUAL (no lo reinterpreta). */
function outlierSummary(o: { applicable: boolean; reason: string; n_outliers: number;
                            fence_low: number | null; fence_high: number | null }): string {
  if (!o) return "Sin datos";
  if (!o.applicable) return o.reason;
  return `${o.n_outliers} fuera de rango (vallas ${fmt(o.fence_low)} – ${fmt(o.fence_high)})`;
}

/** Alto de barra en %, sin dividir por cero cuando todos los bins están en 0. */
function barPercent(count: number, maxCount: number): number {
  if (!maxCount || maxCount <= 0) return 0;
  return Math.round((count / maxCount) * 100);
}

/** Plan 242 F7 — sub-tab "Estadísticas". */
function StatsPanel({ block, titulo, metric }: {
  block: StatsBlock; titulo: string; metric: string;
}) {
  const m = block.metrics?.[metric];
  const bins = m?.histogram ?? [];
  const maxCount = bins.reduce((acc, b) => Math.max(acc, b.count), 0);
  return (
    <Card>
      <SectionHeader
        title={titulo}
        subtitle={`${block.runs_total} corrida(s) · ${m ? percentileSummary(m.overall) : "Sin datos"}`}
      />
      {!m || m.overall.n === 0 ? (
        <p>Sin datos para esta métrica en el período filtrado.</p>
      ) : (
        <>
          <table>
            <caption>Dispersión de {metric}</caption>
            <tbody>
              <tr><th scope="row">Mediana</th><td>{fmt(m.overall.median)}</td>
                  <th scope="row">Media</th><td>{fmt(m.overall.mean)}</td></tr>
              <tr><th scope="row">Desvío</th><td>{fmt(m.overall.stdev)}</td>
                  <th scope="row">CV</th><td>{fmt(m.overall.cv)}</td></tr>
              <tr><th scope="row">Q1 / Q3</th><td>{fmt(m.overall.q1)} / {fmt(m.overall.q3)}</td>
                  <th scope="row">IQR</th><td>{fmt(m.overall.iqr)}</td></tr>
              <tr><th scope="row">MAD</th><td>{fmt(m.overall.mad)}</td>
                  <th scope="row">Mín / Máx</th>
                  <td>{fmt(m.overall.minimum)} / {fmt(m.overall.maximum)}</td></tr>
              <tr><th scope="row">Total</th><td>{fmt(m.overall.total)}</td>
                  <th scope="row">Sin dato</th><td>{m.overall.n_missing}</td></tr>
            </tbody>
          </table>
          <table>
            <caption>Histograma</caption>
            <thead>
              <tr><th scope="col">Desde</th><th scope="col">Hasta</th>
                  <th scope="col">Corridas</th><th scope="col">Peso</th></tr>
            </thead>
            <tbody>
              {bins.map((b, i) => (
                <tr key={`${b.lo}-${b.hi}-${i}`}>
                  <td>{fmt(b.lo)}</td><td>{fmt(b.hi)}</td><td>{b.count}</td>
                  <td>
                    <meter min={0} max={100} value={barPercent(b.count, maxCount)}>
                      {barPercent(b.count, maxCount)}%
                    </meter>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>Valores atípicos (Tukey): {outlierSummary(m.outliers_tukey)}</p>
          <p>Valores atípicos (MAD): {outlierSummary(m.outliers_mad)}</p>
        </>
      )}
    </Card>
  );
}

/** Plan 242 F7 — tabla por dimensión (una sola, la que elija el operador). */
function DimensionTable({ block, dimension }: { block: StatsBlock; dimension: string }) {
  const grupos = block.by_dimension?.[dimension] ?? {};
  const claves = Object.keys(grupos);
  if (claves.length === 0) return <p>Sin datos por {dimension}.</p>;
  return (
    <table>
      <caption>Costo por {dimension}</caption>
      <thead>
        <tr>
          <th scope="col">{dimension}</th><th scope="col">Corridas</th>
          <th scope="col">Total</th><th scope="col">Mediana</th>
          <th scope="col">p90</th><th scope="col">p99</th>
        </tr>
      </thead>
      <tbody>
        {claves.map((k) => (
          <tr key={k}>
            <td>{k}</td><td>{grupos[k].n}</td><td>{fmt(grupos[k].total)}</td>
            <td>{fmt(grupos[k].median)}</td><td>{fmt(grupos[k].p90)}</td>
            <td>{fmt(grupos[k].p99)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Plan 242 F7 — sub-tab "Scoring". Las razones se muestran TAL CUAL vienen
 *  del backend: la explicación es del motor, la UI no la reinterpreta. */
function ScoreRows({ executions, tickets }: {
  executions: ExecutionScore[]; tickets: TicketScore[];
}) {
  return (
    <>
      <table>
        <caption>Ejecuciones — las peores primero</caption>
        <thead>
          <tr>
            <th scope="col">Nota</th><th scope="col">Puntaje</th><th scope="col">Corrida</th>
            <th scope="col">Agente</th><th scope="col">Costo USD</th>
            <th scope="col">Confianza</th><th scope="col">Por qué</th>
          </tr>
        </thead>
        <tbody>
          {executions.map((e) => (
            <tr key={e.execution_id}>
              <td><StatusChip tone={gradeTone(e.grade)} title={`Cohorte ${e.cohort_key} (${e.cohort_n} runs)`}>{e.grade}</StatusChip></td>
              <td>{fmt(e.score)}</td>
              <td>#{e.execution_id}</td>
              <td>{e.agent_type ?? "—"}</td>
              <td>{e.cost_kind === "nominal" ? "nominal (suscripción plana)" : fmt(e.cost_usd)}</td>
              <td>{e.confidence}</td>
              <td>
                <details>
                  <summary>{e.reasons.length} razón(es)</summary>
                  <ul>{e.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
                </details>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <table>
        <caption>Incidencias — las peores primero</caption>
        <thead>
          <tr>
            <th scope="col">Nota</th><th scope="col">Puntaje</th><th scope="col">Ticket</th>
            <th scope="col">Corridas</th><th scope="col">Facturable USD</th>
            <th scope="col">Penalidad</th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((t) => (
            <tr key={t.ticket_id}>
              <td><StatusChip tone={gradeTone(t.grade)}>{t.grade}</StatusChip></td>
              <td>{fmt(t.score)}</td>
              <td>{t.ado_id ?? t.ticket_id}</td>
              <td>{t.runs}</td>
              <td>{fmt(t.billable_usd)}</td>
              <td>{t.rework_penalty > 0 ? `-${fmt(t.rework_penalty)}` : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

/** Plan 142 F6 — Centro de Costos: KPIs+Codeburn read-only sobre telemetría ya
 * persistida (§1). Dueño del estado de filtros; react-query (ya instalado)
 * llama a los 3 endpoints gated por STACKY_COST_CENTER_ENABLED. Con
 * `{enabled:false}` muestra el estado "desactivado, activala en Arnés"
 * (nunca crashea ni queda en blanco).
 *
 * Plan 242 F7 — se le agregan los sub-tabs Estadísticas y Scoring. "Resumen"
 * es el default y renderiza EXACTAMENTE lo de antes, así que `/costcenter`
 * sigue siendo la misma pantalla. El sub-tab se lee del 2do segmento del path
 * y se escribe con `replaceState` (mismo patrón que SettingsPage): App.tsx no
 * pasa `subtab` a esta página y no está en el alcance de esta corrida. */
export default function CostCenterPage() {
  const [filters, setFilters] = useState<CostFiltersParams>({ days: 30 });
  const [bucket, setBucket] = useState<BurnBucket>("day");
  const [dimension, setDimension] = useState<BreakdownDimension>("runtime");
  // Plan 199 F6 — agrupación de la serie apilada (runtime | model | agent_type).
  const [stackGroupBy, setStackGroupBy] = useState("runtime");

  // ── Plan 242 F7 — sub-tab con deep-link ──────────────────────────────────
  // Se siembra del path real y se escribe con replaceState. Un sub-tab
  // desconocido cae en "resumen": nunca una pantalla en blanco.
  const [subTab, setSubTab] = useState<CostSubTab>(() =>
    typeof window === "undefined"
      ? "resumen"
      : costSubTabFrom(parseRoute(window.location.pathname, window.location.search).subtab),
  );
  // Plan 242 — métrica y dimensión que mira el operador en Estadísticas.
  const [statMetric, setStatMetric] = useState<string>("cost_usd");
  const [statDimension, setStatDimension] = useState<string>("runtime");

  const irASubTab = useCallback((id: string) => {
    const destino = costSubTabFrom(id);
    setSubTab(destino);
    if (typeof window === "undefined") return;
    const actual = parseRoute(window.location.pathname, window.location.search);
    const url = serializeRoute({
      ...actual, tab: "costcenter", subtab: costSubTabToSegment(destino),
    });
    window.history.replaceState(null, "", url);
  }, []);

  // Botón atrás/adelante del navegador: re-sincroniza el sub-tab con la URL.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onPop = () => setSubTab(
      costSubTabFrom(parseRoute(window.location.pathname, window.location.search).subtab),
    );
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const statsQ = useQuery({
    queryKey: ["cost-center", "stats", filters, statMetric, statDimension],
    queryFn: () => CostCenter.stats({ ...filters, metric: statMetric, dimension: statDimension }),
    enabled: subTab === "estadisticas",   // no se pide hasta que el operador entra
  });
  const scoresQ = useQuery({
    queryKey: ["cost-center", "scores", filters],
    queryFn: () => CostCenter.scores(filters),
    enabled: subTab === "scoring",
  });

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

  // ── Plan 242 F7 — sub-tabs. "resumen" renderiza EXACTAMENTE lo de antes. ──
  const statsData = statsQ.data && statsQ.data.enabled ? statsQ.data : null;
  const statsApagado = statsQ.data ? statsQ.data.enabled === false : false;
  const scoresData = scoresQ.data && scoresQ.data.enabled ? scoresQ.data : null;
  const scoresApagado = scoresQ.data ? scoresQ.data.enabled === false : false;

  const subTabs = (
    <Tabs
      aria-label="Vistas del Centro de Costos"
      activeId={subTab}
      onChange={irASubTab}
      items={[
        { id: "resumen", label: "Resumen" },
        { id: "estadisticas", label: "Estadísticas" },
        { id: "scoring", label: "Scoring" },
      ]}
    />
  );

  if (subTab === "estadisticas") {
    return (
      <div className={styles.page}>
        <h1 className={styles.title}>Centro de Costos</h1>
        {subTabs}
        <CostFiltersBar value={filters} onChange={setFilters} />
        {statsApagado ? (
          <EmptyState
            variant="generic"
            title="Estadística profunda desactivada"
            message="Activá STACKY_COST_STATS_ENABLED desde Configuración → Arnés (sub-tab Observabilidad) para ver percentiles, dispersión y valores atípicos."
          />
        ) : statsQ.isLoading ? (
          <Skeleton lines={3} height={80} />
        ) : statsQ.isError ? (
          <LoadErrorState what="la estadística de costos" error={statsQ.error} onRetry={() => statsQ.refetch()} />
        ) : statsData ? (
          <>
            <Card padding="sm">
              <SectionHeader
                title="Qué mirar"
                subtitle="Un promedio sobre una distribución de cola larga miente: estos números distinguen 400 corridas parejas de 3 que se comieron todo."
                actions={
                  <>
                    <Select
                      aria-label="Métrica"
                      value={statMetric}
                      onChange={(e) => setStatMetric(e.target.value)}
                    >
                      {COST_STAT_METRICS.map((m) => <option key={m} value={m}>{m}</option>)}
                    </Select>
                    <Select
                      aria-label="Dimensión"
                      value={statDimension}
                      onChange={(e) => setStatDimension(e.target.value)}
                    >
                      {COST_STAT_DIMENSIONS.map((d) => <option key={d} value={d}>{d}</option>)}
                    </Select>
                  </>
                }
              />
              {statsData.capped ? <p>Ventana acotada: se alcanzó el tope de filas.</p> : null}
            </Card>
            {/* G7 — facturable y nominal SIEMPRE separados y rotulados. */}
            <StatsPanel block={statsData.billable_only} metric={statMetric}
                        titulo="Facturable (Codex + Claude)" />
            <StatsPanel block={statsData.nominal_only} metric={statMetric}
                        titulo="Nominal — suscripción plana (Copilot), no facturable" />
            <Card>
              <SectionHeader title={`Facturable por ${statDimension}`} />
              <DimensionTable block={statsData.billable_only} dimension={statDimension} />
            </Card>
            <Card>
              <SectionHeader
                title="Reuso de contexto y repetición"
                subtitle="El rework es un costo real: cada reintento del mismo agente sobre la misma incidencia se paga."
              />
              <table>
                <tbody>
                  <tr><th scope="row">Leído de cache</th>
                      <td>{fmt(statsData.billable_only.cache_efficiency.cache_read_total)}</td></tr>
                  <tr><th scope="row">Escrito a cache</th>
                      <td>{fmt(statsData.billable_only.cache_efficiency.cache_creation_total)}</td></tr>
                  <tr><th scope="row">Proporción de reuso</th>
                      <td>{fmt(statsData.billable_only.cache_efficiency.cache_read_ratio)}</td></tr>
                  <tr><th scope="row">Ahorro estimado USD</th>
                      <td>{fmt(statsData.billable_only.cache_efficiency.cache_savings_usd_total)}</td></tr>
                  <tr><th scope="row">Corridas repetidas</th>
                      <td>{String(statsData.billable_only.rework.rework_runs ?? "—")}</td></tr>
                  <tr><th scope="row">Costo del rework USD</th>
                      <td>{String(statsData.billable_only.rework.rework_cost_usd ?? "—")}</td></tr>
                </tbody>
              </table>
            </Card>
          </>
        ) : null}
      </div>
    );
  }

  if (subTab === "scoring") {
    return (
      <div className={styles.page}>
        <h1 className={styles.title}>Centro de Costos</h1>
        {subTabs}
        <CostFiltersBar value={filters} onChange={setFilters} />
        {scoresApagado ? (
          <EmptyState
            variant="generic"
            title="Nota de eficiencia desactivada"
            message="Activá STACKY_COST_SCORING_ENABLED desde Configuración → Arnés (sub-tab Observabilidad) para ver el puntaje y las razones por corrida."
          />
        ) : scoresQ.isLoading ? (
          <Skeleton lines={3} height={80} />
        ) : scoresQ.isError ? (
          <LoadErrorState what="el scoring de costos" error={scoresQ.error} onRetry={() => scoresQ.refetch()} />
        ) : scoresData ? (
          <>
            <Card padding="sm">
              <SectionHeader
                title="Qué tan bien se gastó"
                subtitle={`${scoresData.runs_scored} de ${scoresData.runs_total} corrida(s) con datos suficientes para puntuar · ${Object.keys(scoresData.cohorts).length} cohorte(s)`}
                actions={
                  <>
                    {(["A", "B", "C", "D", "E", "N/D"] as Grade[]).map((g) => (
                      <StatusChip key={g} tone={gradeTone(g)} title={`${scoresData.grade_distribution[g] ?? 0} corrida(s)`}>
                        {g}: {scoresData.grade_distribution[g] ?? 0}
                      </StatusChip>
                    ))}
                  </>
                }
              />
            </Card>
            <Card>
              <ScoreRows executions={scoresData.executions} tickets={scoresData.tickets} />
            </Card>
          </>
        ) : null}
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Centro de Costos</h1>
      {subTabs}
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
