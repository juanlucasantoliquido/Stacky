// Plan 168 F6 — modelo puro de la sección Fitness (sin React, sin CSS).
// Tipos DTO + helpers de chips/formato como funciones puras testeables con
// vitest (node env; sin RTL/jsdom — gap del repo).

export type SignalLevel = "deterministic" | "execution" | "llm_judge";

export interface EvalCaseDto {
  id: string;
  aspect_key: string;
  agent_type: string | null;
  subject: "artifact" | "output";
  level: SignalLevel;
  title: string;
  checks: Record<string, unknown>[];
  rubric_id: string | null;
  weight: number;
  origin: "seed" | "incident" | "execution" | "manual";
  enabled: boolean;
  source_ref: string | null;
  created_at: string;
  updated_at: string;
}

export interface EvalRunSummaryDto {
  id: string;
  finished_at: string;
  aspect_key: string;
  trigger: string;
  score: number | null;
  passed: boolean;
  deterministic_gate: "passed" | "failed" | "none";
}

export interface ScorecardDto {
  aspect_key: string;
  latest: EvalRunSummaryDto | null;
  previous_score: number | null;
  delta: number | null;
  history: { ts: string; score: number | null }[];
  cases_enabled: number;
  cases_total: number;
}

export type JudgeCheckStatus = "calibrated" | "uncalibrated" | "unavailable";

export function levelLabel(l: SignalLevel): string {
  switch (l) {
    case "deterministic":
      return "Determinista";
    case "execution":
      return "Ejecución";
    case "llm_judge":
      return "Juez LLM";
  }
}

export function levelTone(l: SignalLevel): "success" | "info" | "warning" {
  switch (l) {
    case "deterministic":
      return "success";
    case "execution":
      return "info";
    case "llm_judge":
      return "warning";
  }
}

export function gateLabel(g: "passed" | "failed" | "none"): string {
  switch (g) {
    case "passed":
      return "Deterministas OK";
    case "failed":
      return "Determinista FALLÓ";
    case "none":
      return "Sin deterministas";
  }
}

export function scoreDisplay(s: number | null): string {
  if (s === null) return "—";
  return s.toFixed(2);
}

export function deltaDisplay(d: number | null): string {
  if (d === null) return "";
  if (d > 0) return `▲ +${d.toFixed(2)}`;
  if (d < 0) return `▼ ${d.toFixed(2)}`;
  return "= 0.00";
}

export function deltaTone(d: number | null): "success" | "danger" | "neutral" {
  if (d === null) return "neutral";
  if (d > 0) return "success";
  if (d < 0) return "danger";
  return "neutral";
}

export function aspectLabel(key: string): string {
  if (key === "knowledge_rag") return "Lecciones (RAG)";
  if (key.startsWith("agent_prompts/")) return `Prompt: ${key.slice("agent_prompts/".length)}`;
  return key;
}

export function canEvaluateProposal(artifactType: string, status: string): boolean {
  const evaluable = artifactType === "prompt_file" || artifactType === "knowledge_note";
  const stageOk = status === "draft" || status === "pending_review" || status === "approved";
  return evaluable && stageOk;
}

export function judgeCheckLabel(status: JudgeCheckStatus | null): string {
  switch (status) {
    case "calibrated":
      return "Juez calibrado";
    case "uncalibrated":
      return "Juez descalibrado — no confiar en sus scores";
    case "unavailable":
      return "Juez no disponible";
    default:
      return "Juez sin verificar";
  }
}
