/**
 * devopsPreview.test.ts — Plan 99 F1 + F2 + F3.
 *
 * Fija el CABLEADO del preview. La lógica con estados y carreras vive en el módulo
 * puro `devops/previewFetcher.ts` y se prueba allá (12 casos deterministas): acá se
 * verifica que el componente esté conectado a ese módulo y que no hayan vuelto los
 * defectos que el plan mató.
 *
 * Gap declarado: `@testing-library/react` y `jsdom` NO están instalados en este
 * repo, así que el render real no es verificable por test. Estos greps fijan el
 * cableado; la interacción la cubre la verificación manual de §F4.
 */
import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

const SRC = path.resolve(__dirname, '../../..');
const read = (rel: string) => fs.readFileSync(path.join(SRC, rel), 'utf-8');

const CLIENT = read('api/client.ts');
const ENDPOINTS = read('api/endpoints.ts');
const PREVIEW = read('components/devops/PipelineYamlPreview.tsx');
const BUILDER = read('components/devops/PipelineBuilderSection.tsx');
const CSS = read('components/devops/devops.module.css');

describe('Plan 99 F1 — POST cancelable, aditivo', () => {
  it('1. api expone postAbortable e isAbortError está exportada', async () => {
    const mod = await import('../../../api/client');
    expect(typeof mod.api.postAbortable).toBe('function');
    expect(typeof mod.isAbortError).toBe('function');
    // El predicado es el de la casa, no una copia.
    expect(mod.isAbortError(new DOMException('x', 'AbortError'))).toBe(true);
    expect(mod.isAbortError(new Error('x'))).toBe(false);
  });

  it('2. preview acepta signal y lo enruta a postAbortable', () => {
    expect(ENDPOINTS).toContain('signal?: AbortSignal');
    expect(ENDPOINTS).toContain('api.postAbortable<{ ado: string; gitlab: string }>');
  });

  it('3. las firmas existentes de api NO cambiaron (backward-compatible)', () => {
    for (const firma of ['get:', 'post:', 'put:', 'patch:', 'delete:', 'postWithHeaders:']) {
      expect(CLIENT, `desapareció api.${firma}`).toContain(`  ${firma}`);
    }
  });
});

describe('Plan 99 F2 — preview con cache, anti-stale y SWR', () => {
  it('4. el componente usa el fetcher compartido', () => {
    expect(PREVIEW).toContain('createPreviewFetcher');
    expect(PREVIEW).toContain("from '../../devops/previewFetcher'");
  });

  it('5. no hay blanqueo prematuro de errores', () => {
    // Una sola limpieza, y DESPUÉS del desenlace de error (antes se limpiaba al
    // ARRANCAR el request, lo que hacía parpadear los errores en cada tecla).
    const ocurrencias = (PREVIEW.match(/setPreviewErrors\(\[\]\)/g) ?? []).length;
    expect(ocurrencias).toBe(1);
    expect(PREVIEW.indexOf('setPreviewErrors([])')).toBeGreaterThan(
      PREVIEW.indexOf("outcome.kind === 'error'"),
    );
  });

  it('6. los desenlaces stale se descartan antes de tocar cualquier estado', () => {
    const iStale = PREVIEW.indexOf("if (outcome.kind === 'stale') return;");
    expect(iStale).toBeGreaterThan(-1);
    expect(iStale).toBeLessThan(PREVIEW.indexOf('setLoading(false)'));
    expect(iStale).toBeLessThan(PREVIEW.indexOf('setPreview(result)'));
  });

  it('7. el botón manual bypassa el cache y el auto-refresh no', () => {
    expect(PREVIEW).toContain('refreshPreview(true)');
    expect(PREVIEW).toContain('void refreshPreview();'); // el debounce, sin force
    expect(PREVIEW).toContain('if (force) fetcherRef.current!.invalidate();');
  });

  it('8. badge y atenuado van por clase, nunca inline (uiDebtRatchet)', () => {
    expect(PREVIEW).toContain('styles.recalcBadge');
    expect(PREVIEW).toContain('styles.yamlPreStale');
    expect(PREVIEW).toContain('styles.previewHeader');
    expect(PREVIEW).not.toContain('opacity: loading');
    for (const cls of ['.previewHeader', '.recalcBadge', '.yamlPreStale']) {
      expect(CSS, `falta la clase ${cls}`).toContain(cls);
    }
  });

  it('8.bis. la deuda UI del preview NO subió y sigue sin hex literales', () => {
    // Baseline en src/__tests__/uiDebtBaseline.json = 14. Este plan la BAJÓ a 13
    // (la fila del título pasó a CSS module). El ratchet exige count <= allowed.
    const inline = (PREVIEW.match(/style=\{\{/g) ?? []).length;
    expect(inline).toBeLessThanOrEqual(14);
    expect(PREVIEW).not.toMatch(/#[0-9a-fA-F]{3,6}/);
  });

  it('9. CONTROL DE C1 — el perfilador del Plan 247 sigue vivo', () => {
    // Este es el test que impide el borrado silencioso: el v1 del plan ordenaba
    // reemplazar refreshPreview "COMPLETO", lo que habría eliminado el perfilador
    // sin que nada lo notara.
    expect(PREVIEW).toContain('PipelineProfiler.profile');
    expect(PREVIEW).toContain('setProfileError');
    expect(PREVIEW).toContain('PipelineProfileCard');
    expect((PREVIEW.match(/PipelineProfiler\.profile/g) ?? []).length).toBe(1);
    // Y sigue DENTRO de refreshPreview, después del preview exitoso.
    expect(PREVIEW.indexOf('PipelineProfiler.profile')).toBeGreaterThan(
      PREVIEW.indexOf('setPreview(result)'),
    );
    // Su fallo no puede degradar el preview: sigue envuelto en su propio catch.
    expect(PREVIEW).toContain("setProfileError(pe instanceof Error ? pe.message : 'perfil no disponible')");
  });
});

describe('Plan 99 F3 — debounce fantasma borrado', () => {
  it('10. el fantasma no existe más en el builder', () => {
    expect(BUILDER).not.toContain('refreshTimeoutRef');
    expect(BUILDER).not.toContain('useRef'); // quedó sin usos tras el borrado
  });

  it('11. el debounce REAL sigue vivo en el preview (800ms)', () => {
    expect(PREVIEW).toContain('setTimeout');
    expect(PREVIEW).toContain('800');
    expect(PREVIEW).toContain('clearTimeout(timeoutId)');
  });
});
