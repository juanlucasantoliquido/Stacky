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
  /**
   * Plan 185 — botón de acción opcional (ej: "Deshacer"). Backward-compatible:
   * ningún caller existente lo pasa; si falta, no se renderiza.
   */
  action?: { label: string; onAction: () => void };
}

export default function Toast({
  toast,
  onClose,
  inStack = false,
}: {
  toast: ToastState;
  onClose: () => void;
  /**
   * Plan 185 — cuando el toast se renderiza DENTRO de un stack propio del host
   * (UndoToastHost), `inStack` desactiva su `position: fixed` para que el
   * contenedor gobierne el layout. Default false ⇒ comportamiento previo
   * (fijo esquina inferior derecha) intacto para todos los callers existentes.
   */
  inStack?: boolean;
}) {
  return (
    <div
      className={`${styles.toast} ${styles[`toast_${toast.variant}`]}${
        inStack ? ` ${styles.toast_inStack}` : ""
      }`}
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
      {toast.action ? (
        <button className={styles.toastAction} onClick={toast.action.onAction}>
          {toast.action.label}
        </button>
      ) : null}
    </div>
  );
}
