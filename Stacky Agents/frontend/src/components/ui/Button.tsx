import { ButtonHTMLAttributes, ReactNode } from "react";
import styles from "./Button.module.css";
import Spinner from "./Spinner";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Default "secondary" (el look del <button> global de theme.css). */
  variant?: ButtonVariant;
  /** Default "md". */
  size?: ButtonSize;
  /** Muestra Spinner a la izquierda y deshabilita. Default false. */
  loading?: boolean;
  iconLeft?: ReactNode;
  iconRight?: ReactNode;
}

export function buttonPartKeys(
  variant: ButtonVariant,
  size: ButtonSize,
  loading: boolean,
): string[] {
  const keys = ["btn", variant, size];
  if (loading) keys.push("loading");
  return keys;
}

export default function Button({
  variant,
  size,
  loading,
  iconLeft,
  iconRight,
  className,
  disabled,
  children,
  type,
  ...rest
}: ButtonProps) {
  const keys = buttonPartKeys(variant ?? "secondary", size ?? "md", loading ?? false);
  const cls = keys.map((k) => styles[k]).filter(Boolean).join(" ");
  return (
    <button
      type={type ?? "button"}
      className={className ? `${cls} ${className}` : cls}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? <Spinner size={12} color="currentColor" trackColor="rgba(255, 255, 255, 0.25)" /> : iconLeft}
      {children}
      {iconRight}
    </button>
  );
}
