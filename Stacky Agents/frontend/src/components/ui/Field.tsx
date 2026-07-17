import { CSSProperties, ReactNode, useId } from "react";
import styles from "./Field.module.css";

export interface FieldControlProps {
  id: string;
  "aria-invalid"?: true;
  "aria-describedby"?: string;
}

/** Lógica pura, testeable sin React. Orden de describedby: help antes que error. */
export function fieldControlProps(id: string, hasError: boolean, hasHelp: boolean): FieldControlProps {
  const describedBy = [hasHelp ? `${id}-help` : null, hasError ? `${id}-error` : null]
    .filter(Boolean)
    .join(" ");
  const out: FieldControlProps = { id };
  if (hasError) out["aria-invalid"] = true;
  if (describedBy) out["aria-describedby"] = describedBy;
  return out;
}

/** [ADICIÓN ARQUITECTO] Devuelve el id DOM del primer campo con error según el
    orden visual declarado, o null. Pura, testeable sin React ni DOM. */
export function firstErrorFieldId(
  prefix: string,
  domOrder: readonly string[],
  errors: Record<string, string>,
): string | null {
  const k = domOrder.find((key) => key in errors);
  return k ? `${prefix}-${k}` : null;
}

export interface FieldProps {
  label: ReactNode;
  /** Clase del label. En migraciones pasar SIEMPRE la clase existente de la feature
      (ej. styles.label del module.css del modal) para look byte-idéntico. */
  labelClassName?: string;
  /** [Plan 162 F3] Style inline preexistente del label (ej. EditProjectModal, sección
      workflow, con margen superior vía objeto de estilos). Aditivo: solo para preservar
      byte-identidad en migraciones de labels que ya tenían inline style; no usar en
      superficies nuevas. */
  labelStyle?: CSSProperties;
  help?: ReactNode;
  /** Texto de error inline. Truthy ⇒ aria-invalid + aria-describedby en el control. */
  error?: ReactNode;
  required?: boolean;
  /** Override del id; default useId(). */
  id?: string;
  /** ÚNICA forma de children: render-prop que recibe los props a esparcir en el control. */
  children: (ctl: FieldControlProps) => ReactNode;
}

export default function Field({ label, labelClassName, labelStyle, help, error, required, id, children }: FieldProps) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  const ctl = fieldControlProps(fieldId, Boolean(error), Boolean(help));
  return (
    <div className={styles.field}>
      <label htmlFor={fieldId} className={labelClassName ?? styles.label} style={labelStyle}>
        {label}
        {required ? <span className={styles.required} aria-hidden="true"> *</span> : null}
      </label>
      {children(ctl)}
      {help ? <div id={`${fieldId}-help`} className={styles.help}>{help}</div> : null}
      {error ? <div id={`${fieldId}-error`} className={styles.error} role="alert">{error}</div> : null}
    </div>
  );
}
