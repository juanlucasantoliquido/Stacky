import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/*
 * FA-21 — Mermaid diagram auto-render.
 * Renderiza bloques ```mermaid del output como diagramas SVG interactivos.
 * Inicialización lazy: mermaid se carga solo cuando hay diagramas en el output.
 */
import { useEffect, useRef, useState } from "react";
import styles from "./MermaidDiagram.module.css";
let mermaidLoaded = false;
let mermaidInit = null;
async function loadMermaid() {
    if (mermaidLoaded)
        return;
    if (mermaidInit)
        return mermaidInit;
    mermaidInit = import("mermaid").then(({ default: m }) => {
        m.initialize({
            startOnLoad: false,
            theme: "dark",
            themeVariables: {
                background: "#0e1116",
                primaryColor: "#1e2330",
                primaryTextColor: "#e6e9f0",
                primaryBorderColor: "#2a3142",
                lineColor: "#5b8def",
                secondaryColor: "#161a21",
                tertiaryColor: "#0a0d12",
                noteBkgColor: "#1e2330",
                noteTextColor: "#e6e9f0",
                edgeLabelBackground: "#161a21",
                clusterBkg: "#161a21",
                titleColor: "#e6e9f0",
                fontFamily: "JetBrains Mono, Consolas, monospace",
                fontSize: "13px",
            },
        });
        mermaidLoaded = true;
    });
    return mermaidInit;
}
export default function MermaidDiagram({ code, id }) {
    const containerRef = useRef(null);
    const [error, setError] = useState(null);
    const [svg, setSvg] = useState(null);
    const [zoom, setZoom] = useState(false);
    useEffect(() => {
        let cancelled = false;
        setError(null);
        setSvg(null);
        (async () => {
            try {
                await loadMermaid();
                const { default: m } = await import("mermaid");
                const { svg: rendered } = await m.render(`mermaid-${id}`, code.trim());
                if (!cancelled)
                    setSvg(rendered);
            }
            catch (e) {
                if (!cancelled)
                    setError(e?.message ?? "Error al renderizar diagrama");
            }
        })();
        return () => { cancelled = true; };
    }, [code, id]);
    const liveUrl = `https://mermaid.live/edit#base64:${btoa(code.trim())}`;
    return (_jsxs("div", { className: `${styles.wrapper} ${zoom ? styles.zoomed : ""}`, children: [_jsxs("div", { className: styles.toolbar, children: [_jsx("span", { className: styles.badge, children: "diagram" }), _jsx("a", { href: liveUrl, target: "_blank", rel: "noopener noreferrer", className: styles.action, children: "Editar en mermaid.live \u2197" }), _jsx("button", { className: styles.action, onClick: () => setZoom(v => !v), children: zoom ? "⊡ reducir" : "⊞ expandir" }), _jsx("button", { className: styles.action, onClick: () => navigator.clipboard.writeText(code), children: "\u2398 copiar c\u00F3digo" })] }), error && (_jsxs("div", { className: styles.error, children: [_jsxs("span", { children: ["\u26A0 Error en el diagrama: ", error] }), _jsx("pre", { className: styles.fallback, children: code })] })), !error && !svg && (_jsx("div", { className: styles.loading, children: "renderizando diagrama\u2026" })), svg && (_jsx("div", { ref: containerRef, className: styles.svg, dangerouslySetInnerHTML: { __html: svg } }))] }));
}
