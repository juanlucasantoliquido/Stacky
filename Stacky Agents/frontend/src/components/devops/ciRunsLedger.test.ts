/**
 * ciRunsLedger.test.ts — Plan 191 F2. Tests puros (vitest, sin @testing-library).
 */
import { describe, it, expect } from 'vitest';
import {
  pollTargets,
  retriggerPayload,
  runLabel,
  effectiveStatus,
  POLL_INTERVAL_MS,
  MAX_POLL_TARGETS,
  type CiRun,
} from './ciRunsLedger';

function mkRun(overrides: Partial<CiRun> = {}): CiRun {
  return {
    project: 'p',
    tracker_type: 'gitlab',
    ref: 'develop',
    sha: 'abc',
    pipeline_id: '1',
    web_url: null,
    triggered_at: '2024-01-01T00:00:00+00:00',
    source: 'stacky',
    ...overrides,
  };
}

describe('pollTargets (KPI-4)', () => {
  it('excluye estados finales del mapa statusById', () => {
    const runs = [
      mkRun({ pipeline_id: 'a' }),
      mkRun({ pipeline_id: 'b' }),
      mkRun({ pipeline_id: 'c' }),
    ];
    const statusById = { a: 'running', b: 'success', c: 'pending' };
    expect(pollTargets(runs, statusById)).toEqual(['a', 'c']);
  });

  it('capea a MAX_POLL_TARGETS (5) y respeta el orden de entrada', () => {
    const runs = Array.from({ length: 8 }, (_, i) => mkRun({ pipeline_id: `p${i}` }));
    const result = pollTargets(runs, {});
    expect(result).toHaveLength(MAX_POLL_TARGETS);
    expect(result).toEqual(['p0', 'p1', 'p2', 'p3', 'p4']);
  });

  it('usa last_status persistido: un run terminado NO se pollea al montar (ADICIÓN)', () => {
    const runs = [
      mkRun({ pipeline_id: 'done', last_status: 'success' }),
      mkRun({ pipeline_id: 'live', last_status: 'running' }),
      mkRun({ pipeline_id: 'fresh' }), // sin last_status → se pollea
    ];
    expect(pollTargets(runs, {})).toEqual(['live', 'fresh']);
  });

  it('el poll fresco de statusById pisa al last_status persistido', () => {
    const runs = [mkRun({ pipeline_id: 'x', last_status: 'running' })];
    expect(pollTargets(runs, { x: 'success' })).toEqual([]);
  });
});

describe('retriggerPayload (KPI-5)', () => {
  it('NO contiene la clave confirm', () => {
    const payload = retriggerPayload(mkRun({ ref: 'main' }));
    expect('confirm' in payload).toBe(false);
    expect(payload).toEqual({ ref: 'main' });
  });
});

describe('effectiveStatus', () => {
  it('prefiere el poll fresco, luego last_status, luego "desconocido"', () => {
    const run = mkRun({ pipeline_id: 'z', last_status: 'running' });
    expect(effectiveStatus(run, { z: 'failed' })).toBe('failed');
    expect(effectiveStatus(run, {})).toBe('running');
    expect(effectiveStatus(mkRun({ pipeline_id: 'q' }), {})).toBe('desconocido');
  });
});

describe('runLabel + constantes', () => {
  it('formato exacto', () => {
    expect(runLabel(mkRun({ ref: 'main', pipeline_id: '7', triggered_at: '2024-05-01T10:00:00+00:00' })))
      .toBe('main · #7 · 2024-05-01T10:00:00+00:00');
  });
  it('POLL_INTERVAL_MS = 10000', () => {
    expect(POLL_INTERVAL_MS).toBe(10_000);
  });
});
