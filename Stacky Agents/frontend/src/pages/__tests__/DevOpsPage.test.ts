/**
 * Tests para DevOpsPage (Plan 87 F4)
 * NOTA: Sin @testing-library/react, estos tests verifican estructura por grep/imports
 * El gate real es tsc + verificación manual de criterios binarios
 */

import { describe, it, expect } from 'vitest';

describe('DevOpsPage - F4 estructura extensible', () => {
  it('DEVOPS_SECTIONS exportado con firma render(ctx)', async () => {
    const mod = await import('../DevOpsPage');
    expect(mod.DEVOPS_SECTIONS).toBeDefined();
    expect(mod.DEVOPS_SECTIONS).toBeInstanceOf(Array);
    if (mod.DEVOPS_SECTIONS.length > 0) {
      const section = mod.DEVOPS_SECTIONS[0];
      expect(typeof section.render).toBe('function');
      // La firma recibe ctx: DevOpsSectionContext
      expect(section.render.length).toBeGreaterThanOrEqual(1);
    }
  });

  it('DevOpsHealth y DevOpsSectionContext están definidos como tipos', async () => {
    // Son interfaces TypeScript, no valores runtime
    // Lo verificamos con tsc (gate real) y confirmamos que el módulo exporta
    const mod = await import('../DevOpsPage');
    expect(mod.DEVOPS_SECTIONS).toBeDefined();
    expect(mod.DevOpsPage).toBeDefined();
    // DevOpsHealth y DevOpsSectionContext se usan internamente
    // y tsc verifica sus tipos en DevOpsPage.tsx
  });

  it('exporta FlagGateBanner para reuso en secciones futuras (88/89)', async () => {
    // El componente existe en components/devops/ y es reutilizable
    const { FlagGateBanner } = await import('../../components/devops/FlagGateBanner');
    expect(FlagGateBanner).toBeDefined();
    expect(typeof FlagGateBanner).toBe('function'); // FC es una función
  });
});

