// Plan 267 F8 — Ratchet de paridad backend<->frontend. 7 casos.
//
// Lee el .py del backend como TEXTO (patron calcado de devopsPollingRatchet):
// asi el ratchet no depende de que el backend este corriendo, y no puede haber
// deriva silenciosa entre el catalogo y los bindings.
import fs from 'fs';
import path from 'path';
import { describe, expect, it } from 'vitest';
import { DEVOPS_ACTION_BINDINGS } from '../services/devopsActionBindings';

const CATALOG_PY = path.resolve(
  __dirname,
  '../../../backend/services/devops_action_catalog.py'
);

function src(): string {
  return fs.readFileSync(CATALOG_PY, 'utf8');
}

function catalogIds(): string[] {
  return [...src().matchAll(/^\s*id="(devops\.[a-z_]+\.[a-z_]+)"/gm)].map((m) => m[1]);
}

/** Cada entrada del catalogo, con su effect y su reach, parseada por bloque. */
function catalogEntries(): { id: string; effect: string; reach: string }[] {
  const re =
    /^\s*id="(devops\.[a-z_]+\.[a-z_]+)"[\s\S]*?\n\s*effect="([a-z]+)"[\s\S]*?\n\s*reach=canonical_reach\("([a-z]*)"\)/gm;
  return [...src().matchAll(re)].map((m) => ({
    id: m[1],
    effect: m[2],
    reach: m[3],
  }));
}

describe('Plan 267 F8 — paridad catalogo <-> bindings', () => {
  it('1. todo id del catalogo tiene binding', () => {
    const huerfanos = catalogIds().filter((id) => !(id in DEVOPS_ACTION_BINDINGS));
    expect(huerfanos, `ids del catalogo SIN binding: ${huerfanos.join(', ')}`).toEqual([]);
  });

  it('2. todo binding tiene id en el catalogo', () => {
    const ids = new Set(catalogIds());
    const fantasmas = Object.keys(DEVOPS_ACTION_BINDINGS).filter((k) => !ids.has(k));
    expect(fantasmas, `bindings FANTASMA: ${fantasmas.join(', ')}`).toEqual([]);
  });

  it('3. igualdad exacta de conjuntos (KPI-7: deriva 0)', () => {
    expect([...catalogIds()].sort()).toEqual(Object.keys(DEVOPS_ACTION_BINDINGS).sort());
  });

  it('4. el archivo de catalogo existe (si no, el test NO puede pasar vacio)', () => {
    expect(fs.existsSync(CATALOG_PY), `no existe ${CATALOG_PY}`).toBe(true);
  });

  it('5. hay al menos 23 ids (una regex que deja de matchear daria 2 listas vacias IGUALES)', () => {
    expect(catalogIds().length).toBeGreaterThanOrEqual(23);
  });

  it('6. la paleta ofrece al menos 12 LECTURAS ejecutables (KPI-2)', () => {
    const entradas = catalogEntries();
    // Sin este piso, una regex rota daria 0 y el test 3 pasaria igual.
    expect(entradas.length).toBeGreaterThanOrEqual(23);
    // reach=canonical_reach("read") es la UNICA tupla que contiene palette-run.
    const lecturasEjecutables = entradas.filter(
      (e) => e.effect === 'read' && e.reach === 'read'
    );
    expect(lecturasEjecutables.length).toBeGreaterThanOrEqual(12);
  });

  it('7. ningun write tiene palette-run (KPI-9, espejo del test 11 del backend)', () => {
    // Verificado desde el lado del frontend a proposito: borrar el test de
    // Python no alcanza para reabrir el agujero.
    const ofensores = catalogEntries()
      .filter((e) => e.effect === 'write' && e.reach !== 'write')
      .map((e) => e.id);
    expect(
      ofensores,
      `escrituras con el reach de LECTURA (ejecutables desde la paleta): ${ofensores.join(', ')}`
    ).toEqual([]);
    // Y ninguna declara su reach con una tupla literal.
    expect(src()).not.toMatch(/^\s*reach=\(/m);
  });
});
