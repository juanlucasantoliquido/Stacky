/**
 * Plan 270 F5 — Detección PURA de divergencia entre Stacky y el tracker.
 *
 * Divergente = Stacky dice "completed" pero el tablero sigue pintando la fila
 * como abierta. Es exactamente el sintoma que hizo que el operador abandonara
 * el tablero, y se calcula sin una sola llamada extra: ambos campos ya viajan
 * en el DTO de /api/incident-inbox/items.
 */
import type { IncidentInboxItem, IncidentInboxStatus } from "./incidentInboxModel";
import { nombreLargoDeTracker } from "../lib/trackerLabels";

/** Estado terminal de Stacky que implica "yo ya cerre esto". Espejo de
 *  services/status_vocabulary.py:11 TERMINAL_STATUSES, subconjunto "exitoso". */
export const STACKY_CLOSED_STATUS = "completed";

export const DIVERGENCE_BADGE_LABEL = "Sin sincronizar";
export const DIVERGENCE_BADGE_TITLE =
  "Stacky dio esta incidencia por cerrada, pero el tracker la sigue mostrando abierta.";

/** ¿Esta fila esta desalineada respecto del tracker? */
export function isDiverged(item: IncidentInboxItem): boolean {
  return item.stacky_status === STACKY_CLOSED_STATUS && item.is_open === true;
}

/** Cuantas filas de la lista estan desalineadas (el KPI del plan 270). */
export function countDiverged(items: IncidentInboxItem[]): number {
  return items.filter(isDiverged).length;
}

/** Formatea un NUMERO ya calculado. Cadena VACIA en 0, para que la UI no
 *  muestre un chip con cero (ruido).
 *
 *  Existe separada de divergenceSummary porque el chip consume el conteo del
 *  SERVIDOR (diverged_count, exacto por agregacion) y no la lista local, que
 *  viene truncada por MAX_ITEMS y filtrada por la busqueda. Sin esta funcion
 *  la key del backend NO tiene forma de llegar a la pantalla. */
export function formatDivergenceCount(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return "";
  return n === 1 ? "1 sin sincronizar" : `${n} sin sincronizar`;
}

/** Texto del chip a partir de una lista local. Fallback para un backend viejo
 *  que no manda diverged_count. Delega en formatDivergenceCount: una sola
 *  regla de formato, imposible que las dos vias digan cosas distintas. */
export function divergenceSummary(items: IncidentInboxItem[]): string {
  return formatDivergenceCount(countDiverged(items));
}

/** El conteo que manda: el del servidor si vino, el local si no.
 *  Este es el UNICO lugar donde se decide la precedencia.
 *
 *  PROHIBIDO reescribirlo como `serverCount ?? countDiverged(items)`: `??` solo
 *  cae ante null/undefined, asi que un NaN/Infinity del servidor ATRAVIESA y
 *  formatDivergenceCount devuelve "" => el chip desaparece y la divergencia se
 *  vuelve invisible, que es justo el bug que este plan existe para matar. El
 *  caso 16 del .test.ts es el gate. */
export function resolveDivergenceCount(
  serverCount: number | null | undefined,
  items: IncidentInboxItem[],
): number {
  return typeof serverCount === "number" && Number.isFinite(serverCount)
    ? serverCount
    : countDiverged(items);
}

/** Filtro del chip: cuando esta activo, solo las divergentes. */
export function filterDiverged(
  items: IncidentInboxItem[],
  onlyDiverged: boolean,
): IncidentInboxItem[] {
  return onlyDiverged ? items.filter(isDiverged) : items;
}

/** Gate del badge, ESTRICTO a `true`, espejo de resolveInboxActionsEnabled
 *  (incidentInboxActionsModel.ts:31-35): un backend viejo que no manda la key
 *  deja el badge oculto y la pagina sigue funcionando. */
export function resolveDivergenceBadgeEnabled(
  status: IncidentInboxStatus | null | undefined,
): boolean {
  return status?.divergence_badge_enabled === true;
}

/** Plan 270 F7 — Texto de una linea para el dry-run. "" si no hay que decir nada. */
export function describeCloseDestination(
  d: { resolved?: boolean; tracker_type?: string | null; native_state?: string;
       closes?: boolean; reason?: string; workaround?: string } | null | undefined,
): string {
  if (!d) return "";
  if (d.resolved !== true) {
    const causa = d.reason ?? "destino sin resolver";
    return d.workaround ? `No se puede cerrar: ${causa}. ${d.workaround}` : `No se puede cerrar: ${causa}`;
  }
  // Plan 282 F4 — el nombre sale del diccionario unico, no de un ternario que
  // asume que todo lo que no es GitLab es Azure DevOps.
  const donde = nombreLargoDeTracker(d.tracker_type);
  const cierra = d.closes === true ? "queda cerrada" : "NO queda cerrada";
  return `Se escribe en ${donde} como "${d.native_state}" — ${cierra}.`;
}
