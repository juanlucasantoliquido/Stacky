import { api, apiBase, rawPost, type RawResponse, type GatewayErrorBody } from "./client";
export type { RawResponse, GatewayErrorBody };
import type { EnvironmentPlanResponse, EnvironmentApplyResponse } from "../devops/environmentModel";
import type { PreflightCheck } from "../devops/preflightModel";
import type { DoctorJob } from "../devops/doctorModel";
import type { DocGraphResponse } from "../docs/docGraphModel";
export type { DocGraphResponse };
import type {
  DbEnvironment,
  DbCompareHealth,
  SnapshotMeta,
  TestConnectionResult,
  DbSnapshot,
  CompareRun,
} from "../components/dbcompare/dbcompareTypes";
import type { Manifest } from "../components/dbcompare/scriptsLogic";
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
  TicketPipelineResponse,
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

/** Contrato de respuesta del endpoint POST /api/tickets/{id}/finish-work */
export interface FinishWorkResponse {
  ok: boolean;
  dry_run: boolean;
  ticket_id: number;
  ado_id: number | null;
  preconditions: {
    html_exists: boolean;
    html_invalid_reason: string | null;
    current_stacky_status: string;
    /** @deprecated use active_execution instead */
    execution_id: number | null;
    ado_id: number | null;
    /** Ejecución activa al momento del dry-run (Fase 5.B). */
    active_execution: {
      execution_id: number;
      agent_type: string;
      will_cancel: boolean;
    } | null;
  };
  actions: {
    action: string;
    ok: boolean;
    to?: string | null;
    reason?: string | null;
    status?: string | null;
    html_sha256?: string | null;
    record_id?: number | null;
  }[];
  current_status: string;
  operator: string;
  /** Resultado de la cancelación de la ejecución activa (Fase 5.B). null si no había ejecución activa. */
  cancel_result: {
    execution_id: number;
    agent_type: string;
    cancel_ok: boolean;
    cancel_reason: string | null;
  } | null;
}

// P7: tipo extendido de sync status
export interface SyncStatusV2 {
  last_synced_at: string | null;
  seconds_since_sync: number | null;
  is_stale: boolean;
  stale_threshold_sec: number;
  sync_in_progress: boolean;
}

export interface FrontendConfig {
  ticket_sync_interval_ms: number;
  sync_min_interval_sec: number;
  stale_threshold_sec: number;
  issue_from_brief_enabled: boolean;
}

export const Tickets = {
  list: (project?: string | null, assignedTo?: string | null) => {
    const params = new URLSearchParams();
    if (project) params.set("project", project);
    if (assignedTo) params.set("assigned_to", assignedTo);
    const qs = params.toString();
    return api.get<Ticket[]>(`/api/tickets${qs ? `?${qs}` : ""}`);
  },
  // Requerimiento B: identidad ADO del operador (para filtro "Mis tareas").
  adoUser: (project?: string | null, refresh = false) => {
    const params = new URLSearchParams();
    if (project) params.set("project", project);
    if (refresh) params.set("refresh", "1");
    const qs = params.toString();
    return api.get<{
      ok: boolean;
      linked: boolean;
      source?: string;
      ado_unique_name?: string;
      ado_display_name?: string;
      verified_at?: string;
      stacky_user?: string;
      project?: string;
      message?: string;
    }>(`/api/tickets/ado-user${qs ? `?${qs}` : ""}`);
  },
  byId: (id: number) => api.get<Ticket & { executions: AgentExecution[] }>(`/api/tickets/${id}`),
  hierarchy: (project?: string | null) =>
    api.get<TicketHierarchy>(`/api/tickets/hierarchy${project ? `?project=${encodeURIComponent(project)}` : ""}`),
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
  pipeline: (id: number) =>
    api.get<TicketPipelineResponse>(`/api/tickets/${id}/pipeline`),
  sync: (project?: string | null) =>
    api.post<TicketSyncResult>("/api/tickets/sync", project ? { project } : {}),
  // P7: sync con rate limiting y campos extendidos
  syncV2: (trigger: "manual" | "auto_poll" | "startup" = "manual", project?: string | null) =>
    fetch(`${apiBase}/api/tickets/sync-v2`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Stacky-Trigger": trigger },
      body: JSON.stringify(project ? { project } : {}),
    }).then(r => r.json()) as Promise<TicketSyncResult & { duration_ms?: number; idempotent?: boolean }>,
  syncStatus: (project?: string | null) =>
    api.get<{ last_synced_at: string | null }>(`/api/tickets/sync/status${project ? `?project=${encodeURIComponent(project)}` : ""}`),
  // P7: sync status extendido
  syncStatusV2: (project?: string | null) =>
    api.get<SyncStatusV2>(`/api/tickets/sync/status-v2${project ? `?project=${encodeURIComponent(project)}` : ""}`),
  // P7: config del frontend
  frontendConfig: () => api.get<FrontendConfig>("/api/tickets/config/frontend"),
  // P6: recomendador de asignacion
  assignmentRecommendations: (
    ticketId: number,
    filters?: { max_load_pct?: number; only_skill?: string; exclude_ado_unique_names?: string[] }
  ) => api.post<import("../types").AssignmentRecommendationResponse>(
    `/api/tickets/${ticketId}/assignment-recommendations`,
    filters || {}
  ),
  // P6: aplicar asignacion (siempre dry_run=true por defecto)
  assignTicket: (
    ticketId: number,
    payload: { ado_unique_name: string; dry_run?: boolean; reason?: string }
  ) => api.post<{
    ok: boolean; dry_run: boolean; ticket_id: number; ticket_ado_id: number;
    ado_updated?: boolean; local_db_updated?: boolean;
    assigned_to?: string; would_assign_to?: string; actions: unknown[];
  }>(`/api/tickets/${ticketId}/assign`, payload),
  // P6: estadisticas por usuario
  userStats: (user?: string) =>
    api.get<{ ok: boolean; users: unknown[]; total: number }>(
      `/api/tickets/user-stats${user ? `?user=${encodeURIComponent(user)}` : ""}`
    ),
  // P6: sincronizar usuarios desde ADO
  syncUsersFromAdo: () =>
    api.post<{ ok: boolean; created: number; updated: number; total: number }>(
      "/api/tickets/users/sync-from-ado",
      {}
    ),
  // Feature B: diagnosticos causales
  diagnostics: (ticketId: number) =>
    api.get<{
      ok: boolean; ticket_id: number; ticket_ado_id: number; aging_days: number;
      probable_causes: { category: string; description: string; confidence: number; evidence: string[] }[];
      suggested_actions: string[]; advisory_only: boolean; from_cache: boolean;
    }>(`/api/tickets/${ticketId}/diagnostics`),
  invalidateDiagnosticsCache: (ticketId: number) =>
    api.delete<{ ok: boolean; cache_removed: boolean }>(`/api/tickets/${ticketId}/diagnostics/cache`),
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
  /**
   * Cierre manual fallback de un ticket (Fase 4).
   * Envía X-Completion-Source: manual_ui para trazabilidad en SystemLogs.
   */
  finishWork: (
    id: number,
    payload: {
      operator_reason: string;
      publish_to_ado?: boolean;
      html_output_path?: string | null;
      target_ado_state?: string | null;
      force_publish?: boolean;
      force_finish?: boolean;
      dry_run?: boolean;
      /** Si true (default server-side), cancela la ejecución activa antes del cierre (Fase 5.B). */
      cancel_active_execution?: boolean;
    }
  ): Promise<FinishWorkResponse> =>
    api.postWithHeaders<FinishWorkResponse>(
      `/api/tickets/${id}/finish-work`,
      payload,
      { "X-Completion-Source": "manual_ui" }
    ),

  // ── Fase 2: pending-tasks y create-child-task ──────────────────────────────

  /**
   * Lista los pending-task.json no consumidos para un Epic.
   * GET /api/tickets/by-ado/{epic_ado_id}/pending-tasks
   */
  listPendingTasks: (epicAdoId: number): Promise<ListPendingTasksResponse> =>
    api.get<ListPendingTasksResponse>(`/api/tickets/by-ado/${epicAdoId}/pending-tasks`),

  /**
   * Crea una Task hija del Epic en ADO consumiendo un pending-task.json.
   * POST /api/tickets/by-ado/{epic_ado_id}/create-child-task
   * Envía X-Completion-Source: manual_ui para trazabilidad.
   */
  createChildTask: (
    epicAdoId: number,
    payload: {
      pending_task_path: string;
      operator_reason?: string;
      dry_run?: boolean;
      project?: string | null;
      repo_root?: string | null;
      outputs_root?: string | null;
    }
  ): Promise<CreateChildTaskResponse> =>
    api.postWithHeaders<CreateChildTaskResponse>(
      `/api/tickets/by-ado/${epicAdoId}/create-child-task`,
      payload,
      { "X-Completion-Source": "manual_ui" }
    ),

  /**
   * Vista "Desatascador": tickets en ejecución + readiness de artifacts
   * (comment.html / pending-task.json) a nivel board.
   * GET /api/tickets/unblocker-board
   */
  // Plan 66 — F1: acepta includeCompleted (default true)
  unblockerBoard: (
    project?: string | null,
    artifactRoot?: string | null,
    includeCompleted: boolean = true,
  ): Promise<UnblockerBoardResponse> => {
    const params = new URLSearchParams();
    if (project) params.set("project", project);
    if (artifactRoot) params.set("outputs_root", artifactRoot);
    if (!includeCompleted) params.set("include_completed", "false");
    const qs = params.toString();
    return api.get<UnblockerBoardResponse>(`/api/tickets/unblocker-board${qs ? `?${qs}` : ""}`);
  },

  rescueArtifact: (
    adoId: number,
    payload: {
      artifact_type?: "auto" | "pending_task" | "task" | "comment";
      files: { name: string; content: string }[];
      project?: string | null;
      repo_root?: string | null;
      outputs_root?: string | null;
      rf_id?: string | null;
    }
  ): Promise<RescueArtifactResponse> =>
    api.post<RescueArtifactResponse>(`/api/tickets/by-ado/${adoId}/rescue-artifact`, payload),

  // P2.3 — adjuntos del ticket (portado de WS2)
  attachments: (id: number) =>
    api.get<{ attachments: TicketAttachment[]; error?: string }>(`/api/tickets/${id}/attachments`),
  attachmentContent: (id: number, url: string, name: string) =>
    api.get<{ content: string | null; ok: boolean; binary?: boolean; error?: string }>(
      `/api/tickets/${id}/attachments/content?url=${encodeURIComponent(url)}&name=${encodeURIComponent(name)}`
    ),
  deleteAttachments: (id: number, attachments: { id: string; url: string; name: string }[]) =>
    api.delete<{ deleted: string[]; errors: { id: string; name: string; error: string }[] }>(
      `/api/tickets/${id}/attachments`,
      { attachments }
    ),
  uploadAttachment: (id: number, name: string, content: string) =>
    api.post<{ ok: boolean; error?: string }>(`/api/tickets/${id}/attachments`, { name, content }),
  // Plan 38 B2 — Épica desde Brief
  createEpicFromBrief: (payload: {
    title: string;
    description_html: string;
    brief: string;
    project_name?: string;
    confirm: true;
  }) =>
    api.post<{ ok: boolean; ado_id: number; work_item_type: string; title: string; url: string }>(
      "/api/tickets/epics/from-brief",
      payload
    ),
  // Plan 55 F1 — Preview solo-lectura del payload que se publicaría en ADO.
  epicPreview: (executionId: number, workItemType: "Epic" | "Issue" = "Epic") =>
    api.get<{
      ok: boolean;
      title: string | null;
      html: string | null;
      work_item_type: string;
      error: string | null;
      grounding_warnings: string[];
      publishable_runtime: boolean;
    }>(`/api/tickets/epic-preview?execution_id=${executionId}&work_item_type=${workItemType}`),
  // Plan 59 F2 — Preview solo-lectura de la jerarquía de hijos propuesta.
  epicChildrenPreview: (body: { output: string; brief?: string; project_name?: string }) =>
    api.post<{
      enabled: boolean;
      epic_ok?: boolean;
      epic_title?: string | null;
      epic_error?: string | null;
      features: Array<{
        work_item_type: string;
        title: string;
        html: string;
        children: Array<{ work_item_type: string; title: string; html: string }>;
      }>;
      total_children: number;
      children_error?: string | null;
      plan_fingerprint?: string;
    }>("/api/tickets/epic-children-preview", body),
  // Plan 59 F4 — Crea los hijos del Epic en ADO tras aprobación del operador.
  createEpicChildren: (body: {
    epic_ado_id: number;
    output: string;
    project_name?: string;
    approved_fingerprint?: string;
  }) =>
    api.post<{
      enabled: boolean;
      created_ids: number[];
      reused_ids: number[];
      error: string | null;
      skipped: boolean;
    }>("/api/tickets/epic-children", body),
};

