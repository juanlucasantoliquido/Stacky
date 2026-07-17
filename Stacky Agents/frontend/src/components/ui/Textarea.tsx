import { TextareaHTMLAttributes } from "react";
import styles from "./Textarea.module.css";

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  /** Pinta el estado de error (borde --danger). El texto del error lo pone Field. */
  invalid?: boolean;
}

export function textareaPartKeys(invalid: boolean): string[] {
  return invalid ? ["textarea", "invalid"] : ["textarea"];
}

export default function Textarea({ invalid, className, children, ...rest }: TextareaProps) {
  const cls = textareaPartKeys(invalid ?? false).map((k) => styles[k]).filter(Boolean).join(" ");
  return (
    <textarea className={className ? `${cls} ${className}` : cls} {...rest}>
      {children}
    </textarea>
  );
}
