import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
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
import styles from "./DocViewer.module.css";
// rehype-highlight importa highlight.js via CSS — necesitamos importar un tema.
// El tema está en el paquete de highlight.js que es dependencia de rehype-highlight.
import "highlight.js/styles/github-dark.css";
// ── Link handler — intercepta links para evitar navegación fuera de la app ────
function LinkRenderer({ href, children, ...props }) {
    if (!href) {
        return _jsx("span", { ...props, children: children });
    }
    // Link externo (http/https)
    if (href.startsWith("http://") || href.startsWith("https://")) {
        return (_jsx("a", { href: href, target: "_blank", rel: "noopener noreferrer", ...props, children: children }));
    }
    // Link interno (ancla #...) o relativo — interceptar
    return (_jsx("a", { href: href, onClick: (e) => {
            e.preventDefault();
            // Scroll al ancla si existe en el documento actual
            if (href.startsWith("#")) {
                const id = href.slice(1);
                const el = document.getElementById(id);
                if (el)
                    el.scrollIntoView({ behavior: "smooth" });
            }
        }, ...props, children: children }));
}
// ── DocViewer ─────────────────────────────────────────────────────────────────
export default function DocViewer({ node, content, isLoading, error }) {
    if (isLoading) {
        return (_jsxs("div", { className: styles.stateContainer, children: [_jsx("div", { className: styles.spinner }), _jsxs("p", { className: styles.stateText, children: ["Cargando ", node.label, "..."] })] }));
    }
    if (error) {
        return (_jsxs("div", { className: styles.stateContainer, children: [_jsx("p", { className: styles.errorText, children: "Error al cargar el documento." }), _jsx("p", { className: styles.errorDetail, children: error })] }));
    }
    return (_jsxs("article", { className: styles.viewer, children: [_jsxs("header", { className: styles.docHeader, children: [_jsx("span", { className: styles.docPath, children: node.display_path ?? node.path }), _jsx("span", { className: styles.docSize, children: node.size_bytes > 1024
                            ? `${(node.size_bytes / 1024).toFixed(1)} KB`
                            : `${node.size_bytes} B` })] }), _jsx("div", { className: styles.markdownBody, children: _jsx(ReactMarkdown, { remarkPlugins: [remarkGfm], rehypePlugins: [rehypeHighlight], components: {
                        a: LinkRenderer,
                    }, children: content }) })] }));
}
