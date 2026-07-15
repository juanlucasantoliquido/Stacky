/**
 * Plan 113 — Modelo puro del Documentador 1-click (sin React, sin DOM).
 * Deriva un resumen presentable del estado del run para el panel de resultado.
 */
import type {
  DocumenterStatusResponse,
  DocumenterHealth,
  DocumenterRunEntry,
} from "../api/endpoints";

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

// ---------------------------------------------------------------------------
// Plan 137 F6 — panel de revisión: razones de skip en castellano, preview +
// citas por archivo, y vista del historial persistido (Corridas anteriores).
// ---------------------------------------------------------------------------

/** Traduce una razón cruda de skip (backend) a castellano llano. Clave
 * desconocida → se devuelve tal cual (nunca oculta información). */
export function formatSkipReason(reason: string): string {
  const map: Record<string, string> = {
    unsafe_path: "Ruta insegura (fuera del repo)",
    canonical_readonly: "docs/sistema/ es de solo lectura",
    missing_confidence_marks: "Sin marcas [V]/[INF]/[NV]",
    max_files_cap: "Superó el tope de archivos del run",
  };
  if (reason.startsWith("write_error:")) return "Error de escritura";
  return map[reason] ?? reason;
}

export interface DocumenterFileView {
  path: string;
  action: string;
  preview: string;
  citationsLabel: string;
  citationsBad: string[];
}

/** Vista de archivos escritos con preview + citas, para el panel de revisión.
 * status/files ausente o no-array → []  (nunca lanza). */
export function buildFilesView(
  status: DocumenterStatusResponse | null | undefined
): DocumenterFileView[] {
  const files = status?.files;
  if (!Array.isArray(files)) return [];
  return files.map((f) => {
    const citations = f.citations;
    return {
      path: f.path,
      action: f.action,
      preview: f.content_preview ?? "",
      citationsLabel: citations ? `${citations.ok}/${citations.total} citas verificadas` : "",
      citationsBad: citations?.bad ?? [],
    };
  });
}

/** Vista de archivos saltados por apply_proposals, con razón traducida.
 * status/skipped ausente o no-array → [] (nunca lanza). */
export function buildSkippedView(
  status: DocumenterStatusResponse | null | undefined
): { path: string; label: string }[] {
  const skipped = status?.skipped;
  if (!Array.isArray(skipped)) return [];
  return skipped.map(([path, reason]) => ({ path, label: formatSkipReason(reason) }));
}

export interface DocumenterRunRow {
  runId: string;
  state: string;
  branch: string;
  countsLabel: string;
  citationsLabel: string;
  mtimeIso: string;
}

/** Vista del historial persistido (C4 — el endpoint de historial no puede
 * quedar sin superficie de UI). Acepta tanto `{ok, runs: [...]}` (la forma
 * real de Docs.documenterRuns()) como un array directo; cualquier otra forma
 * (null, {}, runs no-array) → [] (nunca lanza). */
export function buildRunsView(runs: unknown): DocumenterRunRow[] {
  let list: unknown = runs;
  if (runs && typeof runs === "object" && !Array.isArray(runs) && "runs" in runs) {
    list = (runs as { runs?: unknown }).runs;
  }
  if (!Array.isArray(list)) return [];
  return list.map((entry) => {
    const run = (entry ?? {}) as Partial<DocumenterRunEntry>;
    const citationsTotal = run.citations_total ?? 0;
    return {
      runId: run.run_id ?? "",
      state: run.state ?? "",
      branch: run.branch ?? "(degradado)",
      countsLabel: `${run.written_count ?? 0} escritos · ${run.skipped_count ?? 0} saltados`,
      citationsLabel: citationsTotal ? `citas ${run.citations_ok ?? 0}/${citationsTotal}` : "",
      mtimeIso: run.mtime_iso ?? "",
    };
  });
}
