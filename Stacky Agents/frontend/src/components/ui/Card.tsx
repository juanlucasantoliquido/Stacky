import { ReactNode } from "react";
import styles from "./Card.module.css";

export type CardPadding = "none" | "sm" | "md";

export interface CardProps {
  children: ReactNode;
  /** Default "md". */
  padding?: CardPadding;
  /** box-shadow var(--shadow-2). Default false. */
  elevated?: boolean;
  className?: string;
}

const PAD_KEY: Record<CardPadding, string> = { none: "padNone", sm: "padSm", md: "padMd" };

export function cardPartKeys(padding: CardPadding, elevated: boolean): string[] {
  const keys = ["card", PAD_KEY[padding]];
  if (elevated) keys.push("elevated");
  return keys;
}

export default function Card({ children, padding, elevated, className }: CardProps) {
  const keys = cardPartKeys(padding ?? "md", elevated ?? false);
  const cls = keys.map((k) => styles[k]).filter(Boolean).join(" ");
  return <div className={className ? `${cls} ${className}` : cls}>{children}</div>;
}
