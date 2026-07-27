/**
 * devopsPollingRatchet.test.ts — Plan 239 F6.
 *
 * Ningún sondeo periódico de components/devops/ puede correr con la sección oculta.
 * Cubre DOS formas, no una (C3): un ratchet que solo mirara `refetchInterval` dejaría
 * viva la fuga de `setInterval`, que es la más agresiva de las tres.
 *
 * Regla por archivo .tsx de components/devops/:
 *   - cada línea con `refetchInterval:` ⇒ en esa línea o en las 2 siguientes debe
 *     aparecer `visible`;
 *   - cada línea con `setInterval(` ⇒ en las 12 líneas ANTERIORES debe aparecer
 *     `visible` (el guard va antes del setInterval).
 *
 * Es un RATCHET, no una foto: si mañana aparece un sondeo nuevo sin guarda, este
 * test lo caza aunque el censo cambie.
 */
import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

const DEVOPS_DIR = path.resolve(__dirname, '../components/devops');
const ALLOWLIST: string[] = []; // vacía a propósito: hoy no hay excepción legítima

const LOOKAHEAD_REFETCH = 2;
const LOOKBEHIND_INTERVAL = 12;

interface Hallazgo { file: string; line: number; kind: 'refetchInterval' | 'setInterval'; }

/**
 * Plan 103 F5.bis — ALCANCE EXTENDIDO (cambio aditivo; la regla de guarda no cambia).
 *
 * El censo original miraba SOLO los `.tsx` directos de components/devops/. Cualquier
 * sondeo puesto en un `.ts` (hooks, modelos) o en el shell de `pages/` era INVISIBLE
 * para este ratchet — justo el agujero por el que se colaría un hook de monitoreo.
 * Ahora también entran los `.ts` de components/devops/ y los 2 archivos del shell.
 */
const SHELL_FILES = [
  path.resolve(__dirname, '../pages/DevOpsPage.tsx'),
  path.resolve(__dirname, '../pages/DevOpsHeaderV2.tsx'),
];

function tsxFiles(): string[] {
  return fs.readdirSync(DEVOPS_DIR)
    .filter((f) => (f.endsWith('.tsx') || f.endsWith('.ts')) && !/\.test\.tsx?$/.test(f))
    .filter((f) => !ALLOWLIST.includes(f));
}

/** Rutas ABSOLUTAS de todo lo que el ratchet vigila (devops/ + shell). */
function pollingFiles(): Array<{ file: string; full: string }> {
  const out = tsxFiles().map((f) => ({ file: f, full: path.join(DEVOPS_DIR, f) }));
  for (const full of SHELL_FILES) {
    const file = path.basename(full);
    if (fs.existsSync(full) && !ALLOWLIST.includes(file)) out.push({ file, full });
  }
  return out;
}

/** Sondeos SIN guarda de visibilidad. Exportado para probar el helper con fixtures. */
export function unguardedPolling(source: string, file = '<fixture>'): Hallazgo[] {
  const lines = source.split(/\r?\n/);
  const out: Hallazgo[] = [];
  lines.forEach((line, i) => {
    if (line.includes('refetchInterval:')) {
      const ventana = lines.slice(i, i + 1 + LOOKAHEAD_REFETCH).join('\n');
      if (!ventana.includes('visible')) out.push({ file, line: i + 1, kind: 'refetchInterval' });
    }
    if (line.includes('setInterval(')) {
      const desde = Math.max(0, i - LOOKBEHIND_INTERVAL);
      const ventana = lines.slice(desde, i + 1).join('\n');
      if (!ventana.includes('visible')) out.push({ file, line: i + 1, kind: 'setInterval' });
    }
  });
  return out;
}

