// Plan 181 F5 — lógica pura de la barra de masking del data-diff. Puro TS,
// testeado con vitest (sin RTL/jsdom, gap estructural del repo). Lee el campo
// aditivo `masked_columns` que el backend (F3) agrega a cada tabla del data-diff
// con la flag ON; los tipos de dbcompareTypes.ts NO se editan (el campo se lee
// con un cast local — TS estructural ignora campos extra).

export interface MaskingPrefs {
  version: number;
  overrides: Record<string, { state: "visible" | "masked"; updated_at?: string }>;
}

export interface MaskedTableInfo {
  key: string;
  schema: string;
  table: string;
  maskedColumns: string[];
}

/** Split de la clave "schema.tabla" del data_diff (backend
 * dbcompare_data.py: `f"{schema}.{table}"`), por el PRIMER punto. */
export function parseTableKey(key: string): { schema: string; table: string } {
  const dot = key.indexOf(".");
  if (dot < 0) return { schema: "", table: key };
  return { schema: key.slice(0, dot), table: key.slice(dot + 1) };
}

/**
 * Recorre `dataDiff.tables` y junta las tablas con `masked_columns` no vacías,
 * en orden estable por key. Robusto a entradas de error ({error:...}) y a la
 * ausencia del campo (flag OFF ⇒ el backend no lo manda ⇒ [] ⇒ se ignora).
 */
export function collectMaskedTables(tables: Record<string, unknown>): MaskedTableInfo[] {
  const out: MaskedTableInfo[] = [];
  for (const key of Object.keys(tables).sort()) {
    const result = tables[key];
    if (!result || typeof result !== "object") continue;
    const masked = (result as { masked_columns?: unknown }).masked_columns;
    if (!Array.isArray(masked) || masked.length === 0) continue;
    const maskedColumns = masked.filter((c): c is string => typeof c === "string");
    if (maskedColumns.length === 0) continue;
    const { schema, table } = parseTableKey(key);
    out.push({ key, schema, table, maskedColumns });
  }
  return out;
}

export function toggleLabel(state: "masked" | "visible"): string {
  return state === "masked" ? "Revelar" : "Ocultar";
}
