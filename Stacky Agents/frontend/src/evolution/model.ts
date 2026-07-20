// Plan 167 F5 — modelo puro del Centro de Evolución (sin React, sin CSS).
// Tipos DTO + lógica de chips/filtros/predicados de acción como funciones
// puras testeables con vitest (node env; sin RTL/jsdom — gap del repo).

export type ProposalStatus =
  | "draft" | "pending_review" | "approved" | "applied" | "rejected" | "rolled_back";
export type ProposalOrigin = "manual" | "agent" | "optimizer" | "mape";
export type ArtifactType = "free_text" | "knowledge_note" | "prompt_file" | "flag_change";
export type LoopMode = "human_in_the_loop" | "human_on_the_loop";

export interface AspectDto {
  id: string;
  name: string;
  description: string;
  target_kind: string;
  loop_mode: LoopMode;
  links: { label: string; href: string }[];
  created_at: string;
}

export interface FitnessDto {
  score: number | null;
  metrics: Record<string, unknown>;
  eval_ref: string | null;
  evaluated_at: string;
}

export interface ProposalDto {
  id: string;
  aspect_id: string;
  title: string;
  rationale: string;
  origin: ProposalOrigin;
  artifact_type: ArtifactType;
  target_ref: string | null;
  proposed_content: string | null;
  base_hash: string | null;
  evidence: string[];
  status: ProposalStatus;
  fitness_before: FitnessDto | null;
  fitness_after: FitnessDto | null;
  parent_proposal_id: string | null;
  cycle_id: string | null;
  snapshot_info: Record<string, unknown> | null;
  notes: { ts: string; actor: string; text: string }[];
  created_at: string;
  updated_at: string;
  applied_at: string | null;
  rolled_back_at: string | null;
}

export interface CycleDto {
  id: string;
  started_at: string;
  finished_at: string;
  status: string;
  error: string | null;
  rules_fired: string[];
  skipped_duplicate_rules: string[];
  proposal_ids: string[];
  llm_used: boolean;
  llm_error: string | null;
  tokens_est_in: number;
  tokens_est_out: number;
  signals_truncated: boolean;
}

export type StatusCounts = Record<ProposalStatus, number>;

export interface OverviewDto {
  ok: boolean;
  aspects: AspectDto[];
  counts: StatusCounts;
  last_cycle: CycleDto | null;
}

// tono del StatusChip (valores REALES del barrel: components/ui/StatusChip.tsx:4)
export function statusTone(
  s: ProposalStatus,
): "success" | "warning" | "danger" | "info" | "neutral" {
  switch (s) {
    case "draft":
      return "neutral";
    case "pending_review":
      return "info";
    case "approved":
      return "warning";
    case "applied":
      return "success";
    case "rejected":
      return "danger";
    case "rolled_back":
      return "neutral";
  }
}

export function statusLabel(s: ProposalStatus): string {
  switch (s) {
    case "draft":
      return "Borrador";
    case "pending_review":
      return "En revisión";
    case "approved":
      return "Aprobada";
    case "applied":
      return "Aplicada";
    case "rejected":
      return "Rechazada";
    case "rolled_back":
      return "Revertida";
  }
}

export function loopModeLabel(m: LoopMode): string {
  return m === "human_in_the_loop" ? "Humano en el lazo" : "Humano sobre el lazo";
}

export interface ProposalFilters {
  status: ProposalStatus | "TODAS";
  aspectId: string | "TODOS";
  origin: ProposalOrigin | "TODOS";
}

export function filterProposals(list: ProposalDto[], f: ProposalFilters): ProposalDto[] {
  return list.filter(
    (p) =>
      (f.status === "TODAS" || p.status === f.status) &&
      (f.aspectId === "TODOS" || p.aspect_id === f.aspectId) &&
      (f.origin === "TODOS" || p.origin === f.origin),
  );
}

export interface ProposalAction {
  action: string;
  label: string;
  confirm: boolean;
}

export function availableActions(p: ProposalDto): ProposalAction[] {
  switch (p.status) {
    case "draft":
      return [
        { action: "submit", label: "Enviar a revisión", confirm: false },
        { action: "reject", label: "Rechazar", confirm: true },
      ];
    case "pending_review":
      return [
        { action: "approve", label: "Aprobar", confirm: false },
        { action: "reject", label: "Rechazar", confirm: true },
      ];
    case "approved": {
      const appliable = p.artifact_type === "knowledge_note" || p.artifact_type === "prompt_file";
      const base: ProposalAction[] = appliable
        ? [{ action: "apply", label: "Aplicar", confirm: true }]
        : [];
      return base.concat([{ action: "reject", label: "Rechazar", confirm: true }]);
    }
    case "applied":
      return [{ action: "rollback", label: "Revertir", confirm: true }];
    case "rejected":
    case "rolled_back":
      return [];
  }
}

export function flagDeepLink(targetRef: string | null): string | null {
  if (!targetRef) return null;
  return `/settings?flag=${encodeURIComponent(targetRef)}`;
}

export function fitnessDisplay(f: FitnessDto | null): string {
  if (f === null) return "—";
  return String(f.score ?? "—");
}
