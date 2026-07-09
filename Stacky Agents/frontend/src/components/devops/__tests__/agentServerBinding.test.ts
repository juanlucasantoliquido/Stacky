/**
 * Tests para agentServerBinding (Plan 108 F4/F6)
 *
 * Lógica PURA (sin React, sin RTL — gap conocido del repo). Determina si el
 * chat del agente DevOps / Ambientes debe anclarse al servidor seleccionado
 * según el health y la selección del panel.
 */
import { describe, it, expect } from 'vitest';
import { resolveAgentServerBinding } from '../agentServerBinding';

describe('resolveAgentServerBinding - Plan 108 F4', () => {
  it('1. sin servidor ⇒ {null, null, null}', () => {
    const binding = resolveAgentServerBinding(
      { remote_target_enabled: true, servers_enabled: true, remote_console_enabled: true },
      null,
    );
    expect(binding).toEqual({ sendAlias: null, badge: null, hint: null });
  });

  it('2. servidor + las 3 flags ON ⇒ sendAlias y badge correctos', () => {
    const binding = resolveAgentServerBinding(
      { remote_target_enabled: true, servers_enabled: true, remote_console_enabled: true },
      { alias: 'srv1', host: '10.0.0.5' },
    );
    expect(binding.sendAlias).toBe('srv1');
    expect(binding.badge).toContain('srv1');
    expect(binding.badge).toContain('10.0.0.5');
    expect(binding.hint).toBeNull();
  });

  it('3. servidor + remote_target OFF ⇒ sendAlias null y hint no nulo', () => {
    const binding = resolveAgentServerBinding(
      { remote_target_enabled: false, servers_enabled: true, remote_console_enabled: true },
      { alias: 'srv1', host: '10.0.0.5' },
    );
    expect(binding.sendAlias).toBeNull();
    expect(binding.badge).toBeNull();
    expect(binding.hint).not.toBeNull();
    expect(binding.hint).toContain('srv1');
  });

  it('4. servidor + remote_target ON pero console OFF ⇒ hint no nulo', () => {
    const binding = resolveAgentServerBinding(
      { remote_target_enabled: true, servers_enabled: true, remote_console_enabled: false },
      { alias: 'srv1', host: '10.0.0.5' },
    );
    expect(binding.sendAlias).toBeNull();
    expect(binding.hint).not.toBeNull();
  });

  it('5. el mismo binding sirve para Ambientes (no depende de la sección)', () => {
    // Smoke que fija el contrato del tipo: la firma no tiene nada específico
    // de "chat" ni de "ambientes" — EnvironmentsSection (F6) reusa esta MISMA
    // función sin ninguna lógica nueva.
    const health = { remote_target_enabled: true, servers_enabled: true, remote_console_enabled: true };
    const server = { alias: 'srv-amb', host: 'amb.local' };
    const forChat = resolveAgentServerBinding(health, server);
    const forEnvironments = resolveAgentServerBinding(health, server);
    expect(forChat).toEqual(forEnvironments);
  });
});
