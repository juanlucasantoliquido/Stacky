/**
 * DocTree.tsx - Arbol navegable de documentacion (Feature #3)
 *
 * Soporta secciones planas legacy y carpetas recursivas para los docs del
 * proyecto activo. Los archivos se pueden seleccionar; las carpetas expanden
 * o contraen sus hijos.
 */
import { useState, type CSSProperties } from "react";
import type { DocRoot, DocNode, DocHeading } from "../api/endpoints";
import styles from "./DocTree.module.css";

interface DocTreeProps {
  roots: DocRoot[];
  onSelect: (node: DocNode, heading?: DocHeading) => void;
  /** Texto de filtro. Vacio = sin filtro. */
  filterText?: string;
  /** Nodo actualmente seleccionado (para resaltar). */
  selectedNodeId?: string;
}

// -- helpers de filtro ---------------------------------------------------------

function isFolder(node: DocNode): boolean {
  return node.kind === "folder";
}

function countFiles(nodes: DocNode[] = []): number {
  return nodes.reduce((acc, node) => {
    if (isFolder(node)) return acc + countFiles(node.children ?? []);
    return acc + 1;
  }, 0);
}

function nodeOwnMatchesFilter(node: DocNode, filter: string): boolean {
  if (!filter) return true;
  const lower = filter.toLowerCase();
  if (node.label.toLowerCase().includes(lower)) return true;
  return (node.headings ?? []).some((h) => h.text.toLowerCase().includes(lower));
}

function filterNode(node: DocNode, filter: string): DocNode | null {
  if (!filter) return node;

  const children = node.children ?? [];
  if (isFolder(node)) {
    if (nodeOwnMatchesFilter(node, filter)) return node;
    const filteredChildren = children
      .map((child) => filterNode(child, filter))
      .filter((child): child is DocNode => child !== null);
    return filteredChildren.length > 0 ? { ...node, children: filteredChildren } : null;
  }

  return nodeOwnMatchesFilter(node, filter) ? node : null;
}

/**
 * Resalta las ocurrencias de `filter` en `text` devolviendo spans.
 * Si no hay match o filtro vacio, devuelve el texto plano.
 */
function HighlightedText({ text, filter }: { text: string; filter: string }) {
  if (!filter) return <>{text}</>;

  const lower = filter.toLowerCase();
  const idx = text.toLowerCase().indexOf(lower);
  if (idx === -1) return <>{text}</>;

  return (
    <>
      {text.slice(0, idx)}
      <mark className={styles.highlight}>{text.slice(idx, idx + filter.length)}</mark>
      {text.slice(idx + filter.length)}
    </>
  );
}

// -- sub-component: HeadingItem ------------------------------------------------

interface HeadingItemProps {
  heading: DocHeading;
  onClick: () => void;
  filterText: string;
  depth: number;
}

function HeadingItem({ heading, onClick, filterText, depth }: HeadingItemProps) {
  const isMatch =
    !!filterText && heading.text.toLowerCase().includes(filterText.toLowerCase());
  const paddingLeft = heading.level === 1 ? 28 + depth * 14 : 40 + depth * 14;

  return (
    <li
      className={`${styles.headingItem} ${styles[`h${heading.level}`]} ${isMatch ? styles.filterMatch : ""}`}
      style={{ paddingLeft } as CSSProperties}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      title={heading.text}
    >
      <span className={styles.headingPrefix}>{heading.level === 1 ? "H1" : "H2"}</span>{" "}
      <HighlightedText text={heading.text} filter={filterText} />
    </li>
  );
}

// -- sub-component: DocItem ----------------------------------------------------

interface DocItemProps {
  node: DocNode;
  onSelect: (node: DocNode, heading?: DocHeading) => void;
  filterText: string;
  isSelected: boolean;
  selectedNodeId?: string;
  depth?: number;
}

