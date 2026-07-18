// frontend/src/services/routeFilters.ts — Plan 165 F2
// Serialización PURA de filtros de página a/desde querystring. offset NUNCA se
// serializa (la paginación no se comparte ni se persiste — ver plan §3.7).

export interface HistoryFilters {
  agent_type: string; runtime: string; status: string; days: string;
  limit: number; offset: number;   // offset se ignora al serializar
}

/** Filtros de Historial -> Record de query (solo claves NO vacías; sin offset). */
export function historyFiltersToQuery(f: HistoryFilters): Record<string, string> {
  const q: Record<string, string> = {};
  if (f.agent_type) q.agent_type = f.agent_type;
  if (f.runtime) q.runtime = f.runtime;
  if (f.status) q.status = f.status;
  if (f.days) q.days = f.days;
  // limit y offset NO se serializan (limit es fijo por página; offset no se comparte)
  return q;
}

/** Record de query -> filtros parciales de Historial (para rehidratar desde URL). */
export function historyFiltersFromQuery(q: Record<string, string>): Partial<HistoryFilters> {
  const out: Partial<HistoryFilters> = {};
  if (q.agent_type) out.agent_type = q.agent_type;
  if (q.runtime) out.runtime = q.runtime;
  if (q.status) out.status = q.status;
  if (q.days) out.days = q.days;
  return out;
}

export interface SysLogFilters {
  level: string; source: string; action: string; q: string;
  execution_id: string; ticket_id: string; from: string; to: string;
}

const SYSLOG_KEYS: (keyof SysLogFilters)[] =
  ["level", "source", "action", "q", "execution_id", "ticket_id", "from", "to"];

export function sysLogFiltersToQuery(f: SysLogFilters): Record<string, string> {
  const out: Record<string, string> = {};
  for (const k of SYSLOG_KEYS) { if (f[k]) out[k] = f[k]; }
  return out;
}

export function sysLogFiltersFromQuery(q: Record<string, string>): Partial<SysLogFilters> {
  const out: Partial<SysLogFilters> = {};
  for (const k of SYSLOG_KEYS) { if (q[k]) out[k] = q[k]; }
  return out;
}

// C5: claves de filtro que cada página POSEE en el querystring. Exportadas para
// que el efecto de reflejo (Paso 4) las quite de current.query sin acumular —
// NADA de "omitFilterKeys" inlineado a criterio del implementador.
export const HISTORY_FILTER_QUERY_KEYS = ["agent_type", "runtime", "status", "days"] as const;
export const SYSLOG_FILTER_QUERY_KEYS = SYSLOG_KEYS;

/** Quita de un Record de query las claves listadas (puro; para el Paso 4). */
export function omitKeys(
  q: Record<string, string>, keys: readonly string[],
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(q)) { if (!keys.includes(k)) out[k] = v; }
  return out;
}

/** C2: resolución de filtros AL MONTAR (puro, testeado). Precedencia:
 *  - Si la URL trae >=1 clave de filtro => la URL manda COMPLETA la vista
 *    (defaults + URL, IGNORANDO lo persistido): una URL compartida reproduce
 *    EXACTAMENTE la vista del que la compartió (sus campos vacíos no viajan,
 *    y no deben contaminarse con los filtros persistidos del receptor).
 *  - Si la URL no trae ninguna => defaults + persistido. El spread sobre
 *    defaults es además el merge ANTI-DRIFT (C5): useLocalStorageState hace
 *    JSON.parse sin merge, así que un shape persistido viejo (campo nuevo
 *    agregado a Filters) completa el faltante con su default en vez de
 *    filtrar undefined a la API. No hace falta versionar la key.
 */
export function resolveMountFilters<T extends object>(
  defaults: T, persisted: Partial<T>, fromUrl: Partial<T>,
): T {
  return Object.keys(fromUrl).length > 0
    ? { ...defaults, ...fromUrl }
    : { ...defaults, ...persisted };
}
