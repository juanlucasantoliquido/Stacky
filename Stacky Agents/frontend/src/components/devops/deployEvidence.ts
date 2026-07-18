/**
 * deployEvidence.ts — Plan 188 F4.
 *
 * Helpers puros (sin DOM ni red) para el puente "run fallido → incidencia":
 * detectar estados fallidos y materializar la evidencia (markdown + JSON) como
 * adjuntos File con nombres que respetan ALLOWED_EXTENSIONS (.md / .json).
 */
export const FAILED_STATUSES = ['failed', 'failed_smoke'] as const;

export function isFailedStatus(s: string | undefined): boolean {
  return s === 'failed' || s === 'failed_smoke';
}

export function evidenceFileName(runId: string, ext: 'md' | 'json'): string {
  return `evidencia-${runId}.${ext}`;
}

export function evidenceToFiles(runId: string, markdown: string, jsonPayload: unknown): File[] {
  return [
    new File([markdown], evidenceFileName(runId, 'md'), { type: 'text/markdown' }),
    new File(
      [JSON.stringify(jsonPayload, null, 2)],
      evidenceFileName(runId, 'json'),
      { type: 'application/json' },
    ),
  ];
}
