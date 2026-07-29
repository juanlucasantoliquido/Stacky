/**
 * graphFilters.ts — Plan 268 F1.
 * Filtrado PURO de un DocGraphResponse. Devuelve OTRO DocGraphResponse (misma
 * forma) con el subconjunto de nodos/aristas que pasa el filtro. No muta la entrada.
 */
import type { DocGraphResponse, DocGraphNode, DocGraphEdge } from "./docGraphModel";
import type { GraphFilterState, NodeKind, EdgeKind } from "./graphExplorerState";

export interface FilterOption {
  value: string;
  label: string;
  count: number;
}

export interface FilterOptions {
  sources: FilterOption[]; // ordenadas por label asc
  kinds: FilterOption[]; // orden fijo: note, code, missing
  edgeKinds: FilterOption[]; // orden fijo: md, wikilink, code_ref
  staleCount: number;
  orphanCount: number;
  maxDegree: number;
}

/** Grafo vacío pero estructuralmente válido (nunca null: el canvas no debe ramificar). */
export const EMPTY_GRAPH: DocGraphResponse = {
  ok: true,
  generated_at: "",
  active_project: null,
  sources: [],
  nodes: [],
  edges: [],
  orphans: [],
  stats: {},
  doc_health: null,
};

const NODE_KINDS: ReadonlyArray<{ value: NodeKind; label: string }> = [
  { value: "note", label: "Notas" },
  { value: "code", label: "Código" },
  { value: "missing", label: "Faltantes" },
];

const EDGE_KINDS: ReadonlyArray<{ value: EdgeKind; label: string }> = [
  { value: "md", label: "Links markdown" },
  { value: "wikilink", label: "Wikilinks" },
  { value: "code_ref", label: "Referencias a código" },
];

/** true si los filtros no descartan nada (permite devolver el mismo objeto, R2). */
function isPassAll(filters: GraphFilterState): boolean {
  return (
    filters.sourceIds.length === 0 &&
    filters.kinds.length === 0 &&
    filters.edgeKinds.length === 0 &&
    !filters.hideOrphans &&
    !filters.onlyStale &&
    (filters.minDegree ?? 0) <= 0
  );
}

/**
 * Opciones disponibles derivadas del grafo COMPLETO (no del filtrado): la barra
 * no debe cambiar de forma cuando el operador filtra.
 *
 * (C11) Reglas EXACTAS, no interpretables:
 *  - `sources`: una entrada por cada `source_id` NO VACÍO que aparezca en al menos
 *    un nodo. `count` = cuántos nodos lo tienen. El `label` sale de `graph.sources`
 *    buscando por `id`; si ese id NO está en graph.sources, el label ES el propio id.
 *    Orden: por `label` asc con `localeCompare`, y a igual label por `value` asc. Las
 *    fuentes declaradas en graph.sources con 0 nodos NO se listan.
 *  - `kinds` / `edgeKinds`: SIEMPRE las 3 entradas en orden fijo, aun con count 0.
 *  - `staleCount`: nodos con has_stale === true. `orphanCount`: graph.orphans.length.
 *  - `maxDegree`: max(in_degree + out_degree); 0 si no hay nodos.
 */
export function availableFilterOptions(graph: DocGraphResponse | undefined): FilterOptions {
  const nodes = graph?.nodes ?? [];
  const labelById = new Map<string, string>();
  for (const s of graph?.sources ?? []) labelById.set(s.id, s.label || s.id);

  const bySource = new Map<string, number>();
  const byKind = new Map<string, number>();
  let staleCount = 0;
  let maxDegree = 0;
  for (const n of nodes) {
    if (n.source_id) bySource.set(n.source_id, (bySource.get(n.source_id) ?? 0) + 1);
    byKind.set(n.kind, (byKind.get(n.kind) ?? 0) + 1);
    if (n.has_stale === true) staleCount++;
    const deg = (n.in_degree || 0) + (n.out_degree || 0);
    if (deg > maxDegree) maxDegree = deg;
  }

  const byEdgeKind = new Map<string, number>();
  for (const e of graph?.edges ?? []) {
    byEdgeKind.set(e.kind, (byEdgeKind.get(e.kind) ?? 0) + 1);
  }

  const sources: FilterOption[] = Array.from(bySource.entries())
    .map(([value, count]) => ({ value, label: labelById.get(value) ?? value, count }))
    .sort(
      (a, b) =>
        a.label.localeCompare(b.label) ||
        (a.value < b.value ? -1 : a.value > b.value ? 1 : 0)
    );

  return {
    sources,
    kinds: NODE_KINDS.map((k) => ({
      value: k.value,
      label: k.label,
      count: byKind.get(k.value) ?? 0,
    })),
    edgeKinds: EDGE_KINDS.map((k) => ({
      value: k.value,
      label: k.label,
      count: byEdgeKind.get(k.value) ?? 0,
    })),
    staleCount,
    orphanCount: (graph?.orphans ?? []).length,
    maxDegree,
  };
}

/**
 * Aplica los filtros. Reglas, en este orden:
 *  1. nodos: kind ∈ filters.kinds (si kinds no está vacío)
 *  2. nodos: source_id ∈ filters.sourceIds (si sourceIds no está vacío). Los nodos
 *     con source_id vacío PASAN siempre (los `code`/`missing` no tienen fuente).
 *  3. nodos: si hideOrphans, descartar los que están en graph.orphans
 *  4. nodos: si onlyStale, dejar solo has_stale === true
 *  5. nodos: (in_degree + out_degree) >= minDegree
 *  6. aristas: kind ∈ filters.edgeKinds (si edgeKinds no está vacío)
 *  7. aristas: source Y target deben haber sobrevivido al filtro de nodos
 * Devuelve un DocGraphResponse nuevo con nodes/edges filtrados, `orphans` recortado
 * a los nodos vivos, y `sources`/`stats`/`doc_health` copiados tal cual.
 * Entrada undefined → EMPTY_GRAPH. Filtros que no descartan nada → el MISMO objeto (R2).
 */
export function applyGraphFilters(
  graph: DocGraphResponse | undefined,
  filters: GraphFilterState
): DocGraphResponse {
  if (!graph) return EMPTY_GRAPH;
  if (isPassAll(filters)) return graph;

  const kindSet = new Set<string>(filters.kinds);
  const srcSet = new Set<string>(filters.sourceIds);
  const edgeSet = new Set<string>(filters.edgeKinds);
  const orphanSet = new Set(graph.orphans ?? []);
  const minDegree = Math.max(0, filters.minDegree || 0);

  const keptNodes: DocGraphNode[] = [];
  for (const n of graph.nodes ?? []) {
    if (kindSet.size && !kindSet.has(n.kind)) continue;
    if (srcSet.size && n.source_id && !srcSet.has(n.source_id)) continue;
    if (filters.hideOrphans && orphanSet.has(n.id)) continue;
    if (filters.onlyStale && n.has_stale !== true) continue;
    if ((n.in_degree || 0) + (n.out_degree || 0) < minDegree) continue;
    keptNodes.push(n);
  }

  const alive = new Set(keptNodes.map((n) => n.id));
  const keptEdges: DocGraphEdge[] = (graph.edges ?? []).filter(
    (e) =>
      (!edgeSet.size || edgeSet.has(e.kind)) && alive.has(e.source) && alive.has(e.target)
  );

  return {
    ...graph,
    nodes: keptNodes,
    edges: keptEdges,
    orphans: (graph.orphans ?? []).filter((id) => alive.has(id)),
  };
}
