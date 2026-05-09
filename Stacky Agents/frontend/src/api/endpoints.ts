import { api, apiBase } from "./client";
import type {
  ActiveProjectResponse,
  AgentDefinition,
  AgentExecution,
  AgentType,
  AgentWorkflowConfig,
  ContextBlock,
  InitProjectPayload,
  PackDefinition,
  PackRun,
  PipelineBatchResponse,
  PipelineInferenceResult,
  Project,
  ProjectsResponse,
  Ticket,
  TicketFingerprint,
  TicketHierarchy,
  TicketStackyStatus,
  VsCodeAgent,
} from "../types";

export interface TicketSyncResult {
  ok: boolean;
  project?: string;
  fetched?: number;
  created?: number;
  updated?: number;
  removed?: number;
  synced_at?: string;
  error?: string;
  message?: string;
}

export const Tickets = {
  list: () => api.get<Ticket[]>("/api/tickets"),
  byId: (id: number) => api.get<Ticket & { executions: AgentExecution[] }>(`/api/tickets/${id}`),
  hierarchy: () => api.get<TicketHierarchy>("/api/tickets/hierarchy"),
  fingerprint: (id: number) => api.get<TicketFingerprint>(`/api/tickets/${id}/fingerprint`),  // N3
  glossary: (id: number) => api.get<ContextBlock | null>(`/api/tickets/${id}/glossary`),  // FA-09
  comments: (id: number) => api.get<{ comments: { author: string; date: string; text: string }[] }>(`/api/tickets/${id}/comments`),
  adoPipelineStatus: (id: number, forceRefresh = false) =>
    api.get<PipelineInferenceResult>(
      `/api/tickets/${id}/ado-pipeline-status${forceRefresh ? "?force_refresh=true" : ""}`
    ),
  adoPipelineBatch: (ticketIds: number[], forceRefresh = false) =>
    api.post<PipelineBatchResponse>("/api/tickets/ado-pipeline-batch", {
      ticket_ids: ticketIds,
      force_refresh: forceRefresh,
    }),
  invalidatePipelineCache: (id: number) =>
    api.delete<{ ok: boolean }>(`/api/tickets/${id}/ado-pipeline-cache`),
  sync: () => api.post<TicketSyncResult>("/api/tickets/sync"),
  syncStatus: () => api.get<{ last_synced_at: string | null }>("/api/tickets/sync/status"),
  /** Devuelve el stacky_status actual + historial de transiciones del ticket */
  stackyStatus: (id: number, limit = 20) =>
    api.get<{
      ticket_id: number;
      current_status: TicketStackyStatus;
      history: {
        id: number;
        old_status: string | null;
        new_status: string;
        changed_by: string;
        changed_at: string;
        execution_id: number | null;
        agent_type: string | null;
        reason: string | null;
      }[];
    }>(`/api/tickets/${id}/stacky-status?limit=${limit}`),
  /** Actualiza manualmente el stacky_status de un ticket (reset operacional) */
  setStackyStatus: (id: number, status: TicketStackyStatus, reason?: string) =>
    api.patch<{ ticket_id: number; current_status: TicketStackyStatus }>(
      `/api/tickets/${id}/stacky-status`,
      { status, reason }
    ),
};

export interface AgentHistoryEntry {
  ticket_id: number;
  ado_id: number;
  title: string;
  project: string | null;
  ado_state: string | null;
  ado_url: string | null;
  last_execution_id: number;
  last_execution_status: string;
  last_execution_verdict: string | null;
  last_execution_started_at: string | null;
  last_execution_completed_at: string | null;
  last_execution_duration_ms: number | null;
  executions_count: number;
}

export interface AgentHistoryResponse {
  agent_filename: string;
  inferred_agent_type: string;
  mapping_note: string;
  tickets: AgentHistoryEntry[];
  total_executions: number;
}

