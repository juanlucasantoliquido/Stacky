/**
 * docGraphModel.ts — Plan 109 F5.
 *
 * Tipos del contrato de GET /api/docs/graph (§4.1 del plan) y modelo PURO
 * `summarizeGraph` para la pestaña "Cobertura". Sin efectos ni fetch.
 */

export interface DocGraphNode {
  id: string;
  kind: "note" | "code" | "missing";
  label: string;
  path: string;
  source_id: string;
  in_degree: number;
  out_degree: number;
  has_frontmatter: boolean;
  exists: boolean;
}

export interface DocGraphEdge {
  source: string;
  target: string;
  kind: "md" | "wikilink" | "code_ref";
}

export interface DocHealth {
  status: "SIN_DOCS" | "FORMATO_NO_OBSIDIAN" | "INCOMPLETA" | "SANA";
  reasons: string[];
  frontmatter_ratio: number;
  wikilink_edges: number;
  uncovered_modules: string[];
}

export interface DocGraphSource {
  id: string;
  kind: string;
  label: string;
  relative_path: string;
  absolute_path: string;
}

export interface DocGraphResponse {
  ok: boolean;
  generated_at: string;
  active_project: string | null;
  sources: DocGraphSource[];
  nodes: DocGraphNode[];
  edges: DocGraphEdge[];
  orphans: string[];
  stats: Record<string, number>;
  doc_health: DocHealth | null;
}

export interface DocCoverageSummary {
  notes: number;
  codeRefs: number;
  missing: number;
  totalEdges: number;
  /** Suma de in_degree de nodos kind==="note". */
  totalBacklinks: number;
  /** Nodos cuyo id está en orphans, ordenados por path. */
  orphanNotes: DocGraphNode[];
  sources: number;
  health: DocHealth | null;
}

/** Índice nombre-lower-sin-extensión → nodeId, para resolver wikilinks. Mismo
 *  criterio de colisión que el backend (109): gana el path lexicográficamente menor
 *  (y a igual path, el source_id menor). */
export function buildNameIndex(graph: DocGraphResponse): Map<string, string> {
  const idx = new Map<string, string>();
  const notes = (graph?.nodes ?? [])
    .filter((n) => n.kind === "note")
    .slice()
    .sort((a, b) =>
      a.path < b.path ? -1 : a.path > b.path ? 1 : a.source_id < b.source_id ? -1 : 1
    );
  for (const n of notes) {
    const base = n.label.replace(/\.md$/i, "").toLowerCase();
    if (!idx.has(base)) idx.set(base, n.id); // primera (menor) gana
  }
  return idx;
}

/** Resuelve "wikilink:<nombre>" a un nodeId o null. */
export function resolveWikilink(
  url: string,
  nameIndex: Map<string, string>
): string | null {
  if (!url.startsWith("wikilink:")) return null;
  const name = url.slice("wikilink:".length).trim().toLowerCase();
  return nameIndex.get(name) ?? null;
}

/** Notas que enlazan al nodo dado (aristas entrantes: edge.target === nodeId).
 *  Devuelve los nodos `source` resueltos, ordenados por path. null/ausente → []. */
export function backlinksOf(
  graph: DocGraphResponse | undefined,
  nodeId: string | null
): DocGraphNode[] {
  if (!graph || !nodeId) return [];
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const seen = new Set<string>();
  const out: DocGraphNode[] = [];
  for (const e of graph.edges) {
    if (e.target !== nodeId) continue;
    if (seen.has(e.source)) continue;
    const src = byId.get(e.source);
    if (src) {
      seen.add(e.source);
      out.push(src);
    }
  }
  return out.sort((a, b) => a.path.localeCompare(b.path));
}

/** Ids de nodos cuyo label matchea query (substring case-insensitive, trim).
 *  Query vacía → Set vacío. */
export function filterNodeIds(
  graph: DocGraphResponse,
  query: string
): Set<string> {
  const q = query.trim().toLowerCase();
  const out = new Set<string>();
  if (!q) return out;
  for (const n of graph?.nodes ?? []) {
    if (n.label.toLowerCase().includes(q)) out.add(n.id);
  }
  return out;
}

/** Puro y total: tolera arrays vacíos y doc_health null. */
export function summarizeGraph(graph: DocGraphResponse): DocCoverageSummary {
  const nodes = graph?.nodes ?? [];
  const edges = graph?.edges ?? [];
  const orphans = graph?.orphans ?? [];
  const orphanSet = new Set(orphans);
  const noteNodes = nodes.filter((n) => n.kind === "note");
  const orphanNotes = noteNodes
    .filter((n) => orphanSet.has(n.id))
    .slice()
    .sort((a, b) => a.path.localeCompare(b.path));
  const totalBacklinks = noteNodes.reduce(
    (acc, n) => acc + (n.in_degree || 0),
    0
  );
  return {
    notes: noteNodes.length,
    codeRefs: nodes.filter((n) => n.kind === "code").length,
    missing: nodes.filter((n) => n.kind === "missing").length,
    totalEdges: edges.length,
    totalBacklinks,
    orphanNotes,
    sources: graph?.sources?.length ?? 0,
    health: graph?.doc_health ?? null,
  };
}
