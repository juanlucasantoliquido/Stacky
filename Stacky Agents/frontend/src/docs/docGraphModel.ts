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
