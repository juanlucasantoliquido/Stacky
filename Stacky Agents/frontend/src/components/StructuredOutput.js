import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/*
 * N2 — StructuredOutput
 * Renderiza el output de un agente como secciones colapsables interactivas.
 * Parsea headings de nivel 2 como secciones. Tablas se renderizan con bordes.
 * Cada sección tiene: toggle collapse, copiar al clipboard.
 * Diferenciador clave vs Copilot Chat: el output es una interfaz navegable.
 */
import { useState, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import MermaidDiagram from "./MermaidDiagram";
import styles from "./StructuredOutput.module.css";
// FA-21 — Intercepts ```mermaid blocks and replaces with <MermaidDiagram>.
// Returns an array of React nodes from a markdown string.
function renderWithMermaid(markdown, prefix) {
    const MERMAID_RE = /```mermaid\n([\s\S]*?)```/g;
    const parts = [];
    let lastIndex = 0;
    let match;
    let diagIndex = 0;
    while ((match = MERMAID_RE.exec(markdown)) !== null) {
        if (match.index > lastIndex) {
            const plain = markdown.slice(lastIndex, match.index);
            parts.push(_jsx(ReactMarkdown, { remarkPlugins: [remarkGfm], rehypePlugins: [rehypeHighlight], components: MD_COMPONENTS, children: plain }, `plain-${lastIndex}`));
        }
        parts.push(_jsx(MermaidDiagram, { id: `${prefix}-${diagIndex}`, code: match[1] }, `mermaid-${prefix}-${diagIndex++}`));
        lastIndex = match.index + match[0].length;
    }
    if (lastIndex < markdown.length) {
        parts.push(_jsx(ReactMarkdown, { remarkPlugins: [remarkGfm], rehypePlugins: [rehypeHighlight], components: MD_COMPONENTS, children: markdown.slice(lastIndex) }, `plain-${lastIndex}`));
    }
    return parts.length > 0 ? parts : [
        _jsx(ReactMarkdown, { remarkPlugins: [remarkGfm], rehypePlugins: [rehypeHighlight], components: MD_COMPONENTS, children: markdown }, "all")
    ];
}
// FA-20 — Citation Linker
// Detecta referencias `path/file.ext:NN`, `path/file.ext:NN-MM` y `ADO-XXXX`
// dentro del texto y las renderiza como links accionables.
const CITATION_RE = /\b((?:[\w./\\-]+?\.[a-zA-Z0-9]{1,6}):(\d+)(?:-(\d+))?|ADO[-\s]?(\d{2,}))\b/g;
function vscodeUrl(file, line) {
    // Truco standard: vscode:// abre el archivo si es relativo del workspace.
    return `vscode://file/${file}:${line}`;
}
function adoUrl(adoId) {
    return `https://dev.azure.com/UbimiaPacifico/Strategist_Pacifico/_workitems/edit/${adoId}`;
}
// Reemplaza citaciones en una string por nodos React.
function linkifyCitations(text) {
    const nodes = [];
    let lastIndex = 0;
    let match;
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
            nodes.push(_jsx("a", { href: adoUrl(adoId), target: "_blank", rel: "noopener noreferrer", className: styles.citation, "data-kind": "ado", title: `Abrir ADO-${adoId} en Azure DevOps`, children: fullMatch }, `${match.index}-ado`));
        }
        else if (filePart && lineNum) {
            nodes.push(_jsx("a", { href: vscodeUrl(filePart, parseInt(lineNum, 10)), className: styles.citation, "data-kind": "file", title: `Abrir ${filePart} línea ${lineNum} en VS Code`, children: fullMatch }, `${match.index}-file`));
        }
        else {
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
function citationChildren(children) {
    if (typeof children === "string") {
        return linkifyCitations(children);
    }
    if (Array.isArray(children)) {
        return children.map((c, i) => {
            if (typeof c === "string") {
                return _jsx("span", { children: linkifyCitations(c) }, i);
            }
            return c;
        });
    }
    return children;
}
const MD_COMPONENTS = {
    // Aplicamos citation linker en párrafos, items de lista y celdas de tabla.
    p: ({ children }) => _jsx("p", { children: citationChildren(children) }),
    li: ({ children }) => _jsx("li", { children: citationChildren(children) }),
    td: ({ children }) => _jsx("td", { children: citationChildren(children) }),
};
// Parsea el markdown en secciones usando headings h2 (##) como separadores
function parseSections(markdown) {
    const lines = markdown.split("\n");
    const sections = [];
    let preamble = [];
    let currentTitle = "";
    let currentLines = [];
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
        }
        else {
            if (inSection) {
                currentLines.push(line);
            }
            else {
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
function sectionIcon(title) {
    const t = title.toLowerCase();
    if (t.includes("traducción") || t.includes("funcional"))
        return "⇄";
    if (t.includes("alcance") || t.includes("cambio"))
        return "📝";
    if (t.includes("plan de prueba") || t.includes("prueba"))
        return "🧪";
    if (t.includes("test") || t.includes("tu-"))
        return "✅";
    if (t.includes("nota") || t.includes("developer"))
        return "💡";
    if (t.includes("trazabilidad"))
        return "🔗";
    if (t.includes("bd") || t.includes("base de datos") || t.includes("verificación"))
        return "🗄️";
    if (t.includes("compilación"))
        return "⚙️";
    if (t.includes("resumen"))
        return "📋";
    if (t.includes("cobertura"))
        return "📊";
    if (t.includes("verdict") || t.includes("veredicto"))
        return "⚖️";
    if (t.includes("riesgo"))
        return "⚠️";
    if (t.includes("caso"))
        return "☑";
    return "▸";
}
function CopyButton({ text }) {
    const [copied, setCopied] = useState(false);
    const handleCopy = useCallback(async () => {
        try {
            await navigator.clipboard.writeText(text);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
        }
        catch {
            // clipboard not available in all contexts
        }
    }, [text]);
    return (_jsx("button", { className: styles.copyBtn, onClick: handleCopy, title: "Copiar secci\u00F3n", children: copied ? "✓" : "⎘" }));
}
function SectionBlock({ section }) {
    const [collapsed, setCollapsed] = useState(false);
    return (_jsxs("div", { className: styles.section, children: [_jsxs("button", { className: styles.sectionHeader, onClick: () => setCollapsed((v) => !v), "aria-expanded": !collapsed, children: [_jsx("span", { className: styles.sectionIcon, children: sectionIcon(section.title) }), _jsx("span", { className: styles.sectionTitle, children: section.title }), _jsx("span", { className: styles.sectionActions, onClick: (e) => e.stopPropagation(), children: _jsx(CopyButton, { text: `## ${section.title}\n\n${section.content}` }) }), _jsx("span", { className: styles.chevron, children: collapsed ? "▸" : "▾" })] }), !collapsed && (_jsx("div", { className: styles.sectionBody, children: renderWithMermaid(section.content, `sec-${section.index}`) }))] }));
}
export default function StructuredOutput({ output, agentType }) {
    const { preamble, sections } = parseSections(output);
    const hasSections = sections.length > 0;
    // Si no hay secciones (output sin h2), degradar a markdown plano
    if (!hasSections) {
        return (_jsx("div", { className: styles.plain, children: renderWithMermaid(output, "plain") }));
    }
    return (_jsxs("div", { className: styles.structured, children: [preamble && (_jsx("div", { className: styles.preamble, children: renderWithMermaid(preamble, "preamble") })), _jsx("div", { className: styles.sections, children: sections.map((s) => (_jsx(SectionBlock, { section: s }, s.index))) }), _jsxs("div", { className: styles.footer, children: [_jsxs("span", { className: styles.meta, children: [sections.length, " secci\u00F3n", sections.length !== 1 ? "es" : "", " \u00B7 ", agentType] }), _jsx(CopyButton, { text: output })] })] }));
}
