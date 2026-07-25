import { describe, it, expect } from 'vitest';
import {
  domainOf,
  groupByDomain,
  statusLabel,
  statusMark,
  summarize,
  type CapabilityRow,
} from '../parityMatrixModel';

function row(key: string, status: string, enabled = true): CapabilityRow {
  return { key, status, enabled, loss: '', owner_plan: null };
}

describe('parityMatrixModel — Plan 218 F8', () => {
  it('groupByDomain agrupa por el prefijo antes del primer punto', () => {
    const grupos = groupByDomain([
      row('tracker.items.list', 'full'),
      row('mr.approve', 'absent'),
      row('tracker.items.get', 'full'),
      row('ci.job.log', 'full'),
    ]);

    expect(grupos.map(([dom]) => dom)).toEqual(['tracker', 'mr', 'ci']);
    expect(grupos[0][1].map((c) => c.key)).toEqual([
      'tracker.items.list',
      'tracker.items.get',
    ]);
  });

  it('domainOf tolera claves sin punto', () => {
    expect(domainOf('tracker.items.list')).toBe('tracker');
    expect(domainOf('suelta')).toBe('suelta');
  });

  it('summarize cuenta los 4 estados', () => {
    const resumen = summarize([
      row('a.b', 'full'),
      row('a.c', 'partial'),
      row('a.d', 'absent'),
      row('a.e', 'n/a'),
      row('a.f', 'full'),
    ]);
    expect(resumen).toEqual({ full: 2, partial: 1, absent: 1, na: 1 });
  });

  it('statusLabel mapea los 4 sin caer en undefined', () => {
    expect(statusLabel('full')).toBe('Completa');
    expect(statusLabel('partial')).toBe('Parcial');
    expect(statusLabel('absent')).toBe('Ausente');
    expect(statusLabel('n/a')).toBe('No aplica');
    expect(statusLabel('cualquier-cosa')).toBe('Ausente');
  });

  it('statusMark da una marca NO cromática por estado', () => {
    const marcas = ['full', 'partial', 'absent', 'n/a'].map(statusMark);
    expect(new Set(marcas).size).toBe(4);
    expect(marcas.every((m) => m.length > 0)).toBe(true);
  });

  it('tolera listas vacías', () => {
    expect(groupByDomain([])).toEqual([]);
    expect(summarize([])).toEqual({ full: 0, partial: 0, absent: 0, na: 0 });
  });
});
