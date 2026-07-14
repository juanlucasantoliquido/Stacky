/**
 * dataDiffLogic.ts — Plan 126 F5.
 *
 * Lógica PURA (sin React) de la paridad de DATOS del Comparador de BD: arma
 * las filas del grid a partir del DataDiff v1 (services/dbcompare_data.py
 * F2), calcula los contadores de insert/update/delete, y filtra candidatas
 * por texto para el picker. No hace fetch ni toca el DOM.
 *
 * NOTA (mismo patrón que scriptsLogic.ts, Plan 125 F6 / NOTA C1 doc 125 v2):
 * esta pieza NO depende de un host de React (el drill-down del objeto de
 * Plan 124 no está mergeado en este checkout) — por eso se implementa y
 * testea completa, aislada de DataTablePicker.tsx/DataDiffGrid.tsx (que sí
 * montarían dentro de esa página, pendientes de ese plan).
 */

export interface DataDiff {
  version: number;
  schema: string;
  table: string;
  pk_cols: string[];
  columns: string[];
  column_types: Record<string, string>;
  columns_skipped: string[];
  only_source: Record<string, string | null>[];
  only_target: Record<string, string | null>[];
  changed: {
    pk: Record<string, string | null>;
    cells: Record<string, { source: string | null; target: string | null }>;
  }[];
  row_counts: { source: number; target: number };
  truncated: boolean;
  identical: boolean;
}

export interface DataCandidate {
  schema: string;
  table: string;
  has_pk: boolean;
  estimated_columns: number;
  comparable: boolean;
  reason: string;
  row_count_source: number | null;
  row_count_target: number | null;
}

export type DataGridRowKind = 'only_source' | 'only_target' | 'changed';

export interface DataGridCell {
  col: string;
  source: string | null;
  target: string | null;
  changed: boolean;
}

export interface DataGridRow {
  pk: string;
  kind: DataGridRowKind;
  cells: DataGridCell[];
}

function formatPk(pk: Record<string, string | null>, pkCols: string[]): string {
  return pkCols.map((col) => `${col}=${pk[col] ?? 'NULL'}`).join(' · ');
}

/** Orden: changed, only_source, only_target — igual que el DoD del plan 126. */
export function buildDataGridRows(d: DataDiff): DataGridRow[] {
  const rows: DataGridRow[] = [];

  for (const row of d.changed) {
    rows.push({
      pk: formatPk(row.pk, d.pk_cols),
      kind: 'changed',
      cells: Object.entries(row.cells).map(([col, cell]) => ({
        col,
        source: cell.source,
        target: cell.target,
        changed: true,
      })),
    });
  }

  for (const row of d.only_source) {
    rows.push({
      pk: formatPk(row, d.pk_cols),
      kind: 'only_source',
      cells: d.columns.map((col) => ({ col, source: row[col] ?? null, target: null, changed: false })),
    });
  }

  for (const row of d.only_target) {
    rows.push({
      pk: formatPk(row, d.pk_cols),
      kind: 'only_target',
      cells: d.columns.map((col) => ({ col, source: null, target: row[col] ?? null, changed: false })),
    });
  }

  return rows;
}

/** inserts = only_source (faltan en destino), updates = changed, deletes = only_target (sobran en destino). */
export function dataCounters(d: DataDiff): { inserts: number; updates: number; deletes: number } {
  return {
    inserts: d.only_source.length,
    updates: d.changed.length,
    deletes: d.only_target.length,
  };
}

/** Filtro case-insensitive por nombre de tabla o de schema. */
export function candidateFilter(cands: DataCandidate[], text: string): DataCandidate[] {
  const needle = text.trim().toLowerCase();
  if (!needle) return cands;
  return cands.filter(
    (c) => c.table.toLowerCase().includes(needle) || c.schema.toLowerCase().includes(needle),
  );
}
