import { describe, it, expect } from 'vitest';
import {
  logFileName,
  truncationNote,
  jobLabel,
  errorLineHints,
  EMPTY_FAILED_JOBS_MSG,
  type FailedJob,
} from './ciFailureTriage';

describe('logFileName', () => {
  it('arma el nombre de descarga por job id', () => {
    expect(logFileName('123')).toBe('ci-log-123.txt');
    expect(logFileName('build#7')).toBe('ci-log-build#7.txt');
  });
});

describe('truncationNote', () => {
  it('null cuando no está truncado', () => {
    expect(truncationNote(false, 100)).toBeNull();
  });
  it('nota con separador de miles es-AR cuando truncado', () => {
    const note = truncationNote(true, 1000000);
    expect(note).not.toBeNull();
    // es-AR usa el punto como separador de miles.
    expect(note).toContain('1.000.000');
    expect(note).toContain('final del log');
  });
});

describe('jobLabel', () => {
  it('formatea stage · name', () => {
    const j: FailedJob = { job_id: '1', name: 'build', stage: 'ci', web_url: null };
    expect(jobLabel(j)).toBe('ci · build');
  });
});

describe('errorLineHints', () => {
  it('detecta error/failed/exception/fatal case-insensitive con índices 1-based', () => {
    const log = ['ok line', 'this FAILED here', 'clean', 'Exception raised', 'Fatal!'].join('\n');
    expect(errorLineHints(log)).toEqual([2, 4, 5]);
  });
  it('[] en log limpio', () => {
    expect(errorLineHints('todo bien\nsin problemas\nlisto')).toEqual([]);
  });
  it('cap 200 con log de 300 líneas-error', () => {
    const log = Array.from({ length: 300 }, () => 'error acá').join('\n');
    const hints = errorLineHints(log);
    expect(hints.length).toBe(200);
    expect(hints[0]).toBe(1);
  });
  it('no matchea substrings dentro de palabras (word-boundary)', () => {
    expect(errorLineHints('errores no cuenta\nerror sí')).toEqual([2]);
  });
});

describe('EMPTY_FAILED_JOBS_MSG', () => {
  it('el texto exacto está congelado (C1)', () => {
    expect(EMPTY_FAILED_JOBS_MSG).toBe(
      'No se encontraron jobs fallidos (puede ser un error de configuración del pipeline — abrilo en el tracker)',
    );
  });
});
