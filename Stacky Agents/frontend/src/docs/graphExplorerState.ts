/**
 * graphExplorerState.ts — Plan 268 F0.5.
 * Estado PURO del explorador del grafo documental: filtros, búsqueda, foco,
 * grupos colapsados y peek. Sin React, sin DOM, sin fetch. Un reducer total:
 * toda acción desconocida devuelve el mismo objeto (identidad referencial).
 */
export type NodeKind = "note" | "code" | "missing";
export type EdgeKind = "md" | "wikilink" | "code_ref";

export interface GraphFilterState {
  /** [] = todas las fuentes pasan. */
  sourceIds: string[];
  /** [] = todos los tipos de nodo pasan. */
  kinds: NodeKind[];
  /** [] = todos los tipos de arista pasan. */
  edgeKinds: EdgeKind[];
  /** true = descartar nodos cuyo id está en graph.orphans. */
  hideOrphans: boolean;
  /** true = dejar solo nodos con has_stale === true. */
  onlyStale: boolean;
  /** descartar nodos con in_degree + out_degree < minDegree. 0 = sin corte. */
  minDegree: number;
}

export interface GraphExplorerState {
  filters: GraphFilterState;
  query: string;
  /** posición 0-based dentro de la lista de coincidencias. */
  matchIndex: number;
  focusRootId: string | null;
  /** 1..3 */
  focusDepth: number;
  /** pila de raíces anteriores; el tope es a donde vuelve FOCUS_BACK. */
  focusHistory: string[];
  /** claves de grupo colapsadas (ver groupKeyOf, F5). */
  collapsedGroups: string[];
  peekNodeId: string | null;
}

export const EMPTY_FILTERS: GraphFilterState = {
  sourceIds: [],
  kinds: [],
  edgeKinds: [],
  hideOrphans: false,
  onlyStale: false,
  minDegree: 0,
};

export const INITIAL_EXPLORER_STATE: GraphExplorerState = {
  filters: EMPTY_FILTERS,
  query: "",
  matchIndex: 0,
  focusRootId: null,
  focusDepth: 1,
  focusHistory: [],
  collapsedGroups: [],
  peekNodeId: null,
};

export const MIN_FOCUS_DEPTH = 1;
export const MAX_FOCUS_DEPTH = 3;

export type GraphExplorerAction =
  | { type: "SET_QUERY"; query: string }
  | { type: "NEXT_MATCH"; total: number }
  | { type: "PREV_MATCH"; total: number }
  | { type: "TOGGLE_SOURCE"; sourceId: string }
  | { type: "TOGGLE_KIND"; kind: NodeKind }
  | { type: "TOGGLE_EDGE_KIND"; edgeKind: EdgeKind }
  | { type: "SET_MIN_DEGREE"; minDegree: number }
  | { type: "TOGGLE_HIDE_ORPHANS" }
  | { type: "TOGGLE_ONLY_STALE" }
  | { type: "RESET_FILTERS" }
  | { type: "FOCUS_NODE"; nodeId: string }
  | { type: "SET_FOCUS_DEPTH"; depth: number }
  | { type: "FOCUS_BACK" }
  | { type: "CLEAR_FOCUS" }
  | { type: "TOGGLE_GROUP_COLLAPSED"; groupKey: string }
  | { type: "SET_PEEK"; nodeId: string | null }
  | { type: "RESET_ALL" };

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value].sort();
}

export function graphExplorerReducer(
  state: GraphExplorerState,
  action: GraphExplorerAction
): GraphExplorerState {
  switch (action.type) {
    case "SET_QUERY":
      // toda query nueva resetea el cursor de coincidencias a la primera
      return { ...state, query: action.query, matchIndex: 0 };
    case "NEXT_MATCH":
      if (action.total <= 0) return { ...state, matchIndex: 0 };
      return { ...state, matchIndex: (state.matchIndex + 1) % action.total };
    case "PREV_MATCH":
      if (action.total <= 0) return { ...state, matchIndex: 0 };
      return { ...state, matchIndex: (state.matchIndex - 1 + action.total) % action.total };
    case "TOGGLE_SOURCE":
      return {
        ...state,
        filters: { ...state.filters, sourceIds: toggle(state.filters.sourceIds, action.sourceId) },
      };
    case "TOGGLE_KIND":
      return { ...state, filters: { ...state.filters, kinds: toggle(state.filters.kinds, action.kind) } };
    case "TOGGLE_EDGE_KIND":
      return {
        ...state,
        filters: { ...state.filters, edgeKinds: toggle(state.filters.edgeKinds, action.edgeKind) },
      };
    case "SET_MIN_DEGREE":
      return {
        ...state,
        filters: { ...state.filters, minDegree: Math.max(0, Math.floor(action.minDegree || 0)) },
      };
    case "TOGGLE_HIDE_ORPHANS":
      return { ...state, filters: { ...state.filters, hideOrphans: !state.filters.hideOrphans } };
    case "TOGGLE_ONLY_STALE":
      return { ...state, filters: { ...state.filters, onlyStale: !state.filters.onlyStale } };
    case "RESET_FILTERS":
      return { ...state, filters: EMPTY_FILTERS };
    case "FOCUS_NODE":
      if (state.focusRootId === action.nodeId) return state;
      return {
        ...state,
        focusRootId: action.nodeId,
        focusHistory: state.focusRootId
          ? [...state.focusHistory, state.focusRootId]
          : state.focusHistory,
        peekNodeId: action.nodeId,
      };
    case "SET_FOCUS_DEPTH": {
      const d = Math.min(MAX_FOCUS_DEPTH, Math.max(MIN_FOCUS_DEPTH, Math.floor(action.depth || 1)));
      return d === state.focusDepth ? state : { ...state, focusDepth: d };
    }
    case "FOCUS_BACK": {
      if (!state.focusHistory.length) return { ...state, focusRootId: null };
      const hist = state.focusHistory.slice(0, -1);
      const prev = state.focusHistory[state.focusHistory.length - 1];
      return { ...state, focusRootId: prev, focusHistory: hist, peekNodeId: prev };
    }
    case "CLEAR_FOCUS":
      return { ...state, focusRootId: null, focusHistory: [] };
    case "TOGGLE_GROUP_COLLAPSED":
      return { ...state, collapsedGroups: toggle(state.collapsedGroups, action.groupKey) };
    case "SET_PEEK":
      return state.peekNodeId === action.nodeId ? state : { ...state, peekNodeId: action.nodeId };
    case "RESET_ALL":
      return INITIAL_EXPLORER_STATE;
    default:
      return state;
  }
}
