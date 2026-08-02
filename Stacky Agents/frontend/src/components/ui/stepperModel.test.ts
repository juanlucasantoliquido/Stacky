/**
 * stepperModel.test.ts — Plan 294 F8.
 *
 * La primitiva de pasos no existia en el sistema de disenio (18 primitivas, y
 * ninguna Stepper). Su logica vive en .ts PURO porque este repo no tiene RTL ni
 * jsdom: un .test.tsx que renderice reporta "no tests" y sale con exito, que es
 * un falso verde perfecto.
 */
import { describe, it, expect } from 'vitest';
import {
  progressLabel,
  nextStepId,
  prevStepId,
  stepIndex,
  stepStatus,
  type StepDef,
} from './stepperModel';

const PASOS: StepDef[] = [
  { id: 'p1', label: 'Uno' },
  { id: 'p2', label: 'Dos' },
  { id: 'p3', label: 'Tres' },
];

describe('stepperModel', () => {
  it('stepIndex ubica cada paso por su id', () => {
    expect(stepIndex(PASOS, 'p1')).toBe(0);
    expect(stepIndex(PASOS, 'p3')).toBe(2);
  });

  it('nextStepId del ultimo devuelve null', () => {
    expect(nextStepId(PASOS, 'p1')).toBe('p2');
    expect(nextStepId(PASOS, 'p3')).toBeNull();
  });

  it('prevStepId del primero devuelve null', () => {
    expect(prevStepId(PASOS, 'p3')).toBe('p2');
    expect(prevStepId(PASOS, 'p1')).toBeNull();
  });

  it('stepStatus produce los cuatro valores segun el caso', () => {
    expect(stepStatus(PASOS, 'p2', ['p1'], 'p1')).toBe('completo');
    expect(stepStatus(PASOS, 'p2', ['p1'], 'p2')).toBe('actual');
    expect(stepStatus(PASOS, 'p2', ['p1'], 'p3')).toBe('pendiente');
    // un paso posterior al actual que ademas no esta hecho y quedo salteado:
    expect(stepStatus(PASOS, 'p1', [], 'p3')).toBe('bloqueado');
  });

  it('progressLabel dice en que paso vas', () => {
    expect(progressLabel(PASOS, 'p2')).toBe('2 de 3');
  });

  it('un id inexistente no lanza', () => {
    expect(() => stepIndex(PASOS, 'pZ')).not.toThrow();
    expect(stepIndex(PASOS, 'pZ')).toBe(-1);
    expect(nextStepId(PASOS, 'pZ')).toBeNull();
    expect(prevStepId(PASOS, 'pZ')).toBeNull();
    expect(progressLabel(PASOS, 'pZ')).toBe('1 de 3');
  });
});