// ── Fase 2: tipos para pending-tasks y create-child-task ──────────────────────

export interface PendingTaskItem {
  rf_id: string;
  title: string;
  pending_task_path: string;
  generated_at: string;
  plan_de_pruebas_path: string;
  plan_exists: boolean;
  status: "pending_manual_creation" | "consumed";
}

export interface ListPendingTasksResponse {
  ok: boolean;
  epic_ado_id: number;
  pending_tasks: PendingTaskItem[];
  total_pending: number;
  total_consumed: number;
  parse_errors?: { rf_id: string; pending_task_path: string; error: string }[];
  total_errors?: number;
}

export interface CreateChildTaskAction {
  action: string;
  ok?: boolean;
  task_ado_id?: number | null;
  attachment_id?: string | null;
  reason?: string | null;
  detail?: string | null;
  would_call?: string;
  payload_preview?: Record<string, unknown>;
  file_exists?: boolean;
}

export interface CreateChildTaskResponse {
  ok: boolean;
  dry_run: boolean;
  epic_ado_id: number;
  task_parent_ado_id?: number | null;
  task_ado_id: number | null;
  task_url: string | null;
  attachment_id: string | null;
  actions: CreateChildTaskAction[];
  hierarchy_bridge?: {
    root_parent_ado_id?: number;
    process_template?: string;
    path?: string[];
    steps?: {
      type: string;
      ado_id: number;
      parent_ado_id: number;
      reused?: boolean;
    }[];
  } | null;
  pending_task_consumed: boolean;
  idempotent?: boolean;
  reason?: string;
  human_action_required?: string;
  correlation_id: string;
  error?: string;
  missing_fields?: string[];
  message?: string;
}

// ── Desatascador: unblocker-board ─────────────────────────────────────────────

export type UnblockerReadiness =
  | "task_ready"
  | "stale_consumed"
  | "comment_ready"
  | "waiting_files"
  | "artifacts_idle"
  | "files_error"
  | "completed_ok";   // Plan 66

export interface UnblockerParseError {
  rf_id: string;
  pending_task_path: string;
  error: string;
}

// Fix ADO-241: pending-task consumido cuya Task fue borrada en ADO. El archivo
// quedó "consumed" apuntando a un work item inexistente; el backend lo detecta
// contra la sync local y el endpoint create-child-task lo recrea (verifica
// contra ADO antes de honrar la idempotencia).
export interface UnblockerStaleConsumed {
  rf_id: string;
  title: string;
  pending_task_path: string;
  task_ado_id: number | null;
  consumed_at: string | null;
}

export interface UnblockerItem {
  ticket_id: number;
  ado_id: number | null;
  title: string;
  work_item_type: string | null;
  ado_state: string | null;
  stacky_status: string;
  ado_url: string | null;
  running: boolean;
  readiness: UnblockerReadiness;
  blockers: string[];
  comment: { exists: boolean; path: string | null; size_bytes: number };
  pending_tasks: PendingTaskItem[];
  total_pending: number;
  total_consumed: number;
  stale_consumed: UnblockerStaleConsumed[];
  total_stale_consumed: number;
  parse_errors: UnblockerParseError[];
  total_errors: number;
  last_execution: {
    id: number;
    agent_type: string | null;
    status: string;
    started_at: string | null;
  } | null;
}

export interface UnblockerScanRoot {
  label: string;
  path: string;
  exists: boolean;
}

export interface UnblockerScanInfo {
  override?: string | null;
  repo_root: string;
  repo_root_exists: boolean;
  outputs_dir: string;
  outputs_dir_exists: boolean;
  roots: UnblockerScanRoot[];
  watcher?: {
    running: boolean;
    outputs_dir: string | null;
    outputs_dir_exists?: boolean;
    poll_interval?: number;
    stable_delay_a?: number;
    stable_delay_b?: number;
    error?: string;
  };
}

export interface UnblockerBoardResponse {
  ok: boolean;
  repo_root: string;
  scan?: UnblockerScanInfo;
  items: UnblockerItem[];
  total: number;
  counts: {
    running: number;
    comment_ready: number;
    task_ready: number;
    waiting_files: number;
    files_error: number;
    stale_consumed: number;
    completed_ok?: number;          // Plan 66 — optional: backend viejo no lo manda
    completed_ok_truncated?: number; // Plan 66 — cuántos se ocultaron por cap
  };
}

export interface RescueArtifactResponse {
  ok: boolean;
  artifact_type?: "pending_task" | "comment";
  repo_root?: string;
  pending_task_path?: string;
  html_output_path?: string;
  normalized_epic_id?: string;
  original_epic_id?: string | number | null;
  error?: string;
  message?: string;
}

export interface TicketAttachment {
  id: string;
  name: string;
  url: string;
  size: number;
  created_by?: string;
  created_at?: string;
}

export type StackyMemoryStatus =
  | "draft"
  | "active"
  | "needs_review"
  | "superseded"
  | "rejected"
  | "quarantined"
  | "deleted";

export type StackyMemoryCheck =
  | "schema"
  | "checksum"
  | "secret"
  | "duplicate_exact"
  | "duplicate_semantic"
  | "conflict_graph"
  | "llm_judge";

export type StackyMemoryFindingAction =
  | "resolve_finding"
  | "activate_memory"
  | "needs_review_memory"
  | "quarantine_memory"
  | "mark_supersedes"
  | "mark_duplicates"
  | "mark_conflicts_with"
  | "mark_not_conflict";

export interface StackyMemoryObservation {
  memory_id: string;
  project: string;
  scope: string;
  type: string;
  title: string;
  content: string;
  topic_key: string | null;
  status: StackyMemoryStatus;
  confidence: number | null;
  source_kind: string | null;
  source_execution_id: number | null;
  source_ticket_id: number | null;
  source_ado_id: number | null;
  source_agent_type: string | null;
  author_email: string | null;
  author_role: string | null;
  tags: string[];
  revision_count: number;
  duplicate_count: number;
  created_at: string | null;
  updated_at: string | null;
  // Plan 26 — directivas (aditivo; null/0 para observaciones legacy).
  enforcement?: "suggest" | "always" | null;
  priority?: number;
  applies_to?: StackyDirectiveTargeting | null;
  _score?: number;
}

// Plan 26 M1.1 — targeting estructurado de una directiva (todas opcionales).
export interface StackyDirectiveTargeting {
  agent_types?: string[];
  projects?: string[];
  work_item_types?: string[];
  title_keywords?: string[];
  tags?: string[];
}

// Plan 26 M0.2 — preview de lo que `get_context_for_run` inyectaría.
export interface StackyMemoryContextPreview {
  content?: string;
  hits: number;
  active_hits?: number;
  suppressed_hits?: number;
  memory_ids?: string[];
  directive_ids?: string[];
  directive_hits?: number;
  directives_crowded_out_observations?: boolean;
}

// Plan 26 M3.2 — salud del set de directivas.
export interface StackyDirectiveHealth {
  project: string;
  overlapping: { ids: string[]; shared_targeting: Record<string, string[]> }[];
  budget_pressure: {
    project: string;
    agent_type: string;
    directive_chars: number;
    cap: number;
    ratio: number;
  }[];
  stale: { id: string; review_after: string | null; expires_at: string | null }[];
}

// Plan 26 M3.1 — tipos injectables (canal USER) vs reservados (B5).
export interface StackyMemoryTypes {
  injectable: string[];
  reserved: string[];
}

// Plan 26 M0.2/M3.1 — vista de un flag del arnés (subset usado por memoria).
export interface HarnessFlagView {
  key: string;
  type: "bool" | "csv" | "int" | "float" | "json" | string;
  label: string;
  description: string;
  group: string;
  pair: string | null;
  env_only: boolean;
  value: boolean | number | string;
  category: string;
  default: boolean | number | string;
  default_known: boolean;
  active: boolean;
  plain_help?: {              // Plan 86 — ayuda en lenguaje llano (null/ausente = sin ayuda aún)
    what: string;
    on_effect: string;
    off_effect: string;
    example: string;
  } | null;
  requires: string | null;      // Plan 82 — key de la flag bool master, o null
  requires_met: boolean;        // Plan 82 — true si no hay master o el master está ON
  min_value: number | null;     // Plan 83 — mínimo válido inclusive (solo numéricas)
  max_value: number | null;     // Plan 83 — máximo válido inclusive (solo numéricas)
  in_bounds: boolean;           // Plan 83 — false solo si el valor CONFIGURADO viola bounds
  restart_required?: boolean;   // Plan 84 — true = solo se lee al arranque del backend
  pending_restart?: boolean;   // Plan 84 — true = el valor difiere del boot (cambio pendiente)
  boot_value?: string | number | boolean | null;  // Plan 84 — valor con el que arrancó
  reserved?: boolean;         // Plan 85 — declarada para fase diferida, sin consumidor
  reserved_reason?: string;   // Plan 85 — por qué / qué fase la cablea
}

export interface HarnessFlagCategory {
  id: string;
  label: string;
  description: string;
  tier?: "simple" | "advanced";   // Plan 78 — nivel de profundidad (default tratado como "advanced")
  intent?: string;                 // Plan 78 — frase humana de intención
}

export interface StackyMemoryFinding {
  id: number;
  validation_run_id: number;
  project: string;
  check_name: StackyMemoryCheck | string;
  severity: "critical" | "error" | "warning" | "info" | string;
  status: "open" | "resolved" | string;
  memory_id: string | null;
  title: string;
  detail: string | null;
  evidence: Record<string, any>;
  created_at: string | null;
  updated_at: string | null;
}