describe('Criterios binarios F4 (verificables por código)', () => {
  it('F4.d - C10: montaje persistente (no desmonta al navegar)', async () => {
    const fs = await import('fs');
    const devOpsPageContent = fs.readFileSync(
      'N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/pages/DevOpsPage.tsx',
      'utf-8'
    );
    // El render NO debe usar {activeId === s.id && s.render(ctx)} (desmontaría)
    // Debe usar display:none para ocultar
    const hasConditionalRender = /activeId\s*===\s*s\.id\s*&&\s*s\.render\(ctx\)/.test(devOpsPageContent);
    expect(hasConditionalRender).toBe(false);
  });

  it('F4.e - C20: shell no nombra ids fuera de DEVOPS_SECTIONS', async () => {
    const fs = await import('fs');
    const devOpsPageContent = fs.readFileSync(
      'N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/pages/DevOpsPage.tsx',
      'utf-8'
    );
    // "pipelines" solo debe aparecer dentro del array DEVOPS_SECTIONS
    const lines = devOpsPageContent.split('\n');
    let inDevOpsSections = false;
    let pipelinesOutsideSections = false;
    for (const line of lines) {
      if (line.includes('DEVOPS_SECTIONS')) inDevOpsSections = true;
      if (line.includes('export const DEVOPS_SECTIONS')) inDevOpsSections = true;
      if (inDevOpsSections && line.includes(']')) inDevOpsSections = false;
      if (!inDevOpsSections && line.includes('"pipelines"') && !line.trim().startsWith('//')) {
        pipelinesOutsideSections = true;
      }
    }
    expect(pipelinesOutsideSections).toBe(false);
  });

  it('F4.f - C20: barra de sub-tabs tiene flexWrap', async () => {
    const fs = await import('fs');
    const devOpsPageContent = fs.readFileSync(
      'N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/pages/DevOpsPage.tsx',
      'utf-8'
    );
    // La barra de sub-tabs debe tener flexWrap para soportar 5+ secciones
    const hasFlexWrap = /flexWrap\s*:\s*["']?wrap["']?/.test(devOpsPageContent);
    expect(hasFlexWrap).toBe(true);
  });

  it('F4.g - C20: gate declarativo en shell (healthKey => FlagGateBanner)', async () => {
    const fs = await import('fs');
    const devOpsPageContent = fs.readFileSync(
      'N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/pages/DevOpsPage.tsx',
      'utf-8'
    );
    // El shell debe verificar healthKey y renderizar FlagGateBanner si health[healthKey] !== true
    const hasGateLogic = /healthKey.*health\[.*\]\s*!==?\s*true.*FlagGateBanner/.test(devOpsPageContent);
    expect(hasGateLogic).toBe(true);
  });
});

// ── Plan 239 F3 — sección Resumen, aterrizaje (F3.4) y copiar (F3.5) ──────────
describe('Plan 239 F3 — cockpit DevOps', () => {
  const ROOT = 'N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src';

  async function read(rel: string): Promise<string> {
    const fs = await import('fs');
    return fs.readFileSync(`${ROOT}/${rel}`, 'utf-8');
  }

  it('test_resumen_es_la_primera_seccion', async () => {
    const mod = await import('../DevOpsPage');
    expect(mod.DEVOPS_SECTIONS[0].id).toBe('resumen');
  });

  it('test_resumen_tiene_gate_completo', async () => {
    const mod = await import('../DevOpsPage');
    const s = mod.DEVOPS_SECTIONS.find((x) => x.id === 'resumen')!;
    expect(s.healthKey).toBe('cockpit_enabled');
    expect(s.gateFlagKey).toBe('STACKY_DEVOPS_COCKPIT_ENABLED');
    expect(s.gateMessage).toBeTruthy();
  });

  it('test_overview_section_sin_estilos_inline', async () => {
    expect(await read('components/devops/DevOpsOverviewSection.tsx')).not.toContain('style={{');
  });

  it('test_overview_section_no_ejecuta', async () => {
    const src = await read('components/devops/DevOpsOverviewSection.tsx');
    // Solo lectura: nada de ejecutar, desplegar, revertir ni disparar.
    expect(src).not.toMatch(/\bexecute\(|\brollback\(|\btrigger\(|\bdeploy\(/);
  });

  it('test_aterrizaje_no_queda_gateado', async () => {
    const src = await read('pages/DevOpsPage.tsx');
    // El aterrizaje pasa por resolveLandingSection, no por el id crudo del array.
    expect(src).toContain('resolveLandingSection');
  });

  it('test_filtros_usan_el_eco_del_backend', async () => {
    const src = await read('components/devops/DevOpsOverviewSection.tsx');
    // Los 3 Select leen p.filters.*, NO el estado local (KPI-11).
    expect(src).toContain('value={p.filters.app_id ?? \'\'}');
    expect(src).toContain('value={p.filters.project ?? \'\'}');
    expect(src).toContain('value={String(p.filters.window_days)}');
  });

  it('test_filtros_en_la_querykey', async () => {
    const src = await read('components/devops/DevOpsOverviewSection.tsx');
    expect(src).toContain("queryKey: ['devops-overview', appId, project, windowDays]");
  });

  it('test_filtros_persisten', async () => {
    const src = await read('components/devops/DevOpsOverviewSection.tsx');
    expect(src).toContain('useLocalStorageState');
    for (const key of ['stacky.devops.overview.appId', 'stacky.devops.overview.project',
      'stacky.devops.overview.windowDays']) {
      expect(src).toContain(key);
    }
  });

  // ── F3.4 — aterrizaje (C1: BLOQUEANTE) ──
  it('test_outlet_renderiza_siempre_la_activa', async () => {
    const src = await read('pages/DevOpsPage.tsx');
    expect(src).toContain('!mountedIds.has(s.id) && s.id !== activeId');
  });

  it('test_aterrizaje_no_va_en_useState', async () => {
    const src = await read('pages/DevOpsPage.tsx');
    // grep NEGATIVO: el inicializador perezoso corre ANTES de que llegue la salud.
    expect(src).not.toMatch(/useState\(\s*\(\)\s*=>\s*resolveLandingSection/);
  });

  it('test_aterrizaje_espera_la_salud', async () => {
    const src = await read('pages/DevOpsPage.tsx');
    expect(src).toContain('landingApplied');
    expect(src).toContain('if (!healthQuery.data) return;');
  });

  it('test_aterrizaje_usa_handleTabClick', async () => {
    const src = await read('pages/DevOpsPage.tsx');
    expect(src).toMatch(/handleTabClick\(resolveLandingSection\(/);
  });

  // ── F3.5 — copiar resumen (KPI-12) ──
  it('test_overview_usa_CopyAsButton', async () => {
    const src = await read('components/devops/DevOpsOverviewSection.tsx');
    expect(src).toContain("import CopyAsButton from '../CopyAsButton'");
    expect(src).toContain('buildOverviewClipboardText');
  });

  it('test_overview_no_toca_el_portapapeles_a_mano', async () => {
    const src = await read('components/devops/DevOpsOverviewSection.tsx');
    expect(src).not.toContain('navigator.clipboard');
  });
});
