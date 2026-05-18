/**
 * PM Intelligence Suite — cliente API (Fase 1 MVP, sin IA).
 *
 * Contratos derivados de docs/11_PM_INTELLIGENCE_SUITE.md §2.
 * Todos los endpoints están bajo /api/pm/* y requieren proyecto con tracker_type=azure_devops.
 */
import { api } from "./client";

// ── tipos compartidos ─────────────────────────────────────────────────────────

export interface PmDataQualityWarning {
  warning_type: string;
  count: number;
  percentage: number;
  impact: string;
}

export interface PmSprintKpis {
  sprint_id: string;
  sprint_name: string;
  total_items: number;
  done_items: number;
  active_items: number;
  blocked_items: number;
  new_items: number;
  committed_story_points: number;
  completed_story_points: number;
  completion_rate_pct: number;
  bug_count: number;
  bug_rate_pct: number;
  avg_aging_days: number | null;
  avg_cycle_time_days: number | null;
  items_without_estimation: number;
  items_without_owner: number;
  days_remaining: number | null;
  data_quality_warnings: PmDataQualityWarning[];
}

export interface PmIteration {
  id: string | null;
  name: string | null;
  path: string;
  start_date: string | null;
  end_date: string | null;
  timeframe: string | null;
}

export interface PmRiskSnapshot {
  risk_id: string;
  category: string;
  severity: string;
  rule: string | null;
  description: string;
  affected_items: number[];
  evidence?: Record<string, unknown>;
}

export interface PmSnapshotPayload {
  iteration: PmIteration;
  kpis: PmSprintKpis;
  risks: PmRiskSnapshot[];
  items_count: number;
  revisions_count: number;
}

export interface PmSprintSnapshotRow {
  id: number;
  project: string;
  sprint_id: string;
  sprint_name: string;
  start_date: string | null;
  end_date: string | null;
  snapshot: PmSnapshotPayload;
  source: string;
  captured_at: string;
}

export interface PmRiskItem {
  risk_id: string;
  project: string;
  sprint_id: string | null;
  category: string;
  severity: string;
  description: string | null;
  affected_items: number[];
  rule: string | null;
  detected_at: string;
  acknowledged: boolean;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  ai_enriched: boolean;
}

export interface PmComment {
  id: number;
  ado_id: number;
  project: string;
  author: string | null;
  comment_date: string | null;
  text_plain: string | null;
  ai_analyzed: boolean;
  sentiment_label: string | null;
  sentiment_score: number | null;
  indexed_at: string;
}

export interface PmSyncResult {
  project: string;
  snapshot_id: number;
  iteration_path: string;
  items_synced: number;
  revisions_synced: number;
  risks_detected: number;
  risks_inserted: number;
  risks_updated: number;
  duration_ms: number;
}

export interface PmIndexCommentsResult {
  project: string;
  requested_ado_ids: number;
  inserted: number;
  skipped_duplicates: number;
  total_fetched: number;
  errors: Array<{ ado_id: number; error: string }>;
  duration_ms: number;
}

// ── AI usage tracking (Fase 2) ───────────────────────────────────────────────

export interface PmAiUsageRow {
  id: number;
  timestamp: string;
  project: string;
  agent_kind: string;
  prompt_type: string;
  model: string;
  backend: string;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  latency_ms: number;
  success: boolean;
  error: string | null;
  fixture_id: string | null;
  advisory_only: boolean;
  correlation_id: string | null;
}

export interface PmAiUsageBreakdown {
  calls: number;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  success: number;
}

export interface PmAiUsageTotals {
  calls: number;
  success: number;
  success_rate_pct: number;
  tokens_in: number;
  tokens_out: number;
  tokens_total: number;
  cost_usd: number;
  latency_ms_avg: number;
}

export interface PmAiUsageReport {
  project: string | null;
  since_hours: number;
  window_start: string;
  totals: PmAiUsageTotals;
  by_model: Record<string, PmAiUsageBreakdown>;
  by_agent: Record<string, PmAiUsageBreakdown>;
  recent_calls: PmAiUsageRow[];
  advisory_only: boolean;
}

// ── Evals + Sentiment + Recommendations (Fase 2) ─────────────────────────────

export interface PmEvalFixtureResult {
  fixture_id: string;
  type: string;
  description: string;
  success: boolean;
  passed: boolean;
  failures: string[];
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  latency_ms: number;
  model: string;
  usage_id: number | null;
}

export interface PmEvalReport {
  component: string;
  total: number;
  passed: number;
  failed: number;
  pass_rate: number;
  gate_passed: boolean;
  gate_details: Record<string, unknown>;
  tokens_in_total: number;
  tokens_out_total: number;
  cost_usd_total: number;
  fixtures: PmEvalFixtureResult[];
  duration_ms: number;
}

export interface PmEvalComponentInfo {
  component: string;
  fixtures_count: number;
  fixture_ids: string[];
}

export interface PmSentimentResult {
  project: string;
  requested: number;
  analyzed: number;
  skipped_already_analyzed: number;
  failures: number;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  gate_passed: boolean;
  advisory_only: boolean;
  duration_ms?: number;
}

export interface PmRecommendation {
  rec_id: string;
  project: string;
  sprint_id: string | null;
  priority: "P0" | "P1" | "P2";
  category: string;
  action: string;
  rationale: string | null;
  supporting_data: Record<string, unknown>;
  confidence: number;
  advisory_only: boolean;
  publish_recommended: boolean;
  human_approval_required: boolean;
  acknowledged: boolean;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  model: string;
  usage_id: number | null;
  generated_at: string;
}

