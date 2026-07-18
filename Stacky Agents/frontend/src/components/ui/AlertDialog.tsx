import { ReactNode } from "react";
import Dialog from "./Dialog";
import Button from "./Button";
import styles from "./Dialog.module.css";

/**
 * Plan 164 F1 — Aviso informativo de marca sobre la primitiva Dialog. Reemplaza
 * al aviso nativo bloqueante del navegador (para NO-errores; los errores van al
 * canal Toast — §2.2 del plan). Un solo botón OK.
 */
export interface AlertDialogProps {
  open: boolean;
  title?: ReactNode;
  message: ReactNode;
  okLabel?: string;
  /** Se llama al cerrar por cualquier vía (OK/✕/Escape/backdrop). */
  onResolve: () => void;
}

export default function AlertDialog({
  open,
  title,
  message,
  okLabel = "Entendido",
  onResolve,
}: AlertDialogProps) {
  return (
    <Dialog
      open={open}
      onClose={onResolve}
      title={title}
      ariaLabel={title ? undefined : "Aviso"}
      size="sm"
      footer={
        <Button variant="primary" onClick={onResolve} autoFocus>
          {okLabel}
        </Button>
      }
    >
      <div className={styles.message}>{message}</div>
    </Dialog>
  );
}
