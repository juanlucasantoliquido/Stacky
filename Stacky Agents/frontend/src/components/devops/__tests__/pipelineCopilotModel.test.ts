// Plan 279 F8 — Tests de la logica PURA del copiloto de pipelines. 8 casos.
import { describe, expect, it } from 'vitest';
import {
  COPILOT_ACTION_IDS,
  COPILOT_RUNTIMES,
  COPILOT_WRITE_ACTION_ID,
  SESSION_STATES,
  availableActionIds,
  copilotStartBody,
  mustShowUndoHint,
  needsOperatorConfirmation,
  missingWriteFlags,
  pickCopilotConversation,
  resolveCopilotTarget,
  stateLabel,
} from '../pipelineCopilotModel';

describe('Plan 279 F8 — pipelineCopilotModel', () => {
  it('1. SESSION_STATES tiene 8 entradas (espejo de PIPELINE_SESSION_STATES)', () => {
    expect(SESSION_STATES).toHaveLength(8);
    expect(new Set(SESSION_STATES).size).toBe(8);
  });

  it('2. stateLabel no devuelve vacio para ninguno de los 8', () => {
    for (const s of SESSION_STATES) {
      expect(stateLabel(s).trim(), `estado sin etiqueta: ${s}`).not.toBe('');
    }
  });

  it('3. availableActionIds("confirm") incluye la accion de commit', () => {
    expect(availableActionIds('confirm')).toContain(COPILOT_WRITE_ACTION_ID);
  });

  it('4. availableActionIds("intake") no ofrece ninguna escritura', () => {
    // GUARD anti-falso-verde: primero probamos que el detector SI encuentra una
    // escritura donde la hay. Sin esto, una lista vacia haria pasar el assert de
    // ausencia por accidente.
    expect(availableActionIds('confirm')).toContain(COPILOT_WRITE_ACTION_ID);
    expect(availableActionIds('intake').length).toBeGreaterThan(0);
    // Y recien ahora, la ausencia.
    expect(availableActionIds('intake')).not.toContain(COPILOT_WRITE_ACTION_ID);
  });

  it('5. needsOperatorConfirmation solo es true en "confirm"', () => {
    expect(needsOperatorConfirmation('confirm')).toBe(true);
    expect(needsOperatorConfirmation('review')).toBe(false);
  });

  it('6. los ids devueltos son subconjunto de los 6 del plan', () => {
    const universo = new Set<string>(COPILOT_ACTION_IDS);
    expect(COPILOT_ACTION_IDS).toHaveLength(6);
    const intrusos: string[] = [];
    for (const s of SESSION_STATES) {
      for (const id of availableActionIds(s)) {
        if (!universo.has(id)) intrusos.push(`${s}:${id}`);
      }
    }
    expect(intrusos, `ids fuera del catalogo del plan: ${intrusos.join(', ')}`).toEqual([]);
  });

  it('7. COPILOT_RUNTIMES tiene los 3 ids y github_copilot es determinista', () => {
    expect(COPILOT_RUNTIMES.map((r) => r.id).sort()).toEqual(
      ['claude_code_cli', 'codex_cli', 'github_copilot']
    );
    const copilot = COPILOT_RUNTIMES.find((r) => r.id === 'github_copilot');
    expect(copilot?.mode).toBe('deterministic');
    // Los otros dos SI tienen turno CLI (si no, el aserto de arriba no discrimina).
    expect(COPILOT_RUNTIMES.filter((r) => r.mode === 'cli').map((r) => r.id).sort()).toEqual(
      ['claude_code_cli', 'codex_cli']
    );
  });

  it('8. mustShowUndoHint es true en review/secrets/confirm y false en los otros 5', () => {
    const conHint = SESSION_STATES.filter(mustShowUndoHint);
    expect(conHint.sort()).toEqual(['confirm', 'review', 'secrets']);
    const sinHint = SESSION_STATES.filter((s) => !mustShowUndoHint(s));
    expect(sinHint).toHaveLength(5);
  });
});

