/**
 * Plan 214 F4 — Modelo PURO del veredicto QA UAT.
 *
 * El punto es que el resultado se vea con su NIVEL DE CONFIANZA REAL: un PASS con
 * assertions débiles queda anotado, nunca oculto.
 */
import type { StatusTone } from "./ui";

export type QaUatVerdict = "PASS" | "FAIL" | "BLOCKED" | "MIXED" | "SKIPPED";

export function verdictTone(v: string | undefined): StatusTone {
  switch ((v ?? "").toUpperCase()) {
    case "PASS":
      return "success";
    case "FAIL":
      return "danger";
    case "BLOCKED":
    case "MIXED":
      return "warning";
    default:
      return "neutral";
  }
}

/** Las 9 categorías reales del normalizador de veredictos. */
const _CATEGORY: Record<string, string> = {
  NAV: "Navegación",
  DATA: "Datos",
  ENV: "Entorno",
  APP: "Aplicación",
  PIP: "Pipeline",
  GEN: "Generación",
  OBS: "Evidencia",
  SEC: "Seguridad",
  OPS: "Infraestructura",
};

export function categoryLabel(c: string | undefined): string {
  const key = (c ?? "").trim();
  if (!key) return "—";
  // Una categoría desconocida se muestra CRUDA: nunca se oculta señal.
  return _CATEGORY[key.toUpperCase()] ?? key;
}

export function weaknessNote(
  weakCount: number | undefined,
  verdict: string | undefined,
): string | null {
  if ((verdict ?? "").toUpperCase() !== "PASS") return null;
  if (!weakCount || weakCount <= 0) return null;
  return `PASS con ${weakCount} assertions débiles — revisar evidencia`;
}

export interface QaUatCandidate {
  status?: string;
  ado_id?: number;
  mode?: string;
  qa_uat_execution_id?: number;
}

const _CANDIDATE: Record<string, string> = {
  pending: "Validación E2E sugerida",
  blocked_by_build: "E2E en espera: build sin verificar",
  validated: "Validación E2E corrida: PASS",
  failed: "Validación E2E corrida: FALLÓ",
  blocked: "Validación E2E corrida: BLOQUEADA (entorno)",
};

export function candidateLabel(c: QaUatCandidate | undefined): string | null {
  const status = c?.status;
  if (!status) return null;
  return _CANDIDATE[status] ?? null;
}

/** Tono del candidato, para que la tarjeta no mienta sobre el estado real. */
export function candidateTone(c: QaUatCandidate | undefined): StatusTone {
  switch (c?.status) {
    case "validated":
      return "success";
    case "failed":
      return "danger";
    case "blocked":
    case "blocked_by_build":
      return "warning";
    case "pending":
      return "info";
    default:
      return "neutral";
  }
}

export interface QaUatVerdictData {
  verdict?: string;
  verdict_reason?: string;
  verdict_category?: string;
  nav_deviations?: number;
  weak_assertions_count?: number;
  replan_rounds?: number;
  playbooks_used?: string[];
}

/** Lee el veredicto de la metadata; null si esta ejecución no lo trae. */
export function readQaUatVerdict(
  metadata: Record<string, unknown> | undefined | null,
): QaUatVerdictData | null {
  if (!metadata || typeof metadata.verdict !== "string" || !metadata.verdict) return null;
  const m = metadata as Record<string, unknown>;
  return {
    verdict: m.verdict as string,
    verdict_reason: typeof m.verdict_reason === "string" ? m.verdict_reason : undefined,
    verdict_category:
      typeof m.verdict_category === "string" ? m.verdict_category : undefined,
    nav_deviations: typeof m.nav_deviations === "number" ? m.nav_deviations : undefined,
    weak_assertions_count:
      typeof m.weak_assertions_count === "number" ? m.weak_assertions_count : undefined,
    replan_rounds: typeof m.replan_rounds === "number" ? m.replan_rounds : undefined,
    playbooks_used: Array.isArray(m.playbooks_used)
      ? (m.playbooks_used as string[])
      : undefined,
  };
}

/** Lee el candidato de la metadata de una ejecución del Developer. */
export function readQaUatCandidate(
  metadata: Record<string, unknown> | undefined | null,
): QaUatCandidate | null {
  const raw = metadata?.qa_uat_candidate;
  if (!raw || typeof raw !== "object") return null;
  return raw as QaUatCandidate;
}
