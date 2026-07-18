/**
 * pipelineLint.test.ts — Plan 186 F5. Helpers PUROS (sin @testing-library, node env).
 */
import { describe, it, expect } from 'vitest';
import { groupFindings, buildDiffLines, debounceKey, type LintFinding } from './pipelineLint';

function f(code: string, severity: LintFinding['severity'], line: number | null): LintFinding {
  return { code, severity, message: `${code} msg`, line, node: null, fix: null };
}

describe('groupFindings', () => {
  it('agrupa por severidad y ordena por línea', () => {
    const findings: LintFinding[] = [
      f('PL010', 'warning', 5),
      f('PL002', 'error', 8),
      f('PL001', 'error', 2),
      f('PL006', 'info', 3),
      f('PL011', 'warning', 1),
    ];
    const g = groupFindings(findings);
    expect(g.errors.map((x) => x.code)).toEqual(['PL001', 'PL002']);
    expect(g.warnings.map((x) => x.code)).toEqual(['PL011', 'PL010']);
    expect(g.infos.map((x) => x.code)).toEqual(['PL006']);
  });

  it('línea null va al final del grupo', () => {
    const g = groupFindings([f('PLb', 'error', null), f('PLa', 'error', 1)]);
    expect(g.errors.map((x) => x.code)).toEqual(['PLa', 'PLb']);
  });
});

describe('buildDiffLines', () => {
  it('marca 1 línea reemplazada y 2 insertadas', () => {
    const oldY = 'l1\nl2\nl3';
    const newY = 'l1\nl2X\nl3\nl4\nl5';
    const d = buildDiffLines(oldY, newY);
    // l2 eliminada, l2X/l4/l5 agregadas
    expect(d.removed.length).toBe(1);
    expect(d.added.length).toBe(3);
    const dels = d.rows.filter((r) => r.kind === 'del').map((r) => r.text);
    const adds = d.rows.filter((r) => r.kind === 'add').map((r) => r.text);
    expect(dels).toContain('l2');
    expect(adds).toEqual(expect.arrayContaining(['l2X', 'l4', 'l5']));
    // las iguales se preservan
    const sames = d.rows.filter((r) => r.kind === 'same').map((r) => r.text);
    expect(sames).toEqual(['l1', 'l3']);
  });

  it('YAML idéntico → cero add/del', () => {
    const d = buildDiffLines('a\nb', 'a\nb');
    expect(d.added).toEqual([]);
    expect(d.removed).toEqual([]);
  });
});

describe('debounceKey', () => {
  it('estable si no cambia nada', () => {
    expect(debounceKey('stages: []', 'ado')).toBe(debounceKey('stages: []', 'ado'));
  });

  it('cambia si cambia el yaml', () => {
    expect(debounceKey('a', 'ado')).not.toBe(debounceKey('b', 'ado'));
  });

  it('cambia si cambia la fuente', () => {
    expect(debounceKey('same', 'ado')).not.toBe(debounceKey('same', 'gitlab'));
  });
});
