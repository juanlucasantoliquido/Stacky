/**
 * ciFailureTriage.ts — Plan 193 F1. Helpers PUROS del triage de fallos CI.
 * Sin React, sin red: sólo formateo/derivación testeable en vitest.
 */

export interface FailedJob {
  job_id: string;
  name: string;
  stage: string;
  web_url: string | null;
}

/** Nombre del archivo de descarga del log de un job. */
export function logFileName(jobId: string): string {
  return `ci-log-${jobId}.txt`;
}

/** Nota de truncado (null si no truncado). chars_total = largo ORIGINAL (pre-mask). */
export function truncationNote(truncated: boolean, charsTotal: number): string | null {
  if (!truncated) return null;
  return `Mostrando el final del log (${charsTotal.toLocaleString('es-AR')} caracteres en total).`;
}

/** Etiqueta legible de un job fallido: "stage · name". */
export function jobLabel(j: FailedJob): string {
  return `${j.stage} · ${j.name}`;
}

/** C1 — mensaje EXACTO cuando el pipeline falló pero no hay jobs fallidos (config error). */
export const EMPTY_FAILED_JOBS_MSG =
  'No se encontraron jobs fallidos (puede ser un error de configuración del pipeline — abrilo en el tracker)';

// [ADICIÓN ARQUITECTO] — índices 1-based de líneas con pinta de error (cap 200).
const ERROR_LINE_RE = /\b(error|failed|exception|fatal)\b/i;

export function errorLineHints(log: string): number[] {
  const out: number[] = [];
  const lines = (log || '').split('\n');
  for (let i = 0; i < lines.length && out.length < 200; i++) {
    if (ERROR_LINE_RE.test(lines[i])) out.push(i + 1);
  }
  return out;
}
