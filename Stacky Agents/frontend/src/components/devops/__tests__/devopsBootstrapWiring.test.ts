/**
 * devopsBootstrapWiring.test.ts — Plan 98 F4 + F5.
 *
 * Verifica que los DOS endpoints del plan 98 (vivos en el backend desde el
 * 2026-07-06 y sin un solo consumidor hasta hoy) queden REALMENTE cableados.
 *
 * TS-puro con `fs`, estilo `pages/__tests__/ServersSection.test.ts`: en este repo
 * `@testing-library/react` y `jsdom` NO están instalados, así que el render real
 * no es verificable por test. Lo que sí es verificable —y es lo que se rompió acá—
 * es el CABLEADO: que exista el método, que la ruta lleve prefijo, que el shell
 * declare la query y que las secciones tengan su early-path.
 */
import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

const SRC = path.resolve(__dirname, '../../..');
const read = (rel: string) => fs.readFileSync(path.join(SRC, rel), 'utf-8');

const ENDPOINTS = read('api/endpoints.ts');
const SHELL = read('pages/DevOpsPage.tsx');
const SECCIONES: Record<string, string> = {
  'PipelineBuilderSection.tsx': read('components/devops/PipelineBuilderSection.tsx'),
  'PublicationsSection.tsx': read('components/devops/PublicationsSection.tsx'),
  'EnvironmentsSection.tsx': read('components/devops/EnvironmentsSection.tsx'),
};

/** Cuerpo de `const <nombre> = async (…)` hasta el próximo `const ` de igual indentación. */
function cuerpoDeFuncion(source: string, nombre: string): string {
  const inicio = source.indexOf(`const ${nombre} = async`);
  if (inicio === -1) return '';
  const resto = source.slice(inicio + 10);
  const fin = resto.indexOf('\n  const ');
  return fin === -1 ? resto : resto.slice(0, fin);
}

describe('Plan 98 F4 — bootstrap único cableado', () => {
  it('1. endpoints expone DevOps.bootstrap', async () => {
    const mod = await import('../../../api/endpoints');
    expect(typeof mod.DevOps.bootstrap).toBe('function');
  });

  it('2. la ruta del bootstrap lleva el prefijo /api (control negativo del 404 mudo)', () => {
    expect(ENDPOINTS).toContain('/api/devops/bootstrap?project=');
    // Ninguna variante sin prefijo se coló.
    expect(ENDPOINTS).not.toContain('`/devops/bootstrap');
    expect(ENDPOINTS).not.toContain('"/devops/bootstrap');
  });

  it('3. el shell declara la query y propaga la key aditiva del ctx', () => {
    expect(SHELL).toContain("'devops-bootstrap'");
    expect(SHELL).toContain('bootstrap: bootstrapQuery.data ?? null');
    expect(SHELL).toContain('bootstrap_enabled === true');
    // La query se apaga sola con la flag OFF (el endpoint da 404).
    expect(SHELL).toContain('retry: false');
  });

  it('4. el shell NO agregó sondeo periódico (el ratchet del 239 no cambia)', () => {
    // Pineado: 1 `refetchInterval` y 0 `setInterval(` en el shell, medido el
    // 2026-07-26 ANTES de este plan. Si el 98 hubiera agregado latido, sube.
    const refetch = (SHELL.match(/refetchInterval/g) ?? []).length;
    const intervals = (SHELL.match(/setInterval\(/g) ?? []).length;
    expect(refetch).toBe(1);
    expect(intervals).toBe(0);
  });

  it('5. las 3 secciones tienen early-path por ctx.bootstrap', () => {
    for (const [nombre, src] of Object.entries(SECCIONES)) {
      expect(src, `${nombre} sin guard de flag`).toContain('ctx.health.bootstrap_enabled === true');
      expect(src, `${nombre} no lee el bootstrap`).toContain('ctx.bootstrap');
    }
  });

  it('6. EnvironmentsSection conserva la semántica null (sin configurar ≠ vacío)', () => {
    const src = SECCIONES['EnvironmentsSection.tsx'];
    expect(src).toContain('k.devops_environment_settings');
    expect(src).toContain('setHasSavedSettings(false)');
  });
});

describe('Plan 98 F5 — escritura por clave cableada', () => {
  it('7. las 3 secciones importan saveProfileKey del módulo único', () => {
    for (const [nombre, src] of Object.entries(SECCIONES)) {
      expect(src, `${nombre} no importa el helper`).toContain(
        "from '../../devops/profileKeys'",
      );
    }
  });

  it('8. ninguna función de guardado migrada re-implementa el PUT full', () => {
    // Reemplaza al gate INSATISFACIBLE del v1 ("el archivo no contiene api.put(").
    // handleAutoDetect necesita el PUT full: escribe process_catalog, que NO está
    // en PATCHABLE_PROFILE_KEYS (services/client_profile_keys.py).
    const migrados: Array<[string, string]> = [
      ['PipelineBuilderSection.tsx', 'saveDraft'],
      ['PublicationsSection.tsx', 'savePresets'],
      ['PublicationsSection.tsx', 'saveSettings'],
      ['PublicationsSection.tsx', 'handleSaveAsDraft'],
      ['EnvironmentsSection.tsx', 'saveSettings'],
      ['EnvironmentsSection.tsx', 'handleCreateTodoPreset'],
    ];
    for (const [archivo, fn] of migrados) {
      const cuerpo = cuerpoDeFuncion(SECCIONES[archivo], fn);
      expect(cuerpo, `no se encontró ${fn} en ${archivo}`).not.toBe('');
      expect(cuerpo, `${archivo}::${fn} sigue haciendo PUT full`).not.toContain('api.put(');
      expect(cuerpo, `${archivo}::${fn} no usa el helper`).toContain('saveProfileKey(');
    }
  });

  it('9. el conteo de api.put( es exactamente 0 / 1 / 0 y el único vive en handleAutoDetect', () => {
    const cuenta = (s: string) => (s.match(/api\.put\(/g) ?? []).length;
    expect(cuenta(SECCIONES['PipelineBuilderSection.tsx'])).toBe(0);
    expect(cuenta(SECCIONES['PublicationsSection.tsx'])).toBe(1);
    expect(cuenta(SECCIONES['EnvironmentsSection.tsx'])).toBe(0);
    const autodetect = cuerpoDeFuncion(SECCIONES['PublicationsSection.tsx'], 'handleAutoDetect');
    expect(autodetect, 'handleAutoDetect debe conservar SU PUT full (atomicidad catálogo↔presets)')
      .toContain('api.put(');
  });

  it('10. el helper no puede escribir process_catalog (no es parcheable)', () => {
    const helper = read('devops/profileKeys.ts');
    const tipo = helper.slice(
      helper.indexOf('export type PatchableProfileKey'),
      helper.indexOf('export async function'),
    );
    expect(tipo).not.toContain('process_catalog');
    expect(tipo).toContain('devops_pipeline_drafts');
    expect(tipo).toContain('devops_publication_presets');
    expect(tipo).toContain('devops_publication_settings');
    expect(tipo).toContain('devops_environment_settings');
  });
});