function DocItem({
  node,
  onSelect,
  filterText,
  isSelected,
  selectedNodeId,
  depth = 0,
}: DocItemProps) {
  const [expanded, setExpanded] = useState(false);
  const folder = isFolder(node);
  const children = node.children ?? [];
  const hasHeadings = !folder && (node.headings ?? []).length > 0;
  const hasChildren = folder && children.length > 0;

  const autoExpandHeadings =
    !folder &&
    filterText.length > 0 &&
    (node.headings ?? []).some((h) => h.text.toLowerCase().includes(filterText.toLowerCase()));

  const showChildren = folder && (expanded || filterText.length > 0);
  const showHeadings = !folder && (expanded || autoExpandHeadings);
  const headerPaddingLeft = 12 + depth * 14;

  return (
    <li
      className={`${styles.docItem} ${folder ? styles.folderItem : ""} ${isSelected ? styles.selected : ""}`}
    >
      <div
        className={styles.docItemHeader}
        style={{ paddingLeft: headerPaddingLeft } as CSSProperties}
        onClick={() => {
          if (folder) {
            if (hasChildren) setExpanded((v) => !v);
            return;
          }
          onSelect(node);
          if (hasHeadings) setExpanded((v) => !v);
        }}
        title={node.display_path ?? node.path}
      >
        {(hasHeadings || hasChildren) && (
          <span className={styles.expandIcon}>
            {(folder ? showChildren : showHeadings) ? "▾" : "▸"}
          </span>
        )}
        {!hasHeadings && !hasChildren && <span className={styles.expandIcon}>&nbsp;&nbsp;</span>}
        <span className={`${styles.docLabel} ${folder ? styles.folderLabel : ""}`}>
          <HighlightedText text={node.label} filter={filterText} />
        </span>
        <span className={styles.headingCount}>
          {folder ? countFiles(children) : (node.headings ?? []).length > 0 ? `${node.headings.length}h` : ""}
        </span>
      </div>

      {showChildren && (
        <ul className={styles.docList}>
          {children.map((child) => (
            <DocItem
              key={child.id}
              node={child}
              onSelect={onSelect}
              filterText={filterText}
              isSelected={selectedNodeId === child.id}
              selectedNodeId={selectedNodeId}
              depth={depth + 1}
            />
          ))}
        </ul>
      )}

      {showHeadings && (
        <ul className={styles.headingList}>
          {(node.headings ?? []).map((h, i) => (
            <HeadingItem
              key={i}
              heading={h}
              filterText={filterText}
              depth={depth}
              onClick={() => onSelect(node, h)}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

// -- sub-component: RootSection ------------------------------------------------

interface RootSectionProps {
  root: DocRoot;
  visibleChildren: DocNode[];
  onSelect: (node: DocNode, heading?: DocHeading) => void;
  filterText: string;
  selectedNodeId?: string;
}

function RootSection({
  root,
  visibleChildren,
  onSelect,
  filterText,
  selectedNodeId,
}: RootSectionProps) {
  const [collapsed, setCollapsed] = useState(false);
  const fileCount = countFiles(visibleChildren);

  return (
    <div className={styles.rootSection}>
      <div
        className={styles.rootHeader}
        onClick={() => setCollapsed((v) => !v)}
        title={`${root.label} - ${fileCount} documentos`}
      >
        <span className={styles.rootToggle}>{collapsed ? "▸" : "▾"}</span>
        <span className={styles.rootLabel}>{root.label}</span>
        <span className={styles.rootCount}>{fileCount}</span>
      </div>

      {!collapsed && (
        <ul className={styles.docList}>
          {visibleChildren.length === 0 && root.note && (
            <li className={styles.emptyNote}>{root.note}</li>
          )}
          {visibleChildren.map((node) => (
            <DocItem
              key={node.id}
              node={node}
              onSelect={onSelect}
              filterText={filterText}
              isSelected={selectedNodeId === node.id}
              selectedNodeId={selectedNodeId}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

// -- DocTree principal ---------------------------------------------------------

export default function DocTree({
  roots,
  onSelect,
  filterText = "",
  selectedNodeId,
}: DocTreeProps) {
  const filteredRoots = roots
    .map((root) => ({
      root,
      visibleChildren: filterText
        ? root.children
            .map((node) => filterNode(node, filterText))
            .filter((node): node is DocNode => node !== null)
        : root.children,
    }))
    .filter(({ visibleChildren, root }) =>
      filterText ? visibleChildren.length > 0 : visibleChildren.length > 0 || !!root.note
    );

  if (roots.length === 0) {
    return (
      <div className={styles.emptyState}>
        No se encontró documentación. Verificá la ruta configurada.
      </div>
    );
  }

  if (filterText && filteredRoots.every(({ visibleChildren }) => visibleChildren.length === 0)) {
    return (
      <div className={styles.emptyState}>
        No se encontraron documentos que coincidan con "{filterText}".
      </div>
    );
  }

  return (
    <nav className={styles.tree} aria-label="Árbol de documentación">
      {filteredRoots.map(({ root, visibleChildren }) => (
        <RootSection
          key={root.id}
          root={root}
          visibleChildren={visibleChildren}
          onSelect={onSelect}
          filterText={filterText}
          selectedNodeId={selectedNodeId}
        />
      ))}
    </nav>
  );
}
