/**
 * DocBacklinksPanel.tsx — Plan 111 F4.
 *
 * Lista las notas que enlazan al documento abierto (aristas entrantes del grafo 109).
 * Read-only, clickeable para navegar. Se oculta si el doc actual no mapea a un nodo
 * del grafo (best-effort). Máximo 50 entradas.
 */
import { backlinksOf, type DocGraphResponse } from "../../docs/docGraphModel";
import styles from "./DocBacklinksPanel.module.css";

interface DocBacklinksPanelProps {
  graph: DocGraphResponse | undefined;
  currentNodeId: string | null;
  onOpenNoteById: (id: string) => void;
}

export default function DocBacklinksPanel({
  graph,
  currentNodeId,
  onOpenNoteById,
}: DocBacklinksPanelProps) {
  // Ocultar si no hay grafo o el doc actual no resuelve a un nodo del grafo.
  if (!graph || !currentNodeId) return null;
  const exists = graph.nodes.some((n) => n.id === currentNodeId);
  if (!exists) return null;

  const backlinks = backlinksOf(graph, currentNodeId).slice(0, 50);

  return (
    <section className={styles.panel} aria-label="Backlinks">
      <h3 className={styles.title}>Backlinks</h3>
      {backlinks.length === 0 ? (
        <p className={styles.empty}>
          Ninguna nota enlaza a este documento todavía.
        </p>
      ) : (
        <ul className={styles.list}>
          {backlinks.map((n) => (
            <li key={n.id}>
              <button
                type="button"
                className={styles.item}
                onClick={() => onOpenNoteById(n.id)}
                title={n.path}
              >
                {n.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
