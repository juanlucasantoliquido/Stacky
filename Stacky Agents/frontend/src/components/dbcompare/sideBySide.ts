// Plan 124 — Comparador de BD: lógica pura del drill-down side-by-side (doc §F5).
import type { ColumnInfo, DiffItem, TableSnapshot } from "./dbcompareTypes";

export interface ColumnRow {
  name: string;
  source: ColumnInfo | null;
  target: ColumnInfo | null;
  state: "added" | "removed" | "changed" | "unchanged";
  changedFields: string[];
}

const COMPARABLE_FIELDS: (keyof ColumnInfo)[] = ["type", "nullable", "default", "autoincrement"];

function makeRow(
  name: string,
  source: ColumnInfo | null,
  target: ColumnInfo | null,
  sourceTable: TableSnapshot | null,
  targetTable: TableSnapshot | null
): ColumnRow {
  // Tabla entera added (no hay target) o removed (no hay source): todas las columnas heredan
  // el mismo estado de la tabla.
  if (!sourceTable || !targetTable) {
    const state: ColumnRow["state"] = !targetTable ? "added" : "removed";
    return { name, source, target, state, changedFields: [] };
  }
  if (source && !target) return { name, source, target: null, state: "added", changedFields: [] };
  if (!source && target) return { name, source: null, target, state: "removed", changedFields: [] };
  const changedFields: string[] = [];
  for (const field of COMPARABLE_FIELDS) {
    if (source![field] !== target![field]) changedFields.push(field);
  }
  const state: ColumnRow["state"] = changedFields.length > 0 ? "changed" : "unchanged";
  return { name, source, target, state, changedFields };
}

/**
 * Une columnas de ambos lados por `name`: primero las del origen en su orden, después las
 * solo-destino en su orden. `_item` se recibe por contrato del plan (doc §F5) aunque el
 * cálculo de esta función depende solo de los snapshots de tabla.
 */
export function buildColumnRows(
  _item: DiffItem,
  sourceTable: TableSnapshot | null,
  targetTable: TableSnapshot | null
): ColumnRow[] {
  const sourceColumns = sourceTable?.columns ?? [];
  const targetColumns = targetTable?.columns ?? [];
  const targetByName = new Map(targetColumns.map((c) => [c.name, c] as const));
  const seen = new Set<string>();
  const rows: ColumnRow[] = [];

  for (const sCol of sourceColumns) {
    seen.add(sCol.name);
    const tCol = targetByName.get(sCol.name) ?? null;
    rows.push(makeRow(sCol.name, sCol, tCol, sourceTable, targetTable));
  }
  for (const tCol of targetColumns) {
    if (seen.has(tCol.name)) continue;
    rows.push(makeRow(tCol.name, null, tCol, sourceTable, targetTable));
  }
  return rows;
}

export interface SectionRow<T> {
  key: string;
  source: T | null;
  target: T | null;
  state: string;
}

/** Genérico para indexes / foreign_keys / unique_constraints / check_constraints: matchea por
 * la clave que da `keyOf` (firma estructural, no nombre — doctrina 123 §F1). Orden: primero
 * las del origen en su orden, después las solo-destino en su orden. */
export function buildSectionRows<T>(sourceList: T[], targetList: T[], keyOf: (t: T) => string): SectionRow<T>[] {
  const targetByKey = new Map(targetList.map((t) => [keyOf(t), t] as const));
  const seen = new Set<string>();
  const rows: SectionRow<T>[] = [];

  for (const s of sourceList) {
    const key = keyOf(s);
    seen.add(key);
    const t = targetByKey.get(key) ?? null;
    rows.push({ key, source: s, target: t, state: t ? "unchanged" : "added" });
  }
  for (const t of targetList) {
    const key = keyOf(t);
    if (seen.has(key)) continue;
    rows.push({ key, source: null, target: t, state: "removed" });
  }
  return rows;
}
