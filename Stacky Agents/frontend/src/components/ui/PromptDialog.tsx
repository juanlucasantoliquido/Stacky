import { ReactNode, useState, KeyboardEvent } from "react";
import Dialog from "./Dialog";
import Button from "./Button";
import Field from "./Field";
import Input from "./Input";
import { textPromptCanConfirm } from "./dialogHostReducer";
import styles from "./Dialog.module.css";

/**
 * Plan 164 F1/A2 — Entrada de texto de marca sobre la primitiva Dialog.
 * Reemplaza la entrada nativa del navegador. Reusa Field+Input del plan 162
 * (PROHIBIDO <input> crudo). requiredText activa el type-to-confirm: confirmar
 * habilitado sólo si el texto coincide EXACTO. Resuelve string al confirmar,
 * null al descartar (✕/Cancelar/Escape/backdrop).
 */
export interface PromptDialogProps {
  open: boolean;
  title?: ReactNode;
  message?: ReactNode;
  label?: ReactNode;
  initialValue?: string;
  requiredText?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: "default" | "danger";
  /** Se llama con el texto (confirmar) o null (descartar). */
  onResolve: (value: string | null) => void;
}

export default function PromptDialog({
  open,
  title,
  message,
  label = "Valor",
  initialValue = "",
  requiredText,
  confirmLabel = "Confirmar",
  cancelLabel = "Cancelar",
  tone = "default",
  onResolve,
}: PromptDialogProps) {
  const [value, setValue] = useState(initialValue);
  const canConfirm = textPromptCanConfirm(value, requiredText);
  const danger = tone === "danger";

  const submit = () => {
    if (canConfirm) onResolve(value);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      submit();
    }
  };

  return (
    <Dialog
      open={open}
      onClose={() => onResolve(null)}
      title={title}
      ariaLabel={title ? undefined : "Entrada de texto"}
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={() => onResolve(null)}>
            {cancelLabel}
          </Button>
          <Button
            variant={danger ? "danger" : "primary"}
            onClick={submit}
            disabled={!canConfirm}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      {message ? <div className={styles.message}>{message}</div> : null}
      <div className={styles.promptField}>
        <Field label={label}>
          {(ctl) => (
            <Input
              {...ctl}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={onKeyDown}
              autoFocus
            />
          )}
        </Field>
      </div>
    </Dialog>
  );
}
