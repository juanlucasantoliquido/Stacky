/**
 * deploymentsModel.test.ts — Plan 120 F7/F8. Helpers puros, sin render.
 */
import { describe, it, expect } from 'vitest';
import {
  buildTargetCards,
  cardStatus,
  rollbackChoices,
  confirmRequirement,
  waveOrder,
  formatDora,
  buildPendingPresetHandoff,
  consumePendingPreset,
  showCreatePipelineCta,
  type DeployApp,
  type LedgerEntry,
} from './deploymentsModel';

const NOW = new Date('2026-07-10T15:00:00Z');

function entry(overrides: Partial<LedgerEntry> = {}): LedgerEntry {
  return {
    run_id: 'dr-1',
    app_id: 'miapp',
    target: '__local__',
    action: 'deploy',
    version_id: 'v1',
    status: 'success',
    steps: [],
    started_at: '2026-07-10T14:00:00Z',
    finished_at: '2026-07-10T14:05:00Z',
    error: null,
    ...overrides,
  };
}

const APP: DeployApp = {
  id: 'miapp',
  artifact: { kind: 'folder', path: 'C:\\build\\out' },
  targets: {
    __local__: {
      install_path: 'D:\\apps\\miapp',
      smoke: { kind: 'none', url: null, command: null },
      pre_switch: null, post_switch: null, protected: false,
    },
  },
};

describe('buildTargetCards', () => {
  it('Local va SIEMPRE primero', () => {
    const cards = buildTargetCards(APP, [{ alias: 'srv1' }, { alias: 'srv2' }], {}, NOW);
    expect(cards[0].key).toBe('__local__');
    expect(cards.map((c) => c.key)).toEqual(['__local__', 'srv1', 'srv2']);
  });

  it('server registrado sin config de la app => card "sin asignar" (configured=false)', () => {
    const cards = buildTargetCards(APP, [{ alias: 'srv1' }], {}, NOW);
    const srv1 = cards.find((c) => c.key === 'srv1')!;
    expect(srv1.configured).toBe(false);
    expect(srv1.canRollback).toBe(false);
  });

  it('destino configurado con ultimo entry refleja version y status', () => {
    const cards = buildTargetCards(
      APP, [],
      { __local__: entry({ status: 'success', version_id: 'v9' }) },
      NOW,
    );
    expect(cards[0].version).toBe('v9');
    expect(cards[0].status).toBe('ok');
    expect(cards[0].deployedAgo).toContain('hace');
  });
});

describe('cardStatus', () => {
  it('cubre los 8 estados', () => {
    expect(cardStatus(null)).toBe('nunca');
    expect(cardStatus(entry({ status: 'success' }), undefined)).toBe('ok');
    expect(cardStatus(entry({ status: 'failed' }))).toBe('failed');
    expect(cardStatus(entry({ status: 'failed_smoke' }))).toBe('failed_smoke');
    expect(cardStatus(entry({ status: 'running' }))).toBe('running');
    expect(cardStatus(entry({ status: 'running', effective_status: 'stale' }))).toBe('stale');
    expect(cardStatus(entry({ status: 'success' }), 'drift')).toBe('drift');
    expect(cardStatus(entry({ status: 'success' }), 'unknown')).toBe('desconocido');
  });
});