export const Agents = {
  list: () => api.get<AgentDefinition[]>("/api/agents"),
  vsCodeAgents: () => api.get<VsCodeAgent[]>("/api/agents/vscode"),
  history: (filename: string, limit = 50) =>
    api.get<AgentHistoryResponse>(
      `/api/agents/vscode/${encodeURIComponent(filename)}/history?limit=${limit}`
    ),
  run: (payload: {
    agent_type: AgentType;
    ticket_id: number;
    context_blocks: ContextBlock[];
    chain_from?: number[];
  }) => api.post<{ execution_id: number; status: string }>("/api/agents/run", payload),
  cancel: (executionId: number) =>
    api.post<{ ok: true }>(`/api/agents/cancel/${executionId}`),
  estimate: (payload: {
    agent_type: AgentType;
    context_blocks: ContextBlock[];
    model?: string;
  }) =>
    api.post<{
      agent_type: AgentType;
      model: string;
      tokens_in: number;
      tokens_out: number;
      cost_usd_in: number;
      cost_usd_out: number;
      cost_usd_total: number;
      latency_ms: number;
      cache_hit: boolean;
    }>("/api/agents/estimate", payload),
  route: (payload: {
    agent_type: AgentType;
    context_blocks: ContextBlock[];
    model_override?: string | null;
    fingerprint_complexity?: string | null;
  }) =>
    api.post<{ model: string; reason: string; available: string[] }>(
      "/api/agents/route",
      payload
    ),
  systemPrompt: (agentType: AgentType) =>
    api.get<{ agent_type: AgentType; system_prompt: string }>(
      `/api/agents/${agentType}/system-prompt`
    ),
  models: (refresh = false) =>
    api.get<{
      backend: string;
      models: { id: string; name: string; vendor: string; family?: string; preview?: boolean }[];
      error: string | null;
      cached_at: number;
      ttl_sec: number;
      fallback_used: boolean;
    }>(`/api/agents/models${refresh ? "?refresh=true" : ""}`),
  schema: (agentType: AgentType) =>
    api.get<{
      agent_type: AgentType;
      rules: { name: string; description: string; weight: number; severity: string }[];
    }>(`/api/agents/${agentType}/schema`),
  nextSuggestion: (afterAgent: AgentType) =>
    api.get<
      { agent_type: AgentType; probability: number; sample_size: number; source: string }[]
    >(`/api/agents/next-suggestion?after_agent=${afterAgent}`),
  runWithOptions: (payload: {
    agent_type: AgentType;
    ticket_id: number;
    context_blocks: ContextBlock[];
    chain_from?: number[];
    model_override?: string | null;
    system_prompt_override?: string | null;
    use_few_shot?: boolean;
    use_anti_patterns?: boolean;
    fingerprint_complexity?: string | null;
  }) => api.post<{ execution_id: number; status: string }>("/api/agents/run", payload),
  openChat: (payload: {
    ticket_id: number;
    context_blocks: ContextBlock[];
    vscode_agent_filename?: string;
    model_override?: string | null;
  }) => api.post<{ ok: boolean }>("/api/agents/open-chat", payload),
};

export const AntiPatterns = {
  list: () =>
    api.get<
      { id: number; agent_type: string | null; project: string | null; pattern: string;
        reason: string; example: string | null; created_at: string; created_by: string;
        active: boolean }[]
    >("/api/anti-patterns"),
  create: (payload: {
    pattern: string;
    reason: string;
    agent_type?: string;
    project?: string;
    example?: string;
  }) => api.post<{ id: number }>("/api/anti-patterns", payload),
  deactivate: (id: number) => api.delete<{ ok: true }>(`/api/anti-patterns/${id}`),
};

export const Webhooks = {
  list: () =>
    api.get<
      { id: number; project: string | null; event: string; url: string; active: boolean;
        created_at: string; last_fired_at: string | null; last_status: string | null;
        last_error: string | null; fires: number }[]
    >("/api/webhooks"),
  create: (payload: { url: string; event?: string; project?: string; secret?: string }) =>
    api.post<{ id: number }>("/api/webhooks", payload),
  deactivate: (id: number) => api.delete<{ ok: true }>(`/api/webhooks/${id}`),
};

export const Executions = {
  list: (q: { ticket_id?: number; agent_type?: AgentType; status?: string }) => {
    const params = new URLSearchParams();
    if (q.ticket_id) params.set("ticket_id", String(q.ticket_id));
    if (q.agent_type) params.set("agent_type", q.agent_type);
    if (q.status) params.set("status", q.status);
    const qs = params.toString();
    return api.get<AgentExecution[]>(`/api/executions${qs ? `?${qs}` : ""}`);
  },
  byId: (id: number) => api.get<AgentExecution>(`/api/executions/${id}`),
  approve: (id: number) => api.post<AgentExecution>(`/api/executions/${id}/approve`),
  discard: (id: number) => api.post<AgentExecution>(`/api/executions/${id}/discard`),
  publish: (id: number, target: "comment" | "task" = "comment") =>
    api.post<{ ok: true; ado_url: string }>(`/api/executions/${id}/publish-to-ado`, { target }),
  diff: (a: number, b: number) =>
    api.get<{ left: AgentExecution; right: AgentExecution }>(
      `/api/executions/${a}/diff/${b}`
    ),
  streamUrl: (id: number) => `${apiBase}/api/executions/${id}/logs/stream`,
};

