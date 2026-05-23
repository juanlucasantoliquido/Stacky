import { Fragment as _Fragment, jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/**
 * DocTree.tsx - Arbol navegable de documentacion (Feature #3)
 *
 * Soporta secciones planas legacy y carpetas recursivas para los docs del
 * proyecto activo. Los archivos se pueden seleccionar; las carpetas expanden
 * o contraen sus hijos.
 */
import { useState } from "react";
import styles from "./DocTree.module.css";
// -- helpers de filtro ---------------------------------------------------------
function isFolder(node) {
    return node.kind === "folder";
}
function countFiles(nodes = []) {
    return nodes.reduce((acc, node) => {
        if (isFolder(node))
            return acc + countFiles(node.children ?? []);
        return acc + 1;
    }, 0);
}
function nodeOwnMatchesFilter(node, filter) {
    if (!filter)
        return true;
    const lower = filter.toLowerCase();
    if (node.label.toLowerCase().includes(lower))
        return true;
    return (node.headings ?? []).some((h) => h.text.toLowerCase().includes(lower));
}
function filterNode(node, filter) {
    if (!filter)
        return node;
    const children = node.children ?? [];
    if (isFolder(node)) {
        if (nodeOwnMatchesFilter(node, filter))
            return node;
        const filteredChildren = children
            .map((child) => filterNode(child, filter))
            .filter((child) => child !== null);
        return filteredChildren.length > 0 ? { ...node, children: filteredChildren } : null;
    }
    return nodeOwnMatchesFilter(node, filter) ? node : null;
}
/**
 * Resalta las ocurrencias de `filter` en `text` devolviendo spans.
 * Si no hay match o filtro vacio, devuelve el texto plano.
 */
function HighlightedText({ text, filter }) {
    if (!filter)
        return _jsx(_Fragment, { children: text });
    const lower = filter.toLowerCase();
    const idx = text.toLowerCase().indexOf(lower);
    if (idx === -1)
        return _jsx(_Fragment, { children: text });
    return (_jsxs(_Fragment, { children: [text.slice(0, idx), _jsx("mark", { className: styles.highlight, children: text.slice(idx, idx + filter.length) }), text.slice(idx + filter.length)] }));
}
function HeadingItem({ heading, onClick, filterText, depth }) {
    const isMatch = !!filterText && heading.text.toLowerCase().includes(filterText.toLowerCase());
    const paddingLeft = heading.level === 1 ? 28 + depth * 14 : 40 + depth * 14;
    return (_jsxs("li", { className: `${styles.headingItem} ${styles[`h${heading.level}`]} ${isMatch ? styles.filterMatch : ""}`, style: { paddingLeft }, onClick: (e) => {
            e.stopPropagation();
            onClick();
        }, title: heading.text, children: [_jsx("span", { className: styles.headingPrefix, children: heading.level === 1 ? "H1" : "H2" }), " ", _jsx(HighlightedText, { text: heading.text, filter: filterText })] }));
}
function DocItem({ node, onSelect, filterText, isSelected, selectedNodeId, depth = 0, }) {
    const [expanded, setExpanded] = useState(false);
    const folder = isFolder(node);
    const children = node.children ?? [];
    const hasHeadings = !folder && (node.headings ?? []).length > 0;
    const hasChildren = folder && children.length > 0;
    const autoExpandHeadings = !folder &&
        filterText.length > 0 &&
        (node.headings ?? []).some((h) => h.text.toLowerCase().includes(filterText.toLowerCase()));
    const showChildren = folder && (expanded || filterText.length > 0);
    const showHeadings = !folder && (expanded || autoExpandHeadings);
    const headerPaddingLeft = 12 + depth * 14;
    return (_jsxs("li", { className: `${styles.docItem} ${folder ? styles.folderItem : ""} ${isSelected ? styles.selected : ""}`, children: [_jsxs("div", { className: styles.docItemHeader, style: { paddingLeft: headerPaddingLeft }, onClick: () => {
                    if (folder) {
                        if (hasChildren)
                            setExpanded((v) => !v);
                        return;
                    }
                    onSelect(node);
                    if (hasHeadings)
                        setExpanded((v) => !v);
                }, title: node.display_path ?? node.path, children: [(hasHeadings || hasChildren) && (_jsx("span", { className: styles.expandIcon, children: (folder ? showChildren : showHeadings) ? "▾" : "▸" })), !hasHeadings && !hasChildren && _jsx("span", { className: styles.expandIcon, children: "\u00A0\u00A0" }), _jsx("span", { className: `${styles.docLabel} ${folder ? styles.folderLabel : ""}`, children: _jsx(HighlightedText, { text: node.label, filter: filterText }) }), _jsx("span", { className: styles.headingCount, children: folder ? countFiles(children) : (node.headings ?? []).length > 0 ? `${node.headings.length}h` : "" })] }), showChildren && (_jsx("ul", { className: styles.docList, children: children.map((child) => (_jsx(DocItem, { node: child, onSelect: onSelect, filterText: filterText, isSelected: selectedNodeId === child.id, selectedNodeId: selectedNodeId, depth: depth + 1 }, child.id))) })), showHeadings && (_jsx("ul", { className: styles.headingList, children: (node.headings ?? []).map((h, i) => (_jsx(HeadingItem, { heading: h, filterText: filterText, depth: depth, onClick: () => onSelect(node, h) }, i))) }))] }));
}
function RootSection({ root, visibleChildren, onSelect, filterText, selectedNodeId, }) {
    const [collapsed, setCollapsed] = useState(false);
    const fileCount = countFiles(visibleChildren);
    return (_jsxs("div", { className: styles.rootSection, children: [_jsxs("div", { className: styles.rootHeader, onClick: () => setCollapsed((v) => !v), title: `${root.label} - ${fileCount} documentos`, children: [_jsx("span", { className: styles.rootToggle, children: collapsed ? "▸" : "▾" }), _jsx("span", { className: styles.rootLabel, children: root.label }), _jsx("span", { className: styles.rootCount, children: fileCount })] }), !collapsed && (_jsxs("ul", { className: styles.docList, children: [visibleChildren.length === 0 && root.note && (_jsx("li", { className: styles.emptyNote, children: root.note })), visibleChildren.map((node) => (_jsx(DocItem, { node: node, onSelect: onSelect, filterText: filterText, isSelected: selectedNodeId === node.id, selectedNodeId: selectedNodeId }, node.id)))] }))] }));
}
// -- DocTree principal ---------------------------------------------------------
export default function DocTree({ roots, onSelect, filterText = "", selectedNodeId, }) {
    const filteredRoots = roots
        .map((root) => ({
        root,
        visibleChildren: filterText
            ? root.children
                .map((node) => filterNode(node, filterText))
                .filter((node) => node !== null)
            : root.children,
    }))
        .filter(({ visibleChildren, root }) => filterText ? visibleChildren.length > 0 : visibleChildren.length > 0 || !!root.note);
    if (roots.length === 0) {
        return (_jsx("div", { className: styles.emptyState, children: "No se encontr\u00F3 documentaci\u00F3n. Verific\u00E1 la ruta configurada." }));
    }
    if (filterText && filteredRoots.every(({ visibleChildren }) => visibleChildren.length === 0)) {
        return (_jsxs("div", { className: styles.emptyState, children: ["No se encontraron documentos que coincidan con \"", filterText, "\"."] }));
    }
    return (_jsx("nav", { className: styles.tree, "aria-label": "\u00C1rbol de documentaci\u00F3n", children: filteredRoots.map(({ root, visibleChildren }) => (_jsx(RootSection, { root: root, visibleChildren: visibleChildren, onSelect: onSelect, filterText: filterText, selectedNodeId: selectedNodeId }, root.id))) }));
}
