import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import {
  auditSummary,
  canSuppress,
  familyOf,
  groupAuditFindings,
  type AuditFinding,
  type AuditReport,
} from '../pipelineAuditModel';

const HERE = dirname(fileURLToPath(import.meta.url));

function f(over: Partial<AuditFinding> = {}): AuditFinding {
  return {
    code: 'SEC003',
    severity: 'warning',
    message: 'm',
    location: 'steps[0]',
    line: 10,
    evidence: 'e',
    remediation: 'r',
    providers: ['ado'],
    evidence_fingerprint: 'abc',
    ...over,
  };
}

function report(over: Partial<AuditReport> = {}): AuditReport {
  return {
    ok: true,
    findings: [],
    counts: { error: 0, warning: 0, info: 0 },
    suppressed: [],
    undetermined: 0,
    undetermined_notes: [],
    rules_version: '248.1',
    mode: 'audit',
    duration_ms: 1,
    ...over,
  };
}

describe('groupAuditFindings', () => {
  it('ordena por (line, code) y separa las 3 severidades', () => {
    const g = groupAuditFindings([
      f({ code: 'SEC005', line: 20 }),
      f({ code: 'OPT002', severity: 'info', line: 5 }),
      f({ code: 'SEC003', line: 20 }),
      f({ code: 'SEC001', severity: 'error', line: 1 }),
    ]);
    expect(g.warning.map((x) => x.code)).toEqual(['SEC003', 'SEC005']);
    expect(g.error.map((x) => x.code)).toEqual(['SEC001']);
    expect(g.info.map((x) => x.code)).toEqual(['OPT002']);
  });

  it('los hallazgos sin linea van al final', () => {
    const g = groupAuditFindings([f({ code: 'SEC005', line: null }), f({ code: 'SEC003', line: 9 })]);
    expect(g.warning.map((x) => x.code)).toEqual(['SEC003', 'SEC005']);
  });
});

describe('familyOf', () => {
  it('separa seguridad de optimizacion', () => {
    expect(familyOf('SEC003')).toBe('seguridad');
    expect(familyOf('OPT002')).toBe('optimizacion');
  });
});

describe('auditSummary', () => {
  it('null da tono none', () => {
    expect(auditSummary(null).tone).toBe('none');
    expect(auditSummary(null).text.length).toBeGreaterThan(0);
  });

  it('sin hallazgos da ok, con warnings da warn, con errores da bad', () => {
    expect(auditSummary(report()).tone).toBe('ok');
    expect(auditSummary(report({ counts: { error: 0, warning: 2, info: 0 } })).tone).toBe('warn');
    expect(auditSummary(report({ counts: { error: 1, warning: 2, info: 0 } })).tone).toBe('bad');
  });

  it('menciona undetermined cuando es > 0', () => {
    const texto = auditSummary(report({ undetermined: 2 })).text;
    expect(texto).toContain('2');
    expect(texto).toContain('no pudo evaluar');
  });
});

describe('canSuppress', () => {
  it('es false con reason vacio o solo espacios', () => {
    expect(canSuppress(f(), '')).toBe(false);
    expect(canSuppress(f(), '   ')).toBe(false);
    expect(canSuppress(f(), 'ya lo evalue')).toBe(true);
    expect(canSuppress(null, 'motivo')).toBe(false);
  });
});

describe('montaje del panel', () => {
  it('la seccion esta registrada en DEVOPS_SECTIONS', () => {
    // Gate de C3: hace imposible repetir el "modulo sin call site" del Plan 176.
    // Se lee el FUENTE en vez de importar DevOpsPage.tsx (arrastra CSS modules y
    // el arbol entero del panel; el objetivo es probar el registro, no renderizar).
    const src = readFileSync(resolve(HERE, '../../pages/DevOpsPage.tsx'), 'utf-8');
    const entradas = src.match(/id:\s*'pipeline-audit'/g) || [];
    expect(entradas.length).toBe(1);
    expect(src).toContain("healthKey: 'pipeline_audit_enabled'");
    expect(src).toContain("gateFlagKey: 'STACKY_PIPELINE_AUDIT_ENABLED'");
    expect(src).toContain('PipelineAuditPanel');
    expect(src).toContain('pipeline_audit_enabled?: boolean');
  });
});
