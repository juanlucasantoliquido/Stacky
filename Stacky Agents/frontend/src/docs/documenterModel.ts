/**
 * Plan 113 — Modelo puro del Documentador 1-click (sin React, sin DOM).
 * Deriva un resumen presentable del estado del run para el panel de resultado.
 */
import type {
  DocumenterStatusResponse,
  DocumenterHealth,
  DocumenterRunEntry,
} from "../api/endpoints";

export type DocumenterUiState =
  | "running"
  | "completed"
  | "failed"
  | "decided"
  /** Plan 284 F5.3 — el run se detuvo ANTES de escribir y espera al operador.
   *  Sin este estado el panel caía en "unknown" y no se renderizaba: los
   *  botones de aprobación existirían pero nadie los vería nunca. */
  | "awaiting_approval"
  | "unknown";

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
  else if (raw === "awaiting_approval") uiState = "awaiting_approval";  // Plan 284
  else if (raw === "budget_exhausted") uiState = "completed";           // Plan 284 A1
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
  // Plan 284 F3 — la razón trae el detalle ("citations_below_threshold:2/9"),
  // así que el mapeo es por PREFIJO, no por clave exacta.
  if (reason.startsWith("citations_below_threshold")) {
    const detail = reason.split(":")[1] ?? "";
    return `Rechazado: citas archivo:línea que no existen (${detail} verificadas)`;
  }
  return map[reason] ?? reason;
}

/** Plan 284 — normaliza la nota del operador antes de mandarla al backend.
 *  Devuelve undefined si no hay nada que mandar (así el body queda como el de hoy). */
