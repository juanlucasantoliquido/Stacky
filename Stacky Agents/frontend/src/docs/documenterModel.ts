/**
 * Plan 113 — Modelo puro del Documentador 1-click (sin React, sin DOM).
 * Deriva un resumen presentable del estado del run para el panel de resultado.
 */
import type { DocumenterStatusResponse, DocumenterHealth } from "../api/endpoints";

export type DocumenterUiState = "running" | "completed" | "failed" | "decided" | "unknown";

export interface DocumenterSummary {
  uiState: DocumenterUiState;
  running: boolean;
  degraded: boolean;
  writtenCount: number;
  skippedCount: number;
  branch: string | null;
  currentMode: string | null;
  /** Fix "no me hizo nada" (Tarea 2) — execution_id en curso, para enganchar
   *  la consola en vivo (CodexConsoleDock) mientras el run está corriendo. */
  currentExecutionId: number | null;
  /** Fix "no me hizo nada" (Tarea 1) — motivo visible cuando el run completó
   *  sin escribir nada (antes 100% silencioso). */
  errorMessage: string | null;
  diffStat: string;
  healthDelta: string;
}

/** Mapea el `state` crudo del backend a un estado de UI acotado. */
export function summarizeDocumenterStatus(
  status: DocumenterStatusResponse | null | undefined
): DocumenterSummary {
  const raw = (status?.state || "").toLowerCase();
  let uiState: DocumenterUiState = "unknown";
  if (raw === "running") uiState = "running";
  else if (raw === "completed") uiState = "completed";
  else if (raw === "failed") uiState = "failed";
  else if (raw.startsWith("decided")) uiState = "decided";

  return {
    uiState,
    running: uiState === "running",
    degraded: Boolean(status?.degraded),
    writtenCount: status?.written?.length ?? 0,
    skippedCount: status?.skipped?.length ?? 0,
    branch: status?.branch ?? null,
    currentMode: status?.current_mode ?? null,
    currentExecutionId: status?.current_execution_id ?? null,
    errorMessage: status?.error ?? null,
    diffStat: status?.diff_stat ?? "",
    healthDelta: healthDelta(status?.health_before ?? null, status?.health_after ?? null),
  };
}

/** Describe la mejora (o no) de la salud documental en texto llano. */
export function healthDelta(
  before: DocumenterHealth | null,
  after: DocumenterHealth | null
): string {
  const b = before?.status;
  const a = after?.status;
  if (!b || !a) return "";
  if (b === a) return `Sin cambio de categoría (${a}).`;
  return `${b} → ${a}`;
}
