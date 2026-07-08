/**
 * dirTreeModel.ts — Plan 107 F3
 *
 * Modelo puro (sin React, sin I/O): convierte la lista plana PlanEntry[] del
 * dry-run (/api/devops/environments/plan) en un árbol jerárquico con estado
 * y conteos por nodo, para el preview de árbol de DirTreePreview.tsx.
 */
import type { PlanEntry, PlanEntryStatus } from "./environmentModel";

export type NodeStatus = PlanEntryStatus | "mixed";

export interface DirTreeNode {
  name: string; // último segmento ("b" para "a/b")
  path: string; // ruta relativa completa ("a/b"), separador '/'
  children: DirTreeNode[]; // ordenados asc por name (localeCompare)
  selfStatus: PlanEntryStatus | null; // status del entry EXACTO en este path, o null si es intermedio
  // [DESVÍO F3->F4, documentado]: el contrato original del plan no traía este
  // campo, pero el requisito UX de F4 (DirTreePreview) pide tooltip con el
  // `reason` del entry en nodos peligro (conflict/unsafe) -- sin esto es
  // irrecuperable desde el árbol. Extensión ADITIVA: no cambia ningún tipo ni
  // valor existente, solo agrega un campo nuevo. No rompe ningún test F3.
  selfReason: string | null; // reason del entry EXACTO en este path (solo conflict/unsafe lo usan)
  status: NodeStatus; // rollup del subárbol (ver reglas)
  counts: Record<PlanEntryStatus, number>; // conteo de entries reales en el subárbol
}

function emptyCounts(): Record<PlanEntryStatus, number> {
  return { to_create: 0, exists_ok: 0, conflict: 0, unsafe: 0 };
}

interface _MutableNode {
  name: string;
  path: string;
  childrenMap: Map<string, _MutableNode>;
  selfStatus: PlanEntryStatus | null;
  selfReason: string | null;
}

function _rootNode(): _MutableNode {
  return { name: "", path: "", childrenMap: new Map(), selfStatus: null, selfReason: null };
}

/**
 * buildDirTree — nesting determinístico de entries por '/'.
 * Reglas de rollup de `status` (prioridad de peligro):
 *   - si algún entry del subárbol es 'conflict' o 'unsafe' -> 'mixed' (peligro, se pinta danger)
 *   - si no, y algún entry es 'to_create' y algún otro 'exists_ok' -> 'mixed'
 *   - si todos los entries del subárbol son 'to_create' -> 'to_create'
 *   - si todos son 'exists_ok' -> 'exists_ok'
 * `counts` suma SOLO entries reales (los intermedios sin entry propio no cuentan).
 * Entradas duplicadas por path: la última gana en selfStatus (determinístico).
 * Paths con separador '\\' se normalizan a '/' antes de dividir.
 */
export function buildDirTree(entries: PlanEntry[]): DirTreeNode[] {
  const root = _rootNode();

  for (const entry of entries) {
    const normalized = (entry.path ?? "").replace(/\\/g, "/");
    const segments = normalized.split("/").filter((s) => s.length > 0);
    let current = root;
    const acc: string[] = [];
    for (const seg of segments) {
      acc.push(seg);
      let child = current.childrenMap.get(seg);
      if (!child) {
        child = { name: seg, path: acc.join("/"), childrenMap: new Map(), selfStatus: null, selfReason: null };
        current.childrenMap.set(seg, child);
      }
      current = child;
    }
    if (segments.length > 0) {
      current.selfStatus = entry.status; // última entrada gana (mismo nodo, se sobreescribe)
      current.selfReason = entry.reason ?? null;
    }
  }

  function statusFromCounts(counts: Record<PlanEntryStatus, number>): NodeStatus {
    if (counts.conflict > 0 || counts.unsafe > 0) return "mixed";
    const hasToCreate = counts.to_create > 0;
    const hasExists = counts.exists_ok > 0;
    if (hasToCreate && hasExists) return "mixed";
    if (hasToCreate) return "to_create";
    return "exists_ok";
  }

  function convert(node: _MutableNode): DirTreeNode {
    const children = Array.from(node.childrenMap.values())
      .map(convert)
      .sort((a, b) => a.name.localeCompare(b.name));

    const counts = emptyCounts();
    if (node.selfStatus) counts[node.selfStatus] += 1;
    for (const child of children) {
      (Object.keys(counts) as PlanEntryStatus[]).forEach((k) => {
        counts[k] += child.counts[k];
      });
    }

    return {
      name: node.name,
      path: node.path,
      children,
      selfStatus: node.selfStatus,
      selfReason: node.selfReason,
      status: statusFromCounts(counts),
      counts,
    };
  }

  return Array.from(root.childrenMap.values())
    .map(convert)
    .sort((a, b) => a.name.localeCompare(b.name));
}

/** Suma de counts de una lista de nodos raíz (para el encabezado del árbol). */
export function rollupCounts(nodes: DirTreeNode[]): Record<PlanEntryStatus, number> {
  const total = emptyCounts();
  for (const node of nodes) {
    (Object.keys(total) as PlanEntryStatus[]).forEach((k) => {
      total[k] += node.counts[k];
    });
  }
  return total;
}
