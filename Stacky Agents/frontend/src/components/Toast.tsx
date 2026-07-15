import styles from "./Toast.module.css";

/**
 * Toast compartido de la casa (plan 135 F5). Extraído del patrón ejemplar de
 * RecoverExecutionButton. Canal para resultados de ACCIONES (no de cargas:
 * eso es LoadErrorState). Variante warning = éxito con condición (p. ej.
 * requiere reinicio): NUNCA usar variante error para un éxito.
 */
export type ToastVariant = "success" | "warning" | "error";

export interface ToastState {
  variant: ToastVariant;
  /** Opcional: si falta, se renderiza solo el body + botón cerrar. */
  title?: string;
  body: string;
  correlationId?: string;
}

export default function Toast({
  toast,
  onClose,
}: {
  toast: ToastState;
  onClose: () => void;
}) {
  return (
    <div
      className={`${styles.toast} ${styles[`toast_${toast.variant}`]}`}
      data-correlation-id={toast.correlationId ?? undefined}
      role="alert"
      aria-live="assertive"
    >
      <div className={styles.toastHeader}>
        {toast.title ? (
          <strong className={styles.toastTitle}>{toast.title}</strong>
        ) : (
          <span />
        )}
        <button
          className={styles.toastClose}
          onClick={onClose}
          aria-label="Cerrar notificación"
        >
          ✕
        </button>
      </div>
      <p className={styles.toastBody}>{toast.body}</p>
    </div>
  );
}