export interface SimilarHit {
  execution_id: number;
  ticket_ado_id: number;
  agent_type: AgentType;
  score: number;
  started_at: string | null;
  verdict: string | null;
  snippet: string;
}

export const Similarity = {
  // FA-45
  forTicket: (ticketId: number, agentType?: AgentType, limit = 5) => {
    const p = new URLSearchParams({ ticket_id: String(ticketId), limit: String(limit) });
    if (agentType) p.set("agent_type", agentType);
    return api.get<SimilarHit[]>(`/api/similarity/similar?${p.toString()}`);
  },
  // FA-14
  graveyard: (query: string, agentType?: AgentType, limit = 10) => {
    const p = new URLSearchParams({ q: query, limit: String(limit) });
    if (agentType) p.set("agent_type", agentType);
    return api.get<SimilarHit[]>(`/api/similarity/graveyard?${p.toString()}`);
  },
};

export const Packs = {
  list: () => api.get<PackDefinition[]>("/api/packs"),
  start: (payload: { pack_id: string; ticket_id: number; options?: Record<string, unknown> }) =>
    api.post<PackRun>("/api/packs/start", payload),
  byId: (id: number) => api.get<PackRun>(`/api/packs/runs/${id}`),
  advance: (id: number) => api.post<PackRun>(`/api/packs/runs/${id}/advance`),
  pause: (id: number) => api.post<PackRun>(`/api/packs/runs/${id}/pause`),
  resume: (id: number) => api.post<PackRun>(`/api/packs/runs/${id}/resume`),
  abandon: (id: number) => api.delete<{ ok: true }>(`/api/packs/runs/${id}`),
};

// QA UAT Pipeline
export interface QaUatRunStatus {
  ok: boolean;
  execution_id: string;
  status: "queued" | "running" | "completed" | "error";
  pipeline_result?: {
    ok: boolean;
    ticket_id: number;
    verdict?: "PASS" | "FAIL" | "BLOCKED" | "MIXED";
    elapsed_s?: number;
    stages?: Record<string, { ok: boolean; skipped?: boolean; [k: string]: unknown }>;
  };
  error?: string;
}

// QaUat namespace — see full definition below (Sprint 9+)

// FA-13
export const Decisions = {
  list: () =>
    api.get<
      { id: number; project: string | null; summary: string; reasoning: string;
        tags: string[]; supersedes_id: number | null; made_by: string | null;
        made_at: string; active: boolean }[]
    >("/api/decisions"),
  create: (payload: {
    summary: string;
    reasoning: string;
    tags?: string[];
    project?: string;
    supersedes_id?: number;
  }) => api.post<{ id: number }>("/api/decisions", payload),
  deactivate: (id: number) => api.delete<{ ok: true }>(`/api/decisions/${id}`),
};

// FA-05
export const Git = {
  fileContext: (path: string, n = 5) =>
    api.get<{
      path: string;
      last_commits: { sha: string; author: string; date: string; subject: string }[];
      last_modified_by: string | null;
      last_modified_at: string | null;
      error: string | null;
    }>(`/api/git/file-context?path=${encodeURIComponent(path)}&n=${n}`),
  contextBlock: (paths: string[], n = 3) =>
    api.post<ContextBlock | null>("/api/git/context-block", { paths, n }),
};

// FA-22
export const Translator = {
  translate: (payload: {
    target_lang: "en" | "es" | "pt";
    output?: string;
    execution_id?: number;
  }) =>
    api.post<{ target_lang: string; output: string; from_cache: boolean }>(
      "/api/translate",
      payload
    ),
};

// FA-23
export const Exporter = {
  export: (payload: {
    format: "md" | "html" | "slack" | "email";
    execution_id?: number;
    output?: string;
    agent_type?: string;
  }) =>
    api.post<{ format: string; content: string; filename: string; mime: string }>(
      "/api/export",
      payload
    ),
};

// FA-43
export const Coaching = {
  tips: (user?: string, days = 30) => {
    const p = new URLSearchParams({ days: String(days) });
    if (user) p.set("user", user);
    return api.get<{
      user: string;
      tips: { severity: "info" | "warning" | "high"; title: string; detail: string; metric: string }[];
    }>(`/api/coaching/tips?${p.toString()}`);
  },
};

// FA-46
export const BestPractices = {
  feed: (days = 7) =>
    api.get<{
      generated_at: string;
      window_days: number;
      sections: { title: string; items: any[] }[];
    }>(`/api/best-practices/feed?days=${days}`),
};

// FA-07
export const Release = {
  context: (project?: string) =>
    api.get<{ next_release: string | null; freeze_date: string | null;
      days_to_release: number | null; days_to_freeze: number | null; policy: string }>(
      `/api/release/context${project ? `?project=${project}` : ""}`
    ),
  block: (project?: string) =>
    api.get<ContextBlock | null>(`/api/release/block${project ? `?project=${project}` : ""}`),
};

