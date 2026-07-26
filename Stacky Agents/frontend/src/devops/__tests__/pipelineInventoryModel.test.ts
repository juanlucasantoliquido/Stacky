import { describe, expect, it } from 'vitest';

import {
  categoryLabel,
  emptyStateMessage,
  filterEntries,
  groupByCategory,
  mismatchHint,
  statusLabel,
  summarize,
  triggerLabel,
  truncationNotices,
  unavailableSources,
  type InventoryCategory,
  type InventoryEntry,
  type InventoryLastRun,
  type InventoryPayload,
  type InventorySource,
  type InventoryTrigger,
} from '../pipelineInventoryModel';

const run = (over: Partial<InventoryLastRun> = {}): InventoryLastRun => ({
  status: 'success',
  status_detail: 'success',
  at: null,
  web_url: null,
  run_id: null,
  source: 'provider',
  ...over,
});

const trigger = (over: Partial<InventoryTrigger> = {}): InventoryTrigger => ({
  kind: 'default',
  branches: [],
  has_paths: false,
  has_schedule: false,
  has_pr: false,
  source: 'yaml',
  ...over,
});

const entry = (over: Partial<InventoryEntry> = {}): InventoryEntry => ({
  key: 'azure_devops::pipelines/ci.yml',
  provider: 'azure_devops',
  name: 'CI',
  yaml_path: 'pipelines/ci.yml',
  default_branch: 'main',
  definition_id: '7',
  category: 'registrada+en_repo',
  category_reason: '',
  last_run: run(),
  trigger: trigger(),
  found_in: ['ado_definitions', 'repo_scan'],
  hints: [],
  ...over,
});

const source = (over: Partial<InventorySource> = {}): InventorySource => ({
  id: 'ado_definitions',
  available: true,
  count: 1,
  capability: '',
  provider: '',
  reason: '',
  workaround: '',
  ...over,
});

const payload = (over: Partial<InventoryPayload> = {}): InventoryPayload => ({
  ok: true,
  generated_at: '2026-07-26T00:00:00+00:00',
  cached: false,
  cache_age_sec: 0,
  project: '',
  counts: { total: 0 },
  sources: [source(), source({ id: 'repo_scan' })],
  pipelines: [],
  ...over,
});

describe('statusLabel', () => {
  it('cubre los 4 estados', () => {
    expect(statusLabel(run({ status: 'success' }))).toEqual({ text: 'Verde', tone: 'ok' });
    expect(statusLabel(run({ status: 'failed' }))).toEqual({ text: 'Rojo', tone: 'bad' });
    expect(statusLabel(run({ status: 'never_ran' }))).toEqual({
      text: 'Nunca corrio',
      tone: 'faint',
    });
    expect(statusLabel(run({ status: 'unknown', status_detail: 'sin_datos' }))).toEqual({
      text: 'Desconocido',
      tone: 'warn',
    });
  });

  it('muestra el detalle cuando aporta', () => {
    expect(statusLabel(run({ status: 'unknown', status_detail: 'running' })).text).toContain(
      'running',
    );
    expect(statusLabel(run({ status: 'unknown', status_detail: 'sin_datos' })).text).not.toContain(
      'sin_datos',
    );
  });
});

describe('categoryLabel', () => {
  it('cubre las 3 categorias', () => {
    expect(categoryLabel('registrada+en_repo').tone).toBe('ok');
    expect(categoryLabel('registrada_sin_archivo').tone).toBe('bad');
    expect(categoryLabel('en_repo_sin_registrar').tone).toBe('warn');
    (
      ['registrada+en_repo', 'registrada_sin_archivo', 'en_repo_sin_registrar'] as InventoryCategory[]
    ).forEach((c) => {
      expect(categoryLabel(c).text.length).toBeGreaterThan(0);
      expect(categoryLabel(c).hint.length).toBeGreaterThan(0);
    });
  });

  it('cubre la cuarta categoria', () => {
    expect(categoryLabel('registrada_estado_desconocido').tone).toBe('faint');
    const conRojo = (
      [
        'registrada+en_repo',
        'en_repo_sin_registrar',
        'registrada_estado_desconocido',
      ] as InventoryCategory[]
    ).filter((c) => categoryLabel(c).tone === 'bad');
    expect(conRojo).toEqual([]);
  });
});

describe('triggerLabel', () => {
  it('default / none / ci', () => {
    expect(triggerLabel(trigger({ kind: 'default' }))).toBe('Toda rama (sin bloque trigger)');
    expect(triggerLabel(trigger({ kind: 'none' }))).toBe('Manual (trigger: none)');
    expect(triggerLabel(trigger({ kind: 'ci', branches: ['main'] }))).toBe('CI: main');
  });

  it('con ramas y paths', () => {
    const txt = triggerLabel(trigger({ kind: 'ci', branches: ['main'], has_paths: true }));
    expect(txt).toContain('main');
    expect(txt).toContain('[filtra paths]');
  });

  it('con ci y sin ramas', () => {
    expect(triggerLabel(trigger({ kind: 'ci', branches: [] }))).toBe('CI: sin ramas declaradas');
  });

  it('sufijos schedule y PR', () => {
    const txt = triggerLabel(
      trigger({ kind: 'ci', branches: ['main'], has_schedule: true, has_pr: true }),
    );
    expect(txt).toBe('CI: main + programado + PR');
  });

  it('unknown', () => {
    expect(triggerLabel(trigger({ kind: 'unknown' }))).toBe('Sin datos');
  });
});

