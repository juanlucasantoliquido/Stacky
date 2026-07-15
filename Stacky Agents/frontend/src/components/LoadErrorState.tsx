import { formatLoadErrorMessage } from "../utils/loadError";
import styles from "./LoadErrorState.module.css";

/**
 * Hermano de EmptyState (plan 135 F1): se usa cuando una CARGA FALLÓ, para no
 * disfrazar un 500 de "no hay datos" (precedente: 500 mudo del revisor de PRs,
 * 2026-07-11). El botón Reintentar re-dispara LA MISMA carga que falló.
 */
interface Props {
  /** Qué se intentó cargar, en plural y con artículo: "los tickets", "las PRs". */
  what: string;
  /** El error atrapado (Error, string o cualquier cosa); se formatea y trunca. */
  error?: unknown;
  /** Re-dispara la misma carga. Si falta, no se muestra botón. */
  onRetry?: () => void;
  /** Variante de una sola línea para paletas/selectores/listas embebidas. */
  compact?: boolean;
}

export default function LoadErrorState({ what, error, onRetry, compact = false }: Props) {
  const detail = error === undefined || error === null ? null : formatLoadErrorMessage(error);
  if (compact) {
    return (
      <div className={styles.compact} role="alert">
        <span aria-hidden="true">⚠️</span>
        <span className={styles.compactText}>
          No se pudieron cargar {what}
          {detail ? `: ${detail}` : ""}
        </span>
        {onRetry && (
          <button type="button" className={styles.retryCompact} onClick={onRetry}>
            Reintentar
          </button>
        )}
      </div>
    );
  }
  return (
    <div className={styles.root} role="alert">
      <div className={styles.icon} aria-hidden="true">⚠️</div>
      <h3 className={styles.title}>No se pudieron cargar {what}</h3>
      {detail && <p className={styles.message}>{detail}</p>}
      {onRetry && (
        <button type="button" className={styles.action} onClick={onRetry}>
          ↻ Reintentar
        </button>
      )}
    </div>
  );
}
