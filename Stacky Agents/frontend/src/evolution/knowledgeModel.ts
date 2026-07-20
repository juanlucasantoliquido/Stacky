// Plan 170 F6 — DTOs + funciones PURAS del flywheel de conocimiento.
// Espejo de §4.2/§4.8/§4.10. Sin dependencias de DOM (vitest puro — G5).
import type { StatusTone } from "../components/ui";

export interface LessonScopeDto {
  agent_types: string[];
  projects: string[];
  tags: string[];
}

export interface LessonSourceDto {
  kind: "incident" | "optimizer_lesson" | "manual";
  ref: string | null;
}

export interface LessonDto {
  lesson_id: string;
  aspect_id: string;
  text: string;
  origin: string;
  created_at: string | null;
  active: boolean;
  title: string;
  scope: LessonScopeDto;
  source: LessonSourceDto;
  eval_case_id: string | null;
  usage_count: number;
  last_injected_at: string | null;
}

export interface IncidentCandidateDto {
  incident_id: string;
  title: string;
  created_at: string | null;
  has_dev_run: boolean;
  already_harvested: boolean;
}

export interface OptimizerLessonCandidateDto {
  lesson_id: string;
  run_id: string;
  aspect_key: string;
  text: string;
  delta: number | null;
  already_harvested: boolean;
}

export interface HarvestCandidatesDto {
  ok: boolean;
  incidents: IncidentCandidateDto[];
  optimizer_lessons: OptimizerLessonCandidateDto[];
}

export interface RetireSuggestionDto {
  lesson_id: string;
  title: string;
  usage_count: number;
  created_at: string | null;
  reason: "lru_por_uso" | "sin_uso_prolongado";
}

export interface KnowledgeOverviewDto {
  ok: boolean;
  lessons: { active: number; retired: number; cap: number; over_cap: boolean };
  coverage: {
    agents_total: number;
    agents_with_lessons: number;
    by_agent_type: Record<string, number>;
  };
  flywheel: {
    incidents_published: number;
    incidents_harvested: number;
    eval_cases_from_incidents: number;
    eval_cases_from_lessons: number;
    optimizer_lessons_mejoro: number;
    optimizer_lessons_promoted: number;
  };
  usage: {
    injections_total: number;
    never_injected: number;
    top: { lesson_id: string; title: string; usage_count: number }[];
  };
  fitness_knowledge: {
    latest_score: number | null;
    baseline_score: number | null;
    delta: number | null;
    runs: number;
  };
  retire_suggestions: RetireSuggestionDto[];
}

export interface InjectionPreviewBlockDto {
  kind: string;
  id: string;
  title: string;
  content: string;
  metadata: { lesson_ids: string[]; truncated: boolean };
}

export interface InjectionPreviewDto {
  ok: boolean;
  block: InjectionPreviewBlockDto | null;
  matched_count: number;
}

// ── Funciones puras ──────────────────────────────────────────────────────────
export function scopeLabel(scope: LessonScopeDto): string {
  const agents = scope.agent_types || [];
  const projects = scope.projects || [];
  if (agents.length === 0 && projects.length === 0) return "Global";
  const parts: string[] = [];
  if (agents.length) parts.push(agents.join(" · "));
  if (projects.length) parts.push(`proyecto ${projects.join(" · ")}`);
  return parts.join(" — ");
}

export function lessonStatusChip(l: LessonDto): { tone: StatusTone; label: string } {
  return l.active
    ? { tone: "success", label: "Activa" }
    : { tone: "neutral", label: "Retirada" };
}

export function formatDelta(delta: number | null): string {
  if (delta === null || delta === undefined) return "—";
  const s = delta.toFixed(4);
  return delta > 0 ? `+${s}` : s;
}

export function validateManualLesson(input: { title: string; body: string }): {
  ok: boolean;
  errors: Record<string, string>;
} {
  const errors: Record<string, string> = {};
  const title = (input.title || "").trim();
  const body = (input.body || "").trim();
  if (!title) errors.title = "El título es obligatorio.";
  else if (input.title.length > 80) errors.title = "El título supera los 80 caracteres.";
  if (!body) errors.body = "El cuerpo es obligatorio.";
  else if (input.body.length > 1200) errors.body = "El cuerpo supera los 1200 caracteres.";
  return { ok: Object.keys(errors).length === 0, errors };
}

export function sortCandidates<T extends { already_harvested: boolean; created_at?: string | null }>(
  items: T[],
): T[] {
  return [...items].sort((a, b) => {
    if (a.already_harvested !== b.already_harvested) return a.already_harvested ? 1 : -1;
    return (b.created_at || "").localeCompare(a.created_at || "");
  });
}
