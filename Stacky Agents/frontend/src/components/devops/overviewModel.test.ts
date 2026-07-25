/**
 * overviewModel.test.ts — Plan 239 F2. Funciones puras, sin render (jsdom/RTL no están).
 */
import { describe, it, expect } from 'vitest';
import {
  fmtInt,
  fmtPct,
  fmtMinutes,
  fmtWhen,
  buildKpiRows,
  statusLabel,
  blocksNote,
  sparkPoints,
  sparkAltText,
  buildOverviewClipboardText,
  type OverviewPayload,
} from './overviewModel';

const NOW_MS = Date.parse('2026-07-25T12:00:00Z');

function payload(over: Partial<OverviewPayload> = {}): OverviewPayload {
  return {
    generated_at: '2026-07-25T12:00:00Z',
    status: 'ok',
    filters: { app_id: null, project: null, window_days: 14 },
    options: { apps: [{ id: 'app-a', name: 'App A' }], projects: ['RSPACIFICO'] },
    kpis: {
      deploys_7d: 4, deploys_30d: 11, change_failure_rate_30d: 0.18, cfr_sample_30d: 11,
      mttr_minutes_30d: 37.5, last_deploy_at: '2026-07-24T18:03:00Z',
      ci_runs_7d: 9, ci_failures_7d: 2, ci_running_now: 1,
      connections_ok: 3, connections_total: 4,
      servers_total: 2, apps_total: 2, targets_configured: 3, targets_locked: 0,
    },
    series: {
      days: ['2026-07-24', '2026-07-25'],
      deploys_by_day: [1, 2], deploy_failures_by_day: [0, 1],
      ci_runs_by_day: [2, 3], ci_failures_by_day: [0, 1],
    },
    alerts: [],
    recent: [],
    blocks: {
      deployments: { available: true, reason: null },
      ci: { available: true, reason: null },
      connections: { available: true, reason: null },
      servers: { available: true, reason: null },
    },
    ...over,
  };
}

describe('formateadores honestos', () => {
  it('null y undefined ⇒ "n/d"; 0 ⇒ "0" (0 SÍ es un dato)', () => {
    expect(fmtInt(null)).toBe('n/d');
    expect(fmtInt(undefined)).toBe('n/d');
    expect(fmtInt(0)).toBe('0');
    expect(fmtPct(null)).toBe('n/d');
    expect(fmtPct(0)).toBe('0%');
    expect(fmtMinutes(null)).toBe('n/d');
  });

  it('fmtPct redondea a entero', () => {
    expect(fmtPct(0.183)).toBe('18%');
  });

  it('fmtMinutes: 37.5 ⇒ "38 min"; 90 ⇒ "1 h 30 min"; 0 ⇒ "0 min"', () => {
    expect(fmtMinutes(37.5)).toBe('38 min');
    expect(fmtMinutes(90)).toBe('1 h 30 min');
    expect(fmtMinutes(0)).toBe('0 min');
  });

  it('fmtWhen: hoy / ayer / hace N días / n/d', () => {
    expect(fmtWhen('2026-07-25T09:00:00Z', NOW_MS)).toBe('hoy');
    expect(fmtWhen('2026-07-24T09:00:00Z', NOW_MS)).toBe('ayer');
    expect(fmtWhen('2026-07-23T09:00:00Z', NOW_MS)).toBe('hace 2 días');
    expect(fmtWhen(null, NOW_MS)).toBe('n/d');
  });
});

describe('buildKpiRows', () => {
  it('devuelve 8 filas en el orden fijo declarado', () => {
    const filas = buildKpiRows(payload(), NOW_MS);
    expect(filas).toHaveLength(8);
    expect(filas.map((f) => f.key)).toEqual([
      'deploys_7d', 'change_failure_rate_30d', 'mttr_minutes_30d', 'last_deploy_at',
      'ci_runs_7d', 'ci_failures_7d', 'connections', 'servers_total',
    ]);
  });

  it('con payload vacío ⇒ 8 filas y ninguna dice "0" para un dato null', () => {
    const p = payload({
      kpis: {
        deploys_7d: 0, deploys_30d: 0, change_failure_rate_30d: null, cfr_sample_30d: 0,
        mttr_minutes_30d: null, last_deploy_at: null,
        ci_runs_7d: 0, ci_failures_7d: 0, ci_running_now: 0,
        connections_ok: null, connections_total: null,
        servers_total: 0, apps_total: 0, targets_configured: 0, targets_locked: 0,
      },
    });
    const filas = buildKpiRows(p, NOW_MS);
    expect(filas).toHaveLength(8);
    const porClave = Object.fromEntries(filas.map((f) => [f.key, f.value]));
    expect(porClave.change_failure_rate_30d).toBe('n/d');
    expect(porClave.mttr_minutes_30d).toBe('n/d');
    expect(porClave.last_deploy_at).toBe('n/d');
    expect(porClave.connections).toBe('n/d');
  });

  it('CFR >= 0.30 ⇒ tone "danger"; < 0.10 ⇒ "success"', () => {
    const malo = buildKpiRows(
      payload({ kpis: { ...payload().kpis, change_failure_rate_30d: 0.3 } }), NOW_MS);
    expect(malo.find((f) => f.key === 'change_failure_rate_30d')!.tone).toBe('danger');
    const bueno = buildKpiRows(
      payload({ kpis: { ...payload().kpis, change_failure_rate_30d: 0.05 } }), NOW_MS);
    expect(bueno.find((f) => f.key === 'change_failure_rate_30d')!.tone).toBe('success');
  });
});

