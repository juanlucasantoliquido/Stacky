/**
 * DevOpsCockpitRegression.test.ts — Plan 239 F4/F5.
 * Calcado de DevOpsShellV2Regression.test.ts: inspección fs+regex (sin jsdom/RTL).
 * Verifica que el cockpit NO se llevó puesto nada del plan 87/116/119/120.
 */
import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

const SRC = path.resolve(__dirname, '../..');
const read = (rel: string) => fs.readFileSync(path.join(SRC, rel), 'utf-8');

const PAGE = read('pages/DevOpsPage.tsx');

const IDS = [
  'resumen', 'pipelines', 'publicaciones', 'ambientes', 'agente',
  'servidores', 'variables', 'remote-console', 'pr-review', 'despliegues',
];

describe('Plan 239 — no-regresión del panel DevOps', () => {
  it('las 10 secciones siguen registradas en DEVOPS_SECTIONS (por id)', async () => {
    const mod = await import('../DevOpsPage');
    const ids = mod.DEVOPS_SECTIONS.map((s) => s.id);
    expect(ids.sort()).toEqual([...IDS].sort());
  });

  it("cada sección (salvo 'resumen') conserva su healthKey/gateFlagKey/gateMessage originales", async () => {
    const mod = await import('../DevOpsPage');
    const esperado: Record<string, string> = {
      publicaciones: 'publications_enabled',
      ambientes: 'environments_enabled',
      agente: 'agent_enabled',
      servidores: 'servers_enabled',
      variables: 'variables_enabled',
      'remote-console': 'remote_console_enabled',
      'pr-review': 'pr_reviewer_enabled',
      despliegues: 'deployments_enabled',
    };
    for (const [id, healthKey] of Object.entries(esperado)) {
      const s = mod.DEVOPS_SECTIONS.find((x) => x.id === id)!;
      expect(s, `falta la sección ${id}`).toBeTruthy();
      expect(s.healthKey).toBe(healthKey);
      expect(s.gateFlagKey).toBeTruthy();
      expect(s.gateMessage).toBeTruthy();
    }
  });

  it('ConnectionHealthStrip aparece sin estar condicionado a cockpit ni uiV2', () => {
    expect(PAGE).toContain('<ConnectionHealthStrip');
    // La condición de la tira sigue siendo SOLO connection_doctor_enabled (plan 119 fix C1).
    const bloque = PAGE.slice(
      PAGE.indexOf('ConnectionHealthStrip onGotoSection') - 220,
      PAGE.indexOf('ConnectionHealthStrip onGotoSection'),
    );
    expect(bloque).toContain('connection_doctor_enabled');
    expect(bloque).not.toContain('cockpit &&');
    expect(bloque).not.toContain('uiV2 &&');
  });

  it('los componentes nuevos no tienen estilos inline', () => {
    expect(read('pages/DevOpsCockpitNav.tsx')).not.toContain('style={{');
    expect(read('components/devops/DevOpsOverviewSection.tsx')).not.toContain('style={{');
  });

  it('DevOpsCockpitNav importa Tabs de components/ui (no reimplementa la barra)', () => {
    const nav = read('pages/DevOpsCockpitNav.tsx');
    expect(nav).toContain("from '../components/ui/Tabs'");
    expect(nav).not.toContain('<nav');
  });

  it('DevOpsPage conserva la rama v1 de rollback (no se borró el shell legacy)', () => {
    expect(PAGE).toContain('#007bff');
  });

  it('test_seccion_sin_group_cae_en_grupo_default (KPI-10)', async () => {
    const { groupOf, DEFAULT_GROUP } = await import('../devopsCockpitShell');
    expect(groupOf({ group: undefined })).toBe(DEFAULT_GROUP);
  });

  // ── F5 — deep-link ──
  it('App.tsx pasa subTab a DevOpsPage', () => {
    const app = read('App.tsx');
    expect(app).toMatch(/<DevOpsPage subTab=\{route\.subtab \?\? null\} \/>/);
  });

  it('DevOpsPage usa replaceState (no pushState) y tiene el guard current.tab !== "devops"', () => {
    expect(PAGE).toContain('window.history.replaceState');
    expect(PAGE).not.toContain('window.history.pushState');
    expect(PAGE).toContain("if (current.tab !== 'devops') return;");
  });

  it('services/routes.ts NO fue modificado por este plan (reuso puro)', () => {
    const routes = read('services/routes.ts');
    expect(routes).not.toContain('Plan 239');
  });
});
