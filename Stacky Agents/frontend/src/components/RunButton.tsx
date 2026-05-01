import styles from "./RunButton.module.css";

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
        title="Cancelar"
      >
        Running ▮▮ {onCancel ? "(click to cancel)" : ""}
      </button>
    );
  }
  return (
    <button
      className={`${styles.btn} ${styles.idle}`}
      disabled={disabled}
      onClick={onClick}
    >
      ▶ RUN AGENT
    </button>
  );
}
