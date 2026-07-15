import { Skeleton } from "./ui";
import styles from "./SkeletonList.module.css";

/** Clamp defensivo: 1..24 filas. Pura y exportada para test. */
export function clampRows(rows: number): number {
  if (!Number.isFinite(rows)) return 1;
  return Math.max(1, Math.min(24, Math.floor(rows)));
}

interface SkeletonListProps {
  rows?: number;       // default 6
  rowHeight?: number;  // px, default 28
  gap?: "sm" | "md";   // default "sm"
  ariaLabel?: string;  // default "Cargando"
}

export default function SkeletonList({ rows = 6, rowHeight = 28, gap = "sm", ariaLabel = "Cargando" }: SkeletonListProps) {
  const n = clampRows(rows);
  return (
    <div
      className={gap === "md" ? `${styles.list} ${styles.gapMd}` : styles.list}
      role="status"
      aria-busy="true"
      aria-label={ariaLabel}
    >
      {Array.from({ length: n }).map((_, i) => (
        <Skeleton key={i} height={rowHeight} radius="var(--radius-md)" />
      ))}
    </div>
  );
}
