// Plan 267 F5 — 11 casos. Funcion pura + grep-gates sobre CommandPalette.tsx.
import fs from 'fs';
import path from 'path';
import { describe, expect, it, vi } from 'vitest';
import { devopsActionCommands, fuzzyScore } from '../commandPaletteData';
import type { DevOpsActionMeta } from '../../services/devopsActionTypes';

const PALETTE_TSX = path.resolve(__dirname, '../CommandPalette.tsx');

function meta(over: Partial<DevOpsActionMeta> = {}): DevOpsActionMeta {
  return {
    id: 'devops.servers.list',
    label: 'Listar servidores',
    summary: 'Muestra los servidores registrados del proyecto.',
    section_id: 'servidores',
    nav_path: '/devops/servidores',
    effect: 'read',
    impact: 'none',
    targets_environment: false,
    health_key: 'servers_enabled',
    flag_key: 'STACKY_DEVOPS_SERVERS_ENABLED',
    reach: ['button', 'palette-run', 'assistant'],
    params: [],
    phrases: [],
    ...over,
  };
}

const noop = () => {};

describe('Plan 267 F5 — devopsActionCommands', () => {
  it('1. sin acciones => []  (es el camino de la flag OFF: 404 => [])', () => {
    expect(devopsActionCommands([], noop, noop)).toEqual([]);
  });

  it('2. 12 acciones de lectura => 12 comandos, todos kind devops-action', () => {
    const acciones = Array.from({ length: 12 }, (_, i) =>
      meta({ id: `devops.lectura.n${i}`, label: `Lectura ${i}` })
    );
    const cmds = devopsActionCommands(acciones, noop, noop);
    expect(cmds).toHaveLength(12);
    expect(cmds.every((c) => c.kind === 'devops-action')).toBe(true);
  });

  it('3. todos los id empiezan con devops-action- y son unicos', () => {
    const acciones = [
      meta({ id: 'devops.a.uno' }),
      meta({ id: 'devops.a.dos' }),
      meta({
        id: 'devops.b.tres',
        effect: 'write',
        impact: 'high',
        reach: ['button', 'palette-nav', 'assistant'],
      }),
    ];
    const ids = devopsActionCommands(acciones, noop, noop).map((c) => c.id);
    expect(ids.every((i) => i.startsWith('devops-action-'))).toBe(true);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('4. una accion write produce un comando de NAVEGACION', () => {
    const w = meta({
      id: 'devops.pipeline.trigger',
      label: 'Disparar pipeline',
      effect: 'write',
      impact: 'high',
      nav_path: '/devops/pipelines',
      reach: ['button', 'palette-nav', 'assistant'],
    });
    const [c] = devopsActionCommands([w], noop, noop);
    expect(c.icon).toBe('⚠️');
    expect(c.label.startsWith('Ir a ')).toBe(true);
    expect(c.hint).toContain('se hace desde el panel');
  });

  it('5. run() de esa write llama a onNavigate y NO a onRun (KPI-9 en la paleta)', () => {
    const onRun = vi.fn();
    const onNavigate = vi.fn();
    const w = meta({
      id: 'devops.pipeline.trigger',
      effect: 'write',
      impact: 'high',
      nav_path: '/devops/pipelines',
      reach: ['button', 'palette-nav', 'assistant'],
    });
    devopsActionCommands([w], onRun, onNavigate)[0].run();
    expect(onNavigate).toHaveBeenCalledTimes(1);
    expect(onRun).toHaveBeenCalledTimes(0);
  });

  it('6. una accion read produce ⚡, hint = summary y su run() llama a onRun', () => {
    const onRun = vi.fn();
    const onNavigate = vi.fn();
    const a = meta();
    const [c] = devopsActionCommands([a], onRun, onNavigate);
    expect(c.icon).toBe('⚡');
    expect(c.hint).toBe(a.summary);
    c.run();
    expect(onRun).toHaveBeenCalledTimes(1);
    expect(onNavigate).toHaveBeenCalledTimes(0);
  });

  it('7. una accion con reach ["button"] NO aparece', () => {
    expect(devopsActionCommands([meta({ reach: ['button'] })], noop, noop)).toEqual([]);
  });

  it('8. fuzzyScore sigue devolviendo lo mismo (no-regresion del plan 129)', () => {
    expect(fuzzyScore('', 'lo que sea')).toBe(1);
    expect(fuzzyScore('tic', 'Ir a Tickets ADO')).toBe(100 - 'ir a tickets ado'.indexOf('tic'));
    expect(fuzzyScore('zzz', 'Ir a Tickets ADO')).toBe(0);
    expect(fuzzyScore('iad', 'Ir a Docs')).toBeGreaterThan(0);
    expect(fuzzyScore('docs', 'Ir a Docs')).toBe(100 - 'ir a docs'.indexOf('docs'));
    expect(fuzzyScore('ir', 'Ir a PM')).toBe(100);
  });
});

describe('Plan 267 F5 — grep-gates sobre CommandPalette.tsx', () => {
  const src = fs.readFileSync(PALETTE_TSX, 'utf8');

  it('9. la paleta NO sondea [C11: devopsPollingRatchet no cubre este archivo]', () => {
    // devopsPollingRatchet.test.ts escanea SOLO components/devops/, asi que
    // CommandPalette.tsx queda fuera de su alcance: este es su gate propio.
    expect(src.split('setInterval(').length - 1).toBe(0);
    expect(src.split('refetchInterval').length - 1).toBe(0);
  });

  it('10. el catalogo se pide UNA SOLA VEZ', () => {
    expect(src.split("'/devops/actions/catalog'").length - 1
      + src.split('"/devops/actions/catalog"').length - 1).toBe(1);
  });

  it('11. el catalogo se pide con rawGet, NO con api.get [C21]', () => {
    // api.get delega en request<T>() que hace `if (!res.ok) throw` en
    // client.ts (todo non-2xx), y el 404 es el camino documentado de la flag
    // OFF: con api.get la paleta rompe JUSTO con la flag apagada.
    //
    // El gate va por regex y no por el literal `rawGet(` que pedia el plan:
    // medido, la llamada idiomatica de este repo lleva el tipo de respuesta
    // como generico (`rawGet<{...}>(`), asi que el literal a secas es
    // insatisfacible y el gate nunca podria pasar. La regex acepta las dos
    // formas y sigue prohibiendo el wrapper que lanza.
    expect(src).toMatch(/\brawGet\s*(<[\s\S]*?>)?\s*\(/);
    expect(src).not.toContain('api.get(');
    expect(src).toContain('/devops/actions/catalog');
  });
});
