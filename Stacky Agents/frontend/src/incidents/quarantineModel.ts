/**
 * quarantineModel.ts — Plan 256 F3: nucleo PURO de la tarjeta "Artefactos en
 * cuarentena" del panel de Diagnostico.
 *
 * Por que un modulo aparte: en esta casa `@testing-library/react` y `jsdom` no
 * estan instalados, asi que un componente React no se puede testear. Todo lo
 * que decide algo (si la tarjeta existe, como se lee la antiguedad, en que
 * orden aparecen los artefactos) vive aca, sin React ni fetch, y el componente
 * queda como cascara de render.
 *
 * Sin efectos: ninguna funcion de este archivo reintenta, descarta ni pide nada.
 */

/** Un artefacto en cuarentena, tal cual lo publica `GET /api/diag/intake-quarantine`. */
export interface QuarantineItem {
  /** Ruta absoluta del artefacto. Es la clave: el reintento la manda tal cual. */
  path: string;
  /** Razon COMPLETA del rechazo. Nunca se trunca en la UI: truncarla fue el bug. */
  reason: string;
  mtime_ns: number | null;
  file_name: string;
  /** Enum unico de causas: INTAKE_EMPTY, INTAKE_SCHEMA, ORIG_BACKUP_FAILED, ... */
  cause_code: string;
  first_seen: string | null;
  age_days: number;
  occurrences: number;
  has_original_backup: boolean;
  discarded: boolean;
  retryable: boolean;
}

/**
 * Si no hay nada en cuarentena, la tarjeta NO se renderiza: un panel de
 * diagnostico lleno de tarjetas vacias entrena al operador a ignorarlo.
 */
export function shouldRenderCard(count: number): boolean {
  return typeof count === "number" && Number.isFinite(count) && count > 0;
}

const MS_POR_DIA = 86_400_000;

/**
 * Antiguedad en dias enteros, en castellano llano. Es el dato que convierte una
 * lista en una urgencia: el caso testigo estuvo 11 dias atascado sin que nadie
 * lo viera. Tolerante con marcas de tiempo ilegibles (devuelve un texto neutro
 * en vez de romper la tarjeta).
 */
export function formatAge(firstSeenIso: string | null | undefined, nowIso: string): string {
  if (!firstSeenIso) return "antiguedad desconocida";
  const desde = Date.parse(firstSeenIso);
  const hasta = Date.parse(nowIso);
  if (Number.isNaN(desde) || Number.isNaN(hasta)) return "antiguedad desconocida";
  const dias = Math.max(Math.floor((hasta - desde) / MS_POR_DIA), 0);
  if (dias === 0) return "detectado hoy";
  if (dias === 1) return "atascado hace 1 dia";
  return `atascado hace ${dias} dias`;
}

/**
 * Lo mas viejo primero: es lo que lleva mas tiempo perdido. Empate desempatado
 * por ruta para que el orden no baile entre refrescos. Devuelve una copia.
 */
export function sortByAgeDesc(items: QuarantineItem[]): QuarantineItem[] {
  return [...items].sort((a, b) => {
    if (b.age_days !== a.age_days) return b.age_days - a.age_days;
    return a.path.localeCompare(b.path);
  });
}