export interface StackyMemoryValidationRun {
  id: number;
  project: string | null;
  status: "queued" | "running" | "completed" | "error" | string;
  requested_by: string | null;
  checks: StackyMemoryCheck[];
  summary: Record<string, any>;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface StackyMemoryRelation {
  relation_id: string;
  project: string;
  source_memory_id: string;
  target_memory_id: string;
  relation: string;
  status: string;
  reason: string | null;
  evidence: string | null;
  confidence: number | null;
  marked_by_actor: string | null;
  marked_by_kind: string | null;
  marked_by_model: string | null;
  source_validation_run_id: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface StackyMemoryConflictGraph {
  project: string;
  nodes: StackyMemoryObservation[];
  edges: StackyMemoryRelation[];
}

export interface StackyMemoryTicketBadge {
  ticket_id: number;
  open_findings: number;
  critical: number;
  error: number;
  warning: number;
  info: number;
  checks: Record<string, number>;
}

export const Memory = {
  list: (params?: { project?: string | null; status?: string; scope?: string; type?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.project) qs.set("project", params.project);
    if (params?.status) qs.set("status", params.status);
    if (params?.scope) qs.set("scope", params.scope);
    if (params?.type) qs.set("type", params.type);
    if (params?.limit) qs.set("limit", String(params.limit));
    const query = qs.toString();
    return api.get<StackyMemoryObservation[]>(`/api/memory${query ? `?${query}` : ""}`);
  },
  setStatus: (memoryId: string, status: StackyMemoryStatus) =>
    api.post<{ ok: boolean }>(`/api/memory/${encodeURIComponent(memoryId)}/status`, { status }),
  startValidation: (payload: { project?: string | null; checks?: StackyMemoryCheck[] }) =>
    api.post<{ run_id: number; status: string }>("/api/memory/validation/runs", payload),
  validationRuns: (project?: string | null, limit = 20) =>
    api.get<StackyMemoryValidationRun[]>(
      `/api/memory/validation/runs?limit=${limit}${project ? `&project=${encodeURIComponent(project)}` : ""}`
    ),
  findings: (params?: { project?: string | null; status?: string | null; check?: string; severity?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.project) qs.set("project", params.project);
    if (params?.status !== undefined) qs.set("status", params.status ?? "");
    if (params?.check) qs.set("check", params.check);
    if (params?.severity) qs.set("severity", params.severity);
    if (params?.limit) qs.set("limit", String(params.limit));
    const query = qs.toString();
    return api.get<StackyMemoryFinding[]>(`/api/memory/validation/findings${query ? `?${query}` : ""}`);
  },
  applyFindingAction: (
    findingId: number,
    payload: {
      action: StackyMemoryFindingAction;
      source_memory_id?: string | null;
      target_memory_id?: string | null;
      reason?: string | null;
    },
  ) =>
    api.post<StackyMemoryFinding>(
      `/api/memory/validation/findings/${findingId}/action`,
      payload,
    ),
  ticketBadges: (project?: string | null) =>
    api.get<Record<string, StackyMemoryTicketBadge>>(
      `/api/memory/validation/ticket-badges${project ? `?project=${encodeURIComponent(project)}` : ""}`
    ),
  relations: (params?: { project?: string | null; relation?: string; status?: string; memory_id?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.project) qs.set("project", params.project);
    if (params?.relation) qs.set("relation", params.relation);
    if (params?.status) qs.set("status", params.status);
    if (params?.memory_id) qs.set("memory_id", params.memory_id);
    if (params?.limit) qs.set("limit", String(params.limit));
    const query = qs.toString();
    return api.get<StackyMemoryRelation[]>(`/api/memory/relations${query ? `?${query}` : ""}`);
  },
  conflictGraph: (project: string, status?: string) =>
    api.get<StackyMemoryConflictGraph>(
      `/api/memory/conflict-graph?project=${encodeURIComponent(project)}${status ? `&status=${encodeURIComponent(status)}` : ""}`
    ),
  // Plan 26 M2.1 — alta de memoria/directiva (POST /api/memory aditivo).
  create: (payload: {
    project: string;
    type: string;
    title: string;
    content: string;
    scope?: string;
    enforcement?: "suggest" | "always";
    priority?: number;
    applies_to?: StackyDirectiveTargeting;
    topic_key?: string | null;
  }) => api.post<{ memory_id: string }>("/api/memory", payload),
  // Plan 26 M2.2 — edición por memory_id (PATCH, add-only).
  update: (
    memoryId: string,
    payload: {
      title?: string;
      content?: string;
      enforcement?: "suggest" | "always";
      priority?: number;
      applies_to?: StackyDirectiveTargeting;
      expires_at?: string | null;
      review_after?: string | null;
    },
  ) => api.patch<{ ok: boolean }>(`/api/memory/${encodeURIComponent(memoryId)}`, payload),
  // Plan 26 M0.2 — preview de inyección para (project, agent_type, q).
  contextPreview: (params: { project: string; agent_type?: string | null; q?: string | null }) => {
    const qs = new URLSearchParams();
    qs.set("project", params.project);
    if (params.agent_type) qs.set("agent_type", params.agent_type);
    if (params.q) qs.set("q", params.q);
    return api.get<StackyMemoryContextPreview>(`/api/memory/context-preview?${qs.toString()}`);
  },
  // Plan 26 M3.2 — salud de directivas.
  directiveHealth: (project: string) =>
    api.get<StackyDirectiveHealth>(`/api/memory/directive-health?project=${encodeURIComponent(project)}`),
  // Plan 26 M2.2 — dry-run de targeting contra un ticket real.
  directivePreview: (payload: { applies_to: StackyDirectiveTargeting; ticket_id: number; agent_type?: string | null }) =>
    api.post<{ matches: boolean; reasons: string[] }>("/api/memory/directive-preview", payload),
  // Plan 26 M3.1 — tipos injectables vs reservados.
  types: () => api.get<StackyMemoryTypes>("/api/memory/types"),
};

// Plan 26 M0.2/M3.1 — flags del arnés (reusa el registry; fuente única).
export const HarnessFlags = {
  list: () => api.get<{ ok: boolean; flags: HarnessFlagView[]; active_profile: string | null; categories: HarnessFlagCategory[]; profile_deltas?: Record<string, number> }>("/api/harness-flags"),
  // Plan 83 [C3] — fetch directo (no api.put) para que el mensaje "fuera de rango
  // [..]" del 400 llegue LIMPIO (json.error), espejando applyProfile
  // (HarnessFlagsPanel.tsx). api.put/request() envuelve el texto crudo del body en
  // el Error, lo que ensucia el mensaje mostrado en apiError.
  update: (updates: Record<string, boolean | number | string>) =>
    fetch(`${apiBase}/api/harness-flags`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ updates }),
    }).then(async (r) => {
      const json = await r.json();
      if (!r.ok || !json.ok) throw new Error(json.error ?? `HTTP ${r.status}`);
      return json as { ok: boolean; applied?: Record<string, unknown>; error?: string; restart_required_keys?: string[] };
    }),
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

export interface StackyManifestAgent {
  name: string;
  mention: string;
  filename: string;
  path: string;
  relative_path: string;
  description: string;
  checksum_sha256: string;
  source: string;
}

export interface StackyManifestResponse {
  stacky_home: string;
  agents_dir: string;
  effective_agents_dir?: string;
  manifest_path: string;
  manifest: Record<string, unknown> | null;
  agents: StackyManifestAgent[];
  count: number;
}

// Plan 44 — Grounding Observatory
export interface GroundingObservatoryResponse {
  project: string;
  total_epics: number;
  epics_with_warnings: number;
  grounding_warning_rate: number;
  avg_confidence: number | null;
  top_cited_modules: Array<{ name: string; count: number }>;
  top_cited_processes: Array<{ name: string; count: number }>;
  confidence_trend: (number | null)[];
  runtime_coverage: string[];
}

export interface ProcessCatalogSuggestion {
  name: string;
  occurrences: number;
}

export interface ProcessCatalogSuggestionsResponse {
  project: string;
  suggestions: ProcessCatalogSuggestion[];
}

/** Plan 41 F4 — supuesto con evaluación de impacto. */
export interface IntentAssumptionDTO {
  text: string;
  impact: "high" | "medium" | "low";
  needs_confirmation: boolean;
}

/** Plan 41 F4 — intención descompuesta tras pre-vuelo. */
export interface IntentBriefDTO {
  objective: string;
  deliverables: string[];
  assumptions: IntentAssumptionDTO[];
  open_questions: string[];
  areas: string[];
  confidence: number;
  version: string;
}

export const Agents = {
  list: () => api.get<AgentDefinition[]>("/api/agents"),
  vsCodeAgents: () => api.get<VsCodeAgent[]>("/api/agents/vscode"),
  stackyManifest: () => api.get<StackyManifestResponse>("/api/agents/stacky/manifest"),
  stackyMaterialize: (force = false) =>
    api.post<{ ok: true; count: number; agents: StackyManifestAgent[] }>(
      "/api/agents/stacky/materialize",
      { force }
    ),
  history: (filename: string, limit = 50, project?: string | null) => {
    const p = new URLSearchParams({ limit: String(limit) });
    if (project) p.set("project", project);
    return api.get<AgentHistoryResponse>(
      `/api/agents/vscode/${encodeURIComponent(filename)}/history?${p.toString()}`
    );
  },
  // Plan 44 F4 — Observatorio pasivo de grounding de épicas
  groundingObservatory: (project?: string) => {
    const params = new URLSearchParams();
    if (project) params.set("project", project);
    const qs = params.toString();
    return api.get<GroundingObservatoryResponse>(
      `/api/agents/epics/grounding-observatory${qs ? `?${qs}` : ""}`
    );
  },
  // Plan 44 F4 — Sugeridor de procesos para el diccionario
  processCatalogSuggestions: (project: string) =>
    api.get<ProcessCatalogSuggestionsResponse>(
      `/api/agents/projects/${encodeURIComponent(project)}/process-catalog-suggestions`
    ),
  run: (payload: {
    agent_type: AgentType;
    ticket_id: number;
    context_blocks: ContextBlock[];
    chain_from?: number[];
    project?: string;
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
    project?: string;
    model_override?: string | null;
    system_prompt_override?: string | null;
    use_few_shot?: boolean;
    use_anti_patterns?: boolean;
    fingerprint_complexity?: string | null;
    /** Runtime de ejecución: github_copilot | codex_cli | claude_code_cli */
    runtime?: import("../types").AgentRuntime;
    /**
     * Requerido cuando runtime=codex_cli. Nombre del archivo .agent.md del
     * agente VS Code seleccionado (ej: "DevPacifico.agent.md"). El backend
     * devuelve HTTP 400 con error=missing_vscode_agent_filename si se omite.
     */
    vscode_agent_filename?: string;
  }) => api.post<{ execution_id: number; status: string }>("/api/agents/run", payload),
  openChat: (payload: {
    ticket_id: number;
    context_blocks: ContextBlock[];
    project?: string;
    vscode_agent_filename?: string;
    model_override?: string | null;
  }) => api.post<{ ok: boolean }>("/api/agents/open-chat", payload),
  /** Plan 38 B2 / Plan 42 F3 — Lanza el BusinessAgent con un brief (sin ticket real). */
  runBrief: (payload: {
    brief: string;
    runtime?: import("../types").AgentRuntime;
    project?: string | null;
    vscode_agent_filename?: string;
    /** Plan 42 F3 — modelo override (solo claude_code_cli); se clampea a sonnet-4-6 en backend. */
    model?: string | null;
    /** Plan 42 F3 / Plan 43 F0 — esfuerzo del run (default "high"). */
    effort?: "low" | "medium" | "high" | "xhigh" | "max";
    /** Plan 45 F3 — tipo de work item a crear (Epic | Issue). */
    work_item_type?: "Epic" | "Issue";
    /** Plan 41 F4 — pre-vuelo de intención. */
    preflight?: boolean;
    /** Plan 41 F4 — aprobación de intención tras pre-vuelo. */
    approved?: boolean;
    /** Plan 41 F4 — correcciones sugeridas por el operador. */
    corrections?: string;
  }) => api.post<{
    execution_id?: number;
    status?: string;
    stage?: "preflight" | "running";
    intent?: IntentBriefDTO;
    auto_approvable?: boolean;
  }>("/api/agents/run-brief", payload),
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
        format?: "raw" | "teams";
        created_at: string; last_fired_at: string | null; last_status: string | null;
        last_error: string | null; fires: number }[]
    >("/api/webhooks"),
  create: (payload: { url: string; event?: string; project?: string; secret?: string; format?: "raw" | "teams" }) =>
    api.post<{ id: number }>("/api/webhooks", payload),
  deactivate: (id: number) => api.delete<{ ok: true }>(`/api/webhooks/${id}`),
};

export interface ExecutionOutputFile {
  name: string;
  rel_path: string;
  size: number;
  modified: number;
}

export interface ExecutionOutputFilesResponse {
  files: ExecutionOutputFile[];
  dir: string | null;
}

/** Plan 39 A1 — Item del historial de ejecuciones. */
// Plan 117 — insight local anotado en metadata_json de la ejecución.
export interface ExecutionLocalInsight {
  state: "done" | "failed";
  tldr?: string;
  labels?: string[];
  risk?: "low" | "medium" | "high";
  probable_cause?: string | null;
  evidence?: string | null;
  next_step?: string | null;
  model?: string;
  generated_at?: string;
  attempts?: number;
  error?: string;
}

export interface ExecutionHistoryItem {
  id: number;
  ticket_id: number;
  ticket_title: string | null;
  agent_type: string;
  agent_name: string | null;
  runtime: string | null;
  model: string | null;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  cost_usd: number | null;
  tokens_in: number | null;
  tokens_out: number | null;
  prompt_sha: string | null;
  prompt_len: number | null;
  has_prompt_text: boolean;
  produced_files_count: number;
  error_message: string | null;
  local_insight?: ExecutionLocalInsight | null; // Plan 117
}

