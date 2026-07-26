/** Plan 248 F6 — modelo puro del panel de auditoría. Sin DOM, sin React, sin fetch.
 *  Espeja el estilo de components/devops/pipelineLint.ts SIN modificar ese archivo. */

export type AuditSeverity = 'error' | 'warning' | 'info';

export interface AuditFinding {
  code: string;
  severity: AuditSeverity;
  message: string;
  location: string;
  line: number | null;
  evidence: string;
  remediation: string;
  providers: string[];
  evidence_fingerprint: string;
}

export interface AuditReport {
  ok: boolean;
  findings: AuditFinding[];
  counts: Record<string, number>;
  suppressed: AuditFinding[];
  undetermined: number;
  undetermined_notes: string[];
  rules_version: string;
  mode: string;
  duration_ms: number;
}

export interface GroupedAudit {
  error: AuditFinding[];
  warning: AuditFinding[];
  info: AuditFinding[];
}

export const AUDIT_SEVERITIES: AuditSeverity[] = ['error', 'warning', 'info'];

/** Agrupa por severidad y ordena por (line, code) dentro de cada grupo. */
export function groupAuditFindings(fs: AuditFinding[]): GroupedAudit {
  const out: GroupedAudit = { error: [], warning: [], info: [] };
  (fs || []).forEach((f) => {
    if (out[f.severity]) out[f.severity].push(f);
  });
  AUDIT_SEVERITIES.forEach((sev) => {
    out[sev].sort((a, b) => {
      const la = a.line ?? Number.MAX_SAFE_INTEGER;
      const lb = b.line ?? Number.MAX_SAFE_INTEGER;
      if (la !== lb) return la - lb;
      return a.code.localeCompare(b.code);
    });
  });
  return out;
}

/** SEC* -> seguridad, OPT* -> optimizacion. */
export function familyOf(code: string): 'seguridad' | 'optimizacion' {
  return (code || '').toUpperCase().startsWith('SEC') ? 'seguridad' : 'optimizacion';
}

/** Resumen en 1 línea, es-AR. Nunca devuelve texto vacío. */
export function auditSummary(
  r: AuditReport | null,
): { tone: 'none' | 'ok' | 'warn' | 'bad'; text: string } {
  if (!r) return { tone: 'none', text: 'Todavia no se audito esta pipeline.' };
  const errores = r.counts?.error ?? 0;
  const avisos = r.counts?.warning ?? 0;
  const infos = r.counts?.info ?? 0;
  const partes: string[] = [];
  if (errores) partes.push(`${errores} riesgo(s) grave(s)`);
  if (avisos) partes.push(`${avisos} aviso(s)`);
  if (infos) partes.push(`${infos} recomendacion(es)`);
  let texto = partes.length ? partes.join(' · ') : 'Sin hallazgos.';
  if ((r.undetermined ?? 0) > 0) {
    texto += ` · la auditoria no pudo evaluar ${r.undetermined} punto(s)`;
  }
  let tone: 'ok' | 'warn' | 'bad' = 'ok';
  if (errores) tone = 'bad';
  else if (avisos) tone = 'warn';
  return { tone, text: texto };
}

/** HITL: nadie suprime sin escribir por qué. */
export function canSuppress(f: AuditFinding | null, reason: string): boolean {
  if (!f) return false;
  return (reason || '').trim() !== '';
}
