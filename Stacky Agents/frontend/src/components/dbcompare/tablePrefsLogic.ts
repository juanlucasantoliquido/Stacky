// Plan 176 F6 — Preferencias de tabla: parámetro persistente y clave natural.
//
// El operador re-selecciona las mismas ≤20 tablas en cada corrida. Marcarlas una
// vez como "de parámetro" y que arranquen tildadas es la diferencia entre usar
// el diff de datos y no usarlo.

export interface PrefsCandidate {
  schema: string;
  table: string;
  comparable: boolean;
  param_table?: boolean;
  key_source?: "pk" | "natural";
  key_cols?: string[];
  reason?: string;
}

/** Nombre de columna aceptable. El quoting al emitir SQL sigue siendo de
 *  `quote_ident`; acá solo se filtra lo que ni siquiera es un nombre. */
const COLUMNA_VALIDA = /^[A-Za-z0-9_$#]{1,128}$/;

export function candidateKey(c: { schema: string; table: string }): string {
  return `${c.schema}.${c.table}`;
}

/**
 * Qué arranca tildado. Solo tablas de parámetro Y comparables: preseleccionar
 * una tabla que el backend va a rechazar produce un error que el operador no
 * pidió.
 *
 * El orden es alfabético y el cap es el del backend: si hay 25 marcadas, se
 * tildan 20 determinísticas, no "las primeras que llegaron".
 */
export function preselect(candidates: PrefsCandidate[], cap: number): string[] {
  return (candidates ?? [])
    .filter((c) => c.param_table && c.comparable)
    .map(candidateKey)
    .sort()
    .slice(0, Math.max(0, cap));
}

/**
 * "MODULO, CODIGO ,, " ⇒ ["MODULO","CODIGO"]. Devuelve null si no queda ninguna
 * columna usable: guardar una clave vacía la borraría sin decirlo.
 */
export function parseNaturalKeyInput(raw: string): string[] | null {
  const cols = String(raw ?? "")
    .split(",")
    .map((c) => c.trim())
    .filter((c) => c.length > 0);

  if (!cols.length) return null;
  // Un nombre inválido se rechaza acá y no en el 400 del backend: el operador
  // ve el problema mientras escribe.
  if (!cols.every((c) => COLUMNA_VALIDA.test(c))) return null;
  return cols;
}

/** Solo tiene sentido definir una clave donde no hay ninguna todavía. */
export function canDefineKey(candidate: PrefsCandidate): boolean {
  if (!candidate) return false;
  if (candidate.key_source === "pk") return false;
  return !candidate.comparable || candidate.reason === "natural_key_invalid";
}