function censo(): { refetch: Hallazgo[]; intervals: Hallazgo[]; sinGuarda: Hallazgo[] } {
  const refetch: Hallazgo[] = [];
  const intervals: Hallazgo[] = [];
  const sinGuarda: Hallazgo[] = [];
  for (const { file, full } of pollingFiles()) {
    const src = fs.readFileSync(full, 'utf-8');
    src.split(/\r?\n/).forEach((line, i) => {
      if (line.includes('refetchInterval:')) refetch.push({ file, line: i + 1, kind: 'refetchInterval' });
      if (line.includes('setInterval(')) intervals.push({ file, line: i + 1, kind: 'setInterval' });
    });
    sinGuarda.push(...unguardedPolling(src, file));
  }
  return { refetch, intervals, sinGuarda };
}

describe('Plan 239 F6 — ratchet de sondeo del panel DevOps', () => {
  it('todo refetchInterval en components/devops/*.tsx está gateado por `visible` (KPI-4)', () => {
    const malos = censo().sinGuarda.filter((h) => h.kind === 'refetchInterval');
    expect(malos, `sondeo sin guarda: ${JSON.stringify(malos)}`).toEqual([]);
  });

  it('todo setInterval( en components/devops/*.tsx está gateado por `visible` (KPI-4, C3)', () => {
    const malos = censo().sinGuarda.filter((h) => h.kind === 'setInterval');
    expect(malos, `sondeo sin guarda: ${JSON.stringify(malos)}`).toEqual([]);
  });

  it('el censo detecta al menos los 2 refetchInterval y 2 setInterval conocidos', () => {
    const { refetch, intervals } = censo();
    expect(refetch.length).toBeGreaterThanOrEqual(2); // DeploymentsSection + DevOpsOverviewSection
    expect(intervals.length).toBeGreaterThanOrEqual(2); // los dos de TriggerPipelineSection
  });

  it('DeploymentsSection.tsx usa ctx.visible en su refetchInterval', () => {
    const src = fs.readFileSync(path.join(DEVOPS_DIR, 'DeploymentsSection.tsx'), 'utf-8');
    expect(src).toContain('refetchInterval: ctx.visible === false ? false : 4000');
  });

  it('TriggerPipelineSection.tsx gatea sus DOS setInterval con ctx.visible', () => {
    const src = fs.readFileSync(path.join(DEVOPS_DIR, 'TriggerPipelineSection.tsx'), 'utf-8');
    expect(src).toContain('if (ctx.visible === false) return;');
    expect(src).toContain('if (polling && pipelineId && ctx.visible !== false)');
  });

  it('TriggerPipelineSection.tsx incluye ctx.visible en las deps de ambos efectos', () => {
    const src = fs.readFileSync(path.join(DEVOPS_DIR, 'TriggerPipelineSection.tsx'), 'utf-8');
    // Sin esto pasaríamos de "sondea de más" a "no sondea nunca" al volver a la sección.
    expect(src).toContain('[runs, statusById, ledgerAvailable, project, ctx.visible]');
    expect(src).toContain('[polling, pipelineId, ctx.visible]');
  });

  it('la ALLOWLIST está vacía (si alguien la llena, tiene que justificarlo en el diff)', () => {
    expect(ALLOWLIST).toEqual([]);
  });

  it('el helper detecta el caso negativo de refetchInterval (fixture sin visible)', () => {
    const fixture = ['const q = useQuery({', '  refetchInterval: 4000,', '});'].join('\n');
    expect(unguardedPolling(fixture)).toHaveLength(1);
  });

  it('el helper detecta el caso negativo de setInterval (fixture sin visible)', () => {
    const fixture = ['useEffect(() => {', '  const i = setInterval(tick, 1000);', '}, []);'].join('\n');
    expect(unguardedPolling(fixture)).toHaveLength(1);
  });

  it('el helper acepta el caso positivo (guarda presente)', () => {
    const conGuarda = [
      'useEffect(() => {',
      '  if (ctx.visible === false) return;',
      '  const i = setInterval(tick, 1000);',
      '}, [ctx.visible]);',
    ].join('\n');
    expect(unguardedPolling(conGuarda)).toEqual([]);
  });
});
