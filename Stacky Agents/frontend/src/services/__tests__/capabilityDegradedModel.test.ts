import { describe, it, expect } from 'vitest';
import {
  leerDegradaciones,
  etiquetaDeCapacidad,
  agruparPorProveedor,
} from '../capabilityDegradedModel';

function entrada(capability: string, provider = 'gitlab') {
  return {
    capability,
    reason: 'motivo',
    provider,
    site: 'business_preflight._evaluate_functional',
    at: '2026-08-02T14:05:00+00:00',
  };
}

describe('capabilityDegradedModel — Plan 290 F4', () => {
  it('una metadata sin la clave devuelve lista vacia', () => {
    expect(leerDegradaciones({ ado_context: { comments_count: 3 } })).toEqual([]);
    expect(leerDegradaciones(null)).toEqual([]);
    expect(leerDegradaciones(undefined)).toEqual([]);
  });

  it('capability_degraded en null devuelve lista vacia', () => {
    expect(leerDegradaciones({ capability_degraded: null })).toEqual([]);
  });

  it('capability_degraded que no es array devuelve lista vacia', () => {
    expect(leerDegradaciones({ capability_degraded: 'texto' })).toEqual([]);
    expect(leerDegradaciones({ capability_degraded: { a: 1 } })).toEqual([]);
  });

  it('una entrada corrupta se descarta sin vaciar la lista entera', () => {
    const items = leerDegradaciones({
      capability_degraded: [entrada('tracker.comments.list'), null, 42, {}],
    });
    expect(items).toHaveLength(1);
    expect(items[0].capability).toBe('tracker.comments.list');
  });

  it('las DOS keys de produccion tienen etiqueta y NINGUNA cae al default', () => {
    // Sentinela de que nadie borro una entrada del diccionario para "cerrar" la
    // prosa: el camino desconocido es un borde defensivo, no el camino normal.
    const claves = ['tracker.comments.list', 'tracker.acceptance_criteria'];
    for (const k of claves) {
      const etiqueta = etiquetaDeCapacidad(k);
      expect(etiqueta).not.toBe(k);
      expect(etiqueta.length).toBeGreaterThan(0);
    }
    expect(etiquetaDeCapacidad('tracker.comments.list')).toBe(
      'Lectura de comentarios del tracker',
    );
    expect(etiquetaDeCapacidad('tracker.acceptance_criteria')).toBe(
      'Criterios de aceptación',
    );
  });

  it('una capacidad desconocida devuelve la key cruda, nunca undefined', () => {
    const inventada = 'tracker.inventada.por.el.test';
    expect(etiquetaDeCapacidad(inventada)).toBe(inventada);
  });

  it('etiquetaDeCapacidad("") devuelve "" y no el default (?? vs ||)', () => {
    expect(etiquetaDeCapacidad('')).toBe('');
  });

  it('agruparPorProveedor preserva el orden de llegada', () => {
    const grupos = agruparPorProveedor([
      entrada('tracker.comments.list', 'gitlab'),
      entrada('tracker.acceptance_criteria', 'jira'),
      entrada('tracker.acceptance_criteria', 'gitlab'),
    ]);
    expect(grupos.map(([k]) => k)).toEqual(['gitlab', 'jira']);
    expect(grupos[0][1]).toHaveLength(2);
  });
});
