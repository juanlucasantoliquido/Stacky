/**
 * Plan 131 F7 — Lógica PURA del resolutor de incidencias (testeable sin DOM).
 */

export interface IncidentStatusDTO {
  enabled: boolean;
  max_files: number;
  max_file_mb: number;
  allowed_extensions: string[];
}

export interface IncidentFileDTO {
  name: string;
  stored_name: string;
  bytes: number;
  ext: string;
  kind: "image" | "text" | "binary";
  sha256: string;
}

export type IncidentStatusValue =
  | "capturada"
  | "analizando"
  | "analizada"
  | "publicada"
  | "error";

export interface IncidentDTO {
  id: string;
  created_at: string;
  text: string;
  files: IncidentFileDTO[];
  status: IncidentStatusValue;
  execution_id: number | null;
  tracker_id: string | null;
  tracker_url: string | null;
  epic_id: number | null;
  doc_path: string | null;
  error: string | null;
  title?: string | null;
}

export interface IncidentRelatedEpicDTO {
  epic_id: number | null;
  confidence: number | null;
  reason: string | null;
}

export interface IncidentPreviewDTO {
  ok: boolean;
  title?: string | null;
  html?: string | null;
  related_epic?: IncidentRelatedEpicDTO | null;
  publishable: boolean;
  error?: string | null;
}

/** Espejo cliente de los límites §4.1 (backend/services/incident_store.py). */
export function validateFiles(
  files: { name: string; size: number }[],
  status: IncidentStatusDTO
): { ok: boolean; errors: string[] } {
  const errors: string[] = [];

  if (files.length > status.max_files) {
    errors.push(`Máximo ${status.max_files} archivos (subiste ${files.length}).`);
  }

  const maxBytes = status.max_file_mb * 1024 * 1024;
  for (const f of files) {
    const dotIdx = f.name.lastIndexOf(".");
    const ext = dotIdx >= 0 ? f.name.slice(dotIdx).toLowerCase() : "";
    if (!status.allowed_extensions.includes(ext)) {
      errors.push(`Extensión no permitida: ${f.name}`);
    }
    if (f.size > maxBytes) {
      errors.push(`Archivo demasiado grande (máx ${status.max_file_mb} MB): ${f.name}`);
    }
  }

  return { ok: errors.length === 0, errors };
}

/** Texto no vacío O al menos 1 archivo. */
export function canAnalyze(text: string, files: unknown[]): boolean {
  return text.trim().length > 0 || files.length > 0;
}

/** "Épica 267 — confianza 85% — <razón>" / "Sin épica relacionada". */
export function summarizeRelatedEpic(preview: IncidentPreviewDTO): string {
  const related = preview.related_epic;
  if (!related || related.epic_id === null || related.epic_id === undefined) {
    return "Sin épica relacionada";
  }
  let out = `Épica ${related.epic_id}`;
  if (related.confidence !== null && related.confidence !== undefined) {
    out += ` — confianza ${related.confidence}%`;
  }
  if (related.reason) {
    out += ` — ${related.reason}`;
  }
  return out;
}

/**
 * [ADICIÓN ARQUITECTO] La incidencia más reciente resumible: status en
 * (analizando|analizada), con execution_id y SIN tracker_id (no publicada).
 * Cubre reanudación tras cierre accidental del modal / runs zombie.
 */
export function pickResumableIncident(list: IncidentDTO[]): IncidentDTO | null {
  const candidates = list.filter(
    (i) =>
      (i.status === "analizando" || i.status === "analizada") &&
      i.execution_id !== null &&
      i.execution_id !== undefined &&
      !i.tracker_id
  );
  if (candidates.length === 0) return null;
  return candidates.reduce((latest, cur) =>
    cur.created_at > latest.created_at ? cur : latest
  );
}
