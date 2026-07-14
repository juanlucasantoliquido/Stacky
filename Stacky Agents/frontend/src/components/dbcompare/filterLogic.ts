// Plan 124 — Comparador de BD: filtros de la lista/treemap de diferencias (doc §F5, KPI-2).
import type { DiffItem, DiffAction, Severity, ObjectType } from "./dbcompareTypes";

export interface DiffFilters {
  severities: Severity[];
  objectTypes: ObjectType[];
  text: string;
}

export const EMPTY_FILTERS: DiffFilters = { severities: [], objectTypes: [], text: "" };

/** severities/objectTypes vacíos no filtran; text hace includes case-insensitive sobre
 * `${schema}.${name}` y sobre los kinds de los changes del item. */
export function filterDiffItems(items: DiffItem[], f: DiffFilters): DiffItem[] {
  const text = f.text.trim().toLowerCase();
  return items.filter((item) => {
    if (f.severities.length > 0 && !f.severities.includes(item.severity)) return false;
    if (f.objectTypes.length > 0 && !f.objectTypes.includes(item.object_type)) return false;
    if (text) {
      const fullName = `${item.schema}.${item.name}`.toLowerCase();
      const kinds = item.changes.map((c) => c.kind).join(" ").toLowerCase();
      if (!fullName.includes(text) && !kinds.includes(text)) return false;
    }
    return true;
  });
}

export function countByState(items: DiffItem[]): Record<DiffAction, number> {
  const out: Record<DiffAction, number> = { added: 0, removed: 0, changed: 0 };
  for (const item of items) out[item.action] += 1;
  return out;
}