// FA-16
export const Drift = {
  alerts: (unacknowledgedOnly = false) =>
    api.get<{ id: number; agent_type: string; metric: string; prev_value: number;
      curr_value: number; delta: number; severity: string; detected_at: string;
      acknowledged: boolean }[]>(
      `/api/drift/alerts${unacknowledgedOnly ? "?unacknowledged=true" : ""}`
    ),
  run: (windowDays = 7) =>
    api.post<{ alerts_generated: number; alerts: any[] }>("/api/drift/run", { window_days: windowDays }),
  ack: (id: number) => api.post<{ ok: true }>(`/api/drift/alerts/${id}/ack`),
};

// FA-25
export const ContextInbox = {
  bookmarkletUrl: (): string => `${apiBase}/api/context/bookmarklet.js`,
  send: (payload: { url: string; selection: string; title?: string }) =>
    api.post<{ block: ContextBlock; hint: string }>("/api/context/inbox", payload),
};

// FA-15
export const Glossary = {
  entries: (project?: string) =>
    api.get<{ id: number; term: string; definition: string; active: boolean }[]>(
      `/api/glossary/entries${project ? `?project=${project}` : ""}`
    ),
  candidates: (status = "pending") =>
    api.get<{ id: number; term: string; occurrences: number; context_sample: string; status: string }[]>(
      `/api/glossary/candidates?status=${status}`
    ),
  scan: (project?: string, days = 30) =>
    api.post<{ new_candidates: number }>("/api/glossary/scan", { project, days }),
  promote: (id: number, definition: string) =>
    api.post<{ entry_id: number }>(`/api/glossary/candidates/${id}/promote`, { definition }),
  reject: (id: number) => api.post<{ ok: true }>(`/api/glossary/candidates/${id}/reject`),
};

// System-wide structured logging
export interface SystemLogEntry {
  id: number;
  timestamp: string;
  level: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";
  source: string;
  action: string;
  execution_id: number | null;
  ticket_id: number | null;
  user: string | null;
  request_id: string | null;
  method: string | null;
  endpoint: string | null;
  status_code: number | null;
  duration_ms: number | null;
  input: unknown;
  output: unknown;
  error: { type: string; message: string; traceback: string } | null;
  context: Record<string, unknown>;
  tags: string[];
}

export interface SystemLogsResponse {
  total: number;
  offset: number;
  limit: number;
  items: SystemLogEntry[];
}

export interface SystemLogStats {
  total: number;
  by_level: Record<string, number>;
  by_source: { source: string; count: number }[];
}

export const SystemLogs = {
  list: (params: {
    level?: string;
    source?: string;
    action?: string;
    execution_id?: number;
    ticket_id?: number;
    user?: string;
    request_id?: string;
    from?: string;
    to?: string;
    q?: string;
    limit?: number;
    offset?: number;
  }) => {
    const p = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
    });
    const qs = p.toString();
    return api.get<SystemLogsResponse>(`/api/logs${qs ? `?${qs}` : ""}`);
  },
  byId: (id: number) => api.get<SystemLogEntry>(`/api/logs/${id}`),
  stats: () => api.get<SystemLogStats>("/api/logs/stats"),
  exportUrl: (params: { format?: string; level?: string; source?: string; limit?: number }) => {
    const p = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined) p.set(k, String(v));
    });
    return `${apiBase}/api/logs/export?${p.toString()}`;
  },
  purge: (days: number) =>
    api.delete<{ deleted: number; older_than_days: number }>(`/api/logs/purge?days=${days}`),
};

// ── Multi-project ─────────────────────────────────────────────────────────────

