export type AgentType =
  | "business"
  | "functional"
  | "technical"
  | "developer"
  | "qa"
  | "custom";

export interface VsCodeAgent {
  name: string;
  filename: string;
  description: string;
  system_prompt: string;
}

export type ExecutionStatus =
  | "queued"
  | "running"
  | "completed"
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
