import { CSSProperties } from "react";
import styles from "./Skeleton.module.css";

export interface SkeletonProps {
  /** number → px; string se pasa tal cual. Default "100%". */
  width?: number | string;
  /** number → px; string se pasa tal cual. Default 14. */
  height?: number | string;
  /** number → px; string se pasa tal cual. Default "var(--radius-sm)". */
  radius?: number | string;
  /** Cantidad de barras apiladas. Default 1. */
  lines?: number;
  className?: string;
}

function toCssSize(v: number | string | undefined, fallback: string): string {
  if (v === undefined) return fallback;
  return typeof v === "number" ? `${v}px` : v;
}

export function skeletonStyle(
  width: number | string | undefined,
  height: number | string | undefined,
  radius: number | string | undefined,
): CSSProperties {
  return {
    width: toCssSize(width, "100%"),
    height: toCssSize(height, "14px"),
    borderRadius: toCssSize(radius, "var(--radius-sm)"),
  };
}

export default function Skeleton({ width, height, radius, lines, className }: SkeletonProps) {
  const n = Math.max(1, lines ?? 1);
  const bar = (key: number) => (
    <span
      key={key}
      className={className ? `${styles.skeleton} ${className}` : styles.skeleton}
      style={skeletonStyle(width, height, radius)}
      aria-hidden="true"
    />
  );
  if (n === 1) return bar(0);
  return <span className={styles.stack}>{Array.from({ length: n }, (_, i) => bar(i))}</span>;
}
