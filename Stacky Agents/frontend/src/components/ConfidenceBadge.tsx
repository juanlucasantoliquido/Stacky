/*
 * FA-35 — Confidence badge.
 * Renderiza score de confianza del output. < 70 muestra warning visible.
 */
import styles from "./ConfidenceBadge.module.css";

interface Props {
  overall: number;
  signals?: string[];
}

export default function ConfidenceBadge({ overall, signals }: Props) {
  const level = overall >= 80 ? "high" : overall >= 60 ? "mid" : "low";
  const tooltip = signals && signals.length > 0
    ? `Señales detectadas:\n${signals.slice(0, 6).join("\n")}`
    : "Score basado en señales del texto (hedge phrases, longitud, citaciones).";
  return (
    <span className={`${styles.badge} ${styles[level]}`} title={tooltip}>
      <span className={styles.icon}>{level === "high" ? "✓" : level === "mid" ? "◐" : "⚠"}</span>
      conf {overall}
    </span>
  );
}