describe('statusLabel', () => {
  it('"unknown" NO contiene "bien" ni "OK" (guardarraíl anti-falso-verde)', () => {
    const st = statusLabel('unknown');
    expect(st.text.toLowerCase()).not.toContain('bien');
    expect(st.text.toUpperCase()).not.toContain('OK');
    expect(st.tone).toBe('neutral');
  });

  it('mapea los otros 3 estados', () => {
    expect(statusLabel('ok').tone).toBe('success');
    expect(statusLabel('warning').tone).toBe('warning');
    expect(statusLabel('danger').tone).toBe('danger');
  });
});

describe('blocksNote', () => {
  it('lista solo los bloques no disponibles y "" cuando están todos', () => {
    expect(blocksNote(payload())).toBe('');
    const p = payload({
      blocks: {
        deployments: { available: true, reason: null },
        ci: { available: false, reason: 'flag_off' },
        connections: { available: true, reason: 'sin_datos' },
        servers: { available: true, reason: null },
      },
    });
    const note = blocksNote(p);
    expect(note).toContain('CI');
    expect(note).toContain('Conexiones');
    expect(note).not.toContain('Despliegues');
  });
});

describe('sparkline', () => {
  it('serie vacía o toda en cero ⇒ "" (no dibuja)', () => {
    expect(sparkPoints([])).toBe('');
    expect(sparkPoints([0, 0, 0])).toBe('');
  });

  it('sparkPoints([1,2]) tiene 2 pares "x,y"', () => {
    expect(sparkPoints([1, 2]).split(' ')).toHaveLength(2);
  });

  it('es monótona en x y respeta el viewBox', () => {
    const puntos = sparkPoints([3, 1, 4, 1, 5]).split(' ').map((par) => par.split(',').map(Number));
    const xs = puntos.map((p) => p[0]);
    expect(xs).toEqual([...xs].sort((a, b) => a - b));
    puntos.forEach(([x, y]) => {
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThanOrEqual(100);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y).toBeLessThanOrEqual(30);
    });
  });

  it('sparkAltText menciona el total y el máximo', () => {
    const texto = sparkAltText('Despliegues', [1, 2, 3], ['a', 'b', 'c']);
    expect(texto).toContain('6');
    expect(texto).toContain('3');
  });
});

describe('buildOverviewClipboardText (KPI-12)', () => {
  it('incluye estado y fecha en la 1ª línea', () => {
    const texto = buildOverviewClipboardText(payload(), NOW_MS);
    const primera = texto.split('\n')[0];
    expect(primera).toContain('Sin novedades');
    expect(primera).toContain('2026-07-25T12:00:00Z');
  });

  it('incluye las 8 filas de buildKpiRows con su label', () => {
    const p = payload();
    const texto = buildOverviewClipboardText(p, NOW_MS);
    buildKpiRows(p, NOW_MS).forEach((k) => {
      expect(texto).toContain(`${k.label}: ${k.value}`);
    });
  });

  it('declara el alcance', () => {
    const texto = buildOverviewClipboardText(payload(), NOW_MS);
    expect(texto).toContain('todas las aplicaciones');
    expect(texto).toContain('todos los proyectos de CI');
    expect(texto).toContain('14 días');
  });

  it('lista las alertas con su tono en español', () => {
    const p = payload({
      alerts: [
        { id: 'a1', tone: 'danger', title: 'Se rompió', detail: 'detalle 1', section: 'despliegues' },
        { id: 'a2', tone: 'warning', title: 'Ojo', detail: 'detalle 2', section: 'pipelines' },
      ],
    });
    const texto = buildOverviewClipboardText(p, NOW_MS);
    expect(texto).toContain('Avisos: 2');
    expect(texto).toContain('[Crítico] Se rompió — detalle 1');
    expect(texto).toContain('[Atención] Ojo — detalle 2');
  });

  it('sin alertas imprime "(ninguno)", no una lista vacía', () => {
    expect(buildOverviewClipboardText(payload(), NOW_MS)).toContain('(ninguno)');
  });

  it('no miente con datos ausentes: CFR/MTTR null ⇒ "n/d", nunca " 0"', () => {
    const p = payload({
      kpis: { ...payload().kpis, change_failure_rate_30d: null, mttr_minutes_30d: null },
    });
    const texto = buildOverviewClipboardText(p, NOW_MS);
    const lineaCfr = texto.split('\n').find((l) => l.includes('Fallos de despliegue'))!;
    const lineaMttr = texto.split('\n').find((l) => l.includes('Recuperación'))!;
    expect(lineaCfr).toContain('n/d');
    expect(lineaCfr).not.toMatch(/:\s0\b/);
    expect(lineaMttr).toContain('n/d');
    expect(lineaMttr).not.toMatch(/:\s0\b/);
  });

  it('status "unknown" no dice "bien" ni "OK"', () => {
    const texto = buildOverviewClipboardText(payload({ status: 'unknown' }), NOW_MS);
    const primera = texto.split('\n')[0];
    expect(primera.toLowerCase()).not.toContain('bien');
    expect(primera).not.toContain('OK');
  });
});
