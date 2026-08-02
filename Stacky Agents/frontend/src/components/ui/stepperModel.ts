/**
 * stepperModel.ts — Plan 294 F8. Logica PURA de la primitiva de pasos.
 *
 * POR QUE EXISTE. El sistema de disenio tenia 18 primitivas y ninguna de pasos.
 * El unico molde con logica pura reaprovechable era MigratorWizard.logic.ts,
 * pero su tipo de paso es un union literal CERRADO del migrador: se copia el
 * patron, no el archivo.
 *
 * POR QUE ES .ts Y NO .tsx. Este repo NO tiene RTL ni jsdom instalados. Un test
 * que renderice un componente reporta "no tests" y sale con exito: un falso
 * verde perfecto. Toda la logica testeable vive aca; el .tsx queda de cascaron.
 *
 * PURA: sin DOM, sin red, sin estado global. Ninguna funcion lanza.
 */

export interface StepDef {
  id: string;
  label: string;
  optional?: boolean;
}

export type StepStatus = 'pendiente' | 'actual' | 'completo' | 'bloqueado';

/** Indice 0-based del paso, o -1 si el id no existe. NUNCA lanza. */
export function stepIndex(steps: StepDef[], id: string): number {
  return (steps ?? []).findIndex((s) => s.id === id);
}

/** El id del paso siguiente, o null si es el ultimo (o el id no existe). */
export function nextStepId(steps: StepDef[], current: string): string | null {
  const i = stepIndex(steps, current);
  if (i < 0 || i >= steps.length - 1) return null;
  return steps[i + 1].id;
}

/** El id del paso anterior, o null si es el primero (o el id no existe). */
export function prevStepId(steps: StepDef[], current: string): string | null {
  const i = stepIndex(steps, current);
  if (i <= 0) return null;
  return steps[i - 1].id;
}

/**
 * Estado visual de UN paso.
 *
 * `bloqueado` no es decoracion: marca un paso posterior al actual que NO esta
 * hecho y que ademas quedo salteado (hay un hueco antes). Es la diferencia
 * entre "todavia no llegaste" y "no podes llegar desde aca".
 */
export function stepStatus(
  steps: StepDef[],
  current: string,
  done: string[],
  id: string,
): StepStatus {
  const hechos = new Set(done ?? []);
  if (id === current) return 'actual';
  if (hechos.has(id)) return 'completo';

  const iActual = stepIndex(steps, current);
  const iEste = stepIndex(steps, id);
  if (iEste < 0 || iActual < 0) return 'pendiente';
  if (iEste < iActual) return 'pendiente';
  if (iEste === iActual + 1) return 'pendiente';
  return 'bloqueado';
}

/** "3 de 7". Con un id desconocido arranca en 1: nunca muestra "0 de 7". */
export function progressLabel(steps: StepDef[], current: string): string {
  const total = (steps ?? []).length;
  const i = stepIndex(steps, current);
  return `${i < 0 ? 1 : i + 1} de ${total}`;
}
