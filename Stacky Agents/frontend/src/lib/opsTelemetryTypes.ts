/**
 * Plan 171 F5 — Tipos espejo de los contratos congelados de telemetría operativa.
 *
 * Read-only: el backend calcula, el frontend solo muestra. Todo campo que el
 * backend puede no tener llega como `null` explícito, nunca como 0 inventado.
 */

export interface OpsTotals {
  runs: number;
  terminal: number;
  completed: number;
  needs_review: number;
  error: number;
  running: number;
  error_rate: number | null;
  p50_seconds: number | null;
  p90_seconds: number | null;
  billable_usd: number;
  runs_sin_modelo: number;
}

export interface OpsGroup {
  agent_type: string;
  runtime: string;
  runs: number;
  terminal: number;
  completed: number;
  error: number;
  error_rate: number | null;
  p50_seconds: number | null;
  p90_seconds: number | null;
  billable_usd: number;
  models: Record<string, number>;
}

export interface OpsBreach {
  rule_id: string;
  severity: "warn" | "critical";
  agent_type: string | null;
  runtime: string | null;
  message: string;
  observed: number;
  reference: number | null;
  threshold: number;
}

export interface OpsBaseline {
  enabled: boolean;
  current_days: number;
  baseline_days: number;
  regressions: OpsBreach[];
}

export interface OpsStalls {
  count: number;
  execution_ids: number[];
}

export interface OpsThresholds {
  schema_version: number;
  error_rate_warn: number;
  error_rate_delta: number;
  min_runs: number;
  baseline_min_runs: number;
  p90_regression_factor: number;
  p90_min_seconds: number;
  /** Siempre llega resuelto a un entero (el backend sustituye el default del sistema). */
  stall_minutes: number;
  daily_budget_usd: number | null;
}

export interface OpsSummaryResponse {
  enabled: boolean;
  generated_at?: string;
  window_days?: number;
  totals?: OpsTotals;
  groups?: OpsGroup[];
  baseline?: OpsBaseline;
  breaches?: OpsBreach[];
  stalls?: OpsStalls;
  thresholds?: OpsThresholds;
}

export interface OpsTrendPoint {
  date: string;
  runs: number;
  errors: number;
  billable_usd: number;
  p50_seconds: number | null;
}

export interface OpsTrendsResponse {
  enabled: boolean;
  days?: number;
  series?: OpsTrendPoint[];
}

export interface OpsThresholdsResponse {
  enabled: boolean;
  thresholds?: OpsThresholds;
}

export interface RunTracePhase {
  name: string;
  ts: string;
}

export interface RunTraceCost {
  cost_usd: number | null;
  cost_kind: string;
  tokens_in: number | null;
  tokens_out: number | null;
  cache_read_tokens: number | null;
  cache_savings_usd: number | null;
}

export interface RunTraceTicket {
  ticket_id: number | null;
  ado_id: number | null;
  title: string | null;
}

export interface RunTraceIncident {
  id: string | null;
  title: string | null;
  status: string | null;
}

export interface RunTrace {
  execution_id: number;
  agent_type: string | null;
  status: string;
  runtime: string | null;
  model: string | null;
  ticket: RunTraceTicket | null;
  phases: RunTracePhase[];
  duration_seconds: number | null;
  cost: RunTraceCost;
  telemetry_source: string;
  session_id: string | null;
  num_turns: number | null;
  agent_name: string | null;
  prompt_sha: string | null;
  stalled: boolean;
  incident: RunTraceIncident | null;
  sin_dato: string[];
}

export interface RunTraceResponse {
  enabled: boolean;
  trace?: RunTrace;
}