describe('groupByCategory', () => {
  it('con las 3 categorias', () => {
    const a = entry({ key: 'a', category: 'registrada+en_repo' });
    const b = entry({ key: 'b', category: 'registrada_sin_archivo' });
    const c = entry({ key: 'c', category: 'en_repo_sin_registrar' });
    const d = entry({ key: 'd', category: 'registrada+en_repo' });
    const g = groupByCategory([a, b, c, d]);
    expect(g['registrada+en_repo'].map((e) => e.key)).toEqual(['a', 'd']);
    expect(g['registrada_sin_archivo'].map((e) => e.key)).toEqual(['b']);
    expect(g['en_repo_sin_registrar'].map((e) => e.key)).toEqual(['c']);
  });

  it('con lista vacia', () => {
    const g = groupByCategory([]);
    expect(Object.keys(g).length).toBe(4);
    Object.values(g).forEach((v) => expect(v).toEqual([]));
  });
});

describe('filterEntries', () => {
  const entries = [
    entry({ key: '1', name: 'Nightly Build', yaml_path: 'pipelines/nightly.yml' }),
    entry({ key: '2', name: 'Deploy', yaml_path: 'ci/deploy.yml', provider: 'gitlab' }),
  ];

  it('case-insensitive sobre 3 campos', () => {
    expect(filterEntries(entries, 'NIGHTLY').map((e) => e.key)).toEqual(['1']);
    expect(filterEntries(entries, 'ci/dep').map((e) => e.key)).toEqual(['2']);
    expect(filterEntries(entries, 'GITLAB').map((e) => e.key)).toEqual(['2']);
  });

  it('con query vacia devuelve todo', () => {
    expect(filterEntries(entries, '')).toEqual(entries);
    expect(filterEntries(entries, '   ')).toEqual(entries);
  });
});

describe('summarize', () => {
  it('con datos', () => {
    const p = payload({
      counts: { total: 12, registrada_sin_archivo: 2, en_repo_sin_registrar: 3 },
    });
    expect(summarize(p)).toBe('12 pipelines · 2 sin archivo · 3 huerfanas');
  });

  it('con cero', () => {
    expect(summarize(payload({ counts: { total: 0 } }))).toBe('Sin pipelines descubiertas');
  });

  it('con null', () => {
    expect(summarize(null).length).toBeGreaterThan(0);
  });
});

describe('unavailableSources', () => {
  it('filtra las caidas', () => {
    const p = payload({
      sources: [source(), source({ id: 'repo_scan', available: false, reason: 'sin workspace' })],
    });
    expect(unavailableSources(p).map((s) => s.id)).toEqual(['repo_scan']);
  });

  it('con null', () => {
    expect(unavailableSources(null)).toEqual([]);
  });
});

describe('emptyStateMessage', () => {
  it('discrimina las 4 causas', () => {
    const nulo = emptyStateMessage(null, 0);
    const todasCaidas = emptyStateMessage(
      payload({
        sources: [source({ available: false }), source({ id: 'repo_scan', available: false })],
      }),
      0,
    );
    const sinPipelines = emptyStateMessage(payload(), 0);
    const filtroVacio = emptyStateMessage(payload({ pipelines: [entry()] }), 0);
    const mensajes = [nulo, todasCaidas, sinPipelines, filtroVacio];
    expect(new Set(mensajes).size).toBe(4);
    mensajes.forEach((m) => expect(m.length).toBeGreaterThan(0));
  });
});

describe('truncationNotices', () => {
  it('lista los 5 avisos en orden', () => {
    const p = payload({
      sources: [
        source({ capped: true, truncated_hydration: true }),
        source({
          id: 'repo_scan',
          truncated: true,
          skipped_too_big: 2,
          skipped_unparseable: 1,
        }),
      ],
    });
    const avisos = truncationNotices(p);
    expect(avisos.length).toBe(5);
    expect(avisos[0]).toContain('50 definiciones');
    expect(avisos[1]).toContain('10 consultas');
    expect(avisos[2]).toContain('400 archivos');
    expect(avisos[3]).toContain('2 archivo(s)');
    expect(avisos[4]).toContain('1 archivo(s)');
  });

  it('sin recorte devuelve vacio', () => {
    expect(truncationNotices(payload())).toEqual([]);
    expect(truncationNotices(null)).toEqual([]);
  });
});

describe('mismatchHint', () => {
  it('con hints', () => {
    const txt = mismatchHint(
      entry({ category: 'registrada_sin_archivo', hints: ['pipelines/ci_online.yml'] }),
    );
    expect(txt).toContain('pipelines/ci_online.yml');
    expect(txt).toContain('renombre');
    const txt2 = mismatchHint(
      entry({ category: 'en_repo_sin_registrar', hints: ['pipelines/ci-online.yml'] }),
    );
    expect(txt2).toContain('pipelines/ci-online.yml');
  });

  it('sin hints devuelve vacio', () => {
    expect(mismatchHint(entry({ hints: [] }))).toBe('');
    expect(mismatchHint(entry({ category: 'registrada+en_repo', hints: ['x.yml'] }))).toBe('');
  });
});
