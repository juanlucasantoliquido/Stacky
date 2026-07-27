/**
 * Modelo PURO de las acciones de la bandeja de incidencias: cerrar en el
 * tracker, resolver con un agente (que commitea y abre el PR) y hacer las dos
 * cosas en lote. Sin React, sin DOM, sin fetch: testeable con vitest en entorno
 * node (el repo no tiene @testing-library/react ni jsdom — ver el gap conocido
 * RTL/jsdom; el cableado se valida en el smoke manual).
 *
 * Levanta el guardarrail de SOLO LECTURA del Plan 238 detras de la flag
 * STACKY_INCIDENT_INBOX_ACTIONS_ENABLED, que viaja en /api/incident-inbox/status.
 */
import { canResolveWithAgent } from "./devResolverModel";
import type { IncidentInboxItem, IncidentInboxStatus } from "./incidentInboxModel";

/** Estado destino por defecto al cerrar una incidencia desde la bandeja. */
export const DEFAULT_FINISH_STATE = "Done";

/** Sugerencias del selector de estado destino (espejo de FinishWorkButton). */
export const FINISH_STATE_SUGGESTIONS = ["Done", "Closed", "Resolved"];

/** Motivo que queda registrado en el cierre en lote. El backend de finish-work
 *  exige un motivo de al menos 5 caracteres, asi que NUNCA puede quedar vacio. */
export const BULK_FINISH_REASON = "Cierre en lote desde la bandeja de incidencias";

/**
 * ¿La bandeja puede escribir? ESTRICTO a `true`: un backend viejo (que no manda
 * la key) o un status todavia sin cargar dejan la bandeja en modo solo lectura
 * — el comportamiento del Plan 238 y el seguro ante duda. Esto es deliberado y
 * NO sigue el fail-open de flagGate: aca abrir de mas significaria ofrecer
 * botones que el servidor va a rechazar.
 */
export function resolveInboxActionsEnabled(
  status: IncidentInboxStatus | null | undefined,
): boolean {
  return status?.actions_enabled === true;
}

/** Estado destino saneado: vacio o solo espacios ⇒ "Done". Nunca vacio. */
export function normalizeFinishState(raw: string | null | undefined): string {
  return (raw ?? "").trim() || DEFAULT_FINISH_STATE;
}

/** ¿Se puede cerrar esta incidencia desde la bandeja? Cerrar una ya cerrada no
 *  tiene sentido, asi que el boton solo aparece en las abiertas. */
export function canFinishIncident(args: {
  item: IncidentInboxItem;
  actionsEnabled: boolean;
}): boolean {
  return args.actionsEnabled && args.item.is_open === true;
}

/** ¿Se puede lanzar el Dev Resolutor sobre esta incidencia? Delega la regla de
 *  tipo/estado/ejecucion en canResolveWithAgent (Plan 166) para que la bandeja
 *  y el tablero NUNCA discrepen sobre que es resoluble. */
export function canResolveIncident(args: {
  item: IncidentInboxItem;
  actionsEnabled: boolean;
  devResolverEnabled: boolean;
  closedStates: string[];
}): boolean {
  if (!args.actionsEnabled) return false;
  return canResolveWithAgent({
    workItemType: args.item.work_item_type,
    adoState: args.item.ado_state,
    isRunning: args.item.stacky_status === "running",
    enabled: args.devResolverEnabled,
    closedStates: args.closedStates,
  });
}

/**
 * Parte la seleccion en lo que la accion SI puede tocar y lo que va a saltear.
 * Conserva el ORDEN de selectedIds (determinismo del lote), deduplica, y trata
 * los ids desconocidos como salteados — nunca como elegibles.
 */
export function partitionSelection(
  items: IncidentInboxItem[],
  selectedIds: number[],
  canAct: (item: IncidentInboxItem) => boolean,
): { eligible: number[]; skipped: number[] } {
  const byId = new Map(items.map((i) => [i.id, i]));
  const eligible: number[] = [];
  const skipped: number[] = [];
  const seen = new Set<number>();
  for (const id of selectedIds) {
    if (seen.has(id)) continue;
    seen.add(id);
    const item = byId.get(id);
    if (item !== undefined && canAct(item)) eligible.push(id);
    else skipped.push(id);
  }
  return { eligible, skipped };
}

/** Aviso honesto de lo que el lote NO va a tocar. null si no se saltea nada:
 *  un lote que ignora en silencio la mitad de la seleccion es una mentira. */
export function skippedNotice(skipped: number[]): string | null {
  if (skipped.length === 0) return null;
  const n = skipped.length;
  return n === 1
    ? "1 seleccionada quedo afuera (ya cerrada, con agente corriendo o no aplica)."
    : `${n} seleccionadas quedaron afuera (ya cerradas, con agente corriendo o no aplican).`;
}
