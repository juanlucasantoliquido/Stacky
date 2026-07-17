import { CSSProperties, InputHTMLAttributes, ReactNode } from "react";
import styles from "./Checkbox.module.css";

export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label: ReactNode;
  /** En migraciones pasar la clase existente de la feature (ej. styles.checkboxRow). */
  labelClassName?: string;
  /** [Plan 162 F3] Style inline preexistente del label envolvente (byte-identidad). */
  labelStyle?: CSSProperties;
}

export function checkboxPartKeys(): string[] {
  return ["row"];
}

export default function Checkbox({ label, labelClassName, labelStyle, className, ...rest }: CheckboxProps) {
  const cls = checkboxPartKeys().map((k) => styles[k]).filter(Boolean).join(" ");
  return (
    <label className={labelClassName ?? cls} style={labelStyle}>
      <input type="checkbox" className={className} {...rest} />
      {label}
    </label>
  );
}
