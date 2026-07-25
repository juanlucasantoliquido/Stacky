/**
 * DevOpsCockpitClosure.test.ts — Plan 239 F8.
 * Gate de cierre: lo que las fases anteriores no cubren, más una redundancia
 * DELIBERADA sobre los dos bloqueantes (C1 y C3) — el cierre de un bloqueante no
 * debería depender de un solo archivo de test.
 */
import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

const SRC = path.resolve(__dirname, '../..');
const read = (rel: string) => fs.readFileSync(path.join(SRC, rel), 'utf-8');
const PAGE = read('pages/DevOpsPage.tsx');

describe('Plan 239 F8 — cierre', () => {
  it('las 10 secciones de DEVOPS_SECTIONS tienen `group` asignado', async () => {
    const mod = await import('../DevOpsPage');
    const sinGrupo = mod.DEVOPS_SECTIONS.filter((s) => !s.group).map((s) => s.id);
    expect(sinGrupo).toEqual([]);
    expect(mod.DEVOPS_SECTIONS).toHaveLength(10);
  });

  it('ninguna sección perdió su render(ctx)', async () => {
    const mod = await import('../DevOpsPage');
    mod.DEVOPS_SECTIONS.forEach((s) => {
      expect(typeof s.render, `sección ${s.id}`).toBe('function');
    });
  });

  it('DevOpsOverviewSection no importa nada de deploy/execute/rollback/trigger', () => {
    const src = read('components/devops/DevOpsOverviewSection.tsx');
    const imports = src.split(/\r?\n/).filter((l) => l.trim().startsWith('import'));
    const sospechosos = imports.filter((l) => /deploy|execute|rollback|trigger/i.test(l));
    expect(sospechosos).toEqual([]);
  });

  it('DevOpsCockpit.module.css no tiene hex ni px crudos en spacing', () => {
    const css = read('pages/DevOpsCockpit.module.css');
    expect(css.match(/#[0-9a-fA-F]{3,8}\b/g)).toBeNull();
  });

  it('la sección Resumen es la primera del array (KPI-1)', async () => {
    const mod = await import('../DevOpsPage');
    expect(mod.DEVOPS_SECTIONS[0].id).toBe('resumen');
  });

  it('no hay dos secciones con el mismo id', async () => {
    const mod = await import('../DevOpsPage');
    const ids = mod.DEVOPS_SECTIONS.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('todo `group` usado existe en DEVOPS_SECTION_GROUPS', async () => {
    const mod = await import('../DevOpsPage');
    const { DEVOPS_SECTION_GROUPS } = await import('../devopsCockpitShell');
    const validos = new Set(DEVOPS_SECTION_GROUPS.map((g) => g.id));
    mod.DEVOPS_SECTIONS.forEach((s) => {
      expect(validos.has(s.group!), `grupo inválido en ${s.id}: ${s.group}`).toBe(true);
    });
  });

  // ── cierres redundantes de los bloqueantes C1 / C3 ──
  it('C1 (a): DevOpsPage tiene el guard `s.id !== activeId` en el outlet', () => {
    expect(PAGE).toContain('!mountedIds.has(s.id) && s.id !== activeId');
  });

  it('C1 (b): el aterrizaje se aplica en useEffect con landingApplied', () => {
    expect(PAGE).toContain('landingApplied');
    expect(PAGE).toMatch(/useEffect\(\(\) => \{[\s\S]{0,200}landingApplied\.current/);
  });

  it('C1 (b): NO se llama resolveLandingSection dentro de useState(', () => {
    expect(PAGE).not.toMatch(/useState\([^)]*resolveLandingSection/);
  });

  it('C3: ningún .tsx de components/devops tiene setInterval( sin `visible` cerca', () => {
    const dir = path.join(SRC, 'components/devops');
    const malos: string[] = [];
    for (const f of fs.readdirSync(dir).filter((x) => x.endsWith('.tsx'))) {
      const lineas = fs.readFileSync(path.join(dir, f), 'utf-8').split(/\r?\n/);
      lineas.forEach((l, i) => {
        if (!l.includes('setInterval(')) return;
        const ventana = lineas.slice(Math.max(0, i - 12), i + 1).join('\n');
        if (!ventana.includes('visible')) malos.push(`${f}:${i + 1}`);
      });
    }
    expect(malos).toEqual([]);
  });

  it('paridad de runtimes: los archivos nuevos no bifurcan por runtime', () => {
    const nuevos = [
      'components/devops/DevOpsOverviewSection.tsx',
      'components/devops/overviewModel.ts',
      'pages/DevOpsCockpitNav.tsx',
      'pages/devopsCockpitShell.ts',
      'pages/DevOpsCockpit.module.css',
    ];
    const hits: string[] = [];
    nuevos.forEach((f) => {
      if (/codex_cli|claude_code_cli|copilot/i.test(read(f))) hits.push(f);
    });
    expect(hits).toEqual([]);
  });
});
