// Plan 124 [integración F4] — arma el mapa "schema.tabla" -> #columnas que necesita
// `tableTreemapInputs` (treemapLayout.ts) para los pesos del treemap. Peso = #columnas del
// snapshot ORIGEN si la tabla existe ahí; si no, fallback al snapshot DESTINO (doc §F4:
// "del snapshot origen si existe ahí, si no del destino").
import type { DbSnapshot } from "./dbcompareTypes";

export function buildSnapshotCounts(
  source: DbSnapshot | null,
  target: DbSnapshot | null
): Record<string, number> {
  const counts: Record<string, number> = {};

  if (source) {
    for (const [schema, schemaSnap] of Object.entries(source.schemas)) {
      for (const [tableName, table] of Object.entries(schemaSnap.tables)) {
        counts[`${schema}.${tableName}`] = table.columns.length;
      }
    }
  }
  if (target) {
    for (const [schema, schemaSnap] of Object.entries(target.schemas)) {
      for (const [tableName, table] of Object.entries(schemaSnap.tables)) {
        const key = `${schema}.${tableName}`;
        if (!(key in counts)) counts[key] = table.columns.length;
      }
    }
  }
  return counts;
}
