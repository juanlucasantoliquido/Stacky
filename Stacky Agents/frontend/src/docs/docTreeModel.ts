/**
 * Plan 285 F4 — el árbol de documentación deja de mezclar.
 *
 * El backend clasifica cada documento desde el Plan 284
 * (doc_indexer.py:172 → doc_taxonomy.classify_doc_path) y el frontend tenía la
 * información y NO la usaba: medido, 2 hits de `doc_class` en todo
 * `frontend/src/`, ninguno en el árbol. El operador seguía viendo 241 planes
 * revueltos con las 15 notas de su proyecto. Eso es, literalmente, la queja.
 *
 * Módulo PURO: sin React, sin DOM. RTL/jsdom no están instalados, así que un
 * `.test.tsx` reportaría "no tests" y saldría con código 0 — un falso verde
 * perfecto. Toda la lógica vive acá y se testea de verdad.
 */
import type { DocNode } from "../api/endpoints";

/** Las clases NO se inventan: son las de doc_taxonomy.DOC_CLASSES
 *  (backend/services/doc_taxonomy.py:16-18), verificadas contra el módulo. */
export type DocClass = "plan" | "system" | "project" | "agent" | "other";

export const DOC_CLASSES: readonly DocClass[] = [
  "plan",
  "system",
  "project",
  "agent",
  "other",
] as const;

/** Rótulos en castellano para los chips de filtro. */
export const DOC_CLASS_LABELS: Record<DocClass, string> = {
  plan: "Planes",
  system: "Sistema",
  project: "Proyecto",
  agent: "Agentes",
  other: "Otros",
};

/** Un nodo sin `doc_class`, con `""` (taxonomía OFF ⇒ doc_indexer.py:99
 *  devuelve "") o con un valor que no conocemos cae en "other" y por lo tanto
 *  sobrevive a cualquier filtro que incluya "other". Backward-compatible: un
 *  backend viejo se comporta exactamente como hoy. */
export function normalizeDocClass(raw: string | undefined | null): DocClass {
  const v = (raw ?? "").trim().toLowerCase();
  return (DOC_CLASSES as readonly string[]).includes(v) ? (v as DocClass) : "other";
}

export interface PartitionResult {
  visible: DocNode[];
  counts: Record<DocClass, number>;
  hidden: number;
}

function emptyCounts(): Record<DocClass, number> {
  return { plan: 0, system: 0, project: 0, agent: 0, other: 0 };
}

/** Cuenta HOJAS por clase sobre el árbol COMPLETO (no sobre el filtrado):
 *  el chip de "Planes" tiene que mostrar cuántos hay aunque estén ocultos,
 *  o el operador no sabe que existen. */
function countLeaves(nodes: DocNode[], acc: Record<DocClass, number>): number {
  let total = 0;
  for (const n of nodes ?? []) {
    const hijos = n.children ?? [];
    if (n.kind === "folder" || hijos.length > 0) {
      total += countLeaves(hijos, acc);
    } else {
      acc[normalizeDocClass(n.doc_class)] += 1;
      total += 1;
    }
  }
  return total;
}

function filterNodes(nodes: DocNode[], active: Set<DocClass>): DocNode[] {
  const out: DocNode[] = [];
  for (const n of nodes ?? []) {
    const hijos = n.children ?? [];
    const esCarpeta = n.kind === "folder" || hijos.length > 0;
    if (esCarpeta) {
      const vivos = filterNodes(hijos, active);
      // Una carpeta se conserva SOLO si algún descendiente queda visible.
      // Si no, se poda: una carpeta vacía de resultados es ruido.
      if (vivos.length > 0) out.push({ ...n, children: vivos });
    } else if (active.has(normalizeDocClass(n.doc_class))) {
      out.push(n);
    }
  }
  return out;
}

/**
 * Particiona el árbol según las clases activas.
 *
 * - `visible`: el árbol filtrado, con las carpetas sin descendientes podadas.
 * - `counts`: hojas por clase sobre el árbol COMPLETO.
 * - `hidden`: cuántas hojas quedaron fuera.
 *
 * Con `active` conteniendo todas las clases, `visible` equivale al árbol
 * original y `hidden` es 0 — que es el caso "flag apagada".
 */
export function partitionTreeByClass(
  nodes: DocNode[],
  active: Set<DocClass>
): PartitionResult {
  const counts = emptyCounts();
  const totalHojas = countLeaves(nodes ?? [], counts);
  const activas = active ?? new Set<DocClass>();
  const visible = filterNodes(nodes ?? [], activas);
  const vistas = countLeaves(visible, emptyCounts());
  return { visible, counts, hidden: Math.max(0, totalHojas - vistas) };
}

/** Selección inicial de los chips: todo activo MENOS los planes.
 *  Es el default que resuelve la queja — el operador ve su documentación y los
 *  planes quedan detrás de un clic, con su conteo a la vista. */
export function defaultActiveClasses(): Set<DocClass> {
  return new Set<DocClass>(["system", "project", "agent", "other"]);
}
