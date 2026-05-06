import { api, apiBase } from "./client";
import type {
  AgentDefinition,
  AgentExecution,
  AgentType,
  ContextBlock,
  PackDefinition,
  PackRun,
  PipelineBatchResponse,
  PipelineInferenceResult,
  Ticket,
  TicketFingerprint,
  TicketHierarchy,
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

export const QaUat = {
  run: (ticketId: number, mode: "dry-run" | "publish" = "dry-run") =>
    api.post<{ ok: boolean; execution_id: string; status: string }>(
      "/api/qa-uat/run",
      { ticket_id: ticketId, mode }
    ),
  status: (executionId: string) =>
    api.get<QaUatRunStatus>(`/api/qa-uat/run/${executionId}`),
};

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
