/**
 * staleness.ts — Plan 114 F4.
 *
 * Modelo PURO (sin fetch ni efectos) para el doctor de staleness doc↔código.
 * Lee los campos aditivos `has_stale` (nodo nota) y `stale` (arista code_ref)
 * que produce el backend cuando STACKY_DOCS_STALENESS_ENABLED está ON.
 */
import type { DocGraphNode, DocGraphEdge, DocGraphResponse } from "./docGraphModel";

/** true si la nota abierta está marcada como desactualizada. Tolera undefined. */
export function noteIsStale(node: DocGraphNode | null | undefined): boolean {
  return !!node && node.has_stale === true;
}

/** Aristas code_ref marcadas stale del grafo. Vacío si el grafo no viene anotado. */
export function staleEdges(graph: DocGraphResponse | undefined): DocGraphEdge[] {
  return (graph?.edges ?? []).filter(
    (e) => e.kind === "code_ref" && e.stale === true
  );
}
