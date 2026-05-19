/**
 * DocTree.tsx — Árbol navegable de documentación (Feature #3)
 *
 * Recibe roots: DocRoot[] y onSelect(node: DocNode).
 * Expand/collapse por sección raíz.
 * Lista los headings de cada documento como subitems navegables.
 * Acepta filterText para filtrar nodos (Fase 3.C).
 */
import { useState } from "react";
import type { DocRoot, DocNode, DocHeading } from "../api/endpoints";
import styles from "./DocTree.module.css";

interface DocTreeProps {
  roots: DocRoot[];
  onSelect: (node: DocNode, heading?: DocHeading) => void;
  /** Texto de filtro (Fase 3.C). Vacío = sin filtro. */
  filterText?: string;
  /** Nodo actualmente seleccionado (para resaltar). */
  selectedNodeId?: string;
}

// ── helpers de filtro ─────────────────────────────────────────────────────────

function nodeMatchesFilter(node: DocNode, filter: string): boolean {
  if (!filter) return true;
  const lower = filter.toLowerCase();
  if (node.label.toLowerCase().includes(lower)) return true;
  return node.headings.some((h) => h.text.toLowerCase().includes(lower));
}

// ── sub-component: HeadingItem ────────────────────────────────────────────────

interface HeadingItemProps {
  heading: DocHeading;
  onClick: () => void;
  filterText: string;
}

function HeadingItem({ heading, onClick, filterText }: HeadingItemProps) {
  const isMatch =
    filterText && heading.text.toLowerCase().includes(filterText.toLowerCase());
  return (
    <li
      className={`${styles.headingItem} ${styles[`h${heading.level}`]} ${isMatch ? styles.filterMatch : ""}`}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      title={heading.text}
    >
      {heading.level === 1 ? "H1" : "H2"} {heading.text}
    </li>
  );
}

// ── sub-component: DocItem ────────────────────────────────────────────────────

interface DocItemProps {
  node: DocNode;
  onSelect: (node: DocNode, heading?: DocHeading) => void;
  filterText: string;
  isSelected: boolean;
}

function DocItem({ node, onSelect, filterText, isSelected }: DocItemProps) {
  const [expanded, setExpanded] = useState(false);
  const hasHeadings = node.headings.length > 0;

  // Con filtro activo, expandir automáticamente si matchea heading
  const autoExpand =
    filterText.length > 0 &&
    node.headings.some((h) => h.text.toLowerCase().includes(filterText.toLowerCase()));
  const showHeadings = expanded || autoExpand;

  return (
    <li className={`${styles.docItem} ${isSelected ? styles.selected : ""}`}>
      <div
        className={styles.docItemHeader}
        onClick={() => {
          onSelect(node);
          if (hasHeadings) setExpanded((v) => !v);
        }}
        title={node.path}
      >
        {hasHeadings && (
          <span className={styles.expandIcon}>
            {showHeadings ? "▾" : "▸"}
          </span>
        )}
        {!hasHeadings && <span className={styles.expandIcon}>&nbsp;&nbsp;</span>}
        <span className={styles.docLabel}>{node.label}</span>
        <span className={styles.headingCount}>
          {node.headings.length > 0 ? `${node.headings.length}h` : ""}
        </span>
      </div>

      {showHeadings && (
        <ul className={styles.headingList}>
          {node.headings.map((h, i) => (
            <HeadingItem
              key={i}
              heading={h}
              filterText={filterText}
              onClick={() => onSelect(node, h)}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

// ── sub-component: RootSection ────────────────────────────────────────────────

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

  return (
    <div className={styles.rootSection}>
      <div
        className={styles.rootHeader}
        onClick={() => setCollapsed((v) => !v)}
        title={`${root.label} — ${visibleChildren.length} documentos`}
      >
        <span className={styles.rootToggle}>{collapsed ? "▸" : "▾"}</span>
        <span className={styles.rootLabel}>{root.label}</span>
        <span className={styles.rootCount}>{visibleChildren.length}</span>
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
            />
          ))}
        </ul>
      )}
    </div>
  );
}

// ── DocTree principal ─────────────────────────────────────────────────────────

export default function DocTree({
  roots,
  onSelect,
  filterText = "",
  selectedNodeId,
}: DocTreeProps) {
  // Filtrar secciones y documentos por filterText
  const filteredRoots = roots
    .map((root) => ({
      root,
      visibleChildren: filterText
        ? root.children.filter((node) => nodeMatchesFilter(node, filterText))
        : root.children,
    }))
    .filter(({ visibleChildren, root }) =>
      filterText ? visibleChildren.length > 0 : true || root.note
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
