import { describe, it, expect } from 'vitest';
import { countCapabilities, buildAwareness, classifyTab, CAPABILITY_KEYS } from './devopsShell';

describe('countCapabilities', () => {
  it('cuenta solo los true de CAPABILITY_KEYS', () => {
    const h = { flag_enabled: true, servers_enabled: true, agent_enabled: false, ado_commit_supported: true };
    expect(countCapabilities(h)).toEqual({ active: 2, total: CAPABILITY_KEYS.length });
  });
  it('health vacío ⇒ 0 activas', () => {
    expect(countCapabilities({}).active).toBe(0);
  });
});

describe('buildAwareness', () => {
  it('sin servidor seleccionado ⇒ "sin servidor activo" tono faint', () => {
    const segs = buildAwareness({}, null);
    expect(segs[0]).toEqual({ text: 'sin servidor activo', tone: 'faint' });
  });
  it('con alias ⇒ "<alias> activo" tono ok', () => {
    expect(buildAwareness({}, 'pf-pacifico')[0]).toEqual({ text: 'pf-pacifico activo', tone: 'ok' });
  });
  it('rdp_available true ⇒ segmento "RDP listo"', () => {
    expect(buildAwareness({ rdp_available: true }, null)[2].text).toBe('RDP listo');
  });
});

describe('classifyTab', () => {
  it('id igual a activeId ⇒ active', () => {
    expect(classifyTab({ id: 'a' }, {}, 'a').active).toBe(true);
  });
  it('healthKey ausente ⇒ nunca gated', () => {
    expect(classifyTab({ id: 'a' }, {}, 'x').gated).toBe(false);
  });
  it('healthKey en false ⇒ gated', () => {
    expect(classifyTab({ id: 'a', healthKey: 'k' }, { k: false }, 'x').gated).toBe(true);
  });
  it('healthKey en true ⇒ no gated', () => {
    expect(classifyTab({ id: 'a', healthKey: 'k' }, { k: true }, 'x').gated).toBe(false);
  });
});
