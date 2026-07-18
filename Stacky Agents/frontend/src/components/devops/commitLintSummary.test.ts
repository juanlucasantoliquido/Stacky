/**
 * commitLintSummary.test.ts — Plan 186 F6. Helper PURO del resumen del modal de commit.
 */
import { describe, it, expect } from 'vitest';
import { commitLintSummary, type LintReport } from './pipelineLint';

function report(error: number, warning: number, info = 0): LintReport {
  return {
    ok: error === 0,
    findings: [],
    counts: { error, warning, info },
    engine_version: '186.1',
    duration_ms: 1,
    fixes_omitted: false,
  };
}

describe('commitLintSummary', () => {
  it('undefined → tone none, sin label (modal intacto)', () => {
    const s = commitLintSummary(undefined);
    expect(s.tone).toBe('none');
    expect(s.confirmLabel).toBeNull();
    expect(s.text).toBe('');
  });

  it('2 errores → tone error + confirmLabel', () => {
    const s = commitLintSummary(report(2, 0));
    expect(s.tone).toBe('error');
    expect(s.confirmLabel).toBe('Publicar igual (2 errores)');
  });

  it('1 error → singular', () => {
    const s = commitLintSummary(report(1, 0));
    expect(s.confirmLabel).toBe('Publicar igual (1 error)');
  });

  it('solo warnings → tone warn, sin label', () => {
    const s = commitLintSummary(report(0, 3));
    expect(s.tone).toBe('warn');
    expect(s.confirmLabel).toBeNull();
  });

  it('limpio → tone ok', () => {
    const s = commitLintSummary(report(0, 0));
    expect(s.tone).toBe('ok');
    expect(s.text).toContain('186.1');
  });
});
