/**
 * previewFetcher.test.ts — Plan 99 F0 + F0.bis.
 *
 * TODOS los casos son deterministas: promesas resueltas a mano, sin timers falsos,
 * sin sleeps, sin render. Una carrera probada con `setTimeout` es una carrera no
 * probada.
 */
import { describe, it, expect, vi } from 'vitest';
import fs from 'fs';
import path from 'path';
import {
  createPreviewFetcher,
  parsePreviewError,
  PREVIEW_CACHE_LIMIT,
  type PreviewData,
} from './previewFetcher';

const A = { name: 'a' };
const B = { name: 'b' };
const yaml = (s: string): PreviewData => ({ ado: `ado-${s}`, gitlab: `gl-${s}` });

/** Promesa que se resuelve/rechaza cuando el test lo decide. */
function diferida<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('Plan 99 F0 — previewFetcher', () => {
  it('1. un spec nuevo pega a la red y devuelve ok', async () => {
    const call = vi.fn().mockResolvedValue(yaml('a'));
    const f = createPreviewFetcher(call);
    await expect(f.request(A)).resolves.toEqual({ kind: 'ok', data: yaml('a') });
    expect(call).toHaveBeenCalledTimes(1);
  });

  it('2. KPI — A→B→A hace 2 llamadas, no 3 (el retorno pega al cache)', async () => {
    const call = vi.fn(async (spec: object) => yaml(JSON.stringify(spec)));
    const f = createPreviewFetcher(call);
    await f.request(A);
    await f.request(B);
    const tercero = await f.request(A);
    expect(call).toHaveBeenCalledTimes(2);
    expect(tercero).toEqual({ kind: 'ok', data: yaml(JSON.stringify(A)) });
  });

  it('3. la key es la serialización del spec (mismo contenido = mismo hit)', async () => {
    const call = vi.fn().mockResolvedValue(yaml('a'));
    const f = createPreviewFetcher(call);
    await f.request({ name: 'a' });
    await f.request({ name: 'a' }); // otro objeto, mismo contenido
    expect(call).toHaveBeenCalledTimes(1);
  });

  it('4. invalidate() vacía el cache y obliga a repegar', async () => {
    const call = vi.fn().mockResolvedValue(yaml('a'));
    const f = createPreviewFetcher(call);
    await f.request(A);
    f.invalidate();
    expect(f.cacheSize()).toBe(0);
    await f.request(A);
    expect(call).toHaveBeenCalledTimes(2);
  });

  it('5. ANTI-STALE — la respuesta vieja que llega tarde NO gana: es `stale`', async () => {
    const dA = diferida<PreviewData>();
    const dB = diferida<PreviewData>();
    const call = vi
      .fn()
      .mockReturnValueOnce(dA.promise)
      .mockReturnValueOnce(dB.promise);
    const f = createPreviewFetcher(call);

    const pA = f.request(A); // sale primero
    const pB = f.request(B); // lo supera

    dB.resolve(yaml('b')); // B contesta primero
    expect(await pB).toEqual({ kind: 'ok', data: yaml('b') });

    dA.resolve(yaml('a')); // A contesta DESPUÉS, con datos viejos
    expect(await pA).toEqual({ kind: 'stale' });
  });

  it('6. un error de un pedido superado también es `stale` (no pinta un error viejo)', async () => {
    const dA = diferida<PreviewData>();
    const dB = diferida<PreviewData>();
    const call = vi.fn().mockReturnValueOnce(dA.promise).mockReturnValueOnce(dB.promise);
    const f = createPreviewFetcher(call);

    const pA = f.request(A);
    const pB = f.request(B);
    dB.resolve(yaml('b'));
    await pB;
    dA.reject(new Error('500 Internal Server Error: boom'));
    expect(await pA).toEqual({ kind: 'stale' });
  });

  it('7. un AbortError se trata como `stale` vía isAbortError (no como error visible)', async () => {
    const abort = new DOMException('aborted', 'AbortError');
    const call = vi.fn().mockRejectedValue(abort);
    const f = createPreviewFetcher(call);
    expect(await f.request(A)).toEqual({ kind: 'stale' });
  });

  it('8. un 400 estructurado se parsea POR CAMPO (el branch muerto revivido)', async () => {
    // Forma REAL de lo que tira api/client.ts:155.
    const real = new Error(
      '400 BAD REQUEST: {"errors": [{"field": "stages[0].name", "message": "requerido"}]}',
    );
    const call = vi.fn().mockRejectedValue(real);
    const f = createPreviewFetcher(call);
    expect(await f.request(A)).toEqual({
      kind: 'error',
      errors: [{ field: 'stages[0].name', message: 'requerido' }],
    });
  });

  it('9. un error sin JSON degrada a un error general legible', async () => {
    expect(parsePreviewError(new Error('502 Bad Gateway: '))).toEqual([
      { field: 'general', message: '502 Bad Gateway: ' },
    ]);
    expect(parsePreviewError('no soy un Error')).toEqual([
      { field: 'general', message: 'Error desconocido' },
    ]);
  });

  it('10. el cache está capado en PREVIEW_CACHE_LIMIT y descarta el más viejo', async () => {
    const call = vi.fn(async (spec: object) => yaml(JSON.stringify(spec)));
    const f = createPreviewFetcher(call);
    for (let i = 0; i < PREVIEW_CACHE_LIMIT + 5; i++) {
      await f.request({ n: i });
    }
    expect(f.cacheSize()).toBe(PREVIEW_CACHE_LIMIT);
    // El primero fue desalojado ⇒ vuelve a pegar.
    const antes = call.mock.calls.length;
    await f.request({ n: 0 });
    expect(call.mock.calls.length).toBe(antes + 1);
  });
});

describe('Plan 99 F0.bis — paridad de semántica anti-race con el precedente', () => {
  it('11. el desenlace superado no devuelve datos: solo `stale` (nada que aplicar)', async () => {
    const dA = diferida<PreviewData>();
    const dB = diferida<PreviewData>();
    const call = vi.fn().mockReturnValueOnce(dA.promise).mockReturnValueOnce(dB.promise);
    const f = createPreviewFetcher(call);
    const pA = f.request(A);
    const pB = f.request(B);
    dB.resolve(yaml('b'));
    await pB;
    dA.resolve(yaml('a'));
    const outcome = await pA;
    expect(outcome.kind).toBe('stale');
    // Contrato duro: un `stale` NO trae payload que alguien pueda aplicar por error.
    expect(Object.keys(outcome)).toEqual(['kind']);
  });

  it('12. el precedente de PipelineLintPanel sigue vivo (contrato compartido)', () => {
    const src = fs.readFileSync(
      path.resolve(__dirname, '../components/devops/PipelineLintPanel.tsx'),
      'utf-8',
    );
    expect(src).toContain('seqRef');
    expect(src).toContain('seq !== seqRef.current');
  });
});
