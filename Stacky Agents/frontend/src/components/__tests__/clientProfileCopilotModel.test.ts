/**
 * clientProfileCopilotModel.test.ts — Plan 296 F6.
 *
 * PROHIBIDO un .test.tsx con React Testing Library: RTL/jsdom NO estan
 * instalados y ese archivo reporta "no tests" con EXIT 0 — un falso verde.
 * Toda la logica testeable vive en el .ts puro.
 *
 * 15 casos declarados, 15 colectados.
 */
import { describe, expect, it } from 'vitest';

import {
  FICHA_CAMPOS,
  PROFILE_SESSION_STATES,
  RUNTIMES,
  RUNTIME_LABEL,
  accionesDisponibles,
  fichaIncompleta,
  motivoRuntimeNoDisponible,
  progresoTexto,
  puedeElegirRuntime,
  runtimeLabel,
  stateLabel,
} from '../clientProfileCopilotModel';

describe('clientProfileCopilotModel — espejo del backend', () => {
  // 1
  it('los siete estados del backend estan espejados', () => {
    expect(PROFILE_SESSION_STATES).toHaveLength(7);
    expect(PROFILE_SESSION_STATES).toEqual([
      'eleccion_runtime',
      'diagnostico',
      'preguntando',
      'propuesta',
      'confirmando',
      'aplicado',
      'detenido',
    ]);
  });

  // 2
  it('los tres runtimes estan espejados con los ids exactos', () => {
    expect([...RUNTIMES]).toEqual(['claude_code_cli', 'codex_cli', 'github_copilot']);
  });

  // 3
  it('los siete campos de la ficha estan espejados', () => {
    expect([...FICHA_CAMPOS]).toEqual([
      'disponible',
      'recomendado_para',
      'capacidades',
      'credenciales',
      'ejecucion',
      'si_falla',
      'como_cambiar',
    ]);
  });

  // 4
  it('stateLabel nunca devuelve vacio', () => {
    for (const s of PROFILE_SESSION_STATES) {
      expect(stateLabel(s).trim().length).toBeGreaterThan(0);
    }
    expect(stateLabel('estado_inventado').trim().length).toBeGreaterThan(0);
  });

  // 5
  it('RUNTIME_LABEL cubre los tres', () => {
    for (const r of RUNTIMES) {
      expect(RUNTIME_LABEL[r].trim().length).toBeGreaterThan(0);
    }
  });

  // 6
  it('runtimeLabel no inventa etiquetas para ids desconocidos', () => {
    expect(runtimeLabel('gpt5_cli')).toBe('gpt5_cli');
    expect(runtimeLabel('codex_cli')).toBe('Codex');
  });

  // 7
  it('aplicar deshabilitado nombra la flag cuando apply esta OFF', () => {
    const aplicar = accionesDisponibles('propuesta', false).find((a) => a.id === 'aplicar');
    expect(aplicar).toBeDefined();
    expect(aplicar!.habilitado).toBe(false);
    expect(aplicar!.motivo).toContain('STACKY_PROFILE_COPILOT_APPLY_ENABLED');
  });

  // 8
  it('ninguna accion desaparece cuando esta deshabilitada', () => {
    for (const s of PROFILE_SESSION_STATES) {
      expect(accionesDisponibles(s, false).length).toBe(accionesDisponibles(s, true).length);
    }
  });

  // 9
  it('toda accion deshabilitada tiene motivo no vacio', () => {
    for (const s of PROFILE_SESSION_STATES) {
      for (const habilitado of [true, false]) {
        for (const a of accionesDisponibles(s, habilitado)) {
          if (!a.habilitado) {
            expect(a.motivo.trim().length, `${s}/${a.id} sin motivo`).toBeGreaterThan(0);
          }
        }
      }
    }
  });

  // 10
  it('accionesDisponibles no lanza con un estado desconocido', () => {
    const acciones = accionesDisponibles('estado_inventado', true);
    expect(Array.isArray(acciones)).toBe(true);
    expect(acciones.length).toBeGreaterThan(0);
  });

  // 11
  it('fichaIncompleta detecta los campos faltantes', () => {
    const ficha: Record<string, unknown> = {};
    for (const c of FICHA_CAMPOS) ficha[c] = 'algo';
    delete ficha.si_falla;
    delete ficha.como_cambiar;
    expect(fichaIncompleta(ficha).sort()).toEqual(['como_cambiar', 'si_falla']);
  });

  // 12
  it('fichaIncompleta devuelve [] con la ficha completa', () => {
    const ficha: Record<string, unknown> = {};
    for (const c of FICHA_CAMPOS) ficha[c] = 'algo';
    expect(fichaIncompleta(ficha)).toEqual([]);
  });

  // 13
  it('puedeElegirRuntime es true antes de ejecutar y false en terminales', () => {
    for (const s of ['eleccion_runtime', 'diagnostico', 'preguntando', 'propuesta'] as const) {
      expect(puedeElegirRuntime(s), s).toBe(true);
    }
    for (const s of ['aplicado', 'detenido'] as const) {
      expect(puedeElegirRuntime(s), s).toBe(false);
    }
  });

  // 14
  it('progresoTexto muestra el avance de las requeridas', () => {
    expect(progresoTexto({ requeridas_ok: 2, requeridas_total: 3 })).toContain('2 de 3');
  });

  // 15
  it('motivoRuntimeNoDisponible devuelve el texto del backend, no uno inventado', () => {
    const delBackend = "No encontré el programa 'codex'. Instalalo o indicá su ruta completa.";
    expect(motivoRuntimeNoDisponible({ disponibilidad_motivo: delBackend })).toBe(delBackend);
    expect(motivoRuntimeNoDisponible({ disponibilidad_motivo: '' })).toBe('');
    expect(motivoRuntimeNoDisponible({})).toBe('');
  });
});
