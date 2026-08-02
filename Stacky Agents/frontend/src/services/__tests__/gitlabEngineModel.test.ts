import { describe, it, expect } from 'vitest';
import {
  estaEncendido,
  valorParaGuardar,
  avisoDeApagado,
} from '../gitlabEngineModel';

describe('gitlabEngineModel — Plan 290 F5', () => {
  it('"true" enciende', () => {
    expect(estaEncendido('true')).toBe(true);
  });

  it('"1" enciende', () => {
    expect(estaEncendido('1')).toBe(true);
  });

  it('"yes" enciende', () => {
    expect(estaEncendido('yes')).toBe(true);
  });

  it('"false" no enciende', () => {
    expect(estaEncendido('false')).toBe(false);
  });

  it('"" no enciende', () => {
    expect(estaEncendido('')).toBe(false);
  });

  it('un valor basura no enciende por ser string no vacio', () => {
    expect(estaEncendido('quizas')).toBe(false);
    // "on" NO esta en la tabla del backend: si la interfaz lo aceptara,
    // mostraria encendido algo que al reiniciar nace apagado.
    expect(estaEncendido('on')).toBe(false);
  });

  it('undefined / null no encienden', () => {
    expect(estaEncendido(undefined)).toBe(false);
    expect(estaEncendido(null)).toBe(false);
  });

  it('se guardan STRINGS, nunca booleanos ni null', () => {
    expect(valorParaGuardar(true)).toBe('true');
    expect(valorParaGuardar(false)).toBe('false');
  });

  it('apagar avisa, encender no', () => {
    expect(avisoDeApagado(true)).toBeNull();
    expect(avisoDeApagado(false)).toContain('GitLab');
  });
});