export const Executions = {
  list: (q: {
    ticket_id?: number;
    agent_type?: AgentType;
    agent_filename?: string;
    status?: string | string[];
    project?: string | null;
    /** Ignorar el filtro de proyecto y traer ejecuciones de todos los proyectos. */
    all_projects?: boolean;
    include_output?: boolean;
    limit?: number;
    days?: number;
  }) => {
    const params = new URLSearchParams();
    if (q.ticket_id) params.set("ticket_id", String(q.ticket_id));
    if (q.agent_type) params.set("agent_type", q.agent_type);
    if (q.agent_filename) params.set("agent_filename", q.agent_filename);
    if (Array.isArray(q.status)) {
      for (const status of q.status) {
        params.append("status", status);
      }
    } else if (q.status) {
      params.set("status", q.status);
    }
    if (q.project) params.set("project", q.project);
    if (q.all_projects) params.set("all_projects", "true");
    if (q.include_output) params.set("include_output", "true");
    if (q.limit) params.set("limit", String(q.limit));
    if (q.days) params.set("days", String(q.days));
    const qs = params.toString();
    return api.get<AgentExecution[]>(`/api/executions${qs ? `?${qs}` : ""}`);
  },
  byId: (id: number) => api.get<AgentExecution>(`/api/executions/${id}`),
  approve: (id: number) => api.post<AgentExecution>(`/api/executions/${id}/approve`),
  discard: (id: number) => api.post<AgentExecution>(`/api/executions/${id}/discard`),
  humanReview: (id: number, body: { verdict: "approved" | "rejected" | "approved_with_notes"; note?: string }) =>
    api.post<AgentExecution>(`/api/executions/${id}/human-review`, body),
  publish: (id: number, target: "comment" | "task" = "comment") =>
    api.post<{ ok: true; ado_url: string }>(`/api/executions/${id}/publish-to-ado`, { target }),
  sendCodexInput: (id: number, text: string) =>
    api.post<{ ok: boolean; mode: "stdin" | "resume"; execution_id: number; session_id?: string }>(
      `/api/executions/${id}/input`,
      { text }
    ),
  cancel: (id: number) =>
    api.post<{ ok: boolean; execution_id: number }>(`/api/executions/${id}/cancel`),
  diff: (a: number, b: number) =>
    api.get<{ left: AgentExecution; right: AgentExecution }>(
      `/api/executions/${a}/diff/${b}`
    ),
  streamUrl: (id: number) => `${apiBase}/api/executions/${id}/logs/stream`,
  outputFiles: (id: number) =>
    api.get<ExecutionOutputFilesResponse>(`/api/executions/${id}/output-files`),
  // P2.3 — endpoints portados de WS2
  forceTransition: (id: number) =>
    api.post<{ ok: boolean; logs?: string[]; error?: string }>(`/api/executions/${id}/force-transition`),
  reattach: (id: number) =>
    api.post<{ ok: boolean; message?: string; tracker?: string; out_prefix?: string; dir?: string; error?: string }>(
      `/api/executions/${id}/reattach`
    ),
  deleteOne: (id: number) =>
    api.delete<{ ok: boolean; deleted_id: number }>(`/api/executions/${id}`),
  deleteByTicket: (ticketId: number, agentFilename: string) =>
    api.delete<{ ok: boolean; deleted: number[]; skipped: number[] }>(
      `/api/executions/bulk-by-ticket?ticket_id=${ticketId}&agent_filename=${encodeURIComponent(agentFilename)}`
    ),
  /** Plan 39 A1 — Historial completo de ejecuciones con métricas del arnés. */
  history: (q: {
    project?: string;
    agent_type?: string;
    runtime?: string;
    status?: string;
    days?: number;
    limit?: number;
    offset?: number;
  } = {}) => {
    const params = new URLSearchParams();
    if (q.project) params.set("project", q.project);
    if (q.agent_type) params.set("agent_type", q.agent_type);
    if (q.runtime) params.set("runtime", q.runtime);
    if (q.status) params.set("status", q.status);
    if (q.days) params.set("days", String(q.days));
    if (q.limit) params.set("limit", String(q.limit));
    if (q.offset) params.set("offset", String(q.offset));
    const qs = params.toString();
    return api.get<ExecutionHistoryItem[]>(`/api/executions/history${qs ? `?${qs}` : ""}`);
  },
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

// QaUat namespace — see full definition below (Sprint 9+)

// Feature C: Comparador de Agentes
export interface AgentComparisonEntry {
  filename: string;
  agent_type: string;
  total_runs: number;
  approved_count: number;
  discarded_count: number;
  error_count: number;
  cancelled_count: number;
  approval_rate: number;
  avg_duration_ms: number | null;
  p95_duration_ms: number | null;
  tickets_completed: number;
  low_sample_warning: boolean;
  is_best?: boolean;
}

export interface AgentComparisonResponse {
  ok: boolean;
  generated_at: string;
  period_days: number;
  agent_type: string | null;
  agents: AgentComparisonEntry[];
  total_executions: number;
}

export const Metrics = {
  agentComparison: (params?: { days?: number; agent_type?: string }) => {
    const p = new URLSearchParams();
    if (params?.days) p.set("days", String(params.days));
    if (params?.agent_type) p.set("agent_type", params.agent_type);
    const qs = p.toString();
    return api.get<AgentComparisonResponse>(`/api/metrics/agent-comparison${qs ? `?${qs}` : ""}`);
  },
};

// U1.5 — Digest de valor para management (doc 23)
export interface DigestTotals {
  runs: number;
  completed: number;
  needs_review: number;
  error: number;
  success_rate: number;
  tickets_touched: number;
  cost_usd: { reported: number; estimated: number; total: number };
}

export interface DigestGroupRow {
  name: string;
  runs: number;
  completed: number;
  needs_review: number;
  error: number;
  success_rate: number;
}

export interface DigestReport {
  period: { days: number; start: string; end: string };
  totals: DigestTotals;
  by_agent_type: DigestGroupRow[];
  by_runtime: DigestGroupRow[];
  top_failures: { kind: string; count: number }[];
  highlights: string[];
  partial: boolean;
  narrative?: string | null; // Plan 117 (solo con ?narrate=1)
  narrative_error?: string | null; // Plan 117
}

export const Reports = {
  /** Digest en JSON para el preview de la card (fmt=json es el default del backend). */
  digest: (params?: { days?: number; project?: string; narrate?: boolean }) => {
    const p = new URLSearchParams();
    if (params?.days) p.set("days", String(params.days));
    if (params?.project) p.set("project", params.project);
    if (params?.narrate) p.set("narrate", "1"); // Plan 117 — narrativa local opt-in
    const qs = p.toString();
    return api.get<DigestReport>(`/api/reports/digest${qs ? `?${qs}` : ""}`);
  },
  /** URL de descarga directa (Content-Disposition attachment lo maneja el backend). */
  digestDownloadUrl: (params: { fmt: "md" | "html"; days?: number; project?: string }) => {
    const p = new URLSearchParams();
    p.set("fmt", params.fmt);
    if (params.days) p.set("days", String(params.days));
    if (params.project) p.set("project", params.project);
    return `${apiBase}/api/reports/digest?${p.toString()}`;
  },
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
  testDocsPaths: (name: string, payload: Partial<InitProjectPayload>) =>
    api.post<{
      ok: boolean;
      docs_paths: { technical: string; functional: string };
      counts: Record<"technical" | "functional", {
        path: string;
        exists: boolean;
        readable: boolean;
        md: number;
        pdf: number;
        total: number;
        error?: string;
      }>;
      error?: string;
    }>(`/api/projects/${name}/test_docs_paths`, payload),
  browseFolder: (payload?: { title?: string; initial_dir?: string }) =>
    api.post<{ ok: boolean; path: string; error?: string }>("/api/browse_folder", payload ?? {}),
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
  vscodeStatus: (name: string) =>
    api.get<{ ok: boolean; port: number | null; ready: boolean; workspace_root: string | null; project_name: string }>(`/api/projects/${name}/vscode-status`),
  trackerStates: (name: string) =>
    api.get<{ ok: boolean; states: string[]; tracker_type: string }>(`/api/projects/${name}/tracker-states`),
  getAgentWorkflow: (projectName: string, filename: string) =>
    api.get<AgentWorkflowConfig & { ok: boolean }>(`/api/projects/${projectName}/agent-workflow/${encodeURIComponent(filename)}`),
  getAllAgentWorkflows: (projectName: string) =>
    api.get<{ ok: boolean; workflows: Record<string, AgentWorkflowConfig> }>(`/api/projects/${encodeURIComponent(projectName)}/agent-workflows`),
  putAgentWorkflow: (projectName: string, filename: string, workflow: Partial<AgentWorkflowConfig>) =>
    api.put<AgentWorkflowConfig & { ok: boolean }>(`/api/projects/${projectName}/agent-workflow/${encodeURIComponent(filename)}`, workflow),
  // P1.1 ChatDrawer: bootstrap del workspace_root del proyecto activo
  agentBootstrap: () =>
    api.get<{ ok: boolean; project_name: string; tracker_type: string; workspace_root: string; auth_header: string; tracker: Record<string, string> }>("/api/agent_bootstrap"),
};

// ── Requerimiento A (plan 2026-05-27): export/import de configuración ─────────

export interface ConfigBundle {
  meta: {
    schemaVersion: number;
    appVersion?: string;
    projectId?: string;
    scope?: string;
    activeProject?: string | null;
    projectCount?: number;
    exportedAt?: string;
    checksum?: string;
    sections?: string[];
  };
  [section: string]: unknown;
}

export interface ConfigValidation {
  ok: boolean;
  schema_version: number | null;
  app_version: string | null;
  project_id: string | null;
  checksum_ok: boolean;
  errors: string[];
  warnings: string[];
  migration_notes: string[];
}

export interface ConfigChange {
  section: string;
  field: string;
  action: "add" | "update" | "remove";
  old: unknown;
  new: unknown;
}

export interface ConfigSecretRequired {
  tracker_type?: string;
  auth_file: string;
  fields: string[];
}

export interface ConfigImportResult {
  ok: boolean;
  mode: "dry-run" | "merge" | "overwrite";
  applied?: boolean;
  idempotent?: boolean;
  changes?: ConfigChange[];
  secrets_required?: ConfigSecretRequired[];
  projects?: Array<{
    project: string;
    applied?: boolean;
    idempotent?: boolean;
    changes?: ConfigChange[];
    secrets_required?: ConfigSecretRequired[];
  }>;
  validation?: ConfigValidation;
  error?: string;
}

export interface ConfigTransferEvent {
  ts: string;
  action: string;
  project: string;
  result: string;
  actor: string;
  schema_version: number | null;
  app_version: string | null;
  mode: string | null;
  checksum: string | null;
  sections: string[];
  detail: Record<string, unknown>;
}

// ── Client Profile (plan 16 — generalización multi-cliente) ──────────────────

export interface ClientProfileTrackerRole {
  input_states?: string[];
  in_progress?: string;
  blocked_state?: string;
  next_state_ok?: string;
}

export interface ClientProfile {
  schema_version: number;
  code_layout?: Record<string, unknown>;
  language?: Record<string, unknown>;
  database?: Record<string, unknown>;
  build?: Record<string, unknown>;
  conventions?: Record<string, unknown>;
  docs_indexes?: Record<string, unknown>;
  terminology?: Record<string, unknown>;
  tracker_state_machine?: {
    functional?: ClientProfileTrackerRole;
    technical?: ClientProfileTrackerRole;
    developer?: ClientProfileTrackerRole;
  };
  extensions?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface ClientProfileValidation {
  ok: boolean;
  errors: string[];
  warnings: string[];
  normalized: ClientProfile | null;
}

export interface ClientProfilePathCheck {
  section: string;
  key: string;
  rel: string;
  abs: string;
  exists: boolean;
}

export interface ClientProfileGetResponse {
  ok: boolean;
  project: string;
  tracker_type: string;
  has_profile: boolean;
  profile: ClientProfile | null;
  default_template: ClientProfile;
  prefilled_profile?: ClientProfile;
  path_check?: ClientProfilePathCheck[];
  validation: ClientProfileValidation | null;
  error?: string;
}

export interface ClientProfileStateWarning {
  agent_type: string;
  field: "in_progress" | "next_state_ok";
  value: string;
  reason: string;
}

export interface ClientProfileSaveResponse {
  ok: boolean;
  profile?: ClientProfile;
  warnings?: string[];
  state_warnings?: ClientProfileStateWarning[];
  error?: string;
}

export interface DbReadonlyAuthMeta {
  ok: boolean;
  has_credentials: boolean;
  server?: string;
  database?: string;
  user?: string;
  warning?: string;
  error?: string;
}

export const ClientProfileApi = {
  get: (project: string) =>
    api.get<ClientProfileGetResponse>(
      `/api/projects/${encodeURIComponent(project)}/client-profile`
    ),
  save: (project: string, profile: ClientProfile) =>
    api.put<ClientProfileSaveResponse>(
      `/api/projects/${encodeURIComponent(project)}/client-profile`,
      { profile }
    ),
  clear: (project: string) =>
    api.delete<{ ok: boolean; cleared: boolean; error?: string }>(
      `/api/projects/${encodeURIComponent(project)}/client-profile`
    ),
  defaultTemplate: (trackerType: string) =>
    api.get<{ ok: boolean; tracker_type: string; template: ClientProfile }>(
      `/api/client-profile/default?tracker_type=${encodeURIComponent(trackerType)}`
    ),
};

export const DbReadonlyAuth = {
  meta: (project: string) =>
    api.get<DbReadonlyAuthMeta>(
      `/api/projects/${encodeURIComponent(project)}/db-readonly-auth`
    ),
  save: (
    project: string,
    payload: { server?: string; database?: string; user?: string; password: string }
  ) =>
    api.post<{ ok: boolean; auth_file?: string; saved_fields?: string[]; error?: string }>(
      `/api/projects/${encodeURIComponent(project)}/db-readonly-auth`,
      payload
    ),
};

export const ConfigTransfer = {
  sections: () => api.get<{ ok: boolean; sections: string[] }>("/api/config/sections"),
  exportAll: (sections?: string[]) =>
    api.post<{ ok: boolean; bundle: ConfigBundle; filename: string; error?: string }>(
      "/api/config/export",
      sections ? { sections } : {}
    ),
  importAll: (bundle: ConfigBundle, mode: "dry-run" | "merge" | "overwrite") =>
    api.post<ConfigImportResult>(`/api/config/import?mode=${mode}`, { bundle }),
  export: (project: string, sections?: string[]) =>
    api.post<{ ok: boolean; bundle: ConfigBundle; filename: string; error?: string }>(
      `/api/projects/${encodeURIComponent(project)}/config/export`,
      sections ? { sections } : {}
    ),
  import: (project: string, bundle: ConfigBundle, mode: "dry-run" | "merge" | "overwrite") =>
    api.post<ConfigImportResult>(
      `/api/projects/${encodeURIComponent(project)}/config/import?mode=${mode}`,
      { bundle }
    ),
  events: (project: string, limit = 100) =>
    api.get<{ ok: boolean; events: ConfigTransferEvent[] }>(
      `/api/projects/${encodeURIComponent(project)}/config/transfer-events?limit=${limit}`
    ),
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

// ── Claude Code CLI — configuración y autenticación ──────────────────────────

export interface ClaudeTestResult {
  ok: boolean;
  bin: string;
  version?: string;
  error?: string;
}

export interface ClaudeSessionStatus {
  exists: boolean;
  bin: string;
  logged_in: boolean;
  auth_method?: string | null;
  email?: string | null;
  org_name?: string | null;
  subscription_type?: string | null;
  error?: string;
}

export const ClaudeCli = {
  /** Verifica el binario `claude` y devuelve la versión. */
  test: (claudeBin?: string) =>
    api.post<ClaudeTestResult>("/api/global-config/test-claude", {
      claude_bin: claudeBin ?? "",
    }),
  /** Estado de autenticación (claude auth status --json). */
  session: () => api.get<ClaudeSessionStatus>("/api/global-config/claude-session"),
  /** Lanza `claude auth login` (OAuth en navegador). Puede tardar. */
  login: (claudeBin?: string) =>
    api.post<{ ok: boolean; output?: string; error?: string }>(
      "/api/global-config/claude-login",
      { claude_bin: claudeBin ?? "" }
    ),
  /** Cierra la sesión (claude auth logout). */
  logout: () =>
    api.delete<{ ok: boolean; note?: string; error?: string }>(
      "/api/global-config/claude-session"
    ),
  /** Persiste la ruta del binario y el modelo por defecto en el .env del backend. */
  saveConfig: (cfg: { CLAUDE_CODE_CLI_BIN?: string; CLAUDE_CODE_CLI_MODEL?: string }) =>
    api.put<{ ok: boolean }>("/api/global-config", cfg),
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

export interface QaBrowserUsedSource {
  kind?: string | null;
  title?: string | null;
  source_id?: string | number | null;
  confidence?: number | null;
  reason?: string | null;
}

export interface QaBrowserRunSpec {
  schema_version?: string;
  created_at?: string;
  scenarios: Array<Record<string, unknown>>;
  plan_source: {
    used_sources: QaBrowserUsedSource[];
    candidate_count?: number;
    source_policy?: string;
  };
  ticket?: Record<string, unknown>;
  context_stats?: Record<string, unknown>;
  runner_contract?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface QaBrowserRunResponse {
  ok: boolean;
  execution_id: number;
  ticket_id: number;
  ado_id: number;
  spec: QaBrowserRunSpec;
  runner_prompt: string;
  stream_url: string;
  status: "queued" | "running";
}

export interface QaBrowserStartPayload {
  ticket_id: number;
  allowed_base_url: string;
  operator_note?: string;
  max_scenarios?: number;
  auto_start?: boolean;
  model_override?: string | null;
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

export const QaBrowser = {
  startRun: (payload: QaBrowserStartPayload) =>
    api.post<QaBrowserRunResponse>("/api/qa-browser/runs", payload),
};

// ── Operación local: diagnóstico, logs rotativos y backup ───────────────────

export type LocalDiagnosticStatus = "ok" | "warning" | "error";

export interface LocalDiagnosticCheck {
  id: string;
  label: string;
  status: LocalDiagnosticStatus;
  message: string;
  detail?: unknown;
}

export interface LocalDiagnosticsResponse {
  ok: boolean;
  checked_at: string;
  duration_ms: number;
  summary: Record<LocalDiagnosticStatus, number>;
  checks: LocalDiagnosticCheck[];
  logs: {
    directory: string;
    recent_files: string[];
  };
  backups: {
    path: string;
    filename: string;
    size_bytes: number;
    created_at: string;
  }[];
}

export interface BackupRunResponse {
  ok: boolean;
  skipped: boolean;
  reason: string | null;
  backup_path: string | null;
}

export const LocalDiagnostics = {
  get: (): Promise<LocalDiagnosticsResponse> =>
    api.get<LocalDiagnosticsResponse>("/api/diag/local"),

  runBackup: (): Promise<BackupRunResponse> =>
    api.post<BackupRunResponse>("/api/diag/backup/run", {}),

  exportLogsUrl: () => `${apiBase}/api/diag/logs/export`,
};

// ── Plan 46 F3 — Operational Health (Panel de Salud Operativa) ──────────────
export interface OperationalHealthRow {
  id: number;
  ticket_id: number | null;
  agent_type: string;
  runtime: string;
  project: string | null;
  started_at: string | null;
  status: string;
  age_days?: number;
  stale?: boolean;
  failure_kind?: string | null;
  error_message?: string | null;
  cost_usd?: number | null;
  model?: string | null;
  age_minutes?: number;
}

export interface OperationalHealthSummary {
  needs_review_pending: number;
  needs_review_stale: number;
  failed: number;
  expensive: number;
  zombie: number;
  scanned: number;
}

export interface OperationalHealthReport {
  ok: boolean;
  generated_at: string;
  thresholds: Record<string, unknown>;
  summary: OperationalHealthSummary;
  needs_review: OperationalHealthRow[];
  failed: OperationalHealthRow[];
  expensive: OperationalHealthRow[];
  zombie: OperationalHealthRow[];
  expensive_cost_by_model: Record<string, number>;
  expensive_cost_by_runtime: Record<string, number>;
}

export const OperationalHealth = {
  get: (): Promise<OperationalHealthReport> =>
    api.get<OperationalHealthReport>("/api/diag/operational-health"),
};

// ── Plan 38 A2 — Health endpoint ─────────────────────────────────────────────
export const Health = {
  get: (): Promise<{ version?: string; ok?: boolean; healthy?: boolean }> =>
    api.get<{ version?: string; ok?: boolean; healthy?: boolean }>("/api/diag/health"),
};

// ── Feature #3: Docs — árbol de documentación ────────────────────────────────

export interface DocHeading {
  level: 1 | 2;
  text: string;
  anchor: string;
}

export interface DocNode {
  id: string;
  kind?: "file" | "folder";
  label: string;
  path: string;
  display_path?: string;
  source_id?: string;
  size_bytes: number;
  headings: DocHeading[];
  children?: DocNode[];
  /** Presente solo en la sección "agents" cuando _absolute_path está disponible en el servidor. */
  _absolute_path?: string;
}

export interface DocRoot {
  id: "technical-docs" | "agents" | "roadmaps" | "project-docs";
  label: string;
  path?: string;
  display_path?: string;
  source_id?: string;
  children: DocNode[];
  /** Nota informativa cuando la sección está vacía por configuración. */
  note?: string;
}

export interface DocSource {
  id: string;
  kind: "stacky" | "project-docs";
  label: string;
  relative_path: string;
  display_prefix?: string;
  absolute_path?: string;
  project?: string | null;
  workspace_root?: string | null;
  configured?: boolean;
  docs_path_kind?: "technical" | "functional";
  available?: boolean;
}

export interface DocsSourcesResponse {
  ok: boolean;
  active_project: string | null;
  project_display_name?: string | null;
  workspace_root?: string | null;
  default_source_id: string;
  sources: DocSource[];
  note?: string | null;
  /** Plan 109 — true si STACKY_DOCS_GRAPH_ENABLED está ON (gatea la pestaña Cobertura). */
  graph_enabled?: boolean;
  /** Plan 113 — true si STACKY_DOCS_DOCUMENTER_ENABLED está ON (gatea el botón Documentador). */
  documenter_enabled?: boolean;
  /** Plan 114 — true si STACKY_DOCS_STALENESS_ENABLED está ON (gatea chip + acción de staleness). */
  staleness_enabled?: boolean;
}

/** Plan 113 — salud documental recomputada (subset de doc_health). */
export interface DocumenterHealth {
  status: string;
  frontmatter_ratio?: number;
  wikilink_edges?: number;
  uncovered_modules?: string[];
}

/** Plan 113 — estado de un run del Documentador. */
export interface DocumenterStatusResponse {
  ok: boolean;
  run_id?: string;
  state?: string;
  current_mode?: string | null;
  written?: string[];
  skipped?: [string, string][];
  health_before?: DocumenterHealth | null;
  health_after?: DocumenterHealth | null;
  branch?: string | null;
  degraded?: boolean;
  diff_stat?: string;
  reason?: string;
  error?: string | null;
}

export interface DocsIndexResponse {
  ok: boolean;
  indexed_at: string;
  source_id?: string;
  active_project?: string | null;
  workspace_root?: string | null;
  roots: DocRoot[];
}

export interface DocsContentResponse {
  ok: boolean;
  path: string;
  source_id?: string;
  content: string;
  encoding: string;
}

export const Docs = {
  /** Devuelve las fuentes de documentación disponibles para el proyecto activo. */
  getSources: (project?: string): Promise<DocsSourcesResponse> => {
    const qs = project ? `?project=${encodeURIComponent(project)}` : "";
    return api.get<DocsSourcesResponse>(`/api/docs/sources${qs}`);
  },

  /** Devuelve el árbol completo de documentos indexados. */
  getIndex: (params?: { project?: string; sourceId?: string }): Promise<DocsIndexResponse> => {
    const query = new URLSearchParams();
    if (params?.project) query.set("project", params.project);
    if (params?.sourceId) query.set("source_id", params.sourceId);
    const qs = query.toString();
    return api.get<DocsIndexResponse>(`/api/docs/index${qs ? `?${qs}` : ""}`);
  },

  /** Devuelve el contenido raw de un documento por su path relativo. */
  getContent: (
    path: string,
    params?: { project?: string; sourceId?: string }
  ): Promise<DocsContentResponse> => {
    const query = new URLSearchParams({ path });
    if (params?.project) query.set("project", params.project);
    if (params?.sourceId) query.set("source_id", params.sourceId);
    return api.get<DocsContentResponse>(`/api/docs/content?${query.toString()}`);
  },

  /** Plan 109 — grafo documental read-only. 404 si la flag está OFF.
   *  opts.refresh=true fuerza re-scan del backend (query param refresh=1). */
  getGraph: (
    project?: string,
    opts?: { refresh?: boolean }
  ): Promise<DocGraphResponse> => {
    const query = new URLSearchParams();
    if (project) query.set("project", project);
    if (opts?.refresh) query.set("refresh", "1");
    const qs = query.toString();
    return api.get<DocGraphResponse>(`/api/docs/graph${qs ? `?${qs}` : ""}`);
  },

  /** Plan 113 — lanza el Documentador 1-click en background. 404 si la flag OFF, 409 si busy. */
  documenterRun: (project?: string): Promise<{ ok: boolean; run_id?: string; error?: string }> =>
    api.post<{ ok: boolean; run_id?: string; error?: string }>(
      `/api/docs/documenter/run`,
      project ? { project } : {}
    ),

  /** Plan 113 — estado del run del Documentador. */
  documenterStatus: (runId: string): Promise<DocumenterStatusResponse> =>
    api.get<DocumenterStatusResponse>(`/api/docs/documenter/status?run=${encodeURIComponent(runId)}`),

  /** Plan 113 — conserva (keep) o descarta (discard) la rama del run. */
  documenterDecide: (
    runId: string,
    action: "keep" | "discard"
  ): Promise<{ ok: boolean; action?: string; branch?: string; error?: string }> =>
    api.post<{ ok: boolean; action?: string; branch?: string; error?: string }>(
      `/api/docs/documenter/decide`,
      { run: runId, action }
    ),

  /** Plan 114 — encola el Documentador (113) en modo ACTUALIZAR acotado a una nota.
   *  404 si staleness o documenter OFF; 409 si ya hay un run activo. */
  stalenessFix: (
    notePath: string,
    project?: string
  ): Promise<{ ok: boolean; run_id?: string; error?: string }> =>
    api.post<{ ok: boolean; run_id?: string; error?: string }>(
      `/api/docs/staleness/fix`,
      project ? { note_path: notePath, project } : { note_path: notePath }
    ),
};

// ── Feature #4: FlowConfig — mapeo determinístico ado_state → agent_type ─────

export interface FlowConfigRule {
  id: string;
  ado_state: string;
  agent_type: string;
  created_at: string;
  updated_at: string;
}

export interface FlowConfigListResponse {
  ok: boolean;
  rules: FlowConfigRule[];
}

export interface FlowConfigResolveResponse {
  ok: boolean;
  found: boolean;
  ado_state: string;
  agent_type: string | null;
}

export const FlowConfig = {
  list: (project?: string | null): Promise<FlowConfigListResponse> =>
    api.get<FlowConfigListResponse>(`/api/flow-config${project ? `?project=${encodeURIComponent(project)}` : ""}`),

  create: (body: { ado_state: string; agent_type: string; project?: string | null }): Promise<FlowConfigRule> =>
    api.post<FlowConfigRule>("/api/flow-config", body),

  update: (id: string, body: { ado_state?: string; agent_type?: string; project?: string | null }): Promise<FlowConfigRule> =>
    api.put<FlowConfigRule>(`/api/flow-config/${id}`, body),

  delete: (id: string, project?: string | null): Promise<{ ok: boolean }> =>
    api.delete<{ ok: boolean }>(`/api/flow-config/${id}${project ? `?project=${encodeURIComponent(project)}` : ""}`),

  resolve: (adoState: string, project?: string | null): Promise<FlowConfigResolveResponse> =>
    api.get<FlowConfigResolveResponse>(
      `/api/flow-config/resolve?ado_state=${encodeURIComponent(adoState)}${project ? `&project=${encodeURIComponent(project)}` : ""}`
    ),
};

// ── UI Sections — visibilidad de pestañas opcionales (pm / logs / docs) ─────

export interface UiSectionsState {
  [section: string]: { visible: boolean };
}

export interface UiSectionsResponse {
  ok: boolean;
  sections: UiSectionsState;
}

export const UiSections = {
  list: (): Promise<UiSectionsResponse> =>
    api.get<UiSectionsResponse>("/api/ui-sections"),

  set: (section: string, visible: boolean): Promise<UiSectionsResponse> =>
    api.put<UiSectionsResponse>(`/api/ui-sections/${encodeURIComponent(section)}`, { visible }),
};

// ── P4: Gateway de finalización de agentes (recuperación de inconsistencias) ──

export interface AgentCompletionPayload {
  execution_id: number;
  agent_type: string;
  status: "completed";
  html_output_path?: string | null;
  metadata?: Record<string, unknown>;
  reason: string;
  force?: boolean;
}

export interface AgentCompletionSuccess {
  ok: true;
  result: string;          // ej. "agent_completed", "idempotent_replay"
  execution_id: number;
  publish_id?: number | null;
  correlation_id?: string;
}

/**
 * Gateway de finalización de agentes.
 *
 * Llama a POST /api/tickets/by-ado/{ado_id}/agent-completion.
 *
 * Devuelve RawResponse en vez de lanzar excepción para que el caller
 * pueda diferenciar 409 html_already_published → diálogo force=true
 * de otros errores → toast de error.
 *
 * Auth: X-Stacky-Agent-Token leído desde import.meta.env.VITE_STACKY_AGENT_TOKEN.
 * Si no está configurado, se envía cadena vacía (el backend responderá 401).
 */
export const AgentCompletion = {
  complete: (
    adoId: number,
    payload: AgentCompletionPayload
  ): Promise<RawResponse<AgentCompletionSuccess>> => {
    const token =
      (import.meta as any).env?.VITE_STACKY_AGENT_TOKEN ?? "";
    return rawPost<AgentCompletionSuccess>(
      `/api/tickets/by-ado/${adoId}/agent-completion`,
      payload,
      token ? { "X-Stacky-Agent-Token": token } : {}
    );
  },
};

// ── P2.1 Agent Roles (portado de WS2, Sprint 3) ──────────────────────────────
// Soporta AgentConfigModal.tsx — flags stacky/utilitario/vscode por agente.
export interface AgentRoleEntry {
  stacky: boolean;
  utilitario: boolean;
  vscode: boolean;
  name?: string;
  description?: string;
}

export const AgentRoles = {
  list: () =>
    api.get<{ ok: boolean; roles: Record<string, AgentRoleEntry> }>("/api/agent-roles"),
  update: (patch: Record<string, Partial<Omit<AgentRoleEntry, "name" | "description">>>) =>
    api.put<{ ok: boolean }>("/api/agent-roles", patch),
};

// ── P1.1/P1.2 Chat libre + Docs RAG (portado desde WS2, Sprint 4) ─────────────

export interface ChatTurnMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface ChatToolLog {
  tool: string;
  args: string;
  output: string;
  ok: boolean;
}

export interface ChatTurnResponse {
  ok: boolean;
  text: string;
  tool_log: ChatToolLog[];
  turns: number;
  model_used: string;
  logs: string[];
  error?: string;
}

export const Chat = {
  turn: (payload: {
    agent_filename: string;
    model: string | null;
    messages: ChatTurnMessage[];
    workspace_dir?: string | null;
    runtime?: string | null;
    project_name?: string | null;
  }) => api.post<ChatTurnResponse>("/api/chat/turn", payload),
};

export interface DocsRagSource {
  file_path: string;
  section: string;
  score: number;
}

export interface DocsRagChatResponse {
  ok: boolean;
  text: string;
  sources: DocsRagSource[];
  chunks_used: number;
  model_used: string;
  logs: string[];
  error?: string;
}

export interface DocsRagIndexResponse {
  ok: boolean;
  project_name: string;
  chunks_indexed: number;
  files_scanned: number;
  warning?: string;
  error?: string;
}

export interface DocsRagStatsResponse {
  ok: boolean;
  project_name: string;
  chunks: number;
  files: number;
  last_indexed: string | null;
}

export const DocsRag = {
  index: (payload: { project_name?: string; docs_subpath?: string }) =>
    api.post<DocsRagIndexResponse>("/api/docs-rag/index", payload),

  stats: (projectName?: string) =>
    api.get<DocsRagStatsResponse>(
      `/api/docs-rag/stats${projectName ? `?project_name=${encodeURIComponent(projectName)}` : ""}`
    ),

  chat: (payload: {
    messages: ChatTurnMessage[];
    project_name?: string;
    agent_filename?: string;
    model?: string | null;
    top_k?: number;
    workspace_dir?: string | null;
  }) => api.post<DocsRagChatResponse>("/api/docs-rag/chat", payload),
};

// Feature A: Sprint Board
export const PM = {
  sprintBoard: (project?: string) => {
    const qs = project ? `?project=${encodeURIComponent(project)}` : "";
    return api.get<{
      ok: boolean;
      sprint: {
        id: string; name: string; path: string;
        start: string | null; end: string | null; time_frame: string | null;
      } | null;
      groups: Record<string, {
        ado_id: number; title: string; state: string; work_item_type: string;
        priority: number | null; story_points: number; assigned_to: string | null;
        assigned_unique_name: string | null; tags: string[]; days_in_state: number | null;
      }[]>;
      totals: {
        story_points_committed: number;
        story_points_done: number;
        items_total: number;
        items_done: number;
      };
      stale_warning: boolean;
      message?: string;
    }>(`/api/pm/sprint/board${qs}`);
  },
};

// ── Plan 72 — CI Trigger & Monitor ────────────────────────────────────────

export interface CITriggerResponse {
  id: string;
  status: string;
  ref: string;
  sha: string;
  web_url: string;
  pipeline_id?: string;
  message?: string;
}

export interface CIPreviewResponse {
  kind: "branch" | "sha" | "tag";
  ref: string;
  last_pipeline: { id: string; status: string; sha: string; ref: string; web_url?: string } | null;
  would_reuse: boolean;
  existing_pipeline_id: string | null;
}

export interface CIMonitorResponse {
  id: string;
  status: string;
  ref: string;
  sha: string;
  web_url: string;
  tracker_type: string;
  source: string;
}

export const CIPipeline = {
  /** Preview read-only: muestra ref resuelto + ultimo pipeline + would_reuse. */
  preview: (project: string, ref: string): Promise<CIPreviewResponse> =>
    api.get<CIPreviewResponse>(
      `/api/ci/${encodeURIComponent(project)}/trigger-preview?ref=${encodeURIComponent(ref)}`
    ),

  /** Dispara pipeline CI. confirm DEBE ser true (HITL). */
  trigger: (
    project: string,
    ref: string,
    sha: string,
    itemId: string,
    confirm: true
  ): Promise<CITriggerResponse> =>
    api.post<CITriggerResponse>(`/api/ci/${encodeURIComponent(project)}/trigger`, {
      ref,
      sha,
      item_id: itemId,
      confirm,
    }),

  /** Estado actual del pipeline. */
  monitor: (project: string, pipelineId: string): Promise<CIMonitorResponse> =>
    api.get<CIMonitorResponse>(
      `/api/ci/${encodeURIComponent(project)}/pipeline/${encodeURIComponent(pipelineId)}`
    ),
};

// ── Plan 74 F7 — Migrador ADO → GitLab ──────────────────────────────────────

export interface MigrationPlanResponse {
  ok: boolean;
  plan_id: string;
  plan_hash: string;
  total_ops: number;
  counts_by_type: Record<string, number>;
  warnings: string[];
  skipped_at_plan: number;
}

export interface MigrationExecuteResponse {
  ok: boolean;
  migration_run: string;
  applied: number;
  skipped: number;
  failed: Array<{ ado_id: string; op_kind: string; error: string }>;
  orphaned: string[];
}

export interface MigrationMappingRow {
  ado_id: string;
  ado_type: string;
  gitlab_iid: string;
  gitlab_web_url: string;
  marker: string;
  migration_run: string;
  created_at: string;
}

export interface MigrationRun {
  migration_run: string;
  count: number;
  last_created_at: string;
}

export const Migrator = {
  /** Health check del migrador (gated by STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED). */
  health: () => api.get<{ ok: boolean; flag_enabled: boolean }>("/api/migrator/health"),

  /** Genera un plan de migración (dry-run). */
  plan: (stacky_project: string, epic_policy = "auto"): Promise<MigrationPlanResponse> =>
    api.post<MigrationPlanResponse>("/api/migrator/plan", { stacky_project, epic_policy }),

  /** Ejecuta el plan con confirmación HITL. */
  execute: (
    stacky_project: string,
    plan_id: string,
    plan_hash: string,
    confirmed = true
  ): Promise<MigrationExecuteResponse> =>
    api.post<MigrationExecuteResponse>("/api/migrator/execute", {
      stacky_project,
      plan_id,
      plan_hash,
      confirmed,
    }),

  /** Descarga el mapa de migración (JSON). */
  mapping: (stacky_project: string): Promise<{ ok: boolean; rows: MigrationMappingRow[] }> =>
    api.get<{ ok: boolean; rows: MigrationMappingRow[] }>(
      `/api/migrator/${encodeURIComponent(stacky_project)}/mapping`
    ),

  /** Lista las corridas de migración del proyecto. */
  runs: (stacky_project: string): Promise<{ ok: boolean; runs: MigrationRun[] }> =>
    api.get<{ ok: boolean; runs: MigrationRun[] }>(
      `/api/migrator/${encodeURIComponent(stacky_project)}/runs`
    ),
};

// ── Plan 76/80 — Codebase Memory MCP (externo, opt-in) ──────────────────────

export interface CodebaseMemoryMcpStatusResponse {
  enabled: boolean;
  installed_hint: string;
  flag: string;
  external_repo: string;
  guides: Record<string, string>;
  wiring: { binary_path_set: boolean; injects_external: boolean };
}

export interface CodebaseMemoryMcpSavingsResponse {
  samples: number;
  delta_pct: number | null;
  note: string;
}

export const CodebaseMemoryMcp = {
  /** GET /api/codebase-memory-mcp/status — estado + guías + wiring (Plan 80 F6). */
  status: (): Promise<CodebaseMemoryMcpStatusResponse> =>
    api.get<CodebaseMemoryMcpStatusResponse>("/api/codebase-memory-mcp/status"),
  /** GET /api/codebase-memory-mcp/savings — ahorro estimado (PoC manual, Plan 80 F5). */
  savings: (): Promise<CodebaseMemoryMcpSavingsResponse> =>
    api.get<CodebaseMemoryMcpSavingsResponse>("/api/codebase-memory-mcp/savings"),
};

// ── Plan 87 — Panel DevOps (creador gráfico de pipelines) ─────────────────────

// ── Plan 116 — Doctor de conexiones (contratos DiagResult / snapshot) ─────────
export interface ConnectionRemediationAction {
  kind: 'retry' | 'copy_command' | 'open_url' | 'goto_section' | 'none';
  command?: string;
  url?: string;
  section_id?: string;
}
export interface ConnectionRemediation {
  title: string;
  cause: string;
  steps: string[];
  action: ConnectionRemediationAction;
}
export interface ConnectionDiagResult {
  target: string;
  target_label: string;
  group: 'tracker' | 'servers' | 'clis' | 'credentials';
  status: 'ok' | 'warn' | 'fail' | 'skip';
  code: string;
  detail: string;
  latency_ms: number | null;
  remediation: ConnectionRemediation | null;
}
export interface ConnectionsSnapshot {
  generated_at: string;
  duration_ms: number;
  results: ConnectionDiagResult[];
  summary: { ok: number; warn: number; fail: number; skip: number };
}
export interface ConnectionsHealthResponse {
  status: 'ready' | 'never_run';
  stale: boolean;
  snapshot: ConnectionsSnapshot | null;
}

export const DevOps = {
  /** GET /api/devops/health — health del panel (keys aditivas por plan: 88/89/90/91). */
  health: () =>
    api.get<{
      flag_enabled: boolean;
      generator_enabled: boolean;
      trigger_enabled: boolean;
      publications_enabled?: boolean; // Plan 88
      environments_enabled?: boolean; // Plan 89
      agent_enabled?: boolean; // Plan 90
      servers_enabled?: boolean; // Plan 91
      rdp_available?: boolean; // Plan 91
      preflight_enabled?: boolean; // Plan 93
      stack_detect_enabled?: boolean; // Plan 97
      variables_enabled?: boolean; // Plan 94
      production_enabled?: boolean; // Plan 95
      ado_commit_supported?: boolean; // Plan 95 [C2]
      env_tree_preview_enabled?: boolean; // Plan 107
      env_sandbox_enabled?: boolean; // Plan 107
      pr_reviewer_enabled?: boolean; // Plan 110
      connection_doctor_enabled?: boolean; // Plan 116
    }>("/api/devops/health"),
  /** Plan 116 — último snapshot del doctor de conexiones (HITL; 404 si flag OFF). */
  connectionsHealth: () =>
    api.get<ConnectionsHealthResponse>("/api/devops/connections/health"),
  /** Plan 116 — corre el chequeo de conexiones (solo por click del operador). */
  connectionsCheck: () =>
    api.post<ConnectionsHealthResponse>("/api/devops/connections/check", {}),
  /** POST /api/devops/parse-yaml — YAML (ado|gitlab) → dict PipelineSpec. */
  parseYaml: (source: "ado" | "gitlab", yaml: string) =>
    api.post<{ spec: object }>("/api/devops/parse-yaml", { source, yaml }),
  /**
   * POST /api/devops/publications/materialize — Plan 88. Preset + catálogo del
   * proyecto → dict PipelineSpec. SOLO-LECTURA (no commitea, no dispara).
   */
  materializePublication: (project: string, presetName: string) =>
    api.post<{ spec: object; resolved: string[]; unknown_processes: string[] }>(
      "/api/devops/publications/materialize",
      { project, preset_name: presetName },
    ),
  /**
   * POST /api/devops/environments/plan — Plan 89. Dry-run SOLO-LECTURA del árbol
   * de carpetas. Plan 107: rootOverride opcional (sandbox de pruebas); si es
   * undefined el body es EXACTAMENTE el de hoy (cero regresión). Plan 108 F6:
   * serverAlias opcional (ancla el plan al servidor seleccionado); ausente ⇒
   * body idéntico a hoy.
   */
  environmentPlan: (project: string, rootOverride?: string, serverAlias?: string) =>
    api.post<EnvironmentPlanResponse>("/api/devops/environments/plan", {
      project,
      ...(rootOverride ? { root_override: rootOverride } : {}),
      ...(serverAlias ? { server_alias: serverAlias } : {}),
    }),
  /**
   * POST /api/devops/environments/apply — Plan 89. Crea SOLO to_create. HITL:
   * confirm es SIEMPRE argumento del caller (el componente pasa el estado del
   * checkbox; este helper NUNCA lo auto-inyecta). Plan 107: rootOverride +
   * sandboxAck opcionales (sandbox_ack=True obligatorio server-side cuando hay
   * root_override); sin rootOverride el body es EXACTAMENTE el de hoy. Plan 108
   * F6: serverAlias opcional (crea EN el servidor seleccionado).
   */
  environmentApply: (
    project: string,
    paths: string[],
    confirm: boolean,
    fingerprint: string,
    rootOverride?: string,
    sandboxAck?: boolean,
    serverAlias?: string,
  ) =>
    api.post<EnvironmentApplyResponse>("/api/devops/environments/apply", {
      project,
      paths,
      confirm,
      fingerprint,
      ...(rootOverride ? { root_override: rootOverride, sandbox_ack: sandboxAck === true } : {}),
      ...(serverAlias ? { server_alias: serverAlias } : {}),
    }),
  /** GET /api/devops/detect-stack — Plan 97. Detección opt-in de stack por manifiestos, SOLO-LECTURA. */
  detectStack: (project: string) =>
    api.get<{ detected: string | null }>(`/api/devops/detect-stack?project=${encodeURIComponent(project)}`),
  /**
   * POST /api/devops/preflight/check — Plan 93. Semáforo "¿Va a funcionar?"
   * SOLO-LECTURA (no commitea, no dispara). target: "auto" resuelve el
   * tracker real del proyecto (default recomendado).
   */
  preflightCheck: (project: string, spec: object, target: "auto" | "ado" | "gitlab" | "both" = "auto") =>
    api.post<{ checks: PreflightCheck[]; summary: Record<string, number> }>(
      "/api/devops/preflight/check",
      { project, spec, target },
    ),
  /**
   * POST /api/devops/doctor/diagnose — Plan 96. Jobs fallidos + clasificación
   * en llano. SOLO-LECTURA (no persiste logs, no re-lanza, no cancela).
   */
  doctorDiagnose: (project: string, pipelineId: string) =>
    api.post<{
      provider: string;
      jobs: DoctorJob[];
      no_failures_found: boolean;
      failed_jobs_total: number;
    }>("/api/devops/doctor/diagnose", { project, pipeline_id: pipelineId }),
};

export interface DevOpsConversationItem {
  conversation_id: number;
  title: string;
  project: string | null;
  last_execution_id: number | null;
  last_status: string | null;
  last_runtime: string | null;
  started_at: string | null;
  continuable_with_memory: boolean; // C3 (v2): señal honesta por-conversación
  server_alias?: string | null; // Plan 108 F3 — servidor al que quedó sellada la conversación
  // Plan 108 [ADICIÓN ARQUITECTO v2] — ausente si no hay alias; null si la auditoría falló.
  audited_remote_commands?: number | null;
}

/** Plan 90 — conversaciones del agente DevOps (multi-turno sobre runtimes CLI). */
export const DevOpsAgentApi = {
  start: (body: {
    project: string;
    message: string;
    runtime?: "claude_code_cli" | "codex_cli";
    model?: string;
    effort?: string;
    server_alias?: string; // Plan 108 F3/F4 — ancla el turno al servidor seleccionado
  }) =>
    api.post<{
      ok: boolean;
      conversation_id: number;
      execution_id: number;
      runtime: string;
      server_alias?: string | null;
    }>("/api/devops/agent/conversations", body),
  message: (conversationId: number, message: string) =>
    api.post<{ ok: boolean; mode: "stdin" | "resume" | "new_run"; execution_id: number }>(
      `/api/devops/agent/conversations/${conversationId}/message`,
      { message },
    ),
  list: (project?: string) =>
    api.get<{ conversations: DevOpsConversationItem[]; resume_enabled: boolean }>(
      `/api/devops/agent/conversations${project ? `?project=${encodeURIComponent(project)}` : ""}`,
    ),
};

export interface ServerSummary {
  alias: string;
  host: string;
  domain: string;
  username: string;
  notes: string;
  has_password: boolean;
  last_connected_at?: string | null; // [ADICIÓN ARQUITECTO] ISO o null
}

/** Plan 91 — registro de servidores DevOps (CRUD + test conectividad + RDP 1-click). */
export const DevOpsServers = {
  list: () =>
    api.get<{ servers: ServerSummary[]; keyring_available: boolean }>("/api/devops/servers"),
  create: (body: {
    alias: string;
    host: string;
    domain?: string;
    username: string;
    notes?: string;
    password?: string;
  }) => api.post<ServerSummary>("/api/devops/servers", body),
  update: (
    alias: string,
    body: { host: string; domain?: string; username: string; notes?: string; password?: string | null },
  ) => api.put<ServerSummary>(`/api/devops/servers/${encodeURIComponent(alias)}`, body),
  remove: (alias: string) =>
    api.delete<{ ok: boolean }>(`/api/devops/servers/${encodeURIComponent(alias)}`),
  testConnection: (alias: string) =>
    api.post<{ ok: boolean; detail: string }>(`/api/devops/servers/${encodeURIComponent(alias)}/test`, {}),
  connectRdp: (alias: string) =>
    api.post<{ ok: boolean; detail: string }>(`/api/devops/servers/${encodeURIComponent(alias)}/rdp`, {}),
  downloadSetupScripts: async () => {
    // Descarga un ZIP con Enable-WinRM.ps1 y Enable-WinRM.bat para configurar WinRM en un servidor.
    const response = await fetch("/api/devops/servers/download-setup");
    if (!response.ok) throw new Error(`Descarga falló: ${response.statusText}`);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "Enable-WinRM.zip";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },
};

// Plan 105 — Consola remota por servidor
export interface RemoteConsoleConversation {
  id: number;
  title: string;
  ado_state: string;
  created_at: string | null;
  server_alias: string;
  write_enabled: boolean;
  last_execution?: { id: number; state: string };
}

export const DevOpsRemoteConsole = {
  exec: (alias: string, command: string, conversation_id?: number) =>
    api.post<{ ok: boolean; stdout: string; stderr: string; exit_code: number; duration_ms: number }>(
      "/api/devops/console/exec",
      { alias, command, conversation_id }
    ),
  getConversations: (serverAlias: string) =>
    api.get<RemoteConsoleConversation[]>(`/api/devops/console/conversations?server=${encodeURIComponent(serverAlias)}`),
  createConversation: (serverAlias: string, project: string, message: string) =>
    api.post<{ conversation_id: number; execution_id: number }>("/api/devops/console/conversations", {
      server_alias: serverAlias,
      project,
      message,
    }),
  sendMessage: (conversationId: number, message: string) =>
    api.post<{ ok: boolean; execution_id?: number }>(`/api/devops/console/conversations/${conversationId}/message`, { message }),
  setWriteMode: (conversationId: number, enabled: boolean) =>
    api.post<{ ok: boolean; write_enabled: boolean }>(`/api/devops/console/conversations/${conversationId}/write-mode`, { enabled }),
  getAudit: (alias: string, limit?: number, offset?: number) =>
    api.get<Array<{ seq: number; timestamp: string; kind: string; [key: string]: any }>>(
      `/api/devops/console/audit/${encodeURIComponent(alias)}${limit !== undefined ? `?limit=${limit}&offset=${offset}` : ''}`
    ),
  checkWinrm: (alias: string) =>
    api.get<{
      ok: boolean;
      detail?: string;
      // Plan 108 F1b (C9 v2) — diagnóstico tipificado + remediación copy-paste.
      // Ausentes cuando ok=true; [] cuando el kind no tiene pasos (server_not_found, etc.).
      kind?: string;
      remediation?: { where: string; label: string; command: string | null }[];
    }>(`/api/devops/console/winrm/${encodeURIComponent(alias)}`),
};

export interface CIVariableSummary {
  key: string;
  is_secret: boolean;
  has_value: boolean;
  masked: boolean | null;
}

/**
 * Plan 94 — caja fuerte de variables del pipeline (ADO isSecret / GitLab masked).
 * El value es write-only: NUNCA aparece en list ni en la respuesta de create.
 */
export const DevOpsVariables = {
  list: (project: string) =>
    api.get<{ variables: CIVariableSummary[]; provider: string }>(
      `/api/devops/variables?project=${encodeURIComponent(project)}`,
    ),
  create: (body: { project: string; key: string; value: string; secret: boolean; confirm: true }) =>
    api.post<CIVariableSummary>("/api/devops/variables", body),
  remove: (project: string, key: string) =>
    api.post<{ ok: boolean }>("/api/devops/variables/delete", { project, key, confirm: true }),
};

export interface MrInfo {
  id: string;
  web_url: string;
  state: "open" | "merged" | "closed";
  pipeline_status?: "created" | "pending" | "running" | "success" | "failed" | "canceled" | "none";
  mergeable?: boolean;
}

// ── Plan 110 — Revisor de PRs (Haiku solo-lectura + modelo local) ────────────
export interface PrSummary {
  id: string;
  title: string;
  state: "open" | "merged" | "closed";
  source_branch: string;
  target_branch: string;
  author: string;
  web_url: string;
  pipeline_status: string;
}
export interface PrReviewFinding {
  severity: "info" | "warning" | "critical";
  title: string;
  detail: string;
}
export interface PrRecommendedAction {
  type: "approve" | "comment" | "request_changes" | "merge" | "close" | "none";
  label: string;
  params: Record<string, unknown>;
}
export interface PrHaikuReview {
  summary: string;
  findings: PrReviewFinding[];
  recommended_action: PrRecommendedAction;
  confidence: number;
}
export interface PrReviewDetail {
  id: string;
  meta: MrInfo & { source_branch?: string; target_branch?: string };
  files: { path: string; change_type: string }[];
  diff_text: string;
  diff_truncated: boolean;
  diff_available: boolean;
  note: string;
}

export const PrReview = {
  list: (project: string, state = "open") =>
    api.get<{ provider: string; merge_requests: PrSummary[] }>(
      `/api/pr-review/list?project=${encodeURIComponent(project)}&state=${state}`,
    ),
  detail: (project: string, mrId: string) =>
    api.get<PrReviewDetail>(
      `/api/pr-review/detail?project=${encodeURIComponent(project)}&mr_id=${encodeURIComponent(mrId)}`,
    ),
  reviewHaiku: (project: string, mrId: string) =>
    api.post<{ ok: boolean; review: PrHaikuReview; model: string; diff_truncated: boolean; diff_available: boolean; execution_id: number }>(
      "/api/pr-review/review/haiku",
      { project, mr_id: mrId },
    ),
  reviewLocal: (project: string, mrId: string, question?: string) =>
    api.post<{ ok: boolean; answer: string; model: string; diff_truncated: boolean; diff_available: boolean; execution_id: number }>(
      "/api/pr-review/review/local",
      { project, mr_id: mrId, question },
    ),
  actions: (project: string) =>
    api.get<{ provider: string; actions: string[] }>(
      `/api/pr-review/actions?project=${encodeURIComponent(project)}`,
    ),
  // C3 — catálogo Copilot para elegir el id Haiku.
  models: () =>
    api.get<{ models: { id: string; name: string; is_haiku: boolean }[]; configured: string }>(
      "/api/pr-review/models",
    ),
  execute: (b: { project: string; mr_id: string; action: string; body?: string; confirm?: boolean; confirm_merge?: boolean }) =>
    api.post<{ ok: boolean; action: string; result: unknown }>("/api/pr-review/execute", b),
};

/**
 * Plan 95 — flujo "Llevar a producción": crear MR/PR, ver su pipeline y
 * mergear con confirmación HITL (server-side, además del checkbox en UI).
 */
export const DevOpsProduction = {
  createMr: (body: { project: string; source_branch: string; target_branch?: string; title?: string; confirm: true }) =>
    api.post<MrInfo>("/api/devops/production/mr", body),
  getMr: (project: string, mrId: string) =>
    api.get<MrInfo>(`/api/devops/production/mr/${encodeURIComponent(mrId)}?project=${encodeURIComponent(project)}`),
  mergeMr: (project: string, mrId: string) =>
    api.post<{ id: string; state: "merged" }>(`/api/devops/production/mr/${encodeURIComponent(mrId)}/merge`, {
      project,
      confirm: true,
    }),
  ensureAdoDefinition: (project: string) =>
    api.post<{ id: number; name: string; created: boolean }>("/api/devops/production/ado/ensure-definition", {
      project,
      confirm: true,
    }),
};

/** Plan 104 — Doctores IA por sección del panel DevOps. */
export const SectionDoctorApi = {
  run: (sectionId: string, body: {
    project: string;
    runtime: "claude_code_cli" | "codex_cli" | "github_copilot";
    payload: Record<string, unknown>;
  }) =>
    api.post<{
      ok: boolean;
      execution_id: number;
      conversation_id: number;   // [C4] ticket ancla — para linkear al panel del 90
      runtime: string;
      section: string;
    }>(
      `/api/devops/sections/${encodeURIComponent(sectionId)}/doctor`,
      body,
    ),
};

export const PipelineGenerator = {
  /** POST /api/pipeline-generator/preview — spec → {ado, gitlab} (200) o {errors} (400). */
  preview: (spec: object) =>
    api.post<{ ado: string; gitlab: string }>("/api/pipeline-generator/preview", spec),
  /**
   * POST /api/pipeline-generator/commit — commit HITL con confirm.
   * El spec va en el body ROOT junto a confirm/target/branch/project.
   */
  commit: (body: object) => api.post<object>("/api/pipeline-generator/commit", body),
};

/** Plan 106 — Modelo local (Ollama/LM Studio/vLLM). */
export const LocalLlmApi = {
  /** Plan 117 — genera/regenera el insight local de una ejecución (HITL). */
  generateInsight: (executionId: number) =>
    api.post<{ ok: boolean; insight?: ExecutionLocalInsight; error?: string; reason?: string }>(
      `/api/llm/insights/${executionId}/generate`,
      {},
    ),
  localHealth: () =>
    api.get<{ ok: boolean; reachable: boolean; endpoint: string; model: string }>(
      "/api/llm/local-health",
    ),
  /** Lista los modelos instalados en el servidor local (selector de modelos). */
  localModels: () =>
    api.get<{ ok: boolean; reachable: boolean; models: string[]; current: string }>(
      "/api/llm/local-models",
    ),
  /** Prompt libre para probar el modelo local (con selector de modelo opcional). */
  playground: (body: { prompt: string; model?: string; system?: string }) =>
    api.post<{ ok: boolean; response: string; model: string; execution_id: number }>(
      "/api/llm/playground",
      body,
    ),
  analyzeCode: (body: {
    project: string;
    stack?: string;
    files?: Array<{ path: string; content: string }>;
    prompt?: string;
    model?: string;
  }) =>
    api.post<{ ok: boolean; analysis: string; model: string; execution_id: number }>(
      "/api/llm/analyze-code",
      body,
    ),
  suggestPipeline: (body: {
    project: string;
    stack: string;
    spec_partial?: Record<string, unknown>;
    model?: string;
  }) =>
    api.post<{
      ok: boolean;
      suggestions: {
        working_directory: string;
        condition: string;
        environment_variables: Record<string, string>;
        justification: string;
      };
      model: string;
      execution_id: number;
    }>("/api/llm/suggest-pipeline", body),
};

/** Plan 122 — núcleo del Comparador de BD entre ambientes (serie 122-126). */
export const DbCompare = {
  /** GET /api/db-compare/health — SIEMPRE 200, incluso con la flag OFF. */
  health: () => api.get<DbCompareHealth>("/api/db-compare/health"),
  listEnvironments: () =>
    api.get<{ ok: boolean; environments: DbEnvironment[]; keyring_available: boolean }>(
      "/api/db-compare/environments",
    ),
  upsertEnvironment: (body: {
    alias: string;
    engine: string;
    host: string;
    port: number;
    database: string;
    username: string;
    odbc_driver?: string;
    schema_filter?: string[] | null;
    notes?: string;
  }) =>
    api.post<{ ok: boolean; environment?: DbEnvironment; error?: string }>(
      "/api/db-compare/environments",
      body,
    ),
  deleteEnvironment: (alias: string) =>
    api.delete<{ ok: boolean; error?: string }>(
      `/api/db-compare/environments/${encodeURIComponent(alias)}`,
    ),
  setPassword: (alias: string, password: string) =>
    api.post<{ ok: boolean; error?: string }>(
      `/api/db-compare/environments/${encodeURIComponent(alias)}/password`,
      { password },
    ),
  clearPassword: (alias: string) =>
    api.delete<{ ok: boolean }>(
      `/api/db-compare/environments/${encodeURIComponent(alias)}/password`,
    ),
  testConnection: (alias: string) =>
    api.post<TestConnectionResult>(
      `/api/db-compare/environments/${encodeURIComponent(alias)}/test`,
      {},
    ),
  takeSnapshot: (alias: string) =>
    api.post<{ id: string; content_hash: string; counts: SnapshotMeta["counts"]; duration_ms: number }>(
      `/api/db-compare/environments/${encodeURIComponent(alias)}/snapshot`,
      {},
    ),
  listSnapshots: (alias: string) =>
    api.get<{ ok: boolean; snapshots: SnapshotMeta[] }>(
      `/api/db-compare/environments/${encodeURIComponent(alias)}/snapshots`,
    ),
  getSnapshot: (snapshotId: string) =>
    api.get<DbSnapshot>(`/api/db-compare/snapshots/${encodeURIComponent(snapshotId)}`),
  // Plan 125 F5/F6 — bundle de scripts de paridad + backups pareados 1:1.
  // Stacky genera; JAMÁS ejecuta (ver doc 125 §3).
  generateScripts: (runId: string) =>
    api.post<{ ok: boolean; manifest?: Manifest; error?: string }>(
      `/api/db-compare/runs/${encodeURIComponent(runId)}/scripts`,
      {},
    ),
  getManifest: (runId: string) =>
    api.get<{ ok: boolean; manifest?: Manifest; error?: string }>(
      `/api/db-compare/runs/${encodeURIComponent(runId)}/scripts`,
    ),
  scriptFileUrl: (runId: string, path: string) =>
    `${apiBase}/api/db-compare/runs/${encodeURIComponent(runId)}/scripts/file?path=${encodeURIComponent(path)}`,
  scriptsZipUrl: (runId: string) => `${apiBase}/api/db-compare/runs/${encodeURIComponent(runId)}/scripts.zip`,
  getScriptFileText: async (runId: string, path: string): Promise<string> => {
    const response = await fetch(DbCompare.scriptFileUrl(runId, path));
    if (!response.ok) throw new Error(`No se pudo leer el archivo: ${response.statusText}`);
    return response.text();
  },
  downloadScriptsZip: async (runId: string) => {
    const response = await fetch(DbCompare.scriptsZipUrl(runId));
    if (!response.ok) throw new Error(`Descarga falló: ${response.statusText}`);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `dbcompare_${runId}.zip`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },
  // Plan 124 F1 — corridas comparativas (doc 123 §F3). NOTA de contrato verificada contra
  // api/db_compare.py: POST /compare devuelve {ok, run} (202); GET /runs devuelve {ok, runs}
  // (metadatos SIN "diff"); GET /runs/<id> devuelve el CompareRun DIRECTO, sin wrapper {ok,run}.
  compare: (body: { source_alias: string; target_alias: string; mode?: "fresh" | "cached" }) =>
    api.post<{ ok: boolean; run: CompareRun }>("/api/db-compare/compare", body),
  listRuns: (limit?: number) =>
    api.get<{ ok: boolean; runs: CompareRun[] }>(
      `/api/db-compare/runs${limit != null ? `?limit=${limit}` : ""}`,
    ),
  getRun: (runId: string) => api.get<CompareRun>(`/api/db-compare/runs/${encodeURIComponent(runId)}`),
  exportUrl: (runId: string) => `/api/db-compare/runs/${encodeURIComponent(runId)}/export.md`,
};
