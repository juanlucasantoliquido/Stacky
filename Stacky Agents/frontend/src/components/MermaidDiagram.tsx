/*
 * FA-21 — Mermaid diagram auto-render.
 * Renderiza bloques ```mermaid del output como diagramas SVG interactivos.
 * Inicialización lazy: mermaid se carga solo cuando hay diagramas en el output.
 */
import { useEffect, useRef, useState } from "react";
import styles from "./MermaidDiagram.module.css";

interface Props {
  code: string;
  id: string;
}

let mermaidLoaded = false;
let mermaidInit: Promise<void> | null = null;

async function loadMermaid(): Promise<void> {
  if (mermaidLoaded) return;
  if (mermaidInit) return mermaidInit;
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

export default function MermaidDiagram({ code, id }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [svg, setSvg] = useState<string | null>(null);
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
        if (!cancelled) setSvg(rendered);
      } catch (e: any) {
        if (!cancelled) setError(e?.message ?? "Error al renderizar diagrama");
      }
    })();
    return () => { cancelled = true; };
  }, [code, id]);

  const liveUrl = `https://mermaid.live/edit#base64:${btoa(code.trim())}`;

  return (
    <div className={`${styles.wrapper} ${zoom ? styles.zoomed : ""}`}>
      <div className={styles.toolbar}>
        <span className={styles.badge}>diagram</span>
        <a href={liveUrl} target="_blank" rel="noopener noreferrer" className={styles.action}>
          Editar en mermaid.live ↗
        </a>
        <button className={styles.action} onClick={() => setZoom(v => !v)}>
          {zoom ? "⊡ reducir" : "⊞ expandir"}
        </button>
        <button className={styles.action} onClick={() => navigator.clipboard.writeText(code)}>
          ⎘ copiar código
        </button>
      </div>

      {error && (
        <div className={styles.error}>
          <span>⚠ Error en el diagrama: {error}</span>
          <pre className={styles.fallback}>{code}</pre>
        </div>
      )}

      {!error && !svg && (
        <div className={styles.loading}>renderizando diagrama…</div>
      )}

      {svg && (
        <div
          ref={containerRef}
          className={styles.svg}
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      )}
    </div>
  );
}