export const Projects = {
  list: () => api.get<ProjectsResponse>("/api/projects"),
  getActive: () => api.get<ActiveProjectResponse>("/api/active_project"),
  setActive: (name: string) =>
    api.post<{ ok: boolean; active: string; project: Project }>("/api/active_project", { name }),
  init: (payload: InitProjectPayload) =>
    api.post<{ ok: boolean; project: Project }>("/api/init_project", payload),
  update: (name: string, payload: Partial<InitProjectPayload>) =>
    api.patch<{ ok: boolean; project: Project }>(`/api/projects/${name}`, payload),
  remove: (name: string) =>
    api.delete<{ ok: boolean; deleted: string }>(`/api/projects/${name}`),
  byName: (name: string) =>
    api.get<{ ok: boolean; project: Project }>(`/api/projects/${name}`),
  getAgents: (name: string) =>
    api.get<{ ok: boolean; pinned_agents: string[] }>(`/api/projects/${name}/agents`),
  putAgents: (name: string, pinnedAgents: string[]) =>
    api.put<{ ok: boolean; pinned_agents: string[] }>(`/api/projects/${name}/agents`, { pinned_agents: pinnedAgents }),
  getCredentials: (name: string) =>
    api.get<{ ok: boolean; tracker_type: string; has_credentials: boolean; jira_user: string | null; ado_user: string | null; mantis_token_saved?: boolean; mantis_username_saved?: boolean; mantis_project_id?: string; mantis_protocol?: string }>(`/api/projects/${name}/credentials`),
  launchVsCode: (name: string) =>
    api.post<{ ok: boolean; port: number; already_running: boolean; launching?: boolean; workspace_root: string }>(`/api/projects/${name}/launch-vscode`),
  trackerStates: (name: string) =>
    api.get<{ ok: boolean; states: string[]; tracker_type: string }>(`/api/projects/${name}/tracker-states`),
  getAgentWorkflow: (projectName: string, filename: string) =>
    api.get<AgentWorkflowConfig & { ok: boolean }>(`/api/projects/${projectName}/agent-workflow/${encodeURIComponent(filename)}`),
  putAgentWorkflow: (projectName: string, filename: string, workflow: Partial<AgentWorkflowConfig>) =>
    api.put<AgentWorkflowConfig & { ok: boolean }>(`/api/projects/${projectName}/agent-workflow/${encodeURIComponent(filename)}`, workflow),
};

export interface MantisProject {
  id: string;
  name: string;
  description?: string;
  status?: string;
}

export interface MantisListParams {
  url: string;
  protocol?: "rest" | "soap";
  token?: string;
  username?: string;
  password?: string;
  verify_ssl?: boolean;
}

export const Mantis = {
  listProjects: (params: MantisListParams) =>
    api.post<{ ok: boolean; projects: MantisProject[]; error?: string }>(
      "/api/mantis/projects",
      params
    ),
};

// ── QA UAT — Sprint 9 types ───────────────────────────────────────────────────

export interface DataRequestOption {
  id: string;         // provide_existing_value | run_discovery_query | generate_sql_seed | manual_review
  label: string;
  requires_input: string[];
}

export interface DataRequestDecision {
  event: string;
  ticket_id: number;
  scenario_id: string;
  missing_requirement: string;
  question_for_user: string;
  options: DataRequestOption[];
  request_id: string;
  requirement_id: string;
  required_fields: string[];
}

export interface DataRequest {
  id: string;
  run_id: string;
  ticket_id: number;
  scenario_id: string;
  requirement_id: string;
  question: string;
  required_fields_json: string;  // JSON-serialised string[]
  status: "pending_user_input" | "resolved" | "timeout" | "rejected";
  created_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
  resolution_type: string | null;
}

export interface DataRequestListResponse {
  ok: boolean;
  requests: DataRequest[];
  total: number;
  pending: number;
  resolution_artifacts?: Record<string, DataRequestDecision[]>;
}

export interface DataRequestResolveResponse {
  ok: boolean;
  result: {
    request_id: string;
    status: string;
    resolution_type: string;
    resolved_at: string;
    validation?: { valid: boolean; resolved_data_ref: string | null };
  };
  error?: string;
  message?: string;
}

export interface QaUatRunResponse {
  execution_id: number;
  ticket_id: number;
  mode: string;
  stream_url: string;
}

export interface QaUatRunStatus {
  id: number;
  status: "queued" | "running" | "completed" | "error" | "failed";
  agent_type: string;
  output?: string;
  error?: string;
  pipeline_result?: {
    ok: boolean;
    ticket_id: number;
    verdict?: "PASS" | "FAIL" | "BLOCKED" | "MIXED";
    elapsed_s?: number;
    stages?: Record<string, unknown>;
    category?: string;
    reason?: string;
    failed_stage?: string;
    human_action_required?: string;
    data_readiness_v2_results?: unknown[];
    data_resolution_requests?: unknown[];
  };
  metadata?: Record<string, unknown>;
}

// ── QA UAT — Sprint 10: SQL Seed Proposal types ───────────────────────────────

export interface SqlSafetyChecks {
  transaction_present: boolean;
  rollback_default: boolean;
  prod_guard_present: boolean;
  seed_run_id_present: boolean;
  verification_select_present: boolean;
  dangerous_keywords: string[];
}

export interface SqlSafetyFinding {
  rule: string;
  detail: string;
}

export interface SqlSafetyResult {
  schema_version?: string;
  safe: boolean;
  risk_level: "low" | "medium" | "high" | "critical";
  requires_human_approval: boolean;
  blocking_findings: SqlSafetyFinding[];
  checks: SqlSafetyChecks;
  script_sha256: string;
  source: string;
}

