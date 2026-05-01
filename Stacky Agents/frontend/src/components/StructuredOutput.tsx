/*
 * N2 — StructuredOutput
 * Renderiza el output de un agente como secciones colapsables interactivas.
 * Parsea headings de nivel 2 como secciones. Tablas se renderizan con bordes.
 * Cada sección tiene: toggle collapse, copiar al clipboard.
 * Diferenciador clave vs Copilot Chat: el output es una interfaz navegable.
 */
import { useState, useCallback, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import type { AgentType } from "../types";
import MermaidDiagram from "./MermaidDiagram";
import styles from "./StructuredOutput.module.css";

// FA-21 — Intercepts ```mermaid blocks and replaces with <MermaidDiagram>.
// Returns an array of React nodes from a markdown string.
function renderWithMermaid(markdown: string, prefix: string): ReactNode[] {
  const MERMAID_RE = /```mermaid\n([\s\S]*?)```/g;
  const parts: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let diagIndex = 0;

  while ((match = MERMAID_RE.exec(markdown)) !== null) {
    if (match.index > lastIndex) {
      const plain = markdown.slice(lastIndex, match.index);
      parts.push(
        <ReactMarkdown
          key={`plain-${lastIndex}`}
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeHighlight]}
          components={MD_COMPONENTS}
        >
          {plain}
        </ReactMarkdown>
      );
    }
    parts.push(
      <MermaidDiagram
        key={`mermaid-${prefix}-${diagIndex++}`}
        id={`${prefix}-${diagIndex}`}
        code={match[1]}
      />
    );
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < markdown.length) {
    parts.push(
      <ReactMarkdown
        key={`plain-${lastIndex}`}
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={MD_COMPONENTS}
      >
        {markdown.slice(lastIndex)}
      </ReactMarkdown>
    );
  }
  return parts.length > 0 ? parts : [
    <ReactMarkdown
      key="all"
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeHighlight]}
      components={MD_COMPONENTS}
    >
      {markdown}
    </ReactMarkdown>
  ];
}

// FA-20 — Citation Linker
// Detecta referencias `path/file.ext:NN`, `path/file.ext:NN-MM` y `ADO-XXXX`
// dentro del texto y las renderiza como links accionables.
const CITATION_RE = /\b((?:[\w./\\-]+?\.[a-zA-Z0-9]{1,6}):(\d+)(?:-(\d+))?|ADO[-\s]?(\d{2,}))\b/g;

function vscodeUrl(file: string, line: number): string {
  // Truco standard: vscode:// abre el archivo si es relativo del workspace.
  return `vscode://file/${file}:${line}`;
}

function adoUrl(adoId: string): string {
  return `https://dev.azure.com/UbimiaPacifico/Strategist_Pacifico/_workitems/edit/${adoId}`;
}

