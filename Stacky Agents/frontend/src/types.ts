export type AgentType =
  | "business"
  | "functional"
  | "technical"
  | "developer"
  | "qa"
  | "custom";

/** Runtime de ejecución del agente. Controla cómo se lanza la corrida. */
export type AgentRuntime = "github_copilot" | "codex_cli" | "claude_code_cli";

export interface VsCodeAgent {
  name: string;
  filename: string;
  description: string;
  system_prompt: string;
}

export type ExecutionStatus =
  | "preparing"
  | "queued"
  | "running"
  | "completed"
  | "needs_review"
  | "error"
  | "cancelled"
  | "discarded";

export type TicketStackyStatus =
  | "idle"
  | "running"
  | "completed"
  | "error"
  | "cancelled";

export type Verdict = "approved" | "discarded" | null;

export interface AgentDefinition {
  type: AgentType;
  name: string;
  icon: string;
  description: string;
  inputs: string[];
  outputs: string[];
  default_blocks: string[];
}

export interface ContextBlock {
  id: string;
  kind: "auto" | "editable" | "choice";
  title: string;
  content?: string;
  items?: { selected: boolean; label: string }[];
  source?: { type: string; [k: string]: unknown };
}

// P6: tipos para el recomendador de asignacion
export interface AssignmentCandidate {
  ado_unique_name: string;
  display_name: string;
  score: number;
  rank: number;
  overloaded: boolean;
  load_pct: number;
  active_tickets: number;
  active_tickets_detail: { ado_id: number; priority: number; state: string }[];
  reason: string;
  recommendation_flags: string[];
  type_affinity: { score: number; top_types: string[]; match: boolean };
  area_affinity: { score: number; matched_areas: string[] };
  throughput_score: number;
}

export interface AssignmentRecommendationResponse {
  ok: boolean;
  ticket_id: number;
  ticket_ado_id: number;
  scored_at: string;
  candidates: AssignmentCandidate[];
  excluded: { ado_unique_name: string; reason: string; load_pct: number }[];
  advisory_only: true;
  publish_requires_human_approval: true;
  duration_ms?: number;
  warning?: string;
}

export interface Ticket {
  id: number;
  ado_id: number;
  project: string;
  title: string;
  description?: string;
  ado_state?: string;
  ado_url?: string;
  priority?: number;
  work_item_type?: string;      // "Epic" | "Task" | "Bug" | etc.
  // P6: asignado en ADO
  assigned_to_ado?: string | null;
  parent_ado_id?: number | null;
  last_synced_at?: string;
  // Estado interno de Stacky (independiente de ado_state).
  // Actualizado por agent_runner vía ticket_status service.
  stacky_status?: TicketStackyStatus;
  last_execution?: AgentExecution | null;
  pipeline_summary?: {
    done_stages: string[];
    next_suggested: string | null;
    overall_progress: number;
  };
}

export interface TicketNode extends Ticket {
  children: TicketNode[];
}

export interface TicketHierarchy {
  epics: TicketNode[];
  orphans: TicketNode[];
}

export interface AgentExecution {
  id: number;
  ticket_id: number;
  agent_type: AgentType;
  status: ExecutionStatus;
  verdict?: Verdict;
  input_context: ContextBlock[];
  chain_from: number[];
  output?: string;
  output_format?: string;
  metadata?: Record<string, unknown>;
  error_message?: string | null;
  started_by: string;
  started_at: string;
  completed_at?: string | null;
  duration_ms?: number | null;
  pack_run_id?: number | null;
  pack_step?: number | null;
  contract_result?: ContractResult | null;  // N1
  // P2.3: campo portado de WS2 — nombre del .agent.md asociado a la ejecucion
  agent_filename?: string | null;
}

// N1 — Contract Validator
export interface ContractFailure {
  rule: string;
  message: string;
  severity: "error" | "warning";
}

export interface ContractResult {
  agent_type: string;
  passed: boolean;
  score: number;       // 0–100
  failures: ContractFailure[];
  warnings: ContractFailure[];
}

// N3 — Ticket Pre-Analysis Fingerprint
export interface TicketFingerprint {
  ticket_ado_id: number;
  change_type: "feature" | "bug" | "refactor" | "config" | "unknown";
  domain: string[];
  complexity: "S" | "M" | "L" | "XL";
  suggested_pack: string;
  domain_confidence: number;
  keywords_detected: string[];
}

