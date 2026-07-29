// Plan 267 F4 — 15 casos. Logica pura, sin DOM (gap RTL/jsdom del repo).
import { describe, expect, it, vi } from 'vitest';
import { denyByDefault } from './confirmGateway';
import type { DevOpsActionBinding, DevOpsActionRunContext } from './devopsActionRunner';
import {
  confirmRequestFor,
  missingRequired,
  navPathWithParams,
  paletteMode,
  runDevOpsAction,
} from './devopsActionRunner';
import type { DevOpsActionMeta } from './devopsActionTypes';

const P = (
  name: string,
  required = false
): DevOpsActionMeta['params'][number] => ({
  name,
  type: 'string',
  label: name,
  required,
  enum_values: [],
  default: '',
});

function meta(over: Partial<DevOpsActionMeta> = {}): DevOpsActionMeta {
  return {
    id: 'devops.deployment.execute',
    label: 'Ejecutar despliegue',
    summary: 'Corre el despliegue elegido en el entorno elegido.',
    section_id: 'despliegues',
    nav_path: '/devops/despliegues',
    effect: 'write',
    impact: 'high',
    targets_environment: true,
    health_key: 'deployments_execute_enabled',
    flag_key: 'STACKY_DEPLOYMENTS_EXECUTE_ENABLED',
    reach: ['button', 'palette-nav', 'assistant'],
    params: [P('project', true), P('environment', true)],
    phrases: [],
    ...over,
  };
}

function ctx(over: Partial<DevOpsActionRunContext> = {}): DevOpsActionRunContext {
  return {
    askConfirm: vi.fn(async () => true),
    navigate: vi.fn(),
    now: () => 1000,
    ...over,
  };
}

const okBinding = (spy: ReturnType<typeof vi.fn>): DevOpsActionBinding => ({
  id: 'x',
  run: spy as unknown as DevOpsActionBinding['run'],
});

describe('Plan 267 F4 — confirmRequestFor / missingRequired', () => {
  it('1. effect read => null (no se molesta al operador para leer)', () => {
    expect(confirmRequestFor(meta({ effect: 'read', impact: 'none' }), {})).toBeNull();
  });

  it('2. impact high => tone danger', () => {
    expect(confirmRequestFor(meta({ impact: 'high' }), {})?.tone).toBe('danger');
  });

  it('3. impact low => tone default', () => {
    expect(confirmRequestFor(meta({ impact: 'low' }), {})?.tone).toBe('default');
  });

  it('4. el message nombra el entorno cuando esta', () => {
    const r = confirmRequestFor(meta(), { environment: 'prod' });
    expect(r?.message).toContain('sobre el entorno prod');
  });

  it('5. el message dice "sin entorno declarado" si falta', () => {
    const r = confirmRequestFor(meta(), {});
    expect(r?.message).toContain('sin entorno declarado');
  });

  it('6. missingRequired detecta faltantes y [] cuando estan todos', () => {
    expect(missingRequired(meta(), { project: 'P' })).toEqual(['environment']);
    expect(missingRequired(meta(), { project: 'P', environment: 'qa' })).toEqual([]);
  });
});

describe('Plan 267 F4 — runDevOpsAction (orden de guardas inviolable)', () => {
  it('7. denyByDefault + write => el binding NO se llama', async () => {
    const spy = vi.fn(async () => ({ ok: true, summary: 's' }));
    const r = await runDevOpsAction(
      meta(),
      { project: 'P', environment: 'qa' },
      okBinding(spy),
      ctx({ askConfirm: denyByDefault })
    );
    expect(spy).toHaveBeenCalledTimes(0);
    expect(r.confirmed).toBe(false);
    expect(r.ok).toBe(false);
  });

  it('8. effect read => NO se pide confirmacion y SI se ejecuta', async () => {
    const spy = vi.fn(async () => ({ ok: true, summary: 'leido' }));
    const ask = vi.fn(async () => true);
    const r = await runDevOpsAction(
      meta({ effect: 'read', impact: 'none' }),
      { project: 'P', environment: 'qa' },
      okBinding(spy),
      ctx({ askConfirm: ask })
    );
    expect(ask).toHaveBeenCalledTimes(0);
    expect(spy).toHaveBeenCalledTimes(1);
    expect(r.ok).toBe(true);
  });

  it('9. binding undefined => ok:false y no lanza', async () => {
    const r = await runDevOpsAction(
      meta(),
      { project: 'P', environment: 'qa' },
      undefined,
      ctx()
    );
    expect(r.ok).toBe(false);
    expect(r.detail).toContain('devops.deployment.execute');
  });

  it('10. si run() lanza => ok:false con el mensaje, no propaga', async () => {
    const spy = vi.fn(async () => {
      throw new Error('el servidor dijo no');
    });
    const r = await runDevOpsAction(
      meta(),
      { project: 'P', environment: 'qa' },
      okBinding(spy),
      ctx()
    );
    expect(r.ok).toBe(false);
    expect(r.detail).toBe('el servidor dijo no');
  });

  it('11. faltan required => ni askConfirm ni binding se llaman', async () => {
    const spy = vi.fn(async () => ({ ok: true, summary: 's' }));
    const ask = vi.fn(async () => true);
    const r = await runDevOpsAction(
      meta(),
      { project: 'P' },
      okBinding(spy),
      ctx({ askConfirm: ask })
    );
    expect(r.ok).toBe(false);
    expect(ask).toHaveBeenCalledTimes(0);
    expect(spy).toHaveBeenCalledTimes(0);
  });
});

describe('Plan 267 F4 — navPathWithParams / paletteMode', () => {
  it('12. sin params => nav_path pelado; con params => orden alfabetico exacto', () => {
    expect(navPathWithParams(meta(), {})).toBe('/devops/despliegues');
    expect(
      navPathWithParams(meta(), { environment: 'qa', project: 'Pacifico' })
    ).toBe('/devops/despliegues?environment=qa&project=Pacifico');
  });

  it('13. omite vacios y espacios, y escapa el valor', () => {
    expect(navPathWithParams(meta(), { a: '   ', b: '' })).toBe('/devops/despliegues');
    expect(navPathWithParams(meta(), { q: 'a b&c' })).toBe(
      '/devops/despliegues?q=a%20b%26c'
    );
  });

  it('14. paletteMode: run / nav / hidden', () => {
    expect(
      paletteMode(
        meta({
          effect: 'read',
          impact: 'none',
          reach: ['button', 'palette-run', 'assistant'],
        })
      )
    ).toBe('run');
    expect(
      paletteMode(meta({ effect: 'write', reach: ['button', 'palette-nav', 'assistant'] }))
    ).toBe('nav');
    expect(paletteMode(meta({ effect: 'read', impact: 'none', reach: ['button'] }))).toBe(
      'hidden'
    );
  });

  it('15. la paleta NUNCA ejecuta una escritura aunque el payload MIENTA', () => {
    // Payload falsificado: exactamente lo que ningun ratchet del backend puede
    // impedir que llegue por HTTP. Es el UNICO test que verifica I-REACH en el
    // plano del CONSUMO; los otros tres leen el .py del backend.
    const miente = meta({
      effect: 'write',
      impact: 'high',
      reach: ['button', 'palette-run', 'assistant'],
    });
    expect(paletteMode(miente)).toBe('nav');
  });
});
