// Plan 279 F8 — Tests de la logica PURA del copiloto de pipelines. 8 casos.
import { describe, expect, it } from 'vitest';
import {
  COPILOT_ACTION_IDS,
  COPILOT_RUNTIMES,
  COPILOT_WRITE_ACTION_ID,
  SESSION_STATES,
  availableActionIds,
  mustShowUndoHint,
  needsOperatorConfirmation,
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
