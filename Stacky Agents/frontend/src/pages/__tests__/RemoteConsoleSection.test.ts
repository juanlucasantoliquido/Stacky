/**
 * Tests Plan 105 F4 — sección Consola remota.
 * Patrón TS-puro (sin render de React) como ServersSection.test.ts.
 */
import { describe, it, expect } from 'vitest';

describe('Plan 105 F4 — sección Consola remota en DEVOPS_SECTIONS', () => {
  it('DEVOPS_SECTIONS contiene la entrada remote-console con gate declarativo', async () => {
    const mod = await import('../DevOpsPage');
    const entry = mod.DEVOPS_SECTIONS.find((s) => s.id === 'remote-console');
    expect(entry).toBeDefined();
    expect(entry!.healthKey).toBe('remote_console_enabled');
    expect(entry!.gateFlagKey).toBe('STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED');
    expect(typeof entry!.render).toBe('function');
    expect(entry!.gateMessage && entry!.gateMessage.length).toBeGreaterThan(0);
  });

  it('RemoteConsoleSection no hand-rollea el gate (el shell lo hace, §3.7)', async () => {
    const fs = await import('fs');
    const src = fs.readFileSync(
      new URL('../../components/devops/RemoteConsoleSection.tsx', import.meta.url),
      'utf-8',
    );
    expect(src.includes('FlagGateBanner')).toBe(false);
    expect(src.includes('STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED')).toBe(false);
  });
});

describe('Plan 105 F4 — UX command-cards', () => {
  it('RemoteConsoleSection tiene command-cards para comandos frecuentes (UX-3)', async () => {
    const fs = await import('fs');
    const src = fs.readFileSync(
      new URL('../../components/devops/RemoteConsoleSection.tsx', import.meta.url),
      'utf-8',
    );
    expect(src.includes('List processes')).toBe(true);
    expect(src.includes('Disk usage')).toBe(true);
    expect(src.includes('Event logs')).toBe(true);
  });

  it('RemoteConsoleSection tiene tabs Conversación/Auditoría', async () => {
    const fs = await import('fs');
    const src = fs.readFileSync(
      new URL('../../components/devops/RemoteConsoleSection.tsx', import.meta.url),
      'utf-8',
    );
    expect(src.includes('Conversación')).toBe(true);
    expect(src.includes('Auditoría')).toBe(true);
    expect(src.includes('activeTab')).toBe(true);
  });

  it('RemoteConsoleSection tiene atajo Enter para ejecutar (UX-5)', async () => {
    const fs = await import('fs');
    const src = fs.readFileSync(
      new URL('../../components/devops/RemoteConsoleSection.tsx', import.meta.url),
      'utf-8',
    );
    expect(src.includes('Enter')).toBe(true);
    expect(src.includes('handleExec')).toBe(true);
  });
});

describe('Plan 105 F4 — cliente API', () => {
  it('DevOpsRemoteConsole está exportado en endpoints', async () => {
    const mod = await import('../../api/endpoints');
    expect(mod.DevOpsRemoteConsole).toBeDefined();
  });

  it('DevOpsRemoteConsole tiene métodos del plan 105', async () => {
    const mod = await import('../../api/endpoints');
    expect(typeof mod.DevOpsRemoteConsole.exec).toBe('function');
    expect(typeof mod.DevOpsRemoteConsole.getConversations).toBe('function');
    expect(typeof mod.DevOpsRemoteConsole.createConversation).toBe('function');
    expect(typeof mod.DevOpsRemoteConsole.sendMessage).toBe('function');
    expect(typeof mod.DevOpsRemoteConsole.setWriteMode).toBe('function');
    expect(typeof mod.DevOpsRemoteConsole.getAudit).toBe('function');
    expect(typeof mod.DevOpsRemoteConsole.checkWinrm).toBe('function');
  });

  it('DevOpsRemoteConsole usa rutas correctas', async () => {
    const fs = await import('fs');
    const src = fs.readFileSync(
      new URL('../../api/endpoints.ts', import.meta.url),
      'utf-8',
    );
    expect(src.includes('/api/devops/console/exec')).toBe(true);
    expect(src.includes('/api/devops/console/conversations')).toBe(true);
    expect(src.includes('/api/devops/console/audit')).toBe(true);
    expect(src.includes('/api/devops/console/winrm')).toBe(true);
  });
});
