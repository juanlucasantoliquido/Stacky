/**
 * Tests Plan 91 F5/F6 — sección Servidores (TS-puro, sin render de React).
 * Mismo estilo que DevOpsPage.test.ts: import del array + grep de fuente con fs.
 */
import { describe, it, expect } from 'vitest';

describe('Plan 91 F5 — sección Servidores en DEVOPS_SECTIONS', () => {
  it('DEVOPS_SECTIONS contiene la entrada servidores con gate declarativo', async () => {
    const mod = await import('../DevOpsPage');
    const entry = mod.DEVOPS_SECTIONS.find((s) => s.id === 'servidores');
    expect(entry).toBeDefined();
    expect(entry!.healthKey).toBe('servers_enabled');
    expect(entry!.gateFlagKey).toBe('STACKY_DEVOPS_SERVERS_ENABLED');
    expect(typeof entry!.render).toBe('function');
    expect(entry!.gateMessage && entry!.gateMessage.length).toBeGreaterThan(0);
  });

  it('ServersSection no hand-rollea el gate (el shell lo hace, §3.7)', async () => {
    const fs = await import('fs');
    const src = fs.readFileSync(
      new URL('../../components/devops/ServersSection.tsx', import.meta.url),
      'utf-8',
    );
    expect(src.includes('FlagGateBanner')).toBe(false);
    expect(src.includes('STACKY_DEVOPS_SERVERS_ENABLED')).toBe(false);
  });
});

describe('Plan 91 F6 — selector de servidor activo en el shell', () => {
  it('shell no llama a servers con flag off (enabled guard)', async () => {
    const fs = await import('fs');
    const src = fs.readFileSync(
      new URL('../DevOpsPage.tsx', import.meta.url),
      'utf-8',
    );
    expect(src.includes('servers_enabled === true')).toBe(true);
  });

  it('localStorage key exacta', async () => {
    const fs = await import('fs');
    const src = fs.readFileSync(
      new URL('../DevOpsPage.tsx', import.meta.url),
      'utf-8',
    );
    expect(src.includes('stacky.devops.selectedServer')).toBe(true);
  });
});
