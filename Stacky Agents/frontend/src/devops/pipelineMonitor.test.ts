/**
 * pipelineMonitor.test.ts — Plan 103 F1.
 *
 * Deterministas, sin timers ni render. vitest corre en entorno `node`, así que
 * `localStorage` NO existe: los casos de persistencia lo stubbean explícitamente
 * (y el caso 10 verifica que su ausencia degrade sin romper nada, que es el
 * comportamiento real en un navegador con storage denegado).
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
  BACKOFF_STEPS_MS,
  computeBackoffMs,
  isTerminalStatus,
  toneForStatus,
  formatMonitorStatus,
  isPollCapError,
  loadPersistedPipeline,
  persist,
  appliesToProject,
  type MonitoredPipeline,
} from './pipelineMonitor';

const pipeline = (over: Partial<MonitoredPipeline> = {}): MonitoredPipeline => ({
  project: 'p1',
  pipelineId: '4210',
  ref: 'main',
  status: 'running',
  webUrl: 'https://ci/4210',
  updatedAt: '2026-07-26T10:00:00.000Z',
  ...over,
});

/** localStorage de mentira, en memoria. */
function stubStorage() {
  const mapa = new Map<string, string>();
  (globalThis as Record<string, unknown>).localStorage = {
    getItem: (k: string) => mapa.get(k) ?? null,
    setItem: (k: string, v: string) => void mapa.set(k, v),
    removeItem: (k: string) => void mapa.delete(k),
  };
  return mapa;
}

describe('Plan 103 F1 — backoff', () => {
  it('1. el backoff sube por la escalera 3s→5s→10s→30s', () => {
    expect(BACKOFF_STEPS_MS.map((_, i) => computeBackoffMs(i))).toEqual([
      3000, 5000, 10000, 30000,
    ]);
  });

  it('2. el backoff tiene clamp arriba y abajo (nunca se dispara ni se vuelve negativo)', () => {
    expect(computeBackoffMs(99)).toBe(30000);
    expect(computeBackoffMs(-5)).toBe(3000);
    expect(computeBackoffMs(NaN)).toBe(3000);
    expect(computeBackoffMs(1.7)).toBe(5000); // trunca
  });
});

describe('Plan 103 F1 — estados', () => {
  it('3. reconoce los estados terminales (y ahí hay que dejar de sondear)', () => {
    for (const s of ['succeeded', 'FAILED', ' completed ', 'canceled', 'skipped']) {
      expect(isTerminalStatus(s), s).toBe(true);
    }
    for (const s of ['running', 'pending', 'queued', '', null, undefined]) {
      expect(isTerminalStatus(s as string), String(s)).toBe(false);
    }
  });

  it('4. el tono trata lo desconocido como "corriendo", NUNCA como error', () => {
    expect(toneForStatus('succeeded')).toBe('success');
    expect(toneForStatus('failed')).toBe('error');
    expect(toneForStatus('canceled')).toBe('error');
    expect(toneForStatus('running')).toBe('running');
    expect(toneForStatus('un_estado_que_no_conocemos')).toBe('running');
    expect(toneForStatus(null)).toBe('running');
  });

  it('5. el estado se lee en castellano, no como JSON crudo', () => {
    expect(formatMonitorStatus(pipeline({ status: 'succeeded' }))).toBe(
      'Pipeline 4210 (main): terminó bien',
    );
    expect(formatMonitorStatus(pipeline({ status: 'failed', ref: '' }))).toBe(
      'Pipeline 4210: falló',
    );
    // Un estado desconocido se muestra tal cual, no se traga.
    expect(formatMonitorStatus(pipeline({ status: 'weird' }))).toContain('weird');
    expect(formatMonitorStatus(null)).toBe('');
  });

  it('6. el 429 del cap de polls NO es un fallo del pipeline', () => {
    expect(
      isPollCapError(
        new Error('429 TOO MANY REQUESTS: {"error":"too many active polls for pipeline"}'),
      ),
    ).toBe(true);
    expect(isPollCapError(new Error('too many active polls for pipeline'))).toBe(true);
    expect(isPollCapError(new Error('500 INTERNAL SERVER ERROR: boom'))).toBe(false);
    expect(isPollCapError(new Error('404 NOT FOUND'))).toBe(false);
  });
});

describe('Plan 103 F1 — persistencia (el defecto central: hoy se pierde al recargar)', () => {
  let mapa: Map<string, string>;
  beforeEach(() => {
    mapa = stubStorage();
  });
  afterEach(() => {
    delete (globalThis as Record<string, unknown>).localStorage;
  });

  it('7. lo persistido se recupera intacto (sobrevive a la recarga)', () => {
    const p = pipeline();
    persist(p);
    expect(loadPersistedPipeline()).toEqual(p);
  });

  it('8. persist(null) borra la entrada', () => {
    persist(pipeline());
    persist(null);
    expect(loadPersistedPipeline()).toBeNull();
    expect(mapa.size).toBe(0);
  });

  it('9. un JSON corrupto o incompleto degrada a null, no rompe el panel', () => {
    mapa.set('stacky.devops.lastPipeline', '{esto no es json');
    expect(loadPersistedPipeline()).toBeNull();
    mapa.set('stacky.devops.lastPipeline', '{"ref":"main"}'); // sin pipelineId ni project
    expect(loadPersistedPipeline()).toBeNull();
  });

  it('10. sin localStorage (denegado) degrada en silencio, sin lanzar', () => {
    delete (globalThis as Record<string, unknown>).localStorage;
    expect(() => persist(pipeline())).not.toThrow();
    expect(loadPersistedPipeline()).toBeNull();
  });
});

describe('Plan 103 F1 — alcance por proyecto', () => {
  it('11. un pipeline de OTRO proyecto no aplica al badge', () => {
    expect(appliesToProject(pipeline({ project: 'p1' }), 'p1')).toBe(true);
    expect(appliesToProject(pipeline({ project: 'p1' }), 'p2')).toBe(false);
    expect(appliesToProject(null, 'p1')).toBe(false);
    expect(appliesToProject(pipeline(), '')).toBe(false);
  });
});