export interface SeedProposal {
  scenario_id: string;
  script_path: string;
  cleanup_path: string | null;
  script_content: string | null;      // null if > 64KB
  cleanup_content: string | null;
  safety_result: SqlSafetyResult | null;
}

export interface SeedProposalListResponse {
  ok: boolean;
  proposals: SeedProposal[];
  total: number;
}

// ── QA UAT — Sprint 12: Catalog Readiness ─────────────────────────────────────

export interface CatalogCheckResult {
  catalog_name: string;
  db_table: string;
  status: "OK" | "EMPTY" | "UNVERIFIED" | "SEED_REQUIRED" | "PROD_BLOCKED";
  row_count: number | null;
  min_rows: number;
  blocking: boolean;
  seed_proposed: boolean;
  seed_script_path: string | null;
  error: string | null;
}

export interface CatalogReadinessResult {
  schema_version?: string;
  ok: boolean;
  scenario_id: string;
  run_id: string;
  ticket_id: number;
  total: number;
  ok_count: number;
  empty_count: number;
  unverified_count: number;
  seed_proposed_count: number;
  blocking_empty_count: number;
  catalog_results: CatalogCheckResult[];
  evidence_path: string | null;
  checked_at: string | null;
}

export interface CatalogFixtureSummary {
  catalog_name: string;
  db_table: string;
  pk_column: string;
  min_rows: number;
  description: string;
  seed_rows_count: number;
}

// ── QA UAT — Sprint 13: Oracle Engine + Weak Assertion Detector ───────────────

export interface OracleCheckResult {
  oracle_id: string;
  scenario_id: string;
  oracle_type: "UI" | "DB" | "API" | "CATALOG" | "CUSTOM";
  strength: "P0" | "P1" | "P2";
  description: string;
  verdict: "PASS" | "FAIL" | "NO_ORACLE" | "WEAK_ONLY" | "SKIP" | "ERROR";
  actual: unknown;
  expected: unknown;
  error: string | null;
}

export interface ScenarioOracleResult {
  scenario_id: string;
  oracle_verdict: "PASS" | "FAIL" | "NO_ORACLE" | "WEAK_ONLY" | "SKIP" | "ERROR";
  is_p0: boolean;
  oracle_count: number;
  strong_count: number;
  weak_count: number;
  pass_count: number;
  fail_count: number;
  blocking: boolean;
  oracle_checks: OracleCheckResult[];
}

export interface OracleEvaluationResult {
  schema_version?: string;
  ok: boolean;
  run_id: string;
  ticket_id: number;
  total_scenarios: number;
  evaluated_scenarios: number;
  pass_count: number;
  fail_count: number;
  no_oracle_count: number;
  weak_only_count: number;
  p0_blocked_count: number;
  publish_blocked: boolean;
  scenario_results: ScenarioOracleResult[];
  evidence_path: string | null;
  evaluated_at: string | null;
}

export interface TestAssertionResult {
  test_name: string;
  file_name: string;
  line_number: number | null;
  assertion_strength: "STRONG" | "WEAK" | "TRIVIAL" | "NONE";
  expect_call_count: number;
  strong_count: number;
  weak_count: number;
  trivial_count: number;
  is_weak: boolean;
  finding: string | null;
}

export interface FileAssertionAnalysis {
  file_name: string;
  total_tests: number;
  strong_tests: number;
  weak_tests: number;
  trivial_tests: number;
  no_assertion_tests: number;
  has_weak_tests: boolean;
  test_results: TestAssertionResult[];
}

export interface WeakAssertionReport {
  schema_version?: string;
  ok: boolean;
  run_id: string;
  ticket_id: number;
  files_analyzed: number;
  total_tests: number;
  strong_tests: number;
  weak_tests: number;
  trivial_tests: number;
  no_assertion_tests: number;
  publish_blocked: boolean;
  file_analyses: FileAssertionAnalysis[];
  evidence_path: string | null;
  analyzed_at: string | null;
}

// ── QA UAT — Sprint 14: Test Confidence + Data Lineage ────────────────────────

export interface ScoreFactor {
  name: string;
  delta: number;
  reason: string;
}

export interface ConfidenceScore {
  scenario_id: string;
  score: number;
  level: "HIGH" | "MEDIUM" | "LOW";
  is_p0: boolean;
  publish_blocked: boolean;
  factors: ScoreFactor[];
}

export interface ConfidenceReport {
  schema_version?: string;
  ok: boolean;
  run_id: string;
  ticket_id: number;
  total_scenarios: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  blocked_count: number;
  min_confidence: number;
  publish_blocked: boolean;
  scenario_scores: ConfidenceScore[];
  evidence_path: string | null;
  scored_at: string | null;
}

