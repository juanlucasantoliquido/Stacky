import { SelectHTMLAttributes } from "react";
import styles from "./Select.module.css";

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  /** Pinta el estado de error (borde --danger). El texto del error lo pone Field. */
  invalid?: boolean;
}

export function selectPartKeys(invalid: boolean): string[] {
  return invalid ? ["select", "invalid"] : ["select"];
}

export default function Select({ invalid, className, children, ...rest }: SelectProps) {
  const cls = selectPartKeys(invalid ?? false).map((k) => styles[k]).filter(Boolean).join(" ");
  return (
    <select className={className ? `${cls} ${className}` : cls} {...rest}>
      {children}
    </select>
  );
}
