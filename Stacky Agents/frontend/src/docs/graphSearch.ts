/**
 * graphSearch.ts — Plan 268 F2.
 * Búsqueda rankeada y DETERMINISTA sobre los nodos del grafo. Sin fetch, sin DOM.
 */
import type { DocGraphResponse, DocGraphNode } from "./docGraphModel";

export interface GraphSearchMatch {
  nodeId: string;
  /** 3 = el label empieza con la query; 2 = el label la contiene; 1 = solo el path la contiene */
  rank: 3 | 2 | 1;
  node: DocGraphNode;
}

/**
 * Devuelve las coincidencias ordenadas por rank DESC y, a igual rank, por
 * `path` ascendente (localeCompare) y luego por `id` ascendente — determinista.
 * Query vacía o solo espacios → []. Comparación case-insensitive sobre trim().
 * `limit` acota el resultado (default 200) para que la lista no explote.
 */
export function searchGraphNodes(
  graph: DocGraphResponse | undefined,
  query: string,
  limit: number = 200
): GraphSearchMatch[] {
  const q = (query ?? "").trim().toLowerCase();
  if (!q) return [];
  const out: GraphSearchMatch[] = [];
  for (const n of graph?.nodes ?? []) {
    const lab = (n.label ?? "").toLowerCase();
    const pth = (n.path ?? "").toLowerCase();
    const rank: 3 | 2 | 1 | 0 = lab.startsWith(q)
      ? 3
      : lab.includes(q)
        ? 2
        : pth.includes(q)
          ? 1
          : 0;
    if (rank) out.push({ nodeId: n.id, rank, node: n });
  }
  out.sort(
    (a, b) =>
      b.rank - a.rank ||
      (a.node.path ?? "").localeCompare(b.node.path ?? "") ||
      (a.nodeId < b.nodeId ? -1 : a.nodeId > b.nodeId ? 1 : 0)
  );
  return out.slice(0, Math.max(0, limit));
}

/** Set de ids de las coincidencias (para el resaltado del canvas; reemplaza a filterNodeIds). */
export function matchIdSet(matches: GraphSearchMatch[]): Set<string> {
  return new Set(matches.map((m) => m.nodeId));
}

/** El nodeId de la coincidencia en `index`, o null si no hay coincidencias.
 *  `index` se toma módulo length; un índice negativo devuelve null. */
export function matchAt(matches: GraphSearchMatch[], index: number): string | null {
  if (!matches.length) return null;
  if (!Number.isFinite(index) || index < 0) return null;
  return matches[Math.floor(index) % matches.length].nodeId;
}
