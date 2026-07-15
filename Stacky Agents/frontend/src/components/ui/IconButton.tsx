import { ButtonHTMLAttributes, ReactNode } from "react";
import styles from "./IconButton.module.css";

export type IconButtonVariant = "ghost" | "secondary" | "danger";
export type IconButtonSize = "sm" | "md";

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Texto accesible OBLIGATORIO (aria-label y title). */
  label: string;
  icon: ReactNode;
  /** Default "ghost". */
  variant?: IconButtonVariant;
  /** Default "md". */
  size?: IconButtonSize;
}

export function iconButtonPartKeys(
  variant: IconButtonVariant,
  size: IconButtonSize,
): string[] {
  return ["btn", variant, size];
}

export default function IconButton({
  label,
  icon,
  variant,
  size,
  className,
  type,
  ...rest
}: IconButtonProps) {
  const keys = iconButtonPartKeys(variant ?? "ghost", size ?? "md");
  const cls = keys.map((k) => styles[k]).filter(Boolean).join(" ");
  return (
    <button
      type={type ?? "button"}
      className={className ? `${cls} ${className}` : cls}
      aria-label={label}
      title={label}
      {...rest}
    >
      {icon}
    </button>
  );
}