// ---------------------------------------------------------------------------
// Plan 288 — el copiloto se usa LOCAL, sin agente DevOps remoto, y el destino
// lo decide el proyecto.
// ---------------------------------------------------------------------------
describe('Plan 288 — el copiloto arranca local y el proyecto decide el destino', () => {
  it('9. copilotStartBody sella la sesion del copiloto y NO manda server_alias', () => {
    const body = copilotStartBody({
      project: 'RIPLEY',
      message: 'necesito una pipeline de build para el backend',
    });
    // PRESENCIA: el hilo nace sellado como sesion de pipeline (sin esto el
    // backend no envuelve el mensaje con el contrato del copiloto).
    expect(body.pipeline_session).toBeTruthy();
    expect(body.pipeline_session.state).toBe('intake');
    expect(body.project).toBe('RIPLEY');
    // AUSENCIA, en el MISMO caso: `server_alias` es lo que ata el turno a un
    // servidor remoto (api/devops_agent.py:146). El copiloto corre LOCAL.
    expect(Object.keys(body)).not.toContain('server_alias');
  });

  it('10. copilotStartBody deja elegir los 3 runtimes y cae en claude si no', () => {
    for (const r of COPILOT_RUNTIMES) {
      expect(copilotStartBody({ project: 'P', message: 'm', runtime: r.id }).runtime).toBe(r.id);
    }
    expect(copilotStartBody({ project: 'P', message: 'm' }).runtime).toBe('claude_code_cli');
    expect(copilotStartBody({ project: 'P', message: 'm', runtime: 'inventado' }).runtime)
      .toBe('claude_code_cli');
  });

  it('11. resolveCopilotTarget usa lo que dice el proyecto, en los dos sentidos', () => {
    const gl = resolveCopilotTarget({
      provider: 'gitlab', provider_source: 'project', pipeline_file: '.gitlab-ci.yml',
    });
    expect(gl.provider).toBe('gitlab');
    expect(gl.file).toBe('.gitlab-ci.yml');
    expect(gl.blocked).toBe(false);

    const ado = resolveCopilotTarget({
      provider: 'ado', provider_source: 'project', pipeline_file: 'azure-pipelines.yml',
    });
    expect(ado.provider).toBe('ado');
    expect(ado.file).toBe('azure-pipelines.yml');
    expect(ado.blocked).toBe(false);
  });

  it('12. sin proyecto que declare tracker NUNCA cae en ado: bloquea y lo explica', () => {
    // Guard anti-falso-verde: primero, que la funcion SI sabe resolver.
    expect(resolveCopilotTarget({ provider: 'ado', provider_source: 'project' }).provider)
      .toBe('ado');
    for (const payload of [
      null,
      {},
      { provider: '', provider_source: 'unknown' },
      { provider: 'jira', provider_source: 'project' },
      // provider poblado pero origen NO declarado por el proyecto: no alcanza.
      { provider: 'ado', provider_source: 'unknown' },
    ]) {
      const t = resolveCopilotTarget(payload);
      expect(t.provider, JSON.stringify(payload)).toBe('');
      expect(t.file, JSON.stringify(payload)).toBe('');
      expect(t.blocked, JSON.stringify(payload)).toBe(true);
      expect(t.message.trim(), JSON.stringify(payload)).not.toBe('');
    }
  });

  it('13. pickCopilotConversation retoma el hilo de copiloto mas reciente', () => {
    // El backend lista por id descendente, asi que el primero es el mas nuevo.
    const items = [
      { conversation_id: 30, pipeline_copilot: false },
      { conversation_id: 20, pipeline_copilot: true },
      { conversation_id: 10, pipeline_copilot: true },
    ];
    expect(pickCopilotConversation(items)).toBe(20);
    // Sin ninguno: null, no el primero de la lista (eso adoptaria un chat libre
    // y el copiloto mostraria un estado que esa conversacion no tiene).
    expect(pickCopilotConversation([{ conversation_id: 30, pipeline_copilot: false }])).toBeNull();
    expect(pickCopilotConversation([])).toBeNull();
    expect(pickCopilotConversation(undefined)).toBeNull();
  });
});

describe('Plan 288 — el copiloto declara qué le falta para poder escribir', () => {
  it('14. missingWriteFlags nombra las 2 flags OFF y ninguna cuando están ON', () => {
    // Con las dos prendidas: nada que declarar.
    expect(missingWriteFlags({
      pipeline_copilot_commit_enabled: true,
      agent_action_run_enabled: true,
    })).toEqual([]);
    // Cada una por separado, para que el test discrimine cuál falta.
    expect(missingWriteFlags({
      pipeline_copilot_commit_enabled: false,
      agent_action_run_enabled: true,
    })).toEqual(['STACKY_PIPELINE_COPILOT_COMMIT_ENABLED']);
    expect(missingWriteFlags({
      pipeline_copilot_commit_enabled: true,
      agent_action_run_enabled: false,
    })).toEqual(['STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED']);
    // Ausentes (health viejo) cuentan como OFF: avisar de más, nunca de menos.
    expect(missingWriteFlags({})).toEqual([
      'STACKY_PIPELINE_COPILOT_COMMIT_ENABLED',
      'STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED',
    ]);
  });
});
