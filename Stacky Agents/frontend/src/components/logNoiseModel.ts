/**
 * logNoiseModel.ts — Plan 257 F3: núcleo PURO de la tarjeta "Firmas de log más
 * repetidas".
 *
 * Módulo sin JSX y sin red a propósito: `@testing-library/react` y `jsdom` NO
 * están instalados en este frontend (solo vitest), así que un test de render no
 * puede correr. Lo testeable es esta función.
 *
 * READ-ONLY: el backend expone `snapshot()`, que NO resetea los contadores. La
 * interfaz mira el rastro, nunca lo borra.
 */

export interface LogNoiseSignature {
  /** `logger|levelno|template` con números y rutas normalizados SOLO en el tramo del mensaje. */
  signature: string;
  logger: string;
  /** DEBUG | INFO | WARNING (los graves nunca se agrupan). */
  level: string;
  /** Veces que se vio la firma desde el arranque. */
  count: number;
  /** Repeticiones agrupadas todavía pendientes de volcar. */
  suppressed: number;
  first_seen: string | null;
  last_seen: string | null;
}

export interface LogNoisePayload {
  /** El agrupado de repetidos está activo. */
  enabled?: boolean;
  /** La tarjeta está habilitada. Eje APARTE: apagar la tarjeta no apaga el dato. */
  card_enabled?: boolean;
  window_s?: number;
  flush_interval_s?: number;
  signatures?: LogNoiseSignature[] | null;
}

/** Tope de filas de la tarjeta: el operador quiere los peores, no el listado. */
export const LOG_NOISE_TOP = 10;

/**
 * Filas a pintar: las `LOG_NOISE_TOP` firmas con más repeticiones agrupadas.
 *
 * Devuelve `[]` (y la tarjeta no se renderiza) cuando la respuesta viene vacía,
 * cuando el agrupado está apagado o cuando el servidor es viejo y no manda el
 * bloque. Sin ruido visual cuando todo está limpio.
 */
export function buildLogNoiseRows(
  payload: LogNoisePayload | null | undefined
): LogNoiseSignature[] {
  if (!payload || payload.enabled === false || payload.card_enabled === false) return [];
  const firmas = payload.signatures;
  if (!Array.isArray(firmas) || firmas.length === 0) return [];
  return [...firmas]
    .filter((f) => f && typeof f.signature === "string")
    .sort((a, b) => (b.suppressed ?? 0) - (a.suppressed ?? 0) || (b.count ?? 0) - (a.count ?? 0))
    .slice(0, LOG_NOISE_TOP);
}

/** Etiqueta corta y legible de una firma: el template, sin el prefijo técnico. */
export function logNoiseLabel(signature: string): string {
  const partes = signature.split("|");
  return partes.length >= 3 ? partes.slice(2).join("|") : signature;
}