export interface LineageEntry {
  field: string;
  value: string | null;
  source: "SEEDED" | "USER_SUPPLIED" | "ENVIRONMENT" | "FIXTURE" | "DISCOVERED" | "UNKNOWN";
  scenario_id: string;
  seed_run_id: string | null;
  seed_script: string | null;
  seeded_at: string | null;
  cleaned_up: boolean;
  cleanup_at: string | null;
  origin_note: string | null;
  evidence_refs: string[];
}

export interface DataLineageResult {
  schema_version?: string;
  ok: boolean;
  run_id: string;
  ticket_id: number;
  total_entries: number;
  seeded_count: number;
  user_supplied_count: number;
  fixture_count: number;
  discovered_count: number;
  unknown_count: number;
  entries: LineageEntry[];
  evidence_path: string | null;
  built_at: string | null;
}

// ── QA UAT — Sprint 9 endpoints ───────────────────────────────────────────────

export const QaUat = {
  /** Launch the QA UAT pipeline for a ticket. Returns execution_id. */
  run: (payload: { ticket_id: number; mode?: string; headed?: boolean; timeout_ms?: number }) =>
    api.post<QaUatRunResponse>("/api/qa-uat/run", payload),

  /** Poll a QA UAT execution result (alias: getRunResult). */
  status: (executionId: number | string) =>
    api.get<QaUatRunStatus>(`/api/qa-uat/run/${executionId}`),

  /** Poll a QA UAT execution result. */
  getRunResult: (executionId: number) =>
    api.get<QaUatRunStatus>(`/api/qa-uat/run/${executionId}`),

  /** List all data resolution requests for a run. */
  listDataRequests: (runId: string, ticketId: number, status?: string) =>
    api.get<DataRequestListResponse>(
      `/api/qa-uat/data-request?run_id=${encodeURIComponent(runId)}&ticket_id=${ticketId}${status ? `&status=${status}` : ""}`
    ),

  /** Get status of a specific data request. */
  getDataRequestStatus: (requestId: string, runId: string, ticketId: number) =>
    api.get<{ ok: boolean; result: DataRequest }>(
      `/api/qa-uat/data-request/${encodeURIComponent(requestId)}/status?run_id=${encodeURIComponent(runId)}&ticket_id=${ticketId}`
    ),

  /** Resolve a pending data request (submit value or choose decision). */
  resolveDataRequest: (
    requestId: string,
    payload: {
      resolution_type: string;
      supplied_fields?: Record<string, string>;
      note?: string;
      run_id: string;
      ticket_id: number;
      scenario_id?: string;
    }
  ) =>
    api.post<DataRequestResolveResponse>(
      `/api/qa-uat/data-request/${encodeURIComponent(requestId)}/resolve`,
      payload
    ),

  /** Create data resolution broker requests from a readiness result. */
  createDataRequests: (
    runId: string,
    payload: { readiness_result: Record<string, unknown>; environment?: string }
  ) =>
    api.post<{ ok: boolean; result: Record<string, unknown> }>(
      `/api/qa-uat/data-request/${encodeURIComponent(runId)}`,
      payload
    ),

  // ── Sprint 10: SQL Seed Proposal ───────────────────────────────────────────

  /** List seed proposals for a run (reads evidence artifacts). */
  listSeedProposals: (runId: string, ticketId: number, scenarioId?: string) =>
    api.get<SeedProposalListResponse>(
      `/api/qa-uat/seed-proposal?run_id=${encodeURIComponent(runId)}&ticket_id=${ticketId}${scenarioId ? `&scenario_id=${encodeURIComponent(scenarioId)}` : ""}`
    ),

  /** Validate an arbitrary SQL script against safety rules. */
  validateSeedScript: (sqlText: string, source?: string) =>
    api.post<{ ok: boolean; result: SqlSafetyResult }>(
      "/api/qa-uat/seed-proposal/validate",
      { sql_text: sqlText, source: source ?? "operator_submitted" }
    ),

  // ── Sprint 11: Human Approval + Cleanup ────────────────────────────────────

  /** Approve a seed proposal and optionally execute it (dry_run=true by default). */
  approveSeedProposal: (payload: {
    run_id: string;
    ticket_id: number;
    scenario_id: string;
    approved_sha256: string;
    approved_by?: string;
    dry_run?: boolean;
  }) =>
    api.post<{ ok: boolean; result: Record<string, unknown> }>(
      "/api/qa-uat/seed-proposal/approve",
      payload
    ),

  /** Trigger cleanup for seeded data. */
  triggerCleanup: (payload: {
    run_id: string;
    ticket_id: number;
    scenario_id: string;
    seed_run_id: string;
    cleanup_policy?: string;
    dry_run?: boolean;
  }) =>
    api.post<{ ok: boolean; result: Record<string, unknown> }>(
      "/api/qa-uat/seed-proposal/cleanup",
      payload
    ),

  /** List seed approval records for a run. */
  listSeedApprovals: (runId: string, ticketId: number) =>
    api.get<{ ok: boolean; approvals: Record<string, unknown>[]; total: number }>(
      `/api/qa-uat/seed-proposal/approvals?run_id=${encodeURIComponent(runId)}&ticket_id=${ticketId}`
    ),

  // ── Sprint 12: Catalog Readiness ──────────────────────────────────────────

  /** Get catalog readiness artifacts for a run (from evidence dir). */
  listCatalogReadiness: (runId: string, ticketId: number, scenarioId?: string) =>
    api.get<{ ok: boolean; catalogs: CatalogReadinessResult[]; total: number }>(
      `/api/qa-uat/catalog-readiness?run_id=${encodeURIComponent(runId)}&ticket_id=${ticketId}${scenarioId ? `&scenario_id=${encodeURIComponent(scenarioId)}` : ""}`
    ),

  /** Trigger an on-demand catalog readiness check. */
  checkCatalogReadiness: (payload: {
    run_id: string;
    ticket_id: number;
    scenario_id?: string;
    required_catalogs: string[];
    dry_run?: boolean;
  }) =>
    api.post<{ ok: boolean; result: CatalogReadinessResult }>(
      "/api/qa-uat/catalog-readiness/check",
      payload
    ),

  /** List catalog fixture definitions from catalog_fixtures.yml. */
  listCatalogFixtures: () =>
    api.get<{ ok: boolean; fixtures: CatalogFixtureSummary[]; total: number }>(
      "/api/qa-uat/catalog-readiness/fixtures"
    ),

  // ── Sprint 13: Oracle Engine + Weak Assertion Detector ────────────────────

  /** List oracle_result.json artifacts for a run. */
  listOracleResults: (runId: string, ticketId: number, scenarioId?: string) =>
    api.get<{ ok: boolean; results: OracleEvaluationResult[]; total: number }>(
      `/api/qa-uat/oracle-result?run_id=${encodeURIComponent(runId)}&ticket_id=${ticketId}${scenarioId ? `&scenario_id=${encodeURIComponent(scenarioId)}` : ""}`
    ),

  /** Trigger on-demand oracle evaluation for a run. */
  evaluateOracles: (payload: {
    run_id: string;
    ticket_id: number;
    scenarios_path?: string;
    runner_output_path?: string;
    oracle_contracts_dir?: string;
  }) =>
    api.post<{ ok: boolean; result: OracleEvaluationResult }>(
      "/api/qa-uat/oracle-result/evaluate",
      payload
    ),

  /** Get weak assertion report for a run. */
  getWeakAssertions: (runId: string, ticketId: number) =>
    api.get<{ ok: boolean; report: WeakAssertionReport | null; message?: string }>(
      `/api/qa-uat/oracle-result/weak-assertions?run_id=${encodeURIComponent(runId)}&ticket_id=${ticketId}`
    ),

  // ── Sprint 14: Test Confidence + Data Lineage ─────────────────────────────

  /** Get confidence report for a run. */
  getConfidenceReport: (runId: string, ticketId: number) =>
    api.get<{ ok: boolean; report: ConfidenceReport | null; message?: string }>(
      `/api/qa-uat/confidence-report?run_id=${encodeURIComponent(runId)}&ticket_id=${ticketId}`
    ),

  /** Trigger on-demand confidence scoring for a run. */
  scoreConfidence: (payload: {
    run_id: string;
    ticket_id: number;
    min_confidence?: number;
    deployment_matched?: boolean | null;
  }) =>
    api.post<{ ok: boolean; result: ConfidenceReport }>(
      "/api/qa-uat/confidence-report/score",
      payload
    ),

  /** Get data lineage artifact for a run. */
  getDataLineage: (runId: string, ticketId: number) =>
    api.get<{ ok: boolean; lineage: DataLineageResult | null; message?: string }>(
      `/api/qa-uat/data-lineage?run_id=${encodeURIComponent(runId)}&ticket_id=${ticketId}`
    ),

  /** Trigger on-demand data lineage build for a run. */
  buildDataLineage: (payload: { run_id: string; ticket_id: number }) =>
    api.post<{ ok: boolean; result: DataLineageResult }>(
      "/api/qa-uat/data-lineage/build",
      payload
    ),
};
