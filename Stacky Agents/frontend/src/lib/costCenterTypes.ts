/**
 * Plan 142 F4 — Tipos TS que espejan EXACTAMENTE los contratos JSON de los
 * endpoints backend `/api/metrics/cost-summary|cost-burn|cost-breakdown|
 * cost-reconciliation-audit` (services/cost_analytics.py + api/metrics.py).
 * Sólo tipos: sin lógica (la lógica pura vive en costCenter.logic.ts, F5).
 */

export type CostKind = "reported" | "estimated" | "nominal" | "unknown";

/** Respuesta cuando la flag STACKY_COST_CENTER_ENABLED está OFF (los 4 endpoints). */
export interface CostCenterDisabled {
  enabled: false;
}

export interface TopRun {
  execution_id: number;
  ticket_id: number | null;
  agent_type: string | null;
  runtime: string | null;
  model: string | null;
  cost_usd: number | null;
  cost_kind: CostKind;
  started_at: string | null;
}

export interface FiltersEcho {
  date_from: string;
  date_to: string;
  days_effective: number;
  runtime: string | null;
  model: string | null;
  agent_type: string | null;
  ticket_id: number | null;
  project: string | null;
  statuses: string[];
  cost_kind: string | null;
}

export interface ExternalReconciliation {
  external_total_usd: number;
  stacky_billable_usd: number;
  delta_usd: number;
}

export interface CostSummary {
  ok: true;
  enabled: true;
  generated_at: string;
  filters_echo: FiltersEcho;
  capped: boolean;
  runs_total: number;
  runs_with_cost: number;
  runs_without_cost: number;
  reported_usd: number;
  estimated_usd: number;
  nominal_usd: number;
  billable_usd: number;
  pct_estimated: number;
  tokens_in_total: number;
  tokens_out_total: number;
  cache_read_total: number;
  cache_savings_usd_total: number;
  avg_cost_per_run_usd: number;
  cost_per_completed_task_usd: number;
  tokens_out_in_ratio: number;
  top_runs: TopRun[];
  /** F7 (opcional, flag propia) — sólo presente si el operador configuró un export externo. */
  external_reconciliation?: ExternalReconciliation;
}

export type CostSummaryResponse = CostCenterDisabled | CostSummary;

export interface BurnPoint {
  bucket: string;
  reported_usd: number;
  estimated_usd: number;
  nominal_usd: number;
  billable_usd: number;
  cumulative_billable_usd: number;
  tokens_in: number;
  tokens_out: number;
  runs: number;
}

export interface PeriodComparison {
  current_billable_usd: number;
  previous_billable_usd: number;
  delta_pct: number;
}

export interface CostBurn {
  ok: true;
  enabled: true;
  generated_at: string;
  bucket: "hour" | "day" | "week";
  series: BurnPoint[];
  period_comparison: PeriodComparison;
}

export type CostBurnResponse = CostCenterDisabled | CostBurn;

export interface BreakdownGroup {
  key: string;
  reported_usd: number;
  estimated_usd: number;
  nominal_usd: number;
  billable_usd: number;
  tokens_in: number;
  tokens_out: number;
  runs: number;
}

export type BreakdownDimension = "runtime" | "model" | "agent_type" | "ticket" | "project" | "day";

export interface CostBreakdown {
  ok: true;
  enabled: true;
  generated_at: string;
  dimension: BreakdownDimension;
  groups: BreakdownGroup[];
}

export type CostBreakdownResponse = CostCenterDisabled | CostBreakdown;

export interface CostReconciliationAudit {
  ok: true;
  enabled: true;
  generated_at: string;
  canonical_billable_usd: number;
  legacy_reported_usd: number;
  delta_usd: number;
  codex_invisible_usd: number;
  runs_audited: number;
}

export type CostReconciliationAuditResponse = CostCenterDisabled | CostReconciliationAudit;

