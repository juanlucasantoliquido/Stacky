// Plan 173 F2 — Vistas guardadas (presets de filtros por pantalla). PURO.
//
// El operador repite los mismos 4 filtros veinte veces al día. Guardarlos con
// nombre es la diferencia entre una pantalla que se usa y una que se configura.

export interface SavedView {
  name: string;
  filters: Record<string, string>;
}

export interface SavedViewsState {
  views: SavedView[];
  lastApplied: string | null;
}

export const EMPTY_SAVED_VIEWS: SavedViewsState = { views: [], lastApplied: null };
export const MAX_VIEWS_PER_SCREEN = 20;
export const MAX_VIEW_NAME_LEN = 60;

/** Solo lo que tiene valor, y ordenado: dos filtros iguales escritos en distinto
 *  orden tienen que dar el MISMO preset, si no `computeActiveView` no matchearía. */
export function normalizeFilters(filters: Record<string, string>): Record<string, string> {
  const salida: Record<string, string> = {};
  for (const k of Object.keys(filters ?? {}).sort()) {
    const v = filters[k];
    if (v !== undefined && v !== null && String(v) !== "") salida[k] = String(v);
  }
  return salida;
}

/** Mensaje de error para mostrar inline, o null si el nombre sirve. */
export function validateViewName(
  name: string,
  state: SavedViewsState,
  excludeName?: string,
): string | null {
  const limpio = String(name ?? "").trim();
  if (!limpio) return "El nombre no puede estar vacío";
  if (limpio.length > MAX_VIEW_NAME_LEN) return `Máximo ${MAX_VIEW_NAME_LEN} caracteres`;

  const existentes = state?.views ?? [];
  const choca = existentes.some(
    (v) =>
      v.name.toLowerCase() === limpio.toLowerCase() &&
      v.name.toLowerCase() !== String(excludeName ?? "").trim().toLowerCase(),
  );
  if (choca) return "Ya existe una vista con ese nombre";

  // Reemplazar una vista propia no cuenta contra el tope: si no, el operador
  // no podría actualizar su preset una vez llegado al límite.
  const reemplaza = existentes.some((v) => v.name.toLowerCase() === limpio.toLowerCase());
  if (!reemplaza && existentes.length >= MAX_VIEWS_PER_SCREEN) {
    return `Máximo ${MAX_VIEWS_PER_SCREEN} vistas por pantalla`;
  }
  return null;
}

export function upsertView(
  state: SavedViewsState,
  name: string,
  filters: Record<string, string>,
): SavedViewsState {
  const limpio = String(name ?? "").trim();
  const nueva: SavedView = { name: limpio, filters: normalizeFilters(filters) };
  const existentes = state?.views ?? [];
  const i = existentes.findIndex((v) => v.name.toLowerCase() === limpio.toLowerCase());
  const views =
    i >= 0
      ? existentes.map((v, j) => (j === i ? nueva : v))
      : [...existentes, nueva].slice(0, MAX_VIEWS_PER_SCREEN);
  return { views, lastApplied: state?.lastApplied ?? null };
}

export function renameView(
  state: SavedViewsState,
  oldName: string,
  newName: string,
): SavedViewsState {
  const limpio = String(newName ?? "").trim();
  const views = (state?.views ?? []).map((v) => (v.name === oldName ? { ...v, name: limpio } : v));
  // Si el preset activo era el renombrado, sigue activo con su nombre nuevo:
  // dejarlo apuntando al viejo lo mostraría como "ninguno".
  const lastApplied = state?.lastApplied === oldName ? limpio : (state?.lastApplied ?? null);
  return { views, lastApplied };
}

export function deleteView(state: SavedViewsState, name: string): SavedViewsState {
  const views = (state?.views ?? []).filter((v) => v.name !== name);
  const lastApplied = state?.lastApplied === name ? null : (state?.lastApplied ?? null);
  return { views, lastApplied };
}

export function applyView(
  state: SavedViewsState,
  name: string,
): { state: SavedViewsState; filters: Record<string, string> } | null {
  const vista = (state?.views ?? []).find((v) => v.name === name);
  if (!vista) return null;
  return {
    state: { views: state.views, lastApplied: vista.name },
    filters: normalizeFilters(vista.filters),
  };
}

/** Qué preset describe EXACTAMENTE los filtros actuales, o null.
 *  Se compara sobre los normalizados: si no, tocar un filtro y volver atrás
 *  dejaría el preset marcado como inactivo sin motivo. */
export function computeActiveView(
  state: SavedViewsState,
  currentFilters: Record<string, string>,
): string | null {
  const actual = JSON.stringify(normalizeFilters(currentFilters));
  const match = (state?.views ?? []).find(
    (v) => JSON.stringify(normalizeFilters(v.filters)) === actual,
  );
  return match ? match.name : null;
}

/** Cualquier `unknown` (backend, localStorage viejo, null) a un estado válido.
 *  Una entrada rota descarta ESA entrada, no el archivo entero: perder las 19
 *  vistas buenas por una mala sería el peor resultado posible. */
export function sanitizeSavedViews(raw: unknown): SavedViewsState {
  const doc = (raw ?? {}) as { views?: unknown; lastApplied?: unknown };
  const crudas = Array.isArray(doc.views) ? doc.views : [];
  const views: SavedView[] = [];

  for (const item of crudas) {
    if (!item || typeof item !== "object") continue;
    const { name, filters } = item as { name?: unknown; filters?: unknown };
    if (typeof name !== "string" || !name.trim()) continue;
    if (!filters || typeof filters !== "object" || Array.isArray(filters)) continue;

    const limpios: Record<string, string> = {};
    for (const [k, v] of Object.entries(filters as Record<string, unknown>)) {
      if (typeof v === "string") limpios[k] = v;
    }
    views.push({ name: name.trim(), filters: normalizeFilters(limpios) });
    if (views.length >= MAX_VIEWS_PER_SCREEN) break;
  }

  const la = doc.lastApplied;
  const lastApplied =
    typeof la === "string" && views.some((v) => v.name === la) ? la : null;
  return { views, lastApplied };
}

// ── Tablero de tickets: su estado no son filtros de texto ────────────────────

export interface TicketBoardViewState {
  search: string;
  onlyPending: boolean;
  showAll: boolean;
  viewMode: string;
}

/**
 * Los booleanos se codifican "1"/"0", NO "1"/"".
 *
 * Con "" el normalizador los descarta y quedan ausentes — y `showAll` ausente
 * significa `true` por default. O sea: guardar un preset con showAll en false lo
 * releería como true, cambiando en silencio lo que el operador guardó. Un "0"
 * explícito distingue "lo apagué" de "no lo guardé".
 */
export function ticketBoardStateToFilters(s: TicketBoardViewState): Record<string, string> {
  return normalizeFilters({
    search: s?.search ?? "",
    onlyPending: s?.onlyPending ? "1" : "0",
    showAll: s?.showAll ? "1" : "0",
    viewMode: s?.viewMode ?? "",
  });
}

export function filtersToTicketBoardState(f: Record<string, string>): TicketBoardViewState {
  const filtros = f ?? {};
  return {
    search: filtros.search ?? "",
    onlyPending: filtros.onlyPending === "1",
    // Los defaults son los REALES del tablero: inventar otros haría que aplicar
    // un preset viejo cambie cosas que el operador nunca guardó.
    showAll: "showAll" in filtros ? filtros.showAll === "1" : true,
    // (ver ticketBoardStateToFilters: por eso el false viaja como "0")
    viewMode: filtros.viewMode || "graph",
  };
}
