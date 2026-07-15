import styles from "./RunButton.module.css";
import Spinner from "./ui/Spinner";

interface Props {
  state: "idle" | "running" | "cancelling";
  disabled?: boolean;
  onClick: () => void;
  onCancel?: () => void;
}

export default function RunButton({ state, disabled, onClick, onCancel }: Props) {
  if (state === "running") {
    return (
      <button
        className={`${styles.btn} ${styles.running}`}
        onClick={onCancel}
        disabled={!onCancel}
        title={onCancel ? "Click para cancelar" : "Procesando…"}
      >
        <Spinner size={13} color="var(--text-on-warn)" trackColor="rgba(28, 24, 16, 0.25)" durationMs={700} label="Procesando" />
        <span>Procesando…</span>
        {onCancel && <span className={styles.cancel}>✕</span>}
      </button>
    );
  }
  return (
    <button
      className={`${styles.btn} ${styles.idle}`}
      disabled={disabled}
      onClick={onClick}
    >
      ▶ EJECUTAR
    </button>
  );
}
