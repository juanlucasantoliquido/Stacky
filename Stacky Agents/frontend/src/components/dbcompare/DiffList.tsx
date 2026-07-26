import { useEffect, useRef, useState } from "react";

import { useUiPerfFlags } from "../../hooks/useUiPerfFlags";
import { useVirtualList } from "../../hooks/useVirtualList";
import type { DiffItem } from "./dbcompareTypes";
import {
  cycleDecision,
  decisionFor,
  decisionHelp,
  decisionLabel,
  type TriageDecision,
  type TriageDoc,
} from "./triageLogic";
import styles from "./dbcompare.module.css";

const PAGE_SIZE = 100;

// Plan 174 F2 — altura fija de fila, requisito del motor de virtualización.
const DIFF_ROW_HEIGHT_PX = 32;

interface Props {
  items: DiffItem[];
  onSelectItem: (item: DiffItem) => void;
  /** Plan 176 F2 — doc de triage de la corrida. Sin él, la celda no aparece. */
  triage?: TriageDoc | null;
  triageEnabled?: boolean;
  onDecide?: (itemKey: string, decision: TriageDecision) => void;
}

/** Plan 124 F5 — lista detallada de items filtrados, paginada en cliente de a 100 (sin
 * librerías de virtualización, per guardrail §3.1).
 *
 * Plan 176 F2 — con el triage habilitado, cada fila gana una celda para curar la
 * decisión sin salir de la lista. Con la flag OFF la lista es idéntica a antes. */
export function DiffList({ items, onSelectItem, triage, triageEnabled, onDecide }: Props) {
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const conTriage = Boolean(triageEnabled && onDecide);

  // Plan 174 F2 — con miles de objetos, renderizar la lista entera degrada el
  // frame-rate del dashboard COMPLETO, no solo de esta lista.
  const flags = useUiPerfFlags();
  const virt = useVirtualList({
    total: items.length,
    rowHeightPx: DIFF_ROW_HEIGHT_PX,
    enabled: flags.virtualization,
  });
  const padTopRef = useRef<HTMLDivElement>(null);
  const padBottomRef = useRef<HTMLDivElement>(null);

  // Por ref y no como estilo inline en el JSX: el ratchet del plan 138 lo prohíbe.
  useEffect(() => {
    if (padTopRef.current) padTopRef.current.style.height = `${virt.padTopPx}px`;
    if (padBottomRef.current) padBottomRef.current.style.height = `${virt.padBottomPx}px`;
  }, [virt.padTopPx, virt.padBottomPx]);

  const visible = virt.isVirtualized
    ? items.slice(virt.start, virt.end)
    : items.slice(0, visibleCount);

  return (
    <div
      className={`${styles.diffList} ${virt.isVirtualized ? styles.diffListVirtual : ""}`}
      ref={virt.isVirtualized ? virt.containerRef : undefined}
      onScroll={virt.isVirtualized ? virt.onScroll : undefined}
    >
      {virt.isVirtualized && <div ref={padTopRef} />}
      {visible.map((item) => (
        <div
          key={`${item.object_type}.${item.schema}.${item.name}`}
          className={`${styles.diffRow} ${virt.isVirtualized ? styles.diffRowVirtual : ""}`}
          onClick={() => onSelectItem(item)}
        >
          <span className={styles.statDot} style={{ background: `var(--dbc-${item.severity})` }} />
          <strong>
            {item.schema}.{item.name}
          </strong>
          <span>{item.object_type}</span>
          <span>{item.action}</span>
          <span className={styles.recency}>{item.changes.map((c) => c.kind).join(", ")}</span>
          {conTriage && <TriageCell item={item} triage={triage} onDecide={onDecide!} />}
        </div>
      ))}
      {virt.isVirtualized && <div ref={padBottomRef} />}
      {items.length === 0 && <div className={styles.emptyState}>Sin diferencias con este filtro.</div>}
      {/* Con la lista virtualizada el scroll ya recorre todo: el botón de paginar
          sobraría y confundiría sobre cuántos objetos hay de verdad. */}
      {!virt.isVirtualized && visibleCount < items.length && (
        <button onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}>Mostrar 100 más</button>
      )}
    </div>
  );
}

/**
 * La celda de decisión. Cicla pendiente → confirmado → excluido con cada click.
 *
 * `stopPropagation` es obligatorio: la fila entera abre el drill-down, y sin eso
 * decidir abriría también el detalle en cada click.
 */
function TriageCell({
  item,
  triage,
  onDecide,
}: {
  item: DiffItem;
  triage: TriageDoc | null | undefined;
  onDecide: (itemKey: string, decision: TriageDecision) => void;
}) {
  // La item_key la emite el backend; sin ella no hay nada que decidir.
  const key = item.item_key;
  const actual = decisionFor(triage, key);

  if (!key) return null;

  return (
    <button
      type="button"
      className={`${styles.triageBtn} ${styles[`triage_${actual}`] ?? ""}`}
      title={decisionHelp(actual)}
      onClick={(e) => {
        e.stopPropagation();
        onDecide(key, cycleDecision(actual));
      }}
    >
      {decisionLabel(actual)}
    </button>
  );
}

export default DiffList;
