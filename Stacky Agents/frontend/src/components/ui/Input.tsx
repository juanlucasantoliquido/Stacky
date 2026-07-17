import { InputHTMLAttributes } from "react";
import styles from "./Input.module.css";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  /** Pinta el estado de error (borde --danger). El texto del error lo pone Field. */
  invalid?: boolean;
}

export function inputPartKeys(invalid: boolean): string[] {
  return invalid ? ["input", "invalid"] : ["input"];
}

export default function Input({ invalid, className, ...rest }: InputProps) {
  const cls = inputPartKeys(invalid ?? false).map((k) => styles[k]).filter(Boolean).join(" ");
  return <input className={className ? `${cls} ${className}` : cls} {...rest} />;
}
