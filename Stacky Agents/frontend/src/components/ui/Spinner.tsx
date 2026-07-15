import { CSSProperties } from "react";
import styles from "./Spinner.module.css";

export interface SpinnerProps {
  /** Diámetro en px. Default 14. */
  size?: number;
  /** Color del arco. Default "var(--accent)". */
  color?: string;
  /** Color de la pista. Default "var(--spinner-track)" (themeable por el plan 141). */
  trackColor?: string;
  /** Duración de la vuelta en ms. Default 800. */
  durationMs?: number;
  /** aria-label. Default "Cargando". */
  label?: string;
}

export function spinnerStyle(
  size: number | undefined,
  color: string | undefined,
  trackColor: string | undefined,
  durationMs: number | undefined,
): CSSProperties {
  const s = size ?? 14;
  return {
    width: `${s}px`,
    height: `${s}px`,
    borderWidth: "2px",
    borderColor: trackColor ?? "var(--spinner-track)",
    borderTopColor: color ?? "var(--accent)",
    animationDuration: `${durationMs ?? 800}ms`,
  };
}

export default function Spinner({ size, color, trackColor, durationMs, label }: SpinnerProps) {
  return (
    <span
      className={styles.spinner}
      style={spinnerStyle(size, color, trackColor, durationMs)}
      role="status"
      aria-label={label ?? "Cargando"}
    />
  );
}
