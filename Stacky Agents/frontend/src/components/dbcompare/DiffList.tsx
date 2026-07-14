import { useState } from "react";
import type { DiffItem } from "./dbcompareTypes";
import styles from "./dbcompare.module.css";

const PAGE_SIZE = 100;

interface Props {
  items: DiffItem[];
  onSelectItem: (item: DiffItem) => void;
}

/** Plan 124 F5 — lista detallada de items filtrados, paginada en cliente de a 100 (sin
 * librerías de virtualización, per guardrail §3.1). */
export function DiffList({ items, onSelectItem }: Props) {
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const visible = items.slice(0, visibleCount);

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
        </div>
      ))}
      {items.length === 0 && <div className={styles.emptyState}>Sin diferencias con este filtro.</div>}
      {visibleCount < items.length && (
        <button onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}>Mostrar 100 más</button>
      )}
    </div>
  );
}

export default DiffList;
