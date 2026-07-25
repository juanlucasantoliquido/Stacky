/**
 * services/trackerVocabulary.ts — Plan 218 F5.
 *
 * Lectura NEUTRAL de los campos de un ticket: prefiere el campo canónico y cae al
 * legacy `ado_*` si no está. Es la función que los subplanes de UI (232) van
 * adoptando gradualmente, SIN renombrar nada (P6: 495 usos de campos ado_* en 88
 * archivos siguen funcionando igual).
 *
 * Puro: sin estado, sin I/O, sin dependencias de React.
 */

/** Forma mínima que estos helpers necesitan. Acepta cualquier ticket del sistema. */
export interface TrackerFields {
  external_id?: number | null;
  ado_id?: number | null;
  tracker_state?: string | null;
  ado_state?: string | null;
  item_url?: string | null;
  ado_url?: string | null;
  item_type?: string | null;
  work_item_type?: string | null;
}

function firstPresent<T>(canonical: T | null | undefined, legacy: T | null | undefined): T | null {
  if (canonical !== undefined && canonical !== null) return canonical;
  if (legacy !== undefined && legacy !== null) return legacy;
  return null;
}

/** Id externo del ítem en su tracker. `null` si el ticket no trae ninguno. */
export function pickExternalId(t: TrackerFields | null | undefined): number | null {
  if (!t) return null;
  return firstPresent(t.external_id, t.ado_id);
}

/** Estado del ítem tal como lo nombra su tracker. */
export function pickState(t: TrackerFields | null | undefined): string | null {
  if (!t) return null;
  return firstPresent(t.tracker_state, t.ado_state);
}

/** URL del ítem en su tracker. */
export function pickUrl(t: TrackerFields | null | undefined): string | null {
  if (!t) return null;
  return firstPresent(t.item_url, t.ado_url);
}

/** Tipo del ítem (Epic / Task / Bug / …) según su tracker. */
export function pickItemType(t: TrackerFields | null | undefined): string | null {
  if (!t) return null;
  return firstPresent(t.item_type, t.work_item_type);
}
