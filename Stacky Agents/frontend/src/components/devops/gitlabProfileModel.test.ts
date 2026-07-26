import { describe, expect, it } from 'vitest';

import { groupFindings } from './pipelineLint';
import {
  GL_RULE_TITLES,
  groupSemantic,
  toLintFinding,
  type GitlabSemanticFinding,
} from './gitlabProfileModel';

function f(over: Partial<GitlabSemanticFinding> = {}): GitlabSemanticFinding {
  return {
    code: 'GL001',
    severity: 'error',
    message: 'el job b declara un stage que no esta en stages',
    location: 'b',
    evidence: 'stage: fantasma',
    ...over,
  };
}

describe('GL_RULE_TITLES', () => {
  it('cubre GL000..GL011', () => {
    for (let n = 0; n <= 11; n += 1) {
      const code = `GL${String(n).padStart(3, '0')}`;
      expect(GL_RULE_TITLES[code], code).toBeTruthy();
    }
    expect(Object.keys(GL_RULE_TITLES).length).toBe(12);
  });
});

describe('toLintFinding', () => {
  it('mapea location a node', () => {
    const lf = toLintFinding(f());
    expect(lf.node).toBe('b');
    expect(lf.severity).toBe('error');
    expect(lf.message).toBe(f().message);
    expect(lf.fix).toBeNull();
  });
});

describe('groupSemantic', () => {
  it('delega en groupFindings', () => {
    const fs = [f({ code: 'GL001' }), f({ code: 'GL002' }), f({ code: 'GL007', severity: 'warning' })];
    expect(groupSemantic(fs)).toEqual(groupFindings(fs.map(toLintFinding)));
    expect(groupSemantic(fs).errors.length).toBe(2);
    expect(groupSemantic(fs).warnings.length).toBe(1);
  });
});

describe('codigo desconocido', () => {
  it('no rompe el titulo', () => {
    expect(GL_RULE_TITLES['GL999']).toBeUndefined();
    expect(() => toLintFinding(f({ code: 'GL999' }))).not.toThrow();
  });
});
