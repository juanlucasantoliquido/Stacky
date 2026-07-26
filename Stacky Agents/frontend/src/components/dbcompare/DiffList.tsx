import { useState } from "react";
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
  const visible = items.slice(0, visibleCount);
  const conTriage = Boolean(triageEnabled && onDecide);

  return (
    <div className={styles.diffList}>
      {visible.map((item) => (
        <div
          key={`${item.object_type}.${item.schema}.${item.name}`}
          className={styles.diffRow}
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
      {items.length === 0 && <div className={styles.emptyState}>Sin diferencias con este filtro.</div>}
      {visibleCount < items.length && (
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
