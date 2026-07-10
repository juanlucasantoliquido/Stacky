import { describe, it, expect } from 'vitest';
import { worstStatus, actionableResults } from './connectionHealth';
import type { ConnectionsSnapshot, ConnectionDiagResult } from '../../api/endpoints';

function r(group: string, status: string): ConnectionDiagResult {
  return {
    target: group, target_label: group, group: group as any, status: status as any,
    code: '', detail: '', latency_ms: null, remediation: null,
  };
}

function snap(results: ConnectionDiagResult[]): ConnectionsSnapshot {
  return { generated_at: '', duration_ms: 0, results,
           summary: { ok: 0, warn: 0, fail: 0, skip: 0 } };
}

describe('Plan 116 — connectionHealth (pure)', () => {
  it('worstStatus picks fail over ok in a group', () => {
    const s = snap([r('tracker', 'ok'), r('tracker', 'fail')]);
    expect(worstStatus(s, 'tracker')).toBe('fail');
  });

  it('worstStatus is skip when group has no results', () => {
    expect(worstStatus(snap([r('clis', 'ok')]), 'servers')).toBe('skip');
    expect(worstStatus(null, 'tracker')).toBe('skip');
  });

  it('worstStatus warn over ok', () => {
    expect(worstStatus(snap([r('credentials', 'ok'), r('credentials', 'warn')]), 'credentials')).toBe('warn');
  });

  it('actionableResults keeps only fail and warn', () => {
    const s = snap([r('tracker', 'ok'), r('tracker', 'fail'), r('clis', 'skip'), r('servers', 'warn')]);
    const out = actionableResults(s);
    expect(out).toHaveLength(2);
    expect(out.map((x) => x.status).sort()).toEqual(['fail', 'warn']);
  });
});
