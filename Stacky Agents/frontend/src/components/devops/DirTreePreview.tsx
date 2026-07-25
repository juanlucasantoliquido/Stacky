/**
 * DirTreePreview (Plan 107 F4)
 *
 * Preview del árbol de directorios que se va a crear (sección Ambientes,
 * Paso 2), montado SOLO cuando STACKY_DEVOPS_ENV_TREE_PREVIEW_ENABLED está
 * ON (EnvironmentsSection.tsx). SOLO-LECTURA: no cambia qué se crea, solo
 * cómo se muestra lo que YA calculó /environments/plan.
 *
 * Lógica pura (nesting, rollup de status, conteos) vive en
 * devops/dirTreeModel.ts (F3, testeada aislada). Este componente es
 * deliberadamente delgado: solo estado de UI (expandido/colapsado, filtro).
 */
import React, { useMemo, useState } from 'react';
import { buildDirTree, rollupCounts, type DirTreeNode } from '../../devops/dirTreeModel';
import type { PlanEntry } from '../../devops/environmentModel';
import styles from './devops.module.css';

export interface DirTreePreviewProps {
  entries: PlanEntry[]; // del /plan
  sandboxActive?: boolean; // muestra badge "SANDBOX (pruebas)"
  rootLabel: string; // la raíz efectiva a mostrar como nodo raíz
}

type TreeFilter = 'all' | 'new' | 'conflicts';

const DEFAULT_EXPAND_DEPTH = 2; // "hasta 2 niveles" (plan F4, requisito UX #1)

function collectDefaultExpanded(nodes: DirTreeNode[], depth: number, acc: Set<string>): void {
  for (const node of nodes) {
    if (depth < DEFAULT_EXPAND_DEPTH && node.children.length > 0) {
      acc.add(node.path);
    }
    collectDefaultExpanded(node.children, depth + 1, acc);
  }
}

function nodeMatchesFilter(node: DirTreeNode, filter: TreeFilter): boolean {
  if (filter === 'all') return true;
  if (filter === 'new') return node.counts.to_create > 0;
  return node.counts.conflict > 0 || node.counts.unsafe > 0; // 'conflicts' (incluye unsafe)
}

function statusClass(status: DirTreeNode['status']): string {
  if (status === 'to_create') return styles.textSuccess;
  if (status === 'exists_ok') return styles.textMuted;
  return styles.textDanger; // 'mixed' | 'conflict' | 'unsafe'
}

function treeToText(nodes: DirTreeNode[], depth = 0): string {
  const lines: string[] = [];
  for (const node of nodes) {
    lines.push(`${'  '.repeat(depth)}${node.name} [${node.status}]`);
    if (node.children.length > 0) {
      lines.push(treeToText(node.children, depth + 1));
    }
  }
  return lines.filter(Boolean).join('\n');
}

const TreeRow: React.FC<{
  node: DirTreeNode;
  depth: number;
  expanded: Set<string>;
  onToggle: (path: string) => void;
  filter: TreeFilter;
}> = ({ node, depth, expanded, onToggle, filter }) => {
  if (!nodeMatchesFilter(node, filter)) return null;

  const hasChildren = node.children.length > 0;
  const isExpanded = expanded.has(node.path);
  const isDanger = node.status === 'mixed' || node.status === 'conflict' || node.status === 'unsafe';

  return (
    <div className={depth === 0 ? styles.dirTree__rootLevel : styles.dirTree__nested}>
      <div className={styles.dirTree__row}>
        {hasChildren ? (
          <button
            type="button"
            aria-expanded={isExpanded}
            aria-label={`${isExpanded ? 'Colapsar' : 'Expandir'} carpeta ${node.path}`}
            onClick={() => onToggle(node.path)}
            className={styles.dirTree__chip}
          >
            <span aria-hidden="true">{isExpanded ? '▾' : '▸'}</span> <span>{node.name}</span>
          </button>
        ) : (
          <span className={styles.dirTree__chipBare}>
            <span aria-hidden="true">▪</span> <span>{node.name}</span>
          </span>
        )}
        <span
          className={statusClass(node.status)}
          title={isDanger && node.selfReason ? node.selfReason : undefined}
        >
          {node.status}
        </span>
        {node.selfStatus === 'to_create' && (
          <span className={`${styles.textSuccess} ${styles.dirTree__meta}`}>
            nuevo
          </span>
        )}
      </div>
      {hasChildren && isExpanded && (
        <div>
          {node.children.map((child) => (
            <TreeRow key={child.path} node={child} depth={depth + 1} expanded={expanded} onToggle={onToggle} filter={filter} />
          ))}
        </div>
      )}
    </div>
  );
};

export const DirTreePreview: React.FC<DirTreePreviewProps> = ({ entries, sandboxActive, rootLabel }) => {
  const tree = useMemo(() => buildDirTree(entries), [entries]);
  const counts = useMemo(() => rollupCounts(tree), [tree]);
  const [expanded, setExpanded] = useState<Set<string>>(() => {
    const acc = new Set<string>();
    collectDefaultExpanded(tree, 0, acc);
    return acc;
  });
  const [filter, setFilter] = useState<TreeFilter>('all');
  const canCopy = typeof navigator !== 'undefined' && !!navigator.clipboard;

  const toggle = (path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const handleCopy = () => {
    if (!canCopy) return;
    void navigator.clipboard.writeText(`${rootLabel}\n${treeToText(tree)}`);
  };

  return (
    <div className={`${styles.panel} ${styles.dirTree__block}`}>
      <div className={styles.dirTree__head}>
        <strong>Raíz: {rootLabel}</strong>
        {sandboxActive === true && (
          <span className={`${styles.textWarn} ${styles.dirTree__strong}`}>
            SANDBOX — PRUEBAS: no es producción
          </span>
        )}
      </div>

      <p className={styles.dirTree__sub}>
        {counts.to_create} nuevas · {counts.exists_ok} existentes · {counts.conflict + counts.unsafe} conflictos
      </p>

      <div className={styles.dirTree__toolbar}>
        {(
          [
            ['all', 'Todo'],
            ['new', 'Solo nuevas'],
            ['conflicts', 'Solo conflictos'],
          ] as Array<[TreeFilter, string]>
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => setFilter(value)}
            className={`${filter === value ? styles.btnPrimary : undefined} ${styles.dirTree__btn}`}
          >
            {label}
          </button>
        ))}
        {canCopy && (
          <button type="button" onClick={handleCopy} className={styles.dirTree__btnEnd}>
            Copiar árbol
          </button>
        )}
      </div>

      <div>
        {tree.map((node) => (
          <TreeRow key={node.path} node={node} depth={0} expanded={expanded} onToggle={toggle} filter={filter} />
        ))}
      </div>
    </div>
  );
};