export function normalizeOperatorNote(raw: string, maxChars = 4000): string | undefined {
  const trimmed = (raw ?? "").trim();
  if (!trimmed) return undefined;
  return trimmed.slice(0, maxChars);
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


// ---------------------------------------------------------------------------
// Plan 284 F7 — la salida se entiende: veredicto arriba, etapas con su estado,
// cobertura y triage en texto llano. Lógica PURA (sin React, sin DOM): RTL y
// jsdom no están instalados en este repo, así que lo testeable vive acá.
// ---------------------------------------------------------------------------

/** Orden canónico de las 5 etapas. Espeja STAGE_ORDER del backend. */
export const STAGE_ORDER_UI = [
  "PROPONER",
  "CRITICAR",
  "MEJORAR",
  "IMPLEMENTAR",
  "VERIFICAR",
] as const;

const STAGE_LABELS: Record<string, string> = {
  PROPONER: "Proponer",
  CRITICAR: "Criticar",
  MEJORAR: "Mejorar",
  IMPLEMENTAR: "Implementar",
  VERIFICAR: "Verificar",
};

const STAGE_STATE_LABELS: Record<string, string> = {
  pending: "Pendiente",
  running: "En curso",
  done: "Hecha",
  skipped: "Salteada",
  failed: "Falló",
  awaiting_approval: "Esperando tu aprobación",
};

export interface StageView {
  stage: string;
  label: string;
  state: string;
  badge: string;
  summary: string;
}

/** Plan 284 — filas de etapa en el orden canónico, incluso las que no llegaron
 *  a correr (esas quedan en "pending"). Siempre devuelve 5 filas. */
export function buildStagesView(
  status: DocumenterStatusResponse | null | undefined
): StageView[] {
  const porEtapa = new Map<string, { state?: string; summary?: string }>();
  for (const s of status?.stages ?? []) {
    if (s && typeof s.stage === "string") porEtapa.set(s.stage, s);
  }
  return STAGE_ORDER_UI.map((stage) => {
    const encontrada = porEtapa.get(stage);
    const state = encontrada?.state ?? "pending";
    return {
      stage,
      label: STAGE_LABELS[stage] ?? stage,
      state,
      badge: STAGE_STATE_LABELS[state] ?? state,
      summary: encontrada?.summary ?? "",
    };
  });
}

export interface VerdictView {
  verdict: string;
  label: string;
  tone: "ok" | "warn" | "bad";
  detail: string;
}

/** Plan 284 — veredicto legible. Sin veredicto => "Sin veredicto", tone "warn". */
export function buildVerdictView(
  status: DocumenterStatusResponse | null | undefined
): VerdictView {
  const verdict = (status?.verdict ?? "").trim();
  switch (verdict) {
    case "RADIOGRAFIA_COMPLETA":
      return {
        verdict,
        label: "Radiografía completa",
        tone: "ok",
        detail: "Todos los archivos pasaron la verificación de citas.",
      };
    case "RADIOGRAFIA_PARCIAL":
      return {
        verdict,
        label: "Radiografía parcial",
        tone: "warn",
        detail: "Se escribió documentación, pero quedó terreno sin cubrir.",
      };
    case "INSUFICIENTE":
      return {
        verdict,
        label: "Insuficiente: revisá los rechazos",
        tone: "bad",
        detail: "No se escribió nada útil o se rechazaron más archivos de los que se escribieron.",
      };
    case "PENDIENTE_DE_APROBACION":
      return {
        verdict,
        label: "Esperando tu aprobación",
        tone: "warn",
        detail: "El Documentador ya planeó y se autocriticó. No escribió nada todavía.",
      };
    default:
      return { verdict: "", label: "Sin veredicto", tone: "warn", detail: "" };
  }
}

export interface RadiographyView {
  coverageLabel: string;
  uncovered: string[];
  classLabel: string;
  ticketsLabel: string;
  deltaLabel: string;
}

/** Plan 284 — resumen de radiografía + minería de tickets en texto llano. */
export function buildRadiographyView(
  status: DocumenterStatusResponse | null | undefined
): RadiographyView {
  const r = status?.radiography ?? {};
  const total = r.modules_total ?? 0;
  const cubiertos = r.modules_covered ?? 0;
  const pct = Math.round((r.coverage_ratio ?? 0) * 100);
  const coverageLabel =
    total === 0
      ? "Sin módulos que cubrir"
      : `Cobertura ${cubiertos} de ${total} módulos (${pct}%)`;

  const porClase = r.by_doc_class ?? {};
  const classLabel = Object.keys(porClase).length
    ? Object.entries(porClase)
        .filter(([, n]) => (n ?? 0) > 0)
        .map(([clase, n]) => `${clase}: ${n}`)
        .join(" · ")
    : "";

  const m = status?.ticket_mining ?? {};
  const ticketsLabel =
    m.enabled === false
      ? "Minería de tickets desactivada"
      : `${m.total ?? 0} tickets barridos — ${m.signal ?? 0} aportaron historia, ${m.noise ?? 0} descartados`;

  // A2 — la derivada es lo que vuelve esto una radiografía y no una foto.
  const d = status?.radiography_delta ?? {};
  let deltaLabel = "";
  if (d.has_previous === true) {
    const pts = Math.round((d.ratio_delta ?? 0) * 100);
    const signo = pts > 0 ? `+${pts}` : `${pts}`;
    const cerrados = (d.modules_closed ?? []).length;
    deltaLabel = `${signo} pts desde el run anterior`;
    if (cerrados > 0) deltaLabel += ` — cerraste ${cerrados} módulo(s)`;
  }

  return { coverageLabel, uncovered: r.uncovered ?? [], classLabel, ticketsLabel, deltaLabel };
}

// ---------------------------------------------------------------------------
// Plan 285 F1.2 — el operador ve el estado del corpus en vez de adivinarlo.
//
// La lógica vive acá y no en el .tsx porque RTL/jsdom NO están instalados: un
// .test.tsx con RTL reporta "no tests" y sale con código 0, o sea un falso
// verde perfecto. Toda la lógica de UI va en .ts puro y se testea de verdad.
// ---------------------------------------------------------------------------

export interface CorpusView {
  visible: boolean;
  label: string;
  tone: "ok" | "warn";
}

/** Estado del corpus documental del proyecto, en texto llano.
 *  Los números salen SIEMPRE del dato, nunca de un literal: un conteo
 *  hardcodeado envejece solo (el árbol pasó de 240 a 241 planes en un día). */
export function buildCorpusView(
  corpus: DocumenterStatusResponse["corpus"] | null | undefined
): CorpusView {
  if (corpus === undefined || corpus === null) {
    return { visible: false, label: "", tone: "ok" };
  }
  if (corpus.enabled === false) {
    return {
      visible: true,
      tone: "warn",
      label: "Indexado del corpus desactivado: el Documentador no consulta la documentación ya escrita",
    };
  }
  const err = (corpus.error ?? "").trim();
  if (err) {
    const humano =
      err === "sin_workspace_root"
        ? "el proyecto no tiene carpeta de trabajo configurada"
        : err;
    return {
      visible: true,
      tone: "warn",
      label: `No se pudo indexar la documentación del proyecto: ${humano}`,
    };
  }
  const chunks = corpus.chunks_indexed ?? 0;
  if (chunks === 0) {
    return {
      visible: true,
      tone: "warn",
      label: "Corpus vacío: el Documentador no tiene documentación del proyecto que consultar",
    };
  }
  const archivos = corpus.files_scanned ?? 0;
  const planes = corpus.skipped_plans ?? 0;
  return {
    visible: true,
    tone: "ok",
    label: `Corpus: ${chunks} fragmentos de ${archivos} documentos indexados (${planes} planes excluidos)`,
  };
}

// ---------------------------------------------------------------------------
// Plan 285 F3.3 — el descarte de tickets deja de ser invisible.
// ---------------------------------------------------------------------------

export interface TriageReasonRow {
  reason: string;
  count: number;
  human: string;
}

export interface TriageNoiseRow {
  id: string;
  tracker: string;
  title: string;
  score: number;
  reasons: string[];
}

export interface TriageView {
  visible: boolean;
  headline: string;
  truncatedWarning: string;
  reasonRows: TriageReasonRow[];
  noiseRows: TriageNoiseRow[];
}

/** Traduce un motivo interno del triage a texto llano.
 *  Todo motivo desconocido cae en un default legible que muestra el string
 *  crudo: nunca se pierde información por un mapeo incompleto. */
export function formatTriageReason(reason: string): string {
  const clave = (reason ?? "").split(":")[0];
  const map: Record<string, string> = {
    sin_descripcion: "Sin descripción",
    titulo_ruido: "Título de prueba o descartable",
    ticket_interno_de_stacky: "Ticket interno de Stacky (id negativo)",
    tracker_sintetico: "Tracker de demostración",
    cerrado_sin_contenido: "Cerrado sin descripción",
    descripcion_suficiente: "Descripción mínima",
    descripcion_extensa: "Descripción extensa",
    titulo_descriptivo: "Título descriptivo",
    tipo_jerarquico: "Épica o funcionalidad",
    cerrado_y_documentado: "Cerrado y bien descrito",
  };
  return map[clave] ?? clave ?? reason;
}

/** Resumen del descarte de tickets, para el panel. */
export function buildTriageView(
  ticketMining: DocumenterStatusResponse["ticket_mining"] | null | undefined
): TriageView {
  const vacio: TriageView = {
    visible: false, headline: "", truncatedWarning: "",
    reasonRows: [], noiseRows: [],
  };
  const m = ticketMining;
  if (m === undefined || m === null) return vacio;
  const muestra = m.noise_sample ?? [];
  const conteos = m.reason_counts ?? {};
  if (muestra.length === 0 && Object.keys(conteos).length === 0) return vacio;

  const total = m.total ?? 0;
  const signal = m.signal ?? 0;
  const noise = m.noise ?? 0;
  const headline = `${noise} de ${total} tickets descartados — ${signal} aportaron historia`;

  const totalRows = m.total_rows ?? total;
  const truncatedWarning =
    m.truncated === true
      ? `Barrido incompleto: se leyeron ${total} de ${totalRows} tickets. La cobertura de la historia NO es total.`
      : "";

  const reasonRows: TriageReasonRow[] = Object.entries(conteos)
    .map(([reason, count]) => ({
      reason,
      count: count ?? 0,
      human: formatTriageReason(reason),
    }))
    .sort((a, b) => b.count - a.count);

  const noiseRows: TriageNoiseRow[] = muestra.map((t) => ({
    id: String(t.external_id ?? t.ticket_id ?? "?"),
    tracker: t.tracker_type || "desconocido",
    title: t.title || "(sin título)",
    score: t.score ?? 0,
    reasons: (t.reasons ?? []).map(formatTriageReason),
  }));

  return { visible: true, headline, truncatedWarning, reasonRows, noiseRows };
}
