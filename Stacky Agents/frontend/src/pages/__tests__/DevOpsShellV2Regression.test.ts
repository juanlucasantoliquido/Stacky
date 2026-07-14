/**
 * Plan 119 F5 — [ADICIÓN ARQUITECTO] regresión del shell v2, no dependiente de checklist manual.
 * Mismo idioma que DevOpsPage.test.ts (fs + regex sobre el código fuente, sin render/RTL).
 */
import { describe, it, expect } from 'vitest';
import * as fs from 'fs';

describe('Plan 119 F5 — regresión del shell v2', () => {
  it('ConnectionHealthStrip (Plan 116) se renderiza SIN condicionar a uiV2', () => {
    const src = fs.readFileSync(
      'N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/pages/DevOpsPage.tsx',
      'utf-8',
    );
    expect(src.includes('<ConnectionHealthStrip')).toBe(true);
    // No debe haber un `uiV2 &&`/`uiV2 ?` envolviendo directamente el render de ConnectionHealthStrip.
    const stripBlock = src.slice(
      src.indexOf('connection_doctor_enabled === true'),
      src.indexOf('<ConnectionHealthStrip') + 40,
    );
    expect(stripBlock.includes('uiV2')).toBe(false);
  });

  it('botón de descarga de scripts WinRM (Plan 118) sigue presente en ServersSection', () => {
    const src = fs.readFileSync(
      'N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/components/devops/ServersSection.tsx',
      'utf-8',
    );
    expect(src.includes('handleDownloadSetup')).toBe(true);
  });
});
