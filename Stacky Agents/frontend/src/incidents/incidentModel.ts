/**
 * Plan 131 F7 — Lógica PURA del resolutor de incidencias (testeable sin DOM).
 */

export interface IncidentStatusDTO {
  enabled: boolean;
  max_files: number;
  max_file_mb: number;
  allowed_extensions: string[];
  /** Plan 166 F3 — con true, el modal crea directo y en lote sin diálogos. */
  auto_publish_enabled?: boolean;
  /** Plan 166 F5 — con true, el board muestra "Resolver con agente" en las Issues. */
  dev_resolver_enabled?: boolean;
  /** Plan 177 — con true, el board muestra el checkbox "Abrir PR" junto al botón. */
  dev_pr_enabled?: boolean;
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

export interface IncidentRepairMetaDTO {
  attempted: boolean;
  reason: string;
  sent?: boolean;
  budget_exhausted?: boolean;
}

export interface IncidentPreconditionFailureDTO {
  check: string | null;
  detail: string | null;
}

export interface IncidentPreviewDTO {
  ok: boolean;
  title?: string | null;
  html?: string | null;
  related_epic?: IncidentRelatedEpicDTO | null;
  publishable: boolean;
  error?: string | null;
  repair?: IncidentRepairMetaDTO | null;
  detail?: IncidentPreconditionFailureDTO | null;
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

/** Item mínimo compatible con DataTransferItem (estructural: permite pasar un
 * DataTransferItem real del DOM o un mock en tests sin depender de jsdom). */
export interface ClipboardFileItem {
  kind: string;
  type: string;
  getAsFile: () => File | null;
}

/** MIME -> extensión, alineada 1:1 con IMAGE_EXTENSIONS del backend
 * (services/incident_store.py:27) para que validateFiles nunca rechace una
 * imagen pegada por extensión desconocida. Es un ALLOWLIST cerrado (C2):
 * un MIME image/* que no esté acá (p.ej. image/svg+xml, image/tiff) se
 * IGNORA en vez de renombrarse a .png — renombrar colaría por validateFiles
 * (que valida por extensión) contenido cuya extensión real el backend
 * rechaza, y SVG además es vector activo de scripting. Esos archivos siguen
 * pudiendo adjuntarse por selector/drag&drop, donde conservan su extensión
 * real y la validación existente decide. */
const CLIPBOARD_IMAGE_EXT: Record<string, string> = {
  "image/png": ".png",
  "image/jpeg": ".jpg",
  "image/gif": ".gif",
  "image/webp": ".webp",
  "image/bmp": ".bmp",
};

/**
 * Extrae SOLO los items de imagen del allowlist de un evento `paste`,
 * ignorando (sin bloquear) items no-imagen: texto (`kind === "string"`,
 * p.ej. el usuario pegando texto normal en el textarea) y archivos
 * no-imagen (p.ej. un PDF copiado desde el explorador junto con una
 * captura). Cada imagen se renombra "pegado-<timestamp>-<índice><ext>"
 * porque el navegador entrega clipboard images con nombres genéricos
 * ("image.png") que colisionarían en la lista de archivos si se pegan
 * varias veces. Pura salvo por `getAsFile()`/`Date.now()`; segura ante
 * lista vacía o `getAsFile()` que devuelve null.
 */
export function extractPastedImageFiles(items: ClipboardFileItem[]): File[] {
  const out: File[] = [];
  const ts = Date.now();
  items.forEach((item, idx) => {
    if (item.kind !== "file" || !item.type.startsWith("image/")) return;
    const ext = CLIPBOARD_IMAGE_EXT[item.type];
    if (!ext) return; // C2 — MIME image/* fuera del allowlist: ignorar.
    const file = item.getAsFile();
    if (!file) return;
    out.push(new File([file], `pegado-${ts}-${idx}${ext}`, { type: item.type }));
  });
  return out;
}
