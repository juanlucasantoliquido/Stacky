/**
 * pipelineWizardModel.test.ts — Plan 294 F8.
 *
 * R4 es el riel duro de este archivo: la eleccion de runtime NUNCA se degrada
 * sola. `strictRuntime` devuelve el PEDIDO o null, jamas otro. El caso 14 es la
 * mitad que faltaba: los casos 8-10 prueban `strictRuntime`, no el camino real,
 * asi que ademas se verifica por lectura del fuente que el modelo del asistente
 * no rutea por el normalizador permisivo del copiloto (que ante un id
 * desconocido cae al primero, en silencio).
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { SESSION_STATES } from './pipelineCopilotModel';
import {
  WIZARD_ACT_IDS,
  WIZARD_RUNTIME_IDS,
  WIZARD_STEPS,
  advanceWizard,
  buildIntent,
  canAdvance,
  emptyWizardState,
  goBack,
  nextActAfter,
  parseDraft,
  resolveWizardRuntime,
  serializeDraft,
  stepState,
  strictRuntime,
  type WizardState,
} from './pipelineWizardModel';

const PROBE = {
  project: 'RecoveryStrategy',
  repository: 'RecoveryStrategy',
  provider: 'ado',
  default_branch: 'main',
  stack: 'dotnet',
  framework: '.NET',
  package_manager: 'nuget',
  build_command: 'dotnet build',
  test_command: 'dotnet test',
  variables: ['NUGET_FEED'],
};

function conObjetivo(goal: string): WizardState {
  return { ...emptyWizardState(), goal, step: 'p2' };
}

describe('pipelineWizardModel', () => {
  it('tiene los 7 pasos con ids unicos p1..p7', () => {
    expect(WIZARD_STEPS).toHaveLength(7);
    const ids = WIZARD_STEPS.map((s) => s.id);
    expect(new Set(ids).size).toBe(7);
    expect(ids).toEqual(['p1', 'p2', 'p3', 'p4', 'p5', 'p6', 'p7']);
  });

  it('sin objetivo no se puede avanzar, y dice por que', () => {
    const r = canAdvance({ ...emptyWizardState(), step: 'p2' });
    expect(r.ok).toBe(false);
    expect(r.reason.trim().length).toBeGreaterThan(0);
  });

  it('si no se puede avanzar, el paso no se mueve', () => {
    const antes = { ...emptyWizardState(), step: 'p2' };
    expect(advanceWizard(antes).step).toBe('p2');
  });

  it('R8 — volver no pierde lo que ya respondiste', () => {
    const s: WizardState = {
      ...conObjetivo('ejecutar_tests'),
      answers: { test_command: 'dotnet test', branches: 'main' },
    };
    const ida = advanceWizard(s);
    const vuelta = goBack(ida);
    expect(vuelta.step).toBe('p2');
    expect(vuelta.answers).toEqual(s.answers);
  });

  it('el borrador va y vuelve exacto', () => {
    const s: WizardState = {
      ...conObjetivo('ejecutar_tests'),
      answers: { test_command: 'pytest' },
      runtime: 'codex_cli',
      done: ['p1'],
    };
    expect(parseDraft(serializeDraft(s))).toEqual(s);
  });

  it('un borrador corrupto devuelve null en vez de lanzar', () => {
    expect(() => parseDraft('{basura')).not.toThrow();
    expect(parseDraft('{basura')).toBeNull();
  });

  it('sin borrador guardado devuelve null', () => {
    expect(parseDraft(null)).toBeNull();
  });

  it('R4 — si el runtime pedido no esta, devuelve null, NUNCA otro', () => {
    expect(strictRuntime('codex_cli', ['claude_code_cli', 'github_copilot'])).toBeNull();
  });

  it('R4 — si el runtime pedido esta, devuelve ese mismo', () => {
    expect(strictRuntime('codex_cli', ['codex_cli', 'claude_code_cli'])).toBe('codex_cli');
  });

  it('R4 — el gate duro: 3 pedidos x 8 subconjuntos = 24 combinaciones', () => {
    const todos = [...WIZARD_RUNTIME_IDS];
    const subconjuntos: string[][] = [];
    for (let mascara = 0; mascara < 8; mascara += 1) {
      subconjuntos.push(todos.filter((_, i) => (mascara >> i) & 1));
    }
    let vistas = 0;
    for (const pedido of todos) {
      for (const disponibles of subconjuntos) {
        const r = strictRuntime(pedido, disponibles);
        expect(r === pedido || r === null).toBe(true);
        expect(resolveWizardRuntime(pedido, disponibles)).toBe(r);
        vistas += 1;
      }
    }
    expect(vistas).toBe(24);
  });

  it('buildIntent produce exactamente las claves del contrato del backend', () => {
    const s: WizardState = {
      ...conObjetivo('ci_completo'),
      runtime: 'claude_code_cli',
      answers: { build_command: 'dotnet build', test_command: 'dotnet test' },
    };
    const intent = buildIntent(s, PROBE);
    expect(Object.keys(intent).sort()).toEqual(
      [
        'artifacts', 'build_command', 'constraints', 'coverage', 'default_branch',
        'deploy_target', 'environments', 'existing_pipeline_key', 'framework',
        'free_text', 'goal', 'package_manager', 'pipeline_kind', 'project',
        'provider', 'repository', 'required_secrets', 'runtime', 'schema_version',
        'stack', 'stages', 'test_command', 'triggers', 'variables',
      ].sort(),
    );
  });

  it('R3 — buildIntent nunca mete un valor en la lista de nombres', () => {
    const s: WizardState = {
      ...conObjetivo('ci_completo'),
      answers: { variables: 'API_KEY=secreto, NUGET_FEED' },
    };
    const intent = buildIntent(s, { ...PROBE, variables: ['TOKEN: abc', 'LIMPIA'] });
    const nombres = intent.variables as string[];
    for (const n of nombres) {
      expect(n).not.toContain('=');
      expect(n).not.toContain(':');
    }
  });

  it('C7 — el asistente habla el vocabulario de la maquina de estados que ya existe', () => {
    for (const paso of WIZARD_STEPS) {
      const estado = stepState(paso.id);
      expect(estado, `paso ${paso.id} sin estado`).toBeTruthy();
      expect(SESSION_STATES).toContain(estado as never);
    }
  });

  it('R4 — el modelo del asistente no rutea por el normalizador permisivo', () => {
    const fuente = readFileSync(
      new URL('./pipelineWizardModel.ts', import.meta.url),
      'utf-8',
    );
    expect(fuente).not.toContain('normalize' + 'CopilotRuntime');
  });

  it('R2 — los 4 actos del ultimo paso no se encadenan NUNCA', () => {
    expect(WIZARD_ACT_IDS).toHaveLength(4);
    expect(new Set(WIZARD_ACT_IDS).size).toBe(4);
    for (const acto of WIZARD_ACT_IDS) {
      expect(nextActAfter(acto)).toBeNull();
    }
    expect(nextActAfter('acto_inventado')).toBeNull();
  });
});