export interface PmRecommendationRunResult {
  project: string;
  sprint_id: string | null;
  gate_passed: boolean;
  generated: number;
  rejected: number;
  rejected_reasons: string[];
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  model: string;
  advisory_only: boolean;
  duration_ms?: number;
}

interface OkResponse<T> {
  ok: true;
  result: T;
}

// ── helpers ────────────────────────────────────────────────────────────────────

function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  }
  return parts.length ? `?${parts.join("&")}` : "";
}

// ── endpoints ──────────────────────────────────────────────────────────────────

export const PmApi = {
  syncAdo: async (input: { project?: string; iteration_path?: string; team?: string }) => {
    const res = await api.post<OkResponse<PmSyncResult>>("/api/pm/sync-ado", input);
    return res.result;
  },

  sprintCurrent: async (project?: string) => {
    const res = await api.get<OkResponse<{
      project: string;
      snapshot: PmSprintSnapshotRow;
      generated_at: string;
      source: string;
      human_review_required: boolean;
      ai_enriched: boolean;
    }>>(`/api/pm/sprint/current${qs({ project })}`);
    return res.result;
  },

  sprintHistory: async (project?: string, lastN: number = 10) => {
    const res = await api.get<OkResponse<{
      project: string;
      count: number;
      snapshots: PmSprintSnapshotRow[];
    }>>(`/api/pm/sprint/history${qs({ project, last_n: lastN })}`);
    return res.result;
  },

  listRisks: async (input: {
    project?: string;
    sprint_id?: string;
    severity?: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
    acknowledged?: boolean;
  } = {}) => {
    const res = await api.get<OkResponse<{
      project: string;
      count: number;
      risks: PmRiskItem[];
      ai_enriched: boolean;
      generated_at: string;
    }>>(`/api/pm/risks${qs(input)}`);
    return res.result;
  },

  acknowledgeRisk: async (riskId: string, acknowledgedBy?: string) => {
    const res = await api.post<OkResponse<PmRiskItem & { already_acknowledged?: boolean }>>(
      `/api/pm/risks/${encodeURIComponent(riskId)}/acknowledge`,
      acknowledgedBy ? { acknowledged_by: acknowledgedBy } : {},
    );
    return res.result;
  },

  listComments: async (adoId: number, limit: number = 50) => {
    const res = await api.get<OkResponse<{
      ado_id: number;
      count: number;
      comments: PmComment[];
      pii_masked: boolean;
      ai_analyzed: boolean;
    }>>(`/api/pm/comments${qs({ ado_id: adoId, limit })}`);
    return res.result;
  },

  indexComments: async (input: { project?: string; ado_ids: number[]; top_per_item?: number }) => {
    const res = await api.post<OkResponse<PmIndexCommentsResult>>(
      "/api/pm/comments/index",
      input,
    );
    return res.result;
  },

  aiUsage: async (input: {
    project?: string;
    since_hours?: number;
    agent_kind?: "sentiment" | "recommendation";
  } = {}) => {
    const res = await api.get<OkResponse<PmAiUsageReport>>(
      `/api/pm/ai/usage${qs(input)}`,
    );
    return res.result;
  },

  // ── Evals ─────────────────────────────────────────────────────────────────
  evalComponents: async () => {
    const res = await api.get<OkResponse<{ components: PmEvalComponentInfo[] }>>(
      "/api/pm/evals/components",
    );
    return res.result.components;
  },

  runEvals: async (input: {
    component: "comment_sentiment" | "recommendation_engine";
    model?: string;
  }) => {
    const res = await api.post<OkResponse<PmEvalReport>>(
      "/api/pm/evals/run",
      input,
    );
    return res.result;
  },

  // ── Sentiment ─────────────────────────────────────────────────────────────
  analyzeSentiment: async (input: {
    project?: string;
    sprint_name?: string;
    comment_ids: number[];
    model?: string;
    force_unsafe?: boolean;
  }) => {
    const res = await api.post<OkResponse<PmSentimentResult>>(
      "/api/pm/sentiment/analyze",
      input,
    );
    return res.result;
  },

  // ── Recommendations ───────────────────────────────────────────────────────
  generateRecommendations: async (input: {
    project?: string;
    model?: string;
    force_unsafe?: boolean;
    history?: Array<{ name: string; velocity: number; completion_rate_pct: number }>;
  } = {}) => {
    const res = await api.post<OkResponse<PmRecommendationRunResult>>(
      "/api/pm/recommendations/generate",
      input,
    );
    return res.result;
  },

  listRecommendations: async (input: {
    project?: string;
    sprint_id?: string;
    priority?: "P0" | "P1" | "P2";
    acknowledged?: boolean;
  } = {}) => {
    const res = await api.get<OkResponse<{
      project: string;
      count: number;
      recommendations: PmRecommendation[];
      advisory_only: boolean;
      publishable: boolean;
    }>>(`/api/pm/recommendations${qs(input)}`);
    return res.result;
  },

  acknowledgeRecommendation: async (recId: string, acknowledgedBy?: string) => {
    const res = await api.post<OkResponse<PmRecommendation>>(
      `/api/pm/recommendations/${encodeURIComponent(recId)}/acknowledge`,
      acknowledgedBy ? { acknowledged_by: acknowledgedBy } : {},
    );
    return res.result;
  },
};