/** Parámetros de filtro compartidos por los 3 (4) endpoints — mapean 1:1 a query params. */
export interface CostFiltersParams {
  from?: string;   // "YYYY-MM-DD"
  to?: string;     // "YYYY-MM-DD"
  days?: number;   // default 30, clamp 1..365 en el backend
  runtime?: string;
  model?: string;
  agent_type?: string;
  ticket_id?: number;
  project?: string;
  status?: string; // csv
  cost_kind?: CostKind;
  top_n?: number;  // sólo cost-summary
  /* Plan 199 F4 — aditivos. Coexisten con los singulares de arriba (OR entre varios). */
  runtimes?: string;   // csv
  models?: string;     // csv
  min_cost?: number;
  max_cost?: number;
  /** Elige la FUENTE de datos en la UI (F6). NO viaja a los endpoints del 142. */
  source?: CostSource;
}

/** Plan 199 F6 — de dónde sale la data que muestra el Centro de Costos. */
export type CostSource = "live" | "harvest" | "all";

/** Narrowing helper: `enabled` es un discriminante literal (true/false) en los 4
 * contratos de respuesta, así que un simple `if (resp?.enabled)` ya narrowea en
 * TS — este helper sólo documenta la intención en los call-sites de la página. */
export function isCostCenterEnabled<T extends { enabled: true }>(
  resp: T | CostCenterDisabled,
): resp is T {
  return resp.enabled === true;
}

// ── Plan 199 F5/F6 — respuestas de los tres gráficos nuevos ──────────────────

export interface CostBurnStacked {
  bucket: string;
  group_by: string;
  series: { bucket: string; groups: Record<string, number>; billable_usd: number }[];
  groups: string[];
}

export interface CostHeatmap {
  cells: { weekday: number; hour: number; billable_usd: number; runs: number }[];
  max_billable_usd: number;
}

export interface CostDistribution {
  bins: { lo: number; hi: number; count: number }[];
  total: number;
  min: number | null;
  max: number | null;
}

/* ─── Plan 199 F6 — cosecha histórica de telemetría desde disco ─────────────
 * Los 3 endpoints devuelven SIEMPRE 200 (incluso deshabilitados), así que se
 * consumen con `api.get`/`api.post`; el discriminante `enabled`/`flag_enabled`
 * narrowea en el call-site. */

/** `GET /api/metrics/telemetry-harvest/health` — siempre 200. */
export interface HarvestHealth {
  ok: true;
  flag_enabled: boolean;
}

/** Cuántas filas de la BD rellenaría (o rellenó) el backfill. */
export interface HarvestBackfill {
  scanned: number;
  matched: number;
  backfilled: number;
  skipped_billable: number;
  dry_run: boolean;
}

/** Cuántas corridas huérfanas se anexarían (o anexaron) a la bitácora. */
export interface HarvestLedger {
  appended: number;
  skipped_dup: number;
  skipped_unattributed: number;
  dry_run: boolean;
}

export interface HarvestScanOk {
  ok: true;
  enabled: true;
  /** false = DRY-RUN (el default). true sólo si se pidió `apply=1`. */
  applied: boolean;
  generated_at: string;
  discovered: number;
  backfill: HarvestBackfill;
  ledger: HarvestLedger;
}

/** Un artefacto corrupto no devuelve 500: devuelve 200 con `ok:false`. */
export interface HarvestScanError {
  ok: false;
  enabled: true;
  error: string;
}

export type HarvestScanResponse = CostCenterDisabled | HarvestScanError | HarvestScanOk;

/** `GET /telemetry-harvest/summary` — mismos agregados del 142 sobre la bitácora. */
export interface HarvestSummary extends Omit<CostSummary, "filters_echo" | "capped"> {
  attributed_only: boolean;
  /** `ca.breakdown` devuelve `{dimension, groups}`, NO una lista pelada. */
  breakdown: Pick<CostBreakdown, "dimension" | "groups">;
}

export type HarvestSummaryResponse = CostCenterDisabled | HarvestSummary;
