/**
 * productionModel.ts — Plan 95 F4.
 * Lógica pura (sin I/O) del flujo "Llevar a producción" (MR/PR + merge HITL).
 */
import type { MrInfo } from '../api/endpoints';

/**
 * mergeButtonEnabled — el pipeline_status NO bloquea el botón: se MUESTRA,
 * la decisión de mergear con pipeline rojo/corriendo es del operador (HITL).
 */
export function mergeButtonEnabled(mr: Pick<MrInfo, 'state' | 'mergeable'>): boolean {
  return mr.state === 'open' && mr.mergeable === true;
}

/** pipelineStatusLabel — el estado del pipeline del MR/PR, en llano. */
export function pipelineStatusLabel(status: MrInfo['pipeline_status']): string {
  switch (status) {
    case 'created':
      return 'creado, todavía no arrancó';
    case 'pending':
      return 'pendiente';
    case 'running':
      return 'está corriendo…';
    case 'success':
      return 'pasó ✅';
    case 'failed':
      return 'falló ❌';
    case 'canceled':
      return 'cancelado';
    case 'none':
    default:
      return 'sin pipeline';
  }
}

/**
 * shouldContinuePolling [C5] — tope de 60 polls (~5 min a 5s), se pausa si la
 * pestaña está oculta (`document.hidden`) y se detiene si el MR ya no está open.
 */
export function shouldContinuePolling(
  pollCount: number,
  state: MrInfo['state'] | undefined,
  documentHidden: boolean,
): boolean {
  return state === 'open' && !documentHidden && pollCount < 60;
}
