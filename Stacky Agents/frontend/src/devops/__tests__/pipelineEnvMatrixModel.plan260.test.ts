import { describe, expect, it } from 'vitest';

import {
  headline,
  pendienteVisible,
  pendingByEnvironment,
  type EnvMatrixResponse,
  type EnvRequirement,
  type ValueKind,
} from '../pipelineEnvMatrixModel';

const req = (name: string, kind: ValueKind = 'variable'): EnvRequirement => ({
  name,
  kind,
  provider: 'azure_devops',
  is_secret: kind === 'secret',
  declared_default: null,
  per_environment: true,
  confidence: 'alta',
  evidence: [],
});

const matrizConSecretoDeclarado = (): EnvMatrixResponse => ({
  environments: ['Production'],
  requirements: [req('SONAR_TOKEN', 'secret')],
  cells: [
    {
      requirement: 'SONAR_TOKEN',
      environment: 'Production',
      state: 'manual',
      source: 'declarada_sin_valor_verificable',
      note: 'el proveedor no informa si este secreto tiene valor: verificalo vos',
    },
  ],
  pending_count: 0, // (v3, C1) el contrato del 251: SOLO cuenta 'falta'
  pending_fingerprint: 'xyz',
  degraded: [],
  provider: 'azure_devops',
});

describe('plan 260 F6 — el titular cuenta el pendiente VISIBLE', () => {
  it('1. titular cuenta declarada_sin_valor_verificable aunque pending_count sea 0', () => {
    const m = matrizConSecretoDeclarado();
    expect(m.pending_count).toBe(0);
    expect(pendienteVisible(m)).toBe(1);
    expect(headline(m)).toContain('Te falta 1 valor');
    expect(headline(m)).not.toContain('No falta nada');
  });

  it('2. titular ignora un "manual" ajeno (source !== declarada_sin_valor_verificable)', () => {
    const m: EnvMatrixResponse = {
      ...matrizConSecretoDeclarado(),
      cells: [
        {
          requirement: 'CONEXION',
          environment: 'Production',
          state: 'manual',
          source: 'ninguna', // service_connection sin resolver: NO es pendiente visible
          note: null,
        },
      ],
    };
    expect(pendienteVisible(m)).toBe(0);
    expect(headline(m)).toContain('No falta nada');
  });

  it('3. pendingByEnvironment usa el mismo criterio que el titular', () => {
    const m = matrizConSecretoDeclarado();
    expect(pendingByEnvironment(m)).toEqual({ Production: 1 });
  });
});
