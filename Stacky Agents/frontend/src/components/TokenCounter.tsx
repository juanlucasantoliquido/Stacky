import styles from "./TokenCounter.module.css";

interface Props {
  current: number;
  max: number;
}

export default function TokenCounter({ current, max }: Props) {
  const pct = Math.min(1, current / max);
  const color =
    pct < 0.6 ? "muted" : pct < 0.85 ? "warn" : "danger";
  return (
    <div className={styles.box}>
      <span className={`${styles.text} ${styles[color]}`}>
        {format(current)} / {format(max)} tokens
      </span>
      <div className={styles.bar}>
        <div
          className={`${styles.fill} ${styles[color]}`}
          style={{ width: `${pct * 100}%` }}
        />
      </div>
    </div>
  );
}

function format(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}
