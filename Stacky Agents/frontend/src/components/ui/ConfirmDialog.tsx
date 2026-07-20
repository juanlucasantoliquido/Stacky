import { ReactNode } from "react";
import Dialog from "./Dialog";
import Button from "./Button";
import styles from "./Dialog.module.css";

/**
 * Plan 164 F1 — Confirmación de marca sobre la primitiva Dialog. Reemplaza al
 * diálogo de confirmación nativo del navegador (bloqueante, sin tema). Dos
 * botones; tone="danger" para acciones destructivas. Foco inicial: en Cancelar
 * si es danger (para no confirmar por Enter accidental), si no en el primario.
 */
export interface ConfirmDialogProps {
  open: boolean;
  title?: ReactNode;
  message: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: "default" | "danger";
  /** Se llama con true (primario) o false (Cancelar/✕/Escape/backdrop). */
  onResolve: (ok: boolean) => void;
}

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirmar",
  cancelLabel = "Cancelar",
  tone = "default",
  onResolve,
}: ConfirmDialogProps) {
  const danger = tone === "danger";
  return (
    <Dialog
      open={open}
      onClose={() => onResolve(false)}
      title={title}
      ariaLabel={title ? undefined : "Confirmación"}
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={() => onResolve(false)} autoFocus={danger}>
            {cancelLabel}
          </Button>
          <Button
            variant={danger ? "danger" : "primary"}
            onClick={() => onResolve(true)}
            autoFocus={!danger}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className={styles.message}>{message}</div>
    </Dialog>
  );
}