// Reemplaza citaciones en una string por nodos React.
function linkifyCitations(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  CITATION_RE.lastIndex = 0;
  while ((match = CITATION_RE.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    const fullMatch = match[0];
    const filePart = match[2];
    const lineNum = match[3];
    const adoId = match[4];
    if (adoId) {
      nodes.push(
        <a
          key={`${match.index}-ado`}
          href={adoUrl(adoId)}
          target="_blank"
          rel="noopener noreferrer"
          className={styles.citation}
          data-kind="ado"
          title={`Abrir ADO-${adoId} en Azure DevOps`}
        >
          {fullMatch}
        </a>
      );
    } else if (filePart && lineNum) {
      nodes.push(
        <a
          key={`${match.index}-file`}
          href={vscodeUrl(filePart, parseInt(lineNum, 10))}
          className={styles.citation}
          data-kind="file"
          title={`Abrir ${filePart} línea ${lineNum} en VS Code`}
        >
          {fullMatch}
        </a>
      );
    } else {
      nodes.push(fullMatch);
    }
    lastIndex = match.index + fullMatch.length;
  }
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes;
}

// Recorre los children y aplica linkify sólo a las strings.
function citationChildren(children: ReactNode): ReactNode {
  if (typeof children === "string") {
    return linkifyCitations(children);
  }
  if (Array.isArray(children)) {
    return children.map((c, i) => {
      if (typeof c === "string") {
        return <span key={i}>{linkifyCitations(c)}</span>;
      }
      return c;
    });
  }
  return children;
}

const MD_COMPONENTS = {
  // Aplicamos citation linker en párrafos, items de lista y celdas de tabla.
  p: ({ children }: { children?: ReactNode }) => <p>{citationChildren(children)}</p>,
  li: ({ children }: { children?: ReactNode }) => <li>{citationChildren(children)}</li>,
  td: ({ children }: { children?: ReactNode }) => <td>{citationChildren(children)}</td>,
};

interface Section {
  title: string;
  content: string;
  index: number;
}

interface Props {
  output: string;
  agentType: AgentType;
}

// Parsea el markdown en secciones usando headings h2 (##) como separadores
function parseSections(markdown: string): { preamble: string; sections: Section[] } {
  const lines = markdown.split("\n");
  const sections: Section[] = [];
  let preamble: string[] = [];
  let currentTitle = "";
  let currentLines: string[] = [];
  let sectionIndex = 0;
  let inSection = false;

  for (const line of lines) {
    const h2Match = line.match(/^##\s+(.+)$/);
    if (h2Match) {
      if (inSection) {
        sections.push({
          title: currentTitle,
          content: currentLines.join("\n").trim(),
          index: sectionIndex++,
        });
      }
      currentTitle = h2Match[1].trim();
      currentLines = [];
      inSection = true;
    } else {
      if (inSection) {
        currentLines.push(line);
      } else {
        preamble.push(line);
      }
    }
  }

  if (inSection && currentLines.length > 0) {
    sections.push({
      title: currentTitle,
      content: currentLines.join("\n").trim(),
      index: sectionIndex,
    });
  }

  return { preamble: preamble.join("\n").trim(), sections };
}

// Íconos de sección por palabras clave del título
function sectionIcon(title: string): string {
  const t = title.toLowerCase();
  if (t.includes("traducción") || t.includes("funcional")) return "⇄";
  if (t.includes("alcance") || t.includes("cambio")) return "📝";
  if (t.includes("plan de prueba") || t.includes("prueba")) return "🧪";
  if (t.includes("test") || t.includes("tu-")) return "✅";
  if (t.includes("nota") || t.includes("developer")) return "💡";
  if (t.includes("trazabilidad")) return "🔗";
  if (t.includes("bd") || t.includes("base de datos") || t.includes("verificación")) return "🗄️";
  if (t.includes("compilación")) return "⚙️";
  if (t.includes("resumen")) return "📋";
  if (t.includes("cobertura")) return "📊";
  if (t.includes("verdict") || t.includes("veredicto")) return "⚖️";
  if (t.includes("riesgo")) return "⚠️";
  if (t.includes("caso")) return "☑";
  return "▸";
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard not available in all contexts
    }
  }, [text]);

  return (
    <button className={styles.copyBtn} onClick={handleCopy} title="Copiar sección">
      {copied ? "✓" : "⎘"}
    </button>
  );
}

function SectionBlock({ section }: { section: Section }) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className={styles.section}>
      <button
        className={styles.sectionHeader}
        onClick={() => setCollapsed((v) => !v)}
        aria-expanded={!collapsed}
      >
        <span className={styles.sectionIcon}>{sectionIcon(section.title)}</span>
        <span className={styles.sectionTitle}>{section.title}</span>
        <span className={styles.sectionActions} onClick={(e) => e.stopPropagation()}>
          <CopyButton text={`## ${section.title}\n\n${section.content}`} />
        </span>
        <span className={styles.chevron}>{collapsed ? "▸" : "▾"}</span>
      </button>

      {!collapsed && (
        <div className={styles.sectionBody}>
          {renderWithMermaid(section.content, `sec-${section.index}`)}
        </div>
      )}
    </div>
  );
}

export default function StructuredOutput({ output, agentType }: Props) {
  const { preamble, sections } = parseSections(output);
  const hasSections = sections.length > 0;

  // Si no hay secciones (output sin h2), degradar a markdown plano
  if (!hasSections) {
    return (
      <div className={styles.plain}>
        {renderWithMermaid(output, "plain")}
      </div>
    );
  }

  return (
    <div className={styles.structured}>
      {preamble && (
        <div className={styles.preamble}>
          {renderWithMermaid(preamble, "preamble")}
        </div>
      )}
      <div className={styles.sections}>
        {sections.map((s) => (
          <SectionBlock key={s.index} section={s} />
        ))}
      </div>
      <div className={styles.footer}>
        <span className={styles.meta}>
          {sections.length} sección{sections.length !== 1 ? "es" : ""} · {agentType}
        </span>
        <CopyButton text={output} />
      </div>
    </div>
  );
}