describe('rollbackChoices', () => {
  it('excluye fallidas y la version ACTIVA (la mas reciente exitosa)', () => {
    const history: LedgerEntry[] = [
      entry({ run_id: 'r4', status: 'success', version_id: 'v4', finished_at: '2026-07-10T14:00:00Z' }), // activa
      entry({ run_id: 'r3', status: 'failed', version_id: 'v3', finished_at: '2026-07-09T14:00:00Z' }),
      entry({ run_id: 'r2', status: 'success', version_id: 'v2', finished_at: '2026-07-08T14:00:00Z' }),
      entry({ run_id: 'r1', status: 'success', version_id: 'v1', finished_at: '2026-07-07T14:00:00Z' }),
    ];
    const choices = rollbackChoices(history, 3);
    expect(choices.map((c) => c.version)).toEqual(['v2', 'v1']);
  });

  it('respeta el tope `retain`', () => {
    const history: LedgerEntry[] = [
      entry({ run_id: 'r3', status: 'success', version_id: 'v3', finished_at: '2026-07-10T14:00:00Z' }),
      entry({ run_id: 'r2', status: 'success', version_id: 'v2', finished_at: '2026-07-09T14:00:00Z' }),
      entry({ run_id: 'r1', status: 'success', version_id: 'v1', finished_at: '2026-07-08T14:00:00Z' }),
    ];
    expect(rollbackChoices(history, 1).map((c) => c.version)).toEqual(['v2']);
  });
});

describe('confirmRequirement', () => {
  it('destino protected exige texto == app_id', () => {
    expect(confirmRequirement({ protected: true }, 'miapp')).toEqual({ kind: 'text', expected: 'miapp' });
  });

  it('destino no protegido: checkbox simple', () => {
    expect(confirmRequirement({ protected: false }, 'miapp')).toEqual({ kind: 'checkbox' });
    expect(confirmRequirement(undefined, 'miapp')).toEqual({ kind: 'checkbox' });
  });
});

describe('waveOrder', () => {
  it('preserva el orden de seleccion del operador, sin duplicados', () => {
    expect(waveOrder(['srv2', 'srv1', 'srv2', '__local__'])).toEqual(['srv2', 'srv1', '__local__']);
  });
});

describe('formatDora', () => {
  it('formatea porcentajes y minutos, con guion cuando no hay datos', () => {
    const chips = formatDora({
      deploys_7d: 2, deploys_30d: 5, change_failure_rate_30d: 0.2, mttr_minutes_30d: 45, last_deploy_at: null,
    });
    expect(chips).toEqual([
      { label: 'Deploys (7d)', value: '2' },
      { label: 'Deploys (30d)', value: '5' },
      { label: 'Change failure rate (30d)', value: '20%' },
      { label: 'MTTR (30d)', value: '45 min' },
    ]);
  });

  it('sin datos -> guion, sin division por cero', () => {
    const chips = formatDora({
      deploys_7d: 0, deploys_30d: 0, change_failure_rate_30d: null, mttr_minutes_30d: null, last_deploy_at: null,
    });
    expect(chips.find((c) => c.label.includes('Change'))?.value).toBe('—');
    expect(chips.find((c) => c.label.includes('MTTR'))?.value).toBe('—');
  });
});

describe('buildPendingPresetHandoff (F8)', () => {
  it('stack conocido -> handoff con presetId', () => {
    expect(buildPendingPresetHandoff('node')).toEqual({ presetId: 'node' });
  });

  it('sin stack (null) -> null', () => {
    expect(buildPendingPresetHandoff(null)).toBeNull();
  });
});

describe('consumePendingPreset (F8)', () => {
  it('lee y parsea el valor guardado en localStorage', () => {
    expect(consumePendingPreset(JSON.stringify({ presetId: 'node' }))).toEqual({ presetId: 'node' });
  });

  it('valor ausente/corrupto -> null (one-shot no rompe)', () => {
    expect(consumePendingPreset(null)).toBeNull();
    expect(consumePendingPreset('{not json')).toBeNull();
    expect(consumePendingPreset('{}')).toBeNull();
  });
});

describe('showCreatePipelineCta (F8)', () => {
  it('visible solo con stack_detect_enabled', () => {
    expect(showCreatePipelineCta({ stack_detect_enabled: true })).toBe(true);
    expect(showCreatePipelineCta({ stack_detect_enabled: false })).toBe(false);
    expect(showCreatePipelineCta(null)).toBe(false);
    expect(showCreatePipelineCta(undefined)).toBe(false);
  });
});
