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
