/**
 * DocGraphPeek.tsx — Plan 268 F6.2.
 *
 * Panel lateral que muestra el PRINCIPIO del documento del nodo seleccionado sin
 * abandonar el grafo. Es un cascarón: el fetch lo hace `useQuery` con la MISMA
 * queryKey que el Lector (para compartir cache) y toda la lógica de texto vive en
 * `docs/graphPreview.ts` (puro y testeado). Cero atributos de estilo en línea (G8).
 */
import { useQuery } from "@tanstack/react-query";
import { Docs } from "../../api/endpoints";
import type { DocGraphNode } from "../../docs/docGraphModel";
import type { NeighborEntry } from "../../docs/graphNeighborhood";
import { previewExcerpt, previewTitle } from "../../docs/graphPreview";
import { isGroupNodeId } from "../../docs/graphGrouping";
import SkeletonList from "../SkeletonList";
import styles from "./DocGraphExplorer.module.css";

interface DocGraphPeekProps {
  node: DocGraphNode | null; // el nodo seleccionado (ui.peekNodeId ya resuelto)
  projectName?: string;
  neighbors: NeighborEntry[];
  onOpenNote: (nodeId: string) => void;
  onFocusNode: (nodeId: string) => void;
  onClose: () => void;
}

const KIND_LABEL: Record<string, string> = {
  note: "Nota",
  code: "Código",
  missing: "Faltante",
};

const DIRECTION_LABEL: Record<NeighborEntry["direction"], string> = {
  in: "lo referencia",
  out: "referencia a",
  both: "en los dos sentidos",
};

export default function DocGraphPeek({
  node,
  projectName,
  neighbors,
  onOpenNote,
  onFocusNode,
  onClose,
}: DocGraphPeekProps) {
  // Un super-nodo de grupo y los nodos code/missing no tienen documento que leer.
  const isReadable = Boolean(node && node.kind === "note" && node.path && !isGroupNodeId(node.id));

  const { data, isLoading, error } = useQuery({
    // ⚠️ Misma expresión de clave que el Lector (DocsPage): así se comparte la cache.
    // El hit NO es garantizable (DocNode.source_id es opcional allá y obligatorio
    // acá): si difieren se hace un GET de más, que es una lectura de disco local.
    queryKey: ["docs-content", projectName ?? "active", node?.source_id, node?.path],
    queryFn: () => Docs.getContent(node!.path, { project: projectName, sourceId: node!.source_id }),
    enabled: isReadable,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  if (!node) return null;

  const content = data?.content;
  const title = (isReadable ? previewTitle(content) : null) ?? node.label;

  return (
    <aside className={styles.peek} aria-label="Vista previa del nodo">
      <div className={styles.peekHeader}>
        <h3 className={styles.peekTitle}>{title}</h3>
        <button
          type="button"
          className={styles.peekClose}
          onClick={onClose}
          title="Cerrar la vista previa"
          aria-label="Cerrar la vista previa"
        >
          &#10005;
        </button>
      </div>

      <div className={styles.peekChips}>
        <span className={styles.tag}>{KIND_LABEL[node.kind] ?? node.kind}</span>
        {node.source_id ? <span className={styles.tag}>{node.source_id}</span> : null}
        <span className={styles.tag}>
          {node.in_degree} entrantes · {node.out_degree} salientes
        </span>
        {node.has_stale ? (
          <span className={`${styles.tag} ${styles.tagStale}`}>Desactualizada</span>
        ) : null}
      </div>

      {isReadable ? (
        isLoading ? (
          <SkeletonList rows={4} rowHeight={14} ariaLabel="Cargando la vista previa" />
        ) : error ? (
          <p className={styles.peekMuted}>No se pudo cargar la vista previa.</p>
        ) : (
          <p className={styles.peekBody}>{previewExcerpt(content, 600)}</p>
        )
      ) : (
        <p className={styles.peekMuted}>
          {isGroupNodeId(node.id)
            ? "Es un grupo colapsado: hacé click en el nodo grande para expandirlo."
            : "Este elemento no tiene un documento asociado para previsualizar."}
        </p>
      )}

      <div className={styles.peekActions}>
        {isReadable ? (
          <button
            type="button"
            className={styles.navBtn}
            onClick={() => onOpenNote(node.id)}
            title="Abrir la nota completa en el Lector"
          >
            Abrir en el Lector
          </button>
        ) : null}
        <button
          type="button"
          className={styles.navBtn}
          onClick={() => onFocusNode(node.id)}
          title="Aislar este nodo y su vecindario"
        >
          Enfocar
        </button>
      </div>

      {neighbors.length ? (
        <>
          <span className={styles.sectionLabel}>Relaciones ({neighbors.length})</span>
          <ul className={styles.relations}>
            {neighbors.map((n) => (
              <li key={n.node.id}>
                <button
                  type="button"
                  className={styles.relItem}
                  onClick={() => onFocusNode(n.node.id)}
                  title={`${DIRECTION_LABEL[n.direction]} · ${n.node.path || n.node.id}`}
                >
                  <span className={styles.relDir}>{DIRECTION_LABEL[n.direction]}</span>
                  {n.node.label}
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </aside>
  );
}
