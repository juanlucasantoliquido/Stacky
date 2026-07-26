import { describe, expect, it } from 'vitest';

import {
  PHASE_LABELS,
  confidenceLabel,
  gapHeadline,
  phaseRows,
  profileErrorCopy,
  summaryRows,
  type Confidence,
  type PipelineProfileDto,
  type ProfileFieldDto,
} from '../pipelineProfileModel';

function field<T>(value: T, confidence: Confidence = 'alta', evidence = [{ location: 'steps[0]', detail: 'task X' }]): ProfileFieldDto<T> {
  return { value, confidence, evidence };
}

function profile(over: Partial<PipelineProfileDto> = {}): PipelineProfileDto {
  return {
    contract_version: '247.1',
    source_path: 'x.yml',
    stack: field(['dotnet_framework']),
    phases: {
      build: field(true),
      test: field(false),
      package: field(false),
      publish_artifact: field(true),
      deploy: field(false),
    },
    artifacts_published: field(['$(X)']),
    artifacts_consumed: field<string[]>([], 'desconocido', []),
    environments: field([{ name: 'Test', kind: 'test', resolved: true, possible_values: [] }]),
    agents: field([{ kind: 'hosted', name: 'windows-2022', os: true }]),
    triggers: field(['push']),
    purpose: 'Compila y publica artefactos.',
    purpose_source: 'plantilla',
    not_understood: [],
    parse_error: null,
    ...over,
  };
}

describe('phaseRows', () => {
  it('devuelve una fila por fase de PHASE_LABELS', () => {
    const rows = phaseRows(profile());
    expect(rows.length).toBe(Object.keys(PHASE_LABELS).length);
    expect(rows.map((r) => r.label)).toEqual(Object.values(PHASE_LABELS));
  });

  it('distingue ausencia verificada de ausencia dudosa', () => {
    const rows = phaseRows(profile());
    const test = rows.find((r) => r.label === 'Testea')!;
    expect(test.tone).toBe('gap');

    const dudoso = phaseRows(
      profile({
        phases: {
          ...profile().phases,
          test: { value: false, confidence: 'desconocido', evidence: [] },
        },
      }),
    ).find((r) => r.label === 'Testea')!;
    expect(dudoso.tone).toBe('unknown');
  });

  it('la fase presente es ok y trae su evidencia', () => {
    const build = phaseRows(profile()).find((r) => r.label === 'Compila')!;
    expect(build.tone).toBe('ok');
    expect(build.evidence[0]).toContain('steps[0]');
  });

  it('con parse_error devuelve []', () => {
    expect(phaseRows(profile({ parse_error: 'roto' }))).toEqual([]);
    expect(phaseRows(null)).toEqual([]);
  });
});

describe('summaryRows', () => {
  it('nunca imprime [object Object]', () => {
    const rows = summaryRows(profile());
    rows.forEach((r) => expect(r.text).not.toContain('[object Object]'));
  });

  it('formatea ambientes y agentes legibles', () => {
    const rows = summaryRows(profile());
    expect(rows.find((r) => r.label === 'Ambientes')!.text).toBe('Test');
    expect(rows.find((r) => r.label === 'Agente')!.text).toBe('hosted windows-2022');
  });

  it('marca el ambiente sin resolver', () => {
    const rows = summaryRows(
      profile({
        environments: field([
          { name: '${{ parameters.x }}', kind: 'desconocido', resolved: false, possible_values: ['Test'] },
        ]),
      }),
    );
    expect(rows.find((r) => r.label === 'Ambientes')!.text).toContain('sin resolver');
  });

  it('el self-hosted se lee distinto del hosted', () => {
    const rows = summaryRows(
      profile({ agents: field([{ kind: 'self_hosted', name: 'TEST-Server', os: null }]) }),
    );
    expect(rows.find((r) => r.label === 'Agente')!.text).toBe('self-hosted TEST-Server');
  });

  it('la tecnologia vacia no se inventa', () => {
    const rows = summaryRows(profile({ stack: field<string[]>([], 'desconocido', []) }));
    const tech = rows.find((r) => r.label === 'Tecnologia')!;
    expect(tech.text).toBe('no determinada');
    expect(tech.tone).toBe('unknown');
  });

  it('con parse_error devuelve []', () => {
    expect(summaryRows(profile({ parse_error: 'roto' }))).toEqual([]);
    expect(summaryRows(null)).toEqual([]);
  });
});

describe('gapHeadline', () => {
  it('solo con ausencia verificada', () => {
    expect(gapHeadline(profile())).toBe('No corre tests');
  });

  it('no habla si la ausencia es dudosa', () => {
    const p = profile({
      phases: { ...profile().phases, test: { value: false, confidence: 'desconocido', evidence: [] } },
    });
    expect(gapHeadline(p)).toBeNull();
  });

  it('no habla si la fase esta presente', () => {
    const p = profile({ phases: { ...profile().phases, test: field(true) } });
    expect(gapHeadline(p)).toBeNull();
  });

  it('con parse_error devuelve null', () => {
    expect(gapHeadline(profile({ parse_error: 'roto' }))).toBeNull();
    expect(gapHeadline(null)).toBeNull();
  });
});

describe('confidenceLabel', () => {
  it('cubre los 3 niveles', () => {
    expect(new Set([confidenceLabel('alta'), confidenceLabel('media'), confidenceLabel('desconocido')]).size).toBe(3);
  });
});

describe('profileErrorCopy', () => {
  it('copy de inventario no disponible', () => {
    expect(profileErrorCopy('HTTP 501 inventory_unavailable ...')).toBe(
      'Inventario de pipelines no disponible (plan 246): pegá el YAML',
    );
  });

  it('cualquier otro mensaje pasa sin tocar', () => {
    expect(profileErrorCopy('Network error')).toBe('Network error');
  });
});
