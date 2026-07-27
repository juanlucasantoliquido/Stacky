/**
 * devopsEndpointReach.test.ts — Plan 98 F5.bis (adición del arquitecto).
 *
 * CENTINELA DE ENDPOINT INERTE.
 *
 * Problema que ataca (C1 del plan 98): un endpoint del panel DevOps puede quedar
 * vivo en el backend, con su flag ON y sus tests verdes, y **sin un solo consumidor
 * en el frontend**. Nadie se entera. Le pasó exactamente a este plan: F2/F3
 * quedaron desplegadas 20 días con la flag ON y CERO call sites.
 *
 * Regla: por cada literal de ruta `/api/devops/...` declarado en `api/endpoints.ts`,
 * el método que la envuelve tiene que estar referenciado como `<Objeto>.<metodo>`
 * al menos una vez FUERA de `endpoints.ts`.
 *
 * Se compara por par `Objeto.metodo` (no por el nombre pelado del método) a
 * propósito: nombres como `list`, `health` u `overview` se repiten en decenas de
 * objetos y un grep del nombre suelto daría un verde falso siempre.
 *
 * Es un RATCHET con allowlist explícita: si alguien agrega un endpoint sin
 * consumidor, tiene que escribir su nombre acá A PROPÓSITO y explicar por qué.
 * Mismo mecanismo que `src/__tests__/devopsPollingRatchet.test.ts:22`.
 */
import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

const SRC_DIR = path.resolve(__dirname, '../../..');
const ENDPOINTS = path.join(SRC_DIR, 'api', 'endpoints.ts');

/**
 * BASELINE de deuda HEREDADA (medido el 2026-07-26, al nacer este centinela).
 *
 * El plan 98 v2 §F5.bis daba por sentado que la allowlist nacería VACÍA. Es falso:
 * el censo real encontró 9 rutas /api/devops/ declaradas y jamás llamadas, todas
 * ANTERIORES a este plan. Arreglarlas es deuda ajena y está fuera de alcance acá.
 *
 * Este baseline es un TECHO, no un permiso: el test de abajo prohíbe que crezca.
 * Cablear o borrar cualquiera de estas entradas ⇒ sacarla de la lista.
 *
 * OJO: un test que assertea `typeof X.metodo === 'function'` NO cuenta como call
 * site — es exactamente el antipatrón que este centinela existe para cazar (le
 * pasó a `DevOpsRemoteConsole.sendMessage`). Por eso el corpus excluye los tests.
 */
const ALLOWLIST: string[] = [
  'DevOps.parseYaml',                  // /api/devops/parse-yaml
  'DevOpsDeployments.updateApp',       // plan 120 — Centro de Despliegues
  'DevOpsDeployments.deleteApp',       // plan 120
  'DevOpsDeployments.run',             // plan 120
  'DevOpsDeployments.drift',           // plan 120
  'DevOpsDeployments.metrics',         // plan 120
  'DevOpsDeployments.diagnose',        // plan 120
  'DevOpsBuildWorkshop.doctor',        // plan 201 — Taller de Compilación
  'DevOpsRemoteConsole.sendMessage',   // plan 105 — solo lo referencia un test
];

export interface RutaDevOps {
  objeto: string;
  metodo: string;
  ruta: string;
  linea: number;
}

/** Extrae (objeto, metodo, ruta) de cada literal /api/devops/ del fuente dado. */
export function rutasDevOps(source: string): RutaDevOps[] {
  const lines = source.split(/\r?\n/);
  const out: RutaDevOps[] = [];
  let objeto = '';
  let metodo = '';
  lines.forEach((line, i) => {
    const objMatch = /^export const (\w+)\s*=\s*\{/.exec(line);
    if (objMatch) {
      objeto = objMatch[1];
      metodo = '';
      return;
    }
    // Método del objeto: 2 espacios de indentación + nombre + ':' o '('.
    const mMatch = /^ {2}(?:async\s+)?(\w+)\s*[:(]/.exec(line);
    if (mMatch) metodo = mMatch[1];
    const rMatch = /["'`](\/api\/devops\/[A-Za-z0-9_\-/]*)/.exec(line);
    if (rMatch && objeto && metodo) {
      out.push({ objeto, metodo, ruta: rMatch[1], linea: i + 1 });
    }
  });
  return out;
}

/** Todos los .ts/.tsx bajo src/, salvo endpoints.ts y los propios tests. */
function fuentesConsumidoras(dir: string, acc: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '__tests__') continue;
      fuentesConsumidoras(full, acc);
    } else if (/\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name)) {
      if (full !== ENDPOINTS) acc.push(full);
    }
  }
  return acc;
}

function huerfanas(): RutaDevOps[] {
  const rutas = rutasDevOps(fs.readFileSync(ENDPOINTS, 'utf-8'));
  const corpus = fuentesConsumidoras(SRC_DIR)
    .map((f) => fs.readFileSync(f, 'utf-8'))
    .join('\n');
  return rutas.filter((r) => {
    if (ALLOWLIST.includes(`${r.objeto}.${r.metodo}`)) return false;
    return !corpus.includes(`${r.objeto}.${r.metodo}`);
  });
}

describe('Plan 98 F5.bis — centinela de endpoint DevOps inerte', () => {
  it('el extractor reconoce objeto, método y ruta', () => {
    const fixture = [
      'export const DevOps = {',
      '  health: () => api.get("/api/devops/health"),',
      '  bootstrap: (p: string) => api.get(`/api/devops/bootstrap?project=${p}`),',
      '};',
    ].join('\n');
    expect(rutasDevOps(fixture)).toEqual([
      { objeto: 'DevOps', metodo: 'health', ruta: '/api/devops/health', linea: 2 },
      { objeto: 'DevOps', metodo: 'bootstrap', ruta: '/api/devops/bootstrap', linea: 3 },
    ]);
  });

  it('el censo encuentra rutas /api/devops/ reales en endpoints.ts (el test mide algo)', () => {
    const rutas = rutasDevOps(fs.readFileSync(ENDPOINTS, 'utf-8'));
    expect(rutas.length).toBeGreaterThan(10);
  });

  it('ninguna ruta /api/devops/ NUEVA queda sin call site fuera de endpoints.ts', () => {
    const malas = huerfanas();
    expect(
      malas,
      `endpoints DevOps INERTES (declarados y nunca llamados): ${JSON.stringify(malas, null, 2)}`,
    ).toEqual([]);
  });

  it('el baseline de deuda heredada no crece (ratchet) y no se pudre', () => {
    const source = fs.readFileSync(ENDPOINTS, 'utf-8');
    const declarados = new Set(rutasDevOps(source).map((r) => `${r.objeto}.${r.metodo}`));
    const corpus = fuentesConsumidoras(SRC_DIR)
      .map((f) => fs.readFileSync(f, 'utf-8'))
      .join('\n');
    // (a) el baseline no puede crecer: 9 es el techo medido el 2026-07-26.
    expect(ALLOWLIST.length).toBeLessThanOrEqual(9);
    // (b) toda entrada del baseline sigue siendo una ruta declarada Y sigue huérfana.
    //     Si alguien la cableó o la borró, hay que sacarla de la lista (si no, el
    //     baseline se vuelve una mentira que tapa regresiones futuras).
    const podridas = ALLOWLIST.filter((e) => !declarados.has(e) || corpus.includes(e));
    expect(
      podridas,
      `entradas del baseline ya resueltas o inexistentes — sacalas de ALLOWLIST: ${JSON.stringify(podridas)}`,
    ).toEqual([]);
  });
});
