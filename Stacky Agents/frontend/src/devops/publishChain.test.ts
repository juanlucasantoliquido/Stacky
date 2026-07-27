/**
 * publishChain.test.ts — Plan 102 F1. Deterministas, sin red ni render.
 */
import { describe, it, expect, vi } from 'vitest';
import fs from 'fs';
import path from 'path';
import {
  runPublishChain,
  describeOutcome,
  type ChainDeps,
  type ChainProgress,
} from './publishChain';

const SPEC = { stages: [{ name: 'build' }] };
const SPEC_JSON = JSON.stringify(SPEC);

function deps(over: Partial<ChainDeps> = {}): ChainDeps {
  return {
    materialize: vi.fn().mockResolvedValue({
      spec: SPEC,
      resolved: ['proc-a'],
      unknown_processes: [],
    }),
    commit: vi.fn().mockResolvedValue({ branch: 'feat/x' }),
    trigger: vi.fn().mockResolvedValue({ pipeline_id: '99', web_url: 'https://ci/99' }),
    ...over,
  } as ChainDeps;
}

const capturar = () => {
  const pasos: ChainProgress[] = [];
  return { pasos, onProgress: (p: ChainProgress) => void pasos.push(p) };
};

describe('Plan 102 F1 — runPublishChain', () => {
  it('1. el camino feliz corre los 3 pasos en orden y devuelve completed', async () => {
    const d = deps();
    const { pasos, onProgress } = capturar();
    const out = await runPublishChain(d, SPEC_JSON, 'feat/x', onProgress);
    expect(out).toEqual({
      kind: 'completed',
      branch: 'feat/x',
      pipelineId: '99',
      webUrl: 'https://ci/99',
    });
    expect(pasos.filter((p) => p.state === 'done').map((p) => p.step)).toEqual([
      'materialize', 'commit', 'trigger',
    ]);
  });

  it('2. NO bifurca por proveedor: un preset ADO recorre la misma cadena', async () => {
    // Control de C1: el v1 bloqueaba target='ado' por un copy stale del 501.
    // La cadena no recibe siquiera el target — no puede discriminar.
    const d = deps();
    const out = await runPublishChain(d, SPEC_JSON, 'main', capturar().onProgress);
    expect(out.kind).toBe('completed');
    expect(d.commit).toHaveBeenCalledTimes(1);
  });

  it('3. el branch efectivo del backend gana sobre el tipeado', async () => {
    const d = deps({ commit: vi.fn().mockResolvedValue({ branch: 'derivado-por-backend' }) });
    const out = await runPublishChain(d, SPEC_JSON, '', capturar().onProgress);
    expect(out).toMatchObject({ kind: 'completed', branch: 'derivado-por-backend' });
    expect(d.trigger).toHaveBeenCalledWith('derivado-por-backend');
  });

  it('4. si el spec cambió desde el resumen, ABORTA sin tocar nada', async () => {
    const d = deps({
      materialize: vi.fn().mockResolvedValue({
        spec: { stages: [{ name: 'OTRA-COSA' }] },
        resolved: [],
        unknown_processes: [],
      }),
    });
    const out = await runPublishChain(d, SPEC_JSON, 'main', capturar().onProgress);
    expect(out).toEqual({ kind: 'aborted_stale' });
    // Lo importante: ningún side effect externo se ejecutó.
    expect(d.commit).not.toHaveBeenCalled();
    expect(d.trigger).not.toHaveBeenCalled();
  });

  it('5. fallo en materialize: no commitea ni dispara', async () => {
    const d = deps({ materialize: vi.fn().mockRejectedValue(new Error('catálogo vacío')) });
    const out = await runPublishChain(d, SPEC_JSON, 'main', capturar().onProgress);
    expect(out).toEqual({ kind: 'failed', failedAt: 'materialize', error: 'catálogo vacío' });
    expect(d.commit).not.toHaveBeenCalled();
    expect(d.trigger).not.toHaveBeenCalled();
  });

  it('6. fallo en commit: NO dispara el pipeline', async () => {
    const d = deps({ commit: vi.fn().mockRejectedValue(new Error('403 Forbidden')) });
    const out = await runPublishChain(d, SPEC_JSON, 'main', capturar().onProgress);
    expect(out.kind).toBe('failed');
    expect(d.trigger).not.toHaveBeenCalled();
  });

  it('7. fallo en trigger: el commit YA salió y se informa el branch', async () => {
    const d = deps({ trigger: vi.fn().mockRejectedValue(new Error('429 idempotencia')) });
    const out = await runPublishChain(d, SPEC_JSON, 'feat/x', capturar().onProgress);
    expect(out).toEqual({
      kind: 'failed',
      failedAt: 'trigger',
      error: '429 idempotencia',
      branch: 'feat/x',
    });
  });

  it('8. el progreso reporta el paso fallido como failed, no en silencio', async () => {
    const d = deps({ commit: vi.fn().mockRejectedValue(new Error('boom')) });
    const { pasos, onProgress } = capturar();
    await runPublishChain(d, SPEC_JSON, 'main', onProgress);
    const fallido = pasos.find((p) => p.state === 'failed');
    expect(fallido).toMatchObject({ step: 'commit', detail: 'boom' });
  });

  it('9. CERO rollback: el módulo no tiene ninguna dependencia que deshaga', () => {
    const src = fs.readFileSync(path.resolve(__dirname, 'publishChain.ts'), 'utf-8');
    // Solo el código, sin comentarios (que sí explican por qué no hay rollback).
    const codigo = src
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .split('\n')
      .filter((l) => !l.trim().startsWith('//'))
      .join('\n');
    expect(codigo).not.toMatch(/\brollback\b|\bundo\b|\brevert\b/i);
  });

  it('10. fallo en commit NUNCA afirma que no se commiteó nada (C8)', async () => {
    const d = deps({ commit: vi.fn().mockRejectedValue(new Error('500 timeout')) });
    const out = await runPublishChain(d, SPEC_JSON, 'main', capturar().onProgress);
    expect(out).toMatchObject({ failedAt: 'commit', commitUncertain: true });
    // Y NO trae branch: no se sabe si algo quedó escrito y dónde.
    expect(out).not.toHaveProperty('branch');
    const texto = describeOutcome(out);
    expect(texto).toContain('verificá el repo');
    expect(texto.toLowerCase()).not.toContain('nada se commite');
  });
});
