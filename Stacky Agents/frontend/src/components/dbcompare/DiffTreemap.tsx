import { useMemo, useState } from "react";
import type { DiffItem, SchemaDiff } from "./dbcompareTypes";
import { computeTreemapLayout, tableTreemapInputs, type TreemapRect } from "./treemapLayout";
import styles from "./dbcompare.module.css";

const STATE_LABEL: Record<TreemapRect["state"], string> = {
  added: "agregada",
  removed: "eliminada",
  changed: "cambiada",
  unchanged: "sin cambios",
};

const LEGEND_STATES: TreemapRect["state"][] = ["added", "removed", "changed", "unchanged"];

interface Props {
  diff: SchemaDiff;
  snapshotCounts: Record<string, number>;
  onSelectItem: (item: DiffItem) => void;
}

/**
 * Plan 124 F4 — mapa de diferencias: treemap SVG de tablas sobre treemapLayout.ts (ya testeado,
 * KPI-1). `snapshotCounts` lo arma DbComparePage a partir de `DbCompare.getSnapshot` (fallback
 * mapa vacío -> peso 1 uniforme, ya cubierto por `tableTreemapInputs`).
 */
export function DiffTreemap({ diff, snapshotCounts, onSelectItem }: Props) {
  const [onlyDiff, setOnlyDiff] = useState(false);

  const rects = useMemo(() => {
    let inputs = tableTreemapInputs(diff, snapshotCounts);
    if (onlyDiff) inputs = inputs.filter((i) => i.state !== "unchanged");
    return computeTreemapLayout(inputs, 1000, 560);
  }, [diff, snapshotCounts, onlyDiff]);

  const itemByKey = useMemo(() => {
    const m = new Map<string, DiffItem>();
    for (const item of diff.items) {
      if (item.object_type === "table") m.set(`${item.schema}.${item.name}`, item);
    }
    return m;
  }, [diff]);

  return (
    <div className={styles.treemapWrap}>
      <label>
        <input type="checkbox" checked={onlyDiff} onChange={(e) => setOnlyDiff(e.target.checked)} />
        {" "}Mostrar solo con diferencias
      </label>
      <svg viewBox="0 0 1000 560">
        {rects.map((r) => {
          const clipId = `dbc-clip-${r.key.replace(/[^a-zA-Z0-9]/g, "-")}`;
          const showLabel = r.w > 90 && r.h > 26;
          const item = itemByKey.get(r.key);
          return (
            <g
              key={r.key}
              className={styles.treemapCell}
              onClick={() => item && onSelectItem(item)}
              style={{ cursor: item ? "pointer" : "default" }}
            >
              <title>
                {r.label} — {STATE_LABEL[r.state]} — {r.weight} columnas
              </title>
              <rect
                x={r.x}
                y={r.y}
                width={r.w}
                height={r.h}
                fill={`var(--dbc-${r.state})`}
                stroke="var(--bg-panel)"
                strokeWidth={1}
              />
              {showLabel && (
                <>
                  <clipPath id={clipId}>
                    <rect x={r.x} y={r.y} width={r.w} height={r.h} />
                  </clipPath>
                  <text x={r.x + 6} y={r.y + 16} clipPath={`url(#${clipId})`} fontSize={11} fill="var(--text-primary)">
                    {r.label}
                  </text>
                </>
              )}
            </g>
          );
        })}
      </svg>
      <div className={styles.treemapLegend}>
        {LEGEND_STATES.map((s) => (
          <span key={s}>
            <span className={styles.statDot} style={{ background: `var(--dbc-${s})`, display: "inline-block" }} />
            {" "}{STATE_LABEL[s]}
          </span>
        ))}
      </div>
    </div>
  );
}

export default DiffTreemap;
