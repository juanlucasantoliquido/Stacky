// Plan 173 F2 — Preferencias de tabla: qué columnas se ven, cómo se ordena y
// qué ancho tiene cada una. PURO.

export interface ColumnDef {
  id: string;
  label: string;
  /** Clave que entiende el servidor. Sin ella la columna NO es ordenable. */
  sortKey?: string;
}

export interface TableSort {
  column: string;
  dir: "asc" | "desc";
}

export interface TablePrefs {
  /** null = todas visibles. Distinto de []: "no configuré nada" no es "oculté todo". */
  visibleColumns: string[] | null;
  sort: TableSort | null;
  widths: Record<string, number>;
}

export const EMPTY_TABLE_PREFS: TablePrefs = { visibleColumns: null, sort: null, widths: {} };
export const MIN_COL_WIDTH = 40;
export const MAX_COL_WIDTH = 800;

export const HISTORY_COLUMNS: ColumnDef[] = [
  { id: "inicio", label: "Inicio", sortKey: "started_at" },
  { id: "agente", label: "Agente", sortKey: "agent_type" },
  { id: "runtime", label: "Runtime" },
  { id: "modelo", label: "Modelo" },
  { id: "estado", label: "Estado", sortKey: "status" },
  // Plan 269 F4 — segunda dimension: el veredicto por evidencia. SIN `sortKey`:
  // el veredicto se calcula al leer y el backend no puede ordenar por el (mismo
  // criterio que `duracion` y `costo`, justo abajo).
  { id: "veredicto", label: "Veredicto" },
  // Duración y costo NO son ordenables: la primera se calcula por fila y el
  // segundo vive dentro de metadata_json. Ofrecer el sort sería prometer un
  // orden que el backend no puede dar.
  { id: "duracion", label: "Duración" },
  { id: "costo", label: "Costo" },
  { id: "prompt", label: "Prompt" },
  { id: "archivos", label: "Archivos" },
  { id: "ticket", label: "Ticket" },
];

export const SYSLOG_COLUMNS: ColumnDef[] = [
  { id: "level", label: "Nivel" },
  { id: "timestamp", label: "Fecha" },
  { id: "source", label: "Origen" },
  { id: "action", label: "Acción" },
  { id: "exec_id", label: "Ejecución" },
  { id: "ticket", label: "Ticket" },
  { id: "user", label: "Usuario" },
  { id: "method", label: "Método" },
  { id: "endpoint", label: "Endpoint" },
  { id: "status", label: "Estado" },
  { id: "duration", label: "Duración" },
];

export function isColVisible(prefs: TablePrefs, colId: string): boolean {
  const vc = prefs?.visibleColumns;
  return vc == null ? true : vc.includes(colId);
}

export function toggleColumn(prefs: TablePrefs, colId: string, all: ColumnDef[]): TablePrefs {
  const todos = (all ?? []).map((c) => c.id);
  const actuales = prefs?.visibleColumns ?? todos;
  const proximas = actuales.includes(colId)
    ? actuales.filter((c) => c !== colId)
    : todos.filter((c) => actuales.includes(c) || c === colId);

  // Una tabla sin columnas no es una tabla: la última no se puede apagar.
  if (proximas.length === 0) return prefs;
  return { ...prefs, visibleColumns: proximas };
}

/** null → asc → desc → null. Una columna sin `sortKey` no cambia nada. */
export function cycleSort(prefs: TablePrefs, colId: string, all: ColumnDef[]): TablePrefs {
  const def = (all ?? []).find((c) => c.id === colId);
  if (!def?.sortKey) return prefs;

  const actual = prefs?.sort;
  if (!actual || actual.column !== colId) return { ...prefs, sort: { column: colId, dir: "asc" } };
  if (actual.dir === "asc") return { ...prefs, sort: { column: colId, dir: "desc" } };
  return { ...prefs, sort: null };
}

export function setColumnWidth(prefs: TablePrefs, colId: string, px: number): TablePrefs {
  const valor = Math.round(Number(px) || 0);
  const clamped = Math.max(MIN_COL_WIDTH, Math.min(MAX_COL_WIDTH, valor));
  return { ...prefs, widths: { ...(prefs?.widths ?? {}), [colId]: clamped } };
}

/** Tolerante al drift: si mañana se renombra una columna, la preferencia vieja
 *  se descarta en vez de dejar la tabla sin esa columna para siempre. */
export function sanitizeTablePrefs(raw: unknown, all: ColumnDef[]): TablePrefs {
  const doc = (raw ?? {}) as Partial<TablePrefs>;
  const conocidas = new Set((all ?? []).map((c) => c.id));

  let visibleColumns: string[] | null = null;
  if (Array.isArray(doc.visibleColumns)) {
    const filtradas = doc.visibleColumns.filter((c) => typeof c === "string" && conocidas.has(c));
    // Si no quedó ninguna válida se vuelve a "todas": una tabla vacía sería
    // peor que ignorar la preferencia.
    visibleColumns = filtradas.length ? filtradas : null;
  }

  let sort: TableSort | null = null;
  const s = doc.sort;
  if (s && typeof s === "object" && typeof s.column === "string") {
    const def = (all ?? []).find((c) => c.id === s.column);
    if (def?.sortKey && (s.dir === "asc" || s.dir === "desc")) {
      sort = { column: s.column, dir: s.dir };
    }
  }

  const widths: Record<string, number> = {};
  for (const [k, v] of Object.entries(doc.widths ?? {})) {
    if (!conocidas.has(k) || typeof v !== "number" || !Number.isFinite(v)) continue;
    widths[k] = Math.max(MIN_COL_WIDTH, Math.min(MAX_COL_WIDTH, Math.round(v)));
  }

  return { visibleColumns, sort, widths };
}

/** Lo que va al query string. `{}` si no hay orden: mandar un sort vacío haría
 *  que el backend crea que se le pidió un orden. */
export function sortToQuery(
  prefs: TablePrefs,
  all: ColumnDef[],
): { sort?: string; dir?: "asc" | "desc" } {
  const s = prefs?.sort;
  if (!s) return {};
  const def = (all ?? []).find((c) => c.id === s.column);
  if (!def?.sortKey) return {};
  return { sort: def.sortKey, dir: s.dir };
}

// ── Paginación del historial ─────────────────────────────────────────────────

export interface PaginationView {
  label: string;
  canNext: boolean;
}

/**
 * Plan 173 — La ÚNICA fuente de verdad de la paginación del historial.
 *
 * El detalle que importa: con un filtro de runtime activo, el `total` que manda
 * el backend es el COUNT SQL PRE-filtro (el runtime se filtra después, en
 * Python, sobre la página ya traída). Compararlo contra `count` habilitaría
 * "Siguiente" cuando ya no hay nada más. Con runtime activo se ignora el total y
 * se cae a la regla vieja.
 */
export function historyPaginationView(args: {
  offset: number;
  count: number;
  limit: number;
  total: number | null;
  runtimeActive: boolean;
}): PaginationView {
  const { offset, count, limit, total, runtimeActive } = args;
  const usarTotal = total != null && !runtimeActive;
  const desde = offset + 1;
  const hasta = offset + count;
  return {
    label: usarTotal ? `${desde}–${hasta} de ${total}` : `${desde}–${hasta}`,
    canNext: usarTotal ? offset + count < (total as number) : count >= limit,
  };
}
