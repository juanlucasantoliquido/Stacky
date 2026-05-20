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
import styles from "./DocViewer.module.css";

// rehype-highlight importa highlight.js via CSS — necesitamos importar un tema.
// El tema está en el paquete de highlight.js que es dependencia de rehype-highlight.
import "highlight.js/styles/github-dark.css";

interface DocViewerProps {
  node: DocNode;
  content: string;
  isLoading?: boolean;
  error?: string | null;
}

// ── Link handler — intercepta links para evitar navegación fuera de la app ────

function LinkRenderer({
  href,
  children,
  ...props
}: React.AnchorHTMLAttributes<HTMLAnchorElement> & { children?: React.ReactNode }) {
  if (!href) {
    return <span {...props}>{children}</span>;
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
}

// ── DocViewer ─────────────────────────────────────────────────────────────────

export default function DocViewer({ node, content, isLoading, error }: DocViewerProps) {
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
      </header>
      <div className={styles.markdownBody}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeHighlight]}
          components={{
            a: LinkRenderer as any,
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    </article>
  );
}
