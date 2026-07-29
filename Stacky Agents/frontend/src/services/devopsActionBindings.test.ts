// Plan 267 F4 — 7 casos (6 del plan + el que congela la clase de cada binding).
import fs from 'fs';
import path from 'path';
import { describe, expect, it } from 'vitest';
import {
  DELEGATED_ACTION_IDS,
  DEVOPS_ACTION_BINDINGS,
  FALLBACK_META,
  NAVIGATE_ONLY_ACTION_IDS,
  bindingFor,
} from './devopsActionBindings';

const CATALOG_PY = path.resolve(
  __dirname,
  '../../../backend/services/devops_action_catalog.py'
);

/** Los 7 ids EXACTOS de FALLBACK_META (F4). Ni uno mas ni uno menos. */
const LOS_7 = [
  'devops.build.run',
  'devops.build.status',
  'devops.deployment.execute',
  'devops.pipeline.trigger',
  'devops.publication.run',
  'devops.remote_console.run',
  'devops.solution.publish',
];

/** Lee del .py el effect y el impact de un id (mismo patron que el ratchet). */
function campoDelPy(id: string, campo: 'effect' | 'impact'): string | null {
  const src = fs.readFileSync(CATALOG_PY, 'utf8');
  const bloque = new RegExp(
    `id="${id.replace(/\./g, '\\.')}"[\\s\\S]*?\\n        ${campo}="([a-z]+)"`
  );
  const m = src.match(bloque);
  return m ? m[1] : null;
}

describe('Plan 267 F4 — DEVOPS_ACTION_BINDINGS', () => {
  it('1. toda clave cumple el formato de id del catalogo', () => {
    for (const k of Object.keys(DEVOPS_ACTION_BINDINGS)) {
      expect(k).toMatch(/^devops\.[a-z_]+\.[a-z_]+$/);
    }
  });

  it('2. binding.id === su clave (no hay ids desalineados)', () => {
    for (const [k, b] of Object.entries(DEVOPS_ACTION_BINDINGS)) {
      expect(b.id).toBe(k);
    }
  });

  it('3. bindingFor de un id inexistente devuelve undefined sin lanzar', () => {
    expect(bindingFor('no-existe')).toBeUndefined();
  });

  it('4. FALLBACK_META tiene EXACTAMENTE los 7 ids', () => {
    expect(Object.keys(FALLBACK_META).sort()).toEqual(LOS_7);
  });

  it('5. FALLBACK_META coincide con el catalogo backend campo a campo', () => {
    expect(fs.existsSync(CATALOG_PY)).toBe(true);
    for (const id of LOS_7) {
      const effectPy = campoDelPy(id, 'effect');
      const impactPy = campoDelPy(id, 'impact');
      expect(effectPy, `no se pudo leer effect de ${id} en el .py`).not.toBeNull();
      expect(impactPy, `no se pudo leer impact de ${id} en el .py`).not.toBeNull();
      expect(
        FALLBACK_META[id].effect,
        `${id}: fallback effect=${FALLBACK_META[id].effect} vs catalogo=${effectPy}`
      ).toBe(effectPy);
      expect(
        FALLBACK_META[id].impact,
        `${id}: fallback impact=${FALLBACK_META[id].impact} vs catalogo=${impactPy}`
      ).toBe(impactPy);
    }
  });

  it('6. los 7 ids de FALLBACK_META tienen binding', () => {
    for (const id of LOS_7) {
      expect(bindingFor(id), id).toBeDefined();
    }
  });

  it('7. la clase de cada binding esta congelada: 13 ejecutan / 2 navegan / 8 delegan', () => {
    const todos = Object.keys(DEVOPS_ACTION_BINDINGS);
    const delegan = new Set<string>(DELEGATED_ACTION_IDS);
    const navegan = new Set<string>(NAVIGATE_ONLY_ACTION_IDS);
    // Cada id declarado en una lista tiene que existir como binding.
    for (const id of [...delegan, ...navegan]) {
      expect(todos, `${id} declarado pero sin binding`).toContain(id);
    }
    // Y las tres clases particionan el conjunto, sin solaparse.
    const inter = [...delegan].filter((id) => navegan.has(id));
    expect(inter).toEqual([]);
    expect(delegan.size).toBe(8);
    expect(navegan.size).toBe(2);
    expect(todos.length - delegan.size - navegan.size).toBe(13);
  });
});
