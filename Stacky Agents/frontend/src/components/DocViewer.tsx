/**
 * DocViewer.tsx — Renderizador inline de markdown (Feature #3)
 *
 * Renderiza el contenido markdown del nodo seleccionado usando:
 *   - react-markdown@9.0.1
 *   - remark-gfm@4.0.0 (tablas, listas de tareas, strikethrough)
 *   - rehype-highlight@7.0.0 (syntax highlighting de código)
 *
 * Seguridad:
 *   - Links externos → target="_blank" rel="noopener noreferrer"
 *   - Links internos (anclas #) → preventDefault para no navegar fuera de la app
 *   - NO se usa dangerouslySetInnerHTML directo; react-markdown sanitiza por defecto
 */
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import type { DocNode } from "../api/endpoints";
import { remarkWikilinks } from "../docs/remarkWikilinks";
import { resolveWikilink } from "../docs/docGraphModel";
import styles from "./DocViewer.module.css";

// rehype-highlight importa highlight.js via CSS — necesitamos importar un tema.
// El tema está en el paquete de highlight.js que es dependencia de rehype-highlight.
import "highlight.js/styles/github-dark.css";

interface DocViewerProps {
  node: DocNode;
  content: string;
  isLoading?: boolean;
  error?: string | null;
  /** Plan 111: habilita [[wikilinks]] (solo con la flag STACKY_DOCS_GRAPH_ENABLED ON). */
  wikilinksEnabled?: boolean;
  /** Índice nombre→nodeId del grafo (109) para resolver wikilinks. */
  nameIndex?: Map<string, string>;
  /** Navegar a la nota resuelta por un wikilink. */
  onOpenNoteById?: (nodeId: string) => void;
  /** Plan 114: la nota abierta referencia código que cambió después (solo con flag ON). */
  isStale?: boolean;
  /** Plan 114: encola el Documentador en modo ACTUALIZAR sobre esta nota. */
  onProposeUpdate?: () => void;
  /** Plan 114: la acción "Proponer actualización" está en curso (deshabilita el botón). */
  proposeUpdatePending?: boolean;
}

// ── Link handler — intercepta links para evitar navegación fuera de la app ────

function makeLinkRenderer(
  nameIndex?: Map<string, string>,
  onOpenNoteById?: (nodeId: string) => void
) {
  return function LinkRenderer({
    href,
    children,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { children?: React.ReactNode }) {
    if (!href) {
      return <span {...props}>{children}</span>;
    }

    // Plan 111: wikilinks — resolver contra el índice del grafo.
    if (href.startsWith("wikilink:")) {
      const target = nameIndex ? resolveWikilink(href, nameIndex) : null;
      if (target && onOpenNoteById) {
        return (
          <a
            href="#"
            className="wikilink"
            onClick={(e) => {
              e.preventDefault();
              onOpenNoteById(target);
            }}
          >
            {children}
          </a>
        );
      }
      return (
        <span className="wikilink-broken" title="Nota no encontrada">
          {children}
        </span>
      );
    }

  // Link externo (http/https)
  if (href.startsWith("http://") || href.startsWith("https://")) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
        {children}
      </a>
    );
  }

  // Link interno (ancla #...) o relativo — interceptar
  return (
    <a
      href={href}
      onClick={(e) => {
        e.preventDefault();
        // Scroll al ancla si existe en el documento actual
        if (href.startsWith("#")) {
          const id = href.slice(1);
          const el = document.getElementById(id);
          if (el) el.scrollIntoView({ behavior: "smooth" });
        }
      }}
      {...props}
    >
      {children}
    </a>
  );
  };
}

// ── DocViewer ─────────────────────────────────────────────────────────────────

export default function DocViewer({
  node,
  content,
  isLoading,
  error,
  wikilinksEnabled,
  nameIndex,
  onOpenNoteById,
  isStale,
  onProposeUpdate,
  proposeUpdatePending,
}: DocViewerProps) {
  if (isLoading) {
    return (
      <div className={styles.stateContainer}>
        <div className={styles.spinner} />
        <p className={styles.stateText}>Cargando {node.label}...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.stateContainer}>
        <p className={styles.errorText}>Error al cargar el documento.</p>
        <p className={styles.errorDetail}>{error}</p>
      </div>
    );
  }

  return (
    <article className={styles.viewer}>
      <header className={styles.docHeader}>
        <span className={styles.docPath}>{node.display_path ?? node.path}</span>
        <span className={styles.docSize}>
          {node.size_bytes > 1024
            ? `${(node.size_bytes / 1024).toFixed(1)} KB`
            : `${node.size_bytes} B`}
        </span>
        {isStale && (
          <span className={styles.staleBox}>
            <span className="stale-chip" title="Esta nota referencia código que cambió después de su última edición">
              &#9888; referencia código que cambió
            </span>
            {onProposeUpdate && (
              <button
                type="button"
                className={styles.staleAction}
                disabled={proposeUpdatePending}
                onClick={onProposeUpdate}
              >
                {proposeUpdatePending ? "Encolando..." : "Proponer actualización"}
              </button>
            )}
          </span>
        )}
      </header>
      <div className={styles.markdownBody}>
        <ReactMarkdown
          remarkPlugins={wikilinksEnabled ? [remarkGfm, remarkWikilinks] : [remarkGfm]}
          rehypePlugins={[rehypeHighlight]}
          components={{
            a: makeLinkRenderer(nameIndex, onOpenNoteById) as any,
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    </article>
  );
}
