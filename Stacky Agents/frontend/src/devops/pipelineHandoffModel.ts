/** Plan 252 F5 — modelo PURO del paquete de entrega. Sin React, sin fetch, sin DOM. */

export type FrontierVerdict = 'CAN' | 'CANNOT' | 'CANNOT_NOW' | 'UNKNOWN';

export interface FrontierAction {
  id: string;
  label: string;
  effective: FrontierVerdict;
  reason: string;
  probe_detail: string;
  manual_instruction?: string;
}

/** Lo que hizo Stacky. */
export function automaticActions(actions: FrontierAction[]): FrontierAction[] {
  return (actions || []).filter((a) => a.effective === 'CAN');
}

/** Lo que le toca al operador. Partición EXACTA con la anterior: UNKNOWN cuenta acá,
 *  nunca como resuelto. Falla cerrado también en la UI. */
export function manualActions(actions: FrontierAction[]): FrontierAction[] {
  return (actions || []).filter((a) => a.effective !== 'CAN');
}

/** Titular de una línea. */
export function frontierSummary(actions: FrontierAction[]): string {
  const total = (actions || []).length;
  if (total === 0) return 'Todavía no se consultó la frontera de capacidades.';
  const auto = automaticActions(actions).length;
  const manual = total - auto;
  if (manual === 0) return `Stacky resuelve las ${total} acciones: no te queda nada por hacer.`;
  return `Stacky resuelve ${auto} de ${total}; ${manual} ${manual === 1 ? 'queda' : 'quedan'} para vos.`;
}

const VERDICT_LABEL: Record<FrontierVerdict, string> = {
  CAN: 'Lo hace Stacky',
  CANNOT: 'Lo hacés vos',
  CANNOT_NOW: 'Lo hacés vos por ahora',
  UNKNOWN: 'Lo hacés vos (Stacky no pudo verificarlo)',
};

export function verdictLabel(v: FrontierVerdict): string {
  return VERDICT_LABEL[v] ?? VERDICT_LABEL.UNKNOWN;
}

/** null si el paquete se puede pedir; string con el motivo si no. */
export function blockedReason(args: { flagOn: boolean; yamlCount: number }): string | null {
  if (!args.flagOn) {
    return 'El paquete de entrega está apagado. Activá STACKY_PIPELINE_HANDOFF_BUNDLE_ENABLED en Configuración → Arnés.';
  }
  if (!args.yamlCount || args.yamlCount < 1) {
    return 'Todavía no hay ningún archivo de pipeline para empaquetar.';
  }
  return null;
}
