// Plan 267 F6 — 10 casos. Logica pura, sin DOM.
import { describe, expect, it } from 'vitest';
import type { DevOpsActionReceipt } from '../../services/devopsActionRunner';
import type { ProposalBlock, ProposalView } from './devopsActionConsoleModel';
import {
  PROPOSAL_BLOCKS,
  blockedExplanation,
  headerChips,
  isRunDisabled,
  primaryActionLabel,
  receiptLine,
  verEnElPanelPath,
} from './devopsActionConsoleModel';

function view(over: Partial<ProposalView> = {}): ProposalView {
  return {
    actionId: 'devops.deployment.execute',
    label: 'Ejecutar despliegue',
    summary: 'Corre el despliegue elegido en el entorno elegido.',
    navPath: '/devops/despliegues',
    effect: 'write',
    impact: 'high',
    targetsEnvironment: true,
    environment: 'prod',
    params: [
      { name: 'project', label: 'Proyecto', value: 'Pacifico', source: 'operator' },
      { name: 'environment', label: 'Entorno', value: 'prod', source: 'operator' },
    ],
    whatWillHappen: 'Ejecutar despliegue sobre el entorno prod. impacto alto.',
    openQuestions: [],
    alternatives: [],
    confidence: 1,
    needsConfirmation: true,
    blockedReason: '',
    ...over,
  };
}

function receipt(over: Partial<DevOpsActionReceipt> = {}): DevOpsActionReceipt {
  return {
    actionId: 'devops.deployment.execute',
    ok: true,
    summary: 'Despliegue ejecutado',
    detail: '',
    navPath: '/devops/despliegues',
    startedAt: 1000,
    finishedAt: 1234,
    confirmed: true,
    ...over,
  };
}

const NO_VACIOS: ProposalBlock[] = [
  'no_match',
  'ambiguous',
  'missing_params',
  'flag_off',
  'agent_write_disabled',
];

describe('Plan 267 F6 — devopsActionConsoleModel', () => {
  it('1. isRunDisabled: true para los 5 bloqueos, false para ""', () => {
    for (const b of NO_VACIOS) {
      expect(isRunDisabled(view({ blockedReason: b })), b).toBe(true);
    }
    expect(isRunDisabled(view({ blockedReason: '' }))).toBe(false);
  });

  it('2. primaryActionLabel nunca devuelve "" en los 6 estados', () => {
    expect(PROPOSAL_BLOCKS).toHaveLength(6);
    for (const b of PROPOSAL_BLOCKS) {
      expect(primaryActionLabel(view({ blockedReason: b })), b).not.toBe('');
    }
  });

  it('3. blockedExplanation("agent_write_disabled") contiene "Ver en el panel"', () => {
    expect(
      blockedExplanation(view({ blockedReason: 'agent_write_disabled' }))
    ).toContain('Ver en el panel');
  });

  it('4. blockedExplanation("missing_params") nombra un parametro faltante', () => {
    const p = view({
      blockedReason: 'missing_params',
      params: [
        { name: 'project', label: 'Proyecto', value: 'P', source: 'operator' },
        { name: 'environment', label: 'Entorno', value: '', source: 'missing' },
      ],
    });
    expect(blockedExplanation(p)).toContain('Entorno');
  });

  it('5. headerChips devuelve SIEMPRE 3 chips: accion / entorno / impacto', () => {
    const chips = headerChips(view());
    expect(chips).toHaveLength(3);
    expect(chips[0].text).toBe('Ejecutar despliegue');
    expect(chips[1].text).toBe('prod');
    expect(chips[2].text).toBe('Impacto alto');
  });

  it('6. targetsEnvironment con environment vacio => chip 2 tone bad', () => {
    const chips = headerChips(view({ environment: '' }));
    expect(chips[1].tone).toBe('bad');
    expect(chips[1].text).toBe('Falta declarar el entorno');
  });

  it('7. impact high => chip 3 tone bad', () => {
    expect(headerChips(view({ impact: 'high' }))[2].tone).toBe('bad');
    expect(headerChips(view({ impact: 'none' }))[2].tone).toBe('faint');
  });

  it('8. receiptLine de un recibo ok incluye ✅ y la duracion en ms', () => {
    const linea = receiptLine(receipt());
    expect(linea).toContain('✅');
    expect(linea).toContain('234 ms');
  });

  it('9. receiptLine con confirmed:false dice que lo cancelo el operador', () => {
    const linea = receiptLine(receipt({ confirmed: false, ok: false }));
    expect(linea).toContain('Cancelado por el operador');
    expect(linea).toContain('no se ejecutó nada');
  });

  it('10. "Ver en el panel" lleva los datos, no la ruta pelada [C20]', () => {
    expect(verEnElPanelPath(view())).toBe(
      '/devops/despliegues?environment=prod&project=Pacifico'
    );
    expect(
      verEnElPanelPath(
        view({
          params: [
            { name: 'project', label: 'Proyecto', value: '  ', source: 'missing' },
          ],
        })
      )
    ).toBe('/devops/despliegues');
  });
});
