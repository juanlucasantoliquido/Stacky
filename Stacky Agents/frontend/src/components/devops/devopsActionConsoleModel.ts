// Plan 267 F6 — Logica PURA de la consola de acciones del agente.
//
// Todo lo testeable sin DOM vive acá: el repo no tiene RTL ni jsdom, así que si
// esta lógica viviera dentro del .tsx no habría forma de verificarla (gap
// estructural conocido). Los .tsx quedan como cascarones de presentación.
import type { DevOpsActionReceipt } from '../../services/devopsActionRunner';
import { IMPACT_TEXT } from '../../services/devopsActionRunner';

export type ProposalBlock =
  | ''
  | 'no_match'
  | 'ambiguous'
  | 'missing_params'
  | 'flag_off'
  | 'agent_write_disabled';

/** Los 6 estados que la tarjeta tiene que saber pintar. */
export const PROPOSAL_BLOCKS: ProposalBlock[] = [
  '',
  'no_match',
  'ambiguous',
  'missing_params',
  'flag_off',
  'agent_write_disabled',
];

export interface ProposalViewParam {
  name: string;
  label: string;
  value: string;
  source: 'operator' | 'default' | 'missing';
}

/** Espejo de lo que devuelve POST /devops/actions/propose, mas los labels que la
 *  tarjeta necesita para nombrar los parametros en castellano. */
export interface ProposalView {
  actionId: string;
  label: string;
  summary: string;
  navPath: string;
  effect: 'read' | 'write';
  impact: 'none' | 'low' | 'high';
  targetsEnvironment: boolean;
  environment: string;
  params: ProposalViewParam[];
  whatWillHappen: string;
  openQuestions: string[];
  alternatives: string[];
  confidence: number;
  needsConfirmation: boolean;
  blockedReason: ProposalBlock;
}

export type ChipTone = 'ok' | 'warn' | 'bad' | 'faint';

/** Texto EXACTO del boton principal segun el bloqueo. Nunca vacio. */
export function primaryActionLabel(p: ProposalView): string {
  switch (p.blockedReason) {
    case 'no_match':
      return 'Escribí de nuevo';
    case 'ambiguous':
      return 'Elegí una acción';
    case 'missing_params':
      return 'Completá los datos';
    case 'flag_off':
      return 'No disponible';
    case 'agent_write_disabled':
      return 'Ver en el panel';
    default:
      return p.effect === 'write' ? `Ejecutar: ${p.label}` : `Ejecutar: ${p.label}`;
  }
}

/** true si el boton Ejecutar debe estar deshabilitado. */
export function isRunDisabled(p: ProposalView): boolean {
  return p.blockedReason !== '';
}

/** Mensaje que explica POR QUE no se puede ejecutar, y QUE hacer al respecto. */
export function blockedExplanation(p: ProposalView): string {
  switch (p.blockedReason) {
    case '':
      return '';
    case 'no_match':
      return 'No entendí qué querés hacer. Probá nombrar la acción, por ejemplo «ver los logs».';
    case 'ambiguous':
      return 'Hay más de una acción que encaja con lo que pediste. Elegí cuál querés antes de seguir.';
    case 'missing_params':
      return `Faltan datos obligatorios: ${p.params
        .filter((x) => x.source === 'missing')
        .map((x) => x.label || x.name)
        .join(', ')}. Completalos y vuelvo a mostrarte qué va a pasar.`;
    case 'flag_off':
      return 'Esta acción está desactivada en la configuración del panel.';
    case 'agent_write_disabled':
      // Texto obligatorio del plan: la flag OFF no puede sentirse como una pared.
      return 'Esta acción escribe en un sistema real, y la ejecución desde el asistente está desactivada. Podés ejecutarla vos desde el panel: Ver en el panel te deja en la sección con los datos ya cargados.';
    default:
      return 'No se puede ejecutar todavía.';
  }
}

/** Chips a renderizar: SIEMPRE [accion, entorno, impacto] en ese orden. */
export function headerChips(
  p: ProposalView
): { text: string; tone: ChipTone }[] {
  const entornoFalta = p.targetsEnvironment && !p.environment;
  return [
    { text: p.label, tone: 'faint' },
    entornoFalta
      ? { text: 'Falta declarar el entorno', tone: 'bad' }
      : {
          text: p.targetsEnvironment ? p.environment : 'Sin entorno',
          tone: p.targetsEnvironment ? 'ok' : 'faint',
        },
    {
      text: IMPACT_TEXT[p.impact] ?? p.impact,
      tone: p.impact === 'high' ? 'bad' : p.impact === 'low' ? 'warn' : 'faint',
    },
  ];
}

/** Recibo -> linea legible. */
export function receiptLine(r: DevOpsActionReceipt): string {
  const ms = Math.max(0, r.finishedAt - r.startedAt);
  if (!r.confirmed) {
    return `⛔ Cancelado por el operador: no se ejecutó nada (${ms} ms).`;
  }
  const icono = r.ok ? '✅' : '❌';
  const detalle = r.detail ? ` — ${r.detail}` : '';
  return `${icono} ${r.summary}${detalle} (${ms} ms)`;
}

/** Ruta del boton "Ver en el panel": lleva los datos, no la ruta pelada [C20]. */
export function verEnElPanelPath(p: ProposalView): string {
  const pairs = p.params
    .filter((x) => String(x.value ?? '').trim())
    .map((x) => [x.name, String(x.value).trim()] as const)
    .sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))
    .map(
      ([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`
    );
  return pairs.length ? `${p.navPath}?${pairs.join('&')}` : p.navPath;
}
