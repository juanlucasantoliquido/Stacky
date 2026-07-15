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
}

/** Narrowing helper: `enabled` es un discriminante literal (true/false) en los 4
 * contratos de respuesta, así que un simple `if (resp?.enabled)` ya narrowea en
 * TS — este helper sólo documenta la intención en los call-sites de la página. */
export function isCostCenterEnabled<T extends { enabled: true }>(
  resp: T | CostCenterDisabled,
): resp is T {
  return resp.enabled === true;
}
