/**
 * graphNeighborhood.ts — Plan 268 F4.
 * Vecindario NO DIRIGIDO a profundidad N (BFS) sobre un DocGraphResponse.
 */
import type { DocGraphResponse, DocGraphNode, DocGraphEdge } from "./docGraphModel";
import { GROUP_NODE_PREFIX, groupKeyOf } from "./graphGrouping";

/** id → Set de ids adyacentes (arista en cualquier dirección). Self-loops ignorados. */
export function buildAdjacency(graph: DocGraphResponse | undefined): Map<string, Set<string>> {
  const adj = new Map<string, Set<string>>();
  if (!graph) return adj;
  const ids = new Set((graph.nodes ?? []).map((n) => n.id));
  const add = (a: string, b: string) => {
    let s = adj.get(a);
    if (!s) {
      s = new Set<string>();
      adj.set(a, s);
    }
    s.add(b);
  };
  for (const e of graph.edges ?? []) {
    if (e.source === e.target) continue; // self-loop
    if (!ids.has(e.source) || !ids.has(e.target)) continue;
    add(e.source, e.target);
    add(e.target, e.source);
  }
  return adj;
}

/**
 * BFS desde rootId hasta `depth` saltos, inclusive.
 *  - rootId inexistente en el grafo → Set VACÍO (no {rootId}).
 *  - depth <= 0 → {rootId} si existe.
 *  - depth >= diámetro → toda la componente conexa.
 * Nunca entra en bucle infinito con ciclos (usa `seen`).
 */
export function neighborhoodOf(
  graph: DocGraphResponse | undefined,
  rootId: string | null,
  depth: number
): Set<string> {
  if (!graph || !rootId) return new Set();
  const ids = new Set((graph.nodes ?? []).map((n) => n.id));
  if (!ids.has(rootId)) return new Set();
  const adj = buildAdjacency(graph);
  const seen = new Set([rootId]);
  let frontier = [rootId];
  const maxDepth = Math.max(0, Number.isFinite(depth) ? Math.floor(depth) : 0);
  for (let d = 0; d < maxDepth; d++) {
    const next: string[] = [];
    for (const id of frontier) {
      for (const nb of adj.get(id) ?? []) {
        if (!seen.has(nb)) {
          seen.add(nb);
          next.push(nb);
        }
      }
    }
    if (!next.length) break;
    frontier = next;
  }
  return seen;
}

/** Sub-grafo con SOLO los nodos del vecindario y las aristas entre ellos. */
export function focusSubgraph(
  graph: DocGraphResponse,
  rootId: string | null,
  depth: number
): DocGraphResponse {
  const keep = neighborhoodOf(graph, rootId, depth);
  const nodes = (graph.nodes ?? []).filter((n) => keep.has(n.id));
  const edges = (graph.edges ?? []).filter((e) => keep.has(e.source) && keep.has(e.target));
  return {
    ...graph,
    nodes,
    edges,
    orphans: (graph.orphans ?? []).filter((id) => keep.has(id)),
  };
}

export interface NeighborEntry {
  node: DocGraphNode;
  direction: "in" | "out" | "both";
  edgeKinds: Array<"md" | "wikilink" | "code_ref">;
}

const EDGE_KIND_ORDER: ReadonlyArray<DocGraphEdge["kind"]> = ["md", "wikilink", "code_ref"];

/**
 * Vecinos DIRECTOS del root, para la lista lateral "Relaciones".
 * Orden: primero los que apuntan al root (entrantes, "lo referencian") —incluidos los
 * bidireccionales, que también apuntan—, después los que el root apunta (salientes);
 * dentro de cada bloque por path ascendente. Cada entrada trae dirección y kinds.
 */
export function rankedNeighbors(graph: DocGraphResponse, rootId: string): NeighborEntry[] {
  if (!graph || !rootId) return [];
  const byId = new Map((graph.nodes ?? []).map((n) => [n.id, n]));
  if (!byId.has(rootId)) return [];

  const incoming = new Set<string>();
  const outgoing = new Set<string>();
  const kinds = new Map<string, Set<DocGraphEdge["kind"]>>();
  const noteKind = (other: string, kind: DocGraphEdge["kind"]) => {
    let s = kinds.get(other);
    if (!s) {
      s = new Set<DocGraphEdge["kind"]>();
      kinds.set(other, s);
    }
    s.add(kind);
  };

  for (const e of graph.edges ?? []) {
    if (e.source === e.target) continue;
    if (e.target === rootId && byId.has(e.source)) {
      incoming.add(e.source);
      noteKind(e.source, e.kind);
    } else if (e.source === rootId && byId.has(e.target)) {
      outgoing.add(e.target);
      noteKind(e.target, e.kind);
    }
  }

  const entryFor = (id: string): NeighborEntry => {
    const isIn = incoming.has(id);
    const isOut = outgoing.has(id);
    const set = kinds.get(id) ?? new Set<DocGraphEdge["kind"]>();
    return {
      node: byId.get(id)!,
      direction: isIn && isOut ? "both" : isIn ? "in" : "out",
      edgeKinds: EDGE_KIND_ORDER.filter((k) => set.has(k)),
    };
  };

  const byPath = (a: string, b: string) =>
    (byId.get(a)!.path ?? "").localeCompare(byId.get(b)!.path ?? "") ||
    (a < b ? -1 : a > b ? 1 : 0);

  const inBlock = Array.from(incoming).sort(byPath);
  const outOnly = Array.from(outgoing)
    .filter((id) => !incoming.has(id))
    .sort(byPath);

  return [...inBlock, ...outOnly].map(entryFor);
}

/**
 * (C3) Resuelve el id de foco CONTRA EL GRAFO YA COMPUESTO (filtrado + agrupado).
 * Existe porque el foco lo eligió el operador sobre un grafo que después puede
 * cambiar de forma: un filtro puede descartar el nodo enfocado y un colapso de grupo
 * puede reemplazarlo por su super-nodo. Sin esto, focusSubgraph recibe un root
 * inexistente y —por su propia spec— devuelve un grafo VACÍO: pantalla en blanco sin
 * explicación (viola G13).
 *
 * Reglas, en este orden:
 *  1. focusRootId null → null.
 *  2. focusRootId presente en composed.nodes → ese mismo id.
 *  3. Si el nodo original existe y su grupo está colapsado, devolver
 *     GROUP_NODE_PREFIX + groupKeyOf(kind, source_id) si ese super-nodo está en
 *     composed.nodes.
 *  4. En cualquier otro caso → null (⇒ se muestra el grafo compuesto ENTERO, nunca
 *     vacío) y el caller avisa al operador (F4.2 punto 6).
 */
export function resolveFocusId(
  composed: DocGraphResponse,
  original: DocGraphResponse,
  focusRootId: string | null
): string | null {
  if (!focusRootId) return null;
  const composedIds = new Set((composed?.nodes ?? []).map((n) => n.id));
  if (composedIds.has(focusRootId)) return focusRootId;
  const orig = (original?.nodes ?? []).find((n) => n.id === focusRootId);
  if (orig) {
    const superId = GROUP_NODE_PREFIX + groupKeyOf(orig.kind, orig.source_id);
    if (composedIds.has(superId)) return superId;
  }
  return null;
}