// ADO Pipeline Inference — inferencia LLM basada 100% en datos de ADO
export interface PipelineStageInference {
  stage: string;
  label: string;
  done: boolean;
  confidence: number;
  evidence: string;
}

export interface PipelineInferenceResult {
  ado_id: number;
  stages: Record<string, PipelineStageInference>;
  next_suggested: string | null;
  overall_progress: number;
  summary: string;
  inferred_at: string;
  model_used: string;
  source: "llm" | "cache";
  error?: string;
}

export interface PipelineBatchResponse {
  results: Record<string, PipelineInferenceResult>;
}

export interface TicketPipelineStage {
  stage: string;
  done: boolean;
  evidence?: string | null;
  last_execution?: {
    id: number;
    status: ExecutionStatus;
    agent_type: string;
  } | null;
}

export interface TicketPipelineResponse {
  ticket_id: number;
  stages: TicketPipelineStage[];
  next: {
    agent_type: string;
    source: "flow_config" | "default";
  } | null;
}

// ── Multi-project ────────────────────────────────────────────────────────────

export type TrackerType = "azure_devops" | "jira" | "mantis" | "gitlab";  // Plan 65

export interface DocsPaths {
  technical: string;
  functional: string;
}

export interface Project {
  name: string;
  display_name: string;
  workspace_root: string;
  agents_dir?: string;
  docs_paths?: DocsPaths;
  tracker_type: TrackerType;
  /** Azure DevOps fields */
  organization?: string;
  ado_project?: string;
  /** Jira fields */
  jira_url?: string;
  jira_key?: string;
  /** Mantis fields */
  mantis_url?: string;
  mantis_project_id?: string;
  mantis_project_name?: string;
  mantis_protocol?: "rest" | "soap";
  /** GitLab fields */
  gitlab_url?: string;
  gitlab_project?: string;
  gitlab_group?: string;
  gitlab_auth_file?: string;
  /** Runtime */
  active: boolean;
  initialized: boolean;
  has_credentials?: boolean;
  /** Plan 16 — multi-cliente: true si el proyecto tiene client_profile en config.json. */
  has_client_profile?: boolean;
}

export interface ProjectsResponse {
  ok: boolean;
  projects: Project[];
  active: string | null;
}

export interface ActiveProjectResponse {
  ok: boolean;
  active: string | null;
  display_name: string;
  tracker_type: TrackerType;
}

export interface InitProjectPayload {
  name: string;
  display_name?: string;
  workspace_root: string;
  agents_dir?: string;
  docs_paths?: DocsPaths;
  tracker_type: TrackerType;
  // ADO
  organization?: string;
  ado_project?: string;
  area_path?: string;
  pat?: string;
  // Jira
  jira_url?: string;
  jira_key?: string;
  api_version?: string;
  jql?: string;
  verify_ssl?: boolean;
  jira_user?: string;
  jira_token?: string;
  // Mantis
  mantis_url?: string;
  mantis_project_id?: string;
  mantis_project_name?: string;
  mantis_protocol?: "rest" | "soap";
  mantis_token?: string;
  mantis_username?: string;
  mantis_password?: string;
  // GitLab (Plan 65)
  gitlab_url?: string;
  gitlab_project?: string;
  gitlab_group?: string;
  gitlab_auth_file?: string;
}

export interface AgentWorkflowConfig {
  allowed_states: string[];
  transition_state: string;
  requires_prior_output: boolean;
}

export interface PackStep {
  agent_type: AgentType;
  chain_from_previous: boolean;
  pause_after: boolean;
  skip_if_approved_within: string | null;
}

export interface PackDefinition {
  id: string;
  name: string;
  description: string;
  steps: PackStep[];
}

export interface PackRun {
  id: number;
  pack_definition_id: string;
  ticket_id: number;
  status: "running" | "paused" | "completed" | "abandoned" | "error";
  current_step: number;
  options: Record<string, unknown> | null;
  started_by: string;
  started_at: string;
  completed_at?: string | null;
  executions?: AgentExecution[];
  definition?: PackDefinition;
}

export interface LogLine {
  timestamp: string;
  level: "debug" | "info" | "warn" | "error";
  message: string;
  group?: string | null;
  indent?: number;
  type?: string;
}
