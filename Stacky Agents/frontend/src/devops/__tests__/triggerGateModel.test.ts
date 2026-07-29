import { describe, expect, it } from 'vitest';

import { mensajeDeBloqueo, puedeDisparar, mensajeDegradado, avisoAdvertencia, type ReadinessView } from '../triggerGateModel';

const readiness = (over: Partial<ReadinessView> = {}): ReadinessView => ({
  verdict: 'ok',
  pending_count: 0,
  unknown_count: 0,
  missing: [],
  elapsed_ms: 3,
  resolved: true,
  source: 'calculado',
  ...over,
});

describe('plan 260 F6 — triggerGateModel (puro)', () => {
  it('1. mensajeDeBloqueo lista nombres, no valores', () => {
    const r = readiness({
      verdict: 'bloquea',
      pending_count: 2,
      missing: [
        { name: 'DEPLOY_HOST', environment: 'prod' },
        { name: 'SONAR_TOKEN', environment: 'prod' },
      ],
    });
    const msg = mensajeDeBloqueo(r);
    expect(msg).toContain('DEPLOY_HOST');
    expect(msg).toContain('SONAR_TOKEN');
    expect(msg).toContain('2');
  });

  it('2. puedeDisparar solo con ack cuando bloquea', () => {
    const r = readiness({ verdict: 'bloquea', pending_count: 1, missing: [{ name: 'X', environment: 'prod' }] });
    expect(puedeDisparar(r, false)).toBe(false);
    expect(puedeDisparar(r, true)).toBe(true);
  });

  it('3. degradado no bloquea el botón (nunca bloquear por ignorancia)', () => {
    const r = readiness({ verdict: 'degradado', resolved: false });
    expect(puedeDisparar(r, false)).toBe(true);
  });

  it('4. advierte muestra aviso pero habilita', () => {
    const r = readiness({ verdict: 'advierte', unknown_count: 1 });
    expect(puedeDisparar(r, false)).toBe(true);
    expect(avisoAdvertencia(r)).toContain('1');
  });

  it('5. (ADICIÓN 5) readiness muestra la latencia cuando excede el presupuesto', () => {
    const lento = readiness({ verdict: 'degradado', resolved: false, elapsed_ms: 1620 });
    const msg = mensajeDegradado(lento);
    expect(msg).toContain('1620');
    expect(msg.toLowerCase()).toContain('a tiempo');

    const rapido = readiness({ verdict: 'degradado', resolved: false, elapsed_ms: 3 });
    expect(mensajeDegradado(rapido).toLowerCase()).not.toContain('a tiempo');
  });
});
